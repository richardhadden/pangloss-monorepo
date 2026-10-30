"""The database backend, for the packages that need to reach the graph and must not name one.

A backend (`settings.DATABASE_MODULE`, such as `pangloss_memgraph.databases.memgraph`) has a module `backend` that gives the
names of `Backend`. An add-on package (typology, calendar) uses them through `current()`:

```python
from pangloss_core import backend

backend.current().Database.default
```

and annotates a transaction as `backend.Transaction`. (`pangloss-users` and `pangloss-review` use the backend's
`exposed_functions` instead, for what is theirs to do. This module is for the packages that write their own queries.)
See `docs/backend-neutral-addons.md`.
"""

import importlib
from collections.abc import Awaitable, Callable
from typing import Any, Protocol

from pangloss_core import settings


class Transaction(Protocol):
    """What a package may do with a transaction: run a query (`await tx.run(query, parameters, **named)`, giving a result
    that is iterated with `async for` and has `single()` and `consume()`)"""

    async def run(self, query: str, parameters: Any = None, **named: Any) -> Any: ...


class Backend(Protocol):
    """The names that every backend's `backend` module gives"""

    Database: Any
    """The class: `Database.default` is the one in use; it has `read_transaction` and `write_transaction` decorators"""

    timeout_from_setting: Callable[..., Any]
    """`@timeout_from_setting("SEARCH_TIMEOUT_SECONDS", 30)` under a transaction decorator: the time a read may take. A read
    that takes longer raises `PanglossSearchTimeoutError`"""

    unpublished_visible: Callable[[], bool]
    """Whether the request in progress may see what is not published"""

    user_exists: Callable[[str], Awaitable[bool]]
    """Whether there is a user of that name"""


def module_name(database_module: str | None = None) -> str:
    return f"{database_module or settings.SETTINGS.DATABASE_MODULE}.backend"


def current(database_module: str | None = None) -> Backend:
    """The backend of the project (`DATABASE_MODULE`), or of the module named"""
    return importlib.import_module(module_name(database_module))  # ty: ignore[invalid-return-type]
