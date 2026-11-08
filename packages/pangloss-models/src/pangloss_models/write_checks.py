"""What a declared class can do when it is written, beside pydantic's own validators.

Pydantic's `@field_validator` and `@model_validator` on a declared class run where a pydantic user expects them to:
when a `Create` or an `Update` is made (`Person(...)`, a payload the API is sent, the SDK's models), once. These run
at the two points after that, on the server only:

- `@create_validator` and `@update_validator`: a sync `mode="after"` model validator of the models written to the
  database, `CreateDB` (something new) and `UpdateDB` (something that exists, written again). They have the fields
  only the database has (`DBField`), and are where those are worked out (a date's bounds). Both may be put on one
  function. In an update, what is new inside the document (a nested document or embedded object without an id) is a
  `CreateDB`, so it is the create validators of its class that run on it.
- `@before_create` and `@before_update`: an `async` function, run on the server before a write, on everything in
  it that is of the class: the head, and what is nested in it (documents, embedded objects, reified relations, an
  entity made with `create_new`). `@before_create(self)` is given the `CreateDB` of what is new; in an update,
  `@before_update(self, previous)` is given the `UpdateDB` of what was there and is written again, and what it is
  now (`previous`, found by its id in the head as it is now: the `HeadView`, or the view of the nested node), and
  what is new in it has its `@before_create`s. They can read the database (by the models: `await
  Person.search(...)`) and refuse the write by raising `PanglossWriteRefused`. Run by every write of the models
  (the API, a script, `bulk-load`), but not by the SDK's client (they run on the server it sends to); before the
  write's transaction, so two writes at once can both pass a check that would refuse one after the other.

Each is inherited, as a method is: one declared on a trait or a base class runs for its subclasses too, and a subclass
can replace one by declaring another of the same name."""

import inspect
from collections.abc import Callable
from typing import Any

# (the attribute of a function that says what it is for: the names of the decorators put on it)
MARK = "__pangloss_write__"


def _mark[F: Callable[..., Any]](function: F, what: str) -> F:
    marks: set[str] = set(getattr(function, MARK, ()))
    marks.add(what)
    setattr(function, MARK, frozenset(marks))
    return function


def create_validator[F: Callable[..., Any]](function: F) -> F:
    """`def f(self)`: run on the `CreateDB` of the class (a new one, written to the database), after its fields
    are validated. May change `self` (and so what is stored), or raise `ValueError`"""
    return _mark(function, "create_validator")


def update_validator[F: Callable[..., Any]](function: F) -> F:
    """`def f(self)`: run on the `UpdateDB` of the class (one that exists, written again), after its fields are
    validated. May change `self`, or raise `ValueError`"""
    return _mark(function, "update_validator")


def before_create[F: Callable[..., Any]](function: F) -> F:
    """`async def f(self)`: run on the server before a new head of the class is written; `self` is its `CreateDB`.
    Raise `PanglossWriteRefused` to refuse it"""
    _require_async(function, "before_create")
    return _mark(function, "before_create")


def before_update[F: Callable[..., Any]](function: F) -> F:
    """`async def f(self, previous)`: run on the server before a head of the class is written again; `self` is its
    `UpdateDB`, `previous` its `HeadView` as it is now. Raise `PanglossWriteRefused` to refuse it"""
    _require_async(function, "before_update")
    return _mark(function, "before_update")


def _require_async(function: Callable[..., Any], name: str) -> None:
    if not inspect.iscoroutinefunction(function):
        raise TypeError(
            f"@{name} is for an `async def` ({getattr(function, '__qualname__', function)} is not): it may read the database"
        )


def is_marked(value: Any) -> bool:
    return bool(getattr(value, MARK, None))


def marked(model: type, what: str) -> dict[str, Callable[..., Any]]:
    """The functions of a declared class (its own, and those it inherits) that have the decorator `what`, by name,
    in the order of the class's bases (a subclass's of the same name replaces its base's)"""
    found: dict[str, Callable[..., Any]] = {}
    for klass in reversed(model.__mro__):
        for name, value in vars(klass).items():
            if what in getattr(value, MARK, ()):
                found[name] = value
            elif name in found:
                # (replaced by something that is not one)
                del found[name]
    return found


def nodes_of(model: Any) -> list[tuple[tuple[str | int, ...], Any]]:
    """What a write is made of, the head first and then what is in it, in the order of the fields, each with where it
    is (`("clauses", 0)`; the head's is `()`): every model in the tree that is a declared class's (nested documents,
    embedded objects, reified relations, an entity made with `create_new`), but not a reference to an entity that
    exists, which the write does not change"""
    from pydantic import BaseModel

    from pangloss_models.model_bases.base_models import (
        _ReferenceSetBase,
        _ReferenceViewBase,
    )

    found: list[tuple[tuple[str | int, ...], Any]] = []

    def visit(value: Any, path: tuple[str | int, ...]) -> None:
        if isinstance(value, (list, tuple)):
            for index, item in enumerate(value):
                visit(item, (*path, index))
            return
        if not isinstance(value, BaseModel) or isinstance(
            value, (_ReferenceSetBase, _ReferenceViewBase)
        ):
            return
        if getattr(type(value), "_owner", None) is not None:
            found.append((path, value))
        for name in type(value).model_fields:
            visit(getattr(value, name, None), (*path, name))

    visit(model, ())
    return found


async def _run(
    function: Callable[..., Any], path: tuple[str | int, ...], *args: Any
) -> None:
    """A check, and if it refuses, where in the write what it refused is (`clauses`, 0, then its `field`)"""
    from pangloss_models.exceptions import PanglossWriteRefused

    try:
        await function(*args)
    except PanglossWriteRefused as refused:
        refused.path = (*path, *((refused.field,) if refused.field else ()))
        raise


async def check_before_create(db_instance: Any) -> None:
    """The `@before_create`s of everything in a new head (the head, and each node in it), given its `CreateDB`:
    by the backend, before writing"""
    for path, node in nodes_of(db_instance):
        for function in marked(type(node)._owner, "before_create").values():
            await _run(function, path, node)


async def check_before_update(
    db_instance: Any, read_previous: Callable[[], Any]
) -> None:
    """The checks of everything in a head written again: of a node that is new in it (a `CreateDB`), the
    `@before_create`s; of one that was there (an `UpdateDB`), the `@before_update`s, given it as it is now, found by
    its id in the head as it is now (`await read_previous()`, its `HeadView`: read only if there are any). One that
    is not there (no such head, or an id it does not have) is not checked: the write refuses it."""
    from pangloss_models.model_bases.base_models import _UpdateDBBase

    checks = []
    for path, node in nodes_of(db_instance):
        kind = "before_update" if isinstance(node, _UpdateDBBase) else "before_create"
        if found := marked(type(node)._owner, kind):
            checks.append((path, node, kind, found))
    if not checks:
        return
    previous_by_id: dict[Any, Any] | None = None
    for path, node, kind, found in checks:
        if kind == "before_create":
            for function in found.values():
                await _run(function, path, node)
            continue
        if previous_by_id is None:
            previous = await read_previous()
            previous_by_id = (
                {getattr(n, "id", None): n for _, n in nodes_of(previous)}
                if previous
                else {}
            )
        if (before := previous_by_id.get(node.id)) is None:
            continue
        for function in found.values():
            await _run(function, path, node, before)
