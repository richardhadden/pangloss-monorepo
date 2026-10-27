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

logger = logging.getLogger("pangloss.models.hooks")


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
    # For an update that put an earlier version back (`history`): the version it came from
    restored_from: int | None = None


type WriteListener = Callable[[WriteEvent], None]

after_write: list[WriteListener] = []


def emit_write_event(event: WriteEvent) -> None:
    """Tell each of `after_write` of a write. A listener that fails is logged, and the
    others are still told"""
    # (what was written, never what it said)
    logger.info(
        "Write: %s %s %s v%s by %r",
        event.op,
        event.model.__name__,
        event.id,
        event.version,
        event.user,
    )
    for listener in after_write:
        try:
            listener(event)
        except Exception:
            logger.exception(
                "A listener to writes failed for %s %s %s",
                event.op,
                event.model.__name__,
                event.id,
            )


# Properties for a new head node, which an installed app adds (`pangloss-review` writes `published: false` for
# a document that is to be reviewed). Each function is given the class (a `Document` or `Entity` subclass) and
# gives a dict, which may be empty. They are written with the node, in the same transaction as the creation, so
# there is no moment when the node is there without them. An update does not call them (it keeps the
# properties the node has: see `KEPT_PROPERTIES` of the Memgraph backend).
type HeadPropertiesFor = Callable[[type], dict[str, Any]]

new_head_properties: list[HeadPropertiesFor] = []


def properties_for_new_head(model: type) -> dict[str, Any]:
    """What the installed apps want written on a new head node of the class"""
    properties: dict[str, Any] = {}
    for function in new_head_properties:
        properties.update(function(model))
    return properties


# What the database returns, made into what the models read.
#
# A database returns its own types (Memgraph's driver, `neo4j.time.DateTime`). The models do
# not know which database they have: the database module adds a function here that
# converts what it knows of, anywhere in the data, and the models call `convert_from_database`
# on what they are made from. With none, the data is as it is.
type FromDatabaseConverter = Callable[[Any], Any]

from_database: list[FromDatabaseConverter] = []


def convert_from_database(data: Any) -> Any:
    for converter in from_database:
        data = converter(data)
    return data
