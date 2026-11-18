"""Citing a derived document: what is saved is citations of what it rests on. See implementation_docs/derived.md
("Citing a derived document") and `pangloss_models.citations` (a cited basis).

A derived document is the worker's to change and delete, so it is never itself cited (a citation protects what it
cites). A citation that names one, or a part of one, is replaced by a cited basis (`hooks.resolve_citation`): citations
of the nodes its justification matched, with a record of what was chosen. A derived document among those is replaced
by what it rests on in turn, until only what people wrote is left.

When the worker changes or deletes a derived document, the bases made through it are marked, in the transaction of
that write (`hooks.in_write`): `changed`, `lost`, or cleared when it is back.
"""

from typing import Any
from uuid import UUID

from pangloss_models import ModelRegistry, hooks
from pangloss_models.exceptions import PanglossReferenceError

from pangloss_derived import documents
from pangloss_derived.registry import DerivedRegistry


def node_query() -> str:
    # (nothing of the database is imported with the package: a client of the SDK has it with the models)
    from pangloss_cypher import fragments

    return f"""
MATCH (n:PGIndexableNode {{id: $id}})
OPTIONAL MATCH (h:HeadNode {{id: n.head_node_id}})
WITH n, coalesce(h, n) AS head
RETURN n.type AS type, n:Entity AS entity, head.id AS head, head.type AS head_type, head.label AS label,
       {fragments.deleted("head")} AS deleted
"""


JUSTIFICATION_QUERY = """
MATCH (j:PGJustification {document_id: $id})
RETURN j.key AS key, j.rule AS rule, j.nodes AS nodes
"""


def classes_inside() -> set[str]:
    """The names of the classes a node of a derived document can be of: the derived document classes, and what the
    templates of the rules write. (A citation of anything else is not looked at: no read is made for it)"""
    from pangloss_derived.templates import written_classes

    names = set(documents.concrete_class_names())
    for rule in DerivedRegistry.documents.values():
        for model in written_classes(rule.template):
            names.add(model.__name__)
    return names


async def resolve(type_name: str, id: UUID, tx: Any) -> hooks.ResolvedCitation | None:
    """(`hooks.resolve_citation`) what is cited in the place of a derived document, or of a part of one: the nodes
    its justification matched. None for anything else"""
    if not DerivedRegistry.documents or type_name not in classes_inside():
        return None
    if tx is not None:
        return await resolved(tx, str(id))
    from pangloss_derived.worker import database

    db = database()

    @db.read_transaction
    async def read(tx: Any) -> hooks.ResolvedCitation | None:
        return await resolved(tx, str(id))

    return await read()


async def one(tx: Any, query: str, id: str) -> dict[str, Any] | None:
    result = await tx.run(query, id=id)
    record = await result.single()
    return dict(record) if record else None


def is_derived(type_name: str | None) -> bool:
    return documents.is_derived_document(ModelRegistry._model_dict.get(type_name or ""))


async def resolved(tx: Any, id: str) -> hooks.ResolvedCitation | None:
    node = await one(tx, node_query(), id)
    if node is None or not is_derived(node["head_type"]):
        return None
    chosen = f"{node['head_type']} {node['head']}"
    justification = (
        None if node["deleted"] else await one(tx, JUSTIFICATION_QUERY, node["head"])
    )
    if justification is None:
        raise PanglossReferenceError(
            f"A citation names a derived document whose derivation does not hold any more ({chosen}): there is "
            "nothing it rests on to cite"
        )
    targets: dict[str, str] = {}
    await basis(tx, justification["nodes"], targets, {node["head"]})
    if not targets:
        raise PanglossReferenceError(
            f"A citation names a derived document that rests on no document ({chosen})"
        )
    return hooks.ResolvedCitation(
        targets=tuple((kind, target) for target, kind in sorted(targets.items())),
        rule=justification["rule"],
        key=justification["key"],
        label=node["label"],
        # (a statement inside one is cited as its document: what the worker changes and deletes, and marks by)
        via=(node["head_type"], UUID(str(node["head"]))),
    )


async def basis(
    tx: Any, nodes: list[str], targets: dict[str, str], seen: set[str]
) -> None:
    """Add to `targets` (id: class) the documents among the nodes; for one in a derived document, what that document
    rests on instead"""
    for id in dict.fromkeys(str(n) for n in nodes):
        node = await one(tx, node_query(), id)
        if node is None or node["entity"]:
            continue
        if not is_derived(node["head_type"]):
            targets[id] = node["type"]
            continue
        if node["head"] in seen:
            continue
        seen.add(node["head"])
        justification = await one(tx, JUSTIFICATION_QUERY, node["head"])
        if justification is not None:
            await basis(tx, justification["nodes"], targets, seen)


MARKS = {"update": "changed", "delete": "lost", "undelete": ""}


async def mark_citations(tx: Any, op: str, model: type, id: UUID) -> None:
    """(`hooks.in_write`) the worker has changed, deleted or undeleted a derived document: the cited bases made
    through it are marked, in the transaction of that write"""
    if op not in MARKS or not documents.is_derived_document(model):
        return
    from pangloss_cypher import citations

    await citations.mark_via(tx, id, MARKS[op])
