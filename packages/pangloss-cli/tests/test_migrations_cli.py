import sys
import textwrap
from pathlib import Path

import pytest
from pangloss_cli.main import build_app
from pangloss_models.model_registry import ModelRegistry
from typer.testing import CliRunner

from cli_support import write

runner = CliRunner()

FAKE_MIGRATION_BACKEND = """
    APPLIED = {}
    CALLS = []
    BATCHES = []

    async def ensure_ready():
        CALLS.append("ensure_ready")

    async def applied():
        return dict(APPLIED)

    async def lock(who=None):
        CALLS.append("lock")

    async def unlock():
        CALLS.append("unlock")

    async def dry_run(migrations, state):
        from pangloss_models.migrations.reports import ChangeReport, MigrationReport

        CALLS.append("dry_run")
        reports = []
        for migration in migrations:
            changes = []
            failing = False
            for change in migration.changes:
                if getattr(change, "name", None) == "boom":
                    failing = True
                    changes.append(ChangeReport(change, "error", message="it would fail"))
                else:
                    changes.append(ChangeReport(change, "counted", {"properties_set": 3}))
            reports.append(MigrationReport(migration.app, migration.name, changes))
        return reports

    async def apply(migrations, state, fake=False, progress=None, batch_size=None):
        for migration in migrations:
            if progress:
                progress(migration, "faked" if fake else "applying")
            CALLS.append(("apply", migration.name, fake))
            BATCHES.append(batch_size)
            APPLIED[migration.key] = {
                "status": "applied", "checksum": migration.checksum, "fake": fake,
            }
        return state
"""

V1 = """
    from pangloss_models.model_bases.entity import Entity

    class Person(Entity):
        name: str
"""

V2 = """
    from pangloss_models.model_bases.entity import Entity

    class Person(Entity):
        name: str
        born: int
"""


@pytest.fixture(autouse=True)
def clean_registry():
    ModelRegistry._reset()
    yield
    ModelRegistry._reset()


@pytest.fixture(autouse=True)
def data_is_readable(monkeypatch):
    """(the fake database has no data to read: `migrate` reads it with the models after applying)"""
    import pangloss_cli.migrations as module

    async def nothing_to_read(types=None, limit=None):
        from pangloss_models.migrations.check import DataCheck

        return DataCheck()

    monkeypatch.setattr(module, "check_data", nothing_to_read)


@pytest.fixture
def models_project(project: Path):
    write(project, "fakedb/migration_backend.py", FAKE_MIGRATION_BACKEND)
    write(project, "fakeapp/models.py", V1)
    return project


def set_models(project: Path, source: str) -> None:
    """Change the models of the app, as editing models.py between two commands does"""
    write(project, "fakeapp/models.py", source)
    ModelRegistry._reset()
    for name in list(sys.modules):
        if name.startswith("fakeapp.models"):
            del sys.modules[name]


def invoke(*args: str, input: str | None = None):
    app = build_app(argv=[], environment={})
    result = runner.invoke(app, list(args), input=input)
    return result.exit_code, result.output + result.stderr


def migration_files(project: Path) -> list[str]:
    folder = project / "fakeapp" / "migrations"
    return sorted(p.name for p in folder.glob("0*.py")) if folder.exists() else []


def backend():
    return sys.modules["fakedb.migration_backend"]


# ---------------------------------------------------------------------------
# makemigrations
# ---------------------------------------------------------------------------


def test_the_first_migration_makes_the_models(models_project: Path):
    exit_code, output = invoke("makemigrations")
    assert exit_code == 0, output
    assert "fakeapp.0001_initial" in output
    assert "Create the Entity Person" in output
    assert migration_files(models_project) == ["0001_initial.py"]
    assert (models_project / "fakeapp/migrations/__init__.py").exists()

    # nothing has changed since
    exit_code, output = invoke("makemigrations")
    assert exit_code == 0
    assert "No changes" in output
    assert migration_files(models_project) == ["0001_initial.py"]


def test_a_dry_run_and_a_check_write_nothing(models_project: Path):
    exit_code, output = invoke("makemigrations", "--dry-run")
    assert exit_code == 0
    assert "nothing was written" in output
    assert migration_files(models_project) == []

    exit_code, output = invoke("makemigrations", "--check")
    assert exit_code == 1
    assert "changes since the last migration" in output
    assert migration_files(models_project) == []


def test_a_required_field_asks_for_a_value(models_project: Path):
    assert invoke("makemigrations")[0] == 0
    set_models(models_project, V2)

    exit_code, output = invoke("makemigrations", "--noinput")
    assert exit_code == 1  # (it would have to ask)
    assert "value for" in output and "born" in output
    assert migration_files(models_project) == ["0001_initial.py"]

    exit_code, output = invoke("makemigrations", input="nonsense\n1900\n")
    assert exit_code == 0, output
    assert "is not a valid int" in output
    files = migration_files(models_project)
    assert len(files) == 2 and files[1].startswith("0002_")
    text = (models_project / "fakeapp/migrations" / files[1]).read_text()
    assert "'default': 1900" in text


def test_a_rename_is_asked_and_the_answer_is_used(models_project: Path):
    set_models(models_project, V1.replace("name: str", "name: str\n        born: int"))
    assert invoke("makemigrations")[0] == 0
    renamed = V1.replace("name: str", "name: str\n        birth_year: int")
    set_models(models_project, renamed)

    exit_code, output = invoke("makemigrations", input="y\n")
    assert exit_code == 0, output
    assert "was the field 'born' renamed to 'birth_year'" in output.replace("Was", "was")
    assert "Rename the field Person.born to birth_year" in output
    assert "Remove" not in output

    # (not a rename: a removal, and an addition that needs a value)
    set_models(models_project, V1.replace("name: str", "name: str\n        born: int"))
    # the migrations say birth_year now; the models say born: to and fro
    exit_code, output = invoke("makemigrations", input="n\n7\n")
    assert exit_code == 0, output
    assert "LOSES DATA" in output


def test_models_that_the_migrations_already_come_to_need_nothing(models_project: Path):
    assert invoke("makemigrations")[0] == 0
    set_models(models_project, V1)
    assert "No changes" in invoke("makemigrations")[1]


# ---------------------------------------------------------------------------
# migrate, showmigrations
# ---------------------------------------------------------------------------


def test_migrate_applies_what_is_pending_once(models_project: Path):
    assert invoke("makemigrations")[0] == 0
    set_models(models_project, V2)
    assert invoke("makemigrations", input="1900\n")[0] == 0

    exit_code, output = invoke("migrate", "--plan")
    assert exit_code == 0
    assert "0001_initial" in output and "0002_" in output
    assert backend().APPLIED == {}

    exit_code, output = invoke("migrate")
    assert exit_code == 0, output
    applied = [call for call in backend().CALLS if isinstance(call, tuple)]
    assert [name[:4] for _, name, _ in applied] == ["0001", "0002"]
    assert backend().CALLS.count("lock") == 1 and backend().CALLS.count("unlock") == 1
    assert "Done" in output

    # again: nothing to do
    exit_code, output = invoke("migrate")
    assert exit_code == 0
    assert "Nothing to apply" in output
    assert len([c for c in backend().CALLS if isinstance(c, tuple)]) == 2


def test_migrate_can_record_without_running(models_project: Path):
    assert invoke("makemigrations")[0] == 0
    exit_code, output = invoke("migrate", "--fake")
    assert exit_code == 0, output
    assert ("apply", "0001_initial", True) in backend().CALLS
    assert backend().APPLIED[("fakeapp", "0001_initial")]["fake"] is True


def test_migrate_check_says_whether_there_is_something_to_do(models_project: Path):
    assert invoke("makemigrations")[0] == 0
    assert invoke("migrate", "--check")[0] == 1
    assert invoke("migrate")[0] == 0
    assert invoke("migrate", "--check")[0] == 0


def test_data_that_would_be_lost_is_asked_about(models_project: Path):
    set_models(models_project, V2.replace("born: int", "born: int\n        extra: str | None"))
    assert invoke("makemigrations", "--noinput")[0] in (0, 1)
    # a migration that removes a field
    set_models(models_project, V1)
    assert invoke("makemigrations", "--noinput")[0] == 0
    files = migration_files(models_project)
    assert invoke("migrate", "--plan")[0] == 0

    exit_code, output = invoke("migrate", input="n\n")
    assert exit_code != 0
    assert backend().APPLIED == {}

    exit_code, output = invoke("migrate", "--yes")
    assert exit_code == 0, output
    assert len(backend().APPLIED) == len(files)


def test_an_edited_migration_is_refused(models_project: Path):
    assert invoke("makemigrations")[0] == 0
    assert invoke("migrate")[0] == 0
    path = models_project / "fakeapp/migrations/0001_initial.py"
    path.write_text(path.read_text().replace("'Person'", "'Persons'", 1))

    exit_code, output = invoke("migrate")
    assert exit_code == 1
    assert "has been changed since" in output


def test_showmigrations(models_project: Path):
    assert invoke("makemigrations")[0] == 0
    exit_code, output = invoke("showmigrations")
    assert exit_code == 0
    assert "[ ] 0001_initial" in output
    assert invoke("migrate")[0] == 0
    assert "[X] 0001_initial" in invoke("showmigrations")[1]


def test_unlock(models_project: Path):
    exit_code, output = invoke("migrate", "--unlock")
    assert exit_code == 0
    assert "unlock" in backend().CALLS


# ---------------------------------------------------------------------------
# dry runs, and reading the data
# ---------------------------------------------------------------------------


def test_a_dry_run_says_what_would_happen_and_applies_nothing(models_project: Path):
    assert invoke("makemigrations")[0] == 0
    exit_code, output = invoke("migrate", "--dry-run")
    assert exit_code == 0, output
    assert "Tried, and rolled back" in output
    assert "3 properties set" in output
    assert "Nothing was changed" in output
    assert backend().APPLIED == {}
    assert "lock" not in backend().CALLS  # (it changes nothing, so it needs no lock)


def test_a_dry_run_that_would_fail_says_so(models_project: Path):
    assert invoke("makemigrations")[0] == 0
    set_models(models_project, V1.replace("name: str", "name: str\n        boom: str | None"))
    assert invoke("makemigrations")[0] == 0
    exit_code, output = invoke("migrate", "--dry-run")
    assert exit_code == 1
    assert "it would fail" in output
    assert backend().APPLIED == {}


class Checked:
    def __init__(self, problems=()):
        from pangloss_models.migrations.check import DataCheck, DataProblem

        self.result = DataCheck(
            checked=5, problems=[DataProblem("Person", "1", "Ann", ["born: Field required"]) for _ in problems]
        )

    async def __call__(self, types=None, limit=None):
        self.asked = (types, limit)
        return self.result


def test_migrate_reads_the_data_that_a_migration_could_have_made_unreadable(
    models_project: Path, monkeypatch
):
    import pangloss_cli.migrations as module

    # adding a model changes nothing that exists: there is nothing to read
    assert invoke("makemigrations")[0] == 0
    checked = Checked()
    monkeypatch.setattr(module, "check_data", checked)
    exit_code, output = invoke("migrate")
    assert exit_code == 0, output
    assert "Nothing that exists is affected" in output
    assert not hasattr(checked, "asked")

    # a required field does: and only the model that has it is read
    set_models(models_project, V2)
    assert invoke("makemigrations", input="1900\n")[0] == 0
    exit_code, output = invoke("migrate")
    assert exit_code == 0, output
    assert checked.asked == (["Person"], None)
    assert "All 5 can be read" in output


def test_migrate_can_read_everything_or_nothing(models_project: Path, monkeypatch):
    import pangloss_cli.migrations as module

    assert invoke("makemigrations")[0] == 0
    set_models(models_project, V2)
    assert invoke("makemigrations", input="1900\n")[0] == 0
    checked = Checked()
    monkeypatch.setattr(module, "check_data", checked)
    assert invoke("migrate", "--no-check")[0] == 0
    assert not hasattr(checked, "asked")

    set_models(models_project, V2.replace("born: int", "born: int\n        extra: int"))
    assert invoke("makemigrations", input="2\n")[0] == 0
    assert invoke("migrate", "--check-all")[0] == 0
    assert checked.asked == (None, None)


def test_data_that_cannot_be_read_after_a_migration_is_an_error(models_project: Path, monkeypatch):
    import pangloss_cli.migrations as module

    assert invoke("makemigrations")[0] == 0
    set_models(models_project, V2)
    assert invoke("makemigrations", input="1\n")[0] == 0
    monkeypatch.setattr(module, "check_data", Checked(problems=[1, 2]))
    exit_code, output = invoke("migrate")
    assert exit_code == 1
    assert "2 of 5 cannot be read" in output
    assert "born: Field required" in output
    assert backend().APPLIED  # (it was applied)


def test_check_data_reads_the_data(models_project: Path, monkeypatch):
    import pangloss_cli.migrations as module

    checked = Checked()
    monkeypatch.setattr(module, "check_data", checked)
    exit_code, output = invoke("check-data", "--type", "Person", "--limit", "10")
    assert exit_code == 0, output
    assert checked.asked == (["Person"], 10)
    monkeypatch.setattr(module, "check_data", Checked(problems=[1]))
    assert invoke("check-data")[0] == 1


def test_migrate_can_be_told_to_work_in_batches(models_project: Path):
    assert invoke("makemigrations")[0] == 0
    exit_code, output = invoke("migrate", "--batch-size", "500")
    assert exit_code == 0, output
    assert backend().BATCHES == [500]
    assert invoke("migrate", "--batch-size", "0")[0] != 0  # (a batch has at least one node)
