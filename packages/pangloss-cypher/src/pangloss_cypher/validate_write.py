"""Checks made inside a write transaction before anything is written, so that
a write that cannot succeed fails with a useful error, instead of silently
writing nothing (or, for an update, deleting data and writing nothing)."""

import dataclasses
import typing
import uuid

from pangloss_models import (
    PanglossConflictError,
    PanglossMergedError,
    PanglossNotFoundError,
    PanglossReferenceError,
)
from pangloss_models.merging import note_resolved
from pangloss_models.model_bases.labels import has_allowed_label

from pangloss_cypher.write_plan import (
    ExistingEntity,
    InlineEntity,
    InlineEntityKey,
    PlannedNode,
    ReferenceToExisting,
    WritePlan,
)
from pangloss_cypher.build_update_query import (
    build_head_query,
    build_tree_meta_query,
)
from pangloss_cypher.transaction import Transaction
from pangloss_cypher.transactions import dialect
from pangloss_cypher.checks import check_user_exists as check_user_exists


def merged_error(
    type_name: str, id: typing.Any, into: typing.Any
) -> PanglossMergedError:
    """What a write addressed to a merged entity is refused with"""
    return PanglossMergedError(
        f"{type_name} {id} was merged into {into}: it cannot be written to (undo the merge, or write to {into})",
        id=uuid.UUID(str(id)),
        merged_into=uuid.UUID(str(into)),
    )


@dataclasses.dataclass
class ExistingHead:
    created_by: list | None
    created_when: typing.Any
    version: int = 1


# How many merges a merged id is followed through to its survivor (X into B, B into A, ...)
MERGE_CHAIN_LIMIT = 10


async def survivors_of(tx: Transaction, ids: typing.Iterable[str]) -> dict[str, str]:
    """For each of the ids that is an entity merged into another (`merged_into`): the id of its survivor, at the end
    of the chain of merges. The ids that are not merged are not in the result"""
    survivor = {id: id for id in ids}
    asked = set(survivor.values())
    for _ in range(MERGE_CHAIN_LIMIT):
        if not asked:
            break
        result = await tx.run(
            """
            UNWIND $ids AS id
            MATCH (node:PGIndexableNode {id: id})
            WHERE node.merged_into IS NOT NULL
            RETURN id, node.merged_into AS into
            """,
            ids=sorted(asked),
        )
        step = {id: into for id, into in await result.values()}
        if not step:
            break
        survivor = {given: step.get(now, now) for given, now in survivor.items()}
        asked = set(step.values())
    return {given: now for given, now in survivor.items() if now != given}


def resolve_references(plan: WritePlan, survivors: dict[str, str]) -> None:
    """The references of the plan to merged entities (`survivors`: the value given, to the id of the survivor) become
    references to their survivors, in the plan itself. A value that by this names an entity the same relation of the
    same node already names is left out (a list that held both has the survivor once)"""

    def below(node: PlannedNode) -> None:
        # (what each relation of the node names as it was given, so that one made the same by resolving goes,
        # whichever comes first)
        given = {
            (relation.edges, relation.target.value)
            for relation in node.relations
            if isinstance(relation.target, ReferenceToExisting)
        }
        seen: set[tuple[typing.Any, str]] = set()
        kept = []
        for relation in node.relations:
            target = relation.target
            if isinstance(target, ReferenceToExisting):
                resolved = (
                    survivors.get(target.value) if not target.keep_on_merge else None
                )
                if resolved is not None:
                    note_resolved(target.value, resolved)
                    key = (relation.edges, resolved)
                    if key in given or key in seen:
                        continue
                    seen.add(key)
                    relation.target = dataclasses.replace(
                        target, value=resolved, is_url=False
                    )
            elif isinstance(target, PlannedNode):
                below(target)
            elif target.node is not None:
                below(target.node)
            kept.append(relation)
        node.relations = kept

    below(plan.head)


async def check_references_exist(
    tx: Transaction,
    plan: WritePlan,
    existing: dict[InlineEntityKey, ExistingEntity] | None = None,
    *,
    resolved: bool = False,
) -> None:
    """Check that every existing entity referred to exists and is of an allowed type (`existing`: which of the
    entities written in the document exist, whose own references are not written).

    A reference to an entity that was merged into another is made a reference to its survivor first, in the plan
    (`resolve_references`), unless its field keeps what it names (`KeepOnMerge()`); what is checked is the survivor."""

    references = plan.references(existing)
    by_id = [r for r in references if not r.is_url]
    by_url = [r for r in references if r.is_url]

    found: dict[str, list[set[str]]] = {}
    deleted_values: set[str] = set()
    # (the value given, to the id of the node that is merged)
    merged: dict[str, str] = {}

    if by_id:
        result = await tx.run(
            """
            UNWIND $values AS value
            OPTIONAL MATCH (node:PGIndexableNode {id: value})
            RETURN value, labels(node) AS labels, node.deleted AS deleted,
                   CASE WHEN node.merged_into IS NULL THEN null ELSE node.id END AS merged
            """,
            values=sorted({r.value for r in by_id}),
        )
        for value, labels, deleted, merged_id in await result.values():
            found.setdefault(value, []).append(set(labels or []))
            if deleted:
                deleted_values.add(value)
            if merged_id:
                merged[value] = merged_id

    if by_url:
        result = await tx.run(
            """
            UNWIND $values AS value
            OPTIONAL MATCH (:PGUrl {url: value})<-[:has_url]-(node:PGIndexableNode)
            RETURN value, labels(node) AS labels, node.deleted AS deleted,
                   CASE WHEN node.merged_into IS NULL THEN null ELSE node.id END AS merged
            """,
            values=sorted({r.value for r in by_url}),
        )
        for value, labels, deleted, merged_id in await result.values():
            found.setdefault(value, []).append(set(labels or []))
            if deleted:
                deleted_values.add(value)
            if merged_id:
                merged[value] = merged_id

    # (only then: a write that names no merged entity asks nothing more)
    to_resolve = {
        r.value: merged[r.value]
        for r in references
        if r.value in merged and not r.keep_on_merge
    }
    if to_resolve and not resolved:
        survivors = await survivors_of(tx, to_resolve.values())
        resolve_references(
            plan,
            {value: survivors.get(node, node) for value, node in to_resolve.items()},
        )
        return await check_references_exist(tx, plan, existing, resolved=True)

    problems = []
    for reference in references:
        matches = [labels for labels in found.get(reference.value, []) if labels]
        if not matches:
            problems.append(f"{reference.field_name}: '{reference.value}' not found")
        elif reference.value in deleted_values:
            problems.append(
                f"{reference.field_name}: '{reference.value}' has been deleted"
            )
        elif not any(
            has_allowed_label(reference.allowed_types, labels) for labels in matches
        ):
            problems.append(
                f"{reference.field_name}: '{reference.value}' is not of an allowed type "
                f"({', '.join(reference.allowed_types)})"
            )
    if problems:
        raise PanglossReferenceError(
            "Invalid references to existing objects: " + "; ".join(problems)
        )


async def find_existing_entities(
    tx: Transaction, inline_entities: list[InlineEntity]
) -> dict[InlineEntityKey, ExistingEntity]:
    """Which of the entities written in a document (by their id or URL) exist. One that was merged into another is
    found as its survivor (unless the field it is written in keeps what it names: `KeepOnMerge()`)"""
    ids = sorted({e.key[1] for e in inline_entities if e.key[0] == "id"})
    urls = sorted({e.key[1] for e in inline_entities if e.key[0] == "url"})
    existing: dict[InlineEntityKey, ExistingEntity] = {}
    merged: dict[InlineEntityKey, str] = {}

    for kind, values, query in (
        (
            "id",
            ids,
            """
            UNWIND $values AS value
            MATCH (node:PGIndexableNode {id: value})
            RETURN value, node.id AS id, labels(node) AS labels, node.deleted AS deleted,
                   node.merged_into AS merged_into
            ORDER BY id
            """,
        ),
        (
            "url",
            urls,
            """
            UNWIND $values AS value
            MATCH (:PGUrl {url: value})<-[:has_url]-(node:PGIndexableNode)
            RETURN value, node.id AS id, labels(node) AS labels, node.deleted AS deleted,
                   node.merged_into AS merged_into
            ORDER BY id
            """,
        ),
    ):
        if not values:
            continue
        result = await tx.run(query, values=values)
        for value, id, labels, deleted, merged_into in await result.values():
            if (kind, value) in existing:
                continue
            existing[(kind, value)] = ExistingEntity(
                id=id, labels=frozenset(labels), deleted=bool(deleted)
            )
            if merged_into is not None:
                merged[(kind, value)] = id

    kept = {e.key for e in inline_entities if e.keep_on_merge}
    to_resolve = {key: id for key, id in merged.items() if key not in kept}
    if to_resolve:
        survivors = await survivors_of(tx, to_resolve.values())
        result = await tx.run(
            """
            UNWIND $ids AS id
            MATCH (node:PGIndexableNode {id: id})
            RETURN node.id AS id, labels(node) AS labels, node.deleted AS deleted
            """,
            ids=sorted(set(survivors.values())),
        )
        found = {id: (labels, deleted) for id, labels, deleted in await result.values()}
        for key, id in to_resolve.items():
            survivor = survivors.get(id)
            if survivor is not None and survivor in found:
                labels, deleted = found[survivor]
                existing[key] = ExistingEntity(
                    id=survivor, labels=frozenset(labels), deleted=bool(deleted)
                )
                note_resolved(key[1], survivor)
    return existing


def check_inline_entities(
    inline_entities: list[InlineEntity],
    existing: dict[InlineEntityKey, ExistingEntity],
) -> None:
    """Check that an entity written in a document, if it exists, can be the one the
    document means: it is an entity, of an allowed type, that has not been deleted"""
    problems = []
    for entity in inline_entities:
        found = existing.get(entity.key)
        if found is None:
            continue
        name = f"{entity.field_name}: '{entity.key[1]}'"
        if "Entity" not in found.labels:
            problems.append(f"{name} is used by something that is not an entity")
        elif found.deleted:
            problems.append(f"{name} has been deleted")
        elif not has_allowed_label(entity.allowed_types, found.labels):
            problems.append(
                f"{name} is an entity of another type (not "
                f"{', '.join(entity.allowed_types)})"
            )
    if problems:
        raise PanglossConflictError(
            "Entities in the document are not the existing ones: " + "; ".join(problems)
        )


async def check_urls_available(
    tx: Transaction,
    plan: WritePlan,
    existing: dict[InlineEntityKey, ExistingEntity] | None = None,
) -> None:
    """Check that no URL of a new entity is already the URL of an entity"""
    urls = plan.urls_to_write(existing)
    if not urls:
        return
    result = await tx.run(
        "UNWIND $urls AS url MATCH (node:PGUrl {url: url}) RETURN node.url AS url",
        urls=sorted(set(urls)),
    )
    in_use = [url for (url,) in await result.values()]
    if in_use:
        raise PanglossConflictError(f"URLs {in_use} are already in use")


async def check_ids_available(
    tx: Transaction,
    plan: WritePlan,
    existing: dict[InlineEntityKey, ExistingEntity] | None = None,
) -> None:
    """Check that no id given for a new node is already used.

    When updating, nodes already below the head node being updated may be given
    again (they are replaced), but nodes belonging to anything else may not.
    Entities written inline are not checked: one that exists is left as it is."""

    is_update = plan.is_update
    ids = {str(plan.head_id)}
    ids.update(n.id for n in plan.nodes_to_write(existing) if not n.is_entity)

    result = await tx.run(
        """
        UNWIND $ids AS id
        MATCH (node:PGIndexableNode {id: id})
        RETURN node.id AS id, node.head_node_id AS head_node_id
        """,
        ids=sorted(ids),
    )
    head_id = str(plan.head_id)
    in_use = [
        id
        for id, head_node_id in await result.values()
        if not (is_update and (id == head_id or head_node_id == head_id))
    ]
    if in_use:
        if is_update:
            raise PanglossConflictError(
                f"Ids {in_use} belong to objects that are not part of {head_id}"
            )
        raise PanglossConflictError(f"Ids {in_use} are already in use")


async def get_existing_head(
    tx: Transaction, head_id: uuid.UUID, head_type: str
) -> ExistingHead:
    query, params = build_head_query(head_id)
    result = await tx.run(query, **params)  # ty: ignore[invalid-argument-type]
    records = await result.values()
    if not records or head_type not in records[0][0] or records[0][3]:
        raise PanglossNotFoundError(f"There is no {head_type} with id {head_id}")
    _, created_when, created_by, _, version, merged_into = records[0]
    if merged_into is not None:
        raise merged_error(head_type, head_id, merged_into)
    return ExistingHead(
        created_by=created_by, created_when=created_when, version=version
    )


async def get_tree_meta(
    tx: Transaction, head_id: uuid.UUID
) -> dict[str, dict[str, typing.Any]]:
    query, params = build_tree_meta_query(head_id)
    result = await tx.run(query, **params)  # ty: ignore[invalid-argument-type]
    return {id: meta for id, meta in await result.values()}


async def replace_urls(tx: Transaction, entity_id: uuid.UUID, urls: list[str]) -> None:
    """Make `urls` the URLs of an entity: URLs it has that are not in the list are
    removed, and the others are added. A URL that belongs to another entity (even a
    deleted one) is a conflict."""
    urls = sorted(set(urls))
    id = str(entity_id)
    entity = dialect().entity_labels()
    result = await tx.run(
        f"""
        UNWIND $urls AS url
        MATCH (node:PGUrl {{url: url}})
        WHERE NOT ({entity} {{id: $id}})-[:has_url]->(node)
        RETURN node.url AS url
        """,  # ty: ignore[invalid-argument-type]
        urls=urls,
        id=id,
    )
    in_use = [url for (url,) in await result.values()]
    if in_use:
        raise PanglossConflictError(f"URLs {in_use} are already in use")

    await tx.run(
        f"""
        MATCH ({entity} {{id: $id}})-[:has_url]->(node:PGUrl)
        WHERE NOT node.url IN $urls
        DETACH DELETE node
        """,  # ty: ignore[invalid-argument-type]
        urls=urls,
        id=id,
    )
    await tx.run(
        f"""
        MATCH (entity{entity} {{id: $id}})
        UNWIND $urls AS url
        MERGE (node:PGUrl {{url: url}})
        MERGE (entity)-[:has_url]->(node)
        """,  # ty: ignore[invalid-argument-type]
        urls=urls,
        id=id,
    )
