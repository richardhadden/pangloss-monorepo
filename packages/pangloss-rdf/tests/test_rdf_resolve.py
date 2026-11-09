"""What a URI answers: where to go, by who is asking. No database: these are only redirects"""

import sys
from types import SimpleNamespace
from uuid import UUID

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pangloss_models import Entity, initialise
from pangloss_rdf import RDFMeta
from pangloss_rdf.negotiate import format_from_accept, prefers_html
from pangloss_rdf.resolve import resolver_router

ID = UUID("0190a000-0000-7000-8000-000000000001")
BROWSER = "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"


@pytest.mark.parametrize(
    ("header", "expected"),
    [
        (BROWSER, True),
        ("*/*", False),
        ("", False),
        ("text/turtle", False),
        ("text/turtle, text/html;q=0.5", False),
        ("text/html, text/turtle;q=0.5", True),
    ],
)
def test_a_browser_is_one_that_names_html_first(header, expected):
    assert prefers_html(header) is expected


def test_the_weights_are_read():
    assert format_from_accept("text/turtle;q=0.2, application/trig").name == "trig"
    assert format_from_accept("text/turtle;q=0") is None
    assert format_from_accept("text/html") is None


def client(monkeypatch, base="https://site.org/id/", **values):
    settings = SimpleNamespace(ENTITY_BASE_URL=base, **values)
    for module in ("pangloss_rdf.uris", "pangloss_rdf.resolve"):
        monkeypatch.setattr(sys.modules[module], "get_settings", lambda: settings)
    app = FastAPI()
    app.include_router(resolver_router())

    @app.get("/api/{a}/{b}")
    async def other(a: str, b: str):
        return "the api"

    return TestClient(app, follow_redirects=False)


def answer(http, path, accept):
    response = http.get(path, headers={"Accept": accept})
    return response.status_code, response.headers.get("location")


def test_a_client_of_data_goes_to_the_data(monkeypatch):
    http = client(monkeypatch)
    assert answer(http, f"/id/Person/{ID}", "text/turtle") == (
        303,
        f"/api/rdf/Person/{ID}",
    )
    assert answer(http, f"/id/Person/{ID}", "*/*")[1] == f"/api/rdf/Person/{ID}"
    assert http.get(f"/id/Person/{ID}").headers["vary"] == "Accept"


def test_a_browser_goes_to_the_page(monkeypatch):
    http = client(monkeypatch, RDF_HTML_URL="https://site.org/")
    assert answer(http, f"/id/Person/{ID}", BROWSER) == (
        303,
        f"https://site.org/Person/{ID}",
    )


def test_a_browser_with_no_pages_sees_the_data_as_text(monkeypatch):
    http = client(monkeypatch)
    assert answer(http, f"/id/Person/{ID}", BROWSER)[1] == (
        f"/api/rdf/Person/{ID}?view=true"
    )


def test_a_renamed_class_has_its_page_at_its_own_name(monkeypatch):
    class Person(Entity):
        _rdf_meta = RDFMeta(class_name="Human")

    initialise()
    http = client(monkeypatch, RDF_HTML_URL="https://site.org")
    assert answer(http, f"/id/Human/{ID}", BROWSER)[1] == (
        f"https://site.org/Person/{ID}"
    )
    assert Person


@pytest.mark.parametrize("part", ["edge/Act.by/0", "Person.born", "Person.names/2"])
def test_a_node_with_no_document_goes_to_the_item_it_is_in(monkeypatch, part):
    http = client(monkeypatch)
    assert answer(http, f"/id/Person/{ID}/{part}", "text/turtle")[1] == (
        f"/api/rdf/Person/{ID}"
    )


@pytest.mark.parametrize(
    "path", ["/id/ontology", "/id/ontology/Person", "/id/ontology/core"]
)
def test_the_ontologys_addresses_go_to_it(monkeypatch, path):
    http = client(monkeypatch)
    assert answer(http, path, "text/turtle") == (303, "/api/rdf/ontology")


def test_the_dataset(monkeypatch):
    http = client(monkeypatch)
    assert answer(http, "/id/dataset", "text/turtle") == (303, "/api/rdf")


def test_at_the_root_of_a_site_nothing_else_is_caught(monkeypatch):
    http = client(monkeypatch, base="https://site.org/")
    assert http.get(f"/api/{ID}").status_code == 404
    assert http.get("/api/Person").status_code == 404
    assert http.get(f"/api/Person/{ID}", follow_redirects=False).status_code == 200
    assert answer(http, f"/Person/{ID}", "text/turtle")[0] == 303


def test_an_ontology_elsewhere_is_not_ours_to_answer(monkeypatch):
    http = client(monkeypatch, RDF_ONTOLOGY_URL="https://other.org/ns/")
    assert http.get("/id/ontology").status_code == 404
