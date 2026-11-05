"""Reading derived facts from Python: `SameFamily.list(...)`, `SameFamily.get(id)`, `pangloss_derived.graph("family")`.

As the models' own functions, these are bound to the storage in use when the models are initialised (`bind_reads`):
on the server (a backend that runs Cypher) they read the graph (`read`); with the SDK they ask the server's API
(`/api/derived/...`), `async` or blocking as the SDK was connected, and give the same views.
"""

from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, Field

from pangloss_derived.registry import DerivedRegistry, PanglossDerivedError

if TYPE_CHECKING:
    from pangloss_derived.declare import Derived


class DerivedPage(BaseModel):
    """A page of derived facts"""

    results: list[Any] = Field(default_factory=list)
    count: int = 0
    page: int = 1
    page_size: int = 25
    next_page: int | None = None
    previous_page: int | None = None


def storage_kind() -> str:
    """`cypher` (the server), `api` (the SDK) or `api_sync` (the blocking SDK)"""
    from pangloss_core import storage_of

    storage = storage_of()
    if storage.capabilities.cypher:
        return "cypher"
    return "api_sync" if storage.package.endswith("api_sync") else "api"


# -- the API ----------------------------------------------------------------------------------------------------------


def call(path: str, params: dict[str, Any] | None = None) -> Any:
    from pangloss_sdk.protocol import Call

    return Call("GET", path, params=params)


def answer(response: Any) -> Any:
    from pangloss_sdk.protocol import check

    if response.status_code == 404:
        return None
    check(response)
    return response.json()


def list_params(
    model: type["Derived"],
    where: Any,
    entity: Any,
    page: int,
    page_size: int,
    evidence: Any,
) -> dict[str, Any]:
    from pangloss_derived.views import ids

    params: dict[str, Any] = {"page": page, "page_size": page_size}
    if where is not None:
        for field in model._fields.values():
            value = getattr(where, field.name, None)
            if value is not None:
                params[field.name] = (
                    ids(value)
                    if field.kind == "relation"
                    else getattr(value, "value", value)
                )
        for name in ("plain", "context_label", "rule_type"):
            value = getattr(where, name)
            if value is not None:
                params[name] = str(value).lower() if isinstance(value, bool) else value
    if entity is not None:
        params["entity"] = ids(entity)
    if evidence is not None:
        params["evidence"] = ids(evidence)
    return params


def page_from(model: type["Derived"], data: dict[str, Any]) -> DerivedPage:
    return DerivedPage(
        results=[model.View.model_validate(r) for r in data["results"]],
        count=data["count"],
        page=data["page"],
        page_size=data["pageSize"],
        next_page=data["nextPage"],
        previous_page=data["previousPage"],
    )


def graph_from(type_name: str, data: Any) -> list[dict[str, Any]]:
    if data is None:
        raise PanglossDerivedError(f"There is no type of rule called {type_name!r}")
    return data["edges"]


# -- async: the server, or the SDK ------------------------------------------------------------------------------------


async def list_facts(
    model: type["Derived"],
    where: Any = None,
    entity: Any = None,
    page: int = 1,
    page_size: int = 25,
    evidence: Any = None,
) -> DerivedPage:
    if storage_kind() == "api":
        from pangloss_sdk.client import current_async_client

        response = await current_async_client().send(
            call(
                f"/api/derived/{model.__name__}",
                list_params(model, where, entity, page, page_size, evidence),
            )
        )
        return page_from(model, answer(response))
    from pangloss_derived import read

    return DerivedPage(
        **await read.list_facts(model, where, entity, page, page_size, evidence)
    )


async def get_fact(model: type["Derived"], id: str) -> Any | None:
    if storage_kind() == "api":
        from pangloss_sdk.client import current_async_client

        data = answer(
            await current_async_client().send(
                call(f"/api/derived/{model.__name__}/{id}")
            )
        )
        return None if data is None else model.View.model_validate(data)
    from pangloss_derived import read

    return await read.get_fact(model, id)


async def graph_async(type_name: str, plain_only: bool = False) -> list[dict[str, Any]]:
    if storage_kind() == "api":
        from pangloss_sdk.client import current_async_client

        response = await current_async_client().send(
            call(f"/api/derived/graph/{type_name}", {"plain": str(plain_only).lower()})
        )
        return graph_from(type_name, answer(response))
    from pangloss_derived import read

    return await read.graph(type_name, plain_only)


# -- blocking: the SDK connected with `sync=True` ---------------------------------------------------------------------


def list_facts_sync(
    model: type["Derived"],
    where: Any = None,
    entity: Any = None,
    page: int = 1,
    page_size: int = 25,
    evidence: Any = None,
) -> DerivedPage:
    from pangloss_sdk.client import current_client

    response = current_client().send(
        call(
            f"/api/derived/{model.__name__}",
            list_params(model, where, entity, page, page_size, evidence),
        )
    )
    return page_from(model, answer(response))


def get_fact_sync(model: type["Derived"], id: str) -> Any | None:
    from pangloss_sdk.client import current_client

    data = answer(current_client().send(call(f"/api/derived/{model.__name__}/{id}")))
    return None if data is None else model.View.model_validate(data)


def graph_sync(type_name: str, plain_only: bool = False) -> list[dict[str, Any]]:
    from pangloss_sdk.client import current_client

    response = current_client().send(
        call(f"/api/derived/graph/{type_name}", {"plain": str(plain_only).lower()})
    )
    return graph_from(type_name, answer(response))


def graph(type_name: str, plain_only: bool = False) -> Any:
    """A coroutine, or with the blocking SDK the edges (`pangloss_derived.graph`)"""
    if storage_kind() == "api_sync":
        return graph_sync(type_name, plain_only)
    return graph_async(type_name, plain_only)


def bind_reads() -> None:
    """(At `initialise`) `Derived.list` and `Derived.get` as the storage in use has them: `async`, or blocking with the
    blocking SDK"""
    from pangloss_derived.declare import Derived

    if storage_kind() == "api_sync":
        Derived.list = classmethod(list_facts_sync)  # type: ignore[assignment]
        Derived.get = classmethod(get_fact_sync)  # type: ignore[assignment]
    else:
        Derived.list = classmethod(list_facts)  # type: ignore[assignment]
        Derived.get = classmethod(get_fact)  # type: ignore[assignment]
    _ = DerivedRegistry
