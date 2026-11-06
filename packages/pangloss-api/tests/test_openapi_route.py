"""The OpenAPI document is made off the event loop: the server answers other requests meanwhile"""

import asyncio
import threading
import time

import httpx2 as httpx
from conftest import PASSWORD  # noqa: F401
from fastapi.testclient import TestClient
from pangloss_api import create_app
from test_model_routes import make_models


def test_the_document_is_as_fastapi_makes_it(settings):
    make_models()
    app = create_app()
    client = TestClient(app)
    document = client.get("/openapi.json").json()
    assert "/api/Person" in document["paths"]
    assert document == app.openapi()
    # (and the pages that load it are still there: /docs is RapiDoc, not Swagger UI)
    docs = client.get("/docs")
    assert docs.status_code == 200
    assert '<rapi-doc spec-url="/openapi.json"' in docs.text
    assert "swagger" not in docs.text.lower()
    assert client.get("/redoc").status_code == 200
    # (neither is in the document)
    assert "/docs" not in document["paths"]


def test_making_it_does_not_stop_other_requests(settings):
    make_models()
    app = create_app()
    real = app.openapi
    made_in: list[threading.Thread] = []

    def slow():
        if app.openapi_schema is not None:
            return app.openapi_schema  # (kept, as FastAPI keeps it)
        # (as a large project's is: seconds of work that is not waiting)
        made_in.append(threading.current_thread())
        time.sleep(0.4)
        return real()

    app.openapi = slow

    async def main():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://test"
        ) as client:
            finished: list[str] = []

            async def ask(name, path):
                response = await client.get(path)
                finished.append(name)
                return response

            first, second, other = await asyncio.gather(
                ask("document", "/openapi.json"),
                ask("document again", "/openapi.json"),
                ask("other", "/api/users/me"),
            )
            return finished, first, second, other

    finished, first, second, other = asyncio.run(main())
    # the other request was answered while the document was being made
    assert finished[0] == "other" and other.status_code == 401
    # ... which was done once, for both who asked, and not on the server's own thread
    assert len(made_in) == 1 and made_in[0] is not threading.main_thread()
    assert first.status_code == second.status_code == 200
    assert first.json() == second.json() and "/api/Person" in first.json()["paths"]
