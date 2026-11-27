"""The statements a statement is compared with, by rule (implementation_docs/spaces-and-comparison-plan.md, step 6.3):

    await by_rule(tx, statement, see_unpublished=..., most=...) -> Pairs
    await pairs_of(id, see_unpublished) -> (Told | None, {id: Told}, Pairs)
    await pairs_in(tx, id, see_unpublished, most)      # the same, in an open read transaction

The rule:

- the statement's identifying entities (those of its class's `CompareMeta.identifying`), real entities only, as
  `reading` reads them (no stand-in, nothing below a guess not confirmed, a merged entity as the one kept);
- the stored statements of related classes (`meta.related`: the same, or one above the other; compared, not
  abstract) that name one of them in the same identifying field (by the name it counts as: `picture_made` is
  `made`), other than the statement itself: reason `"rule"`. Two statements of one factoid pair;
- of a statement that is prescribed (`Told.prescribed`), also those of related classes that name one of those it is
  prescribed to (`Prescribed.to`) in any identifying field: reason `"addressee"`. No date is asked of them (an
  undated statement is never left out by "after it": the verdict judges the date);
- that the reader may see (`fragments.visible`, by the head: `see_unpublished` is the caller's), and none any space
  of whose path is `CompareMeta(compared=False)`;
- an entity merged into another is found by both: a statement that names the one absorbed pairs with one that names
  the one kept, and the other way about (the ids absorbed into each found by the records of the merges, `PGMerge`);
- at most `most` (`COMPARE_MOST_PAIRS`: `settings.most_pairs`), those with the most reasons first, then by id;
  `more` where some were cut.

A statement that gives no pairs: an id that is not there, or not of a compared class, or that the reader may not
see, or one inside a space that is `compared=False`. Each is an empty `Pairs`, as the other packages answer an item
the reader may not see with nothing (`None`, which their routes make a 404: `pangloss_vectors.views.visible_item`,
`pangloss_reconcile.stored.stored_plan`); `pairs_of` gives `None` for the statement. A `Told` given by the caller
(not an id) is taken as it is: its visibility is the caller's to judge.

The query is the one measured at 2.7M nodes (the plan, "6.3, the query measured before the brief"): from each
entity by its id (a scalar, so that the index is used), its edges back to a statement directly, and (`UNION`) by an
edge of a held field out of a wrapper, up through the wrappers; the class tested after the match (`t.type IN
$types`, a property, not a label: in the `MATCH`'s `WHERE` Memgraph scans the label); then the head and the rule of
what the reader sees. Two statements more than the reading of the statement: the ids absorbed into its entities,
and this."""

import dataclasses
from collections.abc import Iterable, Mapping
from typing import Any
from uuid import UUID

from pangloss_compare import maths, meta, reading

RULE, ADDRESSEE = "rule", "addressee"


@dataclasses.dataclass(frozen=True)
class Pair:
    """A statement found for another, and why: each reason `(field, entity, "rule" | "addressee")`, the field by the
    name it counts as (the root of a narrowed one), the entity as the one kept"""

    id: str
    by: tuple[tuple[str, str, str], ...]


@dataclasses.dataclass(frozen=True)
class Pairs:
    found: list[Pair] = dataclasses.field(default_factory=list)
    more: bool = False
    """Some were cut (past `most`)"""


# The ids merged into these ids, a level of the chains at a time (`merged_into` set on the one absorbed; the record of
# the merge has the indexed `survivor`)
ABSORBED_QUERY = """
    UNWIND $ids AS kid
    MATCH (m:PGMerge {survivor: kid})
    WITH kid, m.absorbed AS aid
    MATCH (b:PGIndexableNode {id: aid})
    WHERE b.merged_into = kid
    RETURN DISTINCT kid, aid
"""

# (as `pangloss_cypher.validate_write.MERGE_CHAIN_LIMIT`)
CHAIN_LIMIT = 10


async def absorbed_into(tx: Any, ids: Iterable[str]) -> dict[str, set[str]]:
    """For each id, the ids of the entities merged into it, at any depth of the chains of merges (none: an empty
    set)"""
    found: dict[str, set[str]] = {id: set() for id in ids}
    asked = {id: id for id in found}
    for _ in range(CHAIN_LIMIT):
        if not asked:
            break
        result = await tx.run(ABSORBED_QUERY, ids=sorted(asked))
        step = [(str(r["kid"]), str(r["aid"])) async for r in result]
        nxt: dict[str, str] = {}
        for into, absorbed in step:
            root = asked[into]
            if absorbed not in found[root] and absorbed != root:
                found[root].add(absorbed)
                nxt[absorbed] = root
        asked = nxt
    return found


def others_query(fragments: Any, dialect: Any, names: list[str]) -> str:
    """The statements that name the entities of `$found` (each `{entity, kept, root, kind, edges}`: the id to start
    from, the one it counts as, the root field or null, the reason, the edges that count) in one of the edges given,
    of the classes `$types`, other than `$own`, that the reader may see. `names`: the classes of a guess not confirmed
    (`reading.unconfirmed`)"""
    head = fragments.head_of("t", "t_head")
    tail = f"""
        WITH f, t, edge
        WHERE t.type IN $types AND t.id <> $own
        {head.match}
        WITH f, t, edge, {head.name}
        WHERE {fragments.visible("t", head)}
        RETURN t.id AS id, t.type AS type, edge, f.kept AS entity, f.root AS root, f.kind AS kind,
            {dialect.meta_property("t", "path")} AS path
    """
    return f"""
        UNWIND $found AS f
        WITH f, f.entity AS vid
        MATCH (v:PGIndexableNode {{id: vid}})<-[e]-(t)
        WHERE type(e) IN f.edges AND {fragments.forward("e")}{fragments.reference("e")}{reading.unconfirmed("t", names, dialect)}
        WITH f, t, type(e) AS edge
        {tail}
        UNION
        UNWIND $found AS f
        WITH f, f.entity AS vid
        MATCH (v:PGIndexableNode {{id: vid}})<-[e3]-(y)
        WHERE type(e3) IN $held AND {fragments.forward("e3")}{fragments.reference("e3")}
            AND {reading.is_wrapper("y")} AND {reading.not_stand_in("y")}{reading.unconfirmed("y", names, dialect)}
        MATCH held = (y){dialect.through_wrappers("w", backwards=True)}(x)
        WHERE {reading.HELD_ALL_THE_WAY} AND {reading.not_stand_in("x")}
        MATCH (x)<-[e2]-(t)
        WHERE type(e2) IN f.edges AND {fragments.forward("e2")}
        WITH f, t, type(e2) AS edge
        {tail}
    """


def _related(name: str, compared: Mapping[str, Any]) -> list[str]:
    return sorted(other for other in compared if meta.related(name, other))


async def by_rule(
    tx: Any, statement: maths.Told | str | UUID, *, see_unpublished: bool, most: int
) -> Pairs:
    """The statements `statement` is compared with by rule (the module's docstring): a stored statement by its id, or
    one already read (`reading.read`)"""
    from pangloss_core import backend
    from pangloss_models import hooks

    if isinstance(statement, maths.Told):
        told: maths.Told = statement
    else:
        id = str(statement)
        read = (await reading.read(tx, [id], see_unpublished=see_unpublished)).get(id)  # fmt: skip
        if read is None:
            return Pairs()
        told = read
    known = reading.Known()
    rules = meta.compare_meta(told.type) if told.type in known.compared else None  # fmt: skip
    if rules is None:
        return Pairs()
    types = _related(told.type, known.compared)
    identifying = list(dict.fromkeys(rules.identifying))

    # (for each root field, the edges that count as it in each related class that has it among its own)
    def edges_of(root: str) -> list[str]:
        return sorted(
            {
                edge
                for other in types
                for edge, name in known.shape(other).fields.items()
                if name == root and root in known.compared[other].identifying
            }
        )

    asked: list[tuple[str, str | None, str, list[str]]] = []
    for root in identifying:
        edges = edges_of(root)
        for entity in sorted(told.fields.get(root, ())):
            asked.append((entity, root, RULE, edges))
    to = told.prescribed.to if told.prescribed else frozenset()
    if to:
        every = sorted(
            {
                edge
                for other in types
                for edge, name in known.shape(other).fields.items()
                if name in known.compared[other].identifying
            }
        )
        for entity in sorted(to):
            asked.append((entity, None, ADDRESSEE, every))
    if not asked:
        return Pairs()

    absorbed = await absorbed_into(tx, {entity for entity, *_ in asked})
    found = [
        {"entity": start, "kept": entity, "root": root, "kind": kind, "edges": edges}
        for entity, root, kind, edges in asked
        for start in [entity, *sorted(absorbed[entity])]
        if edges
    ]
    current = backend.current()
    query = others_query(
        current.fragments, current.dialect, hooks.unconfirmed_classes()
    )
    result = await tx.run(
        query,
        found=found,
        types=types,
        own=told.id,
        held=reading.held_fields(),
        stand_ins=reading.stand_in_classes(),
        see_unpublished=see_unpublished,
    )
    reasons: dict[str, set[tuple[str, str, str]]] = {}
    left_out: set[str] = set()
    async for r in result:
        id, kind = str(r["id"]), str(r["kind"])
        if id in left_out:
            continue
        if not known.compared_path(reading.stored_path(r["path"])):
            left_out.add(id)
            continue
        # (the field the other names the entity in, by the name it counts as in its own class)
        shape = known.shape(str(r["type"]))
        named = shape.fields.get(str(r["edge"]))
        if named is None or named not in known.compared.get(str(r["type"]), meta.DEFAULT).identifying:  # fmt: skip
            continue
        if kind == RULE and named != r["root"]:
            continue
        reasons.setdefault(id, set()).add((named, str(r["entity"]), kind))
    ordered = sorted(reasons.items(), key=lambda item: (-len(item[1]), item[0]))
    return Pairs(
        [Pair(id, tuple(sorted(by))) for id, by in ordered[:most]],
        more=len(ordered) > most,
    )


async def pairs_in(
    tx: Any, id: str | UUID, see_unpublished: bool, most: int
) -> tuple[maths.Told | None, dict[str, maths.Told], Pairs]:
    """`pairs_of` in an open read transaction (`compare.compare` reads more in the same one)"""
    key = str(id)
    statement = (await reading.read(tx, [key], see_unpublished=see_unpublished)).get(key)  # fmt: skip
    if statement is None:
        return None, {}, Pairs()
    found = await by_rule(tx, statement, see_unpublished=see_unpublished, most=most)  # fmt: skip
    others = await reading.read(tx, [p.id for p in found.found], see_unpublished=see_unpublished)  # fmt: skip
    return statement, others, found


async def pairs_of(
    id: str | UUID, see_unpublished: bool, most: int | None = None
) -> tuple[maths.Told | None, dict[str, maths.Told], Pairs]:
    """In one read transaction: the statement `id` (None where it gives no pairs: `by_rule`), its pairs by rule, and
    the statements paired with it, read (by id). `most`: `COMPARE_MOST_PAIRS` unless given"""
    from pangloss_core import backend

    from pangloss_compare import settings

    most = settings.most_pairs() if most is None else most
    database = backend.current().database()

    @database.read_transaction
    async def run(tx: Any) -> tuple[maths.Told | None, dict[str, maths.Told], Pairs]:
        return await pairs_in(tx, id, see_unpublished, most)

    return await run()
