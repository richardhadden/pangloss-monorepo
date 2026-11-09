"""What a URI leads to: `{ENTITY_BASE_URL}/{Class}/{id}` is an identifier, and answers with where to find out about it.

A browser is sent to the item's page (`RDF_HTML_URL`), anyone else to its RDF, by a `303`: the thing is not the document
about it. A node with no document of its own (an edge, an embedded object) is sent to the item it is in. What is under the
ontology's address goes to the ontology.

The requests have to reach the API: where the interface's server is in front, `pangloss interface serve --api-path /entity`.
"""

from urllib.parse import quote, urlsplit
from uuid import UUID

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import RedirectResponse
from pangloss_core.settings import get_settings

from pangloss_rdf.meta import declared_class
from pangloss_rdf.negotiate import prefers_html
from pangloss_rdf.uris import base_url, ontology_url

SEE_OTHER = 303


def _see(location: str) -> RedirectResponse:
    response = RedirectResponse(location, status_code=SEE_OTHER)
    response.headers["Vary"] = "Accept"
    return response


def html_url() -> str | None:
    url = getattr(get_settings(), "RDF_HTML_URL", None)
    return str(url).rstrip("/") if url else None


def _python_name(type_name: str) -> str:
    """The interface's pages are at the class's own name, which `RDFMeta(class_name=...)` does not change"""
    from pangloss_rdf.api import model_of

    model = model_of(type_name)
    return declared_class(model).__name__ if model is not None else type_name


def base_path() -> str:
    return urlsplit(base_url()).path.rstrip("/")


def _resolve_item(type_name: str, item_id: UUID, request: Request) -> RedirectResponse:
    data = f"/api/rdf/{quote(type_name, safe='')}/{item_id}"
    if prefers_html(request.headers.get("accept", "")):
        pages = html_url()
        if pages is not None:
            return _see(f"{pages}/{quote(_python_name(type_name), safe='')}/{item_id}")
        return _see(f"{data}?view=true")
    return _see(data)


def _to(data: str, request: Request) -> RedirectResponse:
    browser = prefers_html(request.headers.get("accept", ""))
    return _see(f"{data}?view=true" if browser else data)


def resolver_router() -> APIRouter:
    """Made when the app is, as the paths are from the settings"""
    router = APIRouter(include_in_schema=False)
    path = base_path()

    @router.get(f"{path}/dataset")
    async def dataset(request: Request):
        return _to("/api/rdf", request)

    if ontology_url().startswith(f"{base_url()}/"):
        ontology_path = urlsplit(ontology_url()).path.rstrip("/#")

        @router.get(ontology_path)
        @router.get(f"{ontology_path}/{{term:path}}")
        async def ontology(request: Request, term: str = ""):
            return _to("/api/rdf/ontology", request)

    # (`:uuid` in the path: at the root of a site `/{a}/{b}` must not catch `/api/Person`)
    @router.get(f"{path}/{{type_name}}/{{item_id:uuid}}")
    @router.get(f"{path}/{{type_name}}/{{item_id:uuid}}/{{part:path}}")
    async def item(type_name: str, item_id: UUID, request: Request, part: str = ""):
        if type_name == "api":
            # (at the root of a site: `/api/{id}` is nothing, and is not a class called api)
            raise HTTPException(404)
        return _resolve_item(type_name, item_id, request)

    return router
