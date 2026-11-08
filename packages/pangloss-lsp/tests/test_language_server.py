"""The server as an editor meets it: a process of its own, spoken to over stdio"""

import json
import queue
import subprocess
import sys
import textwrap
import threading
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

TIMEOUT = 60

GOOD = """\
from pangloss_models import Entity


class Place(Entity):
    pass


class Person(Entity):
    born_in: Place
"""

BROKEN = """\
from pangloss_models import Entity


class Person(Entity):
    anything: dict[str, str]
"""


class Client:
    def __init__(self, root: Path):
        self.process = subprocess.Popen(
            [sys.executable, "-m", "pangloss_lsp.server"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            cwd=root,
        )
        self.messages: queue.Queue[dict] = queue.Queue()
        self.next_id = 0
        threading.Thread(target=self.read, daemon=True).start()

    def read(self) -> None:
        assert self.process.stdout is not None
        while True:
            length = 0
            while (line := self.process.stdout.readline().strip()) != b"":
                if line.lower().startswith(b"content-length:"):
                    length = int(line.split(b":")[1])
            if not length:
                return
            self.messages.put(json.loads(self.process.stdout.read(length)))

    def send(self, message: dict) -> None:
        assert self.process.stdin is not None
        body = json.dumps({"jsonrpc": "2.0", **message}).encode()
        self.process.stdin.write(b"Content-Length: %d\r\n\r\n" % len(body) + body)
        self.process.stdin.flush()

    def notify(self, method: str, params: dict) -> None:
        self.send({"method": method, "params": params})

    def request(self, method: str, params: dict) -> Any:
        self.next_id += 1
        self.send({"id": self.next_id, "method": method, "params": params})
        while True:
            message = self.messages.get(timeout=TIMEOUT)
            if message.get("id") == self.next_id and "method" not in message:
                return message["result"]

    def diagnostics_of(self, uri: str) -> list[dict]:
        while True:
            message = self.messages.get(timeout=TIMEOUT)
            if (
                message.get("method") == "textDocument/publishDiagnostics"
                and message["params"]["uri"] == uri
            ):
                return message["params"]["diagnostics"]


@pytest.fixture
def models(tmp_path: Path) -> Path:
    (tmp_path / "pyproject.toml").write_text(
        '[tool.pangloss]\nsettings = "proj_settings"\n'
    )
    (tmp_path / "proj_settings.py").write_text(
        textwrap.dedent(
            """\
            from pangloss_core import BaseSettings, DatabaseSettings
            from pydantic import AnyHttpUrl


            class Settings(BaseSettings[DatabaseSettings]):
                PROJECT_NAME: str = "Test"
                BACKEND_CORS_ORIGINS: list = []
                INSTALLED_APPS: list[str] = ["proj_app"]
                STORAGE: str = "pangloss_memgraph:storage"
                DATABASE: DatabaseSettings = DatabaseSettings()
                INTERFACE_LANGUAGES: list[str] = []
                AUTHJWT_SECRET_KEY: str = "a secret for the tests, of a decent length"
                ENTITY_BASE_URL: AnyHttpUrl = AnyHttpUrl("http://test.com/")


            Settings()
            """
        )
    )
    (tmp_path / "proj_app").mkdir()
    (tmp_path / "proj_app/__init__.py").write_text("")
    path = tmp_path / "proj_app/models.py"
    path.write_text(GOOD)
    return path


@pytest.fixture
def client(models: Path) -> Iterator[Client]:
    client = Client(models.parent.parent)
    client.request(
        "initialize",
        {
            "processId": None,
            "rootUri": models.parent.parent.as_uri(),
            "capabilities": {},
        },
    )
    client.notify("initialized", {})
    yield client
    client.process.kill()


def opened(client: Client, path: Path) -> None:
    client.notify(
        "textDocument/didOpen",
        {
            "textDocument": {
                "uri": path.as_uri(),
                "languageId": "python",
                "version": 1,
                "text": path.read_text(),
            }
        },
    )


def saved(client: Client, path: Path) -> None:
    client.notify("textDocument/didSave", {"textDocument": {"uri": path.as_uri()}})


def wait_for_stub(models: Path) -> None:
    stub = models.with_suffix(".pyi")
    for _ in range(600):
        if stub.exists():
            return
        threading.Event().wait(0.1)
    raise AssertionError("no stub was written")


def test_a_refused_field_is_shown_on_save_and_cleared_when_it_is_fixed(
    client: Client, models: Path
):
    uri = models.as_uri()
    models.write_text(BROKEN)
    opened(client, models)

    (diagnostic,) = client.diagnostics_of(uri)
    assert diagnostic["severity"] == 1
    assert diagnostic["source"] == "pangloss"
    assert diagnostic["range"] == {
        "start": {"line": 4, "character": 4},
        "end": {"line": 4, "character": 12},
    }
    assert "Person.anything" in diagnostic["message"]

    models.write_text(GOOD)
    saved(client, models)
    assert client.diagnostics_of(uri) == []


def test_stubs_are_kept_fresh_and_a_hover_says_what_a_field_is(
    client: Client, models: Path
):
    opened(client, models)
    wait_for_stub(models)

    for _ in range(100):
        result = client.request(
            "textDocument/hover",
            {
                "textDocument": {"uri": models.as_uri()},
                "position": {"line": 8, "character": 6},
            },
        )
        if result is not None:
            break
        threading.Event().wait(0.1)
    assert result is not None
    assert "Relation to `Place`" in result["contents"]["value"]
    assert "Person.Create" in result["contents"]["value"]


def test_a_hover_elsewhere_says_nothing(client: Client, models: Path):
    opened(client, models)
    wait_for_stub(models)

    assert (
        client.request(
            "textDocument/hover",
            {
                "textDocument": {"uri": models.as_uri()},
                "position": {"line": 0, "character": 3},
            },
        )
        is None
    )


def test_the_server_says_it_wants_to_be_told_of_saves(models: Path):
    client = Client(models.parent.parent)
    capabilities = client.request(
        "initialize", {"processId": None, "rootUri": None, "capabilities": {}}
    )["capabilities"]
    client.process.kill()
    assert capabilities["hoverProvider"]
    assert capabilities["textDocumentSync"]["save"]


WITH_META = """\
from pangloss_models import Entity


class Person(Entity):
    _meta = Entity.Meta(abstract=False)
    name: str
    born_in: Person
"""


def changed(client: Client, path: Path, text: str, version: int = 2) -> None:
    client.notify(
        "textDocument/didChange",
        {
            "textDocument": {"uri": path.as_uri(), "version": version},
            "contentChanges": [{"text": text}],
        },
    )


def completions(client: Client, path: Path, line: int, character: int) -> list[dict]:
    for _ in range(100):
        result = client.request(
            "textDocument/completion",
            {
                "textDocument": {"uri": path.as_uri()},
                "position": {"line": line, "character": character},
            },
        )
        if result is not None:
            return result["items"]
        threading.Event().wait(0.1)
    return []


def test_the_options_of_a_meta_are_completed_in_a_buffer_that_does_not_parse(
    client: Client, models: Path
):
    models.write_text(WITH_META)
    opened(client, models)
    wait_for_stub(models)

    typing = WITH_META.replace("Entity.Meta(abstract=False)", "Entity.Meta(ab")
    changed(client, models, typing)
    items = completions(client, models, 4, len("    _meta = Entity.Meta(ab"))

    labels = [item["label"] for item in items]
    assert "abstract" in labels and "indexes" in labels
    abstract = next(item for item in items if item["label"] == "abstract")
    assert abstract["textEdit"]["newText"] == "abstract="
    assert abstract["textEdit"]["range"] == {
        "start": {"line": 4, "character": len("    _meta = Entity.Meta(")},
        "end": {"line": 4, "character": len("    _meta = Entity.Meta(ab")},
    }


def test_the_fields_of_the_class_are_offered_for_an_index(client: Client, models: Path):
    models.write_text(WITH_META.replace("born_in: Person", "born_in: Person | None"))
    opened(client, models)
    wait_for_stub(models)

    text = WITH_META.replace("Entity.Meta(abstract=False)", "Entity.Meta(indexes=[")
    changed(client, models, text)
    items = completions(client, models, 4, len("    _meta = Entity.Meta(indexes=["))

    # (a value the node holds, and the label: not the relation)
    assert [item["label"] for item in items] == ["name", "label"]
    assert items[0]["textEdit"]["newText"] == '"name"'


def test_a_slot_is_completed_with_its_import(client: Client, models: Path):
    models.write_text(GOOD)
    opened(client, models)
    wait_for_stub(models)

    changed(client, models, GOOD + "    _")
    items = completions(client, models, 9, 5)

    assert "_meta" in [item["label"] for item in items]


def test_hovering_an_option_of_a_meta_documents_it(client: Client, models: Path):
    models.write_text(WITH_META)
    opened(client, models)
    wait_for_stub(models)

    for _ in range(100):
        result = client.request(
            "textDocument/hover",
            {
                "textDocument": {"uri": models.as_uri()},
                "position": {"line": 4, "character": len("    _meta = Entity.Meta(ab")},
            },
        )
        if result is not None:
            break
        threading.Event().wait(0.1)
    assert result is not None
    assert result["contents"]["value"].startswith("`abstract: bool = False`")


OPTIONAL_LIST = """\
from pangloss_models import Entity


class Place(Entity):
    pass


class Person(Entity):
    visited: list[Place] | None
"""


def test_a_refusal_with_an_obvious_correction_offers_it_as_a_quick_fix(
    client: Client, models: Path
):
    models.write_text(OPTIONAL_LIST)
    opened(client, models)
    (diagnostic,) = client.diagnostics_of(models.as_uri())

    actions = client.request(
        "textDocument/codeAction",
        {
            "textDocument": {"uri": models.as_uri()},
            "range": diagnostic["range"],
            "context": {"diagnostics": [diagnostic]},
        },
    )

    (action,) = actions
    assert action["title"] == "Change to `list[Place]`"
    assert action["kind"] == "quickfix"
    (edit,) = action["edit"]["changes"][models.as_uri()]
    assert edit["newText"] == "list[Place]"
    assert edit["range"] == {
        "start": {"line": 8, "character": 13},
        "end": {"line": 8, "character": 31},
    }


def test_a_quick_fix_is_not_offered_once_the_buffer_has_moved_on(
    client: Client, models: Path
):
    models.write_text(OPTIONAL_LIST)
    opened(client, models)
    (diagnostic,) = client.diagnostics_of(models.as_uri())

    changed(client, models, OPTIONAL_LIST.replace("visited:", "visited_places:  "))

    actions = client.request(
        "textDocument/codeAction",
        {
            "textDocument": {"uri": models.as_uri()},
            "range": diagnostic["range"],
            "context": {"diagnostics": [diagnostic]},
        },
    )
    assert actions is None


def test_the_server_advertises_completion_and_quick_fixes(models: Path):
    client = Client(models.parent.parent)
    capabilities = client.request(
        "initialize", {"processId": None, "rootUri": None, "capabilities": {}}
    )["capabilities"]
    client.process.kill()
    assert "(" in capabilities["completionProvider"]["triggerCharacters"]
    assert capabilities["codeActionProvider"]["codeActionKinds"] == ["quickfix"]
