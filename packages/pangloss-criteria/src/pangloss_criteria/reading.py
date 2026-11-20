"""What the interface asks of descriptions, on the server (implementation_docs/matches-criteria.md, "The API"): what
criteria would find before they are saved (`preview`), and the candidates of a saved description, in pages
(`candidates`). The routes are in `api.py`; from Python, and through the SDK, `pangloss_criteria.preview(...)` and
`pangloss_criteria.candidates(...)` (`access`)."""

from collections.abc import Iterable
from typing import Any
from uuid import UUID

from pangloss_core import Transaction, backend
from pangloss_cypher import fragments
from pangloss_cypher.values import native_datetime
from pangloss_models import Entity, ModelRegistry, PanglossSearchError
from pangloss_models.citations import CITATION
from pangloss_models.exceptions import PanglossUnknownTypeError
from pangloss_models.search import resolve_search_type

from pangloss_criteria.access import (
    BrokenDescription,
    BrokenPage,
    Candidate,
    CandidatesPage,
    Mention,
    MentionsPage,
    Preview,
    Reference,
    SharedDescription,
    SharedListed,
    SharedPage,
    Similar,
)
from pangloss_criteria.effective import FIELD, Shared, cited_id, read_shared, shared_of
from pangloss_criteria.evaluate import evaluate, max_candidates
from pangloss_criteria.models import DESCRIPTION, EXCLUDED, NAME
from pangloss_criteria.pattern import SearchPattern, check_stored, combined
from pangloss_criteria.worker import is_pending

PREVIEWED = 5
"""How many candidates a preview gives (the first by label)"""


def checked_pattern(criteria: Any) -> SearchPattern:
    """Criteria as a description would store them: a pattern that may be stored, of an entity class. (Not only of
    a class with `CriteriaMeta(allowed=True)`: a field may name `MatchesCriteria[Place]` in its annotation.)
    Raises `PanglossSearchError`, naming the path, if they are not"""
    if criteria is None or criteria == {} or criteria == "":
        raise PanglossSearchError("criteria: the criteria to preview are needed")
    try:
        pattern = SearchPattern(criteria)
    except ValueError as error:
        raise PanglossSearchError(f"criteria: {error}") from None
    check_stored(pattern, None, EXCLUDED)
    model = resolve_search_type(pattern.type)
    if not (isinstance(model, type) and issubclass(model, Entity)):
        raise PanglossSearchError(
            f"type: '{pattern.type}' is not a class that may be described by criteria (it is no entity)"
        )
    return pattern


async def the_shared(id: UUID | str) -> Shared:
    """The shared description of the id; raises `PanglossSearchError` if there is none (or it is deleted)"""
    found = (await read_shared([id])).get(str(id))
    if found is None or found.deleted or found.criteria is None:
        raise PanglossSearchError(f"description: there is no shared description {id}")
    return found


def own_of(criteria: Any, shared: Shared) -> SearchPattern | None:
    """A mention's own criteria beside a shared description it cites, as a client gives them: none, if it gives none,
    or only the shared description's class with no conditions"""
    if criteria is None or criteria == {} or criteria == "":
        return None
    try:
        pattern = SearchPattern(criteria)
    except ValueError as error:
        raise PanglossSearchError(f"criteria: {error}") from None
    if not pattern.where and pattern.type == SearchPattern(shared.criteria).type:
        return None
    return pattern


async def effective_of(criteria: Any, description: UUID | str | None) -> SearchPattern:
    """What a mention with these criteria of its own, citing the shared description `description` (or none), is
    evaluated by, checked as a description would store it"""
    if description is None:
        return checked_pattern(criteria)
    shared = await the_shared(description)
    own = own_of(criteria, shared)
    if own is not None:
        checked_pattern(own.data)
    return checked_pattern(combined(SearchPattern(shared.criteria), own).data)


async def preview(
    criteria: Any,
    named: Iterable[UUID | str] = (),
    description: UUID | str | None = None,
) -> Preview:
    """What criteria would find if a description with them were saved now, under the rules of an evaluation (not
    through other descriptions; never one of `named`, the entities the document being edited names; merged ids
    resolved): the count, the first `PREVIEWED` by label, and whether they are too many to link. As a logged-in
    reader. `description`: the id of a shared description the mention cites, whose criteria are evaluated with
    these (which may then have no conditions, or be none). Raises `PanglossSearchError` for criteria a description
    could not store"""
    pattern = await effective_of(criteria, description)
    found = await evaluate(pattern, without=[str(id) for id in named], limit=PREVIEWED)
    return Preview(
        count=found.count,
        candidates=[
            Candidate(type=item["type"], id=item["id"], label=item["label"])
            for item in found.candidates[:PREVIEWED]
        ],
        too_broad=found.count > max_candidates(),
    )


# The description and its head, if the reader may see the head (deleted, unpublished: as the document read)
DESCRIPTION_QUERY = f"""
    MATCH (d:{NAME} {{id: $id}})
    MATCH (head:HeadNode {{id: d.head_node_id}})
    WHERE {fragments.visible("head")}
    RETURN head.id AS head, head.type AS head_type, coalesce(d.candidate_count, 0) AS count,
           coalesce(d.candidate_count_everyone, 0) AS count_everyone,
           d.evaluated_when AS evaluated_when, d.broken AS broken, d.broken_since AS broken_since,
           d.criteria AS criteria, {cited_id("d")} AS cites, d.same_one AS same_one
"""

# The places of a mark in a head: the descriptions of the same one, and the criteria of those that hold them
PLACES_QUERY = f"""
    MATCH (d:PGIndexableNode {{head_node_id: $head}})
    WHERE d:{NAME} AND d.same_one = $same_one
    RETURN d.id AS id, d.criteria AS criteria, {cited_id("d")} AS cites
    ORDER BY id
"""

# Its linked candidates that the reader may see, by label (at most the cap: a page is taken of them here)
LINKED_QUERY = f"""
    MATCH (d:{NAME} {{id: $id}})-[edge:target]->(candidate:Entity)
    WHERE {fragments.forward("edge")} AND coalesce(edge.{fragments.COMPUTED_EDGE}, false)
      AND {fragments.edge_visible("edge")} AND {fragments.listed("candidate")}
    RETURN candidate.type AS type, candidate.id AS id, candidate.label AS label
    ORDER BY candidate.label, candidate.id
"""


async def head_of(id: UUID | str) -> tuple[str, str] | None:
    """The type and id of the head a description is in (the id of its `MatchesCriteria`), if the reader of the
    request may see it; None if there is no such description"""
    current = backend.current()

    @current.database().read_transaction
    async def read(tx: Transaction) -> tuple[str, str] | None:
        record = await (
            await tx.run(
                DESCRIPTION_QUERY,
                id=str(id),
                see_unpublished=current.unpublished_visible(),
            )
        ).single()
        return None if record is None else (record["head_type"], record["head"])

    return await read()


async def candidates(
    id: UUID | str, page: int = 1, page_size: int = 25
) -> CandidatesPage | None:
    """A page of the linked candidates of a saved description (the id of the `MatchesCriteria` node), by label, as
    the reader of the request may see them; with its count, and whether its document is pending; the criteria it is
    evaluated by (its own, or for a place with none, those of the place of its mark that holds them) and how many
    places of its document share its mark. Those past the cap (`CRITERIA_MAX_CANDIDATES`) are not linked, and not
    listed. None if there is no description of the id that the reader may see"""
    current = backend.current()
    see_unpublished = current.unpublished_visible()

    @current.database().read_transaction
    async def read(
        tx: Transaction,
    ) -> tuple[dict[str, Any], list[dict[str, Any]]] | None:
        record = await (
            await tx.run(DESCRIPTION_QUERY, id=str(id), see_unpublished=see_unpublished)
        ).single()
        if record is None:
            return None
        rows = [
            dict(row)
            async for row in await tx.run(
                LINKED_QUERY, id=str(id), see_unpublished=see_unpublished
            )
        ]
        description = dict(record)
        description["places"] = 1
        if description["same_one"] is not None:
            # (the head is one the reader may see: the description's own)
            places = [
                dict(row)
                async for row in await tx.run(
                    PLACES_QUERY,
                    head=description["head"],
                    same_one=str(description["same_one"]),
                )
            ]
            description["places"] = max(1, len(places))
            if description["criteria"] is None and description["cites"] is None:
                holder = next(
                    (
                        p
                        for p in places
                        if p["criteria"] is not None or p["cites"] is not None
                    ),
                    None,
                )
                if holder is not None:
                    description["criteria"] = holder["criteria"]
                    description["cites"] = holder["cites"]
        description["shared"] = (
            None
            if description["cites"] is None
            else (await shared_of(tx, [description["cites"]])).get(
                str(description["cites"])
            )
        )
        return description, rows

    found = await read()
    if found is None:
        return None
    description, linked = found
    # (the reader's own count, as a read of the document gives it: `MatchesCriteria.the_readers_own_count`)
    count = description["count" if see_unpublished else "count_everyone"]
    start = (page - 1) * page_size
    return CandidatesPage(
        count=count,
        too_broad=count > len(linked),
        pending=await is_pending(description["head"]),
        evaluated_when=native_datetime(description["evaluated_when"]),
        broken=description["broken"],
        broken_since=description["broken_since"],
        page=page,
        page_size=page_size,
        candidates=[Candidate(**row) for row in linked[start : start + page_size]],
        criteria=None
        if description["criteria"] is None
        else SearchPattern(description["criteria"]).data,
        places=description["places"],
        shared=None
        if description["cites"] is None
        else shared_view(description["cites"], description["shared"]),
    )


def shared_view(id: Any, found: Shared | None) -> SharedDescription:
    """A shared description as the answers give it: its criteria none if it is not there (or deleted)"""
    there = found is not None and not found.deleted and found.criteria is not None
    return SharedDescription(
        id=UUID(str(id)),
        label=found.label if found is not None else None,
        criteria=_criteria_of(found.criteria) if there and found else None,
    )


# The descriptions that are broken (their criteria no longer fit the models), in documents the reader may see, by the
# label of their document. A place with no criteria of its own (`same_one`) is not one: its mark's holder is
BROKEN_WHERE = f"""
    MATCH (d:{NAME})
    WHERE d.broken IS NOT NULL AND (d.criteria IS NOT NULL OR {cited_id("d")} IS NOT NULL)
    MATCH (head:HeadNode {{id: d.head_node_id}})
    WHERE {fragments.visible("head")}
"""

BROKEN_COUNT_QUERY = BROKEN_WHERE + "RETURN count(d) AS count"

BROKEN_QUERY = (
    BROKEN_WHERE
    + """
    RETURN d.id AS id, d.wording AS wording, d.criteria AS criteria, d.broken AS broken,
           d.broken_since AS broken_since, head.id AS head_id, head.type AS head_type, head.label AS head_label
    ORDER BY head.label, head.id, d.id
    SKIP $skip LIMIT $limit
"""
)


def _criteria_of(text: Any) -> dict[str, Any] | None:
    try:
        return SearchPattern(text).data
    except ValueError:
        return None


async def broken(page: int = 1, page_size: int = 25) -> BrokenPage:
    """A page of the descriptions whose criteria no longer fit the models (`broken`: said by a migration or by the
    worker), in the documents the reader may see, by the label of their document: what is to be put right"""
    current = backend.current()
    see_unpublished = current.unpublished_visible()

    @current.database().read_transaction
    async def read(tx: Transaction) -> tuple[int, list[dict[str, Any]]]:
        record = await (
            await tx.run(BROKEN_COUNT_QUERY, see_unpublished=see_unpublished)
        ).single()
        rows = [
            dict(row)
            async for row in await tx.run(
                BROKEN_QUERY,
                see_unpublished=see_unpublished,
                skip=(page - 1) * page_size,
                limit=page_size,
            )
        ]
        return (record["count"] if record else 0), rows

    count, rows = await read()
    return BrokenPage(
        count=count,
        page=page,
        page_size=page_size,
        results=[
            BrokenDescription(
                id=row["id"],
                wording=row["wording"],
                criteria=_criteria_of(row["criteria"]),
                broken=row["broken"],
                broken_since=row["broken_since"],
                head=Reference(
                    type=row["head_type"], id=row["head_id"], label=row["head_label"]
                ),
            )
            for row in rows
        ],
    )


# --- shared descriptions ----------------------------------------------------------------------------------------------

# The shared descriptions the reader may see, by label (their criteria's class is in their text: tested in Python)
SHARED_LIST_QUERY = f"""
    MATCH (s:{DESCRIPTION})
    WHERE {fragments.visible("s")}
      AND ($q IS NULL OR toLower(coalesce(s.label, '')) CONTAINS toLower($q))
    RETURN s.id AS id, s.type AS type, s.label AS label, s.criteria AS criteria
    ORDER BY s.label, s.id
"""

# The mentions that cite a shared description, in documents the reader may see
CITING_WHERE = f"""
    MATCH (citation:{CITATION} {{target_id: id}})<-[edge:{FIELD}]-(d:{NAME})
    WHERE NOT coalesce(edge.reverse, false)
    MATCH (head:HeadNode {{id: d.head_node_id}})
    WHERE {fragments.visible("head")}
"""

MENTION_COUNTS_QUERY = (
    "UNWIND $ids AS id\n" + CITING_WHERE + "RETURN id, count(DISTINCT d) AS mentions"
)

MENTIONS_COUNT_QUERY = (
    "WITH $id AS id\n" + CITING_WHERE + "RETURN count(DISTINCT d) AS count"
)

MENTIONS_QUERY = (
    "WITH $id AS id\n"
    + CITING_WHERE
    + """
    RETURN d.id AS id, d.wording AS wording, d.criteria AS criteria,
           head.id AS head_id, head.type AS head_type, head.label AS head_label
    ORDER BY head.label, head.id, d.id
    SKIP $skip LIMIT $limit
"""
)


def _of_types(criteria: Any, types: list[type] | None) -> bool:
    if types is None:
        return True
    try:
        model = resolve_search_type(SearchPattern(criteria).type)
    except PanglossSearchError, ValueError:
        return False
    return isinstance(model, type) and any(issubclass(model, cls) for cls in types)


def types_named(types: Iterable[str] | None) -> list[type] | None:
    """The classes named (`Person,Organisation`); raises `PanglossSearchError` for a name that is no class"""
    if types is None:
        return None
    names = [name.strip() for name in types if name and name.strip()]
    if not names:
        return None
    try:
        return [resolve_search_type(name) for name in names]
    except PanglossSearchError, PanglossUnknownTypeError, ValueError:
        raise PanglossSearchError(
            f"types: {', '.join(names)} are not all classes of the models"
        ) from None


async def shared_descriptions(
    types: Iterable[str] | None = None,
    q: str | None = None,
    page: int = 1,
    page_size: int = 25,
) -> SharedPage:
    """A page of the shared descriptions the reader may see, by label: those whose criteria are of one of `types`
    (names of classes) or a class below one (all, without), and whose label holds `q`; each with how many mentions
    in documents the reader may see cite it. Raises `PanglossSearchError` for a name that is no class"""
    wanted = types_named(types)
    current = backend.current()
    see_unpublished = current.unpublished_visible()
    if DESCRIPTION not in ModelRegistry.all_models():
        return SharedPage(count=0, page=page, page_size=page_size, results=[])

    @current.database().read_transaction
    async def read(
        tx: Transaction,
    ) -> tuple[int, list[dict[str, Any]], dict[str, int]]:
        rows = [
            dict(row)
            async for row in await tx.run(
                SHARED_LIST_QUERY, q=q or None, see_unpublished=see_unpublished
            )
        ]
        rows = [row for row in rows if _of_types(row["criteria"], wanted)]
        start = (page - 1) * page_size
        shown = rows[start : start + page_size]
        counts = {
            row["id"]: row["mentions"]
            async for row in await tx.run(
                MENTION_COUNTS_QUERY,
                ids=[row["id"] for row in shown],
                see_unpublished=see_unpublished,
            )
        }
        return len(rows), shown, counts

    count, shown, counts = await read()
    return SharedPage(
        count=count,
        page=page,
        page_size=page_size,
        results=[
            SharedListed(
                id=row["id"],
                label=row["label"],
                criteria=_criteria_of(row["criteria"]),
                mentions=counts.get(row["id"], 0),
            )
            for row in shown
        ],
    )


async def shared_mentions(
    id: UUID | str, page: int = 1, page_size: int = 25
) -> MentionsPage | None:
    """A page of the mentions that cite the shared description `id`, in the documents the reader may see, by the
    label of their document: each with its wording, its own criteria (or none) and its document. None if there is no
    such shared description"""
    found = (await read_shared([id])).get(str(id))
    if found is None or found.deleted:
        return None
    current = backend.current()
    see_unpublished = current.unpublished_visible()

    @current.database().read_transaction
    async def read(tx: Transaction) -> tuple[int, list[dict[str, Any]]]:
        record = await (
            await tx.run(
                MENTIONS_COUNT_QUERY, id=str(id), see_unpublished=see_unpublished
            )
        ).single()
        rows = [
            dict(row)
            async for row in await tx.run(
                MENTIONS_QUERY,
                id=str(id),
                see_unpublished=see_unpublished,
                skip=(page - 1) * page_size,
                limit=page_size,
            )
        ]
        return (record["count"] if record else 0), rows

    count, rows = await read()
    return MentionsPage(
        count=count,
        page=page,
        page_size=page_size,
        results=[
            Mention(
                id=row["id"],
                wording=row["wording"],
                criteria=None
                if row["criteria"] is None
                else _criteria_of(row["criteria"]),
                head=Reference(
                    type=row["head_type"], id=row["head_id"], label=row["head_label"]
                ),
            )
            for row in rows
        ],
    )


SIMILAR_SHOWN = 20
"""How many documents `similar` names"""

# The mentions with exactly these criteria of their own (or none) citing exactly this shared description (or
# none), in documents the reader may see other than one
SIMILAR_WHERE = f"""
    MATCH (d:{NAME})
    WHERE (($own IS NULL AND d.criteria IS NULL) OR d.criteria = $own)
      AND NOT coalesce(d.head_node_id = $except, false)
    WITH d, {cited_id("d")} AS cites
    WHERE (($description IS NULL AND cites IS NULL) OR cites = $description)
      AND (d.criteria IS NOT NULL OR cites IS NOT NULL)
    MATCH (head:HeadNode {{id: d.head_node_id}})
    WHERE {fragments.visible("head")}
"""

SIMILAR_COUNT_QUERY = SIMILAR_WHERE + "RETURN count(DISTINCT d) AS count"

SIMILAR_HEADS_QUERY = (
    SIMILAR_WHERE
    + """
    WITH DISTINCT head
    RETURN head.id AS id, head.type AS type, head.label AS label
    ORDER BY head.label, head.id
    LIMIT $limit
"""
)


async def own_and_cited(
    type: str | None, where: Any, description: UUID | str | None
) -> tuple[SearchPattern | None, Shared | None]:
    """What a client gives of a mention's criteria (`type`, `where`, the shared description it cites) as what is
    stored: its own criteria (or none), and the shared description. Raises `PanglossSearchError` for criteria that
    could not be stored, or a shared description that is not there"""
    if description is None:
        return checked_pattern({"type": type, "where": where or {}}), None
    shared = await the_shared(description)
    own = own_of(
        {"type": type or SearchPattern(shared.criteria).type, "where": where or {}},
        shared,
    )
    await effective_of(None if own is None else own.data, description)
    return own, shared


async def similar(
    type: str | None,
    where: Any,
    description: UUID | str | None = None,
    except_: UUID | str | None = None,
) -> Similar:
    """How many mentions in other documents (not `except_`, a head) have exactly these criteria of their own and
    cite the same shared description (or none), and the first `SIMILAR_SHOWN` of their documents by label. Raises
    `PanglossSearchError` for criteria that could not be stored"""
    own, shared = await own_and_cited(type, where, description)
    current = backend.current()
    params = {
        "own": None if own is None else own.text(),
        "description": None if shared is None else shared.id,
        "except": None if except_ is None else str(except_),
        "see_unpublished": current.unpublished_visible(),
    }

    @current.database().read_transaction
    async def read(tx: Transaction) -> tuple[int, list[dict[str, Any]]]:
        record = await (await tx.run(SIMILAR_COUNT_QUERY, **params)).single()
        heads = [
            dict(row)
            async for row in await tx.run(
                SIMILAR_HEADS_QUERY, **params, limit=SIMILAR_SHOWN
            )
        ]
        return (record["count"] if record else 0), heads

    count, heads = await read()
    return Similar(
        count=count,
        documents=[Reference(**row) for row in heads],
    )


__all__ = [
    "PREVIEWED",
    "BrokenDescription",
    "BrokenPage",
    "broken",
    "Candidate",
    "CandidatesPage",
    "Preview",
    "candidates",
    "checked_pattern",
    "effective_of",
    "head_of",
    "own_and_cited",
    "preview",
    "shared_descriptions",
    "shared_mentions",
    "similar",
]
