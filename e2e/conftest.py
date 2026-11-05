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
# (a second user, for what someone else does: comments in the review panel)
OTHER_USERNAME, OTHER_PASSWORD = "bob", "bob-password"
# (and a third, who makes the documents the review tests check: no one may check what they made themselves)
AUTHOR_USERNAME, AUTHOR_PASSWORD = "ann", "ann-password"
# (how often the review feed asks the API, on the interface's server: often, so the tests do not wait)
REVIEW_POLL_MS = "300"
# (and the typology tree's feed)
TYPOLOGY_POLL_MS = "300"

MODELS = textwrap.dedent(
    """
    from pangloss_models.model_bases.document import Document
    from pangloss_models.model_bases.entity import Entity
    from pangloss_models.model_bases.reified_relation import ReifiedRelationDocument
    from pangloss_calendar.models import DateCharacterisation
    from pangloss_dates.dateable import Dateable
    from pangloss_dates.models import Date
    from pangloss_library.models import WeightedAlternative
    from pangloss_review.meta import ReviewMeta
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


    class Group(Entity):
        pass


    class Meeting(Document):
        attendees: list[Person | Group]


    # (only ever part of a report: it cannot be made on its own)
    class ReportSection(Document):
        _meta = Document.Meta(create_directly=False)

        body: str


    class Finding[T](ReifiedRelationDocument[T]):
        note: str


    class Report(Document):
        _review_meta = ReviewMeta(reviewable=True)

        text: str
        sections: list[ReportSection]
        findings: list[Finding[ReportSection]]


    # (who it might be, each with how likely: the percentages add up to 100, edited with sliders)
    class Suspicion(Document):
        suspects: WeightedAlternative[Person]


    # (dated: what the calendar shows)
    class Event(Document):
        text: str
        when: Date


    # (dateable: a person's page can show what refers to them by date)
    class Appointment(Document, Dateable):
        appointed: Person


    # (a feast, by rule or attached by hand: what the calendar's days are characterised by)
    class Feast(DateCharacterisation):
        use: str | None = None


    # (a person said to be a member of a group: two such make the derived fact that they are of one group)
    class Membership(Document):
        member: Person
        group: Group
    """
)
# What the project derives (`pangloss_derived`): the members of one group, from two memberships
DERIVED = textwrap.dedent(
    """
    from typing import Annotated

    from pangloss_derived import Derived, RuleType, SymmetricLabel, Var, rule

    from roles.models import Group, Membership, Person

    family = RuleType("family", "Ties of family and of membership")


    class SameGroup(Derived):
        \"\"\"Members of the same group\"\"\"

        _meta = Derived.Meta(symmetric=True)

        first: Annotated[Person, SymmetricLabel("member")]
        second: Annotated[Person, SymmetricLabel("member")]
        group: Group


    @rule(types=[family])
    def same_group(a: Var[Person], b: Var[Person], group: Var[Group]):
        \"\"\"Two people said to be members of one group\"\"\"
        return SameGroup.Derive(first=a, second=b, group=group).when(
            Membership.Where(member=a, group=group),
            Membership.Where(member=b, group=group),
        )
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

    def send(
        self, method: str, path: str, body=None, form=None, headers=None
    ) -> tuple[int, object]:
        data, more, headers = None, headers or {}, {}
        if body is not None:
            data, headers = (
                json.dumps(body).encode(),
                {"Content-Type": "application/json"},
            )
        if form is not None:
            data = urllib.parse.urlencode(form).encode()
            headers = {"Content-Type": "application/x-www-form-urlencoded"}
        request = urllib.request.Request(
            self.base + path, data, {**headers, **more}, method=method
        )
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
        return self.client(USERNAME, PASSWORD)

    def client(self, username: str, password: str) -> Client:
        """A client logged in as that user"""
        client = Client(self.api)
        status, result = client.send(
            "POST",
            "/api/users/session",
            form={"username": username, "password": password},
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
    (root / "roles" / "derived.py").write_text(DERIVED)
    settings = root / "e2e_project" / "settings.py"
    text = settings.read_text()
    text = text.replace(
        '"pangloss_memgraph",',
        '"pangloss_memgraph",\n        "pangloss_interface",\n        "pangloss_typology",\n        "pangloss_dates",\n'
        '        "pangloss_calendar",\n        "pangloss_review",\n        "pangloss_library",\n        "pangloss_history",\n'
        '        "pangloss_derived",',
        1,
    )
    text = text.replace('DB_USERNAME="memgraph"', 'DB_USERNAME="test"')
    text = text.replace('DB_PASSWORD="memgraph"', 'DB_PASSWORD="test"')
    text = text.replace('["en"]', '["en", "de"]')
    # (a user may not check what they made or last changed: the review tests make documents as another user)
    # (the calendar: Julian, three years, and only the events' dates are counted, not the feasts' rules)
    text = text.replace(
        "    INTERFACE_LANGUAGES:",
        "    REVIEW_ALLOW_SELF_REVIEW: bool = False\n"
        '    DATES_DEFAULT_CALENDAR: str = "julian"\n'
        "    CALENDAR_FIRST_YEAR: int = 1499\n"
        "    CALENDAR_LAST_YEAR: int = 1501\n"
        '    CALENDAR_FIELDS: list[str] = ["Event.when"]\n'
        "    INTERFACE_LANGUAGES:",
        1,
    )
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
        connection = http.client.HTTPConnection("127.0.0.1", port, timeout=300)
        headers = {
            k: v
            for k, v in self.headers.items()
            if k.lower() not in ("host", "connection")
        }
        connection.request(self.command, self.path, body or None, headers)
        response = connection.getresponse()
        self.send_response(response.status)
        for name, value in response.getheaders():
            if name.lower() not in (
                "transfer-encoding",
                "connection",
                "content-length",
            ):
                self.send_header(name, value)
        if (
            response.getheader("Content-Length") is not None
            or self.command == "HEAD"
            or response.status in (204, 304)
        ):
            content = response.read()
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)
        else:
            # (a stream, such as a live server function's: passed on as it comes, not when it ends)
            self.send_header("Transfer-Encoding", "chunked")
            self.end_headers()
            try:
                while chunk := response.read1(65536):
                    self.wfile.write(b"%x\r\n%s\r\n" % (len(chunk), chunk))
                    self.wfile.flush()
                self.wfile.write(b"0\r\n\r\n")
            except OSError:
                # (the browser went away, or the stream stopped: the connection is not reused)
                self.close_connection = True
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
    for username, password in (
        (OTHER_USERNAME, OTHER_PASSWORD),
        (AUTHOR_USERNAME, AUTHOR_PASSWORD),
    ):
        run(
            [
                "users",
                "create",
                "--username",
                username,
                "--email",
                f"{username}@example.com",
                "--password",
                password,
                "--no-admin",
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
            {
                "PANGLOSS_API_URL": f"http://127.0.0.1:{api_port}",
                "PANGLOSS_REVIEW_POLL_MS": REVIEW_POLL_MS,
                "PANGLOSS_TYPOLOGY_POLL_MS": TYPOLOGY_POLL_MS,
            },
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
def dev_url(stack: Stack) -> Iterator[str]:
    """The interface from its development server (`pangloss interface dev`), on the same API and database: the
    development build of Solid checks what the production build does not (a write while rendering stops the whole
    app there), so a page that works in `stack` can still be broken here. It passes `/api` on itself."""
    port = free_port()
    process = subprocess.Popen(
        [
            str(BIN / "pangloss"),
            "interface",
            "dev",
            "--port",
            str(port),
            "--api-url",
            stack.api,
        ],
        cwd=stack.project,
        env=environment(
            PANGLOSS_REVIEW_POLL_MS=REVIEW_POLL_MS,
            PANGLOSS_TYPOLOGY_POLL_MS=TYPOLOGY_POLL_MS,
        ),
        stdout=open(stack.project / "dev.log", "w"),  # noqa: SIM115 (closed with the process)
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )
    try:
        # (Vite listens on `localhost`, which can be IPv6 only; a login there is a cookie of that host, not of
        # 127.0.0.1. The first page is compiled when it is asked for: slower than a built one)
        url = f"http://localhost:{port}"
        wait_for(f"{url}/", "the development server", process, 120)
        yield url
    finally:
        stop(process, signal.SIGTERM)
        try:
            process.wait(10)
        except subprocess.TimeoutExpired:
            stop(process, signal.SIGKILL)


@pytest.fixture(scope="session")
def base_url(stack: Stack) -> str:
    return stack.url


def forget(*labels: str) -> None:
    driver = neo4j.GraphDatabase.driver(MEMGRAPH_URI, auth=MEMGRAPH_AUTH)
    try:
        for label in labels:
            driver.execute_query(  # ty: ignore[no-matching-overload]
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


def julian(year: int, month: int | None = None, day: int | None = None) -> dict:
    return {
        "type": "ExactDate",
        "calendar": "julian",
        "year": year,
        "month": month,
        "day": day,
    }


def between(first: dict, last: dict) -> dict:
    return {
        "type": "DateRange",
        "calendar": "julian",
        "not_before": first,
        "not_after": last,
    }


@pytest.fixture
def appointed(types: Stack) -> SimpleNamespace:
    """Ada: a bishop in 1510, a notary not before 1490 (when it ended, nobody knows), an abbot at a date nobody knows;
    and a statement about her, which has no date"""
    forget("Appointment")
    api = types.admin()

    def made(kind: str, label: str, **fields) -> str:
        return api.ok("POST", f"/api/{kind}", {"label": label, **fields})["id"]

    ada = made("Person", "Ada", has_role=[])
    person = {"type": "Person", "id": ada}
    notary = made(
        "Appointment",
        "Notary",
        appointed=person,
        date={
            "type": "DateRange",
            "calendar": "julian",
            "not_before": julian(1490),
            "not_after": {"type": "UnknownDate"},
        },
    )
    made("Appointment", "Bishop", appointed=person, date=julian(1510))
    made("Appointment", "Abbot", appointed=person, date={"type": "UnknownDate"})
    made("Statement", "She was there", text="She was there", about=person)
    return SimpleNamespace(ada=ada, notary=notary)


@pytest.fixture
def grouped(types: Stack) -> SimpleNamespace:
    """Jan, a member of the guild (with Pieter and Margriet) and of the council (with 25 councillors), and appointed a
    notary in 1495; Hendrik, a member of nothing. The rule `same_group` derives that Jan is of one group with 27 people:
    one more than the first page. Waits for the worker to have derived them all."""
    forget("Membership", "Group", "Appointment", "PGDerived", "PGJustification")
    api = types.admin()

    def made(kind: str, label: str, **fields) -> str:
        return api.ok("POST", f"/api/{kind}", {"label": label, **fields})["id"]

    names: dict[str, str] = {}

    def named(kind: str, label: str, **fields) -> str:
        names[(made_id := made(kind, label, **fields))] = label
        return made_id

    def member(person: str, group: str) -> str:
        return made(
            "Membership",
            f"{names[person]} in {names[group]}",
            member={"type": "Person", "id": person},
            group={"type": "Group", "id": group},
        )

    guild, council = named("Group", "The guild"), named("Group", "The council")
    jan, pieter, margriet = (
        named("Person", name, has_role=[]) for name in ("Jan", "Pieter", "Margriet")
    )
    memberships = {
        "jan_guild": member(jan, guild),
        "pieter": member(pieter, guild),
        "margriet": member(margriet, guild),
        "jan_council": member(jan, council),
    }
    for n in range(25):
        member(named("Person", f"Councillor {n + 1:02}", has_role=[]), council)
    made(
        "Appointment",
        "Notary",
        appointed={"type": "Person", "id": jan},
        date=julian(1495),
    )
    deadline = time.monotonic() + 60
    while api.ok("GET", f"/api/derived/SameGroup?entity={jan}")["count"] < 27:
        assert time.monotonic() < deadline, "the worker did not derive the facts"
        time.sleep(0.3)
    return SimpleNamespace(
        api=api,
        jan=jan,
        pieter=pieter,
        margriet=margriet,
        guild=guild,
        council=council,
        hendrik=made("Person", "Hendrik", has_role=[]),
        memberships=memberships,
    )


@pytest.fixture
def dated(types: Stack) -> SimpleNamespace:
    """Events in March 1500 (Julian): a coronation on the 2nd, a siege from the 3rd to the 10th (a period: a bar in the
    month), a fair on the 4th or the 5th (one day, known only within two: a hollow bar between them), a birth sometime
    in 1500 (listed under the month); a feast by rule (Benedict, 21 March) and one with no rule (Market), to attach by
    hand"""
    forget("Event", "Feast")
    api = types.admin()

    def made(kind: str, label: str, **fields) -> str:
        return api.ok("POST", f"/api/{kind}", {"label": label, **fields})["id"]

    rule = {
        "type": "Recurrence",
        "calendar": "julian",
        "frequency": "yearly",
        "weekdays": [],
        "excluded_days": [],
        "month": 3,
        "month_day": 21,
        "start": julian(1450),
        "end": julian(1530, 12, 31),
    }
    return SimpleNamespace(
        api=api,
        coronation=made("Event", "Coronation", text="Crowned", when=julian(1500, 3, 2)),
        # (one day, known only to the year: listed under a month, not drawn)
        birth=made("Event", "Birth of Alcuin", text="Born", when=julian(1500)),
        siege=made(
            "Event",
            "Siege of the town",
            text="Besieged",
            when={
                "type": "Period",
                "calendar": "julian",
                "start": julian(1500, 3, 3),
                "end": julian(1500, 3, 10),
            },
        ),
        fair=made(
            "Event",
            "The fair",
            text="Traded",
            when=between(julian(1500, 3, 4), julian(1500, 3, 5)),
        ),
        benedict=made("Feast", "Benedict", use="sarum", when=rule),
        market=made("Feast", "Market day", when={"type": "NoRule"}),
    )
