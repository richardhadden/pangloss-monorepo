"""Restoring a version: the old content is written again as a **new** version (history is never
rewritten). See docs/history.md, "Restoring".

What is done, in order, and nothing is written until the checks have passed:

1. the version must have been recorded, at the schema position the database is at now (an older
   one needs upgrading, which is not done yet);
2. its content must still be a valid `Update` of the model;
3. the entities it refers to must exist: ones that were deleted since are undeleted (an undeletion
   writes no content, and is harmless if the restore then fails); one that is gone is a problem;
4. a deleted head node is undeleted, and the update is made conditional on the version it has;
5. the update is made, and told to listeners as a `restore` of the version.

Incoming relations are not touched: they belong to other documents.
"""

import inspect
from collections.abc import Iterator
from typing import Any
from uuid import UUID

from pangloss_core import settings as core_settings
from pangloss_models.exceptions import (
    PanglossConflictError,
    PanglossNotFoundError,
)
from pangloss_models.model_bases.entity import Entity
from pangloss_models.model_registry import ModelRegistry
from pydantic import ValidationError

from pangloss_history.schema_position import schema_position
from pangloss_history.store import HistoryStore


class PanglossRestoreError(PanglossConflictError):
    """A version cannot be restored as it is. `problems` says why, each as `{kind, message, ...}`"""

    def __init__(self, problems: list[dict[str, Any]]):
        self.problems = problems
        super().__init__("; ".join(p["message"] for p in problems))


async def called(value: Any) -> Any:
    return await value if inspect.isawaitable(value) else value


def entity_references(data: Any, entities: set[str], skip: UUID) -> Iterator[tuple[str, UUID]]:
    """The `(type, id)` of each reference to an entity in a snapshot (not the head node itself)"""
    if isinstance(data, dict):
        if data.get("type") in entities and data.get("id") and str(data["id"]) != str(skip):
            yield data["type"], UUID(str(data["id"]))
        for value in data.values():
            yield from entity_references(value, entities, skip)
    elif isinstance(data, list):
        for item in data:
            yield from entity_references(item, entities, skip)


async def bring_back_entities(data: Any, head_id: UUID) -> list[dict[str, Any]]:
    """Undelete the entities that the content refers to and that were deleted. Gives the
    problems: those that cannot be found at all"""
    models = ModelRegistry.all_models()
    entities = {name for name, m in models.items() if isinstance(m, type) and issubclass(m, Entity)}
    problems = []
    for type_name, id in dict.fromkeys(entity_references(data, entities, head_id)):
        model: Any = models[type_name]
        if await called(model.get(id)) is not None:
            continue
        try:
            await called(model.undelete(id))
        except PanglossNotFoundError:
            problems.append(
                {
                    "kind": "reference-missing",
                    "oldValue": {"type": type_name, "id": str(id)},
                    "message": f"{type_name} {id} no longer exists",
                }
            )
    return problems


async def restore(
    store: HistoryStore,
    model: Any,
    id: UUID,
    version: int,
    expected_version: int | None = None,
) -> int:
    """Put version `version` back as a new version. Gives the new version number.

    `expected_version` is the version that the person saw (as `If-Match`): if the head node
    has changed since, `PanglossVersionConflictError`. Without it, the version at the time is used."""
    record = store.get(id, version)
    if record is None or record.model != model.__name__:
        raise PanglossNotFoundError(
            f"Version {version} of {model.__name__} {id} was not recorded"
        )

    settings = core_settings.__dict__.get("SETTINGS")
    position = schema_position(settings.INSTALLED_APPS if settings is not None else [])
    if record.schema_position != position:
        raise PanglossRestoreError(
            [
                {
                    "kind": "schema-changed",
                    "message": f"Version {version} was written when the migrations were at "
                    f"{record.schema_position}, and they are at {position} now: it has to be "
                    "upgraded first, which is not done yet",
                }
            ]
        )

    try:
        update = model.Update.model_validate(record.data())
    except ValidationError as error:
        raise PanglossRestoreError(
            [{"kind": "validation", "message": f"Version {version} is not valid now: {error}"}]
        ) from error

    problems = await bring_back_entities(record.data(), id)
    if problems:
        raise PanglossRestoreError(problems)

    if await called(model.get(id)) is None:
        # (deleted, or not there at all, which `undelete` says)
        await called(model.undelete(id))
    current = (await called(model.get(id))).meta.version
    based_on = expected_version if expected_version is not None else current

    await called(update.save(expected_version=based_on, restored_from=version))
    return based_on + 1
