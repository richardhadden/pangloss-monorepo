import logging
import time
from collections.abc import Awaitable, Callable
from typing import Any, ClassVar, Concatenate

import neo4j
from pangloss_core.settings import BaseSettings
from pangloss_models.exceptions import PanglossReadOnlyError

from pangloss_memgraph.databases.memgraph.settings import MemgraphDatabaseSettings

Transaction = neo4j.AsyncManagedTransaction

logger = logging.getLogger("pangloss.memgraph.transactions")
queries = logging.getLogger("pangloss.memgraph.queries")

MAX_LOGGED_QUERY = 600


class LoggedTransaction:
    """A transaction that logs each statement it runs, at DEBUG: the query and the *names* of its
    parameters (never their values, which are the user's data), and how long the server took to
    take it up. Only used when that is being logged; anything else is the transaction's."""

    def __init__(self, tx: neo4j.AsyncManagedTransaction) -> None:
        self._tx = tx

    async def run(self, query: Any, parameters: Any = None, **kwargs: Any) -> Any:
        started = time.monotonic()
        result = await self._tx.run(query, parameters, **kwargs)
        names = sorted({*(parameters or {}), *kwargs})
        text = " ".join(str(query).split())
        queries.debug(
            "(%.0f ms) %s%s  params: %s",
            (time.monotonic() - started) * 1000,
            text[:MAX_LOGGED_QUERY],
            "..." if len(text) > MAX_LOGGED_QUERY else "",
            ", ".join(names) or "none",
        )
        return result

    def __getattr__(self, name: str) -> Any:
        return getattr(self._tx, name)


def slow_query_ms(settings: BaseSettings) -> int:
    return getattr(settings, "SLOW_QUERY_MS", 500)


async def timed[T](
    database: Database,
    kind: str,
    func: Callable[..., Awaitable[T]],
    run: Callable[[], Awaitable[T]],
) -> T:
    """Run a transaction, logging how long it took (a warning if that is over `SLOW_QUERY_MS`), and
    an error if the database cannot be reached"""
    started = time.monotonic()
    try:
        return await run()
    except (
        neo4j.exceptions.ServiceUnavailable,
        neo4j.exceptions.SessionExpired,
    ) as error:
        logger.error(
            "The database could not be reached (%s transaction %s): %s",
            kind,
            getattr(func, "__qualname__", func),
            error,
        )
        raise
    finally:
        elapsed = (time.monotonic() - started) * 1000
        threshold = getattr(database, "slow_query_threshold", None)
        slow = elapsed > (
            threshold if threshold is not None else slow_query_ms(database.settings)
        )
        logger.log(
            logging.WARNING if slow else logging.DEBUG,
            "%s transaction %s took %.0f ms%s",
            kind,
            getattr(func, "__qualname__", func),
            elapsed,
            " (slow)" if slow else "",
        )


def timeout_from_setting(name: str, default: float):
    """Mark a transaction function as one the database stops after the number of seconds that the setting
    `name` has (`default` if there is none; 0 is no limit). The driver sends it with the transaction, and
    Memgraph stops the query: otherwise a query that is too big runs until it ends or the server's own
    limit (ten minutes) is reached."""

    def mark[F: Callable[..., Any]](func: F) -> F:
        func.timeout_setting = (name, default)  # type: ignore
        return func

    return mark


def logging_queries(
    func: Callable[..., Awaitable[Any]],
) -> Callable[..., Awaitable[Any]]:
    """`func`, given a transaction that logs its statements if DEBUG is on for them"""

    async def logged(
        tx: neo4j.AsyncManagedTransaction, *args: Any, **kwargs: Any
    ) -> Any:
        if queries.isEnabledFor(logging.DEBUG):
            tx = LoggedTransaction(tx)  # ty: ignore[invalid-assignment]
        return await func(tx, *args, **kwargs)

    logged.__qualname__ = getattr(func, "__qualname__", "transaction")
    return logged


class Database:
    settings: BaseSettings[MemgraphDatabaseSettings]
    driver: neo4j.AsyncDriver

    _instances: dict[int, Database] = {}
    _initialised: bool = False
    default: ClassVar[Database]
    # True while this process is making a bulk load (`bulk.bulk_ingest`), which holds the migration
    # lock itself: its own writes are let through, everyone else's are refused
    bulk_loading: bool = False
    # If set, what `SLOW_QUERY_MS` is for this process (a bulk load raises it: with many writers at
    # once nearly every write is "slow", and a warning for each says nothing)
    slow_query_threshold: int | None = None

    def __init__(self, settings: BaseSettings, instance_identifier: int | None = None):
        if settings is None:
            return

        self.settings = settings
        self.__class__.default = self

    async def _initialise_driver(self):
        assert isinstance(self.settings.DATABASE, MemgraphDatabaseSettings)
        self.driver = neo4j.AsyncGraphDatabase.driver(
            self.settings.DATABASE.DB_URL,
            auth=(
                self.settings.DATABASE.DB_USERNAME,
                self.settings.DATABASE.DB_PASSWORD,
            ),
            keep_alive=True,
            max_transaction_retry_time=10.0,
        )

    async def _check_driver(self):
        if self.driver._closed:
            await self._initialise_driver()

    def read_transaction[T, **P](
        self,
        func: Callable[Concatenate[neo4j.AsyncManagedTransaction, P], Awaitable[T]],
    ) -> Callable[P, Awaitable[T]]:
        """Decorator to run a database read transaction

        Wraps an asynchronous function taking a pangloss.neo4j.database.Transaction
        object as its first argument.

        ```
        @read_transaction
        def get_a_thing(tx: Transaction):
            await tx.run(<QUERY>, <PARAMS>)
        ```
        """

        async def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:

            await self._check_driver()

            work = logging_queries(func)
            limit = getattr(func, "timeout_setting", None)
            if limit is not None:
                seconds = getattr(self.settings, limit[0], limit[1])
                if seconds:
                    work = neo4j.unit_of_work(timeout=float(seconds))(work)

            async def run() -> T:
                async with self.driver.session(
                    database=self.settings.DATABASE.DATABASE_NAME
                ) as session:
                    return await session.execute_read(work, *args, **kwargs)

            return await timed(self, "read", func, run)

        return wrapper

    def write_transaction[T, **P](
        self,
        func: Callable[Concatenate[neo4j.AsyncManagedTransaction, P], Awaitable[T]],
    ) -> Callable[P, Awaitable[T]]:
        """Decorator to run a database write transaction

        Wraps an asynchronous function taking a pangloss.neo4j.database.Transaction
        object as its first argument. If the function raises, the transaction is
        rolled back and the exception propagates. While `pangloss migrate` is running
        (it holds a lock in the database) nothing is written: this raises
        `PanglossReadOnlyError`, from inside the transaction, before the function.

        ```
        @write_transaction
        def save_a_thing(tx: Transaction):
            await tx.run(<QUERY>, <PARAMS>)
        ```
        """

        async def wrapper(
            *args: P.args,
            **kwargs: P.kwargs,
        ) -> T:
            await self._check_driver()

            async def not_while_migrating(tx, *a, **k):
                if not self.bulk_loading:
                    await refuse_while_migrating(tx)
                return await func(tx, *a, **k)

            async def run() -> T:
                async with self.driver.session(
                    database=self.settings.DATABASE.DATABASE_NAME
                ) as session:
                    return await session.execute_write(
                        logging_queries(not_while_migrating), *args, **kwargs
                    )

            return await timed(self, "write", func, run)

        return wrapper

    def with_database[ReturnType, **Params](
        self, func: Callable[[Database], Awaitable[ReturnType]]
    ) -> Callable[Params, Awaitable[ReturnType]]:
        """Decorator to allow access to the database instance inside a function,
        taking a `database` argument as its first argument"""

        async def wrapper(*args, **kwargs) -> ReturnType:
            this: Database = self.__class__._instances[id(self)]
            result = await func(this, *args, **kwargs)
            return result

        return wrapper

    @staticmethod
    def initialise_default_database(settings: BaseSettings) -> Database:

        database = Database(settings=settings)
        return database

    async def close(self):
        await self.driver.close()


async def refuse_while_migrating(tx: neo4j.AsyncManagedTransaction) -> None:
    """Raise `PanglossReadOnlyError` if a migration is running (it holds a `PGMigrationLock`). Called
    in the transaction of a write, so a write that began after the lock was taken is refused;
    one that was already running when it was taken is not waited for."""
    result = await tx.run("MATCH (l:PGMigrationLock) RETURN count(l) AS locked")
    row = await result.single()
    if row and row["locked"]:
        raise PanglossReadOnlyError(
            "The database is being migrated: it can be read, and not written to, until that is done "
            "(if no migration is running, `pangloss migrate --unlock`)"
        )
