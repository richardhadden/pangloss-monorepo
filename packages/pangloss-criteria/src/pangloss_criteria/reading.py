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
from pangloss_models import Entity, PanglossSearchError
from pangloss_models.search import resolve_search_type

from pangloss_criteria.access import Candidate, CandidatesPage, Preview
from pangloss_criteria.evaluate import evaluate, max_candidates
from pangloss_criteria.models import EXCLUDED, NAME
from pangloss_criteria.pattern import SearchPattern, check_stored
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


async def preview(criteria: Any, named: Iterable[UUID | str] = ()) -> Preview:
    """What criteria would find if a description with them were saved now, under the rules of an evaluation (not
    through other descriptions; never one of `named`, the entities the document being edited names; merged ids
    resolved): the count, the first `PREVIEWED` by label, and whether they are too many to link. As a logged-in
    reader. Raises `PanglossSearchError` for criteria a description could not store"""
    pattern = checked_pattern(criteria)
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
           d.evaluated_when AS evaluated_when, d.broken AS broken,
           d.criteria AS criteria, d.same_one AS same_one
"""

# The places of a mark in a head: the descriptions of the same one, and the criteria of those that hold them
PLACES_QUERY = f"""
    MATCH (d:PGIndexableNode {{head_node_id: $head}})
    WHERE d:{NAME} AND d.same_one = $same_one
    RETURN d.id AS id, d.criteria AS criteria
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
            if description["criteria"] is None:
                description["criteria"] = next(
                    (p["criteria"] for p in places if p["criteria"] is not None), None
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
        page=page,
        page_size=page_size,
        candidates=[Candidate(**row) for row in linked[start : start + page_size]],
        criteria=None
        if description["criteria"] is None
        else SearchPattern(description["criteria"]).data,
        places=description["places"],
    )


__all__ = [
    "PREVIEWED",
    "Candidate",
    "CandidatesPage",
    "Preview",
    "candidates",
    "checked_pattern",
    "head_of",
    "preview",
]
