import functools
import time
from typing import Literal, Union, cast
from uuid import UUID

from neo4j import AsyncResult
from pangloss_models.model_bases.base_models import _ListItems
from pangloss_models.model_bases.document import (
    Document,
    _DocumentCreateBase,
    _DocumentCreateDBBase,
    _DocumentHeadViewBase,
    _DocumentReferenceViewAPIMeta,
    _DocumentReferenceViewBase,
    _DocumentUpdateDBBase,
)
from pangloss_models.model_bases.entity import (
    Entity,
    _EntityCreateDBBase,
    _EntityReferenceViewBase,
    _EntityUpdateDBBase,
)
from pangloss_models.utils import get_concrete_types
from pangloss_users import current_request_username
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
from pangloss_memgraph.databases.memgraph.database import Database, Transaction


def timer(func):
    @functools.wraps(func)
    async def wrapper(*args, **kwargs):
        start = time.perf_counter()
        result = await func(*args, **kwargs)
        end = time.perf_counter()
        print(f"{func.__name__} took {end - start:.12f}s")
        return result

    return wrapper


def save(
    tx,
    self: _EntityCreateDBBase
    | _DocumentCreateDBBase
    | _EntityUpdateDBBase
    | _DocumentUpdateDBBase,
):
    print("wahoo!", self)


@Database.default.read_transaction
@timer
async def list_items(
    tx: Transaction, cls: type[Document | Entity], search_terms: str | None
) -> _ListItems[_DocumentReferenceViewBase | _EntityReferenceViewBase]:
    query, params = build_generic_list_query(cls, search_terms)

    concrete_types = get_concrete_types(cls)
    concrete_ref_types = [t.ReferenceView for t in concrete_types]

    print(concrete_ref_types)
    type_adapter = TypeAdapter(list[Union[*concrete_ref_types]])

    result = await tx.run(query, **params)
    result_values = await result.value()
    results: dict = result_values[0]
    results["results"] = type_adapter.validate_python(results["results"])
    result = _ListItems(**results)
    print(result)
    return result
    # items = [cls.ReferenceView(item) for item in result_values]
    # print(items)


@Database.default.read_transaction
@timer
async def get_document(
    tx: Transaction, cls: type[Document], id: UUID | AnyHttpUrl
) -> _DocumentHeadViewBase:

    query_string, query_params = build_fetch_document_query(cls, id)
    with open(".query_dumps/read.cypher", "w") as f:
        f.write(f"""{query_string}

            // {query_params!s}
            """)

    result = await tx.run(query_string, **query_params)
    result_value = await result.value()
    if result_value:
        return cls.HeadView(**result_value[0])
    return None


@Database.default.write_transaction
@timer
async def write_head_node(
    tx: Transaction,
    db_instance: _DocumentCreateDBBase,
) -> AsyncResult:

    query_object = build_head_create_query(db_instance)

    with open(".query_dumps/create.cypher", "w") as f:
        f.write(f"""{query_object.to_query_string()}

            // {query_object.params!s}
            """)

    response = await tx.run(query_object.to_query_string(), **query_object.params)
    result = await response.value()
    print(result)
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
