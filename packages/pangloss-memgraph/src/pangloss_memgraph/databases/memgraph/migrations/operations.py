"""What each change does to a Memgraph database.

`apply_change(tx, change, state)` makes a change to the data, in the transaction `tx`.
`state` is the snapshot of the models *before* the change (see
`pangloss_models.meta_kit.migrations.state`): it says the labels of a model and how a field is stored,
so nothing here needs the classes of the models, which may have changed since.

Changes are written for a model and a field, and select by label (`MATCH (n:Statement)`), so
that one change is made wherever the model is used: subclasses carry the label of their
parents, and a nested model is found without knowing what it is nested in.

Indexes and constraints are changed outside of a transaction (`run_ddl`), as Memgraph requires;
enums are stored as the values of their members, so changing one is a change to data like any other.
See `docs/migrations.md` 5.6.
"""

import copy
import dataclasses
import inspect
import re
import uuid
from collections.abc import Awaitable, Callable
from contextvars import ContextVar
from typing import Any

import neo4j
from pangloss_models.context import propagate_context
from pangloss_models.exceptions import (
    PanglossMigrationAnswerNeeded,
    PanglossMigrationError,
    PanglossMigrationNotSupported,
)
from pangloss_models.meta_kit.migrations import changes as c
from pangloss_models.meta_kit.migrations.state import rename_field
from pangloss_models.meta_kit.migrations.state import rename_model as state_after_rename

from pangloss_memgraph.databases.memgraph.database import Database, Transaction
from pangloss_memgraph.databases.memgraph.initialise_database import run_statement
from pangloss_memgraph.databases.memgraph.migrations.conversion import (
    convert_expression,
)

IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

DIRECT_KINDS = {"document", "entity"}
SCALAR_PROPERTY_KINDS = {"literal", "list", "annotatedValue", "typeVar"}


# ---------------------------------------------------------------------------
# Looking things up, and writing Cypher
# ---------------------------------------------------------------------------


def ident(name: str) -> str:
    """A label, edge type or property name, as it can be put into a query (they cannot be
    parameters). Only identifiers: the names come from class and field names."""
    if not IDENTIFIER.match(name):
        raise PanglossMigrationError(f"'{name}' cannot be used as a name in a query")
    return f"`{name}`"


def model_of(state: dict, name: str) -> dict:
    try:
        return state["models"][name]
    except KeyError:
        raise PanglossMigrationError(
            f"There is no model {name} at this point"
        ) from None


def field_of(state: dict, model: str, name: str) -> dict:
    for entry in model_of(state, model)["fields"]:
        if entry["name"] == name:
            return entry
    raise PanglossMigrationError(f"There is no field {model}.{name} at this point")


def edge_pairs(field: dict) -> list[tuple[str, str]]:
    """The edge pairs written for a field: its own, then one for each parent field it narrows"""
    pairs = field.get("storage", {}).get("edges", [])
    return [(forward, reverse or f"{forward}_reverse") for forward, reverse in pairs]


def owns_nodes(field: dict) -> bool:
    """Whether a relation is to nodes that belong to the node it is on (anything but an entity)"""
    if field["kind"] == "embedded":
        return True
    return any(option["kind"] != "entity" for option in field.get("options", []))


# When a dry run is counting, what each statement did is added here
COUNTERS: ContextVar[dict[str, int] | None] = ContextVar(
    "migration_counters", default=None
)
COUNTED = [
    "nodes_created",
    "nodes_deleted",
    "relationships_created",
    "relationships_deleted",
    "properties_set",
    "labels_added",
    "labels_removed",
]


async def run(tx: Transaction, query: str, /, **params: Any) -> list[dict[str, Any]]:
    return await run_with(tx, query, params)


async def run_with(
    tx: Transaction, query: str, params: dict[str, Any]
) -> list[dict[str, Any]]:
    """`run`, with the parameters as a dict (a name may be `query`, which the driver's `run` takes)"""
    try:
        result = await tx.run(query, params)  # ty: ignore[invalid-argument-type]
        rows = await result.data()
        counters = COUNTERS.get()
        if counters is not None:
            summary = await result.consume()
            for name in COUNTED:
                counters[name] = counters.get(name, 0) + getattr(
                    summary.counters, name, 0
                )
        return rows
    except neo4j.exceptions.Neo4jError as error:
        raise PanglossMigrationError(
            f"{error.message}\nin: {' '.join(query.split())}"
        ) from error


@dataclasses.dataclass(frozen=True)
class Window:
    """A batch of the nodes an operation is for: those with an id after `after`, in the order of
    their ids, `size` of them. (`first` is true for the first batch: what is checked once is checked
    then.)"""

    after: str
    size: int

    @property
    def first(self) -> bool:
        return self.after == ""

    @property
    def params(self) -> dict[str, Any]:
        return {"_after": self.after, "_size": self.size}


def select_nodes(label: str, where: str, window: Window | None) -> str:
    """The start of a statement for the nodes of a model that match: all of them, or a window"""
    condition = f"({where})" if where else "true"
    if window is None:
        return f"MATCH (n:{label}) WHERE {condition}"
    return (
        f"MATCH (n:{label}) WHERE n.id > $_after AND {condition} "
        f"WITH n ORDER BY n.id LIMIT $_size"
    )


async def run_on_nodes(
    tx: Transaction, window: Window | None, statement: str, **params: Any
) -> list[str] | None:
    """Run a statement that starts with `select_nodes`: with a window, the ids of the nodes it was
    for are returned (the last is where the next batch begins)"""
    if window is None:
        await run(tx, statement, **params)
        return None
    rows = await run(
        tx, f"{statement} RETURN n.id AS id", **{**params, **window.params}
    )
    return [row["id"] for row in rows]


def needs(change: c.Change, value: Any, what: str) -> None:
    if value is None:
        raise PanglossMigrationAnswerNeeded(f"{change.describe()}: {what}")


def literal_expression(
    value: Any,
    descriptor: dict,
    params: dict[str, Any],
    name: str,
    enums: dict[str, dict],
) -> str:
    """The expression for a value of a type, with what it needs in `params`"""
    kind = descriptor["type"]
    if kind == "enum":
        # (an enum is stored as the value of its member)
        members = enums.get(descriptor["enum"], {}).get("members", [])
        member = next(
            (m for m in members if m["name"] == value or m["value"] == value), None
        )
        if member is None:
            raise PanglossMigrationError(
                f"{value!r} is not a member of the enum {descriptor['enum']}"
            )
        params[name] = member["value"]
        return f"${name}"
    if kind == "list":
        items = [
            literal_expression(item, descriptor["item"], params, f"{name}_{i}", enums)
            for i, item in enumerate(value)
        ]
        return "[" + ", ".join(items) + "]"
    if kind == "decimal":
        params[name] = str(value)
    elif kind == "date" and isinstance(value, str):
        import datetime

        params[name] = datetime.date.fromisoformat(value)
    else:
        params[name] = value
    return f"${name}"


def field_descriptor(field: dict) -> dict:
    """The type of a literal or list field, as a descriptor"""
    if field["kind"] == "list":
        return {"type": "list", "item": field["item"]}
    if field["kind"] == "literal":
        return field["type"]
    raise PanglossMigrationNotSupported(f"A {field['kind']} field has no simple type")


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


async def rename_model(
    tx: Transaction, change: c.RenameModel, state: dict, limit: int | None = None
) -> int:
    """Relabel the nodes, change the `type` they and what they hold have, and work out again the
    context of the documents whose nodes have the name in it (the semantic spaces they are in, and
    the documents that are a part of their context). With a `limit` this is done `limit` at a time:
    a call does the first of these steps that has anything left to do, and says that there may be
    more (it returns `limit`) until all of it is done."""
    old, new = ident(change.old), ident(change.new)
    window = f"WITH n LIMIT {int(limit)} " if limit else ""
    steps = [
        f"MATCH (n:{old}) {window}REMOVE n:{old} SET n:{new} RETURN count(n) AS done",
        f"MATCH (n:{new}) WHERE n.type = $old {window}SET n.type = $new RETURN count(n) AS done",
        f"MATCH (n) WHERE n.head_node_type = $old {window}SET n.head_node_type = $new RETURN count(n) AS done",
    ]
    for step in steps:
        rows = await run(tx, step, old=change.old, new=change.new)
        done = rows[0]["done"] if rows else 0
        if limit and done:
            return limit  # (there may be more of this, or the steps after it)
    # the context of what a renamed document holds has its name in it: the documents with a node
    # that has it are worked out again, and then none has it (so a next call finds the next)
    head_window = (
        f"WITH DISTINCT coalesce(n.head_node_id, n.id) AS head LIMIT {int(limit)} "
        if limit
        else "WITH DISTINCT coalesce(n.head_node_id, n.id) AS head "
    )
    mentions = """
        MATCH (n) WHERE n.meta IS NOT NULL AND (
            $old IN coalesce(n.meta.semantic_spaces, [])
            OR any(label IN coalesce(n.meta.context_labels, []) WHERE label.type = $old
                   OR any(entry IN coalesce(label.contents, []) WHERE entry.type = $old)))
    """
    heads = await run(tx, f"{mentions}{head_window}RETURN head", old=change.old)
    if heads:
        await recompute_contexts(
            tx,
            [row["head"] for row in heads],
            state_after_rename(state, change.old, change.new),
        )
        again = await run(
            tx,
            f"{mentions} WITH DISTINCT coalesce(n.head_node_id, n.id) AS head "
            "WHERE head IN $heads RETURN count(head) AS left",
            old=change.old,
            heads=[row["head"] for row in heads],
        )
        if again and again[0]["left"]:
            # (what is done is meant to be gone: if it is not, going on would never end)
            raise PanglossMigrationError(
                f"The context of {again[0]['left']} documents still has {change.old} in it after it was "
                "worked out again"
            )
        return limit or 0
    return 0


async def delete_model(
    tx: Transaction, change: c.DeleteModel, state: dict, limit: int | None = None
) -> int:
    """Delete the nodes of a model, with their records and what they hold. With a `limit`, `limit`
    head nodes at a time and then the rest of its nodes (a nested document) `limit` at a time; a
    call returns `limit` while there may be more."""
    model = ident(change.model)
    if limit is None:
        # what records it: creation, updates, deletions; the URLs of an entity
        await run(
            tx,
            f"""
            MATCH (h:{model})<-[e]-(record)
            WHERE type(e) IN ['is_creation_of', 'is_update_of', 'is_deletion_of', 'is_undeletion_of']
            DETACH DELETE record
            """,
        )
        await run(tx, f"MATCH (h:{model})-[:has_url]->(u:PGUrl) DETACH DELETE u")
        # what it owns (the nodes of its document), then it
        await run(
            tx,
            f"MATCH (h:{model}:HeadNode) MATCH (x) WHERE x.head_node_id = h.id DETACH DELETE x",
        )
        await run(tx, f"MATCH (n:{model}) DETACH DELETE n")
        return 0
    rows = await run(
        tx,
        f"MATCH (h:{model}:HeadNode) WITH h LIMIT {int(limit)} RETURN collect(h.id) AS ids",
    )
    ids = rows[0]["ids"] if rows else []
    if ids:
        await run(
            tx,
            f"""
            MATCH (h:{model})<-[e]-(record)
            WHERE h.id IN $ids AND type(e) IN ['is_creation_of', 'is_update_of', 'is_deletion_of', 'is_undeletion_of']
            DETACH DELETE record
            """,
            ids=ids,
        )
        await run(
            tx,
            f"MATCH (h:{model})-[:has_url]->(u:PGUrl) WHERE h.id IN $ids DETACH DELETE u",
            ids=ids,
        )
        await run(tx, "MATCH (x) WHERE x.head_node_id IN $ids DETACH DELETE x", ids=ids)
        await run(tx, f"MATCH (n:{model}) WHERE n.id IN $ids DETACH DELETE n", ids=ids)
        return limit  # (more heads, or the nodes that are not heads, may be left)
    rows = await run(
        tx,
        f"MATCH (n:{model}) WITH n LIMIT {int(limit)} DETACH DELETE n RETURN count(n) AS done",
    )
    return rows[0]["done"] if rows else 0


async def alter_model_labels(
    tx: Transaction,
    change: c.AlterModelLabels,
    state: dict,
    window: Window | None = None,
) -> list[str] | None:
    model = ident(change.model)
    changes = ""
    if change.added:
        changes += " SET n" + "".join(":" + ident(label) for label in change.added)
    if change.removed:
        changes += " REMOVE n" + "".join(":" + ident(label) for label in change.removed)
    return await run_on_nodes(tx, window, select_nodes(model, "", window) + changes)


# ---------------------------------------------------------------------------
# Literal fields
# ---------------------------------------------------------------------------


async def add_field(
    tx: Transaction, change: c.AddField, state: dict, window: Window | None = None
) -> list[str] | None:
    field = change.definition
    if change.from_narrowing:
        return None  # (written already, by the field that narrowed it)
    if field["kind"] == "embedded":
        await add_embedded(tx, change, state)
        return None if window is None else []
    if field["kind"] not in SCALAR_PROPERTY_KINDS or not change.needs_value:
        return (
            None if window is None else []
        )  # (an absent property is none; a relation is empty)
    if field["kind"] == "list" and change.default is None:
        change = dataclasses.replace(
            change, default=[]
        )  # (a list that is needed starts empty)
    needs(change, change.default, "a value for the nodes that exist (`default`)")
    params: dict[str, Any] = {}
    if field["kind"] in ("literal", "list"):
        expression = literal_expression(
            change.default, field_descriptor(field), params, "default", state["enums"]
        )
    else:
        params["default"] = change.default
        expression = "$default"
    prop = f"n.{ident(field['name'])}"
    return await run_on_nodes(
        tx,
        window,
        select_nodes(ident(change.model), f"{prop} IS NULL", window)
        + f" SET {prop} = {expression}",
        **params,
    )


async def add_embedded(
    tx: Transaction, change: c.AddField, state: dict, limit: int | None = None
) -> int:
    """A field that is an embedded object, new: each node that exists is given one, with the values
    that were answered (`default`: a value for each field the embedded object requires). Done as
    for literals that become an embedded object, with no literals to move."""
    field = change.definition
    types = field.get("types") or ([field["model"]] if field.get("model") else [])
    if len(types) != 1:
        raise PanglossMigrationNotSupported(
            f"{change.describe()}: it can be any of {', '.join(types) or 'several'}, and which one the "
            "nodes that exist are given is not known: write it by hand"
        )
    synthetic = c.LiteralsToEmbedded(
        model=change.model,
        name=change.name,
        embedded_model=field["model"],
        fields=[],
        definition=field,
        defaults=change.default if isinstance(change.default, dict) else None,
        embedded_type=types[0],
    )
    return await literals_to_embedded(tx, synthetic, state, limit)


async def delete_relation(
    tx: Transaction,
    model: str,
    field: dict,
    only_pairs: list[tuple[str, str]] | None = None,
) -> None:
    """Delete the edges of a relation (and what the node owns through it)"""
    pairs = only_pairs if only_pairs is not None else edge_pairs(field)
    forward = [f for f, _ in pairs]
    reverse = [r for _, r in pairs]
    label = ident(model)
    if owns_nodes(field) and only_pairs is None:
        # the nodes below, without entering entities (which belong to no document)
        await run(
            tx,
            f"""
            MATCH (n:{label})-[e]->(t)
            WHERE type(e) IN $forward AND NOT t:Entity AND NOT coalesce(e.reverse, false)
            OPTIONAL MATCH (t)-[*BFS (e2, n2 | NOT n2:Entity AND NOT coalesce(e2.reverse, false))]->(d)
            WITH collect(DISTINCT t) + collect(DISTINCT d) AS owned
            UNWIND [x IN owned WHERE x IS NOT NULL] AS o
            DETACH DELETE o
            """,
            forward=forward,
        )
    await run(
        tx,
        f"MATCH (n:{label})-[e]->() WHERE type(e) IN $forward AND NOT coalesce(e.reverse, false) DELETE e",
        forward=forward,
    )
    await run(
        tx,
        f"MATCH ()-[e]->(n:{label}) WHERE type(e) IN $reverse AND coalesce(e.reverse, false) DELETE e",
        reverse=reverse,
    )


async def delete_relation_batch(
    tx: Transaction, model: str, field: dict, limit: int
) -> int:
    """`delete_relation`, `limit` at a time: the nodes that `limit` of the relations own (with what
    they own), then `limit` of the forward edges, then `limit` of the reverse. What is done is no
    longer there for the next call to find. Returns the most that any of the three did."""
    pairs = edge_pairs(field)
    forward = [f for f, _ in pairs]
    reverse = [r for _, r in pairs]
    label = ident(model)
    done = 0
    if owns_nodes(field):
        rows = await run(
            tx,
            f"""
            MATCH (n:{label})-[e]->(t)
            WHERE type(e) IN $forward AND NOT t:Entity AND NOT coalesce(e.reverse, false)
            WITH t LIMIT {int(limit)}
            OPTIONAL MATCH (t)-[*BFS (e2, n2 | NOT n2:Entity AND NOT coalesce(e2.reverse, false))]->(d)
            WITH collect(DISTINCT t) AS tops, collect(DISTINCT d) AS below
            WITH size(tops) AS handled, tops + [x IN below WHERE x IS NOT NULL] AS owned
            UNWIND owned AS o
            DETACH DELETE o
            RETURN max(handled) AS handled
            """,
            forward=forward,
        )
        done = max(done, rows[0]["handled"] or 0 if rows else 0)
        if done >= limit:
            return done  # (more may be owned: the edges are for a later call)
    rows = await run(
        tx,
        f"MATCH (n:{label})-[e]->() WHERE type(e) IN $forward AND NOT coalesce(e.reverse, false) "
        f"WITH e LIMIT {int(limit)} DELETE e RETURN count(e) AS n",
        forward=forward,
    )
    done = max(done, rows[0]["n"] if rows else 0)
    rows = await run(
        tx,
        f"MATCH ()-[e]->(n:{label}) WHERE type(e) IN $reverse AND coalesce(e.reverse, false) "
        f"WITH e LIMIT {int(limit)} DELETE e RETURN count(e) AS n",
        reverse=reverse,
    )
    return max(done, rows[0]["n"] if rows else 0)


async def apply_edges(
    tx: Transaction, change: c.Change, state: dict, limit: int
) -> int:
    """One batch of a change made `limit` at a time (`batch_kind` calls them `"edges"`): how many it
    did, which is `limit` if there may be more. What is done is no longer there to do, so a call
    again finds the next."""
    match change:
        case c.RenameField():
            return await rename_relation_edges(tx, change, state, limit)
        case c.AddField():
            return await add_embedded(tx, change, state, limit)
        case c.RemoveField():
            return await delete_relation_batch(
                tx, change.model, field_of(state, change.model, change.name), limit
            )
        case c.AlterReverseName():
            return await alter_reverse_name(tx, change, state, limit)
        case c.UnwrapRelation():
            return await unwrap_relation(tx, change, state, limit)
        case c.WrapRelation():
            return await wrap_relation(tx, change, state, limit)
        case c.ChangeWrapper():
            return await change_wrapper(tx, change, state, limit)
        case c.LiteralsToEmbedded():
            return await literals_to_embedded(tx, change, state, limit)
        case c.EmbeddedToLiterals():
            return await embedded_to_literals(tx, change, state, limit)
        case c.RenameModel():
            return await rename_model(tx, change, state, limit)
        case c.DeleteModel():
            return await delete_model(tx, change, state, limit)
        case c.AlterEnumMemberValue():
            return await alter_enum_member_value(tx, change, state, limit)
        case c.RemoveEnumMember():
            return await remove_enum_member(tx, change, state, limit)
        case c.RecomputeFulfils():
            return await recompute_fulfils(tx, change, state, limit)
        case c.AlterCardinality():
            return await alter_cardinality(tx, change, state, limit)
        case c.AlterRelationTarget():
            return await alter_relation_target(tx, change, state, limit)
        case c.AlterParentFields():
            return await alter_parent_fields(tx, change, state, limit)
        case c.AlterEdgeModel():
            return await alter_edge_model(tx, change, state, limit)
    raise PanglossMigrationError(f"{type(change).__name__} cannot be made in batches")


async def remove_field(
    tx: Transaction, change: c.RemoveField, state: dict, window: Window | None = None
) -> list[str] | None:
    if change.absorbed:
        return None  # (its edges are written by the field that narrows it now)
    field = field_of(state, change.model, change.name)
    if field["kind"] in SCALAR_PROPERTY_KINDS:
        prop = f"n.{ident(change.name)}"
        return await run_on_nodes(
            tx,
            window,
            select_nodes(ident(change.model), f"{prop} IS NOT NULL", window)
            + f" REMOVE {prop}",
        )
    await delete_relation(tx, change.model, field)
    return None


async def rename_edge_type(
    tx: Transaction,
    model: str,
    old: str,
    new: str,
    reverse: bool,
    limit: int | None = None,
) -> int:
    """Edge types are replaced, not changed: a new edge with the properties of the old. With a
    `limit`, that many at most (those done no longer have the old type, so a next call finds the
    next). Returns how many were renamed."""
    label = ident(model)
    if not reverse:
        pattern = f"(a:{label})-[e:{ident(old)}]->(b)"
        guard = "WHERE NOT coalesce(e.reverse, false)"
    else:
        pattern = f"(a)-[e:{ident(old)}]->(b:{label})"
        guard = "WHERE coalesce(e.reverse, false)"
    window = f"WITH a, e, b LIMIT {int(limit)} " if limit else ""
    rows = await run(
        tx,
        f"MATCH {pattern} {guard} {window}"
        f"CREATE (a)-[n:{ident(new)}]->(b) SET n = properties(e) DELETE e RETURN count(n) AS renamed",
    )
    return rows[0]["renamed"] if rows else 0


async def rename_relation_edges(
    tx: Transaction, change: c.RenameField, state: dict, limit: int | None = None
) -> int:
    """The edges of a renamed relation (forward and reverse); with a `limit`, that many of each at
    most. Returns the most of either that were renamed (the same as `limit` if there may be more)."""
    field = field_of(state, change.model, change.old)
    renamed = field_of(
        rename_field(state, change.model, change.old, change.new),
        change.model,
        change.new,
    )
    (old_forward, old_reverse), (new_forward, new_reverse) = (
        edge_pairs(field)[0],
        edge_pairs(renamed)[0],
    )
    done = 0
    if old_forward != new_forward:
        done = max(
            done,
            await rename_edge_type(
                tx, change.model, old_forward, new_forward, False, limit
            ),
        )
    if old_reverse != new_reverse:
        done = max(
            done,
            await rename_edge_type(
                tx, change.model, old_reverse, new_reverse, True, limit
            ),
        )
    return done


async def rename_field_data(
    tx: Transaction, change: c.RenameField, state: dict, window: Window | None = None
) -> list[str] | None:
    field = field_of(state, change.model, change.old)
    if field["kind"] in SCALAR_PROPERTY_KINDS:
        old, new = f"n.{ident(change.old)}", f"n.{ident(change.new)}"
        return await run_on_nodes(
            tx,
            window,
            select_nodes(ident(change.model), f"{old} IS NOT NULL", window)
            + f" SET {new} = {old} REMOVE {old}",
        )
    await rename_relation_edges(tx, change, state)
    return None


async def alter_nullability(
    tx: Transaction,
    change: c.AlterNullability,
    state: dict,
    window: Window | None = None,
) -> list[str] | None:
    if change.nullable:
        return None if window is None else []
    needs(change, change.default, "a value where there is none (`default`)")
    field = field_of(state, change.model, change.name)
    params: dict[str, Any] = {}
    if field["kind"] in ("literal", "list"):
        expression = literal_expression(
            change.default, field_descriptor(field), params, "default", state["enums"]
        )
    else:
        params["default"] = change.default
        expression = "$default"
    prop = f"n.{ident(change.name)}"
    return await run_on_nodes(
        tx,
        window,
        select_nodes(ident(change.model), f"{prop} IS NULL", window)
        + f" SET {prop} = {expression}",
        **params,
    )


async def alter_literal_type(
    tx: Transaction,
    change: c.AlterLiteralType,
    state: dict,
    window: Window | None = None,
) -> list[str] | None:
    return await convert_property(
        tx, change, state, change.old, change.new, False, window
    )


async def alter_list_item_type(
    tx: Transaction,
    change: c.AlterListItemType,
    state: dict,
    window: Window | None = None,
) -> list[str] | None:
    return await convert_property(
        tx, change, state, change.old, change.new, True, window
    )


async def convert_property(
    tx, change, state, old: dict, new: dict, is_list: bool, window: Window | None = None
) -> list[str] | None:
    """Convert the values of a field to another type. What does not convert is dealt with as
    `on_failure` says; by default that is to fail, and **before anything is changed** (a count of
    what would fail, once, before the first batch)."""
    label, prop = ident(change.model), f"n.{ident(change.name)}"
    ref = "x" if is_list else prop
    expression, params = convert_expression(
        old, new, ref, state["enums"], change.mapping
    )
    if is_list:
        converted = f"[x IN {prop} | {expression}]"
        failing = f"any(x IN {prop} WHERE {expression} IS NULL)"
    else:
        converted = expression
        failing = f"{expression} IS NULL"
    policy = change.on_failure or "fail"

    if window is None or window.first:
        failures = (
            await run(
                tx,
                f"MATCH (n:{label}) WHERE {prop} IS NOT NULL AND {failing} RETURN count(n) AS failed",
                **params,
            )
        )[0]["failed"]
        if failures and policy == "fail":
            raise PanglossMigrationAnswerNeeded(
                f"{failures} values of {change.model}.{change.name} cannot be converted "
                f"({change.describe()}): say what to do with them (`on_failure`: 'null' or 'default')"
            )
        if failures and policy == "default":
            needs(
                change,
                change.default,
                "the value to give what does not convert (`default`)",
            )

    if policy == "default" and change.default is not None:
        default_params: dict[str, Any] = {}
        default = literal_expression(
            change.default,
            new if not is_list else {"type": "list", "item": new},
            default_params,
            "fallback",
            state["enums"],
        )
        params = {**params, **default_params}
        result = f"CASE WHEN {failing} THEN {default} ELSE {converted} END"
    elif policy == "null":
        if is_list:
            result = f"[y IN [x IN {prop} | {expression}] WHERE y IS NOT NULL]"
        else:
            result = f"CASE WHEN {failing} THEN null ELSE {converted} END"
    else:
        result = converted
    return await run_on_nodes(
        tx,
        window,
        select_nodes(label, f"{prop} IS NOT NULL", window) + f" SET {prop} = {result}",
        **params,
    )


async def literal_to_annotated(
    tx: Transaction,
    change: c.LiteralToAnnotatedValue,
    state: dict,
    window: Window | None = None,
) -> list[str] | None:
    annotated = (
        model_of(state, change.annotated_model)
        if change.annotated_model in state["models"]
        else None
    )
    extras = {
        f["name"]: f
        for f in (annotated or {"fields": []})["fields"]
        if f["name"] != "value"
    }
    defaults = change.defaults or {}
    missing = [
        name
        for name, f in extras.items()
        if not f.get("nullable") and name not in defaults
    ]
    if missing:
        raise PanglossMigrationAnswerNeeded(
            f"{change.describe()}: values for the extra fields {', '.join(missing)} (`defaults`)"
        )
    prop = f"n.{ident(change.name)}"
    params: dict[str, Any] = {}
    parts = ["value: " + prop]
    for name, value in defaults.items():
        parts.append(
            f"{ident(name)}: {literal_expression(value, field_descriptor(extras[name]), params, 'extra_' + name, state['enums'])}"
        )
    return await run_on_nodes(
        tx,
        window,
        select_nodes(ident(change.model), f"{prop} IS NOT NULL", window)
        + f" SET {prop} = {{{', '.join(parts)}}}",
        **params,
    )


async def annotated_to_literal(
    tx: Transaction,
    change: c.AnnotatedValueToLiteral,
    state: dict,
    window: Window | None = None,
) -> list[str] | None:
    prop = f"n.{ident(change.name)}"
    return await run_on_nodes(
        tx,
        window,
        select_nodes(ident(change.model), f"{prop} IS NOT NULL", window)
        + f" SET {prop} = {prop}.value",
    )


# ---------------------------------------------------------------------------
# Relations
# ---------------------------------------------------------------------------


async def alter_cardinality(
    tx: Transaction, change: c.AlterCardinality, state: dict, limit: int | None = None
) -> int:
    """A list that is now a single value: where a node has several, the first is kept (`keep`).
    With a `limit`, that many nodes at a time (a node that has been dealt with has one)."""
    if change.many:
        return 0
    field = field_of(state, change.model, change.name)
    if owns_nodes(field):
        raise PanglossMigrationNotSupported(
            f"{change.describe()}: the extra nodes would have to be deleted; write it by hand"
        )
    pairs = edge_pairs(field)
    (forward, reverse), others = pairs[0], pairs[1:]
    label = ident(change.model)
    if change.keep != "first":
        several = (
            await run(
                tx,
                f"""
                MATCH (n:{label})-[e]->() WHERE type(e) = $forward AND NOT coalesce(e.reverse, false)
                WITH n, count(e) AS edges WHERE edges > 1 RETURN count(n) AS several
                """,
                forward=forward,
            )
        )[0]["several"]
        if several:
            raise PanglossMigrationAnswerNeeded(
                f"{several} nodes have several {change.model}.{change.name}: say which to keep "
                f"(`keep`: 'first')"
            )
        return 0
    # keep the first edge (the oldest), and remove the others with their reverse edges
    window = f"WITH n, edges LIMIT {int(limit)} " if limit else ""
    rows = await run(
        tx,
        f"""
        MATCH (n:{label})-[e]->(t) WHERE type(e) = $forward AND NOT coalesce(e.reverse, false)
        WITH n, e, t ORDER BY id(e)
        WITH n, collect({{e: e, t: t}}) AS edges WHERE size(edges) > 1
        {window}UNWIND edges[1..] AS extra
        WITH n, extra.e AS e, extra.t AS t
        OPTIONAL MATCH (t)-[r]->(n) WHERE type(r) = $reverse AND coalesce(r.reverse, false)
        DELETE e, r
        RETURN count(DISTINCT n) AS done
        """,
        forward=forward,
        reverse=reverse,
    )
    done = rows[0]["done"] if rows else 0
    for other_forward, other_reverse in others:
        # (the pairs of the parent fields go to the same target)
        other_window = f"WITH n, e, t LIMIT {int(limit)} " if limit else ""
        rows = await run(
            tx,
            f"""
            MATCH (n:{label})-[e]->(t)
            WHERE type(e) = $other AND NOT coalesce(e.reverse, false) AND NOT (n)-[:{ident(forward)}]->(t)
            {other_window}OPTIONAL MATCH (t)-[r]->(n) WHERE type(r) = $other_reverse AND coalesce(r.reverse, false)
            DELETE e, r
            RETURN count(DISTINCT e) AS done
            """,
            other=other_forward,
            other_reverse=other_reverse,
        )
        done = max(done, rows[0]["done"] if rows else 0)
    return done


def allowed_labels(options: list[dict]) -> list[str]:
    """The labels a target can have, for options that are direct"""
    return sorted(
        {
            o["type"]
            for o in options
            if o["kind"]
            in DIRECT_KINDS
            | {
                "reifiedRelation",
                "reifiedRelationDocument",
                "semanticSpace",
                "conjunction",
            }
        }
    )


async def alter_relation_target(
    tx: Transaction,
    change: c.AlterRelationTarget,
    state: dict,
    limit: int | None = None,
) -> int:
    """Edges to what a relation can no longer be to: it fails if there are any (and says how many),
    or they are removed (`on_narrowing`); with a `limit`, that many at a time"""
    if not change.removed:
        return 0
    field = field_of(state, change.model, change.name)
    allowed = allowed_labels(change.options)
    forward, reverse = edge_pairs(field)[0]
    label = ident(change.model)
    if change.on_narrowing != "remove":
        violations = (
            await run(
                tx,
                f"""
                MATCH (n:{label})-[e]->(t) WHERE type(e) = $forward AND NOT coalesce(e.reverse, false)
                  AND NOT any(l IN labels(t) WHERE l IN $allowed)
                RETURN count(e) AS violations
                """,
                forward=forward,
                allowed=allowed,
            )
        )[0]["violations"]
        if violations:
            raise PanglossMigrationAnswerNeeded(
                f"{violations} relations {change.model}.{change.name} are to what it can no longer be "
                f"to: say what to do (`on_narrowing`: 'remove')"
            )
        return 0
    if owns_nodes(field):
        if await run(
            tx,
            f"""
            MATCH (n:{label})-[e]->(t) WHERE type(e) = $forward AND NOT coalesce(e.reverse, false)
              AND NOT any(l IN labels(t) WHERE l IN $allowed)
            RETURN e LIMIT 1
            """,
            forward=forward,
            allowed=allowed,
        ):
            raise PanglossMigrationNotSupported(
                f"{change.describe()}: nodes that belong to the document would be left; write it by hand"
            )
        return 0
    window = f"WITH n, e, t LIMIT {int(limit)} " if limit else ""
    done = 0
    for pair_forward, pair_reverse in edge_pairs(field):
        rows = await run(
            tx,
            f"""
            MATCH (n:{label})-[e]->(t) WHERE type(e) = $forward AND NOT coalesce(e.reverse, false)
              AND NOT any(l IN labels(t) WHERE l IN $allowed)
            {window}OPTIONAL MATCH (t)-[r]->(n) WHERE type(r) = $reverse AND coalesce(r.reverse, false)
            DELETE e, r
            RETURN count(DISTINCT e) AS done
            """,
            forward=pair_forward,
            reverse=pair_reverse,
            allowed=allowed,
        )
        done = max(done, rows[0]["done"] if rows else 0)
    return done


async def alter_reverse_name(
    tx: Transaction, change: c.AlterReverseName, state: dict, limit: int | None = None
) -> int:
    field = field_of(state, change.model, change.name)
    old = edge_pairs(field)[0][1]
    if old == change.new:
        return 0
    return await rename_edge_type(
        tx, change.model, old, change.new, reverse=True, limit=limit
    )


async def alter_parent_fields(
    tx: Transaction, change: c.AlterParentFields, state: dict, limit: int | None = None
) -> int:
    """The edge pair of each parent field a field now narrows is written, and those of the parent
    fields it no longer narrows are deleted: `limit` edges at a time at most (those done are no
    longer there to do)"""
    field = field_of(state, change.model, change.name)
    forward, reverse = edge_pairs(field)[0]
    label = ident(change.model)
    new_reverse = {name: rev or f"{name}_reverse" for name, rev in change.edges}
    window = f"WITH n, e, t LIMIT {int(limit)} " if limit else ""
    done = 0
    for parent in change.added:
        parent_reverse = new_reverse[parent]
        rows = await run(
            tx,
            f"""
            MATCH (n:{label})-[e:{ident(forward)}]->(t)
            WHERE NOT coalesce(e.reverse, false) AND NOT (n)-[:{ident(parent)}]->(t)
            {window}CREATE (n)-[f:{ident(parent)}]->(t) SET f = properties(e)
            WITH n, t, f
            OPTIONAL MATCH (t)-[r:{ident(reverse)}]->(n) WHERE coalesce(r.reverse, false)
            FOREACH (x IN CASE WHEN r IS NULL THEN [] ELSE [1] END |
                CREATE (t)-[g:{ident(parent_reverse)}]->(n) SET g = properties(r))
            RETURN count(DISTINCT f) AS done
            """,
        )
        done = max(done, rows[0]["done"] if rows else 0)
    old_reverse = {name: rev for name, rev in edge_pairs(field)}
    removed_pairs = [
        (name, old_reverse[name]) for name in change.removed if name in old_reverse
    ]
    if removed_pairs and limit is None:
        await delete_relation(tx, change.model, field, only_pairs=removed_pairs)
    elif removed_pairs:
        for removed_forward, removed_reverse in removed_pairs:
            for query, name in (
                (
                    f"MATCH (n:{label})-[e:{ident(removed_forward)}]->() WITH e LIMIT {int(limit)} DELETE e RETURN count(e) AS done",  # ty: ignore[invalid-argument-type]
                    removed_forward,
                ),
                (
                    f"MATCH ()-[e:{ident(removed_reverse)}]->(n:{label}) WITH e LIMIT {int(limit)} DELETE e RETURN count(e) AS done",  # ty: ignore[invalid-argument-type]
                    removed_reverse,
                ),
            ):
                rows = await run(tx, query)
                done = max(done, rows[0]["done"] if rows else 0)
    return done


def edge_model_properties(state: dict, options: list[dict]) -> dict[str, dict]:
    """The fields of the edge model of the options, by name"""
    names = sorted({o["edgeModel"] for o in options if o.get("edgeModel")})
    properties: dict[str, dict] = {}
    for name in names:
        for entry in model_of(state, name)["fields"]:
            properties[entry["name"]] = entry
    return properties


async def alter_edge_model(
    tx: Transaction, change: c.AlterEdgeModel, state: dict, limit: int | None = None
) -> int:
    """Properties taken off, or given a value on, the edges of a relation (both edges of each pair):
    on all, or `limit` at a time (those done no longer have the property, or now do)"""
    field = field_of(state, change.model, change.name)
    old = edge_model_properties(state, field["options"])
    new = edge_model_properties(state, change.options)
    pairs = edge_pairs(field)
    label = ident(change.model)
    done = 0

    async def on_edges(forward_query: str, reverse_query: str, **params: Any) -> None:
        nonlocal done
        for query in (forward_query, reverse_query):
            rows = await run(tx, query, **params)
            done = max(done, rows[0]["done"] if rows else 0)

    window = f"WITH e LIMIT {int(limit)} " if limit else ""
    gone = [name for name in old if name not in new]
    for name in gone:
        for forward, reverse in pairs:
            await on_edges(
                f"MATCH (n:{label})-[e:{ident(forward)}]->() WHERE e.{ident(name)} IS NOT NULL "
                f"{window}REMOVE e.{ident(name)} RETURN count(e) AS done",
                f"MATCH ()-[e:{ident(reverse)}]->(n:{label}) WHERE e.{ident(name)} IS NOT NULL "
                f"{window}REMOVE e.{ident(name)} RETURN count(e) AS done",
            )

    added = {name: entry for name, entry in new.items() if name not in old}
    defaults = change.defaults or {}
    missing = [
        n for n, e in added.items() if not e.get("nullable") and n not in defaults
    ]
    if missing:
        raise PanglossMigrationAnswerNeeded(
            f"{change.describe()}: values for {', '.join(missing)} on the edges that exist (`defaults`)"
        )
    for name, value in defaults.items():
        if name not in added:
            continue
        params: dict[str, Any] = {}
        expression = literal_expression(
            value, field_descriptor(added[name]), params, "edge_value", state["enums"]
        )
        for forward, reverse in pairs:
            await on_edges(
                f"MATCH (n:{label})-[e:{ident(forward)}]->() "
                f"WHERE NOT coalesce(e.reverse, false) AND e.{ident(name)} IS NULL "
                f"{window}SET e.{ident(name)} = {expression} RETURN count(e) AS done",
                f"MATCH ()-[e:{ident(reverse)}]->(n:{label}) "
                f"WHERE coalesce(e.reverse, false) AND e.{ident(name)} IS NULL "
                f"{window}SET e.{ident(name)} = {expression} RETURN count(e) AS done",
                **params,
            )
    return done


# ---------------------------------------------------------------------------
# Wrapping a relation in a node
# ---------------------------------------------------------------------------


# The `meta` of a node that is made beside another, `s`, for what `s` holds (a node a migration
# inserts, such as a reified relation): written as the models would write it. Its times and
# creator are those of `s` (or, for a head node, which has no `meta`, of its creation); it is in
# the semantic spaces `s` is in; and the context is that of `s`, with `s` in it if `s` is a
# document nested in another (and so a part of the context of what it holds).
INSERTED_NODE_META = """
    OPTIONAL MATCH (s)<-[:is_creation_of]-(creation:PGCreation)-[:created_by]->(creator:PGUser)
    WITH *, coalesce(s.meta, {
        created_by: creator.username, created_when: creation.created_when,
        updated_by: creator.username, updated_when: creation.created_when,
        semantic_spaces: [], context_labels: []}) AS base_meta
    WITH *, {
        created_by: base_meta.created_by, created_when: base_meta.created_when,
        updated_by: base_meta.updated_by, updated_when: base_meta.updated_when,
        semantic_spaces: coalesce(base_meta.semantic_spaces, []),
        context_labels: CASE
            WHEN s.meta IS NULL THEN []
            WHEN size(coalesce(base_meta.context_labels, [])) > 0 THEN base_meta.context_labels
            WHEN coalesce($labels_in_context[s.type], true)
                THEN [{type: '#rootcontext', contents: [{type: s.type, id: s.id}]}]
            ELSE [] END} AS new_meta
"""


def labels_in_context(state: dict) -> dict[str, bool]:
    """Whether a nested document of each model is a part of the context of what it holds"""
    return {
        name: model.get("useInSemanticSpaceLabel", True)
        for name, model in state["models"].items()
    }


def narrowers_of(state: dict, forward: str) -> list[str]:
    """The fields that narrow the field with this edge type: they write its edges as well, to
    the same target, and so are the ones that change it"""
    names: set[str] = set()
    for model in state["models"].values():
        for entry in model["fields"]:
            pairs = edge_pairs(entry) if entry.get("storage", {}).get("edges") else []
            if any(pair[0] == forward for pair in pairs[1:]) and pairs:
                names.add(pairs[0][0])
    return sorted(names)


def wrapper_properties(
    change: c.WrapRelation, state: dict
) -> tuple[str, dict[str, Any]]:
    """The assignments for the literals of the wrapper node, from the answers given"""
    wrapper = model_of(state, change.wrapper)
    defaults = change.defaults or {}
    params: dict[str, Any] = {}
    assignments: list[str] = []
    missing = []
    for entry in wrapper["fields"]:
        if entry["kind"] not in ("literal", "list"):
            continue  # (relations and the like: nothing to say for what exists)
        name = entry["name"]
        if name in defaults:
            expression = literal_expression(
                defaults[name],
                field_descriptor(entry),
                params,
                f"wrapper_{name}",
                state["enums"],
            )
            assignments.append(f"{ident(name)}: {expression}")
        elif not entry.get("nullable"):
            missing.append(name)
    if missing:
        raise PanglossMigrationAnswerNeeded(
            f"{change.describe()}: values for {', '.join(missing)} of {change.wrapper} on the "
            f"relations that exist (`defaults`)"
        )
    return ", ".join(assignments), params


async def wrap_relation(
    tx: Transaction, change: c.WrapRelation, state: dict, limit: int | None = None
) -> int:
    if change.wrapper_kind == "semanticSpace":
        return await wrap_in_semantic_space(tx, change, state, limit)
    if change.wrapper_kind != "reifiedRelation":
        raise PanglossMigrationNotSupported(
            f"{change.describe()}: a relation cannot be wrapped in a {change.wrapper_kind} "
            f"(it has several slots to fill): write it by hand"
        )
    return await wrap_reified(tx, change, state, limit=limit)


async def wrap_reified(
    tx: Transaction, change: c.WrapRelation, state: dict, limit: int | None
) -> int:
    """Wrap relations in a reified relation: all of them, or `limit` (the next, in the order of the
    ids of the nodes). What is wrapped is no longer there to be wrapped, so this is called again
    until it wraps none. Returns how many it wrapped."""
    field = field_of(state, change.model, change.name)
    wrapper = model_of(state, change.wrapper)
    pairs = edge_pairs(field)
    primary = pairs[0][0]
    model, wrapper_label = ident(change.model), ident(change.wrapper)
    # (the first label is read as the class of the node, as the models write them)
    wrapper_labels = "".join(
        ":" + ident(label) for label in [*wrapper["labels"], "PGIndexableNode"]
    )
    assignments, params = wrapper_properties(change, state)
    # (what a field that narrows this one relates to is its to change)
    not_narrowed = "".join(
        f" AND NOT (s)-[:{ident(n)}]->(p)" for n in narrowers_of(state, primary)
    )
    pairs_to_wrap = f"""
        MATCH (s:{model})-[e]->(p)
        WHERE type(e) = $primary AND NOT coalesce(e.reverse, false) AND NOT p:{wrapper_label}{not_narrowed}
        {"WITH s, p ORDER BY s.id, p.id LIMIT $limit" if limit else ""}
    """

    count = (
        await run(
            tx,
            f"{pairs_to_wrap} RETURN count(*) AS count",
            primary=primary,
            limit=limit,
        )
    )[0]["count"]
    if not count:
        return 0
    ids = [str(uuid.uuid7()) for _ in range(count)]

    new_edges = []
    for forward, reverse in pairs:
        new_edges.append(f"CREATE (s)-[:{ident(forward)}]->(r)")
        new_edges.append(f"CREATE (r)-[:{ident(reverse)} {{reverse: true}}]->(s)")
    await run(
        tx,
        f"""
        {pairs_to_wrap}
        WITH collect({{s: s, p: p}}) AS pairs
        UNWIND range(0, size(pairs) - 1) AS i
        WITH pairs[i].s AS s, pairs[i].p AS p, $ids[i] AS new_id
        {INSERTED_NODE_META}
        CREATE (r{wrapper_labels} {{
            id: new_id,
            type: $wrapper,
            head_node_id: coalesce(s.head_node_id, s.id),
            head_node_type: coalesce(s.head_node_type, s.type),
            meta: new_meta{", " + assignments if assignments else ""}
        }})
        {" ".join(new_edges)}
        CREATE (r)-[:target]->(p)
        CREATE (p)-[:target_reverse {{reverse: true}}]->(r)
        """,
        primary=primary,
        ids=ids,
        limit=limit,
        wrapper=change.wrapper,
        labels_in_context=labels_in_context(state),
        **params,
    )
    # the edges that went straight to the target (only those of the relations just wrapped:
    # the others are the narrowing fields', and still to be done)
    await run(
        tx,
        f"""
        MATCH (s:{model})-[e]->(p)
        WHERE type(e) IN $forward AND NOT coalesce(e.reverse, false) AND NOT p:{wrapper_label}
          AND EXISTS {{ MATCH (s)-[:{ident(primary)}]->(r:{wrapper_label})-[:target]->(p) }}
        DELETE e
        """,
        forward=[f for f, _ in pairs],
    )
    await run(
        tx,
        f"""
        MATCH (p)-[e]->(s:{model})
        WHERE type(e) IN $reverse AND coalesce(e.reverse, false) AND NOT p:{wrapper_label}
          AND EXISTS {{ MATCH (s)-[:{ident(primary)}]->(r:{wrapper_label})-[:target]->(p) }}
        DELETE e
        """,
        reverse=[r for _, r in pairs],
    )
    return count


async def unwrap_relation(
    tx: Transaction, change: c.UnwrapRelation, state: dict, limit: int | None = None
) -> int:
    """Unwrap relations: all of them, or `limit` (those unwrapped are no longer there to unwrap, so
    this is called again until it unwraps none). Returns how many."""
    if change.wrapper_kind == "semanticSpace":
        return await unwrap_semantic_space(tx, change, state, limit)
    if change.wrapper_kind != "reifiedRelation":
        raise PanglossMigrationNotSupported(
            f"{change.describe()}: unwrapping a {change.wrapper_kind} is not supported: "
            f"write it by hand"
        )
    field = field_of(state, change.model, change.name)
    pairs = edge_pairs(field)
    primary = pairs[0][0]
    model, wrapper_label = ident(change.model), ident(change.wrapper)

    not_narrowed = "".join(
        f" AND NOT (s)-[:{ident(n)}]->(r)" for n in narrowers_of(state, primary)
    )
    ids = await wrapper_ids(tx, model, wrapper_label, primary, not_narrowed, limit)
    if not ids:
        return 0
    creates = []
    for forward, reverse in pairs:
        creates.append(f"MERGE (s)-[:{ident(forward)}]->(p)")
        creates.append(f"MERGE (p)-[:{ident(reverse)} {{reverse: true}}]->(s)")
    await run(
        tx,
        f"""
        MATCH (s:{model})-[e]->(r:{wrapper_label})-[:target]->(p)
        WHERE type(e) = $primary AND NOT coalesce(e.reverse, false){not_narrowed} AND r.id IN $ids
        {" ".join(creates)}
        """,
        primary=primary,
        ids=ids,
    )
    # the node between, with the edges to it and from it (that the relations just unwrapped had)
    await run(
        tx,
        f"""
        MATCH (s:{model})-[e]->(r:{wrapper_label})
        WHERE type(e) = $primary AND NOT coalesce(e.reverse, false){not_narrowed} AND r.id IN $ids
        DETACH DELETE r
        """,
        primary=primary,
        ids=ids,
    )
    return len(ids)


async def wrapper_ids(
    tx: Transaction,
    model: str,
    wrapper_label: str,
    primary: str,
    not_narrowed: str,
    limit: int | None,
) -> list[str]:
    """The ids of the wrapper nodes on the edges of a relation: all of them, or `limit`"""
    window = f"WITH DISTINCT r LIMIT {int(limit)} " if limit else ""
    rows = await run(
        tx,
        f"""
        MATCH (s:{model})-[e]->(r:{wrapper_label})
        WHERE type(e) = $primary AND NOT coalesce(e.reverse, false){not_narrowed}
        {window}RETURN collect(DISTINCT r.id) AS ids
        """,
        primary=primary,
    )
    return rows[0]["ids"] if rows else []


# ---------------------------------------------------------------------------
# Semantic spaces, and the context that nodes are in
# ---------------------------------------------------------------------------


class StoredContext:
    """How a migration looks at the nodes of a document that is stored, for
    `pangloss_models.context.propagate_context` (the one algorithm the models use too): by the id of a
    node, with what was read of the nodes and of the edges between them. Only relations are
    followed, not embedded objects; and an entity is not one of the nodes."""

    def __init__(
        self,
        nodes: dict[str, dict],
        children: dict[str, dict[str, list[str]]],
        state: dict,
        in_context: dict[str, bool],
        out: dict[str, tuple[list[str], list[dict]]],
    ) -> None:
        self.nodes, self.child_ids, self.state = nodes, children, state
        self.counts_as_context, self.out = in_context, out

    def is_entity(self, node: str) -> bool:
        return False

    def is_space(self, node: str) -> bool:
        return "SemanticSpace" in self.nodes[node]["labels"]

    def in_context(self, node: str) -> bool:
        data = self.nodes[node]
        return "Document" in data["labels"] and self.counts_as_context.get(
            data["type"], True
        )

    def type_of(self, node: str) -> str:
        return self.nodes[node]["type"]

    def id_of(self, node: str) -> str:
        return node

    def children(self, node: str):
        model = self.state["models"].get(self.nodes[node]["type"], {})
        for entry in model.get("fields", []):
            if entry["kind"] != "relation":
                continue
            forward = edge_pairs(entry)[0][0]
            for child in self.child_ids.get(node, {}).get(forward, []):
                yield child, entry["many"]

    def assign(
        self, node: str, semantic_spaces: list[str], context_labels: list[dict]
    ) -> None:
        self.out[node] = (semantic_spaces, context_labels)


async def recompute_contexts(tx: Transaction, head_ids: list[str], state: dict) -> None:
    """Write `meta.semantic_spaces` and `meta.context_labels` of every node of the documents again,
    from where the nodes are now. (Nodes that a migration puts a semantic space round, or takes one
    away from, or whose model is renamed, have them wrong otherwise.)"""
    in_context = labels_in_context(state)
    for head_id in dict.fromkeys(head_ids):
        rows = await run(
            tx,
            """
            MATCH (n) WHERE n.id = $id OR n.head_node_id = $id
            RETURN n.id AS id, labels(n) AS labels, n.type AS type, n.meta AS meta
            """,
            id=head_id,
        )
        nodes = {row["id"]: row for row in rows}
        edges = await run(
            tx,
            """
            MATCH (a)-[e]->(b)
            WHERE (a.id = $id OR a.head_node_id = $id) AND b.head_node_id = $id
              AND NOT coalesce(e.reverse, false)
            RETURN a.id AS source, b.id AS target, type(e) AS type ORDER BY id(e)
            """,
            id=head_id,
        )
        children: dict[str, dict[str, list[str]]] = {}
        for edge in edges:
            siblings = children.setdefault(edge["source"], {}).setdefault(
                edge["type"], []
            )
            if (
                edge["target"] not in siblings
            ):  # (parallel edges: a field that narrows another)
                siblings.append(edge["target"])
        if head_id not in nodes:
            continue
        computed: dict[str, tuple[list[str], list[dict]]] = {}
        propagate_context(
            head_id,
            [],
            [],
            None,
            StoredContext(nodes, children, state, in_context, computed),
        )

        updates = []
        for node_id, (spaces, labels) in computed.items():
            meta = nodes[node_id]["meta"]
            if node_id == head_id or meta is None:
                continue  # (a head node has no `meta`)
            updates.append(
                {
                    "id": node_id,
                    "meta": {
                        **meta,
                        "semantic_spaces": spaces,
                        "context_labels": labels,
                    },
                }
            )
        if updates:
            await run(
                tx,
                "UNWIND $updates AS u MATCH (n {id: u.id}) SET n.meta = u.meta",
                updates=updates,
            )


async def wrap_in_semantic_space(
    tx: Transaction, change: c.WrapRelation, state: dict, limit: int | None = None
) -> int:
    """A node for the space on each edge, between the node and what it holds (which is then in the
    space, as is everything below it): on all of them, or on `limit` (what is wrapped is no longer
    there to be wrapped). Returns how many."""
    field = field_of(state, change.model, change.name)
    space_model = model_of(state, change.wrapper)
    pairs = edge_pairs(field)
    primary = pairs[0][0]
    contents_forward, contents_reverse = edge_pairs(
        field_of(state, change.wrapper, "contents")
    )[0]
    model, space_label = ident(change.model), ident(change.wrapper)
    labels = "".join(
        ":" + ident(label) for label in [*space_model["labels"], "PGIndexableNode"]
    )
    not_narrowed = "".join(
        f" AND NOT (s)-[:{ident(n)}]->(p)" for n in narrowers_of(state, primary)
    )

    window = f"WITH s, p LIMIT {int(limit)}" if limit else ""
    match = f"""
        MATCH (s:{model})-[e]->(p)
        WHERE type(e) = $primary AND NOT coalesce(e.reverse, false) AND NOT p:{space_label}{not_narrowed}
        {window}
    """
    count = (await run(tx, match + " RETURN count(*) AS count", primary=primary))[0][
        "count"
    ]
    if not count:
        return 0
    ids = [str(uuid.uuid7()) for _ in range(count)]
    new_edges = []
    for forward, reverse in pairs:
        new_edges.append(f"CREATE (s)-[:{ident(forward)}]->(r)")
        new_edges.append(f"CREATE (r)-[:{ident(reverse)} {{reverse: true}}]->(s)")
    heads = await run(
        tx,
        f"""
        {match}
        WITH collect({{s: s, p: p}}) AS pairs
        UNWIND range(0, size(pairs) - 1) AS i
        WITH pairs[i].s AS s, pairs[i].p AS p, $ids[i] AS new_id
        {INSERTED_NODE_META}
        CREATE (r{labels} {{
            id: new_id,
            type: $wrapper,
            head_node_id: coalesce(s.head_node_id, s.id),
            head_node_type: coalesce(s.head_node_type, s.type),
            meta: {{created_by: new_meta.created_by, created_when: new_meta.created_when,
                    updated_by: new_meta.updated_by, updated_when: new_meta.updated_when,
                    semantic_spaces: [], context_labels: null}}
        }})
        {" ".join(new_edges)}
        CREATE (r)-[:{ident(contents_forward)}]->(p)
        CREATE (p)-[:{ident(contents_reverse)} {{reverse: true}}]->(r)
        RETURN DISTINCT coalesce(s.head_node_id, s.id) AS head
        """,
        primary=primary,
        ids=ids,
        wrapper=change.wrapper,
        labels_in_context=labels_in_context(state),
    )
    # the edges that went straight to what is held now
    for direction in ("forward", "reverse"):
        if direction == "forward":
            query = f"""
                MATCH (s:{model})-[e]->(p)
                WHERE type(e) IN $names AND NOT coalesce(e.reverse, false) AND NOT p:{space_label}
                  AND EXISTS {{ MATCH (s)-[:{ident(primary)}]->(r:{space_label})-[:{ident(contents_forward)}]->(p) }}
                DELETE e
            """
            names = [f for f, _ in pairs]
        else:
            query = f"""
                MATCH (p)-[e]->(s:{model})
                WHERE type(e) IN $names AND coalesce(e.reverse, false) AND NOT p:{space_label}
                  AND EXISTS {{ MATCH (s)-[:{ident(primary)}]->(r:{space_label})-[:{ident(contents_forward)}]->(p) }}
                DELETE e
            """
            names = [r for _, r in pairs]
        await run(tx, query, names=names)
    await recompute_contexts(tx, [row["head"] for row in heads], state)
    return count


async def unwrap_semantic_space(
    tx: Transaction, change: c.UnwrapRelation, state: dict, limit: int | None = None
) -> int:
    field = field_of(state, change.model, change.name)
    pairs = edge_pairs(field)
    primary = pairs[0][0]
    contents_forward = edge_pairs(field_of(state, change.wrapper, "contents"))[0][0]
    model, space_label = ident(change.model), ident(change.wrapper)
    not_narrowed = "".join(
        f" AND NOT (s)-[:{ident(n)}]->(r)" for n in narrowers_of(state, primary)
    )
    ids = await wrapper_ids(tx, model, space_label, primary, not_narrowed, limit)
    if not ids:
        return 0
    creates = []
    for forward, reverse in pairs:
        creates.append(f"MERGE (s)-[:{ident(forward)}]->(p)")
        creates.append(f"MERGE (p)-[:{ident(reverse)} {{reverse: true}}]->(s)")
    heads = await run(
        tx,
        f"""
        MATCH (s:{model})-[e]->(r:{space_label})-[:{ident(contents_forward)}]->(p)
        WHERE type(e) = $primary AND NOT coalesce(e.reverse, false){not_narrowed} AND r.id IN $ids
        {" ".join(creates)}
        RETURN DISTINCT coalesce(s.head_node_id, s.id) AS head
        """,
        primary=primary,
        ids=ids,
    )
    await run(
        tx,
        f"""
        MATCH (s:{model})-[e]->(r:{space_label})
        WHERE type(e) = $primary AND NOT coalesce(e.reverse, false){not_narrowed} AND r.id IN $ids
        DETACH DELETE r
        """,
        primary=primary,
        ids=ids,
    )
    await recompute_contexts(tx, [row["head"] for row in heads], state)
    return len(ids)


# ---------------------------------------------------------------------------
# One wrapper for another, and literals in a node of their own
# ---------------------------------------------------------------------------


async def change_wrapper(
    tx: Transaction, change: c.ChangeWrapper, state: dict, limit: int | None = None
) -> int:
    if change.wrapper_kind != "reifiedRelation":
        raise PanglossMigrationNotSupported(
            f"{change.describe()}: only reified relations are supported: write it by hand"
        )
    old, new = model_of(state, change.old_wrapper), model_of(state, change.new_wrapper)
    field = field_of(state, change.model, change.name)
    primary = edge_pairs(field)[0][0]
    model, old_label = ident(change.model), ident(change.old_wrapper)

    old_props = {f["name"] for f in old["fields"] if f["kind"] in ("literal", "list")}
    new_literals = {
        f["name"]: f for f in new["fields"] if f["kind"] in ("literal", "list")
    }
    defaults = change.defaults or {}
    missing = [
        n
        for n, f in new_literals.items()
        if n not in old_props and not f.get("nullable") and n not in defaults
    ]
    if missing:
        raise PanglossMigrationAnswerNeeded(
            f"{change.describe()}: values for {', '.join(missing)} of {change.new_wrapper} (`defaults`)"
        )
    params: dict[str, Any] = {}
    sets = []
    for name, value in defaults.items():
        if name in new_literals and name not in old_props:
            expression = literal_expression(
                value,
                field_descriptor(new_literals[name]),
                params,
                f"wrapper_{name}",
                state["enums"],
            )
            sets.append(f"r.{ident(name)} = {expression}")
    removes = [f"r.{ident(name)}" for name in sorted(old_props - set(new_literals))]
    old_labels = [label for label in old["labels"] if label not in new["labels"]]
    new_labels = [label for label in new["labels"] if label not in old["labels"]]

    clauses = []
    if old_labels:
        clauses.append("REMOVE r" + "".join(":" + ident(label) for label in old_labels))
    if new_labels:
        clauses.append("SET r" + "".join(":" + ident(label) for label in new_labels))
    clauses.append(
        "SET r.type = $new_type" + "".join(", " + assignment for assignment in sets)
    )
    if removes:
        clauses.append("REMOVE " + ", ".join(removes))
    # (what is changed no longer has the old label, so a next call finds the next)
    window = f"WITH DISTINCT r LIMIT {int(limit)}" if limit else "WITH DISTINCT r"
    rows = await run(
        tx,
        f"""
        MATCH (s:{model})-[e]->(r:{old_label})
        WHERE type(e) = $primary AND NOT coalesce(e.reverse, false)
        {window}
        {" ".join(clauses)}
        RETURN count(r) AS done
        """,
        primary=primary,
        new_type=change.new_wrapper,
        **params,
    )
    return rows[0]["done"] if rows else 0


def embedded_node_clauses(
    state: dict, embedded_model: str
) -> tuple[str, dict[str, Any]]:
    model = model_of(state, embedded_model)
    return "".join(
        ":" + ident(label) for label in [*model["labels"], "PGIndexableNode"]
    ), {}


async def literals_to_embedded(
    tx: Transaction, change: c.LiteralsToEmbedded, state: dict, limit: int | None = None
) -> int:
    """A node of the embedded object on each node that has the fields, with the values moved
    into it: on all of them, or on `limit` (those done no longer have the values). Returns how many."""
    embedded_name = change.embedded_type or change.embedded_model
    embedded = model_of(state, embedded_name)
    own = {f["name"]: f for f in embedded["fields"]}
    required_elsewhere = [
        n
        for n, f in own.items()
        if n not in change.fields
        and not f.get("nullable")
        and f["kind"] in ("literal", "list")
    ]
    defaults = change.defaults or {}
    missing = [n for n in required_elsewhere if n not in defaults]
    if missing:
        raise PanglossMigrationAnswerNeeded(
            f"{change.describe()}: values for {', '.join(missing)} of {embedded_name} (`defaults`)"
        )
    forward, reverse = edge_pairs(change.definition)[0]
    labels = "".join(
        ":" + ident(label) for label in [*embedded["labels"], "PGIndexableNode"]
    )
    model = ident(change.model)
    holds = " OR ".join(f"s.{ident(f)} IS NOT NULL" for f in change.fields) or "true"
    params: dict[str, Any] = {}
    extra = []
    for name, value in defaults.items():
        if name in own:
            extra.append(
                f"{ident(name)}: "
                + literal_expression(
                    value,
                    field_descriptor(own[name]),
                    params,
                    f"default_{name}",
                    state["enums"],
                )
            )

    properties = [f"{ident(f)}: s.{ident(f)}" for f in change.fields] + extra
    tail = ", " + ", ".join(properties) if properties else ""
    removes = (
        f"REMOVE {', '.join(f's.{ident(f)}' for f in change.fields)}"
        if change.fields
        else ""
    )
    window = f"WITH s LIMIT {int(limit)}" if limit else ""
    match = f"""
        MATCH (s:{model})
        WHERE ({holds}) AND NOT (s)-[:{ident(forward)}]->(:Embedded)
        {window}
    """
    count = (await run(tx, match + " RETURN count(*) AS count"))[0]["count"]
    if not count:
        return 0
    ids = [str(uuid.uuid7()) for _ in range(count)]
    await run(
        tx,
        f"""
        {match}
        WITH collect(s) AS owners
        UNWIND range(0, size(owners) - 1) AS i
        WITH owners[i] AS s, $ids[i] AS new_id
        {INSERTED_NODE_META}
        CREATE (e{labels} {{
            id: new_id,
            type: $embedded_type,
            head_node_id: coalesce(s.head_node_id, s.id),
            head_node_type: coalesce(s.head_node_type, s.type),
            meta: {{created_by: new_meta.created_by, created_when: new_meta.created_when,
                    updated_by: new_meta.updated_by, updated_when: new_meta.updated_when,
                    semantic_spaces: [], context_labels: null}}{tail}
        }})
        CREATE (s)-[:{ident(forward)}]->(e)
        CREATE (e)-[:{ident(reverse)} {{reverse: true}}]->(s)
        {removes}
        RETURN DISTINCT coalesce(s.head_node_id, s.id) AS head
        """,
        ids=ids,
        embedded_type=embedded_name,
        labels_in_context=labels_in_context(state),
        **params,
    )
    return count


async def embedded_to_literals(
    tx: Transaction, change: c.EmbeddedToLiterals, state: dict, limit: int | None = None
) -> int:
    """The values of the embedded objects copied onto the nodes that have them, and the objects
    deleted: all of them, or `limit` (those done are no longer there). Returns how many."""
    field = field_of(state, change.model, change.name)
    forward, reverse = edge_pairs(field)[0]
    model = ident(change.model)
    moves = ", ".join(f"s.{ident(f)} = e.{ident(f)}" for f in change.fields)
    if limit is None:
        await run(
            tx,
            f"""
            MATCH (s:{model})-[x:{ident(forward)}]->(e) WHERE NOT coalesce(x.reverse, false)
            SET {moves}
            """,
        )
        await delete_relation(tx, change.model, field)
        return 0
    rows = await run(
        tx,
        f"""
        MATCH (s:{model})-[x:{ident(forward)}]->(e) WHERE NOT coalesce(x.reverse, false)
        WITH s, e LIMIT {int(limit)}
        SET {moves}
        RETURN collect(e.id) AS ids
        """,
    )
    ids = rows[0]["ids"] if rows else []
    if ids:
        await run(
            tx,
            """
            MATCH (e) WHERE e.id IN $ids
            OPTIONAL MATCH (e)-[*BFS (e2, n2 | NOT n2:Entity AND NOT coalesce(e2.reverse, false))]->(d)
            WITH collect(DISTINCT e) + collect(DISTINCT d) AS owned
            UNWIND [x IN owned WHERE x IS NOT NULL] AS o
            DETACH DELETE o
            """,
            ids=ids,
        )
    if ids:
        return len(ids)
    # (the objects are all gone: what is left of the relation, the edges, goes with the last call)
    await delete_relation(tx, change.model, field)
    return 0


# ---------------------------------------------------------------------------
# The classes a node fulfils (`Fulfils`)
# ---------------------------------------------------------------------------


def fulfils_condition(entry: dict) -> str:
    """A Cypher condition that is true of a node `n` that has everything a fulfilled class needs"""
    parts = []
    for need in entry["needs"]:
        if need.get("never"):
            return "false"
        if "property" in need:
            parts.append(f"n.{ident(need['property'])} IS NOT NULL")
        else:
            parts.append(f"EXISTS {{ MATCH (n)-[:{ident(need['edge'])}]->() }}")
    return " AND ".join(parts) or "true"


async def recompute_fulfils(
    tx: Transaction, change: c.RecomputeFulfils, state: dict, limit: int | None = None
) -> int:
    """Give the nodes of the model (of exactly the model, not of its subclasses, which have their
    own change) the labels of the classes they fulfil, and take off those of the classes they do not.

    Each label is looked at by itself: a node should have it if it is one of the model's own, or if
    it fulfils a class that gives it. So a label two classes give is not taken off by one and put
    back by the other. What is done is no longer there to do, so with a `limit` a call again finds
    the next. Returns the most that any label had changed."""
    own = set(model_of(state, change.model)["labels"])
    labels = sorted(
        {
            label
            for entry in [*change.before, *change.after]
            for label in entry["labels"]
        }
        - own
    )
    window = f"WITH n LIMIT {int(limit)} " if limit else ""
    done = 0
    for label in labels:
        providers = [entry for entry in change.after if label in entry["labels"]]
        wanted = (
            " OR ".join(f"({fulfils_condition(entry)})" for entry in providers)
            or "false"
        )
        base = f"MATCH (n:{ident(change.model)}) WHERE n.type = $model"
        for query in (
            f"{base} AND NOT n:{ident(label)} AND ({wanted}) {window}SET n:{ident(label)} RETURN count(n) AS done",
            f"{base} AND n:{ident(label)} AND NOT ({wanted}) {window}REMOVE n:{ident(label)} RETURN count(n) AS done",
        ):
            rows = await run(tx, query, model=change.model)
            done = max(done, rows[0]["done"] if rows else 0)
    return done


# ---------------------------------------------------------------------------
# Indexes and constraints (outside of a transaction)
# ---------------------------------------------------------------------------


async def ddl(database: Database, statement: str) -> None:
    await run_statement(
        database.driver, database.settings.DATABASE.DATABASE_NAME, statement
    )


async def add_index(database: Database, change: c.AddIndex, state: dict) -> None:
    entry = change.index
    label, properties = (
        ident(entry["label"]),
        ", ".join(ident(p) for p in entry["properties"]),
    )
    rows = await run_statement(
        database.driver, database.settings.DATABASE.DATABASE_NAME, "SHOW INDEX INFO"
    )
    if entry.get("kind") == "text":
        name = ident(entry["name"]).strip("`")
        if not any(row["index type"] == f"label_text (name: {name})" for row in rows):
            await ddl(
                database,
                f"CREATE TEXT INDEX {ident(entry['name'])} ON :{label}({properties})",
            )
        return
    if not any(
        row["index type"] == "label+property"
        and row["label"] == entry["label"]
        and row["property"] == entry["properties"]
        for row in rows
    ):
        await ddl(database, f"CREATE INDEX ON :{label}({properties})")


async def remove_index(database: Database, change: c.RemoveIndex, state: dict) -> None:
    entry = change.index
    label, properties = (
        ident(entry["label"]),
        ", ".join(ident(p) for p in entry["properties"]),
    )
    rows = await run_statement(
        database.driver, database.settings.DATABASE.DATABASE_NAME, "SHOW INDEX INFO"
    )
    if entry.get("kind") == "text":
        if any(
            row["index type"] == f"label_text (name: {entry['name']})" for row in rows
        ):
            await ddl(database, f"DROP TEXT INDEX {ident(entry['name'])}")
        return
    if any(
        row["index type"] == "label+property"
        and row["label"] == entry["label"]
        and row["property"] == entry["properties"]
        for row in rows
    ):
        await ddl(database, f"DROP INDEX ON :{label}({properties})")


def constraint_exists(rows: list[dict], entry: dict) -> bool:
    return any(
        row["constraint type"] == "unique"
        and row["label"] == entry["label"]
        and row["properties"] == entry["properties"]
        for row in rows
    )


def unique_statement(verb: str, entry: dict) -> str:
    label = ident(entry["label"])
    properties = ", ".join(f"n.{ident(p)}" for p in entry["properties"])
    return f"{verb} CONSTRAINT ON (n:{label}) ASSERT {properties} IS UNIQUE"


async def add_constraint(
    database: Database, change: c.AddConstraint, state: dict
) -> None:
    rows = await run_statement(
        database.driver,
        database.settings.DATABASE.DATABASE_NAME,
        "SHOW CONSTRAINT INFO",
    )
    if not constraint_exists(rows, change.constraint):
        try:
            await ddl(database, unique_statement("CREATE", change.constraint))
        except neo4j.exceptions.Neo4jError as error:
            raise PanglossMigrationError(
                f"Cannot make {change.describe()}: {error.message} (the data may break it already)"
            ) from error


async def remove_constraint(
    database: Database, change: c.RemoveConstraint, state: dict
) -> None:
    rows = await run_statement(
        database.driver,
        database.settings.DATABASE.DATABASE_NAME,
        "SHOW CONSTRAINT INFO",
    )
    if constraint_exists(rows, change.constraint):
        await ddl(database, unique_statement("DROP", change.constraint))


# --- the values of an enum -----------------------------------------------------------------------
#
# An enum is stored as the values of its members, wherever it is: a field, a list, in a `TypedDict`
# or an annotated value (a map), or a property of an edge. Changing a value, or moving the values
# off a member, is a change to all of those.


def holds_enum(
    ref: str, descriptor: dict, enum: str, keys: str, depth: int = 0
) -> str | None:
    """A Cypher condition that is true when the value `ref` (of the type `descriptor`) has in it a
    value of `enum` that is one of the `$keys` (their text); None if the type has no such enum"""
    kind = descriptor.get("type")
    if kind == "enum":
        return f"toString({ref}) IN ${keys}" if descriptor["enum"] == enum else None
    if kind == "list":
        inner = holds_enum(f"x{depth}", descriptor["item"], enum, keys, depth + 1)
        return f"any(x{depth} IN {ref} WHERE {inner})" if inner else None
    if kind == "typedDict":
        parts = [
            holds_enum(f"{ref}.{ident(name)}", field, enum, keys, depth + 1)
            for name, field in descriptor["fields"].items()
        ]
        parts = [p for p in parts if p]
        return "(" + " OR ".join(parts) + ")" if parts else None
    return None


def rewrite_enum(
    ref: str, descriptor: dict, enum: str, values: str, depth: int = 0
) -> str | None:
    """A Cypher expression for the value `ref` with the values of `enum` that are keys of the map
    `$values` (by their text) changed to what it says; None if the type has no such enum"""
    kind = descriptor.get("type")
    if kind == "enum":
        if descriptor["enum"] != enum:
            return None
        return f"coalesce(${values}[toString({ref})], {ref})"
    if kind == "list":
        inner = rewrite_enum(f"x{depth}", descriptor["item"], enum, values, depth + 1)
        return f"[x{depth} IN {ref} | {inner}]" if inner else None
    if kind == "typedDict":
        changed = {
            name: rewrite_enum(f"{ref}.{ident(name)}", field, enum, values, depth + 1)
            for name, field in descriptor["fields"].items()
        }
        changed = {
            name: expression for name, expression in changed.items() if expression
        }
        if not changed:
            return None
        # (a key that is not there is left not there)
        built = ref
        for name, expression in changed.items():
            built = (
                f"CASE WHEN {ref}.{ident(name)} IS NULL THEN {built} "
                f"ELSE map.set_key({built}, '{name}', {expression}) END"
            )
        return f"CASE WHEN {ref} IS NULL THEN null ELSE {built} END"
    return None


def enum_holders(state: dict, enum: str) -> list[dict]:
    """Where the values of an enum are stored: the properties of nodes (of a model's label), and the
    properties of the edges of a relation. Each is `{"label", "property", "type"}` (a node) or also
    `"edges": [forward, reverse]` (an edge). A model that has a field of a parent shares it."""
    holders: list[dict] = []
    models = state["models"]

    def descriptors(model: dict) -> list[tuple[str, dict]]:
        found = []
        for entry in model["fields"]:
            if entry["kind"] == "literal":
                found.append((entry["name"], entry["type"]))
            elif entry["kind"] == "list":
                found.append((entry["name"], {"type": "list", "item": entry["item"]}))
            elif entry["kind"] == "annotatedValue":
                extra = {
                    f["name"]: field_descriptor(f)
                    for f in models.get(entry.get("model"), {}).get("fields", [])
                    if f["kind"] in ("literal", "list") and f["name"] != "value"
                }
                found.append(
                    (
                        entry["name"],
                        {
                            "type": "typedDict",
                            "fields": {"value": entry["valueType"], **extra},
                        },
                    )
                )
        return found

    for name, model in models.items():
        if model["kind"] in ("EdgeModel", "AnnotatedValue"):
            continue
        parents = set(model.get("labels", [])) - {name}
        for prop, descriptor in descriptors(model):
            if holds_enum("v", descriptor, enum, "k") is None:
                continue
            inherited = any(
                parent in models and (prop, descriptor) in descriptors(models[parent])
                for parent in parents
            )
            if not inherited:
                holders.append({"label": name, "property": prop, "type": descriptor})
        for entry in model["fields"]:
            if entry["kind"] not in ("relation", "embedded"):
                continue
            edge_models = {
                o.get("edgeModel")
                for o in entry.get("options", [])
                if o.get("edgeModel")
            }
            for edge_model in edge_models:
                for prop, descriptor in descriptors(
                    models.get(edge_model, {"fields": []})
                ):
                    if holds_enum("v", descriptor, enum, "k") is None:
                        continue
                    pairs = edge_pairs(entry)
                    holders.append(
                        {
                            "label": name,
                            "property": prop,
                            "type": descriptor,
                            "edges": [[forward, reverse] for forward, reverse in pairs],
                        }
                    )
    return holders


async def rewrite_enum_values(
    tx: Transaction,
    state: dict,
    enum: str,
    mapping: dict[str, Any],
    refuse: Callable[[str, int], None] | None = None,
    limit: int | None = None,
) -> int:
    """Change the stored values of `enum` that are keys of `mapping` (their text) to what it
    gives, everywhere they are. `refuse(where, count)` is called, before anything is changed, for
    each place that has any: it may raise. With a `limit`, that many at most of each place (what is
    changed no longer has the old value, so a next call finds the next). Returns the most that any
    place had changed."""
    window = f"WITH {{v}} LIMIT {int(limit)} " if limit else ""
    keys = list(mapping)
    holders = enum_holders(state, enum)
    queries: list[tuple[str, str, str]] = []  # (where, count query, change query)
    for holder in holders:
        label, prop, descriptor = (
            ident(holder["label"]),
            ident(holder["property"]),
            holder["type"],
        )
        if "edges" not in holder:
            ref = f"n.{prop}"
            test, new = (
                holds_enum(ref, descriptor, enum, "keys"),
                rewrite_enum(ref, descriptor, enum, "values"),
            )
            where = f"{holder['label']}.{holder['property']}"
            queries.append(
                (
                    where,
                    f"MATCH (n:{label}) WHERE {test} RETURN count(n) AS count",
                    f"MATCH (n:{label}) WHERE {test} {window.format(v='n')}SET {ref} = {new} RETURN count(n) AS done",
                )
            )
        else:
            ref = f"e.{prop}"
            test, new = (
                holds_enum(ref, descriptor, enum, "keys"),
                rewrite_enum(ref, descriptor, enum, "values"),
            )
            forward = [pair[0] for pair in holder["edges"]]
            reverse = [pair[1] for pair in holder["edges"]]
            where = f"the edges of {holder['label']}.{holder['edges'][0][0]} ({prop})"
            queries.append(
                (
                    where,
                    f"MATCH (n:{label})-[e]->() WHERE type(e) IN {forward!r} AND {test} RETURN count(e) AS count",
                    f"MATCH (n:{label})-[e]->() WHERE type(e) IN {forward!r} AND {test} {window.format(v='e')}SET {ref} = {new} RETURN count(e) AS done",
                )
            )
            queries.append(
                (
                    where,
                    f"MATCH ()-[e]->(n:{label}) WHERE type(e) IN {reverse!r} AND {test} RETURN count(e) AS count",
                    f"MATCH ()-[e]->(n:{label}) WHERE type(e) IN {reverse!r} AND {test} {window.format(v='e')}SET {ref} = {new} RETURN count(e) AS done",
                )
            )
    if refuse is not None:
        for where, count_query, _ in queries:
            count = (await run(tx, count_query, keys=keys, values=mapping))[0]["count"]
            if count:
                refuse(where, count)
    done = 0
    for _, _, change_query in queries:
        rows = await run(tx, change_query, keys=keys, values=mapping)
        done = max(done, rows[0]["done"] if rows else 0)
    return done


def member_of(state: dict, enum: str, name: str) -> dict:
    for member in state["enums"].get(enum, {}).get("members", []):
        if member["name"] == name:
            return member
    raise PanglossMigrationError(f"There is no member {enum}.{name} at this point")


async def alter_enum_member_value(
    tx: Transaction,
    change: c.AlterEnumMemberValue,
    state: dict,
    limit: int | None = None,
) -> int:
    """The data that has the old value of a member is given the new (`limit` at a time at most)"""
    if change.old == change.new:
        return 0
    return await rewrite_enum_values(
        tx, state, change.enum, {str(change.old): change.new}, limit=limit
    )


async def remove_enum_member(
    tx: Transaction, change: c.RemoveEnumMember, state: dict, limit: int | None = None
) -> int:
    """Move the values off a member, to those of the member that `replacement` names (`limit` at
    a time at most)"""
    removed = member_of(state, change.enum, change.member)["value"]
    if change.replacement is None:

        def refuse(where: str, count: int) -> None:
            raise PanglossMigrationAnswerNeeded(
                f"{count} {where} have {change.enum}.{change.member}: say which member to give them "
                f"(`replacement`)"
            )

        # (nothing is changed if there are none: so a call again finds none)
        await rewrite_enum_values(
            tx, state, change.enum, {str(removed): removed}, refuse
        )
        return 0
    replacement = member_of(state, change.enum, change.replacement)["value"]
    return await rewrite_enum_values(
        tx, state, change.enum, {str(removed): replacement}, limit=limit
    )


# ---------------------------------------------------------------------------
# Choosing
# ---------------------------------------------------------------------------


async def nothing(tx: Any, change: c.Change, state: dict) -> None:
    """Changes that are of the models, and not of the data"""


async def run_cypher(tx: Transaction, change: c.RunCypher, state: dict) -> None:
    await run_with(tx, change.query, change.parameters)


async def run_python(tx: Transaction, change: c.RunPython, state: dict) -> None:
    try:
        function = change.resolve()
    except (ImportError, AttributeError, ValueError) as error:
        raise PanglossMigrationError(
            f"Cannot find {change.function}: {error}"
        ) from error
    result = function(tx, copy.deepcopy(state))
    if inspect.isawaitable(result):
        await result


def manual(why: str) -> Callable[[Transaction, Any, dict], Awaitable[None]]:
    async def refuse(tx: Transaction, change: c.Change, state: dict) -> None:
        raise PanglossMigrationNotSupported(f"{change.describe()}: {why}")

    return refuse


DATA_HANDLERS: dict[type, Callable[[Transaction, Any, dict], Awaitable[None]]] = {  # ty: ignore[invalid-assignment]
    c.CreateModel: nothing,
    c.DeleteModel: delete_model,
    c.RenameModel: rename_model,
    c.AlterModelLabels: alter_model_labels,
    c.AlterModelOption: nothing,
    c.AlterModelKind: manual("the kind of a model cannot be changed"),
    c.AddField: add_field,
    c.RemoveField: remove_field,
    c.RenameField: rename_field_data,
    c.ChangeFieldKind: manual("the kind of a field cannot be changed"),
    c.AlterLiteralType: alter_literal_type,
    c.AlterListItemType: alter_list_item_type,
    c.AlterNullability: alter_nullability,
    c.LiteralToAnnotatedValue: literal_to_annotated,
    c.AnnotatedValueToLiteral: annotated_to_literal,
    c.AlterAnnotatedValue: nothing,
    c.AlterEmbedded: nothing,
    c.AlterRelationTarget: alter_relation_target,
    c.AlterCardinality: alter_cardinality,
    c.AlterReverseName: alter_reverse_name,
    c.AlterParentFields: alter_parent_fields,
    c.AlterEdgeModel: alter_edge_model,
    c.WrapRelation: wrap_relation,
    c.UnwrapRelation: unwrap_relation,
    c.ChangeWrapper: change_wrapper,
    c.LiteralsToEmbedded: literals_to_embedded,
    c.EmbeddedToLiterals: embedded_to_literals,
    c.RemoveEnumMember: remove_enum_member,
    c.AlterEnumMemberValue: alter_enum_member_value,
    c.RecomputeFulfils: recompute_fulfils,
    c.CreateEnum: nothing,
    c.AddEnumMember: nothing,
    c.RenameEnumMember: nothing,
    c.RenameEnum: nothing,
    c.RemoveEnum: nothing,
    c.RunCypher: run_cypher,
    c.RunPython: run_python,
    c.StateOnly: nothing,
}

DDL_HANDLERS: dict[type, Callable[[Database, Any, dict], Awaitable[None]]] = {
    c.AddIndex: add_index,
    c.RemoveIndex: remove_index,
    c.AddConstraint: add_constraint,
    c.RemoveConstraint: remove_constraint,
}


WINDOWED_HANDLERS: dict[type, Callable[..., Awaitable[list[str] | None]]] = {
    c.AddField: add_field,
    c.RemoveField: remove_field,
    c.RenameField: rename_field_data,
    c.AlterNullability: alter_nullability,
    c.AlterLiteralType: alter_literal_type,
    c.AlterListItemType: alter_list_item_type,
    c.LiteralToAnnotatedValue: literal_to_annotated,
    c.AnnotatedValueToLiteral: annotated_to_literal,
    c.AlterModelLabels: alter_model_labels,
}


def batch_kind(change: c.Change, state: dict) -> str | None:
    """How a change can be made in batches, so that a large one is not a single transaction that
    cannot be resumed: `"window"` (the nodes in the order of their ids, a number at a time),
    `"wrap"` (the relations not yet wrapped, a number at a time), `"edges"` (whatever is left to do,
    found by what is no longer there once it is done, a number at a time: edges to rename or delete,
    wrappers to take off, values to change, nodes to relabel or delete), or None (it is made at once).
    `state` is the snapshot before it."""
    if isinstance(change, c.WrapRelation):
        if change.wrapper_kind == "reifiedRelation":
            return "wrap"
        return "edges" if change.wrapper_kind == "semanticSpace" else None
    if isinstance(change, c.UnwrapRelation):
        return (
            "edges"
            if change.wrapper_kind in ("reifiedRelation", "semanticSpace")
            else None
        )
    if isinstance(change, c.ChangeWrapper):
        return "edges" if change.wrapper_kind == "reifiedRelation" else None
    if isinstance(
        change,
        (
            c.LiteralsToEmbedded,
            c.EmbeddedToLiterals,
            c.RenameModel,
            c.DeleteModel,
            c.AlterReverseName,
            c.AlterEnumMemberValue,
            c.RemoveEnumMember,
            c.RecomputeFulfils,
            c.AlterCardinality,
            c.AlterRelationTarget,
            c.AlterParentFields,
            c.AlterEdgeModel,
        ),
    ):
        return "edges"
    if isinstance(change, c.RenameField):
        field = field_of(state, change.model, change.old)
        return "window" if field["kind"] in SCALAR_PROPERTY_KINDS else "edges"
    if type(change) not in WINDOWED_HANDLERS:
        return None
    if isinstance(change, c.RemoveField):
        if change.absorbed:
            return None
        field = field_of(state, change.model, change.name)
        return "window" if field["kind"] in SCALAR_PROPERTY_KINDS else "edges"
    if isinstance(change, c.AddField):
        field = change.definition
        if field["kind"] == "embedded" and not change.from_narrowing:
            return "edges"
        scalar = field["kind"] in SCALAR_PROPERTY_KINDS
        return (
            "window"
            if scalar and change.needs_value and not change.from_narrowing
            else None
        )
    if isinstance(change, c.AlterNullability):
        return None if change.nullable else "window"
    return "window"


async def apply_window(
    tx: Transaction, change: c.Change, state: dict, window: Window
) -> list[str]:
    """One batch of a change that `batch_kind` calls a window: the ids of the nodes it was for"""
    return await WINDOWED_HANDLERS[type(change)](tx, change, state, window) or []


def is_ddl(change: c.Change) -> bool:
    """Whether a change is to the database itself (an index, a constraint), made outside a transaction"""
    return type(change) in DDL_HANDLERS


async def apply_change(tx: Transaction, change: c.Change, state: dict) -> None:
    """Make a change to the data, in a transaction. `state` is the snapshot before the change."""
    handler = DATA_HANDLERS.get(type(change))
    if handler is None:
        raise PanglossMigrationNotSupported(
            f"{type(change).__name__} cannot be applied"
        )
    await handler(tx, change, state)


async def run_ddl(database: Database, change: c.Change, state: dict) -> None:
    """Make a change to the database itself. Not in a transaction; and safe to repeat."""
    await DDL_HANDLERS[type(change)](database, change, state)
