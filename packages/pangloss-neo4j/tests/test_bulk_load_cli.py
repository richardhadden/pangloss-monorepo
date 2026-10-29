"""`pangloss neo4j bulk-load`, end to end: a project made in a temporary directory, the real
`pangloss` command, and the Neo4j that `test_bulk_load.py` has (port 7694, started if it is not
there)."""

import json
import os
import subprocess
import sys
import textwrap
from pathlib import Path

import neo4j
import pytest

from .helpers import BULK_URI

pytestmark = pytest.mark.usefixtures("bulk_neo4j")


SETTINGS = """
    from pangloss_core.settings import BaseSettings
    from pangloss_neo4j.databases.neo4j.settings import Neo4jDatabaseSettings
    from pydantic import AnyHttpUrl


    class Settings(BaseSettings[Neo4jDatabaseSettings]):
        PROJECT_NAME: str = "bulkproj"
        BACKEND_CORS_ORIGINS: list = []
        INSTALLED_APPS: list[str] = ["pangloss_neo4j", "bulkapp"]
        DATABASE_MODULE: str = "pangloss_neo4j.databases.neo4j"
        DATABASE: Neo4jDatabaseSettings = Neo4jDatabaseSettings(
            DB_URL="bolt://localhost:7694",
            DB_USERNAME="neo4j",
            DB_PASSWORD="test-password",
            DATABASE_NAME="neo4j",
        )
        INTERFACE_LANGUAGES: list[str] = ["en"]
        ENTITY_BASE_URL: AnyHttpUrl = AnyHttpUrl("http://localhost:8000/entity/")
        AUTHJWT_SECRET_KEY: str = "a secret for the tests, of a decent length"


    Settings()
"""

MODELS = """
    from pangloss_models.model_bases.document import Document
    from pangloss_models.model_bases.entity import Entity


    class Person(Entity):
        _meta = Entity.Meta(create_with_id=True)


    class Note(Document):
        text: str
        by: Person
"""


def write(root: Path, name: str, content: str) -> None:
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(content))


def pangloss(project: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [str(Path(sys.executable).parent / "pangloss"), *args],
        cwd=project,
        capture_output=True,
        text=True,
        check=False,
        env={**os.environ, "_ZO_DOCTOR": "0"},
        timeout=300,
    )


def person_url(i: int) -> str:
    return f"https://example.org/bulk/person/{i}"


def records(people: int = 300, notes: int = 200) -> list[dict]:
    return [
        *[
            {
                "type": "Person",
                "id": person_url(i),
                "create_new": True,
                "label": f"Person {i}",
            }
            for i in range(people)
        ],
        *[
            {
                "type": "Note",
                "label": f"Note {i}",
                "text": f"A note, number {i}",
                "by": {"type": "Person", "id": person_url(i % people)},
            }
            for i in range(notes)
        ],
    ]


def jsonl(path: Path, rows: list[dict]) -> Path:
    path.write_text("\n".join(json.dumps(row) for row in rows) + "\n")
    return path


@pytest.fixture(scope="module")
def project(bulk_neo4j, tmp_path_factory) -> Path:
    root = tmp_path_factory.mktemp("bulkproj")
    write(
        root,
        "pyproject.toml",
        """
        [project]
        name = "bulkproj"
        version = "0.1.0"
        requires-python = ">=3.15"
        dependencies = []

        [tool.pangloss]
        settings = "bulkproj.settings"
        """,
    )
    write(root, "bulkproj/__init__.py", "")
    write(root, "bulkproj/settings.py", SETTINGS)
    write(root, "bulkapp/__init__.py", "")
    write(root, "bulkapp/models.py", MODELS)

    # a database of its own: nothing in it
    driver = neo4j.GraphDatabase.driver(BULK_URI, auth=("neo4j", "test-password"))
    with driver.session(database="neo4j") as session:
        session.run("MATCH (n) DETACH DELETE n").consume()
    driver.close()

    for command in (
        ("makemigrations",),
        ("migrate",),
        (
            "users",
            "create",
            "--username",
            "loader",
            "--email",
            "loader@example.org",
            "--password",
            "a-long-enough-password",
            "--no-admin",
        ),
    ):
        done = pangloss(root, *command)
        assert done.returncode == 0, (command, done.stdout, done.stderr)
    return root


@pytest.fixture
def empty(project):
    """The database without data (the user, the migrations and the constraints stay)"""
    query(
        "MATCH (n) WHERE NOT n:PGUser AND NOT n:PGMigration DETACH DELETE n",
    )
    assert state()["locks"] == 0
    yield


def query(statement: str) -> list[dict]:
    driver = neo4j.GraphDatabase.driver(BULK_URI, auth=("neo4j", "test-password"))
    try:
        with driver.session(database="neo4j") as session:
            return session.run(statement).data()
    finally:
        driver.close()


def state() -> dict:
    return {
        "constraints": len(query("SHOW CONSTRAINTS")),
        "locks": query("MATCH (l:PGMigrationLock) RETURN count(l) AS c")[0]["c"],
        "people": query("MATCH (n:Person) RETURN count(n) AS c")[0]["c"],
        "notes": query("MATCH (n:Note) RETURN count(n) AS c")[0]["c"],
    }


def test_a_file_is_loaded_and_the_database_is_normal_after(project, empty, tmp_path):
    constraints = state()["constraints"]
    assert constraints >= 10
    path = jsonl(tmp_path / "data.jsonl", records())

    done = pangloss(project, "neo4j", "bulk-load", str(path), "--user", "loader")

    assert done.returncode == 0, done.stdout + done.stderr
    assert "500 records: 300 Person, 200 Note" in done.stdout
    assert "Wrote 500 records" in done.stdout
    assert state() == {
        "constraints": constraints,
        "locks": 0,
        "people": 300,
        "notes": 200,
    }
    # ... and it is all as the models write it: they can read it
    read = pangloss(project, "check-data")
    assert read.returncode == 0, read.stdout + read.stderr
    assert "All 500 can be read" in read.stdout


def test_a_database_with_data_is_refused(project, empty, tmp_path):
    path = jsonl(tmp_path / "data.jsonl", records(5, 3))
    assert (
        pangloss(
            project, "neo4j", "bulk-load", str(path), "--user", "loader"
        ).returncode
        == 0
    )

    again = pangloss(project, "neo4j", "bulk-load", str(path), "--user", "loader")

    assert again.returncode == 1
    assert "only for an empty database" in again.stderr
    assert state()["people"] == 5 and state()["locks"] == 0


def test_an_invalid_record_is_found_before_the_database_is_touched(
    project, empty, tmp_path
):
    rows = records(5, 3)
    del rows[6]["text"]  # (a note with no text: line 7)
    path = jsonl(tmp_path / "bad.jsonl", rows)

    done = pangloss(project, "neo4j", "bulk-load", str(path), "--user", "loader")

    assert done.returncode == 1
    assert "line 7" in done.stderr and "text" in done.stderr
    assert state()["people"] == 0

    # `--validate-only` says the same, and says so for a good file without writing it
    assert (
        pangloss(
            project,
            "neo4j",
            "bulk-load",
            str(path),
            "--user",
            "loader",
            "--validate-only",
        ).returncode
        == 1
    )
    good = jsonl(tmp_path / "good.jsonl", records(5, 3))
    done = pangloss(
        project,
        "neo4j",
        "bulk-load",
        str(good),
        "--user",
        "loader",
        "--validate-only",
    )
    assert done.returncode == 0 and "nothing was written" in done.stdout
    assert state()["people"] == 0


def test_a_user_that_does_not_exist_is_refused(project, empty, tmp_path):
    path = jsonl(tmp_path / "data.jsonl", records(5, 3))

    done = pangloss(project, "neo4j", "bulk-load", str(path), "--user", "nobody")

    assert done.returncode == 1
    assert "no user called 'nobody'" in done.stderr
    assert state()["people"] == 0 and state()["constraints"] >= 10


def test_a_record_that_cannot_be_written_stops_the_load_and_all_is_put_back(
    project, empty, tmp_path
):
    # the same id twice: the second is refused (one writer, so in order), at its line
    rows = records(5, 3)
    rows.insert(3, dict(rows[1]))
    path = jsonl(tmp_path / "dup.jsonl", rows)

    done = pangloss(
        project,
        "neo4j",
        "bulk-load",
        str(path),
        "--user",
        "loader",
        "--concurrency",
        "1",
    )

    assert done.returncode == 1
    assert "line 4" in done.stderr
    assert "back to normal" in done.stderr
    after = state()
    assert after["locks"] == 0
    assert after["constraints"] >= 10
    assert after["people"] == 3  # (what came before it stays: nothing is rolled back)


def test_recover_does_nothing_when_there_is_nothing_to_recover(project, empty):
    done = pangloss(project, "neo4j", "bulk-recover")

    assert done.returncode == 1
    assert "no bulk load to recover" in done.stderr
