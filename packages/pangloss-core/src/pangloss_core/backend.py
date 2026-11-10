"""The database backend, for the packages that need to reach the graph and must not name one.

A backend that runs Cypher (its `Storage` has the capability `cypher`; see `pangloss_core.storage`) has a module `backend`
that gives the names of `Backend`. An add-on package (typology, calendar) uses them through `current()`:

```python
from pangloss_core import backend

backend.current().database()  # the database in use
```

and annotates a transaction as `backend.Transaction`. (`pangloss-users` and `pangloss-review` use the backend's
`exposed_functions` instead, for what is theirs to do. This module is for the packages that write their own queries.)
See `implementation_docs/backend-neutral-addons.md`.
"""

from collections.abc import Awaitable, Callable
from typing import Any, Protocol


class Transaction(Protocol):
    """What a package may do with a transaction: run a query (`await tx.run(query, parameters, **named)`, giving a result
    that is iterated with `async for` and has `single()` and `consume()`)"""

    async def run(self, query: str, parameters: Any = None, **named: Any) -> Any: ...


class Backend(Protocol):
    """The names that every backend's `backend` module gives"""

    Database: Any
    """The class"""

    database: Callable[[], Any]
    """`database()`: the database in use (a `Database`), which has `read_transaction` and `write_transaction` decorators"""

    timeout_from_setting: Callable[..., Any]
    """`@timeout_from_setting("SEARCH_TIMEOUT_SECONDS", 30)` under a transaction decorator: the time a read may take. A read
    that takes longer raises `PanglossSearchTimeoutError`"""

    unpublished_visible: Callable[[], bool]
    """Whether the request in progress may see what is not published"""

    ensure_lock: Callable[[str], Awaitable[None]]
    """`await ensure_lock(key)` before the transaction that locks the key is opened: makes the lock's node"""

    lock: Callable[[Any, str], Awaitable[None]]
    """`await lock(tx, key)`: until the transaction ends, any other transaction that locks the same key waits for it (or runs
    again), and then sees what it did. For a check that must not be raced"""

    user_exists: Callable[[str], Awaitable[bool]]
    """Whether there is a user of that name"""

    fragments: Any
    """Pieces of Cypher that know how models are stored (`pangloss_cypher.fragments`): `visible(node)`, the one rule of
    what a reader sees (the query gives `$see_unpublished`), `not_deleted(node)`, `head_of(node, as_)`, and the checked
    names `label(name)` and `field_edge(field)`. A query that reads model data uses them, not a copy of the rule"""


def current(storage: str | None = None) -> Backend:
    """The backend of the project (its settings' `STORAGE`), or of the storage named (`pangloss_neo4j:storage`)"""
    from pangloss_core.storage import load, storage_of

    return (load(storage) if storage else storage_of()).cypher
