import datetime
import functools
import os
import time
from typing import Literal, Union, cast
from uuid import UUID

from neo4j import AsyncResult
from pangloss_models.exceptions import PanglossWriteError
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
    _EntityHeadViewBase,
    _EntityReferenceViewBase,
    _EntityUpdateBase,
    _EntityUpdateDBBase,
)
from pangloss_models.utils import get_concrete_types
from pangloss_users import current_request_username
from pydantic import AnyHttpUrl, AnyUrl, TypeAdapter

from pangloss_memgraph.databases.memgraph.build_create_query import (
    build_head_create_query,
)
from pangloss_memgraph.databases.memgraph.build_list_query import (
    build_generic_list_query,
)
from pangloss_memgraph.databases.memgraph.build_read_query import (
    build_fetch_document_query,
)
from pangloss_memgraph.databases.memgraph.build_update_query import (
    build_head_update_query,
    build_replace_head_query,
)
from pangloss_memgraph.databases.memgraph.database import Database, Transaction
from pangloss_memgraph.databases.memgraph.read_incoming import (
    fetch_incoming_relations,
)
from pangloss_memgraph.databases.memgraph.validate_write import (
    ExistingHead,
    check_ids_available,
    check_references_exist,
    check_user_exists,
    get_existing_head,
    get_tree_meta,
)


def timer(func):
    @functools.wraps(func)
    async def wrapper(*args, **kwargs):
        start = time.perf_counter()
        result = await func(*args, **kwargs)
        end = time.perf_counter()
        print(f"{func.__name__} took {end - start:.12f}s")
        return result

    return wrapper


@Database.default.read_transaction
@timer
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

    dump_query("list", query, params)

    concrete_types = get_concrete_types(cls)
    concrete_ref_types = [t.ReferenceView for t in concrete_types]

    type_adapter = TypeAdapter(list[Union[*concrete_ref_types]])  # type: ignore

    result = await tx.run(query, **params)
    result_values = await result.value()

    results: dict = result_values[0]

    results["results"] = type_adapter.validate_python(results["results"])
    result = _ListItems(**results)

    return result


@Database.default.read_transaction
@timer
async def get_document(
    tx: Transaction, cls: type[Document], id: UUID | AnyHttpUrl
) -> _DocumentHeadViewBase:

    query_string, query_params = build_fetch_document_query(cls, id)
    dump_query("read", query_string, query_params)

    result = await tx.run(query_string, **query_params)
    result_value = await result.value()
    if result_value:
        return cls.HeadView(**result_value[0])
    return None


def dump_query(name: str, query: str, params: dict) -> None:
    """Write the last query of each kind to `.query_dumps`, for debugging"""
    os.makedirs(".query_dumps", exist_ok=True)
    with open(f".query_dumps/{name}.cypher", "w") as f:
        f.write(f"""{query}

            // {params!s}
            """)


@Database.default.read_transaction
@timer
async def get_entity(
    tx: Transaction, cls: type[Entity], id: UUID | AnyHttpUrl
) -> _EntityHeadViewBase | None:
    """An entity, with its own values and relations, and the documents (and
    entities) that refer to it, in the fields named after the reverse relations"""

    if isinstance(id, AnyUrl):
        result = await tx.run(
            "MATCH (entity:PGIndexableNode) WHERE $url IN entity.urls RETURN entity.id AS id",
            url=str(id),
        )
        found = await result.value()
        if not found:
            return None
        id = UUID(found[0])

    query_string, query_params = build_fetch_document_query(cls, id)
    dump_query("read_entity", query_string, query_params)

    result = await tx.run(query_string, **query_params)
    result_value = await result.value()
    if not result_value:
        return None

    data = result_value[0]
    data.update(await fetch_incoming_relations(tx, cls, id))
    return cls.HeadView(**data)


@Database.default.write_transaction
@timer
async def write_head_node(
    tx: Transaction,
    db_instance: _DocumentCreateDBBase,
) -> list:

    query_object = build_head_create_query(db_instance)

    await check_user_exists(tx)
    await check_references_exist(tx, query_object)
    await check_ids_available(tx, query_object, is_update=False)

    dump_query("create", query_object.to_query_string(), query_object.params)

    response = await tx.run(query_object.to_query_string(), **query_object.params)
    result = await response.value()
    if not result:
        raise PanglossWriteError("Nothing was written")
    return result


async def create_head_node(
    instance: _DocumentCreateBase,
    return_type: Literal["Reference", "Full"] = "Reference",
):
    db_instance: _DocumentCreateDBBase = cast(
        _DocumentCreateDBBase, instance._to_db_model()
    )
    await write_head_node(db_instance)

    if return_type == "Reference":
        return cast(type[Document], instance._owner).ReferenceView(
            **db_instance.model_dump(),
            meta=_DocumentReferenceViewAPIMeta(
                created_by=current_request_username.get()
            ),
        )
    if return_type == "Full":
        return await get_document(cast(type[Document], instance._owner), db_instance.id)


@Database.default.write_transaction
@timer
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

    await check_references_exist(tx, query_object)
    await check_ids_available(tx, query_object, is_update=True)

    replace_query, replace_params = build_replace_head_query(db_instance)
    dump_query("update_replace", replace_query, replace_params)
    dump_query("update", query_object.to_query_string(), query_object.params)

    response = await tx.run(replace_query, **replace_params)
    if not await response.value():
        raise PanglossWriteError("Nothing was updated")

    response = await tx.run(query_object.to_query_string(), **query_object.params)
    if not await response.value():
        raise PanglossWriteError("Nothing was written")

    return existing_head


async def update_head_node(
    instance: _DocumentUpdateBase | _EntityUpdateBase,
    return_type: Literal["Reference", "Full"] = "Reference",
):
    """Replace a Document or Entity (and, for a Document, everything nested in it)
    with the given version"""
    db_instance = cast(
        _DocumentUpdateDBBase | _EntityUpdateDBBase, instance._to_db_model()
    )
    existing_head = await replace_head_node(db_instance)

    owner = cast(type[Document], instance._owner)
    if return_type == "Reference":
        return owner.ReferenceView(
            **db_instance.model_dump(),
            meta=_DocumentReferenceViewAPIMeta(
                created_by=existing_head.created_by,
                created_when=existing_head.created_when,
                updated_by=current_request_username.get(),
                updated_when=datetime.datetime.now(datetime.UTC),
            ),
        )
    if return_type == "Full":
        return await get_document(owner, db_instance.id)
