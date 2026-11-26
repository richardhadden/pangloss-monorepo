"""How a justification holds: its **status**, from the walk (`pangloss_models.spaces`) over what it passed through.

A rule's match rests on each of its nodes that is not an entity (the node of a pattern, and one nested in it) and
on each relation it follows to an entity. Each is a **part** with a path: a node's stored path (`meta.path`); a
relation's, where it passes through a semantic space that says something (`buyer: Person | Not[Person]`), the path of
the node it starts at, that node, and the wrappers on the way. The walk
says of each part whether it is asserted, denied or neither, and the parts are put together:

- `asserted`: every part is;
- `denied`: one part is denied and the others asserted;
- `reported`, `prescribed`: neither asserted nor denied, leaning for it (a report, a belief; an order, a wish);
- `reported_not`, `prescribed_not`: the same, leaning against (it was reported that he did not; he was forbidden to);
- `nothing`: the source says nothing of it (it is not known that p; there was no service that p was a part of; two
  parts each denied).

A rule derives from the first, the third and the fourth (`DERIVES`); the others are no evidence of the positive, and
give no justification unless the rule asks for them (`.when(..., status=["denied"])`: a virtual edge class, "did not
buy from").

A fact is **summed up** from the statuses of its justifications (`summed`, and the same rule in Cypher,
`pangloss_derived.store.SUMMARY_QUERY`): `asserted`, `contested` (asserted, and denied, reported not or forbidden),
`reported`, `prescribed`, `denied` (every justification denied, reported not or forbidden) or `nothing`.

Each part is walked from the **ground** of its head's class (`pangloss_models.spaces`, "The ground"): a statement
directly in a document whose class leaves what it holds neither asserted nor denied is `reported`. The ground also
says each part's **standing**: `"claim"` (what a source says, which another claim can contradict) or `"record"` (what
claims are held against: by default, what an entity holds itself). A relation that starts at an entity has the
standing of that entity's class. A justification is of the record where no part is a claim and one is of the record
(`standing`); a fact, where every justification is (`summed_standing`, and the same in `SUMMARY_QUERY`).

What a wrapper's own `DerivedMeta` says wins over the walk: a blocked one is never reached (the rule's query), a
space that is `transparent` is left out of the path, and one whose `DerivedMeta` says `qualify`, or that the rule
allows, is read as a plain space that neither asserts nor denies, as every space was before the walk.
"""

import dataclasses
import json
from collections.abc import Iterable, Mapping, Sequence
from typing import TYPE_CHECKING, Any

from pangloss_models.context import KIND_OF, REIFIED, SPACE, PathEntry
from pangloss_models.spaces import (
    AGAINST,
    FOR,
    PRESCRIBES,
    Signature,
    SpaceFacts,
    ground_at,
    registered_spaces,
    signature,
)

if TYPE_CHECKING:
    from pangloss_derived.check import CheckedRule

ASSERTED, DENIED, NOTHING = "asserted", "denied", "nothing"
REPORTED, REPORTED_NOT = "reported", "reported_not"
PRESCRIBED, PRESCRIBED_NOT = "prescribed", "prescribed_not"
STATUSES = (
    ASSERTED,
    REPORTED,
    PRESCRIBED,
    DENIED,
    REPORTED_NOT,
    PRESCRIBED_NOT,
    NOTHING,
)
# What a rule derives from, unless it says otherwise
DERIVES = frozenset({ASSERTED, REPORTED, PRESCRIBED})
_LEANING_FOR = (REPORTED, PRESCRIBED)
# (what speaks against it: a denial, a report that it was not so, a forbidding)
AGAINST_IT = (DENIED, REPORTED_NOT, PRESCRIBED_NOT)

CONTESTED = "contested"
# What a fact is, summed up from its justifications
SUMMED = (ASSERTED, CONTESTED, REPORTED, PRESCRIBED, DENIED, NOTHING)

# Whose a justification or a fact is, by the grounds of what it rests on (`pangloss_models.spaces.Signature.standing`)
CLAIM, RECORD = "claim", "record"
STANDINGS = (CLAIM, RECORD)


def ordered(statuses: Iterable[str]) -> list[str]:
    """The distinct statuses, in the order of `STATUSES`"""
    present = set(statuses)
    return [status for status in STATUSES if status in present]


def summed(statuses: Iterable[str]) -> str:
    """What a fact is, from the statuses of its justifications: `asserted` if one is and none speaks against it;
    `contested` if one is and one speaks against it (denied, reported not, forbidden); otherwise `reported` if one is,
    `prescribed` if one is; `denied` if every one speaks against it (in any mix); otherwise `nothing`.
    `pangloss_derived.store.SUMMARY_QUERY` says the same in Cypher"""
    present = set(statuses)
    against = present & set(AGAINST_IT)
    if ASSERTED in present:
        return CONTESTED if against else ASSERTED
    if REPORTED in present:
        return REPORTED
    if PRESCRIBED in present:
        return PRESCRIBED
    if present and present == against:
        return DENIED
    return NOTHING


def status_of(said: Signature) -> str:
    """The status of one part, from what the walk says of its path"""
    if said.veridical == 1:
        return ASSERTED
    if said.veridical == -1:
        return DENIED
    prescribed = said.fit == PRESCRIBES
    if said.lean == FOR:
        return PRESCRIBED if prescribed else REPORTED
    if said.lean == AGAINST:
        return PRESCRIBED_NOT if prescribed else REPORTED_NOT
    return NOTHING


def together(parts: Sequence[str]) -> str:
    """The status of a justification from those of its parts"""
    if NOTHING in parts:
        return NOTHING
    others = [part for part in parts if part != ASSERTED]
    if not others:
        return ASSERTED
    if len(others) == 1:
        return others[0]
    # (two that lean for it, in a report and in an order: prescribed; anything with a denial among several says
    # nothing that a program can use)
    if all(part in _LEANING_FOR for part in others):
        return PRESCRIBED if PRESCRIBED in others else REPORTED
    return NOTHING


def standing(parts: Iterable[str | None]) -> str:
    """The standing of a justification from those of its parts (each `"claim"`, `"record"`, or None for a part with
    no ground: wrappers alone): `"record"` where no part is a claim and at least one is of the record; otherwise
    `"claim"`, a justification none of whose parts has a standing too (nothing makes it the record)"""
    present = set(parts)
    if CLAIM in present or RECORD not in present:
        return CLAIM
    return RECORD


def summed_standing(standings: Iterable[str]) -> str:
    """The standing of a fact, from those of its justifications: `"record"` where every one is of the record (and
    there is one), else `"claim"`. `pangloss_derived.store.SUMMARY_QUERY` says the same in Cypher"""
    present = set(standings)
    return RECORD if present == {RECORD} else CLAIM


def walked_spaces(
    forced: frozenset[str], spaces: Mapping[str, SpaceFacts] | None = None
) -> dict[str, SpaceFacts]:
    """What each space class says of its contents, as a rule's walk reads it: one of `forced` (its `DerivedMeta` says
    `qualify`, or the rule allows it) as a plain space that neither asserts nor denies"""
    known = dict(registered_spaces() if spaces is None else spaces)
    for name in forced:
        if name in known:
            known[name] = SpaceFacts(
                veridical=0,
                fit=known[name]["fit"],
                logical=None,
                degree=known[name]["degree"],
                abstract=known[name].get("abstract", False),
            )
    return known


def stored_path(value: Any) -> list[PathEntry]:
    """A node's path as a query returns it: a list, or (on a database that cannot hold one) its JSON text"""
    if value is None:
        return []
    if isinstance(value, str):
        return json.loads(value)
    return list(value)


def walked_nodes(rule: CheckedRule) -> list[str]:
    """The nodes of a rule whose stored path its query returns (`walks`): those that are not entities, in order"""
    return [name for name, node in rule.nodes.items() if node.kind != "entity"]


@dataclasses.dataclass(frozen=True)
class Part:
    """What one part of a justification is walked over"""

    path: list[PathEntry]
    head: str | None = None
    """Where the path is empty (the node is itself a head): the node's class as stored, whose ground the walk starts
    from"""


def parts_of(rule: CheckedRule, row: Mapping[str, Any]) -> list[Part]:
    """The parts of a row of the rule's query (`walks`: the id, the stored path and the stored class of each of
    `walked_nodes`; `ways`: the type and id of each wrapper of each relation).

    Every node of the rule that is not an entity is a part, by its stored path: the node of a pattern, and one
    nested in it (`Order.Where(content=Gift.Where(...))`), whose path has the spaces of the relation that reaches it;
    one that is itself a head (its path is empty) by its class as stored, whose ground holds. A relation to an
    entity is a part where its wrappers say something by themselves (they are not asserted, read alone): by the path
    of the node it starts at, that node, and its wrappers, the spaces as spaces and the others as statements. It
    then stands for the node it starts at, whose path it has. A relation that starts at an entity (which has no
    path) is its wrappers alone, which have no ground."""
    walks = {
        name: (id, stored_path(path), kind)
        for name, (id, path, kind) in zip(walked_nodes(rule), row["walks"], strict=True)
    }
    parts: list[Part] = []
    # (the nodes a relation that is a part starts at: they are no part by themselves)
    within: set[str] = set()
    for edge, wrappers in zip(rule.edges, row["ways"], strict=True):
        if rule.nodes[edge.target].kind != "entity" or not wrappers:
            continue
        way = [
            PathEntry(
                kind=SPACE if kind in rule.spaces else REIFIED,
                type=kind,
                id=id,
                field="contents",
            )
            for kind, id in wrappers
        ]
        if read(rule, Part(way)) == ASSERTED:
            # (nothing on the way, a space that asserts, a wrapper that is no space: the statement's own path
            # says how the relation holds, `Not[Purchase(buyer=Known[x])]` denied as `Not[Purchase(buyer=x)]` is)
            continue
        if edge.source not in walks:
            parts.append(Part(way))
            continue
        source = rule.nodes[edge.source]
        id, path, kind = walks[edge.source]
        holder = PathEntry(
            kind=KIND_OF.get(getattr(source.model, "__metatype__", ""), "document"),
            # (as stored: where the node is the head, its class's ground is the one the walk starts from)
            type=kind,
            id=id,
            field=edge.field,
        )
        within.add(edge.source)
        parts.append(Part([*path, holder, *way]))
    return [
        Part(path, None if path else kind)
        for name, (_, path, kind) in walks.items()
        if name not in within
    ] + parts


def walk(rule: CheckedRule, part: Part) -> Signature:
    """The walk over one part, from its ground, without the spaces the rule reads as if they were not there"""
    kept = [
        entry
        for entry in part.path
        if not (entry["kind"] == SPACE and entry["type"] in rule.transparent)
    ]
    return signature(kept, rule.spaces, rule.grounds, part.head)


def read(rule: CheckedRule, part: Part) -> str:
    """The status of one part"""
    return status_of(walk(rule, part))


def status_of_row(rule: CheckedRule, row: Mapping[str, Any]) -> str:
    """How the justification a row of the rule's query is holds"""
    return together([read(rule, part) for part in parts_of(rule, row)])


def holds(rule: CheckedRule, row: Mapping[str, Any]) -> tuple[str, str]:
    """How the justification a row of the rule's query is holds, and its standing (`standing`): that of each part,
    by the walk, and of each relation that starts at an entity, by the ground of the entity's class as stored
    (`starts`: the class of the node each relation starts at, where that is an entity), whether or not its wrappers
    make it a part of its own. A rule that follows no relation and has no node but entities (two people born in one
    year) rests on what those entities hold themselves: it has the standing of their classes, as the rule names
    them"""
    said = [walk(rule, part) for part in parts_of(rule, row)]
    starts = [
        class_standing(rule, kind)
        for edge, kind in zip(rule.edges, row["starts"], strict=True)
        if rule.nodes[edge.source].kind == "entity"
    ]
    standings = [s.standing for s in said] + starts
    if not any(standings):
        standings = [
            class_standing(rule, node.model.__name__)
            for node in rule.nodes.values()
            if node.kind == "entity" and node.model.__name__ in rule.grounds
        ]
    return together([status_of(s) for s in said]), standing(standings)


def under_grounds(rule: CheckedRule, row: Mapping[str, Any]) -> list[str]:
    """The head classes of a row's parts whose ground does not plainly assert what they hold (neither asserted nor
    denied, or prescribed: a rumour, a rule book), by name, sorted. What rests on one is qualified by it as by a
    space it passed through: the head's class is among the justification's labels, and a rule that derives a
    document does not make one of it"""
    found: set[str] = set()
    for part in parts_of(rule, row):
        ground = ground_at(part.path, rule.grounds, part.head)
        if ground is not None and (
            ground["veridical"] != 1 or ground["fit"] == PRESCRIBES
        ):
            found.add(part.head or part.path[0]["type"])
    return sorted(found)


def class_standing(rule: CheckedRule, kind: str) -> str | None:
    """The standing of the ground of a head class (refused for a class that has none: `UnknownHeadError`)"""
    ground = ground_at([], rule.grounds, kind)
    return ground["standing"] if ground else None


def derives(rule: CheckedRule, row: Mapping[str, Any], status: str) -> bool:
    """Whether the rule takes a justification of this status. A rule that derives a document takes one that is not
    asserted only where every space it passed through is one the rule allows (a document made from it would plainly
    say what the source did not) and no part is under a head whose ground does not plainly assert (`under_grounds`:
    no rule can allow a ground), unless the rule names its statuses itself (`status=[...]`)"""
    if status not in rule.statuses:
        return False
    if not rule.document or status == ASSERTED or rule.statuses != DERIVES:
        # (a rule that names its statuses has said what its documents are made from: a document of what was
        # denied, by `status=["denied"]`, which no allowed space could give, an allowed one being read as plain)
        return True
    if under_grounds(rule, row):
        return False
    return all(
        entry["type"] in rule.forced
        for part in parts_of(rule, row)
        for entry in part.path
        if entry["kind"] == SPACE
        and entry["type"] not in rule.transparent
        # (a space that asserts what it holds takes nothing from it)
        and rule.spaces[entry["type"]]["veridical"] != 1
    )
