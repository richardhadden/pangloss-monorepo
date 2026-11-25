"""What the similar route reads besides the search: whether the reader may see the item asked about, and the
reference views of the items found, all in one query (as the core's lists give them: `n{.*, meta: {...}}`, read as
the `ReferenceView` of each one's class).

An item may be a document nested in another (a statement in a factoid): what the reader may see of it is decided by
its head, and its reference view is the one the core's search gives a nested node
(`pangloss_cypher.list_query`): the meta of its head (who made it, whether it is published) with `head_node_id`,
`head_node_type` and `is_head_node: false`, by which the interface links it to the page of its head."""

from collections.abc import Sequence
from typing import Any, NamedTuple
from uuid import UUID

from pangloss_core import backend
from pangloss_models import ModelRegistry
from pydantic import AnyHttpUrl

# (a document or an entity: a head, or a document nested in one)
ASKED_QUERY = """
MATCH (asked:PGIndexableNode {id: $id})
WHERE $label IN labels(asked) AND any(kind IN labels(asked) WHERE kind IN ['Document', 'Entity'])
RETURN asked.id AS id
"""


def _seen_query(fragments: Any) -> str:
    """The item, if the reader may see it: by its head, if it is nested (and not if its head is not there)"""
    head = fragments.head_of("n", "n_head")
    return (
        "MATCH (n:PGIndexableNode {id: $id}) "
        f"{head.match} "
        "WITH n, n_head "
        "WHERE (n.head_node_id IS NULL OR n_head IS NOT NULL) "
        f"AND {fragments.visible('n', head)} "
        "RETURN n.id AS id, n.type AS type"
    )


class Seen(NamedTuple):
    id: str
    type: str
    """The name of its own class"""


async def visible_item(
    model: type, reference: UUID | AnyHttpUrl, see_unpublished: bool
) -> Seen | None:
    """The id to search from for the item `reference` names (its id, or one of an entity's URLs) of the class `model`
    (or a class below it), a head or a document nested in one, and its own class: its own, or, for an entity merged
    into another, its survivor's (a merge gives the survivor the URLs of the entity merged into it, so a URL names the
    survivor itself). None if there is no such item, or the reader may not see it (as `GET /api/NAME/{id}` would
    refuse it; a nested document by its head)"""
    from pangloss_cypher.lookup import resolve_id
    from pangloss_cypher.validate_write import survivors_of

    current = backend.current()
    database = current.database()
    seen = _seen_query(current.fragments)

    @database.read_transaction
    async def read(tx: Any) -> Seen | None:
        id = await resolve_id(tx, reference)
        if id is None:
            return None
        asked = await (
            await tx.run(ASKED_QUERY, id=str(id), label=model.__name__)
        ).single()
        if asked is None:
            return None
        item = (await survivors_of(tx, [str(id)])).get(str(id), str(id))
        found = await (
            await tx.run(seen, id=item, see_unpublished=see_unpublished)
        ).single()
        return None if found is None else Seen(str(found["id"]), str(found["type"]))

    return await read()


def _views_query(fragments: Any, dialect: Any) -> str:
    """The reference views of the items of these ids (heads, or documents nested in them) that the reader may look
    through (the meta as the core's search gives it: of the head, for a nested document)"""
    head = fragments.head_of("n", "n_head")
    return f"""
        UNWIND $ids AS id
        MATCH (n:PGIndexableNode {{id: id}})
        {head.match}
        WITH n, n_head
        WHERE (n.head_node_id IS NULL OR n_head IS NOT NULL)
        AND {fragments.listed("n", head)}
        WITH n, {head} AS headnode
        OPTIONAL MATCH (headnode)<-[:is_creation_of]-(creation:PGCreation)
        RETURN n{{.*, meta: {{
            created_by: {fragments.creators("creation")},
            uploaded_by: creation.uploaded_by,
            created_when: creation.created_when,
            updated_by: null,
            updated_when: null,
            semantic_spaces: coalesce({dialect.meta_property("n", "semantic_spaces")}, []),
            {dialect.meta_entry("n", "path")},
            head_node_id: n.head_node_id,
            head_node_type: n.head_node_type,
            is_head_node: n:HeadNode,
            published: coalesce(headnode.published, true),
            review_status: headnode.review_status
        }}}} AS item
    """


async def reference_views(
    ids: Sequence[str], see_unpublished: bool
) -> dict[str, dict[str, Any]]:
    """The reference view of each of these items (heads, or documents nested in them) the reader may look through, as
    JSON (camelCase), by id; one query for them all"""
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
