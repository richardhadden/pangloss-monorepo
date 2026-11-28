"""What people have said of a statement's pairs (implementation_docs/spaces-and-comparison-plan.md, step 6.5):

    await judgements_of(tx, id, others, see_unpublished=...) -> {other id: [Judgement, ...]}

In an open read transaction, one statement: the judgements (documents of a class below `EventJudgement`,
`pangloss_compare.models`) that cite the statement `id` in one of their fields `statement` and `other` and one of
`others` in the other field. A judgement is of the pair in either order. Each with its id, class, label, `verdict`,
`fields`, `note`, who made it and when (the record of its head's creation, as every read gives the creators), and
`changed_since_cited`: either of its two citations is marked changed (`pangloss_cypher.citations`: a cited statement
changed with `acknowledge_citations` marks every citation of it; a judgement is never saved again, `models.py`, so
the mark is for good: a new judgement is how a person says they have looked again). Newest first, then by id.

What the reader sees: only a judgement the reader may see itself (`fragments.visible`, by its head: one that is
deleted, or unpublished for a reader who may not see what is not published, is left out). The statements it cites
are the caller's: `id` and `others` are those the reader may see (`pairs.pairs_in` read them as the reader, in the
same transaction), so a judgement that cites a statement the reader may not see is never matched.

The query starts from the citations of `id` by their indexed `target_id`, follows the edge into each to its
judgement (the class tested after the match, as `pairs.py` does), then the judgement's other citation."""

import dataclasses
import datetime
from collections.abc import Iterable, Sequence
from typing import Any

from pydantic.alias_generators import to_camel

from pangloss_compare.models import BASE, CITING


@dataclasses.dataclass(frozen=True)
class Judgement:
    id: str
    type: str
    verdict: str
    fields: tuple[str, ...]
    note: str
    created_by: tuple[dict[str, Any], ...]
    """Who made it (each as a `Creator` gives it as JSON: `username`, `kind`, `version`, `date`)"""
    created_when: datetime.datetime | None
    changed_since_cited: bool
    """Either statement it cites has changed since it was cited"""
    label: str | None = None
    """Its own label (for a chip of it)"""

    def as_json(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "type": self.type,
            "label": self.label,
            "verdict": self.verdict,
            # (camelCase, as a payload's keys are: stored as Python's names)
            "fields": [to_camel(field) for field in self.fields],
            "note": self.note,
            "createdBy": list(self.created_by),
            "createdWhen": None
            if self.created_when is None
            else self.created_when.isoformat(),
            "changedSinceCited": self.changed_since_cited,
        }


def judgements_query(fragments: Any) -> str:
    head = fragments.head_of("j", "j_head")
    return f"""
        MATCH (c:PGCitation {{target_id: $id}})
        WITH c
        MATCH (c)<-[e]-(j)
        WHERE type(e) IN $citing AND {fragments.forward("e")}
        WITH c, e, j
        WHERE j:{BASE}
        MATCH (j)-[e2]->(c2:PGCitation)
        WHERE type(e2) IN $citing AND type(e2) <> type(e) AND {fragments.forward("e2")}
            AND c2.target_id IN $others
        {head.match}
        WITH c, c2, j, j_head
        WHERE (j.head_node_id IS NULL OR j_head IS NOT NULL) AND {fragments.visible("j", head)}
        WITH c, c2, j, {head} AS made
        OPTIONAL MATCH (made)<-[:is_creation_of]-(creation:PGCreation)
        RETURN j.id AS id, j.type AS type, j.label AS label, j.verdict AS verdict, j.fields AS fields, j.note AS note,
            c2.target_id AS other,
            coalesce(c.changed_since_cited, false) OR coalesce(c2.changed_since_cited, false) AS changed,
            {fragments.creators("creation")} AS created_by, creation.created_when AS created_when
    """


def _when(value: Any) -> datetime.datetime | None:
    from pangloss_cypher.values import native_datetime

    value = native_datetime(value)
    if isinstance(value, str):
        value = datetime.datetime.fromisoformat(value)
    if isinstance(value, datetime.datetime) and value.tzinfo is None:
        value = value.replace(tzinfo=datetime.UTC)
    return value if isinstance(value, datetime.datetime) else None


def _creators(value: Any) -> tuple[dict[str, Any], ...]:
    from pangloss_models.creators import Creator, creators_from

    return tuple(
        Creator.model_validate(each).model_dump(by_alias=True, mode="json")
        for each in creators_from(value)
    )


def newest_first(found: Iterable[Judgement]) -> list[Judgement]:
    """Newest first; one with no record of when, last; then by id, the greater first (deterministic)"""
    least = datetime.datetime.min.replace(tzinfo=datetime.UTC)
    return sorted(
        found,
        key=lambda j: (j.created_when is not None, j.created_when or least, j.id),
        reverse=True,
    )


async def judgements_of(
    tx: Any, id: str, others: Sequence[str], *, see_unpublished: bool
) -> dict[str, list[Judgement]]:
    """The judgements of each pair of `id` with one of `others`, by the other's id, newest first (the module's
    docstring). No others: no statement is run"""
    from pangloss_core import backend

    others = sorted(set(others) - {id})
    if not others:
        return {}
    from pangloss_models import ModelRegistry

    if BASE not in ModelRegistry._model_dict:
        # (the app's models are not declared: there can be no judgement)
        return {}
    result = await tx.run(
        judgements_query(backend.current().fragments),
        id=id,
        others=others,
        citing=list(CITING),
        see_unpublished=see_unpublished,
    )
    found: dict[str, dict[str, Judgement]] = {}
    async for r in result:
        judgement = Judgement(
            id=str(r["id"]),
            type=str(r["type"]),
            verdict=str(r["verdict"]),
            fields=tuple(r["fields"] or ()),
            note=r["note"] or "",
            created_by=_creators(r["created_by"]),
            created_when=_when(r["created_when"]),
            changed_since_cited=bool(r["changed"]),
            label=r["label"],
        )
        found.setdefault(str(r["other"]), {})[judgement.id] = judgement
    return {other: newest_first(by_id.values()) for other, by_id in found.items()}
