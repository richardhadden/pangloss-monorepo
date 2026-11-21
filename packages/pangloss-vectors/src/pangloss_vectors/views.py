"""What the similar route reads besides the search: whether the reader may see the item asked about, and the
reference views of the items found, all in one query (as the core's lists give them: `n{.*, meta: {...}}`, read as
the `ReferenceView` of each one's class)."""

from collections.abc import Sequence
from typing import Any
from uuid import UUID

from pangloss_core import backend
from pangloss_models import ModelRegistry

ASKED_QUERY = """
MATCH (asked:HeadNode {id: $id})
WHERE $label IN labels(asked)
RETURN asked.id AS id
"""


def _seen_query(fragments: Any) -> str:
    return (
        "MATCH (n:HeadNode {id: $id}) "
        f"WHERE {fragments.visible('n')} "
        "RETURN n.id AS id"
    )


async def visible_item(model: type, id: UUID, see_unpublished: bool) -> str | None:
    """The id to search from for the item `id` of the class `model` (or a class below it): its own, or, for an
    entity merged into another, its survivor's. None if there is no such item, or the reader may not see it (as
    `GET /api/NAME/{id}` would refuse it)"""
    from pangloss_cypher.validate_write import survivors_of

    current = backend.current()
    database = current.database()
    seen = _seen_query(current.fragments)

    @database.read_transaction
    async def read(tx: Any) -> str | None:
        asked = await (
            await tx.run(ASKED_QUERY, id=str(id), label=model.__name__)
        ).single()
        if asked is None:
            return None
        item = (await survivors_of(tx, [str(id)])).get(str(id), str(id))
        found = await (
            await tx.run(seen, id=item, see_unpublished=see_unpublished)
        ).single()
        return None if found is None else str(found["id"])

    return await read()


def _views_query(fragments: Any, dialect: Any) -> str:
    """The reference views of the heads of these ids that the reader may look through (the meta as a list gives it)"""
    return f"""
        UNWIND $ids AS id
        MATCH (n:HeadNode {{id: id}})
        WHERE {fragments.listed("n")}
        OPTIONAL MATCH (n)<-[:is_creation_of]-(creation:PGCreation)
        RETURN n{{.*, meta: {{
            created_by: {fragments.creators("creation")},
            uploaded_by: creation.uploaded_by,
            created_when: creation.created_when,
            updated_by: null,
            updated_when: null,
            semantic_spaces: coalesce({dialect.meta_property("n", "semantic_spaces")}, []),
            context_labels: {dialect.meta_property("n", "context_labels")},
            head_node_id: null,
            head_node_type: null,
            is_head_node: true,
            published: coalesce(n.published, true),
            review_status: n.review_status
        }}}} AS item
    """


async def reference_views(
    ids: Sequence[str], see_unpublished: bool
) -> dict[str, dict[str, Any]]:
    """The reference view of each of these heads the reader may look through, as JSON (camelCase), by id; one query
    for them all"""
    if not ids:
        return {}
    current = backend.current()
    database = current.database()
    query = _views_query(current.fragments, current.dialect)

    @database.read_transaction
    async def read(tx: Any) -> list[dict[str, Any]]:
        result = await tx.run(query, ids=list(ids), see_unpublished=see_unpublished)
        return [record["item"] async for record in result]

    found: dict[str, dict[str, Any]] = {}
    for row in await read():
        model = ModelRegistry._model_dict.get(row["type"])
        view_model = getattr(model, "ReferenceView", None)
        if view_model is None:
            continue
        view = view_model.model_validate(row)
        found[str(view.id)] = view.model_dump(by_alias=True, mode="json")
    return found
