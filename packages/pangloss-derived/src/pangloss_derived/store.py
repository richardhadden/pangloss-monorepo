"""Facts and their justifications, in the graph; and the work of finding them again for some documents.

    (:PGDerived:SameFamily {key, type, derived_at, context_labels, qualified_only, types, ...literal fields})
        -[:first]->(x:Person)  -[:second]->(y:Person)  -[:family]->(a:Group)
    (:PGJustification {key, rule, rule_hash, types, nodes, context, context_labels, derived_at, generation})
        -[:justifies]->(fact)
        -[:evidence]->(head node)   (one for each head node its patterns are in)

A fact's `key` is a hash of its class and the values of its fields; a justification's, of its rule, its fact and the
node of each pattern. Both are unique, so that a fact found twice is one, and what is found again is not written again.
Nothing is ever written from an entity or into a document's tree, so no update of either touches them.
"""

import dataclasses
import datetime
import hashlib
import json
import logging
from collections.abc import Sequence
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from pangloss_derived.declare import Derived

from pangloss_cypher import fragments
from pangloss_core import Transaction

from pangloss_derived.check import CheckedRule, Seed
from pangloss_derived.compile import compile_rule
from pangloss_derived.registry import DerivedRegistry

logger = logging.getLogger("pangloss.derived")

FACT = "PGDerived"
JUSTIFICATION = "PGJustification"
RULE_STATE = "PGDeriveRule"


def digest(*parts: Any) -> str:
    return hashlib.sha256(
        json.dumps(parts, sort_keys=True, default=str).encode()
    ).hexdigest()[:32]


@dataclasses.dataclass
class FoundFact:
    key: str
    model: str
    values: dict[str, Any]
    """Each field: an id for a relation, a value for a literal"""


@dataclasses.dataclass
class FoundJustification:
    key: str
    fact: str
    rule: str
    rule_hash: str
    types: list[str]
    nodes: list[str]
    heads: list[str]
    context: dict[str, Any]
    context_labels: list[str]


@dataclasses.dataclass
class Found:
    """What some seeded queries found"""

    facts: dict[str, FoundFact] = dataclasses.field(default_factory=dict)
    justifications: dict[str, FoundJustification] = dataclasses.field(
        default_factory=dict
    )
    overflowed: dict[str, str] = dataclasses.field(default_factory=dict)
    """The seeds (node ids) that gave more than the limit, and the rule"""
    rows: int = 0

    def add(self, rule: CheckedRule, row: dict[str, Any]) -> None:
        self.rows += 1
        if rule.exclusive and not one_of_each(rule, row):
            return
        model = rule.model
        values = dict(zip(model._fields, row["fields"], strict=True))
        nodes = list(row["nodes"])
        proof: list[str] = nodes
        if rule.symmetric and not rule.symmetric_body:
            # (both orders of the two ends were matched: the fact has them in order of id, and the two rows that are one
            # proof with the ends swapped are one justification)
            first, second = (
                name for name, (_, var) in rule.head.items() if var in rule.symmetric
            )
            if str(values[first]) > str(values[second]):
                values[first], values[second] = values[second], values[first]
            proof = sorted(nodes)
        fact_key = digest(model.__name__, [values[f] for f in model._fields])
        if fact_key not in self.facts:
            self.facts[fact_key] = FoundFact(fact_key, model.__name__, values)
        key = digest(rule.name, fact_key, proof)
        if key in self.justifications:
            return
        context = context_of(rule, row)
        labels = sorted(
            {label for p in context["patterns"] for label in p["spaces"]}
            | {label for r in context["relations"] for label in r["through"]}
        )
        self.justifications[key] = FoundJustification(
            key=key,
            fact=fact_key,
            rule=rule.name,
            rule_hash=rule.hash,
            types=rule.type_names,
            nodes=nodes,
            heads=sorted(set(row["heads"])),
            context=context,
            context_labels=labels,
        )


def one_of_each(rule: CheckedRule, row: dict[str, Any]) -> bool:
    """Whether the row takes at most one member of each exclusive wrapper (an `Alternative`) it passes through"""
    taken: dict[str, str] = {}
    for types, ids in zip(row["through"], row["paths"], strict=True):
        for index, kind in enumerate(types):
            if kind not in rule.exclusive:
                continue
            wrapper, member = ids[index], ids[index + 1]
            if taken.setdefault(wrapper, member) != member:
                return False
    return True


def context_of(rule: CheckedRule, row: dict[str, Any]) -> dict[str, Any]:
    """What a justification passed through: the semantic spaces of the node of each pattern, and the wrappers of each
    relation that bound a variable, with the properties of its last edge. What the project counts as nothing
    (`transparent`) is left out"""
    keep = [s for s in rule.transparent]
    patterns = [
        {"node": node, "spaces": [s for s in spaces if s not in keep]}
        for node, spaces in zip(row["nodes"], row["spaces"], strict=True)
    ]
    relations = []
    for edge, through, props in zip(
        rule.edges, row["through"], row["props"], strict=True
    ):
        properties = {
            k: v
            for k, v in (props or {}).items()
            if k not in ("pg_position", "reverse")
        }
        relations.append(
            {
                "field": edge.field,
                "through": [t for t in through if t not in keep],
                "properties": properties,
            }
        )
    return {"patterns": patterns, "relations": relations}


# ---------------------------------------------------------------------------
# Reading what to seed, and running the seeded queries
# ---------------------------------------------------------------------------

TREE_QUERY = """
UNWIND $heads AS head_id
MATCH (h:PGIndexableNode {id: head_id})
RETURN head_id, h.id AS id, labels(h) AS labels
UNION ALL
UNWIND $heads AS head_id
MATCH (n:PGIndexableNode {head_node_id: head_id})
RETURN head_id, n.id AS id, labels(n) AS labels
"""


async def nodes_of_heads(
    tx: Transaction, head_ids: list[str]
) -> list[tuple[str, str, list[str]]]:
    """Each node of the head nodes' trees (and the head nodes): its head, id and labels"""
    result = await tx.run(TREE_QUERY, heads=head_ids)
    return [(r["head_id"], r["id"], list(r["labels"])) async for r in result]


def seeds_of(
    nodes: list[tuple[str, str, list[str]]], seeds: list[Seed]
) -> dict[Seed, list[str]]:
    """For each place of a rule: the ids of the nodes that can be at it"""
    found: dict[Seed, list[str]] = {}
    for seed in seeds:
        label = seed.model.__name__
        ids = [node_id for _, node_id, labels in nodes if label in labels]
        if ids:
            found[seed] = ids
    return found


_compiled: dict[tuple[str, str, str], tuple[str, dict[str, Any]]] = {}


def query_of(rule: CheckedRule, node: str) -> tuple[str, dict[str, Any]]:
    key = (rule.name, rule.hash, node)
    if key not in _compiled:
        _compiled[key] = compile_rule(rule, node)
    return _compiled[key]


async def run_seeded(
    tx: Transaction, rule: CheckedRule, node: str, seeds: list[str], found: Found
) -> None:
    """The justifications of the rule with one of the seeds at the place `node`, added to `found`. A seed that gives
    more than the class's `max_per_seed` gives none (it is in `found.overflowed`)"""
    query, params = query_of(rule, node)
    limit = rule.model._meta.max_per_seed
    result = await tx.run(query, {**params, "seeds": seeds})
    per_seed: dict[str, list[dict[str, Any]]] = {}
    async for record in result:
        seed = record["seed"]
        if seed in found.overflowed:
            continue
        rows = per_seed.setdefault(seed, [])
        rows.append(dict(record))
        if len(rows) > limit:
            found.overflowed[seed] = rule.name
            del per_seed[seed]
            logger.warning(
                "Rule %s: node %s gives more than %s justifications (max_per_seed of %s): none of them is written",
                rule.name,
                seed,
                limit,
                rule.model.__name__,
            )
    for rows in per_seed.values():
        for row in rows:
            found.add(rule, row)


async def find_for_heads(
    tx: Transaction, head_ids: list[str]
) -> tuple[Found, set[str]]:
    """Everything the rules derive with a node of one of the heads in it. Also gives the heads whose work was not
    complete (a seed of theirs overflowed): their justifications are left as they are"""
    found = Found()
    nodes = await nodes_of_heads(tx, head_ids)
    rules = DerivedRegistry.checked
    all_seeds = [seed for rule in rules.values() for seed in rule.seeds]
    for seed, ids in seeds_of(nodes, all_seeds).items():
        await run_seeded(tx, rules[seed.rule], seed.node, ids, found)
    head_of = {node_id: head_id for head_id, node_id, _ in nodes}
    incomplete = {head_of[s] for s in found.overflowed if s in head_of}
    return found, incomplete


# ---------------------------------------------------------------------------
# Writing
# ---------------------------------------------------------------------------

EXISTING_QUERY = f"""
UNWIND $keys AS key
MATCH (j:{JUSTIFICATION} {{key: key}})
RETURN j.key AS key
"""


async def existing_justifications(tx: Transaction, keys: list[str]) -> set[str]:
    if not keys:
        return set()
    result = await tx.run(EXISTING_QUERY, keys=keys)
    return {r["key"] async for r in result}


def fact_query(model: type[Derived]) -> str:
    """Writes the facts of one class that are not there (with their edges to the entities)"""
    label = fragments.label(model.__name__)
    literal = [f for f in model._fields.values() if f.kind == "literal"]
    relations = [f for f in model._fields.values() if f.kind == "relation"]
    sets = "".join(
        f", d.{fragments.field_edge(f.name)} = f.values.{fragments.field_edge(f.name)}"
        for f in literal
    )
    edges = "".join(
        f"\nWITH d, f MATCH (e_{i}:PGIndexableNode {{id: f.values.{fragments.field_edge(f.name)}}}) "
        f"MERGE (d)-[:{fragments.field_edge(f.name)}]->(e_{i})"
        for i, f in enumerate(relations)
    )
    return (
        f"UNWIND $facts AS f\n"
        f"MERGE (d:{FACT}:{label} {{key: f.key}})\n"
        f"ON CREATE SET d.type = $type, d.derived_at = $at{sets}"
        f"{edges}"
    )


JUSTIFY_QUERY = f"""
UNWIND $justifications AS j
MATCH (d:{FACT} {{key: j.fact}})
MERGE (n:{JUSTIFICATION} {{key: j.key}})
ON CREATE SET n.rule = j.rule, n.rule_hash = j.rule_hash, n.types = j.types, n.nodes = j.nodes,
              n.context = j.context, n.context_labels = j.context_labels, n.derived_at = $at
SET n.generation = $generation
MERGE (n)-[:justifies]->(d)
WITH n, j
UNWIND j.heads AS head_id
MATCH (h:HeadNode {{id: head_id}})
MERGE (n)-[:evidence]->(h)
"""

TOUCH_QUERY = f"""
UNWIND $keys AS key
MATCH (n:{JUSTIFICATION} {{key: key}})
SET n.generation = $generation
"""

# (from the head node: the justifications of some heads, and then those of them not found again are deleted by key.
# A test of `j.key IN $found` in the first query made Memgraph start from every justification, for each head)
EVIDENCED_QUERY = f"""
UNWIND $heads AS head_id
MATCH (h:HeadNode {{id: head_id}})
WITH h
MATCH (h)<-[:evidence]-(j:{JUSTIFICATION})
RETURN DISTINCT j.key AS key
"""

DELETE_QUERY = f"""
UNWIND $keys AS key
MATCH (j:{JUSTIFICATION} {{key: key}})-[:justifies]->(d)
WITH j, d.key AS fact
DETACH DELETE j
RETURN fact
"""

ORPHANS_QUERY = f"""
UNWIND $facts AS key
MATCH (d:{FACT} {{key: key}})
WHERE NOT (d)<-[:justifies]-()
DETACH DELETE d
"""

SUMMARY_QUERY = f"""
UNWIND $facts AS key
MATCH (d:{FACT} {{key: key}})<-[:justifies]-(j:{JUSTIFICATION})
WITH d, collect(j) AS js
SET d.context_labels = reduce(acc = [], j IN js | acc + [l IN j.context_labels WHERE NOT l IN acc]),
    d.qualified_only = all(j IN js WHERE size(j.context_labels) > 0),
    d.types = reduce(acc = [], j IN js | acc + [t IN j.types WHERE NOT t IN acc]),
    d.justifications = size(js)
"""


async def summarise(tx: Transaction, facts: list[str]) -> None:
    """The facts left with no justification go; the others are summed up again from theirs"""
    await (await tx.run(ORPHANS_QUERY, facts=facts)).consume()
    await (await tx.run(SUMMARY_QUERY, facts=facts)).consume()


# The justifications written in one transaction. A write of the worker is short, so that it seldom meets a save (each
# fact has edges to its entities, and each justification to its head nodes: in Memgraph, an edge changes the nodes at
# both ends, and two transactions that change one node conflict, and one is run again). Measured on 642,000 nodes, a
# batch written as one transaction of 15 s made saves of the same people wait a second, and was itself run again until
# the driver gave up
WRITE_CHUNK = 500


def chunks[T](items: list[T], size: int) -> list[list[T]]:
    return [items[i : i + size] for i in range(0, len(items), size)]


async def write_new(
    tx: Transaction,
    found: Found,
    justifications: list[FoundJustification],
    generation: str,
    at: datetime.datetime,
) -> set[str]:
    """Write the justifications, and their facts if they are not there; sum the facts up again. Gives the facts"""
    needed = {j.fact for j in justifications}
    by_class: dict[str, list[FoundFact]] = {}
    for key in needed:
        fact = found.facts[key]
        by_class.setdefault(fact.model, []).append(fact)
    for name, facts in by_class.items():
        model = DerivedRegistry.classes[name]
        await (
            await tx.run(
                fact_query(model),
                facts=[{"key": f.key, "values": f.values} for f in facts],
                type=name,
                at=at,
            )
        ).consume()
    await (
        await tx.run(
            JUSTIFY_QUERY,
            justifications=[
                {
                    **dataclasses.asdict(j),
                    "context": json.dumps(j.context, sort_keys=True, default=str),
                }
                for j in justifications
            ],
            at=at,
            generation=generation,
        )
    ).consume()
    await summarise(tx, sorted(needed))
    return needed


async def delete_justifications(tx: Transaction, keys: list[str]) -> int:
    """Delete the justifications, and the facts they leave with none; sum the others up again. Gives how many went"""
    result = await tx.run(DELETE_QUERY, keys=keys)
    facts = [r["fact"] async for r in result]
    if facts:
        await summarise(tx, sorted(set(facts)))
    return len(facts)


async def write_found(
    database: Any,
    found: Found,
    *,
    replace_for_heads: Sequence[str] = (),
    generation: str = "",
    chunk: int = WRITE_CHUNK,
) -> dict[str, int]:
    """Write what was found that is not there; delete the justifications with evidence in `replace_for_heads` that were
    not found (and the facts they leave with none); sum each changed fact up again. Gives counts of what was done.

    In short transactions of `database` (see `WRITE_CHUNK`). Each is safe to run again, and a part written before a
    failure is found as there the next time, so what a batch writes need not be one transaction: the pending marks of
    its heads are completed after, by the worker"""
    at = datetime.datetime.now(datetime.UTC)
    keys = list(found.justifications)

    @database.read_transaction
    async def read_existing(tx: Transaction, part: list[str]) -> set[str]:
        return await existing_justifications(tx, part)

    existing: set[str] = set()
    for part in chunks(keys, 5000):
        existing |= await read_existing(part)
    new = [j for k, j in found.justifications.items() if k not in existing]
    changed: set[str] = set()

    @database.write_transaction
    async def write(tx: Transaction, part: list[FoundJustification]) -> set[str]:
        return await write_new(tx, found, part, generation, at)

    for part in chunks(new, chunk):
        changed |= await write(part)

    if generation and existing:

        @database.write_transaction
        async def touch(tx: Transaction, part: list[str]) -> None:
            await (
                await tx.run(TOUCH_QUERY, keys=part, generation=generation)
            ).consume()

        for part in chunks(sorted(existing), 5000):
            await touch(part)

    removed = 0
    if replace_for_heads:

        @database.read_transaction
        async def evidenced(tx: Transaction) -> list[str]:
            result = await tx.run(EVIDENCED_QUERY, heads=list(replace_for_heads))
            return [r["key"] async for r in result]

        stale = [k for k in await evidenced() if k not in found.justifications]

        @database.write_transaction
        async def delete(tx: Transaction, part: list[str]) -> int:
            return await delete_justifications(tx, part)

        for part in chunks(stale, chunk):
            removed += await delete(part)
    return {"new": len(new), "removed": removed, "facts_changed": len(changed)}


# ---------------------------------------------------------------------------
# The state of each rule
# ---------------------------------------------------------------------------

STATES_QUERY = f"""
MATCH (r:{RULE_STATE})
RETURN r.name AS name, r.hash AS hash, r.state AS state, r.built_at AS built_at,
       r.overflows AS overflows, r.last_overflow AS last_overflow
"""


async def rule_states(tx: Transaction) -> dict[str, dict[str, Any]]:
    from pangloss_cypher.values import native_datetime

    result = await tx.run(STATES_QUERY)
    states = {r["name"]: dict(r) async for r in result}
    for state in states.values():
        state["built_at"] = native_datetime(state["built_at"])
    return states


async def set_rule_state(tx: Transaction, name: str, hash: str, state: str) -> None:
    await (
        await tx.run(
            f"MERGE (r:{RULE_STATE} {{name: $name}}) SET r.hash = $hash, r.state = $state, r.built_at = $at",
            name=name,
            hash=hash,
            state=state,
            at=datetime.datetime.now(datetime.UTC),
        )
    ).consume()


async def count_overflow(tx: Transaction, rule: str, seed: str) -> None:
    await (
        await tx.run(
            f"MERGE (r:{RULE_STATE} {{name: $name}}) "
            "SET r.overflows = coalesce(r.overflows, 0) + 1, r.last_overflow = $seed",
            name=rule,
            seed=seed,
        )
    ).consume()


REMOVE_RULE_QUERY = f"""
MATCH (j:{JUSTIFICATION} {{rule: $rule}})
WITH j LIMIT $limit
MATCH (j)-[:justifies]->(d)
WITH DISTINCT j, d.key AS fact
DETACH DELETE j
RETURN fact
"""

OLD_GENERATION_QUERY = f"""
MATCH (j:{JUSTIFICATION} {{rule: $rule}})
WHERE j.generation IS NULL OR j.generation <> $generation
WITH j LIMIT $limit
MATCH (j)-[:justifies]->(d)
WITH DISTINCT j, d.key AS fact
DETACH DELETE j
RETURN fact
"""


async def remove_justifications(
    tx: Transaction, rule: str, generation: str | None, limit: int
) -> int:
    """Delete up to `limit` justifications of the rule (with `generation`: those not of it), and the facts they leave
    with none. Gives how many went"""
    query = REMOVE_RULE_QUERY if generation is None else OLD_GENERATION_QUERY
    result = await tx.run(query, rule=rule, generation=generation, limit=limit)
    facts = [r["fact"] async for r in result]
    if facts:
        await summarise(tx, sorted(set(facts)))
    return len(facts)


async def ids_of_class(tx: Transaction, label: str) -> list[str]:
    result = await tx.run(f"MATCH (n:{fragments.label(label)}) RETURN n.id AS id")
    return [r["id"] async for r in result]


async def count_of_class(tx: Transaction, label: str) -> int:
    result = await tx.run(f"MATCH (n:{fragments.label(label)}) RETURN count(n) AS n")
    record = await result.single()
    return record["n"] if record else 0
