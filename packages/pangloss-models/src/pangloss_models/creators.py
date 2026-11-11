"""Who made a head node: one or more people, and perhaps a toolchain (a program that made the data from what a
person prepared), at a version and on a date.

`meta.created_by` of a read is a list of `Creator`. A write is made by the user of the request; an admin may say
that it is made by others (`save(created_by=[...], toolchain=ToolchainRun(...))`), and the write then records them
as the creators and the admin as who uploaded it (`meta.uploaded_by`).
"""

import contextlib
import contextvars
import dataclasses
import datetime
import json
from collections.abc import Generator, Iterable, Sequence
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel


class Creator(BaseModel):
    """One of those who made an item: a person, or a toolchain at a version and on a date"""

    model_config = ConfigDict(
        alias_generator=to_camel, populate_by_name=True, frozen=True
    )

    username: str
    kind: Literal["user", "toolchain"] = "user"
    version: str | None = None
    date: datetime.date | None = None


@dataclasses.dataclass(frozen=True)
class ToolchainRun:
    """A toolchain as it was run to make some data: its name (a user of kind `toolchain`), and which version of it,
    on which date"""

    name: str
    version: str | None = None
    date: datetime.date | None = None


def creators_from(value: Any) -> list[dict[str, Any]]:
    """What a database or a caller gives as the creators, as a list of what a `Creator` is made from: a name (a
    record with one creator, or older data), JSON text of a list (a nested node made by several), a list of names
    or of maps (in the order of `position`, which a stored edge has)"""
    if value is None or value == "":
        return []
    if isinstance(value, str):
        if value.startswith("["):
            return creators_from(json.loads(value))
        return [{"username": value}]
    if isinstance(value, (Creator, dict)):
        value = [value]
    found: list[tuple[int, int, dict[str, Any]]] = []
    for index, item in enumerate(value):
        if isinstance(item, str):
            item = {"username": item}
        elif isinstance(item, Creator):
            item = item.model_dump()
        else:
            item = dict(item)
        position = item.pop("position", None)
        if item.get("username") is None:
            # (a record whose user is gone)
            continue
        found.append((position if position is not None else 0, index, item))
    return [item for _, _, item in sorted(found, key=lambda entry: entry[:2])]


def stored_creators(creators: Sequence[Creator]) -> str | None:
    """The creators as a nested node keeps them in its `meta`: the name, for one person (as it always was), or JSON
    text of the list"""
    if not creators:
        return None
    if len(creators) == 1 and creators[0] == Creator(username=creators[0].username):
        return creators[0].username
    return json.dumps(
        [creator.model_dump(mode="json", exclude_none=True) for creator in creators]
    )


def usernames(creators: Iterable[Creator | dict[str, Any] | str] | None) -> list[str]:
    """The names of the creators, in order"""
    return [item["username"] for item in creators_from(creators)]


# The creators that a write names (None: the user of the request, as always). Set by `writing_as`, read where the
# record of a creation is written.
requested_creators: contextvars.ContextVar[tuple[Creator, ...] | None] = (
    contextvars.ContextVar("requested_creators", default=None)
)


def creators_asked(
    created_by: Iterable[str] | str | None = None,
    toolchain: ToolchainRun | str | None = None,
) -> tuple[Creator, ...] | None:
    """The creators that `created_by` (usernames) and `toolchain` name: the people first, then the toolchain. None
    if neither is given"""
    if created_by is None and toolchain is None:
        return None
    if isinstance(created_by, str):
        created_by = [created_by]
    creators = [Creator(username=name) for name in created_by or ()]
    if toolchain is not None:
        if isinstance(toolchain, str):
            toolchain = ToolchainRun(toolchain)
        creators.append(
            Creator(
                username=toolchain.name,
                kind="toolchain",
                version=toolchain.version,
                date=toolchain.date,
            )
        )
    names = [creator.username for creator in creators]
    if len(set(names)) != len(names):
        raise ValueError("A creator is named twice")
    if not creators:
        raise ValueError("created_by names no one")
    return tuple(creators)


@contextlib.contextmanager
def writing_as(creators: Sequence[Creator] | None) -> Generator[None]:
    """What is created inside the block is recorded as made by these (None leaves what is asked outside it)"""
    if creators is None:
        yield
        return
    token = requested_creators.set(tuple(creators))
    try:
        yield
    finally:
        requested_creators.reset(token)
