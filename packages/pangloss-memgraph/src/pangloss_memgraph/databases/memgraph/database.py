import functools
import typing
from typing import Any, Awaitable, Callable, Concatenate, Coroutine, cast

import neo4j
from pangloss_core.settings import BaseSettings

from pangloss_memgraph.databases.memgraph.settings import MemgraphDatabaseSettings

Transaction = neo4j.AsyncManagedTransaction


class Database:
    settings: BaseSettings[MemgraphDatabaseSettings]
    driver: neo4j.AsyncDriver

    _instances: dict[int, "Database"] = {}
    _initialised: bool = False
    default: "Database"

    def __init__(self, settings: BaseSettings, instance_identifier: int | None = None):
        if settings is None:
            return

        self.settings = settings

        # Because @read_transaction and @write_transaction are decorators,
        # "self" is bound with non-functioning instance before initialisation of the db;
        # So we store each instance of this class, and use this
        # to look up the instance
        self.__class__._instances[instance_identifier or id(self)] = self

        global database
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

            this: Database = self.__class__._instances[id(self)]
            await this._check_driver()

            async with this.driver.session(
                database=this.settings.DATABASE.DATABASE_NAME
            ) as session:
                records = await session.execute_read(func, *args, **kwargs)
                return records

        return wrapper

    def write_transaction[T, **P](
        self,
        func: Callable[Concatenate[neo4j.AsyncManagedTransaction, P], Awaitable[T]],
    ) -> Callable[P, Awaitable[T | None]]:
        """Decorator to run a database read transaction

        Wraps an asynchronous function taking a pangloss.neo4j.database.Transaction
        object as its first argument.

        ```
        @read_transaction
        def get_a_thing(tx: Transaction):
            await tx.run(<QUERY>, <PARAMS>)
        ```
        """

        async def wrapper(
            *args: P.args,
            **kwargs: P.kwargs,
        ) -> T | None:
            this: "Database" = self.__class__._instances[id(self)]
            await this._check_driver()

            async with this.driver.session(
                database=this.settings.DATABASE.DATABASE_NAME
            ) as session:
                records = None
                try:
                    records = await session.execute_write(func, *args, **kwargs)
                except neo4j.exceptions.TransactionError:
                    pass

                return records

        return wrapper

    def with_database[ReturnType, **Params](
        self, func: Callable[["Database"], Awaitable[ReturnType]]
    ) -> Callable[Params, Awaitable[ReturnType]]:
        """Decorator to allow access to the database instance inside a function,
        taking a `database` argument as its first argument"""

        async def wrapper(*args, **kwargs) -> ReturnType:
            this: "Database" = self.__class__._instances[id(self)]
            result = await func(this, *args, **kwargs)
            return result

        return wrapper

    @staticmethod
    def initialise_default_database(settings: "BaseSettings") -> "Database":
        global database
        database = Database(settings=settings, instance_identifier=id(database))
        return database

    async def close(self):
        await self.driver.close()
        this: Database = self.__class__._instances[id(self)]
        await this.driver.close()


database: "Database" = Database(settings=None)  # type: ignore
