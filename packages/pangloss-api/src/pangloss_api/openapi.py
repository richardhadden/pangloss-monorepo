"""The OpenAPI document, made without stopping the server.

FastAPI makes the document the first time `/openapi.json` is asked for (or `/docs`, which loads it), in the
coroutine of the request: with 96 classes that is five seconds in which the server answers nothing else. Here it is
made in a thread, once, for whoever asks first; anyone else who asks meanwhile waits for that one, and every other
request goes on being answered. After that it is kept, as FastAPI keeps it.

`/docs` is RapiDoc rather than FastAPI's Swagger UI, which is too slow to use with the routes of a large project
(the smoketest app). RapiDoc's script is in this package and served by it.
"""

import asyncio
import html
from pathlib import Path

from fastapi import FastAPI
from starlette.requests import Request
from starlette.responses import FileResponse, HTMLResponse, Response
from starlette.routing import Route


def make_openapi_in_a_thread(app: FastAPI) -> None:
    """Put FastAPI's own route for the document behind one that has it made off the event loop"""
    if not app.openapi_url:
        return
    found = next(
        (
            (index, route)
            for index, route in enumerate(app.router.routes)
            if isinstance(route, Route) and route.path == app.openapi_url
        ),
        None,
    )
    if found is None:
        return
    index, route = found
    answer = route.endpoint
    making = asyncio.Lock()

    async def openapi(request: Request) -> Response:
        if app.openapi_schema is None:
            async with making:
                if app.openapi_schema is None:
                    await asyncio.to_thread(app.openapi)
        return await answer(request)

    app.router.routes[index] = Route(app.openapi_url, openapi, include_in_schema=False)


# RapiDoc is served from this package (`static/rapidoc/`, MIT: the LICENSE is beside it), not loaded from a CDN: a
# script from another site would run on the API's origin, with whatever the page holds. The version is in the URL,
# so a browser that has kept the old one asks for the new one when the package changes it
RAPIDOC_VERSION = "12.0.0"
RAPIDOC_FILE = Path(__file__).parent / "static" / "rapidoc" / "rapidoc-min.js"


def add_rapidoc(app: FastAPI, path: str = "/docs") -> None:
    """The interactive documentation of the API, at `path` (and its script at `path/rapidoc-min.js`)"""
    if not app.openapi_url:
        return
    script = f"{path}/rapidoc-min.js"
    # (no `persist-auth`: a token typed into the page is not kept in the browser's storage)
    page = f"""<!doctype html>
<html>
<head>
<meta charset="utf-8">
<title>{html.escape(app.title)} - API</title>
<script type="module" src="{script}?v={RAPIDOC_VERSION}"></script>
</head>
<body>
<rapi-doc spec-url="{html.escape(app.openapi_url)}" render-style="focused" schema-style="table"
  schema-expand-level="1" show-method-in-nav-bar="as-plain-text" allow-spec-url-load="false"
  allow-spec-file-load="false"></rapi-doc>
</body>
</html>
"""

    async def docs(request: Request) -> Response:
        return HTMLResponse(page)

    async def rapidoc(request: Request) -> Response:
        return FileResponse(
            RAPIDOC_FILE,
            media_type="text/javascript",
            headers={"Cache-Control": "public, max-age=31536000, immutable"},
        )

    app.router.routes.append(Route(path, docs, include_in_schema=False))
    app.router.routes.append(Route(script, rapidoc, include_in_schema=False))
