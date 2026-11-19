"""What the server computes (`Computed()`, `pangloss_models.computed`), as it is stored and written.

A computed value is a property of its node, as any literal is. A computed relation is the pair of edges of any
relation, each marked `computed: true` (and, if not everyone may see it, `seen_by`): so every read follows it as it
follows the others, and what counts references leaves it out (`fragments.asserted`).

- `write` (`operations.set_computed`) gives a node its computed fields, only if its head is still at the version
  they were worked out from. It makes no `PGUpdate`: the document has no new version, and no history.
- An update deletes the tree below a head and writes it again. `before_replace` reads what was computed for the old
  tree, and `carry_over` gives it to each node of the new one that is the same node saying the same thing: its id,
  and its **basis** (`pg_computed_basis`, a hash of what the node and everything below it says, written with the
  node by `write_plan`).
- A computed edge is no reference: `drop_edges_to` takes away those that lead to an entity that is deleted, or
  merged into another, and gives the heads they were in, which are marked as written so that whoever computes them
  does so again.
"""

import dataclasses
import datetime
import hashlib
import json
from collections.abc import Awaitable, Callable, Iterable
from typing import Any, LiteralString, cast
from uuid import UUID

from pangloss_models import (
    ModelRegistry,
    PanglossNotFoundError,
    PanglossWriteError,
    hooks,
)
from pangloss_models.computed import (
    EVERYONE,
    LOGGED_IN,
    SEEN_BY,
    ComputedTarget,
    ComputedWrite,
    computed_fields,
    has_computed_fields,
)
from pangloss_models.initialise_models.builder import value_annotation
from pangloss_users import current_request_username
from pydantic import TypeAdapter, ValidationError

from pangloss_cypher import fragments, pending
from pangloss_cypher.build_tree import POSITION
from pangloss_cypher.fragments import COMPUTED_EDGE
from pangloss_cypher.heads import VERSION_OF_HEAD
from pangloss_cypher.render_write import edge_names, edges_statement
from pangloss_cypher.transaction import Transaction
from pangloss_cypher.transactions import dialect, write_transaction
from pangloss_cypher.values import convert_type_for_writing
from pangloss_cypher.write_plan import InlineEntity, PlannedNode, WritePlan
from pangloss_cypher.write_plan import edge_names as names_of_field

# The property of a node that has computed fields: a hash of what it and everything below it says (not of what is
# computed), by which an update tells whether the node it writes is the one it deleted
BASIS = "pg_computed_basis"

# (not what a node says: when and by whom, and where it is)
_NOT_SAID = {"meta", "head_node_id", "head_node_type", BASIS}


# --- the basis: what a node says ------------------------------------------------------------------------------------


def _said(
    node: PlannedNode, properties: dict[str, Any] | None = None
) -> dict[str, Any]:
    relations = []
    for relation in node.relations:
        target = relation.target
        if isinstance(target, PlannedNode):
            # (by what it says, not by its id: a nested node written again as new is the same if it says the same)
            to: Any = _said(target)
        else:
            to = getattr(target, "value", None) or getattr(target, "key", None)
        relations.append([list(relation.edges), relation.edge_properties, to])
    return {
        "type": node.type,
        "properties": {
            key: value
            for key, value in (
                node.properties if properties is None else properties
            ).items()
            if key not in _NOT_SAID
        },
        "relations": relations,
    }


def basis_of(node: PlannedNode, properties: dict[str, Any] | None = None) -> str:
    """The basis of a planned node: a hash of its class, its properties (`properties`, if they are not the node's)
    and its relations, with everything below it"""
    text = json.dumps(_said(node, properties), sort_keys=True, default=str)
    return hashlib.sha1(text.encode()).hexdigest()


def give_bases(plan: WritePlan, head_fields: dict[str, Any]) -> dict[str, str]:
    """Give each node of the plan whose class has computed fields its basis (as a property, written with it). The
    bases, by node id. `head_fields`: the values of the head's own fields (the plan of a creation has what the
    apps put on a new head as well, and that of an update nothing: the head says the same in both)"""
    models = ModelRegistry._model_dict
    found: dict[str, str] = {}

    def visit(node: PlannedNode) -> None:
        model = models.get(node.type)
        if model is not None and has_computed_fields(model):
            node.properties[BASIS] = found[node.id] = basis_of(
                node, head_fields if node is plan.head else None
            )
        for relation in node.relations:
            if isinstance(relation.target, PlannedNode):
                visit(relation.target)
            elif isinstance(relation.target, InlineEntity) and relation.target.node:
                # (an entity the document names and makes: a head of its own)
                visit(relation.target.node)

    visit(plan.head)
    return found


# --- an update: what was computed for the tree it replaces -----------------------------------------------------------


@dataclasses.dataclass
class Kept:
    """What was computed for a node of a tree that an update is about to replace"""

    id: str
    type: str
    basis: str
    properties: dict[str, Any]
    edges: list[dict[str, Any]]


def _before_replace_query() -> str:
    return f"""
    MATCH (head:HeadNode {{id: $id}})
    OPTIONAL MATCH {dialect().tree_below("(head)", "(below)")}
    WITH head, collect(DISTINCT below) AS tree
    UNWIND [head] + tree AS node
    WITH node WHERE node.{BASIS} IS NOT NULL
    RETURN node.id AS id, node.type AS type, node.{BASIS} AS basis, properties(node) AS properties,
           [(node)-[edge]->(target) WHERE coalesce(edge.{COMPUTED_EDGE}, false) AND NOT coalesce(edge.reverse, false)
            | {{type: type(edge), target: target.id, properties: properties(edge)}}] AS edges
    """


def _stored_computed(type_name: str, properties: dict[str, Any]) -> dict[str, Any]:
    """Of a node's properties as they are stored, those of its computed values (a map that a backend stores as
    several properties, `name.key`, is all of them)"""
    model = ModelRegistry._model_dict.get(type_name)
    if model is None:
        return {}
    names = tuple(computed_fields(model).values)
    return {
        key: value
        for key, value in properties.items()
        if key in names or key.startswith(tuple(f"{name}." for name in names))
    }


async def before_replace(tx: Transaction, head_id: UUID | str) -> dict[str, Kept]:
    """What was computed for a head and the nodes below it, by node id, read before an update deletes them"""
    result = await tx.run(cast(LiteralString, _before_replace_query()), id=str(head_id))
    kept: dict[str, Kept] = {}
    async for record in result:
        kept[record["id"]] = Kept(
            id=record["id"],
            type=record["type"],
            basis=record["basis"],
            properties=_stored_computed(record["type"], record["properties"]),
            edges=record["edges"],
        )
    return kept


def _reverse_names(type_name: str) -> dict[str, str]:
    """The reverse name of each edge of the computed relations of a class"""
    model = ModelRegistry._model_dict.get(type_name)
    pairs: dict[str, str] = {}
    if model is None:
        return pairs
    for name, definition in computed_fields(model).relations.items():
        for forward, backward in names_of_field(
            name, definition.reverse_name, definition.subclasses_parent_fields
        ):
            pairs.setdefault(forward, backward)
    return pairs


async def carry_over(
    tx: Transaction, kept: dict[str, Kept], bases: dict[str, str]
) -> None:
    """Give the nodes an update has just written what was computed for them before, where the node is the same one
    (its id) saying the same thing (its basis). A node that changed starts with nothing computed"""
    property_rows: list[dict[str, Any]] = []
    edge_rows: list[dict[str, Any]] = []
    pairs: set[tuple[str, str]] = set()
    for node_id, basis in bases.items():
        old = kept.get(node_id)
        if old is None or old.basis != basis:
            continue
        if old.properties:
            property_rows.append({"id": node_id, "properties": old.properties})
        reverse = _reverse_names(old.type)
        for edge in old.edges:
            backward = reverse.get(edge["type"])
            if backward is None:
                # (of a field the class no longer computes)
                continue
            properties = dict(edge["properties"])
            position = properties.pop(POSITION, 0)
            properties.pop("reverse", None)
            pairs.add((edge["type"], backward))
            edge_rows.append(
                {
                    "source": node_id,
                    "target": edge["target"],
                    "names": edge_names(edge["type"], backward),
                    "position": position,
                    "properties": properties,
                    "allowed": None,
                }
            )
    if property_rows:
        await (
            await tx.run(
                """
                UNWIND $rows AS row
                MATCH (node:PGIndexableNode {id: row.id})
                SET node += row.properties
                """,
                rows=property_rows,
            )
        ).consume()
    if edge_rows:
        statement = edges_statement(sorted(pairs), False, edge_rows)
        await (await tx.run(statement.text, **statement.params)).consume()


# --- no reference: an entity that is deleted, or merged into another ------------------------------------------------

DROP_QUERY = f"""
    MATCH (entity:PGIndexableNode {{id: $id}})
    MATCH (entity)-[edge]-(source:PGIndexableNode)
    WHERE coalesce(edge.{COMPUTED_EDGE}, false)
      AND ((startNode(edge) = entity AND coalesce(edge.reverse, false))
           OR (endNode(edge) = entity AND NOT coalesce(edge.reverse, false)))
    WITH edge, coalesce(source.head_node_id, source.id) AS head_id
    DELETE edge
    WITH DISTINCT head_id
    MATCH (head:HeadNode {{id: head_id}})
    RETURN head.id AS id, head.type AS type
"""

HEADS_QUERY = f"""
    MATCH (entity:PGIndexableNode {{id: $id}})<-[edge]-(source:PGIndexableNode)
    WHERE coalesce(edge.{COMPUTED_EDGE}, false) AND NOT coalesce(edge.reverse, false)
    WITH DISTINCT coalesce(source.head_node_id, source.id) AS head_id
    MATCH (head:HeadNode {{id: head_id}})
    RETURN head.id AS id, head.type AS type
"""


async def mark_heads(tx: Transaction, heads: Iterable[tuple[str, str]]) -> list[type]:
    """Mark heads (id, class name) as written, for whoever computes what is in them. Gives their classes, to tell
    `hooks.work_marked` of after the commit"""
    models: list[type] = []
    for head_id, type_name in heads:
        model = ModelRegistry._model_dict.get(type_name)
        if model is None:
            continue
        await pending.mark_written(tx, model, head_id)
        if model not in models:
            models.append(model)
    return models


async def drop_edges_to(tx: Transaction, entity_id: UUID | str) -> list[type]:
    """Take away the computed edges that lead to an entity (it is deleted, or merged into another), and mark the
    heads they were in as written. No new version of those heads: nothing they say has changed"""
    result = await tx.run(DROP_QUERY, id=str(entity_id))
    heads = [(record["id"], record["type"]) async for record in result]
    return await mark_heads(tx, heads)


async def mark_heads_with_edges_to(
    tx: Transaction, entity_id: UUID | str
) -> list[type]:
    """Mark as written the heads that have a computed edge to an entity (a merge into it was undone: what is
    computed may no longer hold)"""
    result = await tx.run(HEADS_QUERY, id=str(entity_id))
    heads = [(record["id"], record["type"]) async for record in result]
    return await mark_heads(tx, heads)


# --- writing --------------------------------------------------------------------------------------------------------

FIND_QUERY = """
    MATCH (node:PGIndexableNode {id: $id})
    OPTIONAL MATCH (above:HeadNode {id: node.head_node_id})
    WITH node, coalesce(above, node) AS head
    RETURN node.type AS type, head.id AS head_id, head.type AS head_type
"""

# (the head is written to, though nothing of it changes: two writers of one head, an update and this, then cannot
# both go ahead on a database that makes the second run again; on one that does not, the head's lock is held)
CHECK_QUERY = cast(
    LiteralString,
    f"""
    MATCH (head:HeadNode {{id: $head}})
    WITH head, {VERSION_OF_HEAD} AS version
    SET head.id = head.id
    RETURN version, {fragments.deleted("head")} AS deleted
""",
)

CLEAR_QUERY = f"""
    MATCH (node:PGIndexableNode {{id: $id}})
    WITH node,
         [(node)-[edge]->() WHERE type(edge) IN $forward AND coalesce(edge.{COMPUTED_EDGE}, false)
                                  AND NOT coalesce(edge.reverse, false) | edge]
         + [(node)<-[edge]-() WHERE type(edge) IN $backward AND coalesce(edge.{COMPUTED_EDGE}, false)
                                    AND coalesce(edge.reverse, false) | edge] AS old
    FOREACH (edge IN old | DELETE edge)
"""


def _edges_query(forward: str, backward: str) -> str:
    """The pair of edges of a computed relation to each entity of `$rows` (`{id, forward, backward}`: the properties
    of each edge). An entity that is deleted, or merged into another, is left out; one that is not there is not
    counted, and the write is refused"""
    return f"""
    UNWIND $rows AS row
    MATCH (node:PGIndexableNode {{id: $id}})
    MATCH (target:PGIndexableNode {{id: row.id}})
    WHERE target:Entity
    FOREACH (_ IN CASE WHEN {fragments.not_deleted("target")} AND {fragments.not_merged("target")}
                       THEN [1] ELSE [] END |
        CREATE (node)-[out:{fragments.field_edge(forward)}]->(target)
        SET out = row.forward
        CREATE (node)<-[back:{fragments.field_edge(backward)}]-(target)
        SET back = row.backward
    )
    RETURN count(*) AS found
    """


def _targets(field: str, value: Any) -> list[ComputedTarget]:
    """What a computed relation is given, as targets, each entity once"""
    items = [] if value is None else value if isinstance(value, list) else [value]
    targets: dict[str, ComputedTarget] = {}
    for item in items:
        if isinstance(item, ComputedTarget):
            target = item
        elif isinstance(item, dict):
            target = ComputedTarget(id=item["id"], seen_by=item.get(SEEN_BY))
        else:
            target = ComputedTarget(id=item)
        if target.seen_by not in (None, EVERYONE, LOGGED_IN):
            raise PanglossWriteError(
                f"{field}: seen_by is {EVERYONE!r} or {LOGGED_IN!r}, not {target.seen_by!r}"
            )
        targets.setdefault(str(target.id), target)
    return list(targets.values())


def _edge_properties(target: ComputedTarget) -> dict[str, Any]:
    properties: dict[str, Any] = {COMPUTED_EDGE: True}
    if target.seen_by not in (None, EVERYONE):
        properties[SEEN_BY] = target.seen_by
    return properties


@dataclasses.dataclass(frozen=True)
class Written:
    """A node whose computed fields were written: the class and id of its head, and the head's version (which the
    write did not change)"""

    model: type
    head_id: UUID
    version: int


async def write(
    tx: Transaction,
    node_id: UUID | str,
    values: dict[str, Any],
    based_on_version: int | None = None,
    less: Iterable[str] = (),
) -> Written | None:
    """Give a node its computed fields (`values`, by name), in the transaction given. None, and nothing is changed,
    if its head is no longer at `based_on_version`, or is deleted. The head is marked with the pending work of its
    class, less the kinds `less` (the caller's own: what it computes it need not compute again)"""
    found = await (await tx.run(FIND_QUERY, id=str(node_id))).single()
    if found is None:
        raise PanglossNotFoundError(f"There is no node with id {node_id}")
    model = ModelRegistry._model_dict.get(found["type"])
    head_model = ModelRegistry._model_dict.get(found["head_type"])
    if model is None or head_model is None:
        raise PanglossWriteError(
            f"{found['type']} {node_id} (in a {found['head_type']}) is not a model of now"
        )
    fields = computed_fields(model)
    unknown = sorted(set(values) - set(fields.relations) - set(fields.values))
    if unknown:
        raise PanglossWriteError(
            f"{found['type']} has no computed field {', '.join(unknown)}: set_computed writes only fields marked "
            "Computed()"
        )

    properties: dict[str, Any] = {}
    for name, value in values.items():
        if name not in fields.values:
            continue
        try:
            checked = TypeAdapter(
                value_annotation(fields.values[name], True)
            ).validate_python(value)
        except ValidationError as error:
            raise PanglossWriteError(
                f"{found['type']}.{name}: {error.errors()[0]['msg']}"
            ) from error
        properties[name] = checked

    head_id = found["head_id"]
    await dialect().before_replace(tx, head_id)
    checked_head = await (await tx.run(CHECK_QUERY, head=head_id)).single()
    if checked_head is None:
        raise PanglossNotFoundError(f"There is no head node with id {head_id}")
    version = checked_head["version"]
    if checked_head["deleted"] or (
        based_on_version is not None and version != based_on_version
    ):
        return None

    for name, definition in fields.relations.items():
        if name not in values:
            continue
        pairs = names_of_field(
            name, definition.reverse_name, definition.subclasses_parent_fields
        )
        await (
            await tx.run(
                cast(LiteralString, CLEAR_QUERY),
                id=str(node_id),
                forward=[forward for forward, _ in pairs],
                backward=[backward for _, backward in pairs],
            )
        ).consume()
        targets = _targets(name, values[name])
        if not targets:
            continue
        rows = [
            {
                "id": str(target.id),
                "forward": {POSITION: position, **_edge_properties(target)},
                "backward": {"reverse": True, **_edge_properties(target)},
            }
            for position, target in enumerate(targets)
        ]
        for forward, backward in pairs:
            record = await (
                await tx.run(
                    cast(LiteralString, _edges_query(forward, backward)),
                    id=str(node_id),
                    rows=rows,
                )
            ).single()
            if record is None or record["found"] != len(rows):
                raise PanglossWriteError(
                    f"{found['type']}.{name}: a computed relation is to entities that are there: "
                    f"{len(rows) - (record['found'] if record else 0)} of those given are not"
                )

    if properties:
        await (
            await tx.run(
                "MATCH (node:PGIndexableNode {id: $id}) SET node += $properties",
                id=str(node_id),
                # (a value of None takes the property away; said apart, as a backend's encoding may leave it out)
                properties={
                    **convert_type_for_writing(
                        dialect().encode_properties(
                            {k: v for k, v in properties.items() if v is not None},
                            node=False,
                        )
                    ),
                    **{k: None for k, v in properties.items() if v is None},
                },
            )
        ).consume()

    await pending.mark_written(tx, head_model, head_id, less=less)
    return Written(model=head_model, head_id=UUID(head_id), version=version)


async def _announce(written: Iterable[Written | None]) -> None:
    """After the commit: a `computed` event for each head whose computed fields were written (no history is kept
    of it), and `hooks.work_marked` for each of their classes, so that another app's worker wakes"""
    models: list[type] = []
    seen: set[UUID] = set()
    for item in written:
        if item is None or item.head_id in seen:
            continue
        seen.add(item.head_id)
        hooks.emit_write_event(
            hooks.WriteEvent(
                op="computed",
                model=item.model,
                id=item.head_id,
                version=item.version,
                user=current_request_username.get(),
                at=datetime.datetime.now(datetime.UTC),
            )
        )
        if item.model not in models:
            models.append(item.model)
    for model in models:
        hooks.emit_work_marked(model)


@write_transaction
async def _write_all(
    tx: Transaction,
    writes: list[ComputedWrite],
    less: tuple[str, ...],
    then: Callable[[Transaction], Awaitable[None]] | None,
) -> list[Written | None]:
    written = [
        await write(tx, item.node_id, item.values, item.based_on_version, less)
        for item in writes
    ]
    if then is not None:
        await then(tx)
    return written


async def set_computed(
    node_id: UUID | str,
    values: dict[str, Any],
    based_on_version: int | None = None,
    *,
    less: Iterable[str] = (),
) -> bool:
    """Give a node (a head, or a node below one) its computed fields: `values` by field name, a relation as a list
    of ids (or `ComputedTarget`s, which say who may see each), a value as itself (None: none). Whether it was
    written: it is not, and nothing changes, if the node's head is no longer at `based_on_version` (the version
    the values were worked out from), or is deleted.

    It makes no new version of the head and no record of an update: what the document says has not changed. The
    head is marked with the pending work of its class, less the kinds `less`, and after the commit a write event
    of kind `computed` is given, and `hooks.work_marked` told."""
    written = await _write_all(
        [ComputedWrite(node_id, values, based_on_version)], tuple(less), None
    )
    await _announce(written)
    return written[0] is not None


async def set_computed_batch(
    writes: Iterable[ComputedWrite],
    *,
    less: Iterable[str] = (),
    then: Callable[[Any], Awaitable[None]] | None = None,
) -> list[bool]:
    """`set_computed` for each of `writes`, in one transaction: whether each was written. `then` is awaited in the
    transaction after them (a worker completes its claims there: `pending.complete`). The transaction may be run
    again, so `then` does only what can be done twice"""
    written = await _write_all(list(writes), tuple(less), then)
    await _announce(written)
    return [item is not None for item in written]


__all__ = [
    "BASIS",
    "ComputedTarget",
    "ComputedWrite",
    "Kept",
    "Written",
    "basis_of",
    "before_replace",
    "carry_over",
    "drop_edges_to",
    "give_bases",
    "mark_heads",
    "mark_heads_with_edges_to",
    "set_computed",
    "set_computed_batch",
    "write",
]
