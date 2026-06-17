import datetime
import functools
import json
import time
from typing import TYPE_CHECKING, overload
from uuid import UUID, uuid7

from pangloss_models.model_bases.base_models import (
    _APIHeadMeta,
    _CreateDBBase,
    _UpdateDBBase,
)
from pangloss_models.model_bases.document import (
    Document,
    _DocumentCreateBase,
    _DocumentCreateDBBase,
    _DocumentHeadViewBase,
    _DocumentUpdateDBBase,
)
from pangloss_models.model_bases.entity import (
    Entity,
    _EntityCreateBase,
    _EntityCreateDBBase,
    _EntityUpdateBase,
    _EntityUpdateDBBase,
)
from pydantic import AnyHttpUrl

from pangloss_memgraph.databases.memgraph.build_create_query import (
    build_head_create_query,
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
        print(f"{func.__name__} took {end - start:.12f}s : {kwargs}")
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
async def get_document(
    tx: Transaction, cls: type[Document], id: UUID | AnyHttpUrl
) -> _DocumentHeadViewBase:

    query_string, query_params = build_fetch_document_query(cls, id)
    with open(".query_dumps/read.cypher", "w") as f:
        f.write(f"""{query_string}

            // {str(query_params)}
            """)

    result = await tx.run(query_string, **query_params)
    result_value = await result.value()
    if result_value:
        return cls.HeadView(**result_value[0])
    return None


@Database.default.write_transaction
@timer
async def create_head_node(
    tx: Transaction,
    instance: _DocumentCreateBase,
    return_created: bool = False,
) -> _DocumentHeadViewBase | None:
    db_instance: _DocumentCreateDBBase = instance._to_db_model()
    query_object = build_head_create_query(db_instance)

    with open(".query_dumps/create.cypher", "w") as f:
        f.write(f"""{query_object.to_query_string()}

            // {str(query_object.params)}
            """)

    result = await tx.run(query_object.to_query_string(), **query_object.params)
    result_value = await result.value()
    print(result_value)
    return instance._owner.ReferenceView(**db_instance.model_dump())
