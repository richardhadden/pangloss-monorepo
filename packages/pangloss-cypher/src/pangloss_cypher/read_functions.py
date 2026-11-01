"""The reads the models are bound to (`get`, `list`, `search`, `autocomplete`), on the backend in use"""

from typing import Any, Union, cast
from uuid import UUID

from pangloss_models.autocomplete import (
    AutocompleteResults,
    labels_to_match,
)
from pangloss_models.model_bases.base_models import _ListItems
from pangloss_models.model_bases.document import (
    Document,
    _DocumentHeadViewBase,
    _DocumentReferenceViewBase,
)
from pangloss_models.model_bases.entity import (
    Entity,
    _EntityEditViewBase,
    _EntityHeadViewBase,
    _EntityReferenceViewBase,
)
from pangloss_models.model_registry import ModelRegistry
from pangloss_models.search import Match, check_match, check_order
from pangloss_models.utils import get_concrete_types
from pydantic import AnyHttpUrl, TypeAdapter

from pangloss_cypher.autocomplete_query import autocomplete_query
from pangloss_cypher.build_tree import GraphFragment
from pangloss_cypher.list_query import (
    DEFAULT_HIT_LIMIT,
    build_generic_list_query,
    build_truncation_query,
)
from pangloss_cypher.lookup import resolve_id
from pangloss_cypher.read_incoming import fetch_incoming_relations
from pangloss_cypher.read_query import build_fetch_document_query
from pangloss_cypher.search_query import build_search_query
from pangloss_cypher.transactions import (
    Transaction,
    current,
    dialect,
    read_transaction,
    timeout_from_setting,
)
from pangloss_cypher.values import convert_type_for_writing


async def empty_page(tx: Transaction, query: str, params: dict) -> dict[str, Any]:
    """The result of a list that has no items on the page asked for: nothing is
    listed, but there may be a count of what there is on the other pages. (The query
    gives no row at all then, so the count comes from the first page.)"""
    page_key = "page" if "page" in params else "page_number"
    page, page_size = params[page_key], params["page_size"]

    total = 0
    if page > 1:
        result = await tx.run(query, **{**params, page_key: 1})  # ty: ignore[invalid-argument-type]
        first_page = await result.value()
        if first_page:
            total = first_page[0]["count"]

    page_count = -(-total // page_size)
    return {
        "results": [],
        "count": total,
        "page": page,
        "page_size": page_size,
        "page_count": page_count,
        "previous_page": page - 1 if page > 1 else None,
        "next_page": page + 1 if page < page_count else None,
    }


@read_transaction
@timeout_from_setting("SEARCH_TIMEOUT_SECONDS", 30)
async def list_items(
    tx: Transaction,
    cls: type[Document | Entity],
    search_terms: str | None = None,
    page_number: int | None = None,
    page_size: int | None = None,
    deep_search: bool = False,
    published: bool | None = None,
    review_status: str | None = None,
) -> _ListItems[_DocumentReferenceViewBase | _EntityReferenceViewBase]:
    hit_limit = getattr(current().settings, "SEARCH_HIT_LIMIT", DEFAULT_HIT_LIMIT)
    query, params = build_generic_list_query(
        cls,
        search_terms=search_terms,
        page_number=page_number,
        page_size=page_size,
        deep_search=deep_search,
        published=published,
        review_status=review_status,
        hit_limit=hit_limit,
    )

    concrete_types = get_concrete_types(cls)
    concrete_ref_types = [t.ReferenceView for t in concrete_types]

    type_adapter = TypeAdapter(list[Union[*concrete_ref_types]])  # type: ignore

    result = await tx.run(query, **params)
    result_values = await result.value()

    # (a list with nothing in it, or a page past the end, gives no row at all)
    results: dict = (
        result_values[0] if result_values else await empty_page(tx, query, params)
    )

    # (whether the words had more hits than were looked at: asked apart, so that it is also known of an empty list)
    results["truncated"] = False
    if "patterns" in params or "tokens" in params:
        check, check_params = build_truncation_query(search_terms, hit_limit)
        checked = await (await tx.run(check, **check_params)).value()
        results["truncated"] = bool(checked and checked[0])

    if "facets" in results:
        results["facets"] = dialect().read_facets(results["facets"])
    results["results"] = type_adapter.validate_python(results["results"])
    result = _ListItems(**results)

    return result


@read_transaction
@timeout_from_setting("SEARCH_TIMEOUT_SECONDS", 30)
async def search(
    tx: Transaction,
    cls: type[Document | Entity],
    match: Match,
    page_number: int | None = None,
    page_size: int | None = None,
) -> _ListItems[_DocumentReferenceViewBase | _EntityReferenceViewBase]:
    """The head documents (or entities) of the class, and its subclasses, that fit the pattern, as a page of
    reference views, like `list_items`. A pattern that cannot be made raises `PanglossSearchError`."""
    conditions = check_match(cls, match)
    query, params = build_search_query(
        cls,
        conditions,
        page_number or 1,
        page_size or 25,
        check_order(cls, match.order_by),
    )
    result = await tx.run(query, **params)
    rows = await result.value()
    found: dict = rows[0] if rows else await empty_page(tx, query, params)

    concrete_ref_types = [t.ReferenceView for t in get_concrete_types(cls)]
    adapter = TypeAdapter(list[Union[*concrete_ref_types]])  # type: ignore
    found["results"] = adapter.validate_python(found["results"])
    return _ListItems(**found)


@read_transaction
async def autocomplete(
    tx: Transaction,
    cls: type[Entity],
    search_terms: str,
    types: list[type[Entity]] | None = None,
    page_number: int | None = None,
    page_size: int | None = None,
) -> AutocompleteResults:
    """The entities of the given types (or of `cls`) whose label has every word of the search
    terms in it: a label that begins with them first, then by how well the index scores them."""
    d = dialect()
    patterns = d.search_patterns(search_terms)
    page, size = page_number or 1, page_size or 10
    if not patterns:
        return AutocompleteResults(
            results=[],
            count=0,
            page=page,
            page_size=size,
            next_page=None,
            previous_page=page - 1 if page > 1 else None,
        )
    params = {
        "patterns": patterns,
        "labels": labels_to_match(types or [cls]),
        "start": d.autocomplete_start(search_terms),
        "page": page,
        "page_size": size,
    }
    query = autocomplete_query(d)
    result = await tx.run(query, **params)  # ty: ignore[invalid-argument-type]
    rows = await result.value()
    found: dict = rows[0] if rows else await empty_page(tx, query, params)
    return AutocompleteResults.model_validate(found)


async def class_of_node[T: (Document, Entity)](
    tx: Transaction, cls: type[T], id: UUID
) -> type[T]:
    """The class a node was made as, if that is a subclass of `cls`; otherwise `cls`.

    A read by a class finds the nodes of its subclasses too (it matches the label), but must read them as
    the subclass, whose fields are its own: so the node's `type` is looked up first. Not looked up for a
    class that has no subclass."""
    if get_concrete_types(cls, include_abstract=True) <= {cls}:
        return cls
    result = await tx.run(
        "MATCH (node:PGIndexableNode {id: $id}) WHERE $type IN labels(node) RETURN node.type AS type",
        id=convert_type_for_writing(id),
        type=cls.__name__,
    )
    found = await result.value()
    made_as = ModelRegistry._model_dict.get(found[0]) if found else None
    if made_as is not None and issubclass(made_as, cls):
        return made_as
    return cls


@read_transaction
async def get_document(
    tx: Transaction, cls: type[Document], id: UUID | AnyHttpUrl
) -> _DocumentHeadViewBase | None:
    """A head document. Of a class that has subclasses, this gives the view of the subclass the document
    is (its `type` says which)"""
    cls = await class_of_node(tx, cls, cast(UUID, id))
    query_string, query_params = build_fetch_document_query(cls, cast(UUID, id))

    result = await tx.run(query_string, **query_params)  # ty: ignore[invalid-argument-type]
    records = await result.data()
    if records:
        return cls.HeadView(**tree_of(records[0]))
    return None


def tree_of(record: dict) -> dict:
    """The document, from a record returned by the query of `get_document`"""
    return GraphFragment.from_record(record).tree()


async def read_entity(
    tx: Transaction, cls: type[Entity], id: UUID | AnyHttpUrl, incoming: bool
) -> tuple[dict, type[Entity]] | None:
    """The data of an entity (with the incoming relations, if `incoming`), and the class it is: `cls`, or
    the subclass it was made as"""
    resolved_id = await resolve_id(tx, id)
    if resolved_id is None:
        return None
    cls = await class_of_node(tx, cls, resolved_id)

    query_string, query_params = build_fetch_document_query(cls, resolved_id)

    result = await tx.run(query_string, **query_params)  # ty: ignore[invalid-argument-type]
    records = await result.data()
    if not records:
        return None

    data = tree_of(records[0])
    data["urls"] = sorted(records[0]["urls"])
    if incoming:
        data.update(await fetch_incoming_relations(tx, cls, resolved_id))
    return data, cls


@read_transaction
async def get_entity(
    tx: Transaction, cls: type[Entity], id: UUID | AnyHttpUrl
) -> _EntityHeadViewBase | None:
    """An entity, with its own values and relations, and the documents (and
    entities) that refer to it, in the fields named after the reverse relations. Of a class that has
    subclasses, this gives the view of the subclass the entity is (its `type` says which)"""
    read = await read_entity(tx, cls, id, incoming=True)
    if read is None:
        return None
    data, made_as = read
    return made_as.HeadView(**data)


@read_transaction
async def get_entity_for_edit(
    tx: Transaction, cls: type[Entity], id: UUID | AnyHttpUrl
) -> _EntityEditViewBase | None:
    """An entity as it is edited: its own values and outgoing relations, without
    the incoming relations (which are not looked for). As for `get_entity`, the subclass's view if the entity
    is one"""
    read = await read_entity(tx, cls, id, incoming=False)
    if read is None:
        return None
    data, made_as = read
    return made_as.EditView(**data)
