"""`/api/rdf`: a document or an entity as RDF.

    GET /api/rdf/{Type}/{id}    ?format=ttl|trig|jsonld|nt|nq, or by `Accept`; Turtle if neither says
    GET /api/rdf/ontology       the project's ontology; ?part=shapes|context
    GET /api/rdf                a description of the dataset

Reading needs no login, and shows what `GET /api/NAME/{id}` would show the same reader.
"""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, FastAPI, HTTPException, Query, Request, Response
from fastapi.responses import JSONResponse, RedirectResponse
from pangloss_models import Document, Entity, ModelRegistry

from pangloss_rdf.export import _called, item_quads
from pangloss_rdf.meta import declared_class
from pangloss_rdf.negotiate import format_from_accept
from pangloss_rdf.serialise import FORMATS, Format, serialise
from pangloss_rdf.uris import check_models, class_name

router = APIRouter(prefix="/api/rdf", tags=["rdf"])


def choose_format(request: Request, asked: str | None) -> Format:
    if asked is not None:
        if asked not in FORMATS:
            raise HTTPException(
                422, detail=f"format must be one of {', '.join(FORMATS)}"
            )
        return FORMATS[asked]
    return format_from_accept(request.headers.get("accept", "")) or FORMATS["ttl"]


def respond(text: str, chosen: Format, view: bool) -> Response:
    """`view`: as plain text, which a browser shows in its tab where it would download a type it does not know"""
    media_type = "text/plain; charset=utf-8" if view else chosen.media_type
    return Response(text, media_type=media_type, headers={"Vary": "Accept"})


def model_of(name: str) -> type | None:
    """The Document or Entity with this name in URIs (its own, or the one `RDFMeta` gives it)"""
    for model in dict.fromkeys(declared_class(m) for m in ModelRegistry._models):
        if issubclass(model, (Document, Entity)) and name in (
            class_name(model),
            model.__name__,
        ):
            return model
    return None


def canonical(owner: type, item_id: UUID, request: Request) -> str:
    query = f"?{request.url.query}" if request.url.query else ""
    return f"/api/rdf/{class_name(owner)}/{item_id}{query}"


Format_ = Annotated[str | None, Query(alias="format")]
View = Annotated[bool, Query()]


@router.get("/ontology", operation_id="rdf_ontology")
async def get_ontology(
    request: Request,
    format: Format_ = None,
    part: Annotated[str | None, Query(pattern="^(shapes|context)$")] = None,
    view: View = False,
):
    from pangloss_rdf.ontology import jsonld_context, ontology_quads
    from pangloss_rdf.shacl import shape_quads

    if part == "context":
        return JSONResponse(
            {"@context": jsonld_context()}, media_type="application/ld+json"
        )
    chosen = choose_format(request, format)
    quads = shape_quads() if part == "shapes" else ontology_quads()
    return respond(serialise(quads, chosen.name), chosen, view)


@router.get("", operation_id="rdf_dataset")
async def get_dataset(request: Request, format: Format_ = None, view: View = False):
    from pangloss_rdf.dataset import dataset_quads

    chosen = choose_format(request, format)
    return respond(serialise(dataset_quads(), chosen.name), chosen, view)


@router.get("/{type_name}/{item_id}", operation_id="rdf_item")
async def get_item(
    type_name: str,
    item_id: UUID,
    request: Request,
    format: Format_ = None,
    view: View = False,
):
    model = model_of(type_name)
    chosen = choose_format(request, format)
    found = await item_quads(model, item_id) if model is not None else None
    if found is None:
        # (the class in an address is not permanent: an entity can become another class, and a class can be removed)
        known = await _called(Entity.references([item_id]))  # ty: ignore[unresolved-attribute]
        if known:
            current = model_of_type(known[0].type)
            if current is not None and class_name(current) != type_name:
                return RedirectResponse(
                    canonical(current, item_id, request), status_code=301
                )
        raise HTTPException(404, detail=f"No {type_name} with id {item_id}")
    item, quads = found
    if class_name(item._owner) != type_name:
        # (read at a parent class: the address is that of the class it is)
        return RedirectResponse(
            canonical(item._owner, item_id, request), status_code=301
        )
    response = respond(serialise(quads, chosen.name), chosen, view)
    version = getattr(getattr(item, "meta", None), "version", None)
    if version is not None and issubclass(item._owner, Document):
        response.headers["ETag"] = f'W/"{version}-{chosen.name}"'
    return response


def model_of_type(name: str) -> type | None:
    return ModelRegistry.all_models().get(name)


def configure_app(app: FastAPI, settings) -> None:
    """Names that clash are found as the server starts, not when something is published"""
    from pangloss_rdf.checks import check_markers
    from pangloss_rdf.vocabulary import check_prefixes

    check_models()
    check_markers()
    check_prefixes()
    from pangloss_rdf.resolve import resolver_router

    app.include_router(resolver_router())
