"""How a justification holds: its **status**, from the walk (`pangloss_models.spaces`) over what it passed through.

A rule's match rests on the node of each pattern and on each relation it follows to an entity. Each is a **part**
with a path: a node's stored path (`meta.path`); a relation's, where it passes through a semantic space
(`buyer: Person | Not[Person]`), the path of the node it starts at, that node, and the spaces on the way. The walk
says of each part whether it is asserted, denied or neither, and the parts are put together:

- `asserted`: every part is;
- `denied`: one part is denied and the others asserted;
- `reported`, `prescribed`: neither asserted nor denied, leaning for it (a report, a belief; an order, a wish);
- `reported_not`, `prescribed_not`: the same, leaning against (it was reported that he did not; he was forbidden to);
- `nothing`: the source says nothing of it (it is not known that p; there was no service that p was a part of; two
  parts each denied).

A rule derives from the first, the third and the fourth (`DERIVES`); the others are no evidence of the positive, and
give no justification unless the rule asks for them.

What a wrapper's own `DerivedMeta` says wins over the walk: a blocked one is never reached (the rule's query), a
space that is `transparent` is left out of the path, and one whose `DerivedMeta` says `qualify`, or that the rule
allows, is read as a plain space that neither asserts nor denies, as every space was before the walk.
"""

import json
from collections.abc import Mapping, Sequence
from typing import TYPE_CHECKING, Any

from pangloss_models.context import KIND_OF, SPACE, PathEntry
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
    `walked_nodes`; `ways`: the type and id of each wrapper of each relation)"""
    walks = {
        name: (id, stored_path(path))
        for name, (id, path) in zip(walked_nodes(rule), row["walks"], strict=True)
    }
    parts: list[list[PathEntry]] = []
    # (the nodes a relation with spaces starts at: its path has theirs in it, so they are no part by themselves)
    within: set[str] = set()
    for edge, way in zip(rule.edges, row["ways"], strict=True):
        if rule.nodes[edge.target].kind != "entity" or edge.source not in walks:
            # (what a relation reaches that is not an entity has a path of its own, with the relation's spaces)
            continue
        spaces = [(kind, id) for kind, id in way if kind in rule.spaces]
        if not spaces:
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
        parts.append(
            [
                *path,
                holder,
                *(
                    PathEntry(kind=SPACE, type=kind, id=id, field="contents")
                    for kind, id in spaces
                ),
            ]
        )
    return [
        walks[name][1] for name in rule.patterns if name in walks and name not in within
    ] + parts


def read(rule: CheckedRule, path: list[PathEntry]) -> str:
    """The status of one part: the walk over its path, without the spaces the rule reads as if they were not there"""
    kept = [
        entry
        for entry in path
        if not (entry["kind"] == SPACE and entry["type"] in rule.transparent)
    ]
    return status_of(signature(kept, rule.spaces))


def status_of_row(rule: CheckedRule, row: Mapping[str, Any]) -> str:
    """How the justification a row of the rule's query is holds"""
    return together([read(rule, path) for path in parts_of(rule, row)])


def derives(rule: CheckedRule, row: Mapping[str, Any], status: str) -> bool:
    """Whether the rule takes a justification of this status. A rule that derives a document takes one that is not
    asserted only where every space it passed through is one the rule allows: a document made from it would plainly
    say what the source did not"""
    if status not in rule.statuses:
        return False
    if not rule.document or status == ASSERTED:
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
