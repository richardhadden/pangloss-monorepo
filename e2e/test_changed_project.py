"""A second, small project, for what the project of the other tests cannot show because it is built once and stays as
it is: versions recorded **before the models were changed** (shown as they would be now, and one that cannot be
restored as it is), a calendar with **no span** set, and a login whose **access cookie runs out** while a page is open
(one minute here).

It is on the test Neo4j (:7693, as `pangloss_testing` has it; wiped), since the test Memgraph has the other project's
data and migrations: these tests are skipped where there is no Neo4j. The models are changed with the commands a
person runs (`makemigrations`, `migrate`), after there is data and its history."""

import re
import signal
import subprocess
import textwrap
import time
from collections.abc import Iterator
from pathlib import Path
from types import SimpleNamespace

import neo4j
import pytest
from conftest import (
    BIN,
    OTHER_PASSWORD,
    OTHER_USERNAME,
    PASSWORD,
    REVIEW_POLL_MS,
    USERNAME,
    Client,
    environment,
    free_port,
    run,
    stop,
    wait_for,
)
from helpers import hydrated
from playwright.sync_api import Page, expect

# (its project is on the one test Neo4j: one worker runs all of it, `--dist=loadgroup`)
pytestmark = pytest.mark.xdist_group("changed-project")

NEO4J_URI, NEO4J_AUTH = "bolt://localhost:7693", ("neo4j", "test-password")

IMPORTS = """
from pangloss_models import Document, Entity
from pangloss_review import ReviewMeta


class Person(Entity):
    pass

"""
# As first written: a note with a remark, and a shelf mark that is any text
FIRST = IMPORTS + textwrap.dedent(
    """
    class Note(Document):
        _review_meta = ReviewMeta(reviewable=True)

        text: str
        remark: str | None = None
        shelf: str
        about: Person
    """
)
# Then the remark is taken away...
SECOND = FIRST.replace("    remark: str | None = None\n", "")
# ...a note has to say how many pages it has (those there are given 12)...
THIRD = SECOND.replace("    text: str\n", "    text: str\n    pages: int\n")
# ...and a shelf mark is a number (every note's is one by then: "42"; its first version's was "by the door")
# (not the same length as before: Python takes a file of the same size, written in the same second, for the one it
# has compiled already, and the change would not be seen)
FOURTH = THIRD.replace("    shelf: str\n", "    shelf: int  # (a number)\n")
assert len({len(FIRST), len(SECOND), len(THIRD), len(FOURTH)}) == 4


def wipe() -> None:
    driver = neo4j.GraphDatabase.driver(NEO4J_URI, auth=NEO4J_AUTH)
    try:
        driver.execute_query("MATCH (n) DETACH DELETE n")
    finally:
        driver.close()


def serve(root: Path, name: str, command: list[str], **env: str) -> subprocess.Popen:
    return subprocess.Popen(
        [str(BIN / "pangloss"), *command],
        cwd=root,
        env=environment(**env),
        stdout=open(root / f"{name}.log", "a"),  # noqa: SIM115 (closed with the process)
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )


def halt(*processes: subprocess.Popen) -> None:
    for process in processes:
        stop(process, signal.SIGTERM)
    for process in processes:
        try:
            process.wait(10)
        except subprocess.TimeoutExpired:
            stop(process, signal.SIGKILL)


def logged_in_client(api: str, username: str, password: str) -> Client:
    client = Client(api)
    status, result = client.send("POST", "/api/users/session", form={"username": username, "password": password})
    assert status == 200, result
    return client


def wait_for_versions(client: Client, note: str, count: int) -> None:
    """(they are recorded just after the write: there is no history at all until the first is)"""
    deadline = time.monotonic() + 10
    while True:
        status, listing = client.send("GET", f"/api/Note/{note}/history")
        if status == 200 and isinstance(listing, dict) and len(listing["versions"]) >= count:
            return
        assert time.monotonic() < deadline, (status, listing)
        time.sleep(0.1)


@pytest.fixture(scope="module")
def changed(tmp_path_factory) -> Iterator[SimpleNamespace]:
    try:
        wipe()
    except (neo4j.exceptions.DriverError, neo4j.exceptions.Neo4jError, OSError) as error:
        pytest.skip(f"the test Neo4j is not on :7693 ({error})")
    root = tmp_path_factory.mktemp("changed")
    run(["new-project", "changed_project"], root)
    run(["new-app", "notes"], root)
    models = root / "notes" / "models.py"
    models.write_text(FIRST)
    settings = root / "changed_project" / "settings.py"
    text = settings.read_text()
    for old, new in (
        ("from pangloss_memgraph import MemgraphDatabaseSettings", "from pangloss_neo4j import Neo4jDatabaseSettings"),
        ("MemgraphDatabaseSettings", "Neo4jDatabaseSettings"),
        (
            '"pangloss_memgraph",',
            '"pangloss_neo4j",\n        "pangloss_interface",\n        "pangloss_dates",\n        "pangloss_calendar",\n'
            '        "pangloss_review",\n        "pangloss_history",',
        ),
        ("pangloss_memgraph:storage", "pangloss_neo4j:storage"),
        ("bolt://localhost:7687", NEO4J_URI),
        ('DB_USERNAME="memgraph"', f'DB_USERNAME="{NEO4J_AUTH[0]}"'),
        ('DB_PASSWORD="memgraph"', f'DB_PASSWORD="{NEO4J_AUTH[1]}"'),
        ('DATABASE_NAME="memgraph"', 'DATABASE_NAME="neo4j"'),
        # (the access cookie lasts a minute; no span for the calendar)
        ("    INTERFACE_LANGUAGES:", "    AUTH_ACCESS_TOKEN_EXPIRE_MINUTES: int = 1\n    INTERFACE_LANGUAGES:"),
    ):
        assert old in text, old
        text = text.replace(old, new)
    settings.write_text(text)

    run(["makemigrations"], root)
    run(["migrate"], root)
    for username, password, admin in ((USERNAME, PASSWORD, "--admin"), (OTHER_USERNAME, OTHER_PASSWORD, "--no-admin")):
        run(
            ["users", "create", "--username", username, "--email", f"{username}@example.com", "--password", password, admin],
            root,
        )  # fmt: skip

    # (the data, and its history, with the models as first written)
    api_port, port = free_port(), free_port()
    api_url = f"http://127.0.0.1:{api_port}"
    api = serve(root, "api", ["run", "--port", str(api_port)])
    try:
        wait_for(f"{api_url}/api/Person", "the API", api)
        client = logged_in_client(api_url, USERNAME, PASSWORD)
        person = client.ok("POST", "/api/Person", {"label": "Ada"})["id"]
        note = client.ok(
            "POST",
            "/api/Note",
            {"label": "A note", "text": "As first written", "remark": "Check this", "shelf": "by the door",
             "about": {"type": "Person", "id": person}},
        )["id"]
        edit = client.ok("GET", f"/api/Note/{note}/edit")
        status, result = client.send(
            "PUT", f"/api/Note/{note}", {**edit, "text": "As changed", "shelf": "42"}, headers={"If-Match": "*"}
        )
        assert status < 300, result
        wait_for_versions(client, note, 2)
    finally:
        halt(api)

    # (the models are changed, three times, each with its migration; what `makemigrations` asks is answered)
    for changed_models, answer in ((SECOND, ""), (THIRD, "12\n"), (FOURTH, "")):
        models.write_text(changed_models)
        asked = subprocess.run(
            [str(BIN / "pangloss"), "makemigrations"],
            cwd=root, env=environment(), input=answer, capture_output=True, text=True, check=False, timeout=600,
        )  # fmt: skip
        assert asked.returncode == 0 and "Wrote " in asked.stdout, asked.stdout + asked.stderr
        run(["migrate", "--yes", "--no-backup"], root)
    run(["interface", "build"], root)

    api = serve(root, "api", ["run", "--port", str(api_port)])
    interface = serve(
        root,
        "interface",
        ["interface", "serve", "--port", str(port), "--api-url", api_url],
        PANGLOSS_REVIEW_POLL_MS=REVIEW_POLL_MS,
    )
    try:
        wait_for(f"{api_url}/api/Person", "the API", api)
        wait_for(f"http://127.0.0.1:{port}/", "the interface", interface)
        # (and the note is changed once more, with the models as they are now: its third version)
        client = logged_in_client(api_url, USERNAME, PASSWORD)
        edit = client.ok("GET", f"/api/Note/{note}/edit")
        status, result = client.send(
            "PUT", f"/api/Note/{note}", {**edit, "text": "After the changes"}, headers={"If-Match": "*"}
        )
        assert status < 300, result
        wait_for_versions(client, note, 3)
        yield SimpleNamespace(
            url=f"http://127.0.0.1:{port}", api=api_url, root=root, note=note, person=person,
            client=lambda username=USERNAME, password=PASSWORD: logged_in_client(api_url, username, password),
        )  # fmt: skip
    finally:
        halt(api, interface)
        wipe()


@pytest.fixture
def signed_in(page: Page, changed) -> Page:
    response = page.request.post(
        f"{changed.url}/api/users/session", form={"username": USERNAME, "password": PASSWORD}
    )
    assert response.ok, response.text()
    return page


def test_the_years_page_of_a_calendar_with_no_span_says_to_set_one(page: Page, changed):
    page.goto(f"{changed.url}/calendar")
    hydrated(page)
    main = page.locator("main")
    expect(main.get_by_role("heading", level=1)).to_contain_text("Years")
    expect(main).to_contain_text(
        "Set CALENDAR_FIRST_YEAR and CALENDAR_LAST_YEAR in the settings of the project to list its years."
    )
    expect(main.get_by_role("link")).to_have_count(0)


def open_version(page: Page, changed, version: int):
    page.goto(f"{changed.url}/Note/{changed.note}")
    hydrated(page)
    page.get_by_role("button", name="History", exact=True).click()
    page.locator(f'[data-testid="history-version"][data-version="{version}"]').click()
    drawer = page.get_by_test_id("history-drawer")
    expect(drawer).to_have_attribute("data-open", "true")
    return drawer


def test_a_version_with_a_value_that_no_longer_fits_cannot_be_restored_as_it_is(signed_in: Page, changed):
    """The first version's shelf mark is "by the door", and a shelf mark is a number now"""
    drawer = open_version(signed_in, changed, 1)
    expect(drawer).to_contain_text("This version can't be restored as it is.")
    expect(drawer).to_contain_text("Some things have changed since it was saved:")
    problems = drawer.get_by_test_id("history-problems").get_by_role("listitem")
    # (each in plain words, naming the field as the form names it; the API's own message is the tooltip)
    expect(problems.filter(has_text="Shelf").first).to_have_text(
        "“Shelf” now holds a different kind of value, and the old one doesn't fit it."
    )
    expect(problems.filter(has_text="Shelf").first).to_have_attribute("title", re.compile("'by the door' cannot be converted"))
    expect(problems.filter(has_text="remark")).to_contain_text("no longer part of this record")
    expect(problems.filter(has_text="remark")).to_have_attribute(
        "title", "Note.remark no longer exists (the value is in history)"
    )
    # (it is shown as it would look today: with the pages the migration gave every note, and without the remark)
    expect(drawer).to_contain_text("As first written")
    expect(drawer.locator("dt", has_text="Pages")).to_be_visible()
    expect(drawer).not_to_contain_text("Check this")
    expect(drawer.get_by_test_id("history-restore")).to_be_disabled()
    # (and the API refuses it too)
    status, _ = changed.client().send(
        "POST", f"/api/Note/{changed.note}/history/1/restore", {}, headers={"If-Match": "*"}
    )
    assert status == 409


def test_a_version_from_before_the_models_changed_is_shown_as_it_would_be_now_and_restored(signed_in: Page, changed):
    """The second version's shelf mark is "42", which is a number: it lacks only the pages, which the migration gave,
    and has a remark, which no note has now"""
    page = signed_in
    drawer = open_version(page, changed, 2)
    expect(drawer).to_contain_text(
        "This version was saved before some fields were changed. It's shown as it would look today."
    )
    expect(drawer).not_to_contain_text("can't be restored")
    expect(drawer.get_by_test_id("history-problems").get_by_role("listitem")).to_have_count(1)
    expect(drawer).to_contain_text("As changed")
    restore = drawer.get_by_test_id("history-restore")
    expect(restore).to_be_enabled()
    restore.click()
    dialog = page.get_by_role("dialog")
    expect(dialog).to_contain_text("Restore version 2?")
    dialog.get_by_role("button", name="Restore", exact=True).click()
    expect(page.get_by_role("status", name="Notifications")).to_contain_text("Restored version 2 as version 4")
    now = changed.client().ok("GET", f"/api/Note/{changed.note}")
    assert (now["text"], now["pages"], now["shelf"]) == ("As changed", 12, 42), now
    assert "remark" not in now


def test_what_someone_else_does_still_reaches_the_page_after_the_access_cookie_has_run_out(signed_in: Page, changed):
    """The feed of the review panel is asked for with the cookies of the page; when the access cookie runs out (a
    minute here) the API refuses the feed's server, and the feed ends with that. The page asks for a new cookie and
    opens the feed again (`createFeedReader`). Until 2026-11-10 it did not: the review button failed, and nothing more
    came"""
    page = signed_in
    bob = changed.client(OTHER_USERNAME, OTHER_PASSWORD)
    page.goto(f"{changed.url}/Note/{changed.note}")
    hydrated(page)
    page.get_by_role("banner", name="Console").get_by_role("button", name="Review: ", exact=False).click()
    panel = page.get_by_role("complementary", name="Review")
    expect(panel).to_have_attribute("data-open", "true")
    comments = panel.get_by_test_id("review-comment")

    bob.ok("POST", f"/api/review/{changed.note}/comments", {"text": "Before it runs out"})
    expect(comments.filter(has_text="Before it runs out")).to_be_visible(timeout=10_000)

    navigations = []
    page.on("framenavigated", lambda frame: navigations.append(frame.url))
    # (nothing is said in the console of the browser: a feed that ends with the cookie is not a failure of the page)
    said = []
    page.on("console", lambda message: said.append(message.text) if message.type == "error" else None)
    # (the cookie of the page is a minute old and more)
    page.wait_for_timeout(70_000)
    bob = changed.client(OTHER_USERNAME, OTHER_PASSWORD)
    bob.ok("POST", f"/api/review/{changed.note}/comments", {"text": "After it has run out"})
    expect(comments.filter(has_text="After it has run out")).to_be_visible(timeout=30_000)
    assert [text for text in said if "console action" in text] == [], said
    # (without a reload, and still logged in: the page can write)
    assert navigations == []
    panel.get_by_role("combobox", name="Comment").fill("Still here")
    panel.get_by_role("button", name="Send").click()
    expect(comments.filter(has_text="Still here")).to_be_visible(timeout=10_000)
