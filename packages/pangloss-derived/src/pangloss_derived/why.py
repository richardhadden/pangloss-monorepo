"""Why a document is there: the rule, what it rests on, and (for a document a person made their own) that, and whether
the derivation it was made from still holds. What a reader sees follows the rules for documents: a source the reader
may not see is counted, not named."""

from typing import Any
from uuid import UUID

from pangloss_cypher import fragments
from pangloss_models import ModelRegistry

from pangloss_derived import convert, documents
from pangloss_derived.read import database, see_unpublished

QUERY = f"""
MATCH (h:HeadNode {{id: $id}})
OPTIONAL MATCH (j:PGJustification {{document_id: $id}})
RETURN h.type AS type, h.derived_by AS derived_by, h.derived_context AS derived_context,
       j.key AS key, j.rule AS rule, j.sources AS sources, j.context_labels AS context_labels,
       coalesce(j.adopted, false) AS adopted, j.adopted_by AS adopted_by, j.adopted_at AS adopted_at,
       coalesce(j.lost, false) AS lost, j IS NOT NULL AS has_justification,
       {fragments.deleted("h")} AS deleted
"""

SOURCES_QUERY = f"""
UNWIND $ids AS id
MATCH (n:PGIndexableNode {{id: id}})
OPTIONAL MATCH (h:HeadNode {{id: coalesce(n.head_node_id, n.id)}})
RETURN n.id AS id, n.type AS type, n.label AS label, h.id AS head, h.type AS head_type, h.label AS head_label,
       {fragments.deleted("h")} AS deleted, {fragments.published("h")} AS published
"""


async def of_document(type_name: str, id: UUID) -> dict[str, Any] | None:
    model = ModelRegistry._model_dict.get(type_name)
    db = database()
    unseen = see_unpublished()

    @db.read_transaction
    async def read(tx: Any) -> dict[str, Any] | None:
        result = await tx.run(QUERY, id=str(id))
        record = await result.single()
        if (
            record is None
            or record["derived_by"] is None
            and not record["has_justification"]
        ):
            return None
        row = dict(record)
        sources = []
        hidden = 0
        ids = [str(s) for s in row["sources"] or []]
        if ids:
            found = await (await tx.run(SOURCES_QUERY, ids=ids)).data()
            for source in found:
                if source["deleted"] or (not source["published"] and not unseen):
                    hidden += 1
                    continue
                sources.append(
                    {
                        "id": source["id"],
                        "type": source["type"],
                        "label": source["label"],
                        "headId": source["head"],
                        "headType": source["head_type"],
                        "headLabel": source["head_label"],
                    }
                )
        return {**row, "visible": sources, "hidden": hidden}

    row = await read()
    if row is None:
        return None
    still_derived = documents.is_derived_document(model)
    converted = (not still_derived) and bool(row["adopted"])
    if not still_derived and not converted:
        return None
    return {
        "id": str(id),
        "type": type_name,
        "rule": row["rule"] or row["derived_by"],
        "key": row["key"],
        "context": sorted(row["context_labels"] or row["derived_context"] or []),
        "sources": row["visible"],
        "hiddenSources": row["hidden"],
        "converted": converted,
        "convertedBy": row["adopted_by"],
        "convertedAt": str(row["adopted_at"]) if row["adopted_at"] else None,
        "holds": not row["lost"] and row["has_justification"],
        "convertsTo": [t.__name__ for t in convert.targets_of(model)]
        if still_derived and model is not None
        else [],
    }
