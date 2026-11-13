"""Merging two entities that are one, and undoing a merge (implementation_docs/entity-identity.md, part 1).

A merge of B (absorbed) into A (the survivor), in one transaction when it writes no more heads than `MERGE_LIMIT`:

1. B is marked `merged_into: A` (a property: there is no edge between them), and A is written with the fields chosen,
   first of all: so that a write that names either gives way to the merge, not the merge to it;
2. B's URLs become A's;
3. every forward edge of a field from a node to B goes to A, with its properties and its place in its list, except
   those of fields marked `KeepOnMerge()`, and the edges of A's and B's own nodes. A node that already has the relation
   to A keeps the edge it has, and its edge to B is dropped. Each edge that goes is recorded first, as a `PGMergeMove`
   with the edge's properties, so that an undo can put it back;
4. each head that changed has a new version (`PGUpdate`), as after an update;
5. what is left on B is counted: anything but the kept fields is an error, and nothing is committed.

It is recorded as a `PGMerge` (with A's fields as they were). B itself is not touched: its fields and what it refers
to are as they were. Undoing (`unmerge_entities`) moves the recorded edges back where the node that held each is
still there and still points at A, gives B its URLs again, clears the mark, and puts A's fields back if A has not
changed since.

A record of a move names the node (its id, which an update keeps), the field and the reverse field, not the edge: an
update of the head deletes its edges and makes them again.
"""

import asyncio
import dataclasses
import datetime
import json
import logging
import random
import uuid
from typing import Any, LiteralString, cast
from uuid import UUID

import neo4j
from pangloss_models import (
    Entity,
    ModelRegistry,
    PanglossMergeBusyError,
    PanglossMergeError,
    PanglossMergeNotAllowedError,
    PanglossMergeTooLargeError,
    PanglossNotFoundError,
    PanglossVersionConflictError,
    PanglossWriteError,
    hooks,
)
from pangloss_models.label_templates import fill_labels
from pangloss_models.markers import keeps_on_merge
from pangloss_models.merging import (
    DEFAULT_MERGE_LIMIT,
    HeadRef,
    MergePreview,
    MergeRecord,
    MergeResult,
    UnmergeResult,
    merged_values,
    survivor_class,
    without_references_to,
)
from pangloss_models.utils import editable
from pangloss_models.write_checks import check_before_update
from pangloss_users import current_request_username
from pydantic import ValidationError

from pangloss_cypher import fragments, pending
from pangloss_cypher.build_tree import POSITION
from pangloss_cypher.checks import check_user_exists
from pangloss_cypher.fragments import field_edge
from pangloss_cypher.read_functions import (
    get_document,
    get_entity_for_edit,
    read_entity,
)
from pangloss_cypher.relink import (
    RelinkedHead,
    announce_relinked,
    move_edges,
    record_updates,
    remove_edges,
)
from pangloss_cypher.transactions import (
    Transaction,
    current,
    dialect,
    read_transaction,
    write_transaction,
)
from pangloss_cypher.write_functions import (
    announce,
    read_labels,
    referrers,
    replace_head_in,
)
from pangloss_cypher.write_plan import edge_names

logger = logging.getLogger("pangloss.merge")

# What a record of a move has besides the properties of the edge it moved (and `pg_position`, the edge's own)
RECORD_KEYS = (
    "pg_merge",
    "pg_source",
    "pg_source_type",
    "pg_head",
    "pg_field",
    "pg_reverse",
    "pg_dropped",
    "pg_holder",
    "pg_late",
)
_REMOVE_RECORD = ", ".join(f"new.{key}" for key in RECORD_KEYS)
_REMOVE_RECORD_REVERSE = ", ".join(
    f"new_reverse.{key}" for key in (*RECORD_KEYS, POSITION)
)

# How many times a merge that was decided on no versions is prepared, if an entity changes under it, and how long it
# waits before the next (seconds, times the number of the attempt, and up to as much again at random)
MERGE_ATTEMPTS = 6
MERGE_ATTEMPT_WAIT = 0.05

# How many heads of one kind a result names (the rest are counted)
MAX_HEADS_NAMED = 200

# If set, the seconds after which the second pass is made again, whatever the dialect and the settings say (the tests
# set 0: a task left waiting when a test's loop stops holds a transaction open)
SECOND_PASS_DELAY: float | None = None

_second_passes: set[asyncio.Task] = set()


class _RolledBack(Exception):
    """Raised at the end of a transaction that was only to find out what it would do: nothing is committed"""

    def __init__(self, outcome: Any):
        super().__init__("rolled back")
        self.outcome = outcome


class _FieldsNotRestored(Exception):
    """The survivor's fields could not be put back by an undo: it is made again without them"""

    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


def merge_limit() -> int:
    return int(getattr(current().settings, "MERGE_LIMIT", DEFAULT_MERGE_LIMIT))


def _native(value: Any) -> Any:
    return value.to_native() if hasattr(value, "to_native") else value


def _model(type_name: str | None) -> type[Entity] | None:
    model = ModelRegistry.all_models().get(type_name) if type_name else None
    if isinstance(model, type) and issubclass(model, Entity):
        return model
    return None


# --- reading what is there ----------------------------------------------------------------------------------------------

ENTITY_QUERY = cast(
    LiteralString,
    f"""
    MATCH (n:PGIndexableNode {{id: $id}})
    WHERE n:Entity
    RETURN n.id AS id, n.type AS type, n.label AS label, labels(n) AS labels,
           {fragments.deleted("n")} AS deleted, n.merged_into AS merged_into,
           size([(n)<-[:is_update_of]-(update:PGUpdate) | update]) + 1 AS version,
           [(n)-[:has_url]->(url:PGUrl) | url.url] AS urls
""",
)


@dataclasses.dataclass
class _Found:
    id: str
    type: str
    label: str | None
    labels: set[str]
    deleted: bool
    merged_into: str | None
    version: int
    urls: list[str]


async def _find(tx: Transaction, id: UUID | str) -> _Found | None:
    row = await (await tx.run(ENTITY_QUERY, id=str(id))).single()
    if row is None:
        return None
    return _Found(
        id=row["id"],
        type=row["type"],
        label=row["label"],
        labels=set(row["labels"]),
        deleted=row["deleted"],
        merged_into=row["merged_into"],
        version=row["version"],
        urls=sorted(row["urls"]),
    )


# The forward edges of fields into an entity, by the node each is from and its field: how many there are, how many
# edges of the field the node has to the other entity (`$other`), and the node that holds the node (for one that is
# below a head). (Each pattern of a comprehension begins at the node already in hand: written from the holder's side,
# Memgraph scanned every node for each row, 7 s for an entity named by 100 documents in a database of 590,000 nodes)
INCOMING_QUERY = """
    MATCH (:PGIndexableNode {id: $id})<-[edge]-(source:PGIndexableNode)
    WHERE NOT coalesce(edge.reverse, false)
    WITH source, type(edge) AS field, count(edge) AS edges
    RETURN source.id AS source, source.type AS source_type,
           coalesce(source.head_node_id, source.id) AS head, field, edges,
           size([(source)-[same]->(other:PGIndexableNode {id: $other})
                 WHERE type(same) = field AND NOT coalesce(same.reverse, false) | 1]) AS to_other,
           CASE WHEN source.head_node_id IS NULL THEN null
                ELSE [(source)<-[held]-(holder:PGIndexableNode) WHERE NOT coalesce(held.reverse, false) | holder.id][0]
           END AS holder
    ORDER BY head, source, field
"""


async def _incoming(tx: Transaction, id: str, other: str) -> list[dict[str, Any]]:
    return await (await tx.run(INCOMING_QUERY, id=id, other=other)).data()


def _edge_pairs(model: type) -> dict[str, str]:
    """The reverse name of each edge a node of the class has for its relations: its fields', and those of the parent
    fields they are also stored as"""
    pairs: dict[str, str] = {}
    for name, definition in model._meta.fields.relation_fields.items():  # ty: ignore[unresolved-attribute]
        for forward, backward in edge_names(
            name, definition.reverse_name, definition.subclasses_parent_fields
        ):
            pairs.setdefault(forward, backward)
    return pairs


def _kept_edges(model: type, present: set[str]) -> set[str]:
    """The edges of a node of the class that a merge leaves where they are, given the fields it has to the absorbed
    entity (`present`): those of its fields marked `KeepOnMerge()`, and of the parent fields those are also stored
    as. (A node that names the entity in a kept field and, apart from that, in a parent field of it keeps both:
    which edge of the parent field is whose cannot be told.)"""
    kept: set[str] = set()
    for name, definition in model._meta.fields.relation_fields.items():  # ty: ignore[unresolved-attribute]
        if name in present and keeps_on_merge(definition):
            kept.update(
                forward
                for forward, _ in edge_names(
                    name, definition.reverse_name, definition.subclasses_parent_fields
                )
            )
    return kept


@dataclasses.dataclass
class _Moves:
    """What a merge does with the edges into the absorbed entity"""

    # (field, reverse) -> the rows of the nodes whose edges go: to the survivor, or (dropped) nowhere
    groups: dict[tuple[str, str], list[dict[str, Any]]] = dataclasses.field(
        default_factory=dict
    )
    kept: int = 0
    own: list[dict[str, Any]] = dataclasses.field(default_factory=list)
    problems: list[str] = dataclasses.field(default_factory=list)

    @property
    def rows(self) -> list[dict[str, Any]]:
        return [row for rows in self.groups.values() for row in rows]

    @property
    def heads(self) -> list[str]:
        return sorted({row["head"] for row in self.rows})

    @property
    def edges(self) -> int:
        return sum(row["edges"] for row in self.rows)

    def only(self, heads: set[str]) -> "_Moves":
        return _Moves(
            groups={
                key: kept
                for key, rows in self.groups.items()
                if (kept := [row for row in rows if row["head"] in heads])
            },
            kept=self.kept,
        )


def _plan(rows: list[dict[str, Any]], own: set[str]) -> _Moves:
    """What to do with each edge into the absorbed entity (`rows`: `INCOMING_QUERY`). `own`: the ids of the two
    entities, whose own nodes are not moved (the survivor does not come to refer to itself)"""
    moves = _Moves()
    models = ModelRegistry.all_models()
    by_source: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        by_source.setdefault(row["source"], []).append(row)
    for source_rows in by_source.values():
        first = source_rows[0]
        if first["head"] in own:
            moves.own += source_rows
            continue
        model = models.get(first["source_type"])
        if model is None:
            moves.problems.append(
                f"{first['source_type']} {first['source']} refers to it, and is not a model of now"
            )
            continue
        pairs = _edge_pairs(model)
        kept = _kept_edges(model, {row["field"] for row in source_rows})
        for row in source_rows:
            if row["field"] in kept:
                moves.kept += row["edges"]
                continue
            reverse = pairs.get(row["field"])
            if reverse is None:
                moves.problems.append(
                    f"{first['source_type']} {first['source']} refers to it by `{row['field']}`, which is not a "
                    f"relation of {first['source_type']}"
                )
                continue
            moves.groups.setdefault((row["field"], reverse), []).append(
                {**row, "dropped": row["to_other"] > 0}
            )
    return moves


async def _head_refs(tx: Transaction, ids: list[str]) -> list[HeadRef]:
    if not ids:
        return []
    result = await tx.run(
        """
        UNWIND $ids AS id
        MATCH (head:PGIndexableNode {id: id})
        RETURN head.id AS id, head.type AS type, head.label AS label
        """,
        ids=ids[:MAX_HEADS_NAMED],
    )
    return [
        HeadRef(id=UUID(row["id"]), type=row["type"], label=row["label"])
        for row in await result.data()
    ]


REFERRING_HEADS_QUERY = """
    MATCH (:PGIndexableNode {id: $id})<-[edge]-(source:PGIndexableNode)
    WHERE NOT coalesce(edge.reverse, false)
    WITH DISTINCT coalesce(source.head_node_id, source.id) AS head
    RETURN head
"""

COUNTS_QUERY = cast(
    LiteralString,
    f"""
    MATCH (:PGIndexableNode {{id: $id}})<-[edge]-(source:PGIndexableNode)
    WHERE NOT coalesce(edge.reverse, false)
    WITH DISTINCT coalesce(source.head_node_id, source.id) AS head_id
    MATCH (head:HeadNode {{id: head_id}})
    WHERE {fragments.not_deleted("head")} AND {fragments.not_merged("head")}
    RETURN head.type AS type, count(head) AS heads
    ORDER BY heads DESC, type
""",
)


async def _migrations(tx: Transaction) -> str:
    """The last migration applied of each app, as it is kept on a merge: an undo compares it with now"""
    result = await tx.run(
        "MATCH (m:PGMigration) RETURN m.app AS app, max(m.name) AS name ORDER BY app"
    )
    return json.dumps({row["app"]: row["name"] for row in await result.data()})


# --- the record ---------------------------------------------------------------------------------------------------------


def _record(properties: dict[str, Any]) -> MergeRecord:
    proposed = properties["state"] in ("proposed", "rejected", "stale")
    values = properties.get("proposed_values")
    return MergeRecord(
        id=UUID(properties["id"]),
        survivor=UUID(properties["survivor"]),
        absorbed=UUID(properties["absorbed"]),
        state=properties["state"],
        by=properties.get("by"),
        when=_native(properties.get("when")),
        survivor_type=properties.get("survivor_type"),
        survivor_type_before=properties.get("survivor_type_before"),
        absorbed_type=properties.get("absorbed_type"),
        survivor_label=properties.get("survivor_label"),
        absorbed_label=properties.get("absorbed_label"),
        survivor_version=properties.get(
            "proposed_survivor_version" if proposed else "survivor_version"
        ),
        absorbed_version=properties.get(
            "proposed_absorbed_version" if proposed else "absorbed_version"
        ),
        heads=properties.get("heads") or 0,
        moved=properties.get("moved") or 0,
        dropped=properties.get("dropped") or 0,
        undone_by=properties.get("undone_by"),
        undone_when=_native(properties.get("undone_when")),
        proposed_by=properties.get("proposed_by"),
        proposed_when=_native(properties.get("proposed_when")),
        note=properties.get("note"),
        values=json.loads(values) if values and proposed else None,
        rejected_by=properties.get("rejected_by"),
        rejected_when=_native(properties.get("rejected_when")),
        reason=properties.get("reason"),
        undo_proposed_by=properties.get("undo_proposed_by"),
        undo_proposed_when=_native(properties.get("undo_proposed_when")),
        undo_note=properties.get("undo_note"),
        undo_rejected_by=properties.get("undo_rejected_by"),
        undo_rejected_reason=properties.get("undo_rejected_reason"),
    )


async def _merge_properties(tx: Transaction, merge_id: UUID | str) -> dict[str, Any]:
    row = await (
        await tx.run(
            "MATCH (m:PGMerge {id: $id}) RETURN properties(m) AS merge",
            id=str(merge_id),
        )
    ).single()
    if row is None:
        raise PanglossNotFoundError(f"There is no merge {merge_id}")
    return row["merge"]


@read_transaction
async def merges_of_entity(
    tx: Transaction, cls: type[Entity], id: UUID
) -> list[MergeRecord]:
    """The merges an entity is part of, as the survivor or as the one absorbed, the latest first (those undone too)"""
    found: dict[str, dict[str, Any]] = {}
    # (each by its index: one query with an `OR` reads every merge)
    for role in ("survivor", "absorbed"):
        result = await tx.run(
            f"MATCH (m:PGMerge {{{role}: $id}}) RETURN properties(m) AS merge",
            id=str(id),
        )
        for row in await result.data():
            found[row["merge"]["id"]] = row["merge"]
    # (a merge's id is a UUID7: in the order they were made)
    return [_record(found[key]) for key in sorted(found, reverse=True)]


@read_transaction
async def get_merge(tx: Transaction, merge_id: UUID | str) -> MergeRecord:
    """A merge, by its id (`PanglossNotFoundError` if there is none)"""
    return _record(await _merge_properties(tx, merge_id))


# --- moving, and recording what is moved ----------------------------------------------------------------------------------


async def _record_moves(
    tx: Transaction,
    merge_id: str,
    field: str,
    reverse: str,
    absorbed: str,
    rows: list[dict[str, Any]],
    late: bool,
) -> int:
    """A `PGMergeMove` for each edge of the field from the nodes of `rows` to the absorbed entity, with the edge's
    properties: how many were recorded"""
    result = await tx.run(
        f"""
        UNWIND $rows AS row
        MATCH (e:PGIndexableNode {{id: row.source}})-[old:{field_edge(field)}]->(:PGIndexableNode {{id: $absorbed}})
        WHERE NOT coalesce(old.reverse, false)
        CREATE (move:PGMergeMove)
        SET move = properties(old)
        SET move.pg_merge = $merge, move.pg_source = row.source, move.pg_source_type = row.source_type,
            move.pg_head = row.head, move.pg_field = $field, move.pg_reverse = $reverse,
            move.pg_dropped = row.dropped, move.pg_holder = row.holder, move.pg_late = $late
        RETURN count(move) AS recorded
        """,  # ty: ignore[invalid-argument-type]
        rows=[
            {
                "source": row["source"],
                "source_type": row["source_type"],
                "head": row["head"],
                "dropped": row["dropped"],
                "holder": row["holder"],
            }
            for row in rows
        ],
        merge=merge_id,
        field=field,
        reverse=reverse,
        absorbed=absorbed,
        late=late,
    )
    row = await result.single()
    return row["recorded"] if row else 0


@dataclasses.dataclass
class _Moved:
    heads: list[RelinkedHead] = dataclasses.field(default_factory=list)
    moved: int = 0
    dropped: int = 0


async def _move(
    tx: Transaction,
    merge_id: str,
    survivor: str,
    absorbed: str,
    moves: _Moves,
    *,
    late: bool = False,
) -> _Moved:
    """Record and move the edges of `moves` from the absorbed entity to the survivor, and give each head that
    changes a new version. The record must hold every edge that goes, or nothing is to be committed (it raises)"""
    done = _Moved()
    heads = moves.heads
    # (as an update does: Neo4j takes the lock of each head, so that an update of one waits for this, or this for it)
    for head in heads:
        await dialect().before_replace(tx, head)
    for (field, reverse), rows in moves.groups.items():
        expected = sum(row["edges"] for row in rows)
        recorded = await _record_moves(
            tx, merge_id, field, reverse, absorbed, rows, late
        )
        if recorded != expected:
            raise PanglossWriteError(
                f"The merge found {expected} `{field}` edges to move and recorded {recorded}: nothing was merged"
            )
        going = [row["source"] for row in rows if not row["dropped"]]
        dropping = [row["source"] for row in rows if row["dropped"]]
        removed = 0
        if going:
            removed += await move_edges(
                tx, field, reverse, absorbed, survivor, going, unless_there=False
            )
        if dropping:
            removed += await remove_edges(tx, field, reverse, absorbed, dropping)
        # (each forward edge has its reverse edge)
        if removed < expected:
            raise PanglossWriteError(
                f"The merge recorded {expected} `{field}` edges and removed {removed}: nothing was merged"
            )
        done.moved += sum(row["edges"] for row in rows if not row["dropped"])
        done.dropped += sum(row["edges"] for row in rows if row["dropped"])
    done.heads = await record_updates(tx, heads)
    return done


async def _check_nothing_left(
    tx: Transaction, survivor: str, absorbed: str, kept: int
) -> None:
    """After the edges have moved: what is left on the absorbed entity must be the kept fields, and its own. Anything
    else is a kind of reference the merge does not know how to move, and then nothing is to be committed"""
    left = _plan(await _incoming(tx, absorbed, survivor), {survivor, absorbed})
    if left.problems:
        raise PanglossMergeError("; ".join(left.problems))
    from_survivor = [row for row in left.own if row["head"] == survivor]
    if from_survivor:
        fields = ", ".join(sorted({row["field"] for row in from_survivor}))
        raise PanglossMergeError(
            f"The survivor itself refers to the entity it absorbs ({fields}): leave the reference out of its values"
        )
    if left.rows:
        fields = ", ".join(sorted({row["field"] for row in left.rows}))
        raise PanglossWriteError(
            f"{left.edges} references were left on the absorbed entity ({fields}): nothing was merged"
        )
    if left.kept != kept:
        raise PanglossWriteError(
            f"{left.kept} kept references are on the absorbed entity where {kept} were: nothing was merged"
        )


async def _invalid_heads(tx: Transaction, heads: list[RelinkedHead]) -> list[str]:
    """Of the heads (read as they are now, in the transaction), those that an update would no longer take: a list
    that held both entities and must hold two, shares that no longer sum"""
    models = ModelRegistry.all_models()
    failing: list[str] = []
    labels = {ref.id: ref.label for ref in await _head_refs(tx, [h.id for h in heads])}
    for head in heads:
        model = models.get(head.type)
        if model is None:
            continue
        try:
            # (a read validates what it reads, as an update validates what it is given)
            if model.__metatype__ == "Entity":
                view = await get_entity_for_edit.__wrapped__(  # ty: ignore[unresolved-attribute]
                    tx, model, UUID(head.id), follow_merge=False
                )
            else:
                view = await get_document.__wrapped__(tx, model, UUID(head.id))  # ty: ignore[unresolved-attribute]
            # (deleted, or not published for this reader: it is not read, and is as valid as it was)
            if view is not None:
                cast(Any, model).Update(**editable(view.model_dump()))
        except ValidationError as error:
            first = error.errors()[0]
            where = ".".join(str(part) for part in first["loc"])
            failing.append(
                f"{head.type} {head.id} ({labels.get(UUID(head.id))!r}): {where}: {first['msg']}"
            )
    return failing


# --- the merge ----------------------------------------------------------------------------------------------------------


@dataclasses.dataclass
class _Prepared:
    """A merge that has been checked against the two entities as they were read, and is ready to be made"""

    survivor: str
    absorbed: str
    survivor_model: type[Entity]
    absorbed_model: type[Entity]
    result_model: type[Entity]
    survivor_version: int
    absorbed_version: int
    db_instance: Any
    values: dict[str, Any]
    before: str
    """The survivor's fields as they are before the merge (what its `Update` takes), as JSON"""


@dataclasses.dataclass
class _Outcome:
    merge: dict[str, Any]
    survivor_version: int = 0
    absorbed_version: int = 0
    heads: list[RelinkedHead] = dataclasses.field(default_factory=list)
    collapsed: list[HeadRef] = dataclasses.field(default_factory=list)
    both: list[HeadRef] = dataclasses.field(default_factory=list)
    kept: int = 0
    head_count: int = 0
    large: bool = False


@read_transaction
async def _read_pair(
    tx: Transaction, cls: type[Entity], absorb: UUID, into: UUID
) -> tuple[_Found, _Found, Any, Any]:
    """The two entities of a merge, checked: each as it is found, and as it is edited"""
    if str(absorb) == str(into):
        raise PanglossMergeError("An entity cannot be merged into itself")
    found: list[_Found] = []
    for id, role in ((into, "merge into"), (absorb, "absorb")):
        entity = await _find(tx, id)
        if entity is None or (cls is not Entity and cls.__name__ not in entity.labels):
            raise PanglossNotFoundError(
                f"There is no {cls.__name__} with id {id} to {role}"
            )
        if entity.deleted:
            raise PanglossMergeError(
                f"{entity.type} {id} has been deleted: it cannot be merged"
            )
        if entity.merged_into is not None:
            raise PanglossMergeError(
                f"{entity.type} {id} was merged into {entity.merged_into}: merge with that one, or undo that merge"
            )
        found.append(entity)
    survivor, absorbed = found
    views = []
    for entity in found:
        model = _model(entity.type)
        if model is None:
            raise PanglossMergeError(
                f"{entity.type} {entity.id} is not an entity model of now"
            )
        read = await read_entity(
            tx, model, UUID(entity.id), incoming=False, follow_merge=False
        )
        if read is None:
            raise PanglossNotFoundError(f"There is no {entity.type} {entity.id}")
        data, made_as = read
        views.append(made_as.EditView(**data))
    return survivor, absorbed, views[0], views[1]


def _values_given(values: Any) -> dict[str, Any]:
    """What was given as the survivor's fields (an `Update`, or what one takes), as a dict"""
    if hasattr(values, "model_dump"):
        return values.model_dump()
    return dict(values)


async def _prepare(
    cls: type[Entity],
    absorb: UUID,
    into: UUID,
    values: Any = None,
    as_class: type[Entity] | None = None,
    versions: tuple[int | None, int | None] = (None, None),
) -> _Prepared:
    """Read the two entities and check that they can be merged; work out the class and the fields of the survivor;
    ask the installed apps (`hooks.before_merge`) and the class's own checks. Nothing is written"""
    survivor, absorbed, survivor_view, absorbed_view = await _read_pair(
        cls, absorb, into
    )
    for entity, expected, role in (
        (survivor, versions[0], "survivor"),
        (absorbed, versions[1], "absorbed entity"),
    ):
        if expected is not None and entity.version != expected:
            raise PanglossVersionConflictError(
                f"{entity.type} {entity.id} (the {role}) is at version {entity.version}, not {expected}: it has "
                "been updated since it was read",
                current_version=entity.version,
            )
    survivor_model = cast(type[Entity], _model(survivor.type))
    absorbed_model = cast(type[Entity], _model(absorbed.type))
    if as_class is None and hasattr(values, "_owner"):
        as_class = values._owner
    result_model = cast(
        type[Entity], survivor_class(survivor_model, absorbed_model, as_class)
    )

    before = editable(survivor_view.model_dump(mode="json"))
    own = {survivor.id, absorbed.id}
    if values is None:
        chosen = merged_values(
            result_model,
            editable(survivor_view.model_dump()),
            editable(absorbed_view.model_dump()),
        )
    else:
        try:
            given = result_model.Update(
                **cast(
                    dict[str, Any],
                    {**_values_given(values), "id": UUID(survivor.id)},
                )
            )
        except ValidationError as error:
            raise PanglossMergeError(
                f"The values given are not those of a {result_model.__name__}: {error}"
            ) from error
        chosen = given.model_dump()
        for name in result_model._meta.fields.relation_fields:
            if name in chosen:
                chosen[name] = without_references_to(chosen[name], own)
    # (the survivor always has the URLs of both)
    chosen["urls"] = sorted({*survivor.urls, *absorbed.urls})
    try:
        update = result_model.Update(**chosen)
    except ValidationError as error:
        raise PanglossMergeError(
            f"The survivor would not be a valid {result_model.__name__}: {error}"
        ) from error

    await hooks.check_before_merge(
        hooks.MergeRequest(
            survivor=survivor_view,
            absorbed=absorbed_view,
            survivor_model=survivor_model,
            absorbed_model=absorbed_model,
            result_model=result_model,
        )
    )
    db_instance = update._to_db_model()
    await fill_labels(db_instance, read_labels)

    async def as_it_is() -> Any:
        return survivor_view

    await check_before_update(db_instance, as_it_is)
    return _Prepared(
        survivor=survivor.id,
        absorbed=absorbed.id,
        survivor_model=survivor_model,
        absorbed_model=absorbed_model,
        result_model=result_model,
        survivor_version=survivor.version,
        absorbed_version=absorbed.version,
        db_instance=db_instance,
        values=update.model_dump(mode="json"),
        before=json.dumps(before),
    )


async def _checked_in_transaction(
    tx: Transaction, prepared: _Prepared, proposal: str | None = None
) -> tuple[_Found, _Found]:
    """The two entities, read again in the merge's transaction, after their locks are taken: they must be as they
    were when the merge was prepared. And the proposal the merge carries out, if it does, must still be open"""
    # (in one order always, so that two merges of the same pair, either way round, do not wait for each other)
    for id in sorted((prepared.survivor, prepared.absorbed)):
        await dialect().before_replace(tx, id)
    if proposal is not None:
        # (first: of two who verify it at once, the second is told it is carried out, not that an entity changed)
        await _check_open_proposal(tx, proposal)
    survivor = await _find(tx, prepared.survivor)
    absorbed = await _find(tx, prepared.absorbed)
    for entity, id, version in (
        (survivor, prepared.survivor, prepared.survivor_version),
        (absorbed, prepared.absorbed, prepared.absorbed_version),
    ):
        if entity is None or entity.deleted:
            raise PanglossMergeError(f"{id} is no longer there to be merged")
        if entity.merged_into is not None:
            raise PanglossMergeError(
                f"{entity.type} {id} was merged into {entity.merged_into} meanwhile"
            )
        if entity.version != version:
            raise PanglossVersionConflictError(
                f"{entity.type} {id} is at version {entity.version}, not {version}: it was updated while the "
                "merge was being prepared",
                current_version=entity.version,
            )
    assert survivor is not None and absorbed is not None
    return survivor, absorbed


async def _merge_in(
    tx: Transaction,
    prepared: _Prepared,
    limit: int,
    allow_large: bool,
    dry_run: bool,
    only_collapsing: bool,
    proposal: str | None = None,
) -> _Outcome:
    await check_user_exists(tx)
    survivor, absorbed = await _checked_in_transaction(tx, prepared, proposal)
    a, b = survivor.id, absorbed.id
    merge_id = proposal or str(uuid.uuid7())
    when = datetime.datetime.now(datetime.UTC)
    changing_class = prepared.result_model is not prepared.survivor_model
    # (what referred to the absorbed entity must refer to the survivor as the class it will be: looked at only when
    # that class is not the absorbed entity's own, or one below it, which every relation to it can hold)
    check_class = not issubclass(prepared.result_model, prepared.absorbed_model)
    referred = (
        await referrers(tx, prepared.absorbed_model, UUID(b)) if check_class else set()
    )

    # 1. The absorbed entity is marked, and the survivor written, before anything else is: a write that names either
    #    then gives way to this, and is run again (when it finds the mark)
    await (
        await tx.run(
            "MATCH (b:PGIndexableNode {id: $id}) SET b.merged_into = $into",
            id=b,
            into=a,
        )
    ).consume()
    # 2. Its URLs become the survivor's (first: a URL that another entity has is refused when the survivor is written)
    await (
        await tx.run(
            """
            MATCH (b:PGIndexableNode {id: $b})-[had:has_url]->(url:PGUrl)
            MATCH (a:PGIndexableNode {id: $a})
            DELETE had
            MERGE (a)-[:has_url]->(url)
            """,
            a=a,
            b=b,
        )
    ).consume()
    existing_head, _ = await replace_head_in(
        tx,
        prepared.db_instance,
        prepared.survivor_version,
        None,
        prepared.survivor_model if changing_class else None,
    )

    rows = await _incoming(tx, b, a)
    moves = _plan(rows, {a, b})
    if moves.problems:
        raise PanglossMergeError(
            "The merge cannot move everything that refers to the absorbed entity: "
            + "; ".join(moves.problems)
        )
    heads = moves.heads
    large = len(heads) > limit
    if large and not allow_large:
        raise PanglossMergeTooLargeError(
            f"The merge would write {len(heads)} documents and entities, more than {limit} (MERGE_LIMIT): it is "
            "made only as a large merge, by an admin",
            heads=len(heads),
            limit=limit,
        )
    collapsing = sorted({row["head"] for row in moves.rows if row["dropped"]})
    with_survivor = {
        row["head"] for row in await (await tx.run(REFERRING_HEADS_QUERY, id=a)).data()
    }
    both = sorted((set(heads) & with_survivor) - set(collapsing))

    merge = {
        "id": merge_id,
        "survivor": a,
        "absorbed": b,
        "state": "running",
        "by": current_request_username.get(),
        "when": when,
        "survivor_type": prepared.result_model.__name__,
        "survivor_type_before": prepared.survivor_model.__name__,
        "absorbed_type": prepared.absorbed_model.__name__,
        "survivor_label": survivor.label,
        "absorbed_label": absorbed.label,
        "survivor_version": existing_head.version + 1,
        "absorbed_version": absorbed.version,
        "before": prepared.before,
        "urls": absorbed.urls,
        "migrations": await _migrations(tx),
        "heads": 0,
        "moved": 0,
        "dropped": 0,
        "kept": moves.kept,
    }
    outcome = _Outcome(
        merge=merge,
        survivor_version=existing_head.version + 1,
        absorbed_version=absorbed.version,
        kept=moves.kept,
        head_count=len(heads),
        large=large,
        collapsed=await _head_refs(tx, collapsing),
        both=await _head_refs(tx, both),
    )
    if proposal is None:
        await (await tx.run("CREATE (m:PGMerge) SET m = $merge", merge=merge)).consume()
    else:
        await (
            await tx.run(
                "MATCH (m:PGMerge {id: $id}) SET m += $merge", id=merge_id, merge=merge
            )
        ).consume()
    await _overtake_proposals(tx, merge_id, b, absorbed.label)

    # (a large merge moves its edges in batches, each a transaction: here only those of the heads in which the two
    # entities fall together, to see that the heads are still valid, and nothing of it is kept)
    if only_collapsing:
        moves = moves.only(set(collapsing))
    if not large or only_collapsing:
        moved = await _move(tx, merge_id, a, b, moves)
        outcome.heads = moved.heads
        failing = await _invalid_heads(
            tx, [head for head in moved.heads if head.id in set(collapsing)]
        )
        if failing:
            raise PanglossMergeError(
                "The merge would leave documents that are no longer valid, because they name both entities where "
                "they must name two: change them first. " + "; ".join(failing)
            )
    if only_collapsing:
        raise _RolledBack(outcome)
    if not large:
        await _check_nothing_left(tx, a, b, moves.kept)
        if check_class:
            lost = (
                referred
                - await referrers(tx, prepared.result_model, UUID(a))
                - await referrers(tx, prepared.absorbed_model, UUID(b))
            )
            if lost:
                which = ", ".join(
                    f"{type_name} {id} ({name})" for name, type_name, id in sorted(lost)
                )
                raise PanglossMergeError(
                    f"The survivor would be a {prepared.result_model.__name__}, and the absorbed entity is referred "
                    f"to by a relation that cannot hold one: {which}"
                )
        merge.update(
            state="done",
            heads=len(moved.heads),
            moved=moved.moved,
            dropped=moved.dropped,
            finished=datetime.datetime.now(datetime.UTC),
        )
        await _set_merge(tx, merge_id, merge)
    for model, id in ((prepared.result_model, a), (prepared.absorbed_model, b)):
        await pending.mark_written(tx, model, id)
    if dry_run:
        raise _RolledBack(outcome)
    return outcome


# What of a merge's record changes after it is first written
_CHANGING = (
    "state",
    "heads",
    "moved",
    "dropped",
    "finished",
    "undone_by",
    "undone_when",
    "late",
    "rejected_by",
    "rejected_when",
    "reason",
    "undo_proposed_by",
    "undo_proposed_when",
    "undo_note",
    "undo_rejected_by",
    "undo_rejected_reason",
)


async def _check_open_proposal(tx: Transaction, merge_id: str) -> dict[str, Any]:
    """The proposal of a merge, which must still be open, and not this user's own to verify"""
    merge = await _merge_properties(tx, merge_id)
    if merge["state"] != "proposed":
        raise PanglossMergeError(
            f"Merge {merge_id} is {merge['state']}, not proposed: it cannot be verified"
            + (f" ({merge['reason']})" if merge.get("reason") else "")
        )
    if merge.get("proposed_by") == current_request_username.get():
        raise PanglossMergeNotAllowedError(
            "A merge is verified by someone other than the one who proposed it"
        )
    return merge


async def _overtake_proposals(
    tx: Transaction, merge_id: str, absorbed: str, label: str | None
) -> None:
    """The other proposals that involve an entity that is now merged are stale: they say why"""
    reason = f"{label or absorbed} was merged into another entity (merge {merge_id})"
    # (each by its index)
    for role in ("survivor", "absorbed"):
        await (
            await tx.run(
                f"""
                MATCH (m:PGMerge {{{role}: $entity}})
                WHERE m.state = 'proposed' AND m.id <> $id
                SET m.state = 'stale', m.reason = $reason
                """,
                entity=absorbed,
                id=merge_id,
                reason=reason,
            )
        ).consume()


async def _set_merge(
    tx: Transaction, merge_id: str, properties: dict[str, Any]
) -> None:
    changed = {key: value for key, value in properties.items() if key in _CHANGING}
    await (
        await tx.run(
            "MATCH (m:PGMerge {id: $id}) SET m += $changed",
            id=merge_id,
            changed=changed,
        )
    ).consume()


@write_transaction
async def _merge_transaction(
    tx: Transaction,
    prepared: _Prepared,
    limit: int,
    allow_large: bool,
    dry_run: bool = False,
    only_collapsing: bool = False,
    proposal: str | None = None,
) -> _Outcome:
    return await _merge_in(
        tx, prepared, limit, allow_large, dry_run, only_collapsing, proposal
    )


@write_transaction
async def _batch_transaction(
    tx: Transaction, merge_id: str, limit: int | None, late: bool
) -> _Moved:
    """A batch of a large merge (or its second pass, `late`): the edges of up to `limit` heads that are still on the
    absorbed entity go to the survivor. Nothing, if the merge no longer stands"""
    await check_user_exists(tx)
    merge = await _merge_properties(tx, merge_id)
    wanted = ("done",) if late else ("running",)
    if merge["state"] not in wanted:
        return _Moved()
    a, b = merge["survivor"], merge["absorbed"]
    absorbed = await _find(tx, b)
    if absorbed is None or absorbed.merged_into != a:
        return _Moved()
    moves = _plan(await _incoming(tx, b, a), {a, b})
    if moves.problems:
        raise PanglossMergeError("; ".join(moves.problems))
    if limit is not None:
        moves = moves.only(set(moves.heads[:limit]))
    if not moves.rows:
        return _Moved()
    moved = await _move(tx, merge_id, a, b, moves, late=late)
    await (
        await tx.run(
            """
            MATCH (m:PGMerge {id: $id})
            SET m.heads = coalesce(m.heads, 0) + $heads, m.moved = coalesce(m.moved, 0) + $moved,
                m.dropped = coalesce(m.dropped, 0) + $dropped,
                m.late = coalesce(m.late, 0) + $late
            """,
            id=merge_id,
            heads=len(moved.heads),
            moved=moved.moved,
            dropped=moved.dropped,
            late=moved.moved + moved.dropped if late else 0,
        )
    ).consume()
    return moved


@write_transaction
async def _finish_transaction(tx: Transaction, merge_id: str) -> dict[str, Any]:
    """The end of a large merge: nothing may be left on the absorbed entity but what is kept"""
    merge = await _merge_properties(tx, merge_id)
    if merge["state"] != "running":
        return merge
    await _check_nothing_left(
        tx, merge["survivor"], merge["absorbed"], merge.get("kept") or 0
    )
    merge.update(state="done", finished=datetime.datetime.now(datetime.UTC))
    await _set_merge(tx, merge_id, merge)
    return merge


async def _giving_way(run: Any, *args: Any, **kwargs: Any) -> Any:
    """Run a transaction of a merge. One that keeps giving way to other writes until the driver stops trying is a
    merge that cannot be made now (`PanglossMergeBusyError`)"""
    try:
        return await run(*args, **kwargs)
    except neo4j.exceptions.Neo4jError as error:
        if not error.is_retryable():
            raise
        raise PanglossMergeBusyError(
            "The merge gave way to other writes of the same entities and documents until it ran out of time: "
            "nothing was merged. Try again when they are done"
        ) from error


async def _running_merge(absorb: UUID, into: UUID) -> str | None:
    """The id of a large merge of this pair that stopped before its batches were all made, if there is one"""
    for merge in await merges_of_entity(Entity, absorb):
        if merge.state == "running" and merge.survivor == into:
            return str(merge.id)
    return None


async def _batches(merge_id: str, limit: int) -> list[RelinkedHead]:
    heads: list[RelinkedHead] = []
    while True:
        moved = await _giving_way(_batch_transaction, merge_id, limit, False)
        if not moved.heads:
            return heads
        heads += moved.heads
        await announce_relinked(moved.heads)


async def merge_entities(
    cls: type[Entity],
    absorb: UUID,
    into: UUID,
    *,
    values: Any = None,
    as_class: type[Entity] | None = None,
    version_into: int | None = None,
    version_absorb: int | None = None,
    allow_large: bool = False,
    _proposal: str | None = None,
) -> MergeResult:
    """Merge the entity `absorb` into the entity `into` (`Person.merge(absorb=b, into=a)`): everything that refers to
    the first refers to the second, which has the fields given (`values`: an `Update`, or what one takes; by default
    `pangloss_models.merging.merged_values`) and the URLs of both; the first is kept as it is, marked as merged, and
    reads and writes that name it find the second. It can be undone (`unmerge`).

    `as_class`: the class the survivor takes, when the two differ (by default the narrower). `version_into` and
    `version_absorb`: the versions the merge was decided on; if either has changed, nothing is written
    (`PanglossVersionConflictError`). `allow_large`: a merge that writes more heads than `MERGE_LIMIT` is refused
    (`PanglossMergeTooLargeError`) unless this is given; it is then made in batches, and if it stops part of the
    way, calling this again goes on with it (or `unmerge` takes it back).

    Raises `PanglossMergeError`, with the reason, if the merge cannot be made."""
    limit = merge_limit()
    absorb, into = UUID(str(absorb)), UUID(str(into))
    resumed = await _running_merge(absorb, into) if allow_large else None
    if resumed is not None:
        await _batches(resumed, limit)
        await _giving_way(_finish_transaction, resumed)
        late = await _second_pass(resumed)
        return MergeResult(merge=await get_merge(resumed), late=late)

    # (decided on no versions, a merge that finds an entity changed under it is prepared again: another merge into the
    # same survivor has just been made)
    attempts = 1 if (version_into, version_absorb) != (None, None) else MERGE_ATTEMPTS
    for attempt in range(1, attempts + 1):
        prepared = await _prepare(
            cls, absorb, into, values, as_class, (version_into, version_absorb)
        )
        try:
            if allow_large:
                # (what a large merge cannot take back once its batches are made is looked at first, and rolled back)
                try:
                    await _giving_way(
                        _merge_transaction,
                        prepared,
                        limit,
                        True,
                        True,
                        only_collapsing=True,
                        proposal=_proposal,
                    )
                except _RolledBack:
                    pass
            outcome: _Outcome = await _giving_way(
                _merge_transaction, prepared, limit, allow_large, proposal=_proposal
            )
            break
        except PanglossVersionConflictError:
            if attempt == attempts:
                raise
            await asyncio.sleep(MERGE_ATTEMPT_WAIT * attempt * (1 + random.random()))
    merge_id = outcome.merge["id"]
    note = hooks.MergeNote(
        id=UUID(merge_id),
        survivor=UUID(prepared.survivor),
        absorbed=UUID(prepared.absorbed),
    )
    announce(
        "update",
        prepared.result_model,
        UUID(prepared.survivor),
        outcome.survivor_version,
        prepared.db_instance,
        changed_class_from=prepared.survivor_model
        if prepared.result_model is not prepared.survivor_model
        else None,
        merge=note,
    )
    announce(
        "merge",
        prepared.absorbed_model,
        UUID(prepared.absorbed),
        outcome.absorbed_version,
        merge=note,
    )
    await announce_relinked(outcome.heads)
    if outcome.large:
        await _batches(merge_id, limit)
        await _giving_way(_finish_transaction, merge_id)
    late = await _second_pass(merge_id)
    return MergeResult(
        merge=await get_merge(merge_id),
        collapsed=outcome.collapsed,
        both=outcome.both,
        kept=outcome.kept,
        late=late,
    )


# --- the second pass --------------------------------------------------------------------------------------------------


async def merge_second_pass(merge_id: UUID | str) -> int:
    """Move to the survivor of a merge the references that are on the absorbed entity though the merge is done: made
    by a write that was under way when the merge committed, or by one that does not resolve merged ids. Each is
    recorded with the merge, so that an undo puts it back. Gives how many heads it wrote"""
    moved: _Moved = await _giving_way(_batch_transaction, str(merge_id), None, True)
    if moved.heads:
        logger.warning(
            "Merge %s: %s references were on the absorbed entity after the merge, and were moved to the survivor",
            merge_id,
            moved.moved + moved.dropped,
        )
        await announce_relinked(moved.heads)
    return len(moved.heads)


def second_pass_delay() -> float:
    if SECOND_PASS_DELAY is not None:
        return SECOND_PASS_DELAY
    setting = getattr(current().settings, "MERGE_SECOND_PASS_SECONDS", None)
    return float(setting if setting is not None else dialect().merge_second_pass_delay)


async def _second_pass(merge_id: str) -> int:
    """The second pass of a merge, at once; and, where the database may still have a write open that began before
    the merge committed, again after a while (not awaited)"""
    late = await merge_second_pass(merge_id)
    delay = second_pass_delay()
    if delay > 0:
        database = current()

        async def later() -> None:
            from pangloss_cypher.transactions import using

            await asyncio.sleep(delay)
            try:
                with using(database):
                    await merge_second_pass(merge_id)
            except Exception:
                logger.exception("The delayed second pass of merge %s failed", merge_id)

        task = asyncio.get_running_loop().create_task(later())
        _second_passes.add(task)
        task.add_done_callback(_second_passes.discard)
    return late


async def settle_second_passes() -> None:
    """Wait for the delayed second passes that are under way in this loop (a server that is stopping; a test)"""
    loop = asyncio.get_running_loop()
    waiting = [task for task in _second_passes if task.get_loop() is loop]
    if waiting:
        await asyncio.gather(*waiting, return_exceptions=True)


# --- the preview --------------------------------------------------------------------------------------------------------


@read_transaction
async def _counts(tx: Transaction, id: str) -> dict[str, int]:
    result = await tx.run(COUNTS_QUERY, id=id)
    return {row["type"]: row["heads"] for row in await result.data()}


async def preview_merge(
    cls: type[Entity],
    absorb: UUID,
    into: UUID,
    *,
    values: Any = None,
    as_class: type[Entity] | None = None,
) -> MergePreview:
    """What `merge` would do with the same arguments, writing nothing: whether it can be made and if not why, the
    class and the fields the survivor would have, how many heads would be written, and the heads to look at. (The
    merge is made in a transaction that is rolled back, so what it says is what would happen; a merge over
    `MERGE_LIMIT` is counted, not tried.)"""
    limit = merge_limit()
    absorb, into = UUID(str(absorb)), UUID(str(into))
    preview = MergePreview(survivor=into, absorbed=absorb, limit=limit)
    try:
        prepared = await _prepare(cls, absorb, into, values, as_class)
    except PanglossMergeError as error:
        preview.refused.append(str(error))
        return preview
    preview.survivor_type = prepared.result_model.__name__
    preview.values = prepared.values
    preview.refer_to_survivor = await _counts(prepared.survivor)
    preview.refer_to_absorbed = await _counts(prepared.absorbed)
    try:
        await _giving_way(_merge_transaction, prepared, limit, True, True)
    except _RolledBack as rolled_back:
        outcome: _Outcome = rolled_back.outcome
        preview.heads = outcome.head_count
        preview.large = outcome.large
        preview.collapsed = outcome.collapsed
        preview.both = outcome.both
        preview.kept = outcome.kept
    except PanglossMergeBusyError:
        raise
    except PanglossMergeError as error:
        preview.refused.append(str(error))
    except PanglossWriteError as error:
        preview.refused.append(str(error))
    return preview


# --- undoing ------------------------------------------------------------------------------------------------------------

MOVES_QUERY = f"""
    MATCH (move:PGMergeMove {{pg_merge: $merge}})
    RETURN move.pg_source AS source, move.pg_source_type AS source_type, move.pg_head AS head,
           move.pg_field AS field, move.pg_reverse AS reverse, coalesce(move.pg_dropped, false) AS dropped,
           move.{POSITION} AS position
"""


def _state_query(field: str) -> str:
    edge = field_edge(field)
    return f"""
    UNWIND $sources AS id
    OPTIONAL MATCH (e:PGIndexableNode {{id: id}})
    OPTIONAL MATCH (head:HeadNode {{id: coalesce(e.head_node_id, e.id)}})
    RETURN id, e IS NOT NULL AS found, {fragments.deleted("head")} AS deleted,
           size([(e)-[x:{edge}]->(:PGIndexableNode {{id: $survivor}}) WHERE NOT coalesce(x.reverse, false) | 1]) AS to_survivor,
           size([(e)-[x:{edge}]->(:PGIndexableNode {{id: $absorbed}}) WHERE NOT coalesce(x.reverse, false) | 1]) AS to_absorbed
    """


async def _restore_dropped(
    tx: Transaction,
    merge_id: str,
    field: str,
    reverse: str,
    target: str,
    sources: list[str],
) -> None:
    """The edges that a merge dropped from the nodes `sources` are made again, to `target`, from their records"""
    forward, backward = field_edge(field), field_edge(reverse)
    await (
        await tx.run(
            f"""
            UNWIND $sources AS source
            MATCH (move:PGMergeMove {{pg_merge: $merge}})
            WHERE move.pg_source = source AND move.pg_field = $field AND move.pg_dropped
            MATCH (e:PGIndexableNode {{id: source}})
            MATCH (b:PGIndexableNode {{id: $target}})
            CREATE (e)-[new:{forward}]->(b)
            SET new = properties(move)
            REMOVE {_REMOVE_RECORD}
            CREATE (e)<-[new_reverse:{backward}]-(b)
            SET new_reverse = properties(move), new_reverse.reverse = true
            REMOVE {_REMOVE_RECORD_REVERSE}
            """,  # ty: ignore[invalid-argument-type]
            sources=sources,
            merge=merge_id,
            field=field,
            target=target,
        )
    ).consume()


MADE_SINCE_QUERY = cast(
    LiteralString,
    f"""
    MATCH (:PGIndexableNode {{id: $id}})<-[edge]-(source:PGIndexableNode)
    WHERE NOT coalesce(edge.reverse, false)
    WITH DISTINCT coalesce(source.head_node_id, source.id) AS head_id
    WHERE NOT head_id IN $restored
    MATCH (head:HeadNode {{id: head_id}})
    WHERE {fragments.not_deleted("head")}
    OPTIONAL MATCH (head)<-[:is_creation_of]-(creation:PGCreation)
    WITH head, creation.created_when AS created,
         [(head)<-[:is_update_of]-(update:PGUpdate) | update.updated_when] AS updates
    WHERE created > $since OR any(updated IN updates WHERE updated > $since)
    RETURN head.id AS id, head.type AS type, head.label AS label
    ORDER BY toLower(coalesce(head.label, '')), id
    LIMIT {MAX_HEADS_NAMED}
""",
)


@dataclasses.dataclass
class _Undo:
    merge: dict[str, Any]
    result: UnmergeResult
    heads: list[RelinkedHead] = dataclasses.field(default_factory=list)
    survivor_version: int | None = None
    restored_instance: Any = None
    restored_from: type | None = None


def _fields_before(
    merge: dict[str, Any],
) -> tuple[type[Entity] | None, Any, str | None]:
    """The survivor's fields as they were before the merge, as an `Update` of the class it was: (the class, the
    update, or why there is none)"""
    model = _model(merge.get("survivor_type_before"))
    if model is None:
        return (
            None,
            None,
            f"{merge.get('survivor_type_before')} is no longer an entity model",
        )
    try:
        return model, model.Update(**json.loads(merge["before"])), None
    except ValidationError as error:
        return model, None, f"what it held is no longer valid: {error}"


async def _unmerge_in(
    tx: Transaction,
    merge_id: str,
    restore_fields: bool,
    confirm_migrated: bool,
    dry_run: bool,
    db_instance: Any,
    accepting: bool = False,
) -> _Undo:
    await check_user_exists(tx)
    merge = await _merge_properties(tx, merge_id)
    a, b = merge["survivor"], merge["absorbed"]
    for id in sorted((a, b)):
        await dialect().before_replace(tx, id)
    merge = await _merge_properties(tx, merge_id)
    if merge["state"] not in ("done", "running"):
        raise PanglossMergeError(
            f"Merge {merge_id} is {merge['state']}: it cannot be undone"
        )
    if accepting and not dry_run:
        if merge.get("undo_proposed_by") is None:
            raise PanglossMergeNotAllowedError(
                f"Nobody has proposed that merge {merge_id} be undone: propose it, for someone else to accept"
            )
        if merge["undo_proposed_by"] == current_request_username.get():
            raise PanglossMergeNotAllowedError(
                "The undoing of a merge is accepted by someone other than the one who proposed it"
            )
    survivor, absorbed = await _find(tx, a), await _find(tx, b)
    if survivor is None or absorbed is None:
        raise PanglossMergeError(
            f"The entities of merge {merge_id} are no longer there"
        )
    if absorbed.merged_into != a:
        raise PanglossMergeError(
            f"{absorbed.type} {b} is not merged into {a}: merge {merge_id} does not stand"
        )
    if survivor.merged_into is not None:
        raise PanglossMergeError(
            f"{survivor.type} {a} was itself merged into {survivor.merged_into} since: undo that merge first"
        )
    if survivor.deleted:
        raise PanglossMergeError(
            f"{survivor.type} {a} has been deleted: undelete it, and then the merge can be undone"
        )
    if not confirm_migrated and merge.get("migrations") != await _migrations(tx):
        raise PanglossMergeError(
            "The database has been migrated since the merge, so the moves it recorded may name fields that have "
            "changed: look at what can be put back (a dry run), and then undo it with `confirm_migrated`"
        )

    moves = await (await tx.run(MOVES_QUERY, merge=merge_id)).data()
    # (the merges of others into the same survivor that stand: what they dropped is the survivor's own)
    others = [
        row["id"]
        for row in await (
            await tx.run(
                "MATCH (m:PGMerge {survivor: $a}) WHERE m.state IN ['done', 'running'] AND m.id <> $id "
                "RETURN m.id AS id",
                a=a,
                id=merge_id,
            )
        ).data()
    ]
    result = UnmergeResult(merge=_record(merge))
    by_group: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for move in moves:
        by_group.setdefault((move["field"], move["reverse"]), []).append(move)

    restored_heads: set[str] = set()
    for (field, reverse), group in sorted(by_group.items()):
        sources = sorted({move["source"] for move in group})
        states = {
            row["id"]: row
            for row in await (
                await tx.run(
                    _state_query(field),  # ty: ignore[invalid-argument-type]
                    sources=sources,
                    survivor=a,
                    absorbed=b,
                )
            ).data()
        }
        back: list[str] = []
        again: list[str] = []
        seen: set[tuple[str, bool]] = set()
        for move in group:
            state = states[move["source"]]
            reason = (
                "gone"
                if not state["found"]
                else "deleted"
                if state["deleted"]
                else "changed"
                if state["to_survivor"] == 0
                else None
            )
            if reason is not None:
                result.unmatched.append(
                    {
                        "source": move["source"],
                        "source_type": move["source_type"],
                        "head": move["head"],
                        "field": field,
                        "reason": reason,
                    }
                )
                continue
            result.restored += 1
            restored_heads.add(move["head"])
            key = (move["source"], move["dropped"])
            if key in seen:
                continue
            seen.add(key)
            (again if move["dropped"] else back).append(move["source"])
        # (the heads are locked before they are written, as in the merge)
        if back:
            # What another merge that stands dropped from these nodes is the edge that is now going back: the node
            # then keeps the survivor by that merge, which no longer has it as dropped
            kept_by_other = (
                [
                    row["source"]
                    for row in await (
                        await tx.run(
                            """
                            UNWIND $others AS other
                            MATCH (move:PGMergeMove {pg_merge: other})
                            WHERE move.pg_field = $field AND move.pg_dropped AND move.pg_source IN $sources
                            RETURN DISTINCT move.pg_source AS source
                            """,
                            others=others,
                            field=field,
                            sources=back,
                        )
                    ).data()
                ]
                if others
                else []
            )
            await move_edges(tx, field, reverse, a, b, back, unless_there=True)
            for other in others:
                if kept_by_other:
                    await _restore_dropped(tx, other, field, reverse, a, kept_by_other)
                    await (
                        await tx.run(
                            """
                            MATCH (move:PGMergeMove {pg_merge: $other})
                            WHERE move.pg_field = $field AND move.pg_dropped AND move.pg_source IN $sources
                            SET move.pg_dropped = false
                            """,
                            other=other,
                            field=field,
                            sources=kept_by_other,
                        )
                    ).consume()
        if again:
            # (not where the node has the relation to the absorbed entity already)
            wanted = [s for s in again if states[s]["to_absorbed"] == 0]
            if wanted:
                await _restore_dropped(tx, merge_id, field, reverse, b, wanted)

    heads = sorted(restored_heads)
    for head in heads:
        await dialect().before_replace(tx, head)
    undo = _Undo(merge=merge, result=result)
    undo.heads = await record_updates(tx, heads)
    result.heads = len(undo.heads)

    # The absorbed entity's URLs go back (before the survivor's fields: an update of it removes the URLs it is not
    # given)
    await (
        await tx.run(
            """
            MATCH (a:PGIndexableNode {id: $a})-[had:has_url]->(url:PGUrl)
            WHERE url.url IN $urls
            MATCH (b:PGIndexableNode {id: $b})
            DELETE had
            MERGE (b)-[:has_url]->(url)
            """,
            a=a,
            b=b,
            urls=merge.get("urls") or [],
        )
    ).consume()
    await (
        await tx.run("MATCH (b:PGIndexableNode {id: $id}) REMOVE b.merged_into", id=b)
    ).consume()

    # The survivor's fields: put back only if it has not changed since the merge (nor absorbed another); otherwise
    # they are given as they were, for a person to reconcile with what it has now
    unchanged = survivor.version == merge.get("survivor_version") and not others
    before_model, _, why_not = _fields_before(merge)
    if restore_fields and unchanged and db_instance is not None:
        now_model = _model(survivor.type)
        try:
            existing_head, _ = await replace_head_in(
                tx,
                db_instance,
                survivor.version,
                None,
                now_model if now_model is not before_model else None,
            )
        except PanglossWriteError as error:
            raise _FieldsNotRestored(str(error)) from error
        result.fields_restored = True
        undo.survivor_version = existing_head.version + 1
        undo.restored_instance = db_instance
        undo.restored_from = now_model if now_model is not before_model else None
    else:
        result.draft = json.loads(merge["before"])
        result.draft_type = merge.get("survivor_type_before")
        result.draft_reason = (
            why_not
            if db_instance is None and why_not
            else "it has been changed since the merge"
            if not unchanged
            else "its fields could not be written as they were"
        )

    result.made_since = [
        HeadRef(id=UUID(row["id"]), type=row["type"], label=row["label"])
        for row in await (
            await tx.run(
                MADE_SINCE_QUERY,
                id=a,
                restored=heads,
                since=merge.get("finished") or merge.get("when"),
            )
        ).data()
    ]

    merge.update(
        state="undone",
        undone_by=current_request_username.get(),
        undone_when=datetime.datetime.now(datetime.UTC),
    )
    await _set_merge(tx, merge_id, merge)
    result.merge = _record(merge)
    for type_name, id in ((survivor.type, a), (absorbed.type, b)):
        model = _model(type_name)
        if model is not None:
            await pending.mark_written(tx, model, id)
    undo.merge = merge
    if dry_run:
        raise _RolledBack(undo)
    return undo


@write_transaction
async def _unmerge_transaction(
    tx: Transaction,
    merge_id: str,
    restore_fields: bool,
    confirm_migrated: bool,
    dry_run: bool,
    db_instance: Any,
    accepting: bool = False,
) -> _Undo:
    return await _unmerge_in(
        tx, merge_id, restore_fields, confirm_migrated, dry_run, db_instance, accepting
    )


async def unmerge_entities(
    cls: type[Entity],
    merge_id: UUID | str,
    *,
    confirm_migrated: bool = False,
    dry_run: bool = False,
    accepting: bool = False,
) -> UnmergeResult:
    """Undo a merge (`Person.unmerge(merge_id)`): the references it moved go back to the absorbed entity, where the
    node that held each is still there, not deleted, and still points at the survivor (the rest are listed:
    `unmatched`); the absorbed entity has its URLs again and is no longer merged; the survivor's fields are put back
    as they were if it has not changed since, and otherwise given as a draft. What was written to the survivor since
    the merge stays on it (`made_since`).

    Refused (`PanglossMergeError`) if the survivor has itself been merged into another since (undo that first), or
    is deleted (undelete it first). If the database has been migrated since the merge, the moves recorded may no
    longer fit: it is undone only with `confirm_migrated`. `dry_run`: what it would do, writing nothing.
    `accepting`: only if someone else proposed that it be undone (`propose_unmerge`); if not,
    `PanglossMergeNotAllowedError`."""
    merge_id = str(merge_id)
    record = await _giving_way(_merge_record_for_undo, merge_id)
    _, update, _ = _fields_before(record)
    db_instance = None
    if update is not None:
        db_instance = update._to_db_model()
        await fill_labels(db_instance, read_labels)
    try:
        try:
            undo: _Undo = await _giving_way(
                _unmerge_transaction,
                merge_id,
                True,
                confirm_migrated,
                dry_run,
                db_instance,
                accepting,
            )
        except _FieldsNotRestored as not_restored:
            undo = await _giving_way(
                _unmerge_transaction,
                merge_id,
                False,
                confirm_migrated,
                dry_run,
                None,
                accepting,
            )
            undo.result.draft_reason = not_restored.reason
    except _RolledBack as rolled_back:
        return rolled_back.outcome.result

    merge = undo.merge
    note = hooks.MergeNote(
        id=UUID(merge_id),
        survivor=UUID(merge["survivor"]),
        absorbed=UUID(merge["absorbed"]),
        undone=True,
    )
    if undo.restored_instance is not None and undo.survivor_version is not None:
        announce(
            "update",
            undo.restored_instance._owner,
            UUID(merge["survivor"]),
            undo.survivor_version,
            undo.restored_instance,
            changed_class_from=undo.restored_from,
            merge=note,
        )
    absorbed_model = _model(merge.get("absorbed_type"))
    if absorbed_model is not None:
        announce(
            "unmerge",
            absorbed_model,
            UUID(merge["absorbed"]),
            merge.get("absorbed_version") or 1,
            merge=note,
        )
    await announce_relinked(undo.heads)
    return undo.result


@read_transaction
async def _merge_record_for_undo(tx: Transaction, merge_id: str) -> dict[str, Any]:
    return await _merge_properties(tx, merge_id)


# --- proposing, verifying, rejecting ----------------------------------------------------------------------------------


@write_transaction
async def _write_proposal(tx: Transaction, merge: dict[str, Any]) -> dict[str, Any]:
    await check_user_exists(tx)
    merge["migrations"] = await _migrations(tx)
    await (await tx.run("CREATE (m:PGMerge) SET m = $merge", merge=merge)).consume()
    return merge


async def propose_merge(
    cls: type[Entity],
    absorb: UUID,
    into: UUID,
    *,
    values: Any = None,
    as_class: type[Entity] | None = None,
    note: str | None = None,
) -> MergeRecord:
    """Propose that `absorb` be merged into `into`, for someone else to verify (`verify_merge`) or reject
    (`reject_merge`): the merge is checked as `merge_preview` checks it, and recorded with the fields chosen, the
    versions of the two entities and who proposed it. Nothing else is written.

    Raises `PanglossMergeError` if the merge could not be made as things are."""
    preview = await preview_merge(cls, absorb, into, values=values, as_class=as_class)
    if not preview.possible:
        raise PanglossMergeError("; ".join(preview.refused))
    prepared = await _prepare(cls, UUID(str(absorb)), UUID(str(into)), values, as_class)
    survivor_label = json.loads(prepared.before).get("label")
    merge = await _write_proposal(
        {
            "id": str(uuid.uuid7()),
            "survivor": prepared.survivor,
            "absorbed": prepared.absorbed,
            "state": "proposed",
            "proposed_by": current_request_username.get(),
            "proposed_when": datetime.datetime.now(datetime.UTC),
            "note": note,
            "survivor_type": prepared.result_model.__name__,
            "survivor_type_before": prepared.survivor_model.__name__,
            "absorbed_type": prepared.absorbed_model.__name__,
            "survivor_label": survivor_label,
            "absorbed_label": await _label_of(prepared.absorbed),
            "proposed_survivor_version": prepared.survivor_version,
            "proposed_absorbed_version": prepared.absorbed_version,
            "proposed_values": json.dumps(prepared.values),
            "heads": preview.heads,
        }
    )
    return _record(merge)


@read_transaction
async def _label_of(tx: Transaction, id: str) -> str | None:
    found = await _find(tx, id)
    return found.label if found is not None else None


@write_transaction
async def _close_proposal(
    tx: Transaction, merge_id: str, state: str, reason: str | None, by: str | None
) -> dict[str, Any]:
    merge = await _merge_properties(tx, merge_id)
    if merge["state"] != "proposed":
        raise PanglossMergeError(
            f"Merge {merge_id} is {merge['state']}, not proposed: it cannot be {state}"
        )
    merge.update(
        state=state,
        reason=reason,
        rejected_by=by,
        rejected_when=datetime.datetime.now(datetime.UTC) if by else None,
    )
    await _set_merge(tx, merge_id, merge)
    return merge


@read_transaction
async def _migrations_now(tx: Transaction) -> str:
    return await _migrations(tx)


async def verify_merge(
    merge_id: UUID | str,
    *,
    values: Any = None,
    as_class: type[Entity] | None = None,
    version_into: int | None = None,
    version_absorb: int | None = None,
    allow_large: bool = False,
) -> MergeResult:
    """Carry out a merge that someone else proposed (`propose_merge`), with the fields they chose or those given
    here (`values`). The one who proposed it cannot (`PanglossMergeNotAllowedError`). The merge is checked again.

    If either entity has changed since it was proposed, the fields chosen then may undo the change: it is refused
    (`PanglossVersionConflictError`) unless `values` are given, with the versions they were decided on. A proposal
    from before a migration is stale, and refused."""
    merge_id = str(merge_id)
    proposal = await _giving_way(_merge_record_for_undo, merge_id)
    if proposal["state"] != "proposed":
        raise PanglossMergeError(
            f"Merge {merge_id} is {proposal['state']}, not proposed: it cannot be verified"
            + (f" ({proposal['reason']})" if proposal.get("reason") else "")
        )
    if proposal.get("proposed_by") == current_request_username.get():
        raise PanglossMergeNotAllowedError(
            "A merge is verified by someone other than the one who proposed it"
        )
    if proposal.get("migrations") != await _migrations_now():
        reason = "the database was migrated since it was proposed: propose it again"
        await _close_proposal(merge_id, "stale", reason, None)
        raise PanglossMergeError(f"Merge {merge_id} is stale: {reason}")
    if values is None:
        values = json.loads(proposal["proposed_values"])
        version_into = proposal.get("proposed_survivor_version")
        version_absorb = proposal.get("proposed_absorbed_version")
        if as_class is None:
            as_class = _model(proposal.get("survivor_type"))
    return await merge_entities(
        Entity,
        UUID(proposal["absorbed"]),
        UUID(proposal["survivor"]),
        values=values,
        as_class=as_class,
        version_into=version_into,
        version_absorb=version_absorb,
        allow_large=allow_large,
        _proposal=merge_id,
    )


async def reject_merge(merge_id: UUID | str, reason: str | None = None) -> MergeRecord:
    """Reject a merge that was proposed: it is kept, with who rejected it and why"""
    return _record(
        await _close_proposal(
            str(merge_id), "rejected", reason, current_request_username.get()
        )
    )


@write_transaction
async def _set_undo_proposal(
    tx: Transaction, merge_id: str, changes: dict[str, Any], proposing: bool
) -> dict[str, Any]:
    await check_user_exists(tx)
    merge = await _merge_properties(tx, merge_id)
    if merge["state"] != "done":
        raise PanglossMergeError(
            f"Merge {merge_id} is {merge['state']}: there is nothing to undo"
        )
    if not proposing and merge.get("undo_proposed_by") is None:
        raise PanglossMergeError(f"Nobody has proposed that merge {merge_id} be undone")
    merge.update(changes)
    await _set_merge(tx, merge_id, merge)
    return merge


async def propose_unmerge(merge_id: UUID | str, note: str | None = None) -> MergeRecord:
    """Propose that a merge be undone, for someone else to accept (`unmerge(merge_id, accepting=True)`) or reject
    (`reject_unmerge`). Refused (`PanglossMergeError`) if it could not be undone as things are"""
    merge_id = str(merge_id)
    # (what an undo would refuse is said now; a migration since is for the one who accepts to confirm)
    await unmerge_entities(Entity, merge_id, confirm_migrated=True, dry_run=True)
    return _record(
        await _set_undo_proposal(
            merge_id,
            {
                "undo_proposed_by": current_request_username.get(),
                "undo_proposed_when": datetime.datetime.now(datetime.UTC),
                "undo_note": note,
                "undo_rejected_by": None,
                "undo_rejected_reason": None,
            },
            True,
        )
    )


async def reject_unmerge(
    merge_id: UUID | str, reason: str | None = None
) -> MergeRecord:
    """Reject the proposal that a merge be undone: the merge stands, and the record says who rejected it and why"""
    return _record(
        await _set_undo_proposal(
            str(merge_id),
            {
                "undo_proposed_by": None,
                "undo_proposed_when": None,
                "undo_note": None,
                "undo_rejected_by": current_request_username.get(),
                "undo_rejected_reason": reason,
            },
            False,
        )
    )


@read_transaction
async def list_merges(
    tx: Transaction,
    states: list[str] | None = None,
    undo_proposed: bool = False,
    skip: int = 0,
    limit: int = 50,
) -> tuple[list[MergeRecord], int]:
    """The merges recorded, the latest first, and how many there are: those in one of `states` (all, if none are
    named), together with (`undo_proposed`) those that someone has proposed be undone"""
    # (a merge's id is a UUID7: in the order they were made. There are few of them: no index is used)
    condition = (
        "true"
        if not states and not undo_proposed
        else "m.state IN $states"
        + (
            " OR (m.state = 'done' AND m.undo_proposed_by IS NOT NULL)"
            if undo_proposed
            else ""
        )
    )
    result = await tx.run(
        f"""
        MATCH (m:PGMerge) WHERE {condition}
        WITH m ORDER BY m.id DESC
        WITH collect(properties(m)) AS merges
        RETURN size(merges) AS total, merges[$skip..$end] AS merges
        """,
        states=states or [],
        skip=skip,
        end=skip + limit,
    )
    row = await result.single()
    if row is None:
        return [], 0
    return [_record(merge) for merge in row["merges"]], row["total"]


# --- what is left on merged entities (`pangloss check-data`) -------------------------------------------------------------

STRAY_QUERY = cast(
    LiteralString,
    """
    MATCH (b:Entity) WHERE b.merged_into IS NOT NULL
    MATCH (b)<-[edge]-(source:PGIndexableNode)
    WHERE NOT coalesce(edge.reverse, false)
    RETURN b.id AS absorbed, b.type AS absorbed_type, b.label AS absorbed_label, b.merged_into AS survivor,
           source.id AS source, source.type AS source_type, type(edge) AS field,
           coalesce(source.head_node_id, source.id) AS head
    ORDER BY absorbed, head, source, field
    """,
)


@dataclasses.dataclass
class StrayReference:
    """A reference to an entity that has been merged into another, by a relation that a merge moves: one that a write
    made without resolving the id (the models' writes resolve it)"""

    absorbed: UUID
    absorbed_type: str
    absorbed_label: str | None
    survivor: UUID
    head: UUID
    head_type: str | None
    source_type: str
    field: str
    merge: UUID | None
    """The merge that stands of the absorbed entity, whose second pass moves the reference (None: the entity is
    marked as merged and no merge of it stands, which no operation of Pangloss leaves)"""


@read_transaction
async def stray_references(tx: Transaction) -> list[StrayReference]:
    """Every reference to a merged entity that a merge would have moved (not those of `KeepOnMerge()` fields, nor of
    the entity's own survivor)"""
    rows = await (await tx.run(STRAY_QUERY)).data()
    if not rows:
        return []
    models = ModelRegistry.all_models()
    standing: dict[str, str | None] = {}
    head_types: dict[str, str | None] = {}
    by_source: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for row in rows:
        by_source.setdefault((row["absorbed"], row["source"]), []).append(row)
    found: list[StrayReference] = []
    for (absorbed, _), source_rows in by_source.items():
        first = source_rows[0]
        if first["head"] in (absorbed, first["survivor"]):
            continue
        model = models.get(first["source_type"])
        kept = (
            _kept_edges(model, {row["field"] for row in source_rows})
            if isinstance(model, type)
            else set()
        )
        for row in source_rows:
            if row["field"] in kept:
                continue
            if absorbed not in standing:
                merges = await (
                    await tx.run(
                        "MATCH (m:PGMerge {absorbed: $id}) WHERE m.state IN ['done', 'running'] "
                        "RETURN m.id AS id ORDER BY m.id DESC LIMIT 1",
                        id=absorbed,
                    )
                ).data()
                standing[absorbed] = merges[0]["id"] if merges else None
            if row["head"] not in head_types:
                refs = await _head_refs(tx, [row["head"]])
                head_types[row["head"]] = refs[0].type if refs else None
            merge = standing[absorbed]
            found.append(
                StrayReference(
                    absorbed=UUID(absorbed),
                    absorbed_type=row["absorbed_type"],
                    absorbed_label=row["absorbed_label"],
                    survivor=UUID(row["survivor"]),
                    head=UUID(row["head"]),
                    head_type=head_types[row["head"]],
                    source_type=row["source_type"],
                    field=row["field"],
                    merge=UUID(merge) if merge else None,
                )
            )
    return found


async def move_stray_references() -> int:
    """Move every stray reference to the survivor of its merge (the merge's second pass, so each is recorded and an
    undo puts it back). The merges are taken in the order they were made, so that what is on an entity that was
    merged, and whose survivor was merged after, ends on the last survivor. Gives how many heads were written"""
    merges = sorted(
        {str(stray.merge) for stray in await stray_references() if stray.merge}
    )
    written = 0
    seen: set[str] = set()
    while merges:
        for merge_id in merges:
            written += await merge_second_pass(merge_id)
            seen.add(merge_id)
        # (what was moved to a survivor that is itself merged is stray again, on that one)
        merges = sorted(
            {str(stray.merge) for stray in await stray_references() if stray.merge}
            - seen
        )
    return written


@read_transaction
async def unfinished_merges(tx: Transaction) -> list[MergeRecord]:
    """The large merges that stopped before their batches were all made: to be gone on with (`merge(...,
    allow_large=True)` of the same pair) or undone"""
    result = await tx.run(
        "MATCH (m:PGMerge) WHERE m.state = 'running' RETURN properties(m) AS merge ORDER BY m.id"
    )
    return [_record(row["merge"]) for row in await result.data()]
