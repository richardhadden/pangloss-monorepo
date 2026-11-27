"""A statement compared with the statements it is paired with (implementation_docs/spaces-and-comparison-plan.md,
step 6.5; the route is `GET /api/compare/{type}/{ref}`, `api.py`):

    await compare(id, see_unpublished) -> Comparison | None
    await compare_near(id, see_unpublished) -> Comparison | None     # the pairs through near entities (step 6.4)

In one read transaction: the statement and its pairs by rule (`pairs.pairs_in`), the fit of people's judgements in
use (`fits.in_use_in`, one statement; used only where it is of today's signature, `fits.for_route`, and only those of
its two models that passed its check), the verdict of each pair worked out (`maths.verdict` with every compared
class's `rules.rules()` and the fit as `fitted`, then `settle` over the entries, which is `maths.settled` of what they
say once people's judgements are in), the judgements
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
the other's id. The answer says which fit it used (`model`: null, or its id, when it was made, how many judgements it is
of, and which of its two models were used, `oneEvent` and `answers`); `workedOut` is what the verdict said with
it. Nothing is written."""

import dataclasses
from collections.abc import Mapping, Sequence
from typing import Any
from uuid import UUID

from pangloss_compare import maths
from pangloss_compare.judgements import Judgement
from pangloss_compare.near import NEAR, NearPair
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
    found: str = "rule"
    """How the pair was found: `"rule"` (`pair.by` its reasons), or `"near"` (`near` its reasons)"""
    near: tuple[Mapping[str, Any], ...] = ()
    """Of a pair found through near entities: each reason as the answer gives it (`near_reason`)"""

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
            "found": self.found,
            "by": [dict(reason) for reason in self.near]
            if self.found == NEAR
            else [
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
    model: Mapping[str, Any] | None = None
    """The fit of people's judgements the verdicts were worked out with (`fits.for_route`), or None: by hand"""
    near: Mapping[str, Any] | None = None
    """Of the pairs through near entities (`compare_near`): `{profile, k, floor, state}`; None: the pairs by rule"""

    def as_json(self) -> dict[str, Any]:
        return {
            "statement": self.statement.as_json(),
            "pairs": [entry.as_json() for entry in self.entries],
            "more": self.more,
            "model": None if self.model is None else dict(self.model),
            "near": None if self.near is None else dict(self.near),
        }


async def _named(
    tx: Any, told: Sequence[maths.Told], entities: Sequence[str] = ()
) -> dict[str, Named]:
    """The statements as chips show them, by id; and in the same statement, of the entities of these ids, each its
    class and label"""
    result = await tx.run(LABELS_QUERY, ids=[*(t.id for t in told), *entities])
    rows = {str(r["id"]): r async for r in result}
    found: dict[str, Named] = {
        id: Named(id, str(rows[id]["type"]), rows[id]["label"])
        for id in entities
        if id in rows
    }
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

    from pangloss_compare import fits, judgements, learning, pairs, settings
    from pangloss_compare.rules import rules

    most = settings.most_pairs() if most is None else most
    database = backend.current().database()

    @database.read_transaction
    async def run(tx: Any) -> Comparison | None:
        statement, others, found = await pairs.pairs_in(tx, id, see_unpublished, most)
        if statement is None:
            return None
        known = rules()
        fitted, model = fits.for_route(await fits.in_use_in(tx), learning.signature(known))  # fmt: skip
        paired = [p for p in found.found if p.id in others]
        verdicts = [
            maths.verdict(statement, others[p.id], known, fitted=fitted) for p in paired
        ]
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
        return Comparison(named[statement.id], tuple(entries), found.more, model)

    return await run()


# --- the pairs through near entities (step 6.4) -------------------------------------------------------------


def near_reason(
    field: str, entity: str, near: str, score: float, named: Mapping[str, Named]
) -> dict[str, Any]:
    """A reason of a pair through near entities as the answer gives it: the field, X and X' (each its id, class and
    label, for a chip and for a link to merging them) and the score"""

    def chip(id: str) -> dict[str, Any]:
        found = named.get(id)
        return {
            "id": id,
            "type": None if found is None else found.type,
            "label": None if found is None else found.label,
        }

    return {
        "field": field,
        "kind": NEAR,
        "entity": chip(entity),
        "near": chip(near),
        "score": score,
    }


def near_entries(
    statement: maths.Told,
    found: Sequence[NearPair],
    others: Mapping[str, maths.Told],
    known: Mapping[str, maths.Rules],
    fitted: Mapping[str, Mapping[str, float]] | None,
    judged: Mapping[str, Sequence[Judgement]],
    named: Mapping[str, Named],
) -> list[Entry]:
    """The entries of the pairs through near entities (pure): each verdict of the statement and the other with each
    X' read as its X (`near.substituted`), only where it is neither `two` nor `nothing` (`near.shown`), in the order
    of the pairs by rule (`order_key`). Never `superseded` (`settle` is of the pairs by rule)"""
    from pangloss_compare import near

    entries = []
    for pair in found:
        other = others.get(pair.id)
        if other is None:
            continue
        verdict = maths.verdict(statement, near.substituted(other, pair), known, fitted=fitted)  # fmt: skip
        if not near.shown(verdict):
            continue
        entries.append(
            Entry(
                named[pair.id],
                verdict,
                Pair(pair.id, ()),
                tuple(judged.get(pair.id, ())),
                found=NEAR,
                near=tuple(
                    near_reason(t.field, t.entity, t.near, t.score, named)
                    for t in pair.by
                ),
            )
        )
    return sorted(entries, key=lambda e: order_key(e.verdict, e.other.id))


async def compare_near(
    id: str | UUID, see_unpublished: bool, most: int | None = None
) -> Comparison | None:
    """The comparison of the statement `id` with the statements paired with it through near entities only
    (`near.py`), as the reader may see them: the same shape as `compare`'s, with `near` saying by which profile, `k`
    and floor, and the searches' state (`none`: no profile, or `pangloss-vectors` not installed). None where `compare`
    gives None. `most`: `COMPARE_MOST_PAIRS` unless given.

    Two read transactions and the searches between them (each `nearest`'s own): the statement, and its label with
    its entities' classes (one statement); then the fit in use, the statements naming each X' with the pairs by rule
    (all of them, to leave out: `pairs.naming`, one query and the merges), those read, their judgements and the
    labels (one statement). Nothing is written"""
    from pangloss_core import backend

    from pangloss_compare import (
        fits,
        judgements,
        learning,
        near,
        pairs,
        reading,
        settings,
    )
    from pangloss_compare.rules import rules

    most = settings.most_pairs() if most is None else most
    profile = settings.near_profile() if settings.vectors_installed() else None
    k, floor = settings.near_k(), settings.near_floor()
    database = backend.current().database()

    @database.read_transaction
    async def first(tx: Any) -> tuple[maths.Told | None, dict[str, Named]]:
        key = str(id)
        statement = (await reading.read(tx, [key], see_unpublished=see_unpublished)).get(key)  # fmt: skip
        if statement is None:
            return None, {}
        entities = sorted({e for ids in statement.fields.values() for e in ids})
        return statement, await _named(tx, [statement], entities if profile else ())

    statement, own = await first()
    if statement is None:
        return None
    said = {"profile": profile, "k": k, "floor": floor, "state": near.NONE}
    if profile is None:
        return Comparison(own[statement.id], (), False, None, said)

    found = await near.searched(
        statement,
        profile=profile,
        k=k,
        floor=floor,
        see_unpublished=see_unpublished,
        classes={id: named.type for id, named in own.items() if id != statement.id},
    )
    said["state"] = found.state

    @database.read_transaction
    async def second(tx: Any) -> Comparison:
        known = rules()
        fitted, model = fits.for_route(await fits.in_use_in(tx), learning.signature(known))  # fmt: skip
        paired: list[NearPair] = []
        more = False
        if found.near:
            named_by = await pairs.naming(
                tx,
                statement,
                {root: list(by_near) for root, by_near in found.near.items()},
                see_unpublished=see_unpublished,
            )
            paired, more = near.candidates(
                named_by.named,
                found.near,
                own=statement.id,
                by_rule=named_by.by_rule,
                most=most,
            )
        others = await reading.read(tx, [p.id for p in paired], see_unpublished=see_unpublished)  # fmt: skip
        paired = [p for p in paired if p.id in others]
        judged = (
            await judgements.judgements_of(
                tx,
                statement.id,
                [p.id for p in paired],
                see_unpublished=see_unpublished,
            )
            if paired
            else {}
        )
        entities = sorted({e for p in paired for t in p.by for e in (t.entity, t.near)})
        named = await _named(tx, [statement, *(others[p.id] for p in paired)], entities)
        entries = near_entries(statement, paired, others, known, fitted, judged, named)
        return Comparison(named[statement.id], tuple(entries), more, model, said)

    return await second()
