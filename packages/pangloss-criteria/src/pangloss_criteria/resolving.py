"""A description resolved, "This is…" (implementation_docs/matches-criteria.md, "In a view", and Q9). The entity chosen
takes the description's place in its document, as reconciling an `Unreconciled` does (`pangloss_review.reconcile`):
the document is read, the `MatchesCriteria` node is replaced by a reference to the entity (with the properties of the
relation, if its field has an edge model), and the whole is written again as an update, by the user, from the version
read (a new version, a write event, a record in the history, where the description stays). The entity need not be a
candidate: what the field takes is said by the update's own validation.

The route is `POST /api/criteria/{id}/resolve` (`api.py`); from Python, and through the SDK,
`pangloss_criteria.resolve(...)` (`access`).

A description that is one of several places of its document describing the same one (`same_one`) is resolved in
all of them at once: the entity takes the place of each, in the one update.
"""

import datetime
import logging
from collections.abc import Callable
from typing import Any
from uuid import UUID

from pangloss_models import (
    ModelRegistry,
    PanglossNotFoundError,
    PanglossWriteRefused,
    hooks,
)
from pangloss_models import rewriting
from pangloss_models.rewriting import replaced, replaced_where
from pydantic import ValidationError

from pangloss_criteria import holders, reading
from pangloss_criteria.access import Reference, Resolved

logger = logging.getLogger("pangloss.criteria")


def part_of(value: Any, id: str) -> dict[str, Any] | None:
    """The node of that id in what an update takes"""
    if isinstance(value, dict):
        if str(value.get("id")) == id:
            return value
        value = list(value.values())
    if isinstance(value, list):
        for item in value:
            if (found := part_of(item, id)) is not None:
                return found
    return None


def places_of(data: Any, id: str) -> Callable[[dict[str, Any]], bool]:
    """Which nodes of a document are the places of the description `id`: it, and every description of its document
    with its mark (`same_one`), if it has one"""
    part = part_of(data, id)
    mark = None if part is None else part.get("same_one")
    if mark is None:
        return lambda node: str(node.get("id")) == id
    kinds = set(holders.description_labels())
    return lambda node: (
        str(node.get("id")) == id
        or (node.get("type") in kinds and str(node.get("same_one")) == str(mark))
    )


def refused(error: ValidationError, head_type: str) -> PanglossWriteRefused:
    """What the update's validation said, as the refusal of a write (a 422 over the API)"""
    reasons = "; ".join(each["msg"] for each in error.errors()[:3])
    return PanglossWriteRefused(
        f"{head_type} does not take that in the place of the description: {reasons}"
    )


async def resolve(
    id: UUID | str, entity: Reference, version: int | None = None
) -> Resolved:
    """Put `entity` in the place of the description `id` (the id of its `MatchesCriteria`), and of every other
    place of its document with its mark (`same_one`), and write its document again: based on `version` (the version the choice was made on: `PanglossVersionConflictError` if it has changed
    since), or on the version read now. `PanglossNotFoundError` if there is no description of the id the reader may
    see (or it is no longer in its document); `PanglossWriteRefused` if the field does not take the entity there, and
    `PanglossReferenceError` if there is no such entity"""
    found = await reading.head_of(id)
    if found is None:
        raise PanglossNotFoundError(f"There is no description {id}")
    head_type, head_id = found
    model: Any = ModelRegistry._model_dict.get(head_type)
    if model is None:
        raise PanglossNotFoundError(f"There is no description {id}")

    # (each place replaced, its id and the type its node says, for `hooks.resolved`)
    places: list[tuple[str, str]] = []

    def reference(part: dict[str, Any]) -> dict[str, Any]:
        places.append((str(part.get("id")), str(part.get("type"))))
        made: dict[str, Any] = {"type": entity.type, "id": entity.id}
        # (the properties of the relation to it, a certainty say, are of the relation: kept)
        if part.get("edge_properties") is not None:
            made["edge_properties"] = part["edge_properties"]
        return made

    # (in every place of the same one, if it is one of several: each keeps the properties of its own relation)
    def change(data: Any) -> tuple[Any, bool]:
        return replaced_where(data, places_of(data, str(id)), reference)

    try:
        done = await rewriting.rewrite(model, UUID(head_id), change, version=version)
    except ValidationError as error:
        raise refused(error, head_type) from error
    if isinstance(done, rewriting.Missing):
        if done.what == "head":
            raise PanglossNotFoundError(f"There is no description {id}")
        raise PanglossNotFoundError(
            f"The description {id} is no longer in {head_type} {head_id}"
        )
    based_on = version if version is not None else done.version
    view = done.view
    await _tell_resolved(places, UUID(str(id)), head_type, head_id, entity)
    return Resolved(
        head=Reference(type=head_type, id=UUID(head_id), label=view.label),
        entity=entity,
        version=based_on + 1,
    )


async def _tell_resolved(
    places: list[tuple[str, str]],
    id: UUID,
    head_type: str,
    head_id: str,
    entity: Reference,
) -> None:
    """Tell `hooks.resolved` of each place a resolve has filled, after the write: the one asked about is `direct`"""
    # (imported here: a client of the API has this package, and not `pangloss_users`)
    from pangloss_users import current_request_username

    user = current_request_username.get()
    at = datetime.datetime.now(datetime.UTC)
    for place_id, place_type in places:
        try:
            resolution = hooks.Resolution(
                stand_in_id=UUID(place_id),
                stand_in_type=place_type,
                head_id=UUID(head_id),
                head_type=head_type,
                entity_id=entity.id,
                entity_type=entity.type,
                user=user,
                at=at,
                direct=UUID(place_id) == id,
            )
        except Exception:
            # (the document is written: that the event could not be made never fails the resolve)
            logger.exception(
                "No event could be made of the place %s resolved in %s %s",
                place_id,
                head_type,
                head_id,
            )
            continue
        await hooks.tell_resolved(resolution)


__all__ = ["places_of", "replaced", "replaced_where", "resolve"]
