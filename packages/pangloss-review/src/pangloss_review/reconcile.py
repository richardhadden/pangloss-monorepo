"""Reconciling: an unreconciled mention (`pangloss_review.models.Unreconciled`) is replaced by an entity.

The mention is part of a document, so reconciling it is an update of that document, made here as a person would make it
in a form: the document is read, the mention is replaced by a reference to the entity, and the whole is written again
(by the user who asked, from the version that was read: a new version, a write event, a record in the history). The
mention's URIs are given to the entity, those it does not have and no other entity has.

Other mentions of the same thing (`similar`) can be reconciled with it in one go: the first at once, the rest in the
background, one document at a time (`in_background`). If the server stops, what is left is still unreconciled, and is
offered again.
"""

import asyncio
import difflib
import logging
from collections.abc import Awaitable, Callable, Coroutine
from typing import Any
from uuid import UUID

from pangloss_models import Entity, ModelRegistry, PanglossWriteError
from pangloss_models.utils import editable, get_concrete_types
from pydantic import ValidationError

from pangloss_review import graph, uris
from pangloss_review.exceptions import PanglossNoSuchTaskError, PanglossReconcileError
from pangloss_review.meta import allows_unreconciled, reconcile_rule
from pangloss_review.models import label_key
from pangloss_review.status import (
    Mention,
    Mentions,
    Reconciled,
    Ref,
    ReviewStatus,
    SimilarMention,
    TaskCounts,
)

logger = logging.getLogger("pangloss.review")

# How alike two folded labels must be for one to be offered with the other, and how many are offered
SIMILAR_AT_LEAST = 0.75
SIMILAR_LIMIT = 50
# The shortest word of a label that other labels are searched for
WORD_LENGTH = 3
# How many other head documents a rule that is a function is asked about, at most (each is read)
RULE_LIMIT = 100

type Replace = Callable[[dict[str, Any]], dict[str, Any]]


# --- the document a part is in, written again ---------------------------------------------------------------------


def replaced(value: Any, id: str, replace: Replace) -> tuple[Any, bool]:
    """`value` (what an update takes) with the node of that id replaced by what `replace` makes of it, and whether
    it was found"""
    if isinstance(value, dict):
        if str(value.get("id")) == id:
            return replace(value), True
        found = False
        changed = {}
        for key, item in value.items():
            changed[key], item_found = replaced(item, id, replace)
            found = found or item_found
        return changed, found
    if isinstance(value, list):
        items = [replaced(item, id, replace) for item in value]
        return [item for item, _ in items], any(found for _, found in items)
    return value, False


async def rewrite_part(head_type: str, head_id: str, id: str, replace: Replace) -> Any:
    """Write the head document again with one part of it (the node `id`) replaced. Gives the head as it was read.
    Raises `PanglossNoSuchTaskError` if the document or the part is not there (any more), `PanglossReconcileError`
    if the document does not take what the part is replaced by"""
    model: Any = ModelRegistry._model_dict.get(head_type)
    view = await model.get(UUID(head_id)) if model is not None else None
    if model is None or view is None:
        raise PanglossNoSuchTaskError(f"There is no {head_type} {head_id}")
    data, found = replaced(editable(view.model_dump()), id, replace)
    if not found:
        raise PanglossNoSuchTaskError(f"{id} is no longer in {head_type} {head_id}")
    try:
        update = model.Update(**data)
    except ValidationError as error:
        reasons = "; ".join(e["msg"] for e in error.errors()[:3])
        raise PanglossReconcileError(
            f"{head_type} {view.label or head_id} does not take that: {reasons}"
        ) from error
    await update.save(expected_version=view.meta.version)
    return view


# --- work done after the answer ------------------------------------------------------------------------------------

_background: set[asyncio.Task] = set()


def in_background(work: Coroutine[Any, Any, Any]) -> None:
    """Run after the request is answered, in the server's process, as the user of the request (a task copies the
    context it is made in). A failure is logged: what it did not do is still a task"""
    task = asyncio.get_running_loop().create_task(work)
    _background.add(task)

    def done(finished: asyncio.Task) -> None:
        _background.discard(finished)
        if not finished.cancelled() and finished.exception() is not None:
            logger.error(
                "Review work in the background failed", exc_info=finished.exception()
            )

    task.add_done_callback(done)


async def background_done() -> None:
    """Wait for the work in the background to end (for tests, and a server that is stopping)"""
    while _background:
        await asyncio.gather(*list(_background), return_exceptions=True)


# (one batch at a time in a process: two that change the same document, a suggestion and a mention of one URI in
# it, would each write over the version the other read, and the second would be refused and left)
_batches: dict[int, asyncio.Lock] = {}


def _one_batch_at_a_time() -> asyncio.Lock:
    loop = id(asyncio.get_running_loop())
    if loop not in _batches:
        _batches.clear()
        _batches[loop] = asyncio.Lock()
    return _batches[loop]


async def one_by_one(
    ids: list[UUID], what: str, each: Callable[[UUID], Awaitable[Any]]
) -> None:
    """Do `each` for every id, going on past one that cannot be done (it is gone, or its document was changed
    meanwhile): it stays a task. After any batch that was started before this one"""
    done = 0
    async with _one_batch_at_a_time():
        for id in ids:
            try:
                await each(id)
                done += 1
            except (
                PanglossNoSuchTaskError,
                PanglossReconcileError,
                PanglossWriteError,
            ) as error:
                logger.warning("%s %s was left: %s", what, id, error)
    logger.info("%s: %s of %s done in the background", what, done, len(ids))


# --- reading the mentions ------------------------------------------------------------------------------------------


def unreconciled_types() -> list[str]:
    """The names of the entity classes that may be left unreconciled, sorted"""
    return sorted(
        name
        for name, model in ModelRegistry._model_dict.items()
        if allows_unreconciled(model)
    )


async def _mentions_from(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The rows of `graph`, as what a `Mention` is made from: each with the document it is directly in"""
    holders = await graph.holders([row["id"] for row in rows])
    made = []
    for row in rows:
        head = {
            "type": row["head_type"],
            "id": row["head_id"],
            "label": row["head_label"],
        }
        made.append(
            {
                **row,
                "uris": [str(uri) for uri in row["uris"]],
                "head": head,
                "holder": holders.get(row["id"], head),
            }
        )
    return made


async def get_mention(id: UUID) -> Mention:
    row = await graph.mention(str(id))
    if row is None:
        raise PanglossNoSuchTaskError(f"There is no unreconciled mention {id}")
    made = (await _mentions_from([row]))[0]
    return Mention(**made, known=await uris.entities_with(made["uris"]))


def shares_a_uri(mine: list[Any], row: dict[str, Any]) -> bool:
    """Whether a part (a row of `graph`) names one of these URIs, as it is now"""
    own = {str(uri) for uri in mine}
    return any(str(uri) in own for uri in row.get("uris") or ())


async def mentions_naming(
    named: list[Any], except_id: str | None = None
) -> list[Mention]:
    """The mentions that name one of the URIs: of the same person or thing as whatever else names it"""
    found = (await uris.naming([str(uri) for uri in named], except_id))["mention"]
    rows = [
        row for row in await graph.mentions_by_id(found) if shares_a_uri(named, row)
    ]
    rows.sort(key=lambda row: (row["label_key"] or "", row["id"]))
    return [Mention(**row) for row in await _mentions_from(rows[:SIMILAR_LIMIT])]


async def suggestions_of_mention(id: UUID) -> list[Any]:
    """The identifications a toolchain suggested that name a URI of this mention: of the same person"""
    from pangloss_review import identify

    mine = await graph.mention(str(id))
    if mine is None:
        raise PanglossNoSuchTaskError(f"There is no unreconciled mention {id}")
    return await identify.suggestions_naming(mine["uris"])


async def list_mentions(
    type: str | None = None,
    q: str | None = None,
    assigned_to: str | None = None,
    page: int = 1,
    page_size: int = 25,
) -> Mentions:
    """A page of the unreconciled mentions, by label: of an entity class, with `q` in the label, in documents given
    to a user to review (`""`: to no one)"""
    key = label_key(q) if q and q.strip() else None
    found = await graph.mentions(type, key, assigned_to, page, page_size)
    count = found["count"]
    last = -(-count // page_size)
    return Mentions(
        results=[Mention(**row) for row in await _mentions_from(found["results"])],
        count=count,
        page=page,
        page_size=page_size,
        next_page=page + 1 if page < last else None,
        previous_page=page - 1 if page > 1 else None,
    )


def maybe_alike(key: str, other: str) -> bool:
    """Whether two folded labels could be alike enough: a quick upper bound of `likeness`, to pass over most of
    thousands of candidates without working it out"""
    matcher = difflib.SequenceMatcher(None, key, other, autojunk=False)
    return (
        matcher.real_quick_ratio() >= SIMILAR_AT_LEAST
        and matcher.quick_ratio() >= SIMILAR_AT_LEAST
    )


async def task_counts(assigned_to: str | None = None) -> TaskCounts:
    """How many tasks there are of each kind (documents to check, mentions to reconcile, identifications to confirm):
    of everyone, or of the documents given to a user (`""`: to no one)"""
    open_statuses = [ReviewStatus.UNCHECKED.value, ReviewStatus.ERRORS_FOUND.value]
    return TaskCounts(**await graph.task_counts(open_statuses, assigned_to))


def likeness(key: str, other: str) -> float:
    """How alike two folded labels are, from 0 to 1"""
    if key == other:
        return 1.0
    return difflib.SequenceMatcher(None, key, other, autojunk=False).ratio()


async def _together(mine: dict[str, Any], others: list[dict[str, Any]]) -> list[dict]:
    """Of the other mentions, those the rule of this mention's head document lets go with it
    (`ReviewMeta(reconcile_together=...)`): all of them, with no rule. A mention in the same document always does"""
    head_model: Any = ModelRegistry._model_dict.get(mine["head_type"])
    rule = reconcile_rule(head_model) if head_model is not None else None
    if rule is None:
        return others
    elsewhere = sorted(
        {o["head_id"] for o in others if o["head_id"] != mine["head_id"]}
    )
    allowed = {mine["head_id"]}
    if callable(rule):
        types = {o["head_id"]: o["head_type"] for o in others}
        own = await head_model.get(UUID(mine["head_id"]))
        for head_id in elsewhere[:RULE_LIMIT]:
            model: Any = ModelRegistry._model_dict.get(types[head_id])
            other = await model.get(UUID(head_id)) if model is not None else None
            if own is not None and other is not None and rule(own, other):
                allowed.add(head_id)
    else:
        fields = list(rule)
        held = await graph.head_entities([mine["head_id"], *elsewhere], fields)
        own_held = held[mine["head_id"]]
        allowed.update(
            head_id
            for head_id in elsewhere
            if all(
                held[head_id].get(field, frozenset())
                == own_held.get(field, frozenset())
                for field in fields
            )
        )
    return [o for o in others if o["head_id"] in allowed]


async def similar(id: UUID) -> list[SimilarMention]:
    """The other mentions that may be of the same thing as this one, to be reconciled with it in one go: of the same
    entity class, with the same label after folding (`exact`) or one much like it, the most alike first; only those
    the rule of the document's class lets go with it"""
    mine = await graph.mention(str(id))
    if mine is None:
        raise PanglossNoSuchTaskError(f"There is no unreconciled mention {id}")
    key = mine["label_key"] or label_key(mine["label"])
    words = sorted({word for word in key.split(" ") if len(word) >= WORD_LENGTH})
    type = mine["unreconciled_type"]
    # (the same label: all of them, by the index; the near ones are scored, and the most alike kept)
    scores = {found: 1.0 for found in await graph.same_label(str(id), type, key)}
    near = [
        (likeness(key, other), found)
        for found, other in (await graph.near_labels(str(id), type, key, words)).items()
        if maybe_alike(key, other)
    ]
    near = sorted((score, found) for score, found in near if score >= SIMILAR_AT_LEAST)
    scores |= {found: score for score, found in near[-2 * SIMILAR_LIMIT :]}
    # (a URI in common says more than any label: those come first, whatever they are called and whatever rule the
    # document has for labels)
    named = (await uris.naming(mine["uris"], str(id)))["mention"]
    by_uri = [
        row
        for row in await graph.mentions_by_id(named)
        if shares_a_uri(mine["uris"], row)
    ]
    by_uri.sort(key=lambda row: (row["label_key"] or "", row["id"]))
    same_uri = {row["id"] for row in by_uri}
    rows = await graph.mentions_by_id(
        [found for found in scores if found not in same_uri]
    )
    rows.sort(key=lambda row: (-scores[row["id"]], row["label_key"] or "", row["id"]))
    kept = by_uri + await _together(mine, rows)

    def score_of(row: dict[str, Any]) -> float:
        other = row["label_key"] or label_key(row["label"])
        return scores.get(row["id"]) or likeness(key, other)

    return [
        SimilarMention(
            **row,
            score=round(score_of(row), 3),
            exact=score_of(row) == 1.0,
            same_uri=row["id"] in same_uri,
        )
        for row in await _mentions_from(kept[:SIMILAR_LIMIT])
    ]


# --- reconciling ---------------------------------------------------------------------------------------------------


async def give_uris(
    model: Any, entity_id: UUID, uris: list[str]
) -> tuple[list[str], list[str]]:
    """Give an entity the URIs it does not have. Gives those added, and those left because another entity has them"""
    wanted = list(dict.fromkeys(str(uri) for uri in uris))
    if not wanted:
        return [], []
    entity = await model.get_for_edit(entity_id)
    if entity is None:
        return [], []
    has = {str(url) for url in entity.urls}
    taken = await graph.urls_taken(wanted, str(entity_id))
    new = [uri for uri in wanted if uri not in has and uri not in taken]
    if new:
        data = editable(entity.model_dump())
        data["urls"] = [*entity.urls, *new]
        try:
            await model.Update(**data).save(expected_version=entity.meta.version)
        except PanglossWriteError as error:
            # (the mention is reconciled already: that the entity could not be given the URIs, taken at that moment
            # or changed meanwhile, is said, and does not undo it)
            logger.warning(
                "%s %s was not given %s: %s", model.__name__, entity_id, new, error
            )
            return [], [uri for uri in wanted if uri not in has]
    return new, [uri for uri in wanted if uri in taken]


def entity_model(type: str, standing_for: str) -> Any:
    """The class of an entity that is to take the place of a mention of `standing_for`: it must be that class or one
    below it"""
    models = ModelRegistry._model_dict
    model = models.get(type)
    wanted = models.get(standing_for)
    if model is None or not issubclass(model, Entity):
        raise PanglossReconcileError(f"{type} is not a class of entity")
    if wanted is None or model not in get_concrete_types(wanted):
        raise PanglossReconcileError(
            f"A {type} cannot take the place of an unreconciled {standing_for}"
        )
    return model


async def _reconcile_one(row: dict[str, Any], model: Any, entity_id: UUID) -> Any:
    """Put the entity in the place of one mention (a row of `graph`). Gives the head of its document, as read"""

    def reference(part: dict[str, Any]) -> dict[str, Any]:
        made: dict[str, Any] = {"type": model.__name__, "id": entity_id}
        # (the properties of the relation to it, a certainty say, are of the relation: kept)
        if part.get("edge_properties") is not None:
            made["edge_properties"] = part["edge_properties"]
        return made

    return await rewrite_part(row["head_type"], row["head_id"], row["id"], reference)


async def reconcile(
    id: UUID,
    type: str,
    entity_id: UUID,
    also: list[UUID] | None = None,
    in_form: bool = False,
    suggestions: list[UUID] | None = None,
) -> Reconciled:
    """Reconcile a mention with an entity: the entity takes its place in its document, and is given its URIs. The
    other mentions named (`also`: from `similar`) are reconciled with the same entity in the background.

    `in_form`: the mention is being reconciled in a form of its document that is not saved yet, where the entity is
    put in its place as a change of the form. Its document is then not written here (that would make the form
    stale), neither for this mention nor for the others of it that are named: the entity is given the URIs, and
    the others in other documents are done.

    `suggestions`: identifications a toolchain suggested that name a URI of the mention (`suggestions_of_mention`),
    to be confirmed as this entity, in the background too."""
    row = await graph.mention(str(id))
    if row is None:
        raise PanglossNoSuchTaskError(f"There is no unreconciled mention {id}")
    model = entity_model(type, row["unreconciled_type"])
    # (without what refers to it, which may be thousands of documents, and more with each mention reconciled)
    entity = await model.get_for_edit(entity_id)
    if entity is None:
        raise PanglossReconcileError(f"There is no {type} {entity_id}")
    # (the id of the entity itself: it may have been named by a URL)
    entity_id = entity.id

    if not in_form:
        await _reconcile_one(row, model, entity_id)
    added, taken = await give_uris(model, entity_id, row["uris"])

    others = [other for other in dict.fromkeys(also or []) if other != id]
    if in_form:
        elsewhere = []
        for other in others:
            found = await graph.mention(str(other))
            if found is not None and found["head_id"] != row["head_id"]:
                elsewhere.append(other)
        others = elsewhere

    async def reconcile_other(other: UUID) -> None:
        other_row = await graph.mention(str(other))
        if other_row is None:
            raise PanglossNoSuchTaskError(f"There is no unreconciled mention {other}")
        entity_model(type, other_row["unreconciled_type"])
        await _reconcile_one(other_row, model, entity_id)
        await give_uris(model, entity_id, other_row["uris"])

    if others:
        in_background(one_by_one(others, "Reconciling", reconcile_other))
    if suggestions:
        from pangloss_review import identify

        others_count = await identify.confirm_as_entity(
            suggestions,
            {"type": model.__name__, "id": entity_id},
            except_head=row["head_id"] if in_form else None,
        )
    else:
        others_count = 0
    return Reconciled(
        id=id,
        entity=Ref(type=model.__name__, id=entity_id, label=entity.label),
        head=Ref(type=row["head_type"], id=row["head_id"], label=row["head_label"]),
        uris_added=added,
        uris_taken=taken,
        queued=len(others) + others_count,
    )


async def reconcile_with(
    mentions: list[UUID], type: str, entity_id: UUID, except_head: str | None = None
) -> int:
    """Reconcile mentions with an entity that something else says they are (an identification that names their
    URI, confirmed), in the background; not those of one document (`except_head`: its form does them). Gives how
    many are being done"""
    model: Any = ModelRegistry._model_dict.get(type)
    if model is None or not issubclass(model, Entity):
        raise PanglossReconcileError(f"{type} is not a class of entity")
    rows = await graph.mentions_by_id([str(id) for id in dict.fromkeys(mentions)])
    wanted = [UUID(row["id"]) for row in rows if row["head_id"] != except_head]

    async def reconcile_other(other: UUID) -> None:
        other_row = await graph.mention(str(other))
        if other_row is None:
            raise PanglossNoSuchTaskError(f"There is no unreconciled mention {other}")
        entity_model(type, other_row["unreconciled_type"])
        await _reconcile_one(other_row, model, entity_id)
        await give_uris(model, entity_id, other_row["uris"])

    if wanted:
        in_background(one_by_one(wanted, "Reconciling", reconcile_other))
    return len(wanted)
