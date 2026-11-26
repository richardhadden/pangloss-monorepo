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

What a wrapper's own `DerivedMeta` says wins over the walk: a blocked one is never reached (the rule's query), a
space that is `transparent` is left out of the path, and one whose `DerivedMeta` says `qualify`, or that the rule
allows, is read as a plain space that neither asserts nor denies, as every space was before the walk.
"""

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


def parts_of(rule: CheckedRule, row: Mapping[str, Any]) -> list[list[PathEntry]]:
    """The path of each part of a row of the rule's query (`walks`: the id and the stored path of each of
    `walked_nodes`; `ways`: the type and id of each wrapper of each relation).

    Every node of the rule that is not an entity is a part, by its stored path: the node of a pattern, and one
    nested in it (`Order.Where(content=Gift.Where(...))`), whose path has the spaces of the relation that reaches it.
    A relation to an entity is a part where its wrappers say something by themselves (they are not asserted, read
    alone): by the path of the node it starts at, that node, and its wrappers, the spaces as spaces and the others
    as statements. It then stands for the node it starts at, whose path it has. A relation that starts at an entity
    (which has no path) is its wrappers alone."""
    walks = {
        name: (id, stored_path(path))
        for name, (id, path) in zip(walked_nodes(rule), row["walks"], strict=True)
    }
    parts: list[list[PathEntry]] = []
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
        if read(rule, way) == ASSERTED:
            # (nothing on the way, a space that asserts, a wrapper that is no space: the statement's own path
            # says how the relation holds, `Not[Purchase(buyer=Known[x])]` denied as `Not[Purchase(buyer=x)]` is)
            continue
        if edge.source not in walks:
            parts.append(way)
            continue
        source = rule.nodes[edge.source]
        id, path = walks[edge.source]
        holder = PathEntry(
            kind=KIND_OF.get(getattr(source.model, "__metatype__", ""), "document"),
            type=source.model.__name__,
            id=id,
            field=edge.field,
        )
        within.add(edge.source)
        parts.append([*path, holder, *way])
    return [path for name, (_, path) in walks.items() if name not in within] + parts


def read(rule: CheckedRule, path: list[PathEntry]) -> str:
    """The status of one part: the walk over its path, without the spaces the rule reads as if they were not there"""
    kept = [
        entry
        for entry in path
        if not (entry["kind"] == SPACE and entry["type"] in rule.transparent)
    ]
    # (no grounds given yet: every head reads as asserted)
    return status_of(signature(kept, rule.spaces, {}))


def status_of_row(rule: CheckedRule, row: Mapping[str, Any]) -> str:
    """How the justification a row of the rule's query is holds"""
    return together([read(rule, path) for path in parts_of(rule, row)])


def derives(rule: CheckedRule, row: Mapping[str, Any], status: str) -> bool:
    """Whether the rule takes a justification of this status. A rule that derives a document takes one that is not
    asserted only where every space it passed through is one the rule allows (a document made from it would plainly
    say what the source did not), unless the rule names its statuses itself (`status=[...]`)"""
    if status not in rule.statuses:
        return False
    if not rule.document or status == ASSERTED or rule.statuses != DERIVES:
        # (a rule that names its statuses has said what its documents are made from: a document of what was
        # denied, by `status=["denied"]`, which no allowed space could give, an allowed one being read as plain)
        return True
    return all(
        entry["type"] in rule.forced
        for path in parts_of(rule, row)
        for entry in path
        if entry["kind"] == SPACE
        and entry["type"] not in rule.transparent
        # (a space that asserts what it holds takes nothing from it)
        and rule.spaces[entry["type"]]["veridical"] != 1
    )
