import datetime
from typing import Any, Literal, Union, cast
from uuid import UUID

from neo4j.exceptions import ClientError, TransientError
from pangloss_models import hooks
from pangloss_models.autocomplete import (
    AutocompleteResults,
    labels_to_match,
    search_words,
)
from pangloss_models.exceptions import (
    PanglossConflictError,
    PanglossEntityInUseError,
    PanglossSearchTimeoutError,
    PanglossVersionConflictError,
    PanglossWriteError,
)
from pangloss_models.hooks import WriteEvent, emit_write_event
from pangloss_models.model_bases.base_models import _ListItems
from pangloss_models.model_bases.document import (
    Document,
    _DocumentCreateBase,
    _DocumentCreateDBBase,
    _DocumentHeadViewBase,
    _DocumentReferenceViewAPIMeta,
    _DocumentReferenceViewBase,
    _DocumentUpdateBase,
    _DocumentUpdateDBBase,
)
from pangloss_models.model_bases.entity import (
    Entity,
    _EntityEditViewBase,
    _EntityHeadViewBase,
    _EntityReferenceViewBase,
    _EntityUpdateBase,
    _EntityUpdateDBBase,
)
from pangloss_models.model_registry import ModelRegistry
from pangloss_models.search import Match, check_match, check_order
from pangloss_models.utils import get_concrete_types
from pangloss_users import current_request_username
from pangloss_users.models import AccessTokenRecord, UserInDB
from pydantic import AnyHttpUrl, TypeAdapter

from pangloss_memgraph.databases.memgraph import review, users
from pangloss_memgraph.databases.memgraph.build_autocomplete_query import (
    AUTOCOMPLETE_QUERY,
)
from pangloss_memgraph.databases.memgraph.build_create_query import (
    build_head_create_query,
    convert_type_for_writing,
)
from pangloss_memgraph.databases.memgraph.build_list_query import (
    build_generic_list_query,
)
from pangloss_memgraph.databases.memgraph.build_read_query import (
    build_fetch_document_query,
)
from pangloss_memgraph.databases.memgraph.build_search_query import build_search_query
from pangloss_memgraph.databases.memgraph.build_tree import build_tree
from pangloss_memgraph.databases.memgraph.build_update_query import (
    build_head_update_query,
    build_replace_head_query,
)
from pangloss_memgraph.databases.memgraph.database import (
    Database,
    Transaction,
    timeout_from_setting,
)
from pangloss_memgraph.databases.memgraph.delete_node import (
    DeletionResult,
    soft_delete,
    undelete,
)
from pangloss_memgraph.databases.memgraph.lookup import resolve_id
from pangloss_memgraph.databases.memgraph.read_incoming import (
    fetch_incoming_relations,
)
from pangloss_memgraph.databases.memgraph.validate_write import (
    ExistingHead,
    check_ids_available,
    check_inline_entities,
    check_references_exist,
    check_urls_available,
    check_user_exists,
    find_existing_entities,
    get_existing_head,
    get_tree_meta,
    replace_urls,
)


async def empty_page(tx: Transaction, query: str, params: dict) -> dict[str, Any]:
    """The result of a list that has no items on the page asked for: nothing is
    listed, but there may be a count of what there is on the other pages. (The query
    gives no row at all then, so the count comes from the first page.)"""
    page_key = "page" if "page" in params else "page_number"
    page, page_size = params[page_key], params["page_size"]

    total = 0
    if page > 1:
        result = await tx.run(query, **{**params, page_key: 1})
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


@Database.default.read_transaction
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
    query, params = build_generic_list_query(
        cls,
        search_terms=search_terms,
        page_number=page_number,
        page_size=page_size,
        deep_search=deep_search,
        published=published,
        review_status=review_status,
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

    results["results"] = type_adapter.validate_python(results["results"])
    result = _ListItems(**results)

    return result


@Database.default.read_transaction
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
    try:
        result = await tx.run(query, **params)
        rows = await result.value()
        found: dict = rows[0] if rows else await empty_page(tx, query, params)
    except TransientError as error:
        # (the driver would try a transient error again, and the search would take as long again)
        if "timeout" not in str(error).lower():
            raise
        raise PanglossSearchTimeoutError(
            "The search took longer than the time allowed for it: make it more specific"
        ) from None

    concrete_ref_types = [t.ReferenceView for t in get_concrete_types(cls)]
    adapter = TypeAdapter(list[Union[*concrete_ref_types]])  # type: ignore
    found["results"] = adapter.validate_python(found["results"])
    return _ListItems(**found)


@Database.default.read_transaction
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
    words = search_words(search_terms)
    page, size = page_number or 1, page_size or 10
    if not words:
        return AutocompleteResults(
            results=[],
            count=0,
            page=page,
            page_size=size,
            next_page=None,
            previous_page=page - 1 if page > 1 else None,
        )
    params = {
        "patterns": [f".*{word}.*" for word in words],
        "labels": labels_to_match(types or [cls]),
        "start": " ".join(words),
        "page": page,
        "page_size": size,
    }
    result = await tx.run(AUTOCOMPLETE_QUERY, **params)
    rows = await result.value()
    found: dict = rows[0] if rows else await empty_page(tx, AUTOCOMPLETE_QUERY, params)
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


@Database.default.read_transaction
async def get_document(
    tx: Transaction, cls: type[Document], id: UUID | AnyHttpUrl
) -> _DocumentHeadViewBase | None:
    """A head document. Of a class that has subclasses, this gives the view of the subclass the document
    is (its `type` says which)"""
    cls = await class_of_node(tx, cls, cast(UUID, id))
    query_string, query_params = build_fetch_document_query(cls, id)

    result = await tx.run(query_string, **query_params)
    records = await result.data()
    if records:
        return cls.HeadView(**tree_of(records[0]))
    return None


def tree_of(record: dict) -> dict:
    """The document, from a record returned by the query of `get_document`"""
    tree = build_tree(record["root"], record["root_labels"], record["edges"])
    tree["meta"] = record["meta"]
    return tree


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

    result = await tx.run(query_string, **query_params)
    records = await result.data()
    if not records:
        return None

    data = tree_of(records[0])
    data["urls"] = sorted(records[0]["urls"])
    if incoming:
        data.update(await fetch_incoming_relations(tx, cls, resolved_id))
    return data, cls


@Database.default.read_transaction
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


@Database.default.read_transaction
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


async def run_write_query(tx: Transaction, query: str, params: dict) -> list:
    """Run a query that writes, and get its result"""
    response = await tx.run(query, **params)  # type: ignore
    return await response.value()


@Database.default.write_transaction
async def soft_delete_node(
    tx: Transaction, cls: type[Document | Entity], id: UUID | AnyHttpUrl
) -> DeletionResult:
    return await soft_delete(tx, cls, id)


def announce(
    op: Literal["create", "update", "delete", "undelete"],
    model: type,
    id: UUID,
    version: int,
    payload: Any | None = None,
    created_entities: tuple[Any, ...] = (),
    restored_from: int | None = None,
) -> None:
    """Tell the listeners (`pangloss_models.hooks`) of a write that has committed"""
    emit_write_event(
        WriteEvent(
            op=op,
            model=model,
            id=id,
            version=version,
            user=current_request_username.get(),
            at=datetime.datetime.now(datetime.UTC),
            payload=payload,
            created_entities=created_entities,
            restored_from=restored_from,
        )
    )


async def delete_document(cls: type[Document], id: UUID) -> None:
    """Delete a head document (it is flagged, not removed). A document that is nested
    in another cannot be deleted."""
    result = await soft_delete_node(cls, id)
    if result.id is not None:
        announce("delete", cls, result.id, result.version)


async def delete_entity(cls: type[Entity], id: UUID | AnyHttpUrl) -> None:
    """Delete an entity that nothing refers to (it is flagged, not removed).

    If something does, it is not deleted, but marked for deletion
    (`meta.marked_for_deletion`), and a `PanglossEntityInUseError` is raised."""
    result = await soft_delete_node(cls, id)
    if result.deleted and result.id is not None:
        announce("delete", cls, result.id, result.version)
    if not result.deleted:
        raise PanglossEntityInUseError(
            f"{cls.__name__} {id} is referred to by {result.reference_count} "
            f"object{'s' if result.reference_count != 1 else ''}, so cannot be "
            "deleted. It has been marked for deletion",
            entity_id=id,
            referenced_by=result.referenced_by,
        )


@Database.default.write_transaction
async def undelete_node(
    tx: Transaction, cls: type[Document | Entity], id: UUID | AnyHttpUrl
) -> tuple[UUID, int]:
    return await undelete(tx, cls, id)


async def undelete_document(cls: type[Document], id: UUID) -> None:
    """Restore a deleted head document. `PanglossNotDeletedError` is raised if it has
    not been deleted."""
    node_id, version = await undelete_node(cls, id)
    announce("undelete", cls, node_id, version)


async def undelete_entity(cls: type[Entity], id: UUID | AnyHttpUrl) -> None:
    """Restore a deleted entity (by id or URL). `PanglossNotDeletedError` is raised if
    it has not been deleted."""
    node_id, version = await undelete_node(cls, id)
    announce("undelete", cls, node_id, version)


@Database.default.write_transaction
async def write_head_node(
    tx: Transaction,
    db_instance: _DocumentCreateDBBase,
) -> tuple[Any, ...]:
    """Write a new head node. Gives the entities that the write made as well (named in
    the document, and not there before)"""

    await check_user_exists(tx)

    query_object = build_head_create_query(db_instance)
    if query_object.inline_entities:
        # (the query is different for those that exist already)
        existing = await find_existing_entities(tx, query_object.inline_entities)
        check_inline_entities(query_object.inline_entities, existing)
        query_object = build_head_create_query(db_instance, existing)

    await check_references_exist(tx, query_object)
    await check_ids_available(tx, query_object, is_update=False)
    await check_urls_available(tx, query_object)

    result = await run_write_query(
        tx, query_object.to_query_string(), query_object.params
    )
    if not result:
        raise PanglossWriteError("Nothing was written")
    return query_object.created_entities()


# How many times a write is tried, if it loses a race to write the same id or URL
WRITE_ATTEMPTS = 3


async def write_with_retries(write, *args):
    """Run a write, again if it breaks a uniqueness constraint when it commits.

    That is an id or URL that another write used at the same moment, after this one
    had checked that it was free. Running it again checks again: if the other write
    made an entity that this one also writes, this one now finds it and uses it; if
    it is something that cannot be shared, it is a conflict."""
    for attempt in range(1, WRITE_ATTEMPTS + 1):
        try:
            return await write(*args)
        except ClientError as error:
            if "unique constraint" not in str(error).lower():
                raise
            if attempt == WRITE_ATTEMPTS:
                raise PanglossConflictError(
                    "An id or URL in this write was used by other writes at the "
                    "same time"
                ) from error


async def _get_head_view(cls: type[Document | Entity], id: UUID):
    if cls.__metatype__ == "Entity":
        return await get_entity(cast(type[Entity], cls), id)
    return await get_document(cast(type[Document], cls), id)


async def create_head_node(
    instance: _DocumentCreateBase,
    detail: bool = False,
    published: bool | None = None,
    review_status: str | None = None,
):
    """Create a Document or Entity. Returns its `ReferenceView`, or, if `detail`, its
    `HeadView`.

    With `pangloss-review`, a new document of a reviewed class is `unchecked` (not published) unless
    `published=True` (it is `checked`) or a `review_status` is given."""
    db_instance: _DocumentCreateDBBase = cast(
        _DocumentCreateDBBase, instance._to_db_model()
    )
    with hooks.requesting_review_status(
        hooks.review_status_asked(published, review_status)
    ):
        created_entities = await write_with_retries(write_head_node, db_instance)

    owner = cast(type[Document | Entity], instance._owner)
    announce("create", owner, db_instance.id, 1, db_instance, created_entities)
    if detail:
        return await _get_head_view(owner, db_instance.id)
    return owner.ReferenceView(
        **db_instance.model_dump(),
        meta=_DocumentReferenceViewAPIMeta(created_by=current_request_username.get()),
    )


@Database.default.write_transaction
async def replace_head_node(
    tx: Transaction,
    db_instance: _DocumentUpdateDBBase | _EntityUpdateDBBase,
    expected_version: int | None = None,
) -> tuple[ExistingHead, tuple[Any, ...]]:
    """Replace everything below a head node, and its properties, with the new
    version. All checks are made before anything is deleted, and if anything
    fails the transaction is rolled back.

    If `expected_version` is given, the update is only made if that is the version
    of the head node now. (Two updates at once are safe: both read the version, but
    both write to the head node, so the second is made to run again by the
    database, and then finds the new version.)"""

    await check_user_exists(tx)
    existing_head = await get_existing_head(tx, db_instance.id, db_instance.type)
    if expected_version is not None and existing_head.version != expected_version:
        raise PanglossVersionConflictError(
            f"{db_instance.type} {db_instance.id} is at version "
            f"{existing_head.version}, not {expected_version}: it has been updated "
            "since it was read",
            current_version=existing_head.version,
        )
    previous_meta = await get_tree_meta(tx, db_instance.id)

    query_object = build_head_update_query(db_instance, previous_meta)
    if query_object.inline_entities:
        existing = await find_existing_entities(tx, query_object.inline_entities)
        check_inline_entities(query_object.inline_entities, existing)
        query_object = build_head_update_query(db_instance, previous_meta, existing)

    await check_references_exist(tx, query_object)
    await check_ids_available(tx, query_object, is_update=True)
    await check_urls_available(tx, query_object)

    replace_query, replace_params = build_replace_head_query(db_instance)

    if not await run_write_query(tx, replace_query, replace_params):
        raise PanglossWriteError("Nothing was updated")

    # (the URLs of an entity are nodes it does not own, so they are replaced apart)
    urls = getattr(db_instance, "urls", None)
    if urls is not None:
        await replace_urls(tx, db_instance.id, [str(url) for url in urls])

    if not await run_write_query(
        tx, query_object.to_query_string(), query_object.params
    ):
        raise PanglossWriteError("Nothing was written")

    return existing_head, query_object.created_entities()


async def update_head_node(
    instance: _DocumentUpdateBase | _EntityUpdateBase,
    detail: bool = False,
    expected_version: int | None = None,
    restored_from: int | None = None,
    published: bool | None = None,
    review_status: str | None = None,
):
    """Replace a Document or Entity (and, for a Document, everything nested in it)
    with the given version.

    With `pangloss-review`, an update leaves the review state as it is unless `published` (`True` is `checked`,
    `False` is `unchecked`) or `review_status` is given.

    `restored_from` is only for what listens to writes (history): that this update puts
    back that earlier version.

    `expected_version` is the `meta.version` that the new version was made from:
    if someone has updated it since, `PanglossVersionConflictError` is raised and
    nothing is written. Without it, the update is made whatever the version."""
    db_instance = cast(
        _DocumentUpdateDBBase | _EntityUpdateDBBase, instance._to_db_model()
    )
    with hooks.requesting_review_status(
        hooks.review_status_asked(published, review_status)
    ):
        existing_head, created_entities = await write_with_retries(
            replace_head_node, db_instance, expected_version
        )

    owner = cast(type[Document | Entity], instance._owner)
    announce(
        "update",
        owner,
        db_instance.id,
        existing_head.version + 1,
        db_instance,
        created_entities,
        restored_from,
    )
    if detail:
        return await _get_head_view(owner, db_instance.id)
    return owner.ReferenceView(
        **db_instance.model_dump(),
        meta=_DocumentReferenceViewAPIMeta(
            created_by=existing_head.created_by,
            created_when=existing_head.created_when,
            updated_by=current_request_username.get(),
            updated_when=datetime.datetime.now(datetime.UTC),
        ),
    )


# ---------------------------------------------------------------------------
# Users (see `pangloss_users.service`)
# ---------------------------------------------------------------------------


@Database.default.write_transaction
async def create_user_in_db(tx: Transaction, user: UserInDB) -> None:
    await users.create_user(tx, user)


@Database.default.read_transaction
async def get_user_in_db(tx: Transaction, username: str) -> UserInDB | None:
    return await users.get_user(tx, username)


@Database.default.read_transaction
async def get_user_in_db_by_email(tx: Transaction, email: str) -> UserInDB | None:
    return await users.get_user_by_email(tx, email)


@Database.default.read_transaction
async def list_users_in_db(tx: Transaction) -> list[UserInDB]:
    return await users.list_users(tx)


@Database.default.write_transaction
async def update_user_in_db(
    tx: Transaction, username: str, changes: dict[str, Any]
) -> UserInDB:
    return await users.update_user(tx, username, changes)


@Database.default.write_transaction
async def revoke_session_in_db(
    tx: Transaction, jti: str, expires: datetime.datetime
) -> None:
    await users.revoke_session(tx, jti, expires)


@Database.default.read_transaction
async def is_session_revoked_in_db(tx: Transaction, jti: str) -> bool:
    return await users.is_session_revoked(tx, jti)


@Database.default.write_transaction
async def create_access_token_in_db(tx: Transaction, record: AccessTokenRecord) -> None:
    await users.create_access_token(tx, record)


@Database.default.read_transaction
async def get_access_token_in_db_by_hash(
    tx: Transaction, token_hash: str
) -> AccessTokenRecord | None:
    return await users.get_access_token_by_hash(tx, token_hash)


@Database.default.read_transaction
async def list_access_tokens_in_db(
    tx: Transaction, username: str
) -> list[AccessTokenRecord]:
    return await users.list_access_tokens(tx, username)


@Database.default.write_transaction
async def delete_access_token_in_db(tx: Transaction, username: str, id: str) -> bool:
    return await users.delete_access_token(tx, username, id)


@Database.default.write_transaction
async def touch_access_token_in_db(
    tx: Transaction, id: str, when: datetime.datetime
) -> None:
    await users.touch_access_token(tx, id, when)


# Review (`pangloss-review`)


@Database.default.read_transaction
async def get_review_state_in_db(tx: Transaction, id: UUID) -> dict[str, Any] | None:
    return await review.get_review_state(tx, id)


@Database.default.write_transaction
async def set_review_status_in_db(
    tx: Transaction, id: UUID, status: str, published: bool, user: str
) -> dict[str, Any] | None:
    return await review.set_review_status(tx, id, status, published, user)


@Database.default.write_transaction
async def add_review_comment_in_db(
    tx: Transaction, id: UUID, username: str, text: str, target_id: UUID | None
) -> dict[str, Any] | str | None:
    return await review.add_review_comment(tx, id, username, text, target_id)


@Database.default.read_transaction
async def list_review_comments_in_db(
    tx: Transaction, id: UUID, include_resolved: bool
) -> list[dict[str, Any]]:
    return await review.list_review_comments(tx, id, include_resolved)


@Database.default.write_transaction
async def resolve_review_comment_in_db(
    tx: Transaction, id: UUID, comment_id: UUID, user: str
) -> dict[str, Any] | None:
    return await review.resolve_review_comment(tx, id, comment_id, user)


@Database.default.read_transaction
async def review_queue_in_db(
    tx: Transaction, statuses: list[str], type: str | None, page: int, page_size: int
) -> dict[str, Any]:
    return await review.review_queue(tx, statuses, type, page, page_size)
