import datetime
from typing import Any, Union, cast
from uuid import UUID

from neo4j import AsyncResult
from neo4j.exceptions import ClientError
from pangloss_models.exceptions import (
    PanglossConflictError,
    PanglossEntityInUseError,
    PanglossWriteError,
)
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
    _EntityCreateDBBase,
    _EntityEditViewBase,
    _EntityHeadViewBase,
    _EntityReferenceViewBase,
    _EntityUpdateBase,
    _EntityUpdateDBBase,
)
from pangloss_models.utils import get_concrete_types
from pangloss_users import current_request_username
from pangloss_users.models import UserInDB
from pydantic import AnyHttpUrl, TypeAdapter

from pangloss_memgraph.databases.memgraph.build_create_query import (
    build_head_create_query,
)
from pangloss_memgraph.databases.memgraph.build_list_query import (
    build_generic_list_query,
)
from pangloss_memgraph.databases.memgraph.build_read_query import (
    build_fetch_document_query,
)
from pangloss_memgraph.databases.memgraph.build_tree import build_tree
from pangloss_memgraph.databases.memgraph.build_update_query import (
    build_head_update_query,
    build_replace_head_query,
)
from pangloss_memgraph.databases.memgraph.database import Database, Transaction
from pangloss_memgraph.databases.memgraph import users
from pangloss_memgraph.databases.memgraph.delete_node import (
    DeletionResult,
    soft_delete,
    undelete,
)
from pangloss_memgraph.databases.memgraph.lookup import resolve_id
from pangloss_memgraph.databases.memgraph.read_enums import convert_enums
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
)


@Database.default.read_transaction
async def list_items(
    tx: Transaction,
    cls: type[Document | Entity],
    search_terms: str | None = None,
    page_number: int | None = None,
    page_size: int | None = None,
    deep_search: bool = False,
) -> _ListItems[_DocumentReferenceViewBase | _EntityReferenceViewBase]:
    query, params = build_generic_list_query(
        cls,
        search_terms=search_terms,
        page_number=page_number,
        page_size=page_size,
        deep_search=deep_search,
    )


    concrete_types = get_concrete_types(cls)
    concrete_ref_types = [t.ReferenceView for t in concrete_types]

    type_adapter = TypeAdapter(list[Union[*concrete_ref_types]])  # type: ignore

    result = await tx.run(query, **params)
    result_values = await result.value()

    results: dict = result_values[0]

    results["results"] = type_adapter.validate_python(
        convert_enums(results["results"])
    )
    result = _ListItems(**results)

    return result


@Database.default.read_transaction
async def get_document(
    tx: Transaction, cls: type[Document], id: UUID | AnyHttpUrl
) -> _DocumentHeadViewBase:

    query_string, query_params = build_fetch_document_query(cls, id)

    result = await tx.run(query_string, **query_params)
    records = await result.data()
    if records:
        return cls.HeadView(**convert_enums(tree_of(records[0])))
    return None


def tree_of(record: dict) -> dict:
    """The document, from a record returned by the query of `get_document`"""
    tree = build_tree(record["root"], record["root_labels"], record["edges"])
    tree["meta"] = record["meta"]
    return tree


async def read_entity(
    tx: Transaction, cls: type[Entity], id: UUID | AnyHttpUrl, incoming: bool
) -> dict | None:
    """The data of an entity (with the incoming relations, if `incoming`)"""
    resolved_id = await resolve_id(tx, id)
    if resolved_id is None:
        return None

    query_string, query_params = build_fetch_document_query(cls, resolved_id)

    result = await tx.run(query_string, **query_params)
    records = await result.data()
    if not records:
        return None

    data = tree_of(records[0])
    if incoming:
        data.update(await fetch_incoming_relations(tx, cls, resolved_id))
    return convert_enums(data)


@Database.default.read_transaction
async def get_entity(
    tx: Transaction, cls: type[Entity], id: UUID | AnyHttpUrl
) -> _EntityHeadViewBase | None:
    """An entity, with its own values and relations, and the documents (and
    entities) that refer to it, in the fields named after the reverse relations"""
    data = await read_entity(tx, cls, id, incoming=True)
    return cls.HeadView(**data) if data is not None else None


@Database.default.read_transaction
async def get_entity_for_edit(
    tx: Transaction, cls: type[Entity], id: UUID | AnyHttpUrl
) -> _EntityEditViewBase | None:
    """An entity as it is edited: its own values and outgoing relations, without
    the incoming relations (which are not looked for)"""
    data = await read_entity(tx, cls, id, incoming=False)
    return cls.EditView(**data) if data is not None else None


async def run_write_query(tx: Transaction, query: str, params: dict) -> list:
    """Run a query that writes, and get its result. An enum that is not in the
    database (because `initialise_database` has not been run since the models
    changed) is reported as such."""
    try:
        response = await tx.run(query, **params)  # type: ignore
        return await response.value()
    except ClientError as error:
        if "Invalid enum" in str(error):
            raise PanglossWriteError(
                f"{error.message}: the database does not have this enum or member. "
                "Run initialise_database() (after initialising the models) to make "
                "the enums used by the models"
            ) from error
        raise


@Database.default.write_transaction
async def soft_delete_node(
    tx: Transaction, cls: type[Document | Entity], id: UUID | AnyHttpUrl
) -> DeletionResult:
    return await soft_delete(tx, cls, id)


async def delete_document(cls: type[Document], id: UUID) -> None:
    """Delete a head document (it is flagged, not removed). A document that is nested
    in another cannot be deleted."""
    await soft_delete_node(cls, id)


async def delete_entity(cls: type[Entity], id: UUID | AnyHttpUrl) -> None:
    """Delete an entity that nothing refers to (it is flagged, not removed).

    If something does, it is not deleted, but marked for deletion
    (`meta.marked_for_deletion`), and a `PanglossEntityInUseError` is raised."""
    result = await soft_delete_node(cls, id)
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
) -> None:
    await undelete(tx, cls, id)


async def undelete_document(cls: type[Document], id: UUID) -> None:
    """Restore a deleted head document. `PanglossNotDeletedError` is raised if it has
    not been deleted."""
    await undelete_node(cls, id)


async def undelete_entity(cls: type[Entity], id: UUID | AnyHttpUrl) -> None:
    """Restore a deleted entity (by id or URL). `PanglossNotDeletedError` is raised if
    it has not been deleted."""
    await undelete_node(cls, id)


@Database.default.write_transaction
async def write_head_node(
    tx: Transaction,
    db_instance: _DocumentCreateDBBase,
) -> list:

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
    return result


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
):
    """Create a Document or Entity. Returns its `ReferenceView`, or, if `detail`, its
    `HeadView`"""
    db_instance: _DocumentCreateDBBase = cast(
        _DocumentCreateDBBase, instance._to_db_model()
    )
    await write_with_retries(write_head_node, db_instance)

    owner = cast(type[Document | Entity], instance._owner)
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
) -> ExistingHead:
    """Replace everything below a head node, and its properties, with the new
    version. All checks are made before anything is deleted, and if anything
    fails the transaction is rolled back."""

    await check_user_exists(tx)
    existing_head = await get_existing_head(tx, db_instance.id, db_instance.type)
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

    if not await run_write_query(
        tx, query_object.to_query_string(), query_object.params
    ):
        raise PanglossWriteError("Nothing was written")

    return existing_head


async def update_head_node(
    instance: _DocumentUpdateBase | _EntityUpdateBase,
    detail: bool = False,
):
    """Replace a Document or Entity (and, for a Document, everything nested in it)
    with the given version"""
    db_instance = cast(
        _DocumentUpdateDBBase | _EntityUpdateDBBase, instance._to_db_model()
    )
    existing_head = await write_with_retries(replace_head_node, db_instance)

    owner = cast(type[Document | Entity], instance._owner)
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
