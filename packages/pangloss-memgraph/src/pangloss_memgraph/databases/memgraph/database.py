from collections.abc import Awaitable, Callable
from typing import ClassVar, Concatenate

import neo4j
from pangloss_core.settings import BaseSettings
from pangloss_models.exceptions import PanglossReadOnlyError

from pangloss_memgraph.databases.memgraph.settings import MemgraphDatabaseSettings

Transaction = neo4j.AsyncManagedTransaction


class Database:
    settings: BaseSettings[MemgraphDatabaseSettings]
    driver: neo4j.AsyncDriver

    _instances: dict[int, Database] = {}
    _initialised: bool = False
    default: ClassVar[Database]

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

            async with self.driver.session(
                database=self.settings.DATABASE.DATABASE_NAME
            ) as session:
                return await session.execute_read(func, *args, **kwargs)

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
                await refuse_while_migrating(tx)
                return await func(tx, *a, **k)

            async with self.driver.session(
                database=self.settings.DATABASE.DATABASE_NAME
            ) as session:
                return await session.execute_write(not_while_migrating, *args, **kwargs)

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
