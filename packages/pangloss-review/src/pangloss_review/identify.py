"""Identifications that a toolchain suggested (`IdentificationByToolchain` of `pangloss-library`), for a person to
confirm.

One in a document is a task while it is there. Confirming it makes it an `Identification` by the person who confirms:
the same node (its id is kept) with the same target, by an update of its document as for reconciling (`reconcile`).
With one candidate, the URIs the toolchain gave go to that entity. Others that suggest the same candidates with about
the same likelihoods (`similar`) can be given the confirmed identification in one go, in the background.

A person corrects a suggestion in the form of its document, as any other part, and confirms it before or after.
"""

import contextlib
import contextvars
import datetime
import logging
from collections.abc import Generator
from typing import Any
from uuid import UUID

from pangloss_models import Entity, ModelRegistry, WriteEvent, hooks, nodes_of

from pangloss_review import graph, uris
from pangloss_review.exceptions import PanglossNoSuchTaskError, PanglossReconcileError
from pangloss_review.reconcile import (
    _mentions_from,
    mentions_naming,
    reconcile_with,
    shares_a_uri,
    give_uris,
    in_background,
    one_by_one,
    rewrite_part,
)
from pangloss_review.status import (
    Confirmed,
    Ref,
    SimilarSuggestion,
    Suggestion,
    Suggestions,
)

logger = logging.getLogger("pangloss.review")

# The class a confirmed suggestion becomes (of `pangloss-library`), unless its class names another (`confirmed_as`,
# a subclass of it: a project's own kind of suggestion and of identification)
CONFIRMED = "Identification"
# How far apart, in points of a per cent, the likelihood of a candidate may be in two suggestions that are offered
# together
PERCENT_WITHIN = 10
SIMILAR_LIMIT = 50


def has_suggestions() -> bool:
    """Whether the project's models have identifications by a toolchain at all"""
    return graph.SUGGESTED in ModelRegistry._model_dict


async def _suggestions_from(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The rows of `graph`, as what a `Suggestion` is made from: each with its candidates and where it is"""
    rows = await _mentions_from(rows)
    held = await graph.candidates([row["id"] for row in rows])
    return [
        {
            **row,
            "candidates": held.get(row["id"], []),
            "becomes": _becomes(row.get("type")),
        }
        for row in rows
    ]


def _becomes(suggestion_type: str | None) -> str:
    """The name of the class a confirmed suggestion of this class becomes (`confirmed_as`)"""
    named = getattr(
        ModelRegistry._model_dict.get(str(suggestion_type)), "confirmed_as", CONFIRMED
    )
    return named if isinstance(named, str) else named.__name__


async def get_suggestion(id: UUID) -> Suggestion:
    rows = await graph.suggestions_by_id([str(id)])
    if not rows:
        raise PanglossNoSuchTaskError(f"There is no identification by a toolchain {id}")
    made = (await _suggestions_from(rows))[0]
    return Suggestion(**made, known=await uris.entities_with(made["uris"]))


async def suggestions_naming(
    named: list[Any], except_id: str | None = None
) -> list[SimilarSuggestion]:
    """The suggestions that name one of the URIs: of the same person as whatever else names it"""
    found = (await uris.naming([str(uri) for uri in named], except_id))["suggestion"]
    rows = [
        row for row in await graph.suggestions_by_id(found) if shares_a_uri(named, row)
    ]
    rows.sort(key=lambda row: row["id"])
    made = await _suggestions_from(rows[:SIMILAR_LIMIT])
    return [SimilarSuggestion(**row, same_uri=True) for row in made]


async def mentions_of_suggestion(id: UUID) -> list[Any]:
    """The unreconciled mentions that name a URI of this suggestion: of the same person"""
    rows = await graph.suggestions_by_id([str(id)])
    if not rows:
        raise PanglossNoSuchTaskError(f"There is no identification by a toolchain {id}")
    return await mentions_naming(rows[0]["uris"])


async def list_suggestions(
    assigned_to: str | None = None, page: int = 1, page_size: int = 25
) -> Suggestions:
    """A page of the identifications to confirm, the oldest first"""
    if not has_suggestions():
        found: dict[str, Any] = {"count": 0, "results": []}
    else:
        found = await graph.suggestions(assigned_to, page, page_size)
    count = found["count"]
    last = -(-count // page_size)
    return Suggestions(
        results=[
            Suggestion(**row) for row in await _suggestions_from(found["results"])
        ],
        count=count,
        page=page,
        page_size=page_size,
        next_page=page + 1 if page < last else None,
        previous_page=page - 1 if page > 1 else None,
    )


def alike(mine: list[dict[str, Any]], other: list[dict[str, Any]]) -> bool:
    """Whether two suggestions say the same: the same candidates, each about as likely in one as in the other"""
    own = {c["id"]: c["percent"] for c in mine}
    theirs = {c["id"]: c["percent"] for c in other}
    if not own or set(own) != set(theirs):
        return False
    return all(
        abs((own[id] or 0) - (theirs[id] or 0)) <= PERCENT_WITHIN
        if own[id] is not None or theirs[id] is not None
        else True
        for id in own
    )


async def similar(id: UUID) -> list[SimilarSuggestion]:
    """The other suggestions that are of the same person as this one, to be given the same confirmed identification
    in one go. First those that name a URI it names (`same_uri`): the same person, whoever their candidates are.
    Then those that say the same (`alike`), compared with the candidates this one has now: after it is confirmed (it
    is no longer a suggestion) they are those of the identification it became."""
    mine = await graph.suggestions_by_id([str(id)])
    by_uri = await suggestions_naming(mine[0]["uris"], str(id)) if mine else []
    return by_uri + await _alike(id, {str(found.id) for found in by_uri})


async def _alike(id: UUID, but: set[str]) -> list[SimilarSuggestion]:
    held = (await graph.candidates([str(id)]))[str(id)]
    if not held:
        return []
    # (found from one candidate: every suggestion like this one has it)
    others = [
        i
        for i in await graph.suggestions_of(held[0]["id"])
        if i != str(id) and i not in but
    ]
    rows = await graph.suggestions_by_id(others)
    theirs = await graph.candidates([row["id"] for row in rows])
    kept = [row for row in rows if alike(held, theirs[row["id"]])]
    kept.sort(key=lambda row: row["id"])
    made = await _suggestions_from(kept[: max(SIMILAR_LIMIT - len(but), 0)])
    return [SimilarSuggestion(**row) for row in made]


def fresh(value: Any) -> Any:
    """What a part of a document holds, to be written in another place: the entities it refers to as they are, and
    everything else (the wrappers between) without its id, so that it is made anew there"""
    if isinstance(value, list):
        return [fresh(item) for item in value]
    if not isinstance(value, dict):
        return value
    model = ModelRegistry._model_dict.get(str(value.get("type")))
    if model is not None and issubclass(model, Entity):
        kept = {"type": value["type"], "id": value["id"]}
        # (as the models give it, or as the API and a form do)
        edge = value.get("edge_properties", value.get("edgeProperties"))
        if edge is not None:
            kept["edge_properties"] = edge
        return kept
    return {key: fresh(item) for key, item in value.items() if key != "id"}


def confirmed_class(suggestion_type: str | None) -> Any:
    """The class that a confirmed suggestion of this class becomes. Raises `PanglossReconcileError` if the models
    have none"""
    models = ModelRegistry._model_dict
    named = getattr(models.get(str(suggestion_type)), "confirmed_as", CONFIRMED)
    name = named if isinstance(named, str) else named.__name__
    if name not in models:
        raise PanglossReconcileError(
            f"The models have no {name} for a confirmed suggestion to become"
        )
    return models[name]


def target_of_one(target: Any, entity: dict[str, Any]) -> list[dict[str, Any]]:
    """What an identification is of, when it is of this entity and no other, in the place of `target`: the entity,
    or, where the identification holds alternatives (the library's `WeightedAlternative`), the one alternative"""
    first = target[0] if isinstance(target, list) and target else None
    if isinstance(first, dict) and first.get("type") == "WeightedAlternative":
        one = {**entity, "edge_properties": {"percent": 100}}
        return [{"type": "WeightedAlternative", "alternatives": [one]}]
    return [dict(entity)]


def entities_of(target: Any) -> tuple[tuple[str, str], ...]:
    """The entities that what an identification is of names (as a part of a document holds it), each its id and its
    class, in their order: one, or the alternatives"""
    found: list[tuple[str, str]] = []

    def walk(value: Any) -> None:
        if isinstance(value, list):
            for item in value:
                walk(item)
            return
        if not isinstance(value, dict):
            return
        model = ModelRegistry._model_dict.get(str(value.get("type")))
        if model is not None and issubclass(model, Entity):
            found.append((str(value["id"]), str(value["type"])))
            return
        for item in value.values():
            walk(item)

    walk(target)
    return tuple(found)


def several(target: Any) -> bool:
    """Whether what an identification is of names more than one entity (alternatives)"""
    return len(entities_of(target)) > 1


async def _confirm_one(
    row: dict[str, Any],
    user: str,
    target: Any | None = None,
    entity: dict[str, Any] | None = None,
) -> Any:
    """Make one suggestion (a row of `graph`) an identification by the user, with the target it has, the one given,
    or the one entity given (`target_of_one`). Gives what its target is then"""
    # (what a suggestion has that an identification does not take from it: said once, by the library, whose classes
    # these are)
    from pangloss_library.models import NOT_KEPT

    confirmed: dict[str, Any] = {}

    def identification(part: dict[str, Any]) -> dict[str, Any]:
        if entity is not None:
            confirmed["target"] = target_of_one(part["target"], entity)
        else:
            confirmed["target"] = part["target"] if target is None else fresh(target)
        becomes = confirmed_class(part.get("type"))
        # (what the two classes have in common is kept: the fields of a project's own subclasses)
        kept = {
            key: value
            for key, value in part.items()
            if key not in NOT_KEPT and key in becomes.model_fields
        }
        made = {
            **kept,
            "type": becomes.__name__,
            "id": part["id"],
            "identified_by": user,
            "target": confirmed["target"],
        }
        # (the URIs are for the one who is identified: with several candidates still, nobody can be given them,
        # and the identification keeps them)
        if (
            part.get("uris")
            and several(confirmed["target"])
            and "uris" in becomes.model_fields
        ):
            made["uris"] = part["uris"]
        if part.get("edge_properties") is not None:
            made["edge_properties"] = part["edge_properties"]
        return made

    await rewrite_part(row["head_type"], row["head_id"], row["id"], identification)
    return confirmed["target"]


async def _tell_confirmed(
    row: dict[str, Any],
    user: str,
    entities: tuple[tuple[str, str], ...],
    direct: bool,
    confirmed_type: str | None = None,
) -> None:
    """Tell `hooks.confirmed` that a suggestion (a row of `graph`, as it was before) was confirmed: after its document
    is written, before its URIs are given (that they could not be given does not lose it), from what was read
    already"""
    try:
        confirmation = hooks.Confirmation(
            suggestion_id=UUID(str(row["id"])),
            suggestion_type=str(row["type"]),
            confirmed_type=confirmed_type or confirmed_class(row.get("type")).__name__,
            head_id=UUID(str(row["head_id"])),
            head_type=str(row["head_type"]),
            user=user,
            at=datetime.datetime.now(datetime.UTC),
            entities=entities,
            direct=direct,
        )
    except Exception:
        # (the document is written: that the event could not be made never fails the confirmation)
        logger.exception("No event could be made of the confirmation of %s", row)
        return
    await hooks.tell_confirmed(confirmation)


async def _give_uris_to_the_one(
    id: str, uris: list[str], held: list[dict[str, Any]] | None = None
) -> tuple[list[str], list[str]]:
    """Give the URIs of a confirmed suggestion to its candidate, if it has just one (`held`: its candidates, if they
    have been read)"""
    if held is None:
        held = (await graph.candidates([id]))[id]
    if len(held) != 1 or not uris:
        return [], []
    model = ModelRegistry._model_dict.get(held[0]["type"])
    if model is None:
        return [], []
    return await give_uris(model, UUID(held[0]["id"]), uris)


# --- confirmed by saving the document ---------------------------------------------------------------------------------


async def _by_a_toolchain(username: str) -> bool:
    """Whether a user is a toolchain (a user of kind `toolchain`)"""
    # (imported here, as in `reconcile`: a client of the API has the models, and not `pangloss_users`)
    from pangloss_users import service

    user = await service.get_user(username)
    return user is not None and user.kind == "toolchain"


async def _after_save(event: WriteEvent, noted: list[Any]) -> None:
    """What a save of a document confirmed (`noted` by the library): each suggestion it wrote again as an
    identification is told to `hooks.confirmed` (not `direct`), with the entities of the target this write gave it
    (noted in the write: a later write of the document meanwhile does not change them), and the URIs of each, a
    suggestion or an identification that kept them, go to its one candidate. Nothing for a write by a toolchain (it is
    no person's confirmation, and no entity is to be given URIs by it); nothing for one that is still a suggestion
    (the write that was to confirm it was not made). **A restore** (`event.restored_from`) is told to no one: putting
    back a version in which the node was an identification is no one's judgement of the suggestion now there; its
    URIs are given as for any save."""
    if await _by_a_toolchain(event.user):
        return
    restored = event.restored_from is not None
    for one in noted:
        id = str(one.id)
        if await graph.suggestions_by_id([id]):
            continue
        held = None
        if one.was is not None and not restored:
            row = {
                "id": id,
                "type": one.was,
                "head_id": event.id,
                "head_type": event.model.__name__,
            }
            entities = one.entities
            if entities is None:
                held = (await graph.candidates([id]))[id]
                entities = tuple((str(c["id"]), str(c["type"])) for c in held)
            await _tell_confirmed(
                row, one.by or event.user, entities, False, confirmed_type=one.type
            )
        if one.uris:
            await _give_uris_to_the_one(id, one.uris, held)


def on_write(event: WriteEvent) -> None:
    """(a listener to writes) A document saved with a suggestion in it written as an identification: whoever saved
    it confirmed it, in the form or with a script. In the background: it is told to `hooks.confirmed`, and the one
    candidate is given the URIs as when it is confirmed by `confirm`. `confirm` does both itself, to say what came
    of it."""
    try:
        from pangloss_library.models import confirmed_in_write
    except ImportError:
        return
    noted = confirmed_in_write.get()
    if not noted:
        return
    confirmed_in_write.set(None)
    if event.op != "update" or _confirming_here.get():
        return
    # (of this write: what is in it, as what it was noted as. What a write that was not made noted is not)
    written = {
        (str(getattr(node, "id", None)), getattr(node, "type", None))
        for _, node in nodes_of(event.payload)
    }
    mine = [one for one in noted if (str(one.id), one.type) in written]
    if mine:
        in_background(_after_save(event, mine))


# (set while `confirm` writes: it gives the URIs itself)
_confirming_here: contextvars.ContextVar[bool] = contextvars.ContextVar(
    "confirming_here", default=False
)


async def confirm_as_entity(
    ids: list[UUID], entity: dict[str, Any], except_head: str | None = None
) -> int:
    """Confirm suggestions as one entity that something else says they are (a mention that names their URI,
    reconciled), by the user of the request, in the background; not those of one document (`except_head`: its form
    does them). Gives how many are being done"""
    from pangloss_library.models import writer

    user = writer()
    rows = await graph.suggestions_by_id([str(id) for id in dict.fromkeys(ids)])
    wanted = [UUID(row["id"]) for row in rows if row["head_id"] != except_head]

    async def confirm_other(other: UUID) -> None:
        now = await graph.suggestions_by_id([str(other)])
        if not now:
            raise PanglossNoSuchTaskError(
                f"There is no identification by a toolchain {other}"
            )
        with _confirming():
            target = await _confirm_one(now[0], user, entity=entity)
        await _tell_confirmed(now[0], user, entities_of(target), direct=False)
        await _give_uris_to_the_one(now[0]["id"], now[0]["uris"])

    if wanted:
        in_background(one_by_one(wanted, "Confirming", confirm_other))
    return len(wanted)


async def give_to_others(
    id: UUID,
    user: str,
    others: list[UUID],
    target: Any,
    mentions: list[UUID] | None = None,
    entity: dict[str, Any] | None = None,
) -> int:
    """Give other suggestions (from `similar`) the identification that this one is being given in a form that is
    not saved yet: each becomes an identification by the user with this target, in the background. Those in the
    document of this one are left (they are in the form too, and a write of it now would make the form stale).
    Gives how many are being done"""
    rows = await graph.suggestions_by_id([str(id)])
    head = rows[0]["head_id"] if rows else None
    found = await graph.suggestions_by_id(
        [str(other) for other in dict.fromkeys(others) if other != id]
    )
    wanted = [UUID(row["id"]) for row in found if row["head_id"] != head]

    async def confirm_other(other: UUID) -> None:
        now = await graph.suggestions_by_id([str(other)])
        if not now:
            raise PanglossNoSuchTaskError(
                f"There is no identification by a toolchain {other}"
            )
        with _confirming():
            given = await _confirm_one(now[0], user, target)
        await _tell_confirmed(now[0], user, entities_of(given), direct=False)
        await _give_uris_to_the_one(now[0]["id"], now[0]["uris"])

    if wanted:
        in_background(one_by_one(wanted, "Confirming", confirm_other))
    # (the mentions that name its URI, where it is of one entity: reconciled with that entity)
    reconciled = 0
    if mentions and entity is not None:
        reconciled = await reconcile_with(
            mentions, entity["type"], UUID(str(entity["id"])), except_head=head
        )
    return len(wanted) + reconciled


@contextlib.contextmanager
def _confirming() -> Generator[None]:
    token = _confirming_here.set(True)
    try:
        yield
    finally:
        _confirming_here.reset(token)


async def confirm(
    id: UUID,
    user: str,
    also: list[UUID] | None = None,
    entity: dict[str, Any] | None = None,
) -> Confirmed:
    """Confirm a suggestion as it is now: it becomes an `Identification` by the user; with one candidate, the entity
    is given the suggestion's URIs. With `entity` (`{"type", "id"}`), it is confirmed as that one entity: one of its
    alternatives, or any the place takes (`target_of_one`), which is given its URIs. The other suggestions named
    (`also`: from `similar`) are given the same target (or the same one entity), in the background. Each is told to
    `hooks.confirmed`, this one `direct`."""
    rows = await graph.suggestions_by_id([str(id)])
    if not rows:
        raise PanglossNoSuchTaskError(f"There is no identification by a toolchain {id}")
    row = rows[0]
    confirmed_class(row.get("type"))
    with _confirming():
        target = await _confirm_one(row, user, entity=entity)
    await _tell_confirmed(row, user, entities_of(target), direct=True)
    added, taken = await _give_uris_to_the_one(row["id"], row["uris"])

    others = [other for other in dict.fromkeys(also or []) if other != id]

    async def confirm_other(other: UUID) -> None:
        found = await graph.suggestions_by_id([str(other)])
        if not found:
            raise PanglossNoSuchTaskError(
                f"There is no identification by a toolchain {other}"
            )
        with _confirming():
            if entity is not None:
                given = await _confirm_one(found[0], user, entity=entity)
            else:
                given = await _confirm_one(found[0], user, target)
        await _tell_confirmed(found[0], user, entities_of(given), direct=False)
        await _give_uris_to_the_one(found[0]["id"], found[0]["uris"])

    if others:
        in_background(one_by_one(others, "Confirming", confirm_other))
    return Confirmed(
        id=id,
        head=Ref(type=row["head_type"], id=row["head_id"], label=row["head_label"]),
        uris_added=added,
        uris_taken=taken,
        queued=len(others),
    )
