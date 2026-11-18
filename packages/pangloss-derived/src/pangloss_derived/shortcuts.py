"""Shortcut edges: beside the node of each derived edge of a class with `Meta(shortcut=True)`, an edge of the name of
the class from its subject to its object. See implementation_docs/derived.md ("Shortcut edges").

    (a:Person)-[:SameGroup {key, derived: true}]->(b:Person)
    (:PGDerived:SameGroup {key, pg_shortcut: true})-[:first]->(a)  -[:second]->(b)  -[:group]->(g)

They are for paths and graph algorithms written in Cypher, where a hop through the node of each edge costs a hop and
an edge of a known name can be repeated (`-[:SameGroup*1..3]-`). Nothing of Pangloss reads them: what is derived about
an entity is read from the nodes, because who sees an edge is worked out from its justifications. A shortcut says
neither who sees it, nor what its derivation passed through (`plain`), nor what qualifies it: its `key` is the key of
its node (`MATCH (d:PGDerived {key: e.key})`), which has all of it.

**There is a shortcut exactly where there is a node** whose class says so. The worker writes it in the transaction
that writes the node (`store.fact_query`) and deletes it in the one that deletes the node (`store.orphans_query`), and
the node records that it has one (`pg_shortcut`). When the worker starts, `sync` writes those of a class that has
begun to say `shortcut=True` and deletes those of a class that has stopped. So an entity that was deleted or merged
into another keeps its shortcuts until the worker has taken away what was derived of it, as it keeps the nodes.

The core leaves them out of every query that takes any edge between two items (`pangloss_cypher.fragments.model_edge`,
on the property `derived`): they are in no incoming list, make no entity "referred to", and are moved by no merge.
"""

import logging
from typing import TYPE_CHECKING, Any

from pangloss_core import Transaction
from pangloss_cypher import fragments

from pangloss_derived.registry import DerivedRegistry

if TYPE_CHECKING:
    from pangloss_derived.declare import DerivedEdge

logger = logging.getLogger("pangloss.derived")

FACT = "PGDerived"
# On the node of a derived edge: it has a shortcut beside it
MARK = "pg_shortcut"
# On the shortcut: what the core leaves out by
DERIVED = fragments.DERIVED_EDGE
# The nodes looked at in one transaction of `sync`
CHUNK = 2000


def classes() -> dict[str, "type[DerivedEdge]"]:
    """The classes whose edges have a shortcut"""
    return {
        name: model
        for name, model in DerivedRegistry.concrete_classes().items()
        if model._meta.shortcut
    }


def write_clause(model: "type[DerivedEdge]", node: str, key: str) -> str:
    """What follows the node `node` of an edge of the class (with its edges to its ends written) to write its
    shortcut, if it is not there. `key`: the expression of its key"""
    name = fragments.label(model.__name__)
    subject, object_ = (fragments.field_edge(end) for end in model._ends)
    return (
        f"MATCH (pg_s)<-[:{subject}]-({node})-[:{object_}]->(pg_o)\n"
        f"MERGE (pg_s)-[pg_x:{name} {{key: {key}}}]->(pg_o)\n"
        f"ON CREATE SET pg_x.{DERIVED} = true\n"
        f"SET {node}.{MARK} = true"
    )


# The shortcut of a node that says it has one: from the end that is its subject, the edge of its key
def delete_clause(node: str, found: str) -> str:
    """What follows the node `node` of an edge to gather its shortcut (if it says it has one) as the list `found`,
    keeping `node`"""
    return (
        f"OPTIONAL MATCH ({node})-[pg_end]->(pg_s)\n"
        f"WHERE {node}.{MARK} AND type(pg_end) = {node}.pg_subject\n"
        f"OPTIONAL MATCH (pg_s)-[pg_x]->()\n"
        f"WHERE pg_x.{DERIVED} AND type(pg_x) = {node}.type AND pg_x.key = {node}.key\n"
        f"WITH {node}, collect(DISTINCT pg_x) AS {found}"
    )


def unmarked_query(model: "type[DerivedEdge]") -> str:
    return (
        f"MATCH (d:{FACT}:{fragments.label(model.__name__)})\n"
        f"WHERE d.{MARK} IS NULL\n"
        f"WITH d LIMIT $limit\n"
        f"SET d.{MARK} = true\n"
        f"RETURN collect(d.key) AS keys"
    )


def write_query(model: "type[DerivedEdge]") -> str:
    return f"UNWIND $keys AS key\nMATCH (d:{FACT} {{key: key}})\n" + write_clause(
        model, "d", "d.key"
    )


def marked_query(label: str | None) -> str:
    """Up to `$limit` nodes that say they have a shortcut and are to have none: of one class, or (`None`) of any
    class but `$keep`. Gives their keys, and takes the mark off"""
    which = f":{fragments.label(label)}" if label else ""
    return (
        f"MATCH (d:{FACT}{which})\n"
        f"WHERE d.{MARK}" + ("" if label else " AND NOT d.type IN $keep") + "\n"
        f"WITH d LIMIT $limit\n"
        f"{delete_clause('d', 'gone')}\n"
        f"FOREACH (x IN gone | DELETE x)\n"
        f"REMOVE d.{MARK}\n"
        f"RETURN count(d) AS done"
    )


async def sync(database: Any, chunk: int = CHUNK) -> dict[str, dict[str, int]]:
    """Make the shortcuts in the graph those the classes ask for: write those of the nodes of a class that says
    `shortcut=True` and have none (the class has begun to say so), and delete those of the nodes of a class that does
    not say so (it has stopped). Gives, for each class something was done for, how many were `written` or `deleted`.
    In short transactions, each of which can be run again.

    Costs a look at the nodes of the derived edges (which `PGDerived` and the label of the class find), and nothing
    else when there is nothing to do"""
    done: dict[str, dict[str, int]] = {}
    wanted = classes()

    for name, model in wanted.items():

        @database.write_transaction
        async def write(tx: Transaction, model: Any = model) -> int:
            result = await tx.run(unmarked_query(model), limit=chunk)
            record = await result.single()
            keys = list(record["keys"]) if record else []
            if keys:
                await (await tx.run(write_query(model), keys=keys)).consume()
            return len(keys)

        written = 0
        while True:
            count = await write()
            written += count
            if count < chunk:
                break
        if written:
            done.setdefault(name, {})["written"] = written

    @database.write_transaction
    async def delete(tx: Transaction) -> int:
        result = await tx.run(marked_query(None), limit=chunk, keep=sorted(wanted))
        record = await result.single()
        return record["done"] if record else 0

    deleted = 0
    while True:
        count = await delete()
        deleted += count
        if count < chunk:
            break
    if deleted:
        done["(classes without shortcut)"] = {"deleted": deleted}
    for name, counts in done.items():
        logger.info("Shortcut edges, %s: %s", name, counts)
    return done


async def forget(database: Any, name: str, chunk: int = CHUNK) -> int:
    """Delete the shortcuts of the nodes of one class (they are written again by `sync`, if the class asks for
    them). Gives how many nodes had one"""

    @database.write_transaction
    async def delete(tx: Transaction) -> int:
        result = await tx.run(marked_query(name), limit=chunk)
        record = await result.single()
        return record["done"] if record else 0

    deleted = 0
    while True:
        count = await delete()
        deleted += count
        if count < chunk:
            break
    return deleted


def count_query(model: "type[DerivedEdge]") -> str:
    name = fragments.label(model.__name__)
    subject = fragments.field_edge(model._ends[0])
    return (
        f"MATCH (d:{FACT}:{name})\n"
        f"OPTIONAL MATCH (d)-[:{subject}]->(s)\n"
        f"OPTIONAL MATCH (s)-[x:{name}]->()\n"
        f"WHERE x.{DERIVED} AND x.key = d.key\n"
        f"WITH d, count(x) AS found\n"
        f"RETURN count(d) AS edges, sum(CASE WHEN found > 0 THEN 1 ELSE 0 END) AS shortcuts, "
        f"sum(CASE WHEN found > 1 THEN 1 ELSE 0 END) AS doubled, "
        f"sum(CASE WHEN coalesce(d.{MARK}, false) THEN 1 ELSE 0 END) AS marked"
    )


async def counts(tx: Transaction) -> dict[str, dict[str, int]]:
    """For each class that asks for shortcuts: how many derived `edges` it has, how many of them have their
    `shortcut` (all of them, when the worker is up to date), how many have more than one (`doubled`: none, ever), and
    how many are `marked` as having one"""
    found: dict[str, dict[str, int]] = {}
    for name, model in classes().items():
        record = await (await tx.run(count_query(model))).single()
        found[name] = (
            {k: record[k] for k in ("edges", "shortcuts", "doubled", "marked")}
            if record
            else {"edges": 0, "shortcuts": 0, "doubled": 0, "marked": 0}
        )
    return found
