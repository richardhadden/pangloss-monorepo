"""The reads the models are bound to (`get`, `list`, `search`, `autocomplete`), on the backend in use"""

from dataclasses import dataclass
from typing import Any, LiteralString, Union, cast
from uuid import UUID

from pangloss_models.autocomplete import (
    AutocompleteItem,
    AutocompleteResults,
    labels_to_match,
)
from pangloss_models.model_bases.base_models import _ListItems
from pangloss_models import (
    Document,
    Entity,
    Match,
    ModelRegistry,
    OrderBy,
    PanglossReferenceError,
    Where,
)
from pangloss_models.model_bases.document import (
    _DocumentHeadViewBase,
    _DocumentReferenceViewBase,
)
from pangloss_models.model_bases.entity import (
    _EntityEditViewBase,
    _EntityHeadViewBase,
    _EntityReferenceViewBase,
)
from pangloss_models.search import (
    check_field_types,
    check_match,
    check_order,
    search_match,
)
from pangloss_models.utils import get_concrete_types
from pydantic import AnyHttpUrl, TypeAdapter
from pydantic.alias_generators import to_camel

from pangloss_cypher import fragments
from pangloss_cypher.autocomplete_query import (
    autocomplete_query,
    most_connected_query,
    most_used_query,
    search_everything_query,
)
from pangloss_cypher.build_tree import GraphFragment
from pangloss_cypher.list_query import (
    DEFAULT_HIT_LIMIT,
    build_generic_list_query,
    build_truncation_query,
)
from pangloss_cypher.lookup import resolve_id
from pangloss_cypher.read_incoming import fetch_incoming_relations
from pangloss_cypher.read_query import build_fetch_document_query
from pangloss_cypher.search_query import build_field_types_query, build_search_query
from pangloss_cypher.validate_write import MERGE_CHAIN_LIMIT
from pangloss_cypher.transactions import (
    Transaction,
    current,
    dialect,
    read_transaction,
    timeout_from_setting,
)
from pangloss_cypher.values import convert_type_for_writing
from pangloss_cypher.visibility import unpublished_visible


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


# (asked apart from the list, for the items of the one page: the list's own query stays as it is)
USE_COUNTS_QUERY = f"""
    UNWIND $ids AS listed_id
    MATCH (n:PGIndexableNode {{id: listed_id}})
    {fragments.uses_of("n")}
    RETURN n.id AS id, uses
"""


async def count_uses(tx: Transaction, items: list[dict]) -> dict[str, int]:
    """How many things the reader sees refer to each of the items, by id (`fragments.uses_of`)"""
    result = await tx.run(
        USE_COUNTS_QUERY,  # ty: ignore[invalid-argument-type]
        ids=[item["id"] for item in items],
        see_unpublished=unpublished_visible(),
    )
    return {record["id"]: record["uses"] async for record in result}


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
    used_only: bool = False,
    use_counts: bool = False,
) -> _ListItems[_DocumentReferenceViewBase | _EntityReferenceViewBase]:
    """`used_only`: only what something the reader sees refers to. `use_counts`: how many things refer to each item of
    the page (`use_counts` of the page, by id)"""
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
        used_only=used_only,
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
    if use_counts:
        results["use_counts"] = await count_uses(tx, results["results"])
    results["results"] = type_adapter.validate_python(results["results"])
    result = _ListItems(**results)

    return result


@read_transaction
@timeout_from_setting("SEARCH_TIMEOUT_SECONDS", 30)
async def field_types(
    tx: Transaction,
    cls: type[Document | Entity],
    field: str,
    where: Any = None,
    parts: bool = False,
) -> dict[str, int]:
    """The concrete types that the relation `field` of the nodes of the class (and its subclasses) that fit `where`
        points at, through wrappers, each with how many of the nodes point at one (`where` as a search takes it: JSON, or a
    `Model.Where`). `parts`: the nodes are any of the class
        the reader sees, parts of documents too; otherwise those a search finds (head documents, or entities). For the
        API (the search form offers only the types there are), not bound to the models. Raises `PanglossSearchError`."""
    name, conditions, head = check_field_types(cls, field, where, parts)
    query, params = build_field_types_query(cls, name, conditions, head)
    result = await tx.run(query, **params)
    return {record["type"]: record["count"] async for record in result}


@read_transaction
@timeout_from_setting("SEARCH_TIMEOUT_SECONDS", 30)
async def search(
    tx: Transaction,
    cls: type[Document | Entity],
    pattern: Match | Where | None = None,
    page_number: int | None = None,
    page_size: int | None = None,
    *,
    order_by: list[OrderBy | str] | None = None,
    used_only: bool = False,
    use_counts: bool = False,
) -> _ListItems[_DocumentReferenceViewBase | _EntityReferenceViewBase]:
    """The head documents (or entities) of the class, and its subclasses, that fit the pattern (a `Match`, or a
    `Where`; all of them, without one), as a page of reference views, like `list_items`. A pattern that cannot be
    made raises `PanglossSearchError`."""
    match = search_match(cls, pattern, order_by)
    conditions = check_match(cls, match)
    query, params = build_search_query(
        cls,
        conditions,
        page_number or 1,
        page_size or 25,
        check_order(cls, match.order_by),
        used_only,
    )
    result = await tx.run(query, **params)
    rows = await result.value()
    found: dict = rows[0] if rows else await empty_page(tx, query, params)
    if use_counts:
        found["use_counts"] = await count_uses(tx, found["results"])

    concrete_ref_types = [t.ReferenceView for t in get_concrete_types(cls)]
    adapter = TypeAdapter(list[Union[*concrete_ref_types]])  # type: ignore
    found["results"] = adapter.validate_python(found["results"])
    return _ListItems(**found)


@read_transaction
async def autocomplete(
    tx: Transaction,
    cls: type[Entity],
    search_terms: str = "",
    types: list[type[Entity]] | None = None,
    page_number: int | None = None,
    page_size: int | None = None,
) -> AutocompleteResults:
    """The entities of the given types (or of `cls`) whose label has every word of the search
    terms in it: a label that begins with them first, then by how well the index scores them.
    With no search terms (blank), the entities of the types most used first (`most_used_query`)."""
    d = dialect()
    page, size = page_number or 1, page_size or 10
    params: dict[str, Any] = {
        "labels": labels_to_match(types or [cls]),
        "page": page,
        "page_size": size,
    }
    if search_terms.strip():
        patterns = d.search_patterns(search_terms)
        if not patterns:
            return AutocompleteResults(
                results=[],
                count=0,
                page=page,
                page_size=size,
                next_page=None,
                previous_page=page - 1 if page > 1 else None,
            )
        params |= {
            "patterns": patterns,
            "start": d.autocomplete_start(search_terms),
            "limit": getattr(current().settings, "SEARCH_HIT_LIMIT", DEFAULT_HIT_LIMIT),
        }
        query = autocomplete_query(d)
    else:
        query = most_used_query(d)
    result = await tx.run(query, **params)
    rows = await result.value()
    found: dict = rows[0] if rows else await empty_page(tx, query, params)
    return AutocompleteResults.model_validate(found)


@read_transaction
@timeout_from_setting("SEARCH_TIMEOUT_SECONDS", 30)
async def search_everything(
    tx: Transaction,
    search_terms: str,
    labels: list[str] | None,
    excluded: list[str],
    page_number: int | None = None,
    page_size: int | None = None,
) -> AutocompleteResults:
    """The head documents and entities whose label has every word (with no words, all of `labels`; without those too,
    nothing), the most connected first
    (`pangloss_models.autocomplete.search_everything` decides `labels` and `excluded`)"""
    d = dialect()
    page, size = page_number or 1, page_size or 25
    params: dict[str, Any] = {
        "patterns": d.search_patterns(search_terms),
        "labels": labels,
        "excluded": excluded,
        "see_unpublished": unpublished_visible(),
        "limit": getattr(current().settings, "SEARCH_HIT_LIMIT", DEFAULT_HIT_LIMIT),
        "page": page,
        "page_size": size,
    }
    if not params["patterns"] and not labels:
        return AutocompleteResults(
            results=[],
            count=0,
            page=page,
            page_size=size,
            next_page=None,
            previous_page=None,
        )
    query = (
        search_everything_query(d)
        if params["patterns"]
        else most_connected_query(d, labels or [])
    )
    result = await tx.run(query, **params)
    rows = await result.value()
    found: dict = rows[0] if rows else await empty_page(tx, query, params)
    return AutocompleteResults.model_validate(found)


# $ids: the ids looked for (strings)
REFERENCES_QUERY = cast(
    LiteralString,
    f"""
    UNWIND $ids AS id
    MATCH (n:PGIndexableNode {{id: id}})
    WHERE n:Entity AND {fragments.not_deleted("n")}
    RETURN n.id AS id, n.type AS type, n.label AS label
""",
)


@read_transaction
async def references(
    tx: Transaction, cls: type[Entity], ids: list[UUID]
) -> list[AutocompleteItem]:
    """The entities with these ids that are there (not deleted), each with its type and label as they are now, in the
    order asked for. An id that is not an entity's (or not of `cls` or a subclass), or whose entity is deleted, is left
    out. For what refers to entities by a copy of their label (a stashed form): to see what is gone, and what is
    renamed"""
    if not ids:
        return []
    asked = list(dict.fromkeys(convert_type_for_writing(id) for id in ids))
    result = await tx.run(REFERENCES_QUERY, ids=asked)
    found = {row["id"]: row for row in await result.data()}
    allowed = {t.__name__ for t in get_concrete_types(cls, include_abstract=True)}
    return [
        AutocompleteItem.model_validate(found[id])
        for id in asked
        if id in found and (cls is Entity or found[id]["type"] in allowed)
    ]


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
    tx: Transaction,
    cls: type[Entity],
    id: UUID | AnyHttpUrl,
    incoming: bool,
    incoming_limit: int | None = None,
    counts: dict[str, int] | None = None,
    follow_merge: bool = True,
) -> tuple[dict, type[Entity]] | None:
    """The data of an entity (with the incoming relations, if `incoming`: all of them, or `incoming_limit` of each
    field), and the class it is: `cls`, or the subclass it was made as. `counts`, if given, is filled with how many
    there are in each incoming field.

    An entity that was merged into another (`Entity.merge`) is read as the one it was merged into, as that one is
    (of whatever class), with the ids passed through in `meta.merged_from`; with `follow_merge=False` it is read as
    itself, with `meta.merged_into`."""
    resolved_id = await resolve_id(tx, id)
    if resolved_id is None:
        return None
    cls = await class_of_node(tx, cls, resolved_id)
    merged_from: list[UUID] = []

    while True:
        query_string, query_params = build_fetch_document_query(cls, resolved_id)
        result = await tx.run(query_string, **query_params)  # ty: ignore[invalid-argument-type]
        records = await result.data()
        if not records:
            return None
        into = records[0]["root"].get("merged_into")
        if into is None or not follow_merge or len(merged_from) >= MERGE_CHAIN_LIMIT:
            break
        # (the survivor is read as what it is: it may be of a wider class than the one asked for)
        merged_from.append(resolved_id)
        resolved_id = UUID(str(into))
        survivor = await class_of_survivor(tx, resolved_id)
        if survivor is None:
            return None
        cls = survivor

    data = tree_of(records[0])
    data["urls"] = sorted(records[0]["urls"])
    merged_into = data.pop("merged_into", None)
    if merged_from:
        data["meta"]["merged_from"] = merged_from
    if merged_into is not None:
        data["meta"]["merged_into"] = merged_into
    if incoming:
        found, totals = await fetch_incoming_relations(
            tx, cls, resolved_id, limit=incoming_limit
        )
        data.update(found)
        if counts is not None:
            counts.update(totals)
    return data, cls


async def class_of_survivor(tx: Transaction, id: UUID) -> type[Entity] | None:
    """The class of an entity that others were merged into, by its `type`"""
    result = await tx.run(
        "MATCH (node:PGIndexableNode {id: $id}) WHERE node:Entity RETURN node.type AS type",
        id=convert_type_for_writing(id),
    )
    found = await result.value()
    model = ModelRegistry._model_dict.get(found[0]) if found else None
    if model is None or not issubclass(model, Entity):
        return None
    return model


@read_transaction
async def get_entity(
    tx: Transaction,
    cls: type[Entity],
    id: UUID | AnyHttpUrl,
    follow_merge: bool = True,
) -> _EntityHeadViewBase | None:
    """An entity, with its own values and relations, and the documents (and
    entities) that refer to it, in the fields named after the reverse relations. Of a class that has
    subclasses, this gives the view of the subclass the entity is (its `type` says which).

    The id of an entity that was merged into another gives that other (`meta.merged_from` says so), of whatever
    class it is; with `follow_merge=False`, the merged entity itself (`meta.merged_into`)."""
    read = await read_entity(tx, cls, id, incoming=True, follow_merge=follow_merge)
    if read is None:
        return None
    data, made_as = read
    return made_as.HeadView(**data)


@read_transaction
async def get_entity_with_some(
    tx: Transaction, cls: type[Entity], id: UUID | AnyHttpUrl, incoming_limit: int
) -> tuple[_EntityHeadViewBase, dict[str, int]] | None:
    """An entity as `get_entity` gives it, but with no more than `incoming_limit` of what refers to it in each
    field (the first by label), and how many there are in each field. For a page that shows an entity which
    thousands of documents refer to: the rest is read a page at a time (`get_incoming`)"""
    counts: dict[str, int] = {}
    read = await read_entity(
        tx, cls, id, incoming=True, incoming_limit=incoming_limit, counts=counts
    )
    if read is None:
        return None
    data, made_as = read
    return made_as.HeadView(**data), counts


@read_transaction
async def get_entity_without_incoming(
    tx: Transaction, cls: type[Entity], id: UUID | AnyHttpUrl
) -> _EntityHeadViewBase | None:
    """An entity as `get_entity` gives it, but with none of what refers to it (its incoming fields are empty, and
    not looked for). For a page that reads the entity first and what refers to it apart (`get_incoming_fields`)"""
    read = await read_entity(tx, cls, id, incoming=False)
    if read is None:
        return None
    data, made_as = read
    return made_as.HeadView(**data)


@dataclass
class IncomingFields:
    """What refers to an entity, the first of each relation (`get_incoming_fields`)"""

    model: type[Entity]
    """The class the entity is"""
    counts: dict[str, int]
    """How many there are in each incoming field that has any (by the field's Python name)"""
    fields: dict[str, list[Any]]
    """The first of each, by the field's Python name, as they are in that field of the entity's `HeadView`"""


@read_transaction
async def get_incoming_fields(
    tx: Transaction, cls: type[Entity], id: UUID | AnyHttpUrl, limit: int
) -> IncomingFields | None:
    """What refers to an entity, in every incoming field at once: no more than `limit` of each (the first by label),
    and how many there are in each. None if there is no such entity. With `get_entity_without_incoming`, the two
    halves of `get_entity_with_some`, for a page that reads them apart"""
    # (the entity is read first, as `get_incoming` reads it: whether it is there to be seen, and the class it is)
    read = await read_entity(tx, cls, id, incoming=False)
    if read is None:
        return None
    data, made_as = read
    found, counts = await fetch_incoming_relations(
        tx, made_as, UUID(str(data["id"])), limit=limit
    )
    fields = {
        name: TypeAdapter(
            made_as.HeadView.model_fields[name].annotation
        ).validate_python(items)
        for name, items in found.items()
        if name in made_as.HeadView.model_fields
    }
    return IncomingFields(
        model=made_as, counts={k: v for k, v in counts.items() if v}, fields=fields
    )


@dataclass
class IncomingPage:
    """Some of what refers to an entity by one relation (`get_incoming`)"""

    model: type[Entity]
    """The class the entity is"""
    field: str
    count: int
    """How many there are in all"""
    items: list[Any]
    """As they are in the field of the entity's `HeadView`"""


def incoming_field_named(cls: type[Entity], name: str) -> str | None:
    """The incoming field of a class called `name`, as Python has it or as JSON does (`given_to_reverse`,
    `givenToReverse`)"""
    names = cls._meta.field_definitions.incoming_fields
    return next((n for n in names if name in (n, to_camel(n)) and names[n]), None)


@read_transaction
async def get_incoming(
    tx: Transaction,
    cls: type[Entity],
    id: UUID | AnyHttpUrl,
    field: str,
    skip: int = 0,
    limit: int = 50,
) -> IncomingPage | None:
    """What refers to an entity by one relation (`field`: an incoming field of its `HeadView`), `limit` of them from
    `skip`, by the label of what refers. None if there is no such entity; a `PanglossReferenceError` if the class
    the entity is has no such field"""
    read = await read_entity(tx, cls, id, incoming=False)
    if read is None:
        return None
    data, made_as = read
    name = incoming_field_named(made_as, field)
    if name is None:
        raise PanglossReferenceError(
            f"Nothing refers to a {made_as.__name__} by a relation called {field}"
        )
    found, counts = await fetch_incoming_relations(
        tx, made_as, UUID(str(data["id"])), field=name, skip=skip, limit=limit
    )
    items = TypeAdapter(made_as.HeadView.model_fields[name].annotation).validate_python(
        found.get(name, [])
    )
    return IncomingPage(
        model=made_as, field=name, count=counts.get(name, 0), items=items
    )


@read_transaction
async def get_entity_for_edit(
    tx: Transaction,
    cls: type[Entity],
    id: UUID | AnyHttpUrl,
    follow_merge: bool = True,
) -> _EntityEditViewBase | None:
    """An entity as it is edited: its own values and outgoing relations, without
    the incoming relations (which are not looked for). As for `get_entity`, the subclass's view if the entity
    is one, and the survivor of a merged one unless `follow_merge=False`"""
    read = await read_entity(tx, cls, id, incoming=False, follow_merge=follow_merge)
    if read is None:
        return None
    data, made_as = read
    return made_as.EditView(**data)
