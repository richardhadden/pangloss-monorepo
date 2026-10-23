"""What happens after a write: a way for an installed app to react to it.

A database module calls `emit_write_event` **after** a write to a head node has committed
(never inside the transaction, which may be run again). Whoever wants to know of writes
(such as `pangloss-history`) adds a function to `after_write`. With none, nothing is done.

A listener is called at once, in the request that made the write, so it must be quick (put
the work on a queue). One that raises is logged and ignored: a listener never fails a write.
"""

import dataclasses
import datetime
import logging
from collections.abc import Callable
from typing import Any, Literal
from uuid import UUID

logger = logging.getLogger("pangloss.hooks")


@dataclasses.dataclass(frozen=True)
class WriteEvent:
    """A committed write to a head node (a Document or an Entity)"""

    op: Literal["create", "update", "delete", "undelete"]
    # The model, as `Document` or `Entity` subclass
    model: type
    id: UUID
    # The version of the head node: the one this write made (create is 1, an update is one
    # more than before). A delete or undelete changes no content, and the version is
    # the one it had at the time
    version: int
    user: str
    at: datetime.datetime
    # The validated write form (the `CreateDB` or `UpdateDB` instance), with the ids of
    # everything in it. `None` for delete and undelete
    payload: Any | None = None
    # The entities that this write made, named in a document with `create_new` and not
    # there before: each is the `CreateDB` instance of an entity, and a head node of its own,
    # at version 1
    created_entities: tuple[Any, ...] = ()


type WriteListener = Callable[[WriteEvent], None]

after_write: list[WriteListener] = []


def emit_write_event(event: WriteEvent) -> None:
    """Tell each of `after_write` of a write. A listener that fails is logged, and the
    others are still told"""
    for listener in list(after_write):
        try:
            listener(event)
        except Exception:
            logger.exception(
                "A listener to writes failed for %s %s %s",
                event.op,
                event.model.__name__,
                event.id,
            )
