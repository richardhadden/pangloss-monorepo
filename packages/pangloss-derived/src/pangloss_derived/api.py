"""`/api/derived`: derived facts, and the worker that keeps them up to date (a background task of the server).

    GET /api/derived                                  the derived classes, the rules and the types of rule
    GET /api/derived/status                           what is pending, the state of each rule, what the worker did
    GET /api/derived/graph/{type}?plain=true          the edges of the rules of a type (`format=graphml`: as GraphML)
    GET /api/derived/about/{Type}/{id}                what the rules derive about an entity or a head document: for
                                                      each class, a count and a first page (what its view has as
                                                      `_derived`, for a reader that asks for it apart)
    GET /api/derived/{Class}?entity=…&page=2          a page of the edges of a class (of an entity, at any field or
                                                      only `at=giver` (several: `at=first,second`); or `evidence=` a
                                                      document; and `plain`, `status`, `context_label`, `rule_type`, and a value
                                                      for an end or a qualifier)
    GET /api/derived/{Class}/{id}                     one, with the justifications the reader sees ("why")
    GET /api/derived/document/{Type}/{id}             why a document exists: the rule, what it rests on, whether it was
                                                      made a document of someone's own, and whether its derivation holds
    GET /api/derived/convert/{Type}/{id}/{To}         the form of the class it can be made into, filled in (login)
    POST /api/derived/convert                         make it that class, in place (login)

What a reader sees is as for documents: a fact is seen if one of its justifications rests only on documents the reader
may see. The view of an entity (`GET /api/Person/{id}`) and of a head document has `_derived`, a first page of each class
(unless read with `?extras=false`; `/api/derived/about/{Type}/{id}` gives the same apart).

The worker runs in the server unless the setting `DERIVED_WORKER_IN_SERVER` is false (for a deployment that runs
`pangloss derive worker` on its own). Only one worker works at a time, whichever process it is in.
"""

import dataclasses
from typing import Annotated, Any

from uuid import UUID

from fastapi import APIRouter, Depends, FastAPI, HTTPException, Query, Request, status
from fastapi.responses import JSONResponse, Response
from pangloss_api import (
    BackgroundTask,
    checks_own_parameters,
    get_current_user,
    refuse_unknown_parameters,
)

from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel, ValidationError

from pangloss_derived import read
from pangloss_derived.check import ends_of
from pangloss_derived.registry import DerivedRegistry, PanglossDerivedError
from pangloss_derived.views import Summed
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
                    "role": f.role,
                }
                for f in model._fields.values()
            },
            "symmetric": bool(model._meta.symmetric),
            "symmetricLabel": read.symmetric_label_of(model),
            "ends": list(ends_of(model)),
            "reverseName": model._reverse_name,
            "qualifiers": [f.name for f in model.qualifiers()],
            "perJustification": [f.name for f in model.per_justification()],
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
    # (the rules that derive documents: of a document class, not of a class of edges)
    rules.update(
        {
            name: {
                "class": rule.model.__name__,
                "description": rule.rule.description,
                "types": rule.type_names,
                "datalog": rule.describe(),
                "document": True,
            }
            for name, rule in DerivedRegistry.documents.items()
        }
    )
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
        # (derived documents: those waiting to be written or looked at again, and those waiting to be deleted; how
        # many each rule has)
        "documents": {
            "pending": found["documents"],
            "retractions": found["retractions"],
            "written": found["written"],
        },
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
            "documents": dataclasses.asdict(stats.documents),
            "secondsDocuments": round(stats.seconds_documents, 3),
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
    format: Annotated[
        str,
        Query(
            pattern="^(json|graphml)$",
            description="`json`, or `graphml` (a file for Gephi, Cytoscape or networkx)",
        ),
    ] = "json",
) -> Any:
    edges = await read.graph(type_name, plain_only=plain)
    if format == "graphml":
        from pangloss_derived.export import graphml

        return Response(
            graphml(edges, type_name),
            media_type="application/graphml+xml",
            headers={
                "Content-Disposition": f'attachment; filename="{type_name}.graphml"'
            },
        )
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
    at: Annotated[
        str | None,
        Query(
            description="With `entity`: only the edges it is at one of these fields of (names, with commas)"
        ),
    ] = None,
    plain: Annotated[bool | None, Query()] = None,
    status_: Annotated[
        Summed | None,
        Query(
            alias="status",
            description="What its justifications say, summed up: asserted, contested, reported, prescribed, "
            "denied or nothing",
        ),
    ] = None,
    context_label: Annotated[str | None, Query()] = None,
    rule_type: Annotated[
        str | None, Query(description="Derived by a rule of this type")
    ] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=read.MAX_PAGE_SIZE)] = read.FIRST_PAGE,
) -> dict[str, Any]:
    """A page of the facts of the class. A field of the class can be given as a parameter (`?family=<id>`)"""
    model = read.derived_class(name)
    filterable = set(model.Where.model_fields) - {
        "plain",
        "status",
        "context_label",
        "rule_type",
    }
    refuse_unknown_parameters(request, also=filterable)
    fields = {
        key: value for key, value in request.query_params.items() if key in filterable
    }
    if at is not None and entity is None:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "`at` needs `entity`: the fields it is at",
        )
    places = [f for f in at.split(",") if f] if at else None
    for place in places or []:
        field = model._fields.get(place)
        if field is None or field.kind != "relation":
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT,
                f"at: {name} has no relation field {place!r}",
            )
    try:
        where = model.Where(
            plain=plain,
            status=status_,
            context_label=context_label,
            rule_type=rule_type,
            **fields,
        )
    except ValueError as error:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(error)) from None
    found = await read.list_facts(
        model,
        where,
        entity,
        page,
        page_size,
        evidence,
        at=places,
    )
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


class ConvertRequest(BaseModel):
    model: str
    id: UUID
    to: str
    version: int
    data: dict[str, Any]


@router.get(
    "/convert/{type_name}/{id}/{to}",
    operation_id="derived_convert_form",
    dependencies=[Depends(get_current_user)],
)
async def convert_form(type_name: str, id: UUID, to: str) -> dict[str, Any]:
    """The form of the class a derived document can be made into, filled in with what the two share"""
    from pangloss_derived import convert

    try:
        return await convert.prefill(type_name, id, to)
    except PanglossDerivedError as error:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(error)) from error


@router.post(
    "/convert",
    operation_id="derived_convert",
    dependencies=[Depends(get_current_user)],
)
async def convert_document(body: ConvertRequest) -> dict[str, Any]:
    """Make a derived document a document of one's own, in place (same id and history); its justification is adopted"""
    from pangloss_derived import convert

    try:
        return await convert.convert(
            body.model, body.id, body.to, body.data, body.version
        )
    except PanglossDerivedError as error:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(error)) from error
    except ValidationError as error:
        # (what the form gave is not a document of the class: said at its fields, as for any save)
        raise RequestValidationError(
            [{**e, "loc": ("body", "data", *e["loc"])} for e in error.errors()],
            body=body.data,
        ) from error


@router.post(
    "/document/{type_name}/{id}/clear-context",
    operation_id="derived_clear_context",
    dependencies=[Depends(get_current_user)],
)
async def clear_context(type_name: str, id: UUID) -> dict[str, Any]:
    """Of a document made from a derived one: take off what its derivation passed through (its author says that it
    no longer rests on the derivation). Gives why it is there, as it is now"""
    from pangloss_derived import convert, why

    try:
        cleared = await convert.clear_context(type_name, id)
    except PanglossDerivedError as error:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(error)) from error
    found = await why.of_document(type_name, id) if cleared else None
    if found is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, detail="Not a document made from a derived one"
        )
    return found


@router.get("/document/{type_name}/{id}", operation_id="derived_document")
async def about_document(type_name: str, id: UUID) -> dict[str, Any]:
    """Why a document is there: the rule that made it, the documents it rests on, what its derivation passed through,
    and (for one a person made their own) that, and whether the derivation still holds"""
    from pangloss_derived import why

    found = await why.of_document(type_name, id)
    if found is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Not a derived document")
    return found
