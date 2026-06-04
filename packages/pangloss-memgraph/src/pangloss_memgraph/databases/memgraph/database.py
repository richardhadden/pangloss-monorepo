import functools
import typing
from typing import Awaitable, Callable, Concatenate

import neo4j
from pangloss_core.settings import BaseSettings

class Database:
    settings: BaseSettings
    driver: neo4j.AsyncDriver

    _instances: dict[int, "Database"] = {}
    _initialised: bool = False

    def __init__(
        self, settings: "BaseSettings", instance_identifier: int | None = None
    ):
        if settings is None:
            return

        self.settings = settings
        self._initialise_driver()

        # Because @read_transaction and @write_transaction are decorators,
        # "self" is bound with non-functioning instance before initialisation of the db;
        # So we store each instance of this class, and use this
        # to look up the instance
        self.__class__._instances[instance_identifier or id(self)] = self

    def _initialise_driver(self):
        self.driver = neo4j.AsyncGraphDatabase.driver(
            self.settings.DB_URL,
            auth=(self.settings.DB_USER, self.settings.DB_PASSWORD),
            keep_alive=True,
        )

    def _check_driver(self):
        if self.driver._closed:
            self._initialise_driver()

    def read_transaction[ReturnType, **Params](
        self,
        func)
        """Decorator to run a database read transaction

        Wraps an asynchronous function taking a pangloss.neo4j.database.Transaction
        object as its first argument.

        ```
        @read_transaction
        def get_a_thing(tx: Transaction):
            await tx.run(<QUERY>, <PARAMS>)
        ```
        """

        async def wrapper(*args: Params.args, **kwargs: Params.kwargs) -> ReturnType:
            this: "Database" = self.__class__._instances[id(self)]
            this._check_driver()
            # async with neo4j.AsyncGraphDatabase.driver(uri, auth=auth) as driver:
            async with this.driver.session(
                database=this.settings.DB_DATABASE_NAME
            ) as session:
                records = await session.execute_read(func, *args, **kwargs)
                return records

        return wrapper

    def write_transaction[ReturnType, **Params](
        self,
        func: Callable[
            Concatenate[neo4j.AsyncManagedTransaction, Params],
            Awaitable[ReturnType | None],
        ]
        | Callable[
            Concatenate[neo4j.AsyncManagedTransaction, Params],
            Awaitable[ReturnType | None],
        ],
    ) -> Callable[Params, Awaitable[ReturnType | None]]:
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
            *args: Params.args,
            **kwargs: Params.kwargs,
        ) -> ReturnType | None:
            this: "Database" = self.__class__._instances[id(self)]
            this._check_driver()

            async with this.driver.session(
                database=this.settings.DB_DATABASE_NAME
            ) as session:
                records = None
                try:
                    records = await session.execute_write(func, **kwargs)
                except neo4j.exceptions.TransactionError:
                    pass

                return records

        return wrapper

    def with_database[ReturnType, **Params](
        self, func: Callable[["Database"], Awaitable[ReturnType]]
    ) -> Callable[Concatenate[Params], Awaitable[ReturnType]]:
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
        await DatabaseUtils.close_database_connection()

database: Database
