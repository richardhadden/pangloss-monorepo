"""A statement compared with the statements it is paired with (implementation_docs/spaces-and-comparison-plan.md,
step 6.5; the route is `GET /api/compare/{type}/{ref}`, `api.py`):

    await compare(id, see_unpublished) -> Comparison | None

In one read transaction: the statement and its pairs by rule (`pairs.pairs_in`), the verdict of each pair worked
out (`maths.verdict` with every compared class's `rules.rules()`, then `settle` over the entries, which is `maths.settled` of what they say once people's judgements are in), the judgements
people have made of each pair (`judgements.judgements_of`), and the labels of the statements and their heads, for a
chip (one statement: `LABELS_QUERY`). None where `pairs_in` gives no statement (not there, not of a compared class,
not the reader's to see, inside a space that is `compared=False`).

**A person's judgement overrides** (`overridden`): where a pair has one, the newest decides the entry's `relation`
(`two_events` is the relation `two`) and `fields`; `how` is then empty (a judgement says which fields, not how) and
`reported` false. `worked_out` keeps what the maths said (`relation`, `fields`, `how`, `reported`) on every entry,
so that both can be shown. A judgement on a statement changed since it was cited still overrides, and says so
(`changed_since_cited` on it). The rest of the verdict (`likelihood`, `within`, `strength`, `superseded`, `first`,
`second`, `common`) is the maths' whatever a person said.

The entries are in the order of what the maths said: by `strength`, highest first, `two` and `nothing` last, then by
the other's id. Nothing is written."""

import dataclasses
from collections.abc import Mapping, Sequence
from typing import Any
from uuid import UUID

from pangloss_compare import maths
from pangloss_compare.judgements import Judgement
from pangloss_compare.pairs import Pair

# (what a person's verdict says, as a relation of `maths.RELATIONS`: the rest are named alike)
AS_RELATION = {"two_events": "two"}

# Where the maths says the two are not one thing: last
APART = ("two", "nothing")

# The label of each statement and of its head (one row each), for a chip. The ids are those `pairs_in` read as the
# reader in the same transaction
LABELS_QUERY = """
    UNWIND $ids AS nid
    MATCH (n:PGIndexableNode {id: nid})
    OPTIONAL MATCH (h:HeadNode {id: n.head_node_id})
    WITH n, coalesce(h, n) AS h
    RETURN n.id AS id, n.type AS type, n.label AS label, h.id AS head, h.type AS head_type, h.label AS head_label
"""


@dataclasses.dataclass(frozen=True)
class Named:
    """A statement as a chip shows it: its id, class and label, and its head's"""

    id: str
    type: str
    label: str | None = None
    head: str | None = None
    head_type: str | None = None
    head_label: str | None = None

    def as_json(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "type": self.type,
            "label": self.label,
            "head": {"id": self.head, "type": self.head_type, "label": self.head_label},
        }


@dataclasses.dataclass(frozen=True)
class Said:
    """What an entry says of a pair: the maths', or a person's"""

    relation: str
    fields: tuple[str, ...] = ()
    how: Mapping[str, str] = dataclasses.field(default_factory=dict)
    reported: bool = False

    def as_json(self) -> dict[str, Any]:
        return {
            "relation": self.relation,
            "fields": list(self.fields),
            "how": dict(self.how),
            "reported": self.reported,
        }


def worked_out(verdict: maths.Verdict) -> Said:
    return Said(verdict.relation, verdict.fields, dict(verdict.how), verdict.reported)


def overridden(verdict: maths.Verdict, judgements: Sequence[Judgement]) -> Said:
    """What the entry says: the newest judgement's (the first of `judgements`, newest first), else the maths'"""
    if not judgements:
        return worked_out(verdict)
    newest = judgements[0]
    return Said(AS_RELATION.get(newest.verdict, newest.verdict), newest.fields)


def order_key(verdict: maths.Verdict, other: str) -> tuple[bool, float, str]:
    """By what the maths said: the strongest first, `two` and `nothing` last, then by id"""
    return verdict.relation in APART, -verdict.strength, other


@dataclasses.dataclass(frozen=True)
class Entry:
    other: Named
    verdict: maths.Verdict
    pair: Pair
    judgements: tuple[Judgement, ...] = ()
    superseded: bool = False
    """(`settle`) what this only reports of a prescription, another entry tells"""

    @property
    def said(self) -> Said:
        return overridden(self.verdict, self.judgements)

    @property
    def judged(self) -> str | None:
        return self.judgements[0].verdict if self.judgements else None

    def as_json(self) -> dict[str, Any]:
        v = self.verdict
        return {
            "other": self.other.as_json(),
            **self.said.as_json(),
            "likelihood": v.likelihood,
            "within": v.within,
            "strength": v.strength,
            "superseded": self.superseded,
            "first": v.first,
            "second": v.second,
            "common": v.common,
            "workedOut": worked_out(v).as_json(),
            "found": "rule",
            "by": [
                {"field": field, "entity": entity, "kind": kind}
                for field, entity, kind in self.pair.by
            ],
            "judged": self.judged,
            "judgements": [j.as_json() for j in self.judgements],
        }


def settle(entries: Sequence[Entry]) -> list[Entry]:
    """`maths.settled`, of what the entries say and not of the maths alone: once an entry tells what came of a
    prescription (it asserts or denies it, or a person has judged that it does), an entry that only reports of the
    same prescription, and that no person has judged, is `superseded`. A pair a person judged to be of two events
    tells nothing"""
    told = {
        e.verdict.first
        for e in entries
        if e.said.relation in maths.ANSWERS and not e.said.reported
    }
    return [
        dataclasses.replace(
            e,
            superseded=not e.judgements
            and e.said.relation in maths.ANSWERS
            and e.said.reported
            and e.verdict.first in told,
        )
        for e in entries
    ]


@dataclasses.dataclass(frozen=True)
class Comparison:
    statement: Named
    entries: tuple[Entry, ...]
    more: bool = False
    """Some pairs were cut (`COMPARE_MOST_PAIRS`)"""

    def as_json(self) -> dict[str, Any]:
        return {
            "statement": self.statement.as_json(),
            "pairs": [entry.as_json() for entry in self.entries],
            "more": self.more,
        }


async def _named(tx: Any, told: Sequence[maths.Told]) -> dict[str, Named]:
    result = await tx.run(LABELS_QUERY, ids=[t.id for t in told])
    rows = {str(r["id"]): r async for r in result}
    found: dict[str, Named] = {}
    for t in told:
        r = rows.get(t.id)
        found[t.id] = Named(
            t.id,
            t.type,
            None if r is None else r["label"],
            t.head,
            None if r is None else r["head_type"],
            None if r is None else r["head_label"],
        )
    return found


async def compare(
    id: str | UUID, see_unpublished: bool, most: int | None = None
) -> Comparison | None:
    """The comparison of the statement `id` with its pairs, as the reader may see them (the module's docstring).
    `most`: `COMPARE_MOST_PAIRS` unless given"""
    from pangloss_core import backend

    from pangloss_compare import judgements, pairs, settings
    from pangloss_compare.rules import rules

    most = settings.most_pairs() if most is None else most
    database = backend.current().database()

    @database.read_transaction
    async def run(tx: Any) -> Comparison | None:
        statement, others, found = await pairs.pairs_in(tx, id, see_unpublished, most)
        if statement is None:
            return None
        known = rules()
        paired = [p for p in found.found if p.id in others]
        verdicts = [maths.verdict(statement, others[p.id], known) for p in paired]
        judged = await judgements.judgements_of(
            tx, statement.id, [p.id for p in paired], see_unpublished=see_unpublished
        )
        named = await _named(tx, [statement, *(others[p.id] for p in paired)])
        entries = sorted(
            settle(
                [
                    Entry(named[p.id], v, p, tuple(judged.get(p.id, ())))
                    for p, v in zip(paired, verdicts, strict=True)
                ]
            ),
            key=lambda e: order_key(e.verdict, e.other.id),
        )
        return Comparison(named[statement.id], tuple(entries), found.more)

    return await run()
