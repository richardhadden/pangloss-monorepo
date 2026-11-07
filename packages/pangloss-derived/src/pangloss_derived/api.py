"""`/api/derived`: derived facts, and the worker that keeps them up to date (a background task of the server).

    GET /api/derived                                  the derived classes, the rules and the types of rule
    GET /api/derived/status                           what is pending, the state of each rule, what the worker did
    GET /api/derived/graph/{type}?plain=true          the facts of the rules of a type, as edges
    GET /api/derived/about/{Type}/{id}                what the rules derive about an entity or a head document: for
                                                      each class, a count and a first page (what its view has as
                                                      `_derived`, for a reader that asks for it apart)
    GET /api/derived/{Class}?entity=…&page=2          a page of the facts of a class (of an entity, or `evidence=` a
                                                      document; and `plain`, `context_label`, `rule_type`, and a value
                                                      for any field)
    GET /api/derived/{Class}/{id}                     one, with the justifications the reader sees ("why")

What a reader sees is as for documents: a fact is seen if one of its justifications rests only on documents the reader
may see. The view of an entity (`GET /api/Person/{id}`) and of a head document has `_derived`, a first page of each class
(unless read with `?extras=false`; `/api/derived/about/{Type}/{id}` gives the same apart).

The worker runs in the server unless the setting `DERIVED_WORKER_IN_SERVER` is false (for a deployment that runs
`pangloss derive worker` on its own). Only one worker works at a time, whichever process it is in.
"""

from typing import Annotated, Any

from fastapi import APIRouter, FastAPI, HTTPException, Query, Request, status
from fastapi.responses import JSONResponse
from pangloss_api import (
    BackgroundTask,
    checks_own_parameters,
    refuse_unknown_parameters,
)

from pangloss_derived import read
from pangloss_derived.check import ends_of
from pangloss_derived.registry import DerivedRegistry, PanglossDerivedError
from pangloss_derived.worker import pending_status, worker

router = APIRouter(prefix="/api/derived", tags=["derived"])


async def derived_error_handler(request: Request, error: Exception) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_404_NOT_FOUND,
        content={"detail": str(error), "error": type(error).__name__},
    )


def configure_app(app: FastAPI, settings: Any) -> None:
    app.add_exception_handler(PanglossDerivedError, derived_error_handler)
    if getattr(settings, "DERIVED_WORKER_IN_SERVER", True):
        app.state.background_tasks.append(BackgroundTask("derived", worker.run))


def dumped(view: Any) -> dict[str, Any]:
    return view.model_dump(by_alias=True, mode="json")


@router.get("", operation_id="derived_schema")
async def schema() -> dict[str, Any]:
    """What can be derived, and how"""
    classes = {}
    for name, model in DerivedRegistry.concrete_classes().items():
        classes[name] = {
            "description": (model.__doc__ or "").strip(),
            "fields": {
                f.name: {
                    "kind": f.kind,
                    "type": getattr(f.model, "__name__", str(f.model)),
                }
                for f in model._fields.values()
            },
            "symmetric": bool(model._meta.symmetric),
            "symmetricLabel": read.symmetric_label_of(model),
            "ends": list(ends_of(model)),
        }
    rules = {
        name: {
            "class": rule.model.__name__,
            "description": rule.rule.description,
            "types": rule.type_names,
            "datalog": rule.describe(),
        }
        for name, rule in DerivedRegistry.checked.items()
    }
    types = {
        name: {
            "description": t.description,
            "rules": [
                r
                for r, rule in DerivedRegistry.checked.items()
                if name in rule.type_names
            ],
        }
        for name, t in DerivedRegistry.types.items()
    }
    return {"classes": classes, "rules": rules, "types": types}


@router.get("/status", operation_id="derived_status")
async def get_status() -> dict[str, Any]:
    found = await pending_status()
    stats = worker.stats
    return {
        "pending": found["pending"],
        "rules": {
            name: {k: v for k, v in state.items() if k != "name"}
            for name, state in found["rules"].items()
        },
        "worker": {
            "batches": stats.batches,
            "heads": stats.heads,
            "new": stats.new,
            "removed": stats.removed,
            "overflows": stats.overflows,
            "secondsFinding": round(stats.seconds_finding, 3),
            "secondsWriting": round(stats.seconds_writing, 3),
            "lastBatchAt": stats.last_batch_at,
            "rebuilds": stats.rebuilds,
        },
    }


@router.get("/graph/{type_name}", operation_id="derived_graph")
async def get_graph(
    type_name: str,
    plain: Annotated[
        bool, Query(description="Only facts with a plain justification")
    ] = False,
) -> dict[str, Any]:
    edges = await read.graph(type_name, plain_only=plain)
    return {"type": type_name, "count": len(edges), "edges": edges}


@router.get("/about/{type_name}/{id}", operation_id="derived_about")
async def get_about(type_name: str, id: str) -> dict[str, Any]:
    """What the rules derive about an entity or a head document, of the class `type_name` (its own, as its view
    says): for each derived class that points at it (by its name, or its reverse name), the count and a first page,
    as the view has it under `_derived`. Empty when nothing is derived about it; 404 if there is no such class"""
    from pangloss_models import Document, Entity, ModelRegistry

    owner = ModelRegistry.all_models().get(type_name)
    if owner is None or not issubclass(owner, (Entity, Document)):
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, f"There is no model called {type_name!r}"
        )
    return await read.derived_of_entity(owner, id)


@router.get("/{name}", operation_id="derived_list")
@checks_own_parameters
async def list_derived(
    name: str,
    request: Request,
    entity: Annotated[
        str | None, Query(description="Only the facts about this entity")
    ] = None,
    evidence: Annotated[
        str | None,
        Query(description="Only the facts this head document is evidence of"),
    ] = None,
    plain: Annotated[bool | None, Query()] = None,
    context_label: Annotated[str | None, Query()] = None,
    rule_type: Annotated[
        str | None, Query(description="Derived by a rule of this type")
    ] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=read.MAX_PAGE_SIZE)] = read.FIRST_PAGE,
) -> dict[str, Any]:
    """A page of the facts of the class. A field of the class can be given as a parameter (`?family=<id>`)"""
    model = read.derived_class(name)
    refuse_unknown_parameters(request, also=model._fields)
    fields = {
        key: value
        for key, value in request.query_params.items()
        if key in model._fields
    }
    try:
        where = model.Where(
            plain=plain, context_label=context_label, rule_type=rule_type, **fields
        )
    except ValueError as error:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(error)) from None
    found = await read.list_facts(model, where, entity, page, page_size, evidence)
    return {
        "results": [dumped(v) for v in found["results"]],
        "count": found["count"],
        "page": found["page"],
        "pageSize": found["page_size"],
        "nextPage": found["next_page"],
        "previousPage": found["previous_page"],
    }


@router.get("/{name}/{id}", operation_id="derived_get")
async def get_derived(name: str, id: str) -> dict[str, Any]:
    model = read.derived_class(name)
    found = await read.get_fact(model, id)
    if found is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"There is no {name} {id}")
    return dumped(found)
