"""What each change does to a Memgraph database.

`apply_change(tx, change, state)` makes a change to the data, in the transaction `tx`.
`state` is the snapshot of the models *before* the change (see
`pangloss_models.migrations.state`): it says the labels of a model and how a field is stored,
so nothing here needs the classes of the models, which may have changed since.

Changes are written for a model and a field, and select by label (`MATCH (n:Statement)`), so
that one change is made wherever the model is used: subclasses carry the label of their
parents, and a nested model is found without knowing what it is nested in.

Enums are changed outside of a transaction (`run_ddl`), as Memgraph requires; see
`docs/migrations.md` 5.6.
"""

import copy
import dataclasses
import inspect
import re
import uuid
from contextvars import ContextVar
from collections.abc import Awaitable, Callable
from typing import Any

import neo4j
from pangloss_models.exceptions import (
    PanglossMigrationAnswerNeeded,
    PanglossMigrationError,
    PanglossMigrationNotSupported,
)
from pangloss_models.migrations import changes as c
from pangloss_models.migrations.state import rename_field
from pangloss_models.migrations.state import rename_model as state_after_rename

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
        raise PanglossMigrationError(f"There is no model {name} at this point") from None


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
COUNTERS: ContextVar[dict[str, int] | None] = ContextVar("migration_counters", default=None)
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


async def run_with(tx: Transaction, query: str, params: dict[str, Any]) -> list[dict[str, Any]]:
    """`run`, with the parameters as a dict (a name may be `query`, which the driver's `run` takes)"""
    try:
        result = await tx.run(query, params)  # type: ignore[arg-type]
        rows = await result.data()
        counters = COUNTERS.get()
        if counters is not None:
            summary = await result.consume()
            for name in COUNTED:
                counters[name] = counters.get(name, 0) + getattr(summary.counters, name, 0)
        return rows
    except neo4j.exceptions.Neo4jError as error:
        raise PanglossMigrationError(f"{error.message}\nin: {' '.join(query.split())}") from error


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
    rows = await run(tx, f"{statement} RETURN n.id AS id", **{**params, **window.params})
    return [row["id"] for row in rows]


def needs(change: c.Change, value: Any, what: str) -> None:
    if value is None:
        raise PanglossMigrationAnswerNeeded(f"{change.describe()}: {what}")


def literal_expression(
    value: Any, descriptor: dict, params: dict[str, Any], name: str, enums: dict[str, dict]
) -> str:
    """The expression for a value of a type, with what it needs in `params`"""
    kind = descriptor["type"]
    if kind == "enum":
        enum = enums.get(descriptor["enum"], {})
        members = enum.get("members", [])
        member = next(
            (m["name"] for m in members if m["name"] == value or m["value"] == value), None
        )
        if member is None:
            raise PanglossMigrationError(
                f"{value!r} is not a member of the enum {descriptor['enum']}"
            )
        params[f"{name}_enum"] = descriptor["enum"]
        params[f"{name}_member"] = member
        return f"ToEnum(${name}_enum, ${name}_member)"
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


async def rename_model(tx: Transaction, change: c.RenameModel, state: dict) -> None:
    old, new = ident(change.old), ident(change.new)
    await run(tx, f"MATCH (n:{old}) REMOVE n:{old} SET n:{new}")
    await run(tx, f"MATCH (n:{new}) WHERE n.type = $old SET n.type = $new", old=change.old, new=change.new)
    await run(
        tx,
        "MATCH (n) WHERE n.head_node_type = $old SET n.head_node_type = $new",
        old=change.old,
        new=change.new,
    )
    # the context of what a renamed document holds has its name in it
    heads = await run(
        tx,
        f"MATCH (n:{new}) WHERE n:Document OR n:SemanticSpace "
        "RETURN DISTINCT coalesce(n.head_node_id, n.id) AS head",
    )
    if heads:
        await recompute_contexts(
            tx, [row["head"] for row in heads], state_after_rename(state, change.old, change.new)
        )


async def delete_model(tx: Transaction, change: c.DeleteModel, state: dict) -> None:
    model = ident(change.model)
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
    await run(tx, f"MATCH (h:{model}:HeadNode) MATCH (x) WHERE x.head_node_id = h.id DETACH DELETE x")
    await run(tx, f"MATCH (n:{model}) DETACH DELETE n")


async def alter_model_labels(
    tx: Transaction, change: c.AlterModelLabels, state: dict, window: Window | None = None
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
        raise PanglossMigrationNotSupported(
            f"{change.describe()}: a node would be needed for each that exists; write it by hand"
        )
    if field["kind"] not in SCALAR_PROPERTY_KINDS or not change.needs_value:
        return None if window is None else []  # (an absent property is none; a relation is empty)
    if field["kind"] == "list" and change.default is None:
        change = dataclasses.replace(change, default=[])  # (a list that is needed starts empty)
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
        select_nodes(ident(change.model), f"{prop} IS NULL", window) + f" SET {prop} = {expression}",
        **params,
    )


async def delete_relation(
    tx: Transaction, model: str, field: dict, only_pairs: list[tuple[str, str]] | None = None
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


async def remove_field(
    tx: Transaction, change: c.RemoveField, state: dict, window: Window | None = None
) -> list[str] | None:
    if change.absorbed:
        return None  # (its edges are written by the field that narrows it now)
    field = field_of(state, change.model, change.name)
    if field["kind"] in SCALAR_PROPERTY_KINDS:
        prop = f"n.{ident(change.name)}"
        return await run_on_nodes(
            tx, window, select_nodes(ident(change.model), f"{prop} IS NOT NULL", window) + f" REMOVE {prop}"
        )
    await delete_relation(tx, change.model, field)
    return None


async def rename_edge_type(tx: Transaction, model: str, old: str, new: str, reverse: bool) -> None:
    """Edge types are replaced, not changed: a new edge with the properties of the old"""
    label = ident(model)
    if not reverse:
        pattern = f"(a:{label})-[e:{ident(old)}]->(b)"
        guard = "WHERE NOT coalesce(e.reverse, false)"
    else:
        pattern = f"(a)-[e:{ident(old)}]->(b:{label})"
        guard = "WHERE coalesce(e.reverse, false)"
    await run(
        tx,
        f"MATCH {pattern} {guard} CREATE (a)-[n:{ident(new)}]->(b) SET n = properties(e) DELETE e",
    )


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
    renamed = field_of(rename_field(state, change.model, change.old, change.new), change.model, change.new)
    (old_forward, old_reverse), (new_forward, new_reverse) = edge_pairs(field)[0], edge_pairs(renamed)[0]
    if old_forward != new_forward:
        await rename_edge_type(tx, change.model, old_forward, new_forward, reverse=False)
    if old_reverse != new_reverse:
        await rename_edge_type(tx, change.model, old_reverse, new_reverse, reverse=True)
    return None


async def alter_nullability(
    tx: Transaction, change: c.AlterNullability, state: dict, window: Window | None = None
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
        select_nodes(ident(change.model), f"{prop} IS NULL", window) + f" SET {prop} = {expression}",
        **params,
    )


async def alter_literal_type(
    tx: Transaction, change: c.AlterLiteralType, state: dict, window: Window | None = None
) -> list[str] | None:
    return await convert_property(tx, change, state, change.old, change.new, False, window)


async def alter_list_item_type(
    tx: Transaction, change: c.AlterListItemType, state: dict, window: Window | None = None
) -> list[str] | None:
    return await convert_property(tx, change, state, change.old, change.new, True, window)


async def convert_property(
    tx, change, state, old: dict, new: dict, is_list: bool, window: Window | None = None
) -> list[str] | None:
    """Convert the values of a field to another type. What does not convert is dealt with as
    `on_failure` says; by default that is to fail, and **before anything is changed** (a count of
    what would fail, once, before the first batch)."""
    label, prop = ident(change.model), f"n.{ident(change.name)}"
    ref = "x" if is_list else prop
    expression, params = convert_expression(old, new, ref, state["enums"], change.mapping)
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
            needs(change, change.default, "the value to give what does not convert (`default`)")

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
    tx: Transaction, change: c.LiteralToAnnotatedValue, state: dict, window: Window | None = None
) -> list[str] | None:
    annotated = model_of(state, change.annotated_model) if change.annotated_model in state["models"] else None
    extras = {
        f["name"]: f for f in (annotated or {"fields": []})["fields"] if f["name"] != "value"
    }
    defaults = change.defaults or {}
    missing = [name for name, f in extras.items() if not f.get("nullable") and name not in defaults]
    if missing:
        raise PanglossMigrationAnswerNeeded(
            f"{change.describe()}: values for the extra fields {', '.join(missing)} (`defaults`)"
        )
    prop = f"n.{ident(change.name)}"
    params: dict[str, Any] = {}
    parts = ["value: " + prop]
    for name, value in defaults.items():
        parts.append(f"{ident(name)}: {literal_expression(value, field_descriptor(extras[name]), params, 'extra_' + name, state['enums'])}")
    return await run_on_nodes(
        tx,
        window,
        select_nodes(ident(change.model), f"{prop} IS NOT NULL", window)
        + f" SET {prop} = {{{', '.join(parts)}}}",
        **params,
    )


async def annotated_to_literal(
    tx: Transaction, change: c.AnnotatedValueToLiteral, state: dict, window: Window | None = None
) -> list[str] | None:
    prop = f"n.{ident(change.name)}"
    return await run_on_nodes(
        tx,
        window,
        select_nodes(ident(change.model), f"{prop} IS NOT NULL", window) + f" SET {prop} = {prop}.value",
    )


# ---------------------------------------------------------------------------
# Relations
# ---------------------------------------------------------------------------


async def alter_cardinality(tx: Transaction, change: c.AlterCardinality, state: dict) -> None:
    if change.many:
        return
    field = field_of(state, change.model, change.name)
    if owns_nodes(field):
        raise PanglossMigrationNotSupported(
            f"{change.describe()}: the extra nodes would have to be deleted; write it by hand"
        )
    pairs = edge_pairs(field)
    (forward, reverse), others = pairs[0], pairs[1:]
    label = ident(change.model)
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
    if not several:
        return
    if change.keep != "first":
        raise PanglossMigrationAnswerNeeded(
            f"{several} nodes have several {change.model}.{change.name}: say which to keep "
            f"(`keep`: 'first')"
        )
    # keep the first edge (the oldest), and remove the others with their reverse edges
    await run(
        tx,
        f"""
        MATCH (n:{label})-[e]->(t) WHERE type(e) = $forward AND NOT coalesce(e.reverse, false)
        WITH n, e, t ORDER BY id(e)
        WITH n, collect({{e: e, t: t}}) AS edges WHERE size(edges) > 1
        UNWIND edges[1..] AS extra
        WITH n, extra.e AS e, extra.t AS t
        OPTIONAL MATCH (t)-[r]->(n) WHERE type(r) = $reverse AND coalesce(r.reverse, false)
        DELETE e, r
        """,
        forward=forward,
        reverse=reverse,
    )
    for other_forward, other_reverse in others:
        # (the pairs of the parent fields go to the same target)
        await run(
            tx,
            f"""
            MATCH (n:{label})-[e]->(t)
            WHERE type(e) = $other AND NOT coalesce(e.reverse, false) AND NOT (n)-[:{ident(forward)}]->(t)
            OPTIONAL MATCH (t)-[r]->(n) WHERE type(r) = $other_reverse AND coalesce(r.reverse, false)
            DELETE e, r
            """,
            other=other_forward,
            other_reverse=other_reverse,
        )


def allowed_labels(options: list[dict]) -> list[str]:
    """The labels a target can have, for options that are direct"""
    return sorted({o["type"] for o in options if o["kind"] in DIRECT_KINDS | {
        "reifiedRelation", "reifiedRelationDocument", "semanticSpace", "conjunction"}})


async def alter_relation_target(tx: Transaction, change: c.AlterRelationTarget, state: dict) -> None:
    if not change.removed:
        return
    field = field_of(state, change.model, change.name)
    allowed = allowed_labels(change.options)
    forward, reverse = edge_pairs(field)[0]
    label = ident(change.model)
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
    if not violations:
        return
    if change.on_narrowing != "remove":
        raise PanglossMigrationAnswerNeeded(
            f"{violations} relations {change.model}.{change.name} are to what it can no longer be "
            f"to: say what to do (`on_narrowing`: 'remove')"
        )
    if owns_nodes(field):
        raise PanglossMigrationNotSupported(
            f"{change.describe()}: nodes that belong to the document would be left; write it by hand"
        )
    for pair_forward, pair_reverse in edge_pairs(field):
        await run(
            tx,
            f"""
            MATCH (n:{label})-[e]->(t) WHERE type(e) = $forward AND NOT coalesce(e.reverse, false)
              AND NOT any(l IN labels(t) WHERE l IN $allowed)
            OPTIONAL MATCH (t)-[r]->(n) WHERE type(r) = $reverse AND coalesce(r.reverse, false)
            DELETE e, r
            """,
            forward=pair_forward,
            reverse=pair_reverse,
            allowed=allowed,
        )


async def alter_reverse_name(tx: Transaction, change: c.AlterReverseName, state: dict) -> None:
    field = field_of(state, change.model, change.name)
    old = edge_pairs(field)[0][1]
    if old != change.new:
        await rename_edge_type(tx, change.model, old, change.new, reverse=True)


async def alter_parent_fields(tx: Transaction, change: c.AlterParentFields, state: dict) -> None:
    field = field_of(state, change.model, change.name)
    forward, reverse = edge_pairs(field)[0]
    label = ident(change.model)
    new_reverse = {name: rev or f"{name}_reverse" for name, rev in change.edges}
    for parent in change.added:
        parent_reverse = new_reverse[parent]
        await run(
            tx,
            f"""
            MATCH (n:{label})-[e:{ident(forward)}]->(t)
            WHERE NOT coalesce(e.reverse, false) AND NOT (n)-[:{ident(parent)}]->(t)
            CREATE (n)-[f:{ident(parent)}]->(t) SET f = properties(e)
            WITH n, t
            MATCH (t)-[r:{ident(reverse)}]->(n) WHERE coalesce(r.reverse, false)
            CREATE (t)-[g:{ident(parent_reverse)}]->(n) SET g = properties(r)
            """,
        )
    old_reverse = {name: rev for name, rev in edge_pairs(field)}
    removed_pairs = [(name, old_reverse[name]) for name in change.removed if name in old_reverse]
    if removed_pairs:
        await delete_relation(tx, change.model, field, only_pairs=removed_pairs)


def edge_model_properties(state: dict, options: list[dict]) -> dict[str, dict]:
    """The fields of the edge model of the options, by name"""
    names = sorted({o["edgeModel"] for o in options if o.get("edgeModel")})
    properties: dict[str, dict] = {}
    for name in names:
        for entry in model_of(state, name)["fields"]:
            properties[entry["name"]] = entry
    return properties


async def alter_edge_model(tx: Transaction, change: c.AlterEdgeModel, state: dict) -> None:
    field = field_of(state, change.model, change.name)
    old = edge_model_properties(state, field["options"])
    new = edge_model_properties(state, change.options)
    pairs = edge_pairs(field)
    label = ident(change.model)

    gone = [name for name in old if name not in new]
    for name in gone:
        for forward, reverse in pairs:
            await run(
                tx,
                f"MATCH (n:{label})-[e:{ident(forward)}]->() REMOVE e.{ident(name)}",
            )
            await run(
                tx,
                f"MATCH ()-[e:{ident(reverse)}]->(n:{label}) REMOVE e.{ident(name)}",
            )

    added = {name: entry for name, entry in new.items() if name not in old}
    defaults = change.defaults or {}
    missing = [n for n, e in added.items() if not e.get("nullable") and n not in defaults]
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
            await run(
                tx,
                f"MATCH (n:{label})-[e:{ident(forward)}]->() WHERE NOT coalesce(e.reverse, false) "
                f"SET e.{ident(name)} = {expression}",
                **params,
            )
            await run(
                tx,
                f"MATCH ()-[e:{ident(reverse)}]->(n:{label}) WHERE coalesce(e.reverse, false) "
                f"SET e.{ident(name)} = {expression}",
                **params,
            )


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
        name: model.get("useInSemanticSpaceLabel", True) for name, model in state["models"].items()
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


def wrapper_properties(change: c.WrapRelation, state: dict) -> tuple[str, dict[str, Any]]:
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
                defaults[name], field_descriptor(entry), params, f"wrapper_{name}", state["enums"]
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


async def wrap_relation(tx: Transaction, change: c.WrapRelation, state: dict) -> None:
    if change.wrapper_kind == "semanticSpace":
        return await wrap_in_semantic_space(tx, change, state)
    if change.wrapper_kind != "reifiedRelation":
        raise PanglossMigrationNotSupported(
            f"{change.describe()}: a relation cannot be wrapped in a {change.wrapper_kind} "
            f"(it has several slots to fill): write it by hand"
        )
    await wrap_reified(tx, change, state, limit=None)


async def wrap_reified(tx: Transaction, change: c.WrapRelation, state: dict, limit: int | None) -> int:
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
    not_narrowed = "".join(f" AND NOT (s)-[:{ident(n)}]->(p)" for n in narrowers_of(state, primary))
    pairs_to_wrap = f"""
        MATCH (s:{model})-[e]->(p)
        WHERE type(e) = $primary AND NOT coalesce(e.reverse, false) AND NOT p:{wrapper_label}{not_narrowed}
        {"WITH s, p ORDER BY s.id, p.id LIMIT $limit" if limit else ""}
    """

    count = (
        await run(tx, f"{pairs_to_wrap} RETURN count(*) AS count", primary=primary, limit=limit)
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
            meta: new_meta{', ' + assignments if assignments else ''}
        }})
        {' '.join(new_edges)}
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


async def unwrap_relation(tx: Transaction, change: c.UnwrapRelation, state: dict) -> None:
    if change.wrapper_kind == "semanticSpace":
        return await unwrap_semantic_space(tx, change, state)
    if change.wrapper_kind != "reifiedRelation":
        raise PanglossMigrationNotSupported(
            f"{change.describe()}: unwrapping a {change.wrapper_kind} is not supported: "
            f"write it by hand"
        )
    field = field_of(state, change.model, change.name)
    pairs = edge_pairs(field)
    primary = pairs[0][0]
    model, wrapper_label = ident(change.model), ident(change.wrapper)

    not_narrowed = "".join(f" AND NOT (s)-[:{ident(n)}]->(r)" for n in narrowers_of(state, primary))
    creates = []
    for forward, reverse in pairs:
        creates.append(f"MERGE (s)-[:{ident(forward)}]->(p)")
        creates.append(f"MERGE (p)-[:{ident(reverse)} {{reverse: true}}]->(s)")
    await run(
        tx,
        f"""
        MATCH (s:{model})-[e]->(r:{wrapper_label})-[:target]->(p)
        WHERE type(e) = $primary AND NOT coalesce(e.reverse, false){not_narrowed}
        {' '.join(creates)}
        """,
        primary=primary,
    )
    # the node between, with the edges to it and from it (that the relations just unwrapped had)
    await run(
        tx,
        f"""
        MATCH (s:{model})-[e]->(r:{wrapper_label})
        WHERE type(e) = $primary AND NOT coalesce(e.reverse, false){not_narrowed}
        DETACH DELETE r
        """,
        primary=primary,
    )


# ---------------------------------------------------------------------------
# Semantic spaces, and the context that nodes are in
# ---------------------------------------------------------------------------


def propagate_context(
    node_id: str,
    nodes: dict[str, dict],
    children: dict[str, dict[str, list[str]]],
    state: dict,
    in_context: dict[str, bool],
    spaces: list[str],
    labels: list[dict],
    parent: str | None,
    out: dict[str, tuple[list[str], list[dict]]],
) -> None:
    """The semantic spaces and context labels of a node and what is below it, as the models give
    them when they write a document (`recursively_propagate_context_types`, which this follows
    closely, including that what a single relation holds shares the lists of the node and a
    list's items are given copies): a node is in the spaces above it; a space adds itself to the
    context; and a document nested in another is a part of the context of what it holds (in the
    innermost space, or in a root context). Only relations are followed, not embedded objects."""
    node = nodes[node_id]
    node_labels = node["labels"]
    is_space = "SemanticSpace" in node_labels
    if not is_space:
        out[node_id] = ([*spaces], [*labels])
    if is_space:
        spaces.append(node["type"])
        labels.append({"type": node["type"]})
    elif parent is not None and "Document" in node_labels and in_context.get(node["type"], True):
        entry = {"type": node["type"], "id": node_id}
        if labels:
            labels[-1].setdefault("contents", []).append(entry)
        else:
            labels.append({"type": "#rootcontext", "contents": [entry]})

    model = state["models"].get(node["type"], {})
    for entry in model.get("fields", []):
        if entry["kind"] != "relation":
            continue
        forward = edge_pairs(entry)[0][0]
        for child in children.get(node_id, {}).get(forward, []):
            if entry["many"]:
                propagate_context(
                    child, nodes, children, state, in_context,
                    [*spaces], copy.deepcopy(labels), node_id, out,
                )
            else:
                propagate_context(
                    child, nodes, children, state, in_context, spaces, labels, node_id, out
                )


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
            siblings = children.setdefault(edge["source"], {}).setdefault(edge["type"], [])
            if edge["target"] not in siblings:  # (parallel edges: a field that narrows another)
                siblings.append(edge["target"])
        if head_id not in nodes:
            continue
        computed: dict[str, tuple[list[str], list[dict]]] = {}
        propagate_context(head_id, nodes, children, state, in_context, [], [], None, computed)

        updates = []
        for node_id, (spaces, labels) in computed.items():
            meta = nodes[node_id]["meta"]
            if node_id == head_id or meta is None:
                continue  # (a head node has no `meta`)
            updates.append(
                {"id": node_id, "meta": {**meta, "semantic_spaces": spaces, "context_labels": labels}}
            )
        if updates:
            await run(
                tx,
                "UNWIND $updates AS u MATCH (n {id: u.id}) SET n.meta = u.meta",
                updates=updates,
            )


async def wrap_in_semantic_space(tx: Transaction, change: c.WrapRelation, state: dict) -> None:
    """A node for the space on each edge, between the node and what it holds (which is then in the
    space, as is everything below it)"""
    field = field_of(state, change.model, change.name)
    space_model = model_of(state, change.wrapper)
    pairs = edge_pairs(field)
    primary = pairs[0][0]
    contents_forward, contents_reverse = edge_pairs(field_of(state, change.wrapper, "contents"))[0]
    model, space_label = ident(change.model), ident(change.wrapper)
    labels = "".join(":" + ident(label) for label in [*space_model["labels"], "PGIndexableNode"])
    not_narrowed = "".join(f" AND NOT (s)-[:{ident(n)}]->(p)" for n in narrowers_of(state, primary))

    match = f"""
        MATCH (s:{model})-[e]->(p)
        WHERE type(e) = $primary AND NOT coalesce(e.reverse, false) AND NOT p:{space_label}{not_narrowed}
    """
    count = (await run(tx, match + " RETURN count(*) AS count", primary=primary))[0]["count"]
    if not count:
        return
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
        {' '.join(new_edges)}
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


async def unwrap_semantic_space(tx: Transaction, change: c.UnwrapRelation, state: dict) -> None:
    field = field_of(state, change.model, change.name)
    pairs = edge_pairs(field)
    primary = pairs[0][0]
    contents_forward = edge_pairs(field_of(state, change.wrapper, "contents"))[0][0]
    model, space_label = ident(change.model), ident(change.wrapper)
    not_narrowed = "".join(f" AND NOT (s)-[:{ident(n)}]->(r)" for n in narrowers_of(state, primary))
    creates = []
    for forward, reverse in pairs:
        creates.append(f"MERGE (s)-[:{ident(forward)}]->(p)")
        creates.append(f"MERGE (p)-[:{ident(reverse)} {{reverse: true}}]->(s)")
    heads = await run(
        tx,
        f"""
        MATCH (s:{model})-[e]->(r:{space_label})-[:{ident(contents_forward)}]->(p)
        WHERE type(e) = $primary AND NOT coalesce(e.reverse, false){not_narrowed}
        {' '.join(creates)}
        RETURN DISTINCT coalesce(s.head_node_id, s.id) AS head
        """,
        primary=primary,
    )
    await run(
        tx,
        f"""
        MATCH (s:{model})-[e]->(r:{space_label})
        WHERE type(e) = $primary AND NOT coalesce(e.reverse, false){not_narrowed}
        DETACH DELETE r
        """,
        primary=primary,
    )
    await recompute_contexts(tx, [row["head"] for row in heads], state)


# ---------------------------------------------------------------------------
# One wrapper for another, and literals in a node of their own
# ---------------------------------------------------------------------------


async def change_wrapper(tx: Transaction, change: c.ChangeWrapper, state: dict) -> None:
    if change.wrapper_kind != "reifiedRelation":
        raise PanglossMigrationNotSupported(
            f"{change.describe()}: only reified relations are supported: write it by hand"
        )
    old, new = model_of(state, change.old_wrapper), model_of(state, change.new_wrapper)
    field = field_of(state, change.model, change.name)
    primary = edge_pairs(field)[0][0]
    model, old_label = ident(change.model), ident(change.old_wrapper)

    old_props = {f["name"] for f in old["fields"] if f["kind"] in ("literal", "list")}
    new_literals = {f["name"]: f for f in new["fields"] if f["kind"] in ("literal", "list")}
    defaults = change.defaults or {}
    missing = [n for n, f in new_literals.items() if n not in old_props and not f.get("nullable") and n not in defaults]
    if missing:
        raise PanglossMigrationAnswerNeeded(
            f"{change.describe()}: values for {', '.join(missing)} of {change.new_wrapper} (`defaults`)"
        )
    params: dict[str, Any] = {}
    sets = []
    for name, value in defaults.items():
        if name in new_literals and name not in old_props:
            expression = literal_expression(
                value, field_descriptor(new_literals[name]), params, f"wrapper_{name}", state["enums"]
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
    clauses.append("SET r.type = $new_type" + "".join(", " + assignment for assignment in sets))
    if removes:
        clauses.append("REMOVE " + ", ".join(removes))
    await run(
        tx,
        f"""
        MATCH (s:{model})-[e]->(r:{old_label})
        WHERE type(e) = $primary AND NOT coalesce(e.reverse, false)
        {' '.join(clauses)}
        """,
        primary=primary,
        new_type=change.new_wrapper,
        **params,
    )


def embedded_node_clauses(state: dict, embedded_model: str) -> tuple[str, dict[str, Any]]:
    model = model_of(state, embedded_model)
    return "".join(":" + ident(label) for label in [*model["labels"], "PGIndexableNode"]), {}


async def literals_to_embedded(tx: Transaction, change: c.LiteralsToEmbedded, state: dict) -> None:
    """A node of the embedded object on each node that has the fields, with the values moved
    into it"""
    embedded_name = change.embedded_type or change.embedded_model
    embedded = model_of(state, embedded_name)
    own = {f["name"]: f for f in embedded["fields"]}
    required_elsewhere = [n for n, f in own.items() if n not in change.fields and not f.get("nullable") and f["kind"] in ("literal", "list")]
    defaults = change.defaults or {}
    missing = [n for n in required_elsewhere if n not in defaults]
    if missing:
        raise PanglossMigrationAnswerNeeded(
            f"{change.describe()}: values for {', '.join(missing)} of {embedded_name} (`defaults`)"
        )
    forward, reverse = edge_pairs(change.definition)[0]
    labels = "".join(":" + ident(label) for label in [*embedded["labels"], "PGIndexableNode"])
    model = ident(change.model)
    holds = " OR ".join(f"s.{ident(f)} IS NOT NULL" for f in change.fields)
    move = ", ".join(f"{ident(f)}: s.{ident(f)}" for f in change.fields)
    params: dict[str, Any] = {}
    extra = []
    for name, value in defaults.items():
        if name in own:
            extra.append(
                f"{ident(name)}: "
                + literal_expression(value, field_descriptor(own[name]), params, f"default_{name}", state["enums"])
            )

    match = f"""
        MATCH (s:{model})
        WHERE ({holds}) AND NOT (s)-[:{ident(forward)}]->(:Embedded)
    """
    count = (await run(tx, match + " RETURN count(*) AS count"))[0]["count"]
    if not count:
        return
    ids = [str(uuid.uuid7()) for _ in range(count)]
    heads = await run(
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
                    semantic_spaces: [], context_labels: null}},
            {move}{', ' + ', '.join(extra) if extra else ''}
        }})
        CREATE (s)-[:{ident(forward)}]->(e)
        CREATE (e)-[:{ident(reverse)} {{reverse: true}}]->(s)
        REMOVE {', '.join(f"s.{ident(f)}" for f in change.fields)}
        RETURN DISTINCT coalesce(s.head_node_id, s.id) AS head
        """,
        ids=ids,
        embedded_type=embedded_name,
        labels_in_context=labels_in_context(state),
        **params,
    )


async def embedded_to_literals(tx: Transaction, change: c.EmbeddedToLiterals, state: dict) -> None:
    field = field_of(state, change.model, change.name)
    forward, reverse = edge_pairs(field)[0]
    model = ident(change.model)
    moves = ", ".join(f"s.{ident(f)} = e.{ident(f)}" for f in change.fields)
    await run(
        tx,
        f"""
        MATCH (s:{model})-[x:{ident(forward)}]->(e) WHERE NOT coalesce(x.reverse, false)
        SET {moves}
        """,
    )
    await delete_relation(tx, change.model, field)


# ---------------------------------------------------------------------------
# Enums (outside of a transaction)
# ---------------------------------------------------------------------------


async def existing_enums(database: Database) -> dict[str, list[str]]:
    rows = await run_statement(
        database.driver, database.settings.DATABASE.DATABASE_NAME, "SHOW ENUMS"
    )
    return {row["Enum Name"]: row["Enum Values"] for row in rows}


async def ddl(database: Database, statement: str) -> None:
    await run_statement(database.driver, database.settings.DATABASE.DATABASE_NAME, statement)


async def create_enum(database: Database, change: c.CreateEnum, state: dict) -> None:
    present = await existing_enums(database)
    names = change.members
    if change.enum not in present:
        await ddl(
            database,
            f"CREATE ENUM {ident(change.enum)} VALUES {{ {', '.join(ident(n) for n in names)} }}",
        )
        return
    # (it may be there already: made by an earlier run, or by `initialise_database`)
    for name in names:
        if name not in present[change.enum]:
            await ddl(database, f"ALTER ENUM {ident(change.enum)} ADD VALUE {ident(name)}")


async def add_enum_member(database: Database, change: c.AddEnumMember, state: dict) -> None:
    present = await existing_enums(database)
    if change.member not in present.get(change.enum, []):
        await ddl(database, f"ALTER ENUM {ident(change.enum)} ADD VALUE {ident(change.member)}")


async def rename_enum_member(database: Database, change: c.RenameEnumMember, state: dict) -> None:
    present = await existing_enums(database)
    members = present.get(change.enum, [])
    if change.old in members and change.new not in members:
        await ddl(
            database,
            f"ALTER ENUM {ident(change.enum)} UPDATE VALUE {ident(change.old)} TO {ident(change.new)}",
        )
    elif change.old in members and change.new in members:
        raise PanglossMigrationError(
            f"Both {change.enum}.{change.old} and {change.enum}.{change.new} are in the database"
        )


async def rename_enum(database: Database, change: c.RenameEnum, state: dict) -> None:
    """A new enum (Memgraph cannot rename one) with the members of the old, and the values
    that use the old converted. The old stays in the database."""
    old = state["enums"].get(change.old)
    if old is None:
        raise PanglossMigrationError(f"There is no enum {change.old} at this point")
    await create_enum(
        database,
        c.CreateEnum(enum=change.new, definition={**old, "name": change.new}),
        state,
    )
    old_type, new_type = {"type": "enum", "enum": change.old}, {"type": "enum", "enum": change.new}

    async def convert(tx: Transaction) -> None:
        for model_name, model in state["models"].items():
            for entry in model["fields"]:
                if entry["kind"] == "literal" and entry["type"] == old_type:
                    synthetic = c.AlterLiteralType(
                        model=model_name, name=entry["name"], old=old_type, new=new_type
                    )
                    await convert_property(tx, synthetic, state, old_type, new_type, is_list=False)
                elif entry["kind"] == "list" and entry["item"] == old_type:
                    synthetic_list = c.AlterListItemType(
                        model=model_name, name=entry["name"], old=old_type, new=new_type
                    )
                    await convert_property(tx, synthetic_list, state, old_type, new_type, is_list=True)

    async with database.driver.session(database=database.settings.DATABASE.DATABASE_NAME) as session:
        await session.execute_write(convert)


async def remove_enum_member(tx: Transaction, change: c.RemoveEnumMember, state: dict) -> None:
    """Move the values off a member (it stays in the database enum)"""
    enum_type = {"type": "enum", "enum": change.enum}
    for model_name, model in state["models"].items():
        for entry in model["fields"]:
            uses = (entry["kind"] == "literal" and entry["type"] == enum_type) or (
                entry["kind"] == "list" and entry["item"] == enum_type
            )
            if not uses:
                continue
            if model["kind"] in ("EdgeModel", "AnnotatedValue"):
                raise PanglossMigrationNotSupported(
                    f"{change.describe()}: {model_name}.{entry['name']} is stored on an "
                    f"{model['kind']}; write it by hand"
                )
            prop = f"n.{ident(entry['name'])}"
            label = ident(model_name)
            member = "ToEnum($enum, $member)"
            if entry["kind"] == "literal":
                holds, replace = f"{prop} = {member}", None
            else:
                holds, replace = f"{member} IN {prop}", None
            count = (
                await run(
                    tx,
                    f"MATCH (n:{label}) WHERE {holds} RETURN count(n) AS count",
                    enum=change.enum,
                    member=change.member,
                )
            )[0]["count"]
            if not count:
                continue
            if change.replacement is None:
                raise PanglossMigrationAnswerNeeded(
                    f"{count} {model_name}.{entry['name']} have {change.enum}.{change.member}: say "
                    f"which member to give them (`replacement`)"
                )
            replacement = "ToEnum($enum, $replacement)"
            if entry["kind"] == "literal":
                await run(
                    tx,
                    f"MATCH (n:{label}) WHERE {holds} SET {prop} = {replacement}",
                    enum=change.enum,
                    member=change.member,
                    replacement=change.replacement,
                )
            else:
                await run(
                    tx,
                    f"MATCH (n:{label}) WHERE {holds} "
                    f"SET {prop} = [x IN {prop} | CASE WHEN x = {member} THEN {replacement} ELSE x END]",
                    enum=change.enum,
                    member=change.member,
                    replacement=change.replacement,
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
        raise PanglossMigrationError(f"Cannot find {change.function}: {error}") from error
    result = function(tx, copy.deepcopy(state))
    if inspect.isawaitable(result):
        await result


def manual(why: str) -> Callable[[Transaction, Any, dict], Awaitable[None]]:
    async def refuse(tx: Transaction, change: c.Change, state: dict) -> None:
        raise PanglossMigrationNotSupported(f"{change.describe()}: {why}")

    return refuse


DATA_HANDLERS: dict[type, Callable[[Transaction, Any, dict], Awaitable[None]]] = {
    c.CreateModel: nothing,
    c.DeleteModel: delete_model,
    c.RenameModel: rename_model,
    c.AlterModelLabels: alter_model_labels,
    c.AlterModelOption: nothing,
    c.AlterModelKind: manual("a Document and an Entity are stored differently; write it by hand"),
    c.AddField: add_field,
    c.RemoveField: remove_field,
    c.RenameField: rename_field_data,
    c.ChangeFieldKind: manual("write it by hand"),
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
    c.RemoveEnum: nothing,
    c.RunCypher: run_cypher,
    c.RunPython: run_python,
    c.StateOnly: nothing,
}

DDL_HANDLERS: dict[type, Callable[[Database, Any, dict], Awaitable[None]]] = {
    c.CreateEnum: create_enum,
    c.AddEnumMember: add_enum_member,
    c.RenameEnumMember: rename_enum_member,
    c.RenameEnum: rename_enum,
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
    `"wrap"` (the relations not yet wrapped, a number at a time), or None (it is made at once).
    `state` is the snapshot before it."""
    if isinstance(change, c.WrapRelation):
        return "wrap" if change.wrapper_kind == "reifiedRelation" else None
    if type(change) not in WINDOWED_HANDLERS:
        return None
    if isinstance(change, c.RemoveField):
        field = field_of(state, change.model, change.name)
        return "window" if field["kind"] in SCALAR_PROPERTY_KINDS and not change.absorbed else None
    if isinstance(change, c.RenameField):
        field = field_of(state, change.model, change.old)
        return "window" if field["kind"] in SCALAR_PROPERTY_KINDS else None
    if isinstance(change, c.AddField):
        field = change.definition
        scalar = field["kind"] in SCALAR_PROPERTY_KINDS
        return "window" if scalar and change.needs_value and not change.from_narrowing else None
    if isinstance(change, c.AlterNullability):
        return None if change.nullable else "window"
    return "window"


async def apply_window(tx: Transaction, change: c.Change, state: dict, window: Window) -> list[str]:
    """One batch of a change that `batch_kind` calls a window: the ids of the nodes it was for"""
    return await WINDOWED_HANDLERS[type(change)](tx, change, state, window) or []


def is_ddl(change: c.Change) -> bool:
    """Whether a change is to the database itself (enums), made outside a transaction"""
    return type(change) in DDL_HANDLERS


async def apply_change(tx: Transaction, change: c.Change, state: dict) -> None:
    """Make a change to the data, in a transaction. `state` is the snapshot before the change."""
    handler = DATA_HANDLERS.get(type(change))
    if handler is None:
        raise PanglossMigrationNotSupported(f"{type(change).__name__} cannot be applied")
    await handler(tx, change, state)


async def run_ddl(database: Database, change: c.Change, state: dict) -> None:
    """Make a change to the database itself. Not in a transaction; and safe to repeat."""
    await DDL_HANDLERS[type(change)](database, change, state)
