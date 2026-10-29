"""End-to-end tests: a real project (API, database, built interface) driven in a browser by Playwright.

Run with `uv run pytest e2e` (they are not in `packages/`, so `./run_tests.sh` does not run them). Needs the
test Memgraph on :7687 (wiped), Node, and a browser: `uv run playwright install chromium`.

The project is made new for the session, in a temporary directory, with the commands a user would run
(`pangloss new-project`, `makemigrations`, `migrate`, `interface build`, ...). A small proxy puts the API at `/api`
beside the interface, as whatever is in front of a deployed interface does.
"""

import http.client
import http.cookiejar
import json
import os
import signal
import socket
import subprocess
import sys
import textwrap
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Iterator
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace

import neo4j
import pytest

BIN = Path(sys.executable).parent
MEMGRAPH_URI = "bolt://localhost:7687"
MEMGRAPH_AUTH = ("test", "test")
USERNAME, PASSWORD = "e2e", "e2e-password"

MODELS = textwrap.dedent(
    """
    from pangloss_models.model_bases.document import Document
    from pangloss_models.model_bases.entity import Entity
    from pangloss_typology import Typed, Typology, TypologyMeta


    class Role(Entity):
        has_type: list[Typed[RoleTypology]]


    class RoleTypology(Typology):
        _typology_meta = TypologyMeta(name="RoleType", also=Role)


    class Person(Entity):
        has_role: list[Role]


    class Statement(Document):
        text: str
        about: Person
    """
)
TYPES = (
    '[{"label": "Clerk", "children": [{"label": "Secretary"}]}, {"label": "Advisor"}]'
)


class Client:
    """The API as a user with a session (cookies), for what a test sets up or checks"""

    def __init__(self, base: str):
        self.base = base
        self.opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar())
        )

    def send(self, method: str, path: str, body=None, form=None) -> tuple[int, object]:
        data, headers = None, {}
        if body is not None:
            data, headers = (
                json.dumps(body).encode(),
                {"Content-Type": "application/json"},
            )
        if form is not None:
            data = urllib.parse.urlencode(form).encode()
            headers = {"Content-Type": "application/x-www-form-urlencoded"}
        request = urllib.request.Request(self.base + path, data, headers, method=method)
        try:
            with self.opener.open(request) as response:
                text = response.read()
                return response.status, (json.loads(text) if text else None)
        except urllib.error.HTTPError as error:
            text = error.read()
            return error.code, (json.loads(text) if text else None)

    def ok(self, method: str, path: str, body=None):
        status, result = self.send(method, path, body)
        assert status < 300, (method, path, status, result)
        return result


@dataclass
class Stack:
    url: str
    """What the browser opens: the interface, with the API at `/api`"""
    api: str
    project: Path

    def run(self, *args: str) -> str:
        return run(args, self.project)

    def tree(self) -> list[dict]:
        """The hierarchy of `RoleType` as the API gives it"""
        with urllib.request.urlopen(
            f"{self.api}/api/typology/RoleType/tree"
        ) as response:
            return json.load(response)

    def admin(self) -> Client:
        """A client logged in as the user of the project"""
        client = Client(self.api)
        status, result = client.send(
            "POST",
            "/api/users/session",
            form={"username": USERNAME, "password": PASSWORD},
        )
        assert status == 200, result
        return client

    def type_id(self, label: str) -> str:
        def walk(nodes):
            for node in nodes:
                if node["label"] == label:
                    return node["id"]
                if found := walk(node["children"]):
                    return found

        found = walk(self.tree())
        assert found, label
        return found


def environment(**more: str) -> dict[str, str]:
    env = {k: v for k, v in os.environ.items() if k != "VIRTUAL_ENV"}
    env["PATH"] = f"{BIN}{os.pathsep}{env['PATH']}"
    env["_ZO_DOCTOR"] = "0"
    return {**env, **more}


def run(args, cwd: Path, **env: str) -> str:
    done = subprocess.run(
        [str(BIN / "pangloss"), *args],
        cwd=cwd,
        env=environment(**env),
        capture_output=True,
        text=True,
        check=False,
        timeout=600,
    )
    if done.returncode != 0:
        raise RuntimeError(
            f"pangloss {' '.join(args)} failed:\n{done.stdout}\n{done.stderr}"
        )
    return done.stdout


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def wipe_database() -> None:
    driver = neo4j.GraphDatabase.driver(MEMGRAPH_URI, auth=MEMGRAPH_AUTH)
    try:
        driver.execute_query("MATCH (n) DETACH DELETE n", database_="memgraph")
    finally:
        driver.close()


def make_project(root: Path) -> Path:
    run(["new-project", "e2e_project"], root)
    run(["new-app", "roles"], root)
    (root / "roles" / "models.py").write_text(MODELS)
    settings = root / "e2e_project" / "settings.py"
    text = settings.read_text()
    text = text.replace(
        '"pangloss_memgraph",',
        '"pangloss_memgraph",\n        "pangloss_interface",\n        "pangloss_typology",',
        1,
    )
    text = text.replace('DB_USERNAME="memgraph"', 'DB_USERNAME="test"')
    text = text.replace('DB_PASSWORD="memgraph"', 'DB_PASSWORD="test"')
    text = text.replace('["en"]', '["en", "de"]')
    settings.write_text(text)
    (root / "types.json").write_text(TYPES)
    return root


def wait_for(
    url: str, what: str, process: subprocess.Popen, seconds: float = 60
) -> None:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(
                f"{what} stopped: {process.stdout.read() if process.stdout else ''}"
            )
        try:
            with urllib.request.urlopen(url, timeout=2):
                return
        except urllib.error.HTTPError:
            return  # (it answers)
        except OSError:
            time.sleep(0.3)
    raise RuntimeError(f"{what} did not start at {url}")


def stop(process: subprocess.Popen, sent: int) -> None:
    """Signal the process and what it started"""
    try:
        os.killpg(process.pid, sent)
    except ProcessLookupError:
        pass


class Proxy(BaseHTTPRequestHandler):
    """`/api` to the API, the rest to the interface"""

    api_port = 0
    ui_port = 0
    protocol_version = "HTTP/1.1"

    def handle_any(self) -> None:
        port = self.api_port if self.path.startswith("/api") else self.ui_port
        body = self.rfile.read(int(self.headers.get("Content-Length") or 0))
        connection = http.client.HTTPConnection("127.0.0.1", port, timeout=60)
        headers = {
            k: v
            for k, v in self.headers.items()
            if k.lower() not in ("host", "connection")
        }
        connection.request(self.command, self.path, body or None, headers)
        response = connection.getresponse()
        content = response.read()
        self.send_response(response.status)
        for name, value in response.getheaders():
            if name.lower() not in (
                "transfer-encoding",
                "connection",
                "content-length",
            ):
                self.send_header(name, value)
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)
        connection.close()

    do_GET = do_POST = do_PUT = do_PATCH = do_DELETE = do_HEAD = handle_any

    def log_message(self, *args) -> None:
        pass


@pytest.fixture(scope="session")
def stack(tmp_path_factory) -> Iterator[Stack]:
    try:
        wipe_database()
    except (
        neo4j.exceptions.DriverError,
        neo4j.exceptions.Neo4jError,
        OSError,
    ) as error:
        pytest.skip(f"the test Memgraph is not on :7687 ({error})")
    root = make_project(tmp_path_factory.mktemp("project"))
    run(["makemigrations"], root)
    run(["migrate"], root)
    run(
        [
            "users",
            "create",
            "--username",
            USERNAME,
            "--email",
            "e2e@example.com",
            "--password",
            PASSWORD,
            "--admin",
        ],
        root,
    )
    run(["typology", "load", "RoleType", "types.json", "--user", USERNAME], root)
    run(["interface", "build"], root)

    api_port, ui_port, port = free_port(), free_port(), free_port()
    commands = {
        "api": ([str(BIN / "pangloss"), "run", "--port", str(api_port)], {}),
        "interface": (
            [str(BIN / "pangloss"), "interface", "serve", "--port", str(ui_port)],
            {"PANGLOSS_API_URL": f"http://127.0.0.1:{api_port}"},
        ),
    }
    processes = [
        subprocess.Popen(
            command,
            cwd=root,
            env=environment(**more),
            stdout=open(root / f"{name}.log", "w"),  # noqa: SIM115 (closed with the process; not a pipe, which would fill)
            stderr=subprocess.STDOUT,
            start_new_session=True,  # (its own group, so that the `node` under `pangloss interface serve` stops too)
        )
        for name, (command, more) in commands.items()
    ]
    Proxy.api_port, Proxy.ui_port = api_port, ui_port
    server = ThreadingHTTPServer(("127.0.0.1", port), Proxy)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        wait_for(
            f"http://127.0.0.1:{api_port}/api/typology/RoleType/tree",
            "the API",
            processes[0],
        )
        wait_for(f"http://127.0.0.1:{ui_port}/", "the interface", processes[1])
        yield Stack(f"http://127.0.0.1:{port}", f"http://127.0.0.1:{api_port}", root)
    finally:
        server.shutdown()
        for process in processes:
            stop(process, signal.SIGTERM)
        for process in processes:
            try:
                process.wait(10)
            except subprocess.TimeoutExpired:
                stop(process, signal.SIGKILL)
        wipe_database()


@pytest.fixture(scope="session")
def base_url(stack: Stack) -> str:
    return stack.url


def forget(*labels: str) -> None:
    driver = neo4j.GraphDatabase.driver(MEMGRAPH_URI, auth=MEMGRAPH_AUTH)
    try:
        for label in labels:
            driver.execute_query(
                f"MATCH (n:{label}) DETACH DELETE n", database_="memgraph"
            )
    finally:
        driver.close()


@pytest.fixture
def types(stack: Stack) -> Stack:
    """The `RoleType` hierarchy as loaded (Clerk > Secretary, Advisor), and nothing else, whatever an earlier test did"""
    forget("Statement", "Person", "Role", "RoleType")
    stack.run("typology", "load", "RoleType", "types.json", "--user", USERNAME)
    return stack


@pytest.fixture
def data(types: Stack) -> SimpleNamespace:
    """The types, and some people and roles: Maximilian (his secretary: a Role of the type Secretary), Marie (her advisor)
    and Charles (no role)"""
    api = types.admin()

    def made(kind: str, label: str, **fields) -> str:
        return api.ok("POST", f"/api/{kind}", {"label": label, **fields})["id"]

    def typed(label: str, type_label: str) -> str:
        return made(
            "Role",
            label,
            has_type=[{"type": "RoleType", "id": types.type_id(type_label)}],
        )

    secretary = typed("Maximilian's secretary", "Secretary")
    advisor = typed("Marie's advisor", "Advisor")
    marie = made(
        "Person", "Marie of Burgundy", has_role=[{"type": "Role", "id": advisor}]
    )
    statement = made(
        "Statement",
        "Court at Ghent",
        text="Marie held court at Ghent",
        about={"type": "Person", "id": marie},
    )
    ids = SimpleNamespace(
        statement=statement,
        api=api,
        type_id=types.type_id,
        tree=types.tree,
        secretary_role=secretary,
        advisor_role=advisor,
        maximilian=made(
            "Person", "Maximilian", has_role=[{"type": "Role", "id": secretary}]
        ),
        marie=marie,
        charles=made("Person", "Charles the Bold", has_role=[]),
    )
    return ids


@pytest.fixture
def logged_in(page, types: Stack):
    """A page whose browser has a session (the API's `POST /session` sets the cookies; the login dialog is not used,
    because it is the test of the login, not of what needs one)"""
    response = page.request.post(
        "/api/users/session", form={"username": USERNAME, "password": PASSWORD}
    )
    assert response.ok, response.text()
    return page
