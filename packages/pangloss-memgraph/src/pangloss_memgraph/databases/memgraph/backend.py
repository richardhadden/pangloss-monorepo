"""What the packages that write their own queries (typology, calendar) take from this backend: see `pangloss_core.backend`"""

import re
from collections.abc import Sequence
from typing import Any

import neo4j
from pangloss_core.storage import PanglossStorageError

from pangloss_memgraph.databases.memgraph.database import (
    Database,
    Transaction,
    current,
    timeout_from_setting,
    write_transaction,
)
from pangloss_cypher import fragments
from pangloss_cypher.visibility import unpublished_visible

__all__ = [
    "Database",
    "Transaction",
    "database",
    "dialect",
    "ensure_lock",
    "fragments",
    "install_query_module",
    "lock",
    "timeout_from_setting",
    "unpublished_visible",
    "user_exists",
]


# The database in use (`database().read_transaction`, `database().driver`, ...)
database = current

# The backend's `Dialect` (the same as `database().dialect`)
dialect = Database.dialect


async def ensure_lock(key: str) -> None:
    """Make the lock node of the key, in a transaction of its own, before the transaction that locks it is opened. (A
    transaction that makes the node cannot be retried over it: if two make it at once the second is refused at its commit,
    which the driver does not try again; and a transaction does not see a node made after it began.) Harmless if it is there"""

    @write_transaction
    async def make(tx: Transaction) -> None:
        await (await tx.run("MERGE (:PGLock {key: $key})", key=key)).consume()

    try:
        await make()
    except neo4j.exceptions.ClientError as error:
        if "unique constraint" not in str(error).lower():
            raise
        # (another made it at the same moment, which is all that was wanted)


async def lock(tx: Transaction, key: str) -> None:
    """Make this transaction conflict with every other that locks the same `key`, until it ends: the other is made to run again, and then
    sees what the first did. Without it, two changes that are each right alone can together be wrong (two moves in a
    hierarchy that make a loop): what two transactions add does not conflict. The lock is a node of its own (`:PGLock {key}`,
    unique); `ensure_lock(key)` makes it, before the transaction is opened."""
    taken = await (
        await tx.run(
            "MATCH (l:PGLock {key: $key}) SET l.writes = coalesce(l.writes, 0) + 1 RETURN count(l) AS taken",
            key=key,
        )
    ).single()
    if not taken or not taken["taken"]:
        raise RuntimeError(f"There is no lock {key!r}: ensure_lock({key!r}) makes it")


async def user_exists(username: str) -> bool:
    in_use = current()
    driver = await in_use.ensure_driver()
    async with driver.session(
        database=in_use.settings.DATABASE.DATABASE_NAME
    ) as session:
        result = await session.run(
            "MATCH (u:PGUser {username: $username}) RETURN u LIMIT 1",
            username=username,
        )
        return await result.single() is not None


async def _auto_commit(query: str, **parameters: Any) -> list[dict[str, Any]]:
    """Run a query in a transaction of its own (Memgraph refuses the procedures of `mg` that change module files in a
    transaction of several commands, as it does DDL)"""
    in_use = current()
    driver = await in_use.ensure_driver()
    async with driver.session(
        database=in_use.settings.DATABASE.DATABASE_NAME
    ) as session:
        result = await session.run(query, parameters)  # ty: ignore[invalid-argument-type]
        rows = await result.data()
        await result.consume()
        return rows


_MODULE_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


async def install_query_module(
    name: str, source: str, expects: Sequence[str] = (), library: bool = False
) -> bool:
    """Put the Python text `source` into the database as the query module `name` (without `.py`; a module of that name
    may import another installed beside it). Nothing is written if the module is there with that text already (False);
    a module that differs is replaced, and one that is not there made (True). Callable at once, by `CALL name.proc(...)`.

    Then it is checked that the module loaded: it must have a procedure or a function (unless it is a `library`, a
    module of helpers that others import), and each of `expects` (names without the module's) must be among them.
    Memgraph does not say why a module did not load (an import that fails leaves the file with nothing in it): its
    reason is in the database's own log, which the error says."""
    if not _MODULE_NAME.match(name):
        raise ValueError(f"{name!r} cannot be the name of a query module")
    files = await _auto_commit("CALL mg.get_module_files() YIELD path RETURN path")
    path = next(
        (row["path"] for row in files if str(row["path"]).endswith(f"/{name}.py")),
        None,
    )
    if path is not None:
        rows = await _auto_commit(
            "CALL mg.get_module_file($path) YIELD content RETURN content", path=path
        )
        if rows and rows[0]["content"] == source:
            written = False
        else:
            await _auto_commit(
                "CALL mg.update_module_file($path, $source)", path=path, source=source
            )
            written = True
    else:
        await _auto_commit(
            "CALL mg.create_module_file($file, $source) YIELD path RETURN path",
            file=f"{name}.py",
            source=source,
        )
        written = True
    if library:
        return written

    prefix = f"{name}."
    names = {
        str(row["name"]).removeprefix(prefix)
        for query in (
            "CALL mg.procedures() YIELD name RETURN name",
            "CALL mg.functions() YIELD name RETURN name",
        )
        for row in await _auto_commit(query)
        if str(row["name"]).startswith(prefix)
    }
    where = "Memgraph gives the reason only in its own log (`docker logs`, or the file of `--log-file`)"
    if not names:
        raise PanglossStorageError(
            f"The query module {name} was installed but did not load: it has no procedure or function. {where}"
        )
    missing = [expected for expected in expects if expected not in names]
    if missing:
        raise PanglossStorageError(
            f"The query module {name} was installed but has no {', '.join(missing)} (it has "
            f"{', '.join(sorted(names))}). If it should, {where}"
        )
    return written
