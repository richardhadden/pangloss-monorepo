import sys
from pathlib import Path

import pytest
from cli_support import write
from pangloss_cli.main import build_app
from pangloss_models.model_registry import ModelRegistry
from typer.testing import CliRunner

runner = CliRunner()

FAKE_MIGRATION_BACKEND = """
    APPLIED = {}
    CALLS = []
    BATCHES = []

    async def ensure_ready():
        CALLS.append("ensure_ready")

    async def applied():
        return dict(APPLIED)

    BACKUP_FAILS = False
    RESTORED = []

    async def backup_notice():
        return "Memgraph keeps 3 snapshots"

    async def backups():
        return [{"path": "/snapshots/1", "creation_time": "2026-10-21T10:00", "size": "62KiB"}]

    async def restore(path):
        from pangloss_models.exceptions import PanglossMigrationError

        if path != "/snapshots/1":
            raise PanglossMigrationError(f"{path} is not a snapshot the server has")
        RESTORED.append(path)

    async def backup():
        from pangloss_models.exceptions import PanglossMigrationError

        CALLS.append("backup")
        if BACKUP_FAILS:
            raise PanglossMigrationError("Cannot take a snapshot: no")
        return "/snapshots/1"

    HAS_DATA = False

    async def has_data():
        return HAS_DATA

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

    async def unapply(migrations, state, fake=False, progress=None, batch_size=None):
        for migration in migrations:
            if progress:
                progress(migration, "undoing")
            CALLS.append(("unapply", migration.name, fake, [ch.kind for ch in migration.changes]))
            BATCHES.append(batch_size)
            del APPLIED[migration.key]
        return state

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

    async def nothing_to_read(types=None, limit=None, **_):
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


def test_an_empty_migration_is_made_to_write_by_hand(models_project: Path):
    assert invoke("makemigrations")[0] == 0
    exit_code, output = invoke("makemigrations", "--empty")
    assert exit_code == 1 and "needs the app" in output
    exit_code, output = invoke("makemigrations", "--empty", "nonsense")
    assert exit_code == 1 and "INSTALLED_APPS" in output

    exit_code, output = invoke(
        "makemigrations", "--empty", "fakeapp", "--name", "by_hand"
    )
    assert exit_code == 0, output
    assert migration_files(models_project) == ["0001_initial.py", "0002_by_hand.py"]
    path = models_project / "fakeapp/migrations/0002_by_hand.py"
    assert "RunCypher" in path.read_text()  # (the hint)

    # the models have not changed, so there is nothing else to make, and it can be applied
    assert "No changes" in invoke("makemigrations")[1]

    path.write_text(
        path.read_text().replace(
            "changes = changes_from_data([])",
            "from pangloss_models.migrations.changes import RunCypher\n\n"
            "changes = changes_from_data([RunCypher(query='MATCH (n) SET n.x = 1', lossy=True)])",
        )
    )
    exit_code, output = invoke("migrate", "--plan")
    assert exit_code == 0, output
    assert "Run a query" in output and "[LOSES DATA]" in output


def test_a_rename_is_asked_and_the_answer_is_used(models_project: Path):
    set_models(models_project, V1.replace("name: str", "name: str\n        born: int"))
    assert invoke("makemigrations")[0] == 0
    renamed = V1.replace("name: str", "name: str\n        birth_year: int")
    set_models(models_project, renamed)

    exit_code, output = invoke("makemigrations", input="y\n")
    assert exit_code == 0, output
    assert "was the field 'born' renamed to 'birth_year'" in output.replace(
        "Was", "was"
    )
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
    set_models(
        models_project, V2.replace("born: int", "born: int\n        extra: str | None")
    )
    assert invoke("makemigrations", "--noinput")[0] in (0, 1)
    # a migration that removes a field
    set_models(models_project, V1)
    assert invoke("makemigrations", "--noinput")[0] == 0
    files = migration_files(models_project)
    assert invoke("migrate", "--plan")[0] == 0

    # (a backup, or not wanting one, has to be said)
    exit_code, output = invoke("migrate", "--yes")
    assert exit_code != 0 and "--backup" in output
    assert backend().APPLIED == {}

    exit_code, output = invoke("migrate", "--no-backup", input="n\n")
    assert exit_code != 0
    assert backend().APPLIED == {}

    exit_code, output = invoke("migrate", "--no-backup", "--yes")
    assert exit_code == 0, output
    assert len(backend().APPLIED) == len(files)
    assert "Backup" not in output and "backup" not in backend().CALLS


def test_a_backup_is_taken_after_the_lock_and_before_applying(models_project: Path):
    assert invoke("makemigrations")[0] == 0
    exit_code, output = invoke("migrate", "--backup")
    assert exit_code == 0, output
    assert "Backup: /snapshots/1" in output
    assert backend().CALLS.index("lock") < backend().CALLS.index("backup")
    assert backend().CALLS.index("backup") < backend().CALLS.index(
        ("apply", "0001_initial", False)
    )


def test_nothing_is_backed_up_for_a_fake_or_when_it_failed_to_be_taken(
    models_project: Path,
):
    assert invoke("makemigrations")[0] == 0
    assert invoke("migrate", "--fake", "--backup")[0] == 0
    assert "backup" not in backend().CALLS

    backend().APPLIED.clear()
    backend().BACKUP_FAILS = True
    exit_code, output = invoke("migrate", "--backup")
    assert exit_code != 0 and "Cannot take a snapshot" in output
    assert backend().APPLIED == {}
    assert "unlock" in backend().CALLS


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
    set_models(
        models_project, V1.replace("name: str", "name: str\n        boom: str | None")
    )
    assert invoke("makemigrations")[0] == 0
    exit_code, output = invoke("migrate", "--dry-run")
    assert exit_code == 1
    assert "it would fail" in output
    assert backend().APPLIED == {}


class Checked:
    def __init__(self, problems=()):
        from pangloss_models.migrations.check import DataCheck, DataProblem

        self.result = DataCheck(
            checked=5,
            problems=[
                DataProblem("Person", "1", "Ann", ["born: Field required"])
                for _ in problems
            ],
        )

    async def __call__(self, types=None, limit=None, concurrency=8):
        self.asked = (types, limit)
        self.concurrency = concurrency
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


def test_data_that_cannot_be_read_after_a_migration_is_an_error(
    models_project: Path, monkeypatch
):
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
    exit_code, output = invoke(
        "check-data", "--type", "Person", "--limit", "10", "--parallel", "3"
    )
    assert exit_code == 0, output
    assert checked.asked == (["Person"], 10) and checked.concurrency == 3
    monkeypatch.setattr(module, "check_data", Checked(problems=[1]))
    assert invoke("check-data")[0] == 1


def test_migrate_can_be_told_to_work_in_batches(models_project: Path):
    assert invoke("makemigrations")[0] == 0
    exit_code, output = invoke("migrate", "--batch-size", "500")
    assert exit_code == 0, output
    assert backend().BATCHES == [500]
    assert (
        invoke("migrate", "--batch-size", "0")[0] != 0
    )  # (a batch has at least one node)


# ---------------------------------------------------------------------------
# going backwards
# ---------------------------------------------------------------------------

V1_NICKNAME = V1.replace("name: str", "name: str\n        nickname: str | None")


@pytest.fixture
def two_migrations(models_project: Path):
    assert invoke("makemigrations")[0] == 0
    set_models(models_project, V1_NICKNAME)
    assert invoke("makemigrations")[0] == 0
    assert invoke("migrate")[0] == 0
    assert [name for _, name in backend().APPLIED] == [
        "0001_initial",
        migration_files(models_project)[1][:-3],
    ]
    return models_project


def test_a_plan_back_says_what_would_be_undone(two_migrations: Path):
    exit_code, output = invoke("migrate", "fakeapp", "0001", "--plan")
    assert exit_code == 0, output
    assert "To undo" in output and "RemoveField" not in output
    assert "Remove the literal field Person.nickname" in output
    assert "LOSES DATA" in output
    assert len(backend().APPLIED) == 2


def test_going_back_undoes_what_follows_and_it_can_be_applied_again(
    two_migrations: Path,
):
    exit_code, output = invoke("migrate", "fakeapp", "0001", "--yes")
    assert exit_code != 0 and "--backup" in output
    assert len(backend().APPLIED) == 2

    exit_code, output = invoke("migrate", "fakeapp", "0001", "--no-backup", input="n\n")
    assert exit_code != 0
    assert len(backend().APPLIED) == 2

    exit_code, output = invoke("migrate", "fakeapp", "0001", "--backup", "--yes")
    assert exit_code == 0, output
    assert "Backup: /snapshots/1" in output
    assert [name for _, name in backend().APPLIED] == ["0001_initial"]
    unapplied = [call for call in backend().CALLS if call[0] == "unapply"]
    assert [call[3] for call in unapplied] == [["RemoveField"]]

    # (undone, so pending again)
    assert "To apply" in invoke("migrate", "--plan")[1]
    assert invoke("migrate")[0] == 0
    assert len(backend().APPLIED) == 2


def test_zero_undoes_them_all_and_a_target_ahead_goes_forward(two_migrations: Path):
    assert invoke("migrate", "fakeapp", "zero", "--no-backup", "--yes")[0] == 0
    assert backend().APPLIED == {}

    exit_code, output = invoke("migrate", "fakeapp", "0001")
    assert exit_code == 0, output
    assert [name for _, name in backend().APPLIED] == [
        "0001_initial"
    ]  # (and not the second)


def test_a_target_has_to_be_one_migration_of_an_app(two_migrations: Path):
    exit_code, output = invoke("migrate", "fakeapp", "0009")
    assert exit_code != 0 and "not one migration" in output
    exit_code, output = invoke("migrate", "elsewhere", "0001")
    assert exit_code != 0 and "INSTALLED_APPS" in output
    assert len(backend().APPLIED) == 2


def test_a_migration_that_cannot_be_undone_is_said_to_be(two_migrations: Path):
    path = two_migrations / "fakeapp/migrations" / migration_files(two_migrations)[1]
    path.write_text(
        path.read_text().replace(
            "changes = changes_from_data(",
            "from pangloss_models.migrations.changes import RunCypher\n\n"
            "changes = changes_from_data([RunCypher(query='RETURN 1')] + ",
        )
    )
    # (it was edited after it was applied, so the files and the record disagree)
    assert invoke("migrate", "fakeapp", "0001", "--no-backup", "--yes")[0] != 0
    backend().APPLIED.clear()
    assert invoke("migrate", "--fake")[0] == 0
    exit_code, output = invoke("migrate", "fakeapp", "0001", "--no-backup", "--yes")
    assert exit_code != 0
    assert "cannot be undone" in output and "reverse_query" in output
    assert len(backend().APPLIED) == 2


# ---------------------------------------------------------------------------
# squashing
# ---------------------------------------------------------------------------

V1_NICKNAME_BORN = V1_NICKNAME.replace(
    "nickname: str | None", "nickname: str | None\n        born: int | None"
)


@pytest.fixture
def three_migrations(models_project: Path):
    assert invoke("makemigrations")[0] == 0
    set_models(models_project, V1_NICKNAME)
    assert invoke("makemigrations")[0] == 0
    set_models(models_project, V1_NICKNAME_BORN)
    assert invoke("makemigrations")[0] == 0
    assert len(migration_files(models_project)) == 3
    return models_project


def test_a_run_is_squashed_and_the_originals_are_kept(three_migrations: Path):
    exit_code, output = invoke(
        "squashmigrations", "fakeapp", "0001", "0003", "--dry-run"
    )
    assert exit_code == 0, output
    assert "nothing was written" in output and "replaces" in output
    assert len(migration_files(three_migrations)) == 3

    exit_code, output = invoke("squashmigrations", "fakeapp", "0001", "0003")
    assert exit_code == 0, output
    files = migration_files(three_migrations)
    assert len(files) == 4 and any("squashed_0003" in f for f in files)
    assert "changes in 3 migrations -> 1 changes" in output.replace("  ", " ")

    # nothing has changed in the models, so nothing is to be made
    assert "No changes" in invoke("makemigrations")[1]
    # (and the next migration comes after the squashed one)
    set_models(
        three_migrations,
        V1_NICKNAME_BORN.replace(
            "born: int | None", "born: int | None\n        age: int | None"
        ),
    )
    assert invoke("makemigrations")[0] == 0
    assert any(f.startswith("0004_") for f in migration_files(three_migrations))


def test_a_new_database_has_only_the_squashed_migration(three_migrations: Path):
    assert invoke("squashmigrations", "fakeapp", "0001", "0003")[0] == 0
    exit_code, output = invoke("migrate")
    assert exit_code == 0, output
    assert [name for _, name in backend().APPLIED] == [
        next(f[:-3] for f in migration_files(three_migrations) if "squashed" in f)
    ]
    assert "[X] 0001_squashed_0003" in invoke("showmigrations")[1]


def test_a_database_that_had_the_originals_needs_nothing(three_migrations: Path):
    assert invoke("migrate")[0] == 0
    assert len(backend().APPLIED) == 3
    assert invoke("squashmigrations", "fakeapp", "0001", "0003")[0] == 0

    exit_code, output = invoke("migrate")
    assert exit_code == 0 and "Nothing to apply" in output
    assert len(backend().APPLIED) == 3  # (the record is the originals')
    assert "[X] 0001_squashed_0003" in invoke("showmigrations")[1]

    # ... also when the originals have been deleted
    for name in migration_files(three_migrations):
        if "squashed" not in name:
            (three_migrations / "fakeapp/migrations" / name).unlink()
    exit_code, output = invoke("migrate")
    assert exit_code == 0 and "Nothing to apply" in output
    assert "disagree" not in output


def test_a_database_part_way_goes_on_with_the_originals(three_migrations: Path):
    assert invoke("migrate", "fakeapp", "0001")[0] == 0
    assert invoke("squashmigrations", "fakeapp", "0001", "0003")[0] == 0
    exit_code, output = invoke("migrate")
    assert exit_code == 0, output
    assert sorted(name[:4] for _, name in backend().APPLIED) == ["0001", "0002", "0003"]


def test_a_part_way_database_without_the_originals_can_still_be_listed(
    three_migrations: Path,
):
    assert invoke("migrate", "fakeapp", "0001")[0] == 0
    assert invoke("squashmigrations", "fakeapp", "0001", "0003")[0] == 0
    for name in migration_files(three_migrations):
        if "squashed" not in name:
            (three_migrations / "fakeapp/migrations" / name).unlink()

    exit_code, output = invoke("showmigrations")
    assert exit_code == 1
    assert "[X] 0001_initial (no file)" in output
    assert "[ ] 0001_squashed_0003" in output
    assert "files are missing" in output and "restore the files" in output


def test_nothing_is_squashed_that_cannot_be(three_migrations: Path):
    exit_code, output = invoke("squashmigrations", "fakeapp", "0001", "0009")
    assert exit_code != 0 and "not one migration" in output
    exit_code, output = invoke("squashmigrations", "elsewhere", "0001", "0003")
    assert exit_code != 0 and "INSTALLED_APPS" in output
    assert len(migration_files(three_migrations)) == 3


# ---------------------------------------------------------------------------
# the database's structure
# ---------------------------------------------------------------------------

INDEX_A = {"kind": "label+property", "label": "Person", "properties": ["name"]}
INDEX_B = {"kind": "label+property", "label": "Person", "properties": ["born"]}


def test_indexes_the_database_needs_are_migrations(models_project: Path):
    invoke("makemigrations", "--dry-run")  # (loads the backend)
    structure = {"indexes": [INDEX_A], "constraints": []}
    backend().structure = lambda: structure
    exit_code, output = invoke("makemigrations")
    assert exit_code == 0, output
    assert "Create the index :Person(name)" in output

    assert "No changes" in invoke("makemigrations")[1]

    # (a newer version of the database package wants another, and no longer the first)
    structure["indexes"] = [INDEX_B]
    exit_code, output = invoke("makemigrations")
    assert exit_code == 0, output
    assert (
        "Create the index :Person(born)" in output
        and "Drop the index :Person(name)" in output
    )
    assert len(migration_files(models_project)) == 2

    # ... which the server's check notices until they are made
    import asyncio

    from pangloss_models.migrations.startup import migration_problems

    found = asyncio.run(migration_problems(["fakeapp"], backend()))
    assert any("have not been applied" in line for line in found)
    assert invoke("migrate")[0] == 0
    assert asyncio.run(migration_problems(["fakeapp"], backend())) == []


def test_setting_up_a_database_that_has_migrations_is_warned_about(
    models_project: Path,
):
    exit_code, output = invoke("setup-database")
    assert exit_code == 0, output
    assert "has migrations" not in output

    assert invoke("makemigrations")[0] == 0
    exit_code, output = invoke("setup-database")
    assert exit_code == 0, output
    assert "This project has migrations" in output and "Database is set up" in output


def test_a_database_with_data_and_no_record_is_pointed_to_fake(models_project: Path):
    assert invoke("makemigrations")[0] == 0
    invoke("migrate", "--plan")  # (loads the backend)
    backend().HAS_DATA = True
    exit_code, output = invoke("migrate", "--plan")
    assert (
        exit_code == 0 and "no record of any migration" in output and "--fake" in output
    )

    # not once there is a record, nor when faking
    backend().APPLIED.clear()
    exit_code, output = invoke("migrate", "--fake")
    assert "no record of any migration" not in output
    assert invoke("migrate", "--plan")[0] == 0
    backend().HAS_DATA = False


def test_migrations_can_be_made_for_one_app(models_project: Path):
    exit_code, output = invoke("makemigrations", "elsewhere")
    assert exit_code != 0 and "INSTALLED_APPS" in output
    assert migration_files(models_project) == []

    exit_code, output = invoke("makemigrations", "fakeapp")
    assert exit_code == 0, output
    assert migration_files(models_project) == ["0001_initial.py"]

    exit_code, output = invoke("makemigrations", "fakeapp")
    assert "No changes" in output

    # (a change to the app's models, asked about as for all)
    set_models(models_project, V2)
    exit_code, output = invoke("makemigrations", "fakeapp", "--noinput")
    assert exit_code == 1 and "born" in output
    exit_code, output = invoke("makemigrations", "fakeapp", "--check")
    assert exit_code == 1 and "changes since the last migration" in output
    exit_code, output = invoke("makemigrations", "fakeapp", input="1900\n")
    assert exit_code == 0, output
    assert len(migration_files(models_project)) == 2


def test_a_model_that_changes_kind_is_refused_by_makemigrations(models_project: Path):
    assert invoke("makemigrations")[0] == 0
    set_models(
        models_project,
        V1.replace(
            "from pangloss_models.model_bases.entity import Entity",
            "from pangloss_models.model_bases.document import Document",
        ).replace("(Entity)", "(Document)"),
    )
    exit_code, output = invoke("makemigrations")
    assert exit_code == 1
    assert "kind of a model cannot be changed" in output and "Keep its kind" in output
    assert migration_files(models_project) == ["0001_initial.py"]
    assert invoke("makemigrations", "--check")[0] == 1


@pytest.fixture
def born_then_removed(models_project: Path):
    assert invoke("makemigrations")[0] == 0
    set_models(models_project, V2)
    assert invoke("makemigrations", input="1900\n")[0] == 0
    set_models(models_project, V1)
    assert invoke("makemigrations")[0] == 0
    assert invoke("migrate", "--no-backup", "--yes")[0] == 0
    assert len(backend().APPLIED) == 3
    return models_project


def test_a_plan_back_says_what_going_back_will_ask_for(born_then_removed: Path):
    exit_code, output = invoke("migrate", "fakeapp", "0002", "--plan")
    assert exit_code == 0, output
    assert "To undo" in output and "Going back will ask for" in output
    assert "born" in output
    assert len(backend().APPLIED) == 3

    # not asked in a plan; asked when it is done (and by a dry run, which tries it)
    exit_code, output = invoke(
        "migrate", "fakeapp", "0002", "--dry-run", input="1950\n"
    )
    assert exit_code == 0, output
    assert len(backend().APPLIED) == 3
    exit_code, output = invoke(
        "migrate", "fakeapp", "0002", "--no-backup", "--yes", input="1950\n"
    )
    assert exit_code == 0, output
    assert len(backend().APPLIED) == 2
    undone = [call for call in backend().CALLS if call[0] == "unapply"]
    assert undone[-1][3] == ["AddField"]


def test_going_back_can_be_in_batches(born_then_removed: Path):
    exit_code, output = invoke(
        "migrate",
        "fakeapp",
        "0002",
        "--no-backup",
        "--yes",
        "--batch-size",
        "7",
        input="1950\n",
    )
    assert exit_code == 0, output
    assert backend().BATCHES[-1] == 7


def test_a_migration_that_failed_or_was_left_running_is_undone_too(
    born_then_removed: Path,
):
    last = sorted(backend().APPLIED)[-1]
    backend().APPLIED[last]["status"] = "failed"
    exit_code, output = invoke(
        "migrate", "fakeapp", "0002", "--no-backup", "--yes", input="1950\n"
    )
    assert exit_code == 0, output
    assert last not in backend().APPLIED
    assert len(backend().APPLIED) == 2


def test_a_squashed_migration_is_squashed_again_with_the_ones_after_it(
    three_migrations: Path,
):
    assert invoke("squashmigrations", "fakeapp", "0001", "0002")[0] == 0
    files = migration_files(three_migrations)
    assert len(files) == 4 and any("squashed_0002" in f for f in files)

    exit_code, output = invoke("squashmigrations", "fakeapp", "0001", "0003")
    assert exit_code == 0, output
    assert "0001_squashed_0003" in output and "replaces" in output
    files = migration_files(three_migrations)
    assert len(files) == 5 and any("0001_squashed_0003" in f for f in files)

    # a new database has only the last; one that had everything has nothing to do
    exit_code, output = invoke("migrate")
    assert exit_code == 0, output
    assert [name for _, name in backend().APPLIED] == [
        next(f[:-3] for f in files if "0001_squashed_0003" in f)
    ]
    assert "No changes" in invoke("makemigrations")[1]


def test_the_originals_of_a_squashed_migration_can_be_deleted(three_migrations: Path):
    assert invoke("squashmigrations", "fakeapp", "0001", "0003")[0] == 0
    assert len(migration_files(three_migrations)) == 4

    exit_code, output = invoke("cleanmigrations", "fakeapp", input="n\n")
    assert (
        exit_code != 0
        and "0001_initial.py" in output
        and "No other database is looked at" in output
    )
    assert len(migration_files(three_migrations)) == 4

    exit_code, output = invoke("cleanmigrations", "fakeapp", "--yes")
    assert exit_code == 0, output
    assert len(migration_files(three_migrations)) == 1
    assert "squashed_0003" in migration_files(three_migrations)[0]
    assert "Nothing to delete" in invoke("cleanmigrations")[1]

    # the project goes on as before
    assert invoke("migrate")[0] == 0
    assert "No changes" in invoke("makemigrations")[1]


def test_cleaning_warns_of_the_history_that_would_be_left_part_way(
    three_migrations: Path, monkeypatch
):
    from pangloss_cli import migrations as module

    assert invoke("squashmigrations", "fakeapp", "0001", "0003")[0] == 0
    asked = []

    def warn(project, squashed):
        asked.extend(m.name for m in squashed)
        return ["3 recorded versions were written part way through it"]

    monkeypatch.setattr(module, "history_warnings", warn)
    exit_code, output = invoke("cleanmigrations", "fakeapp", "--yes")
    assert exit_code == 0, output  # (a warning, not a refusal)
    assert "History: 3 recorded versions" in output
    assert len(asked) == 1 and "squashed_0003" in asked[0]
    assert len(migration_files(three_migrations)) == 1


def test_nothing_is_deleted_for_a_database_that_is_part_way_through(
    three_migrations: Path,
):
    assert invoke("migrate", "fakeapp", "0001")[0] == 0  # (only the first applied)
    assert invoke("squashmigrations", "fakeapp", "0001", "0003")[0] == 0

    exit_code, output = invoke("cleanmigrations", "--yes")
    assert exit_code == 0, output
    assert "part way" in output and "Nothing to delete" in output
    assert len(migration_files(three_migrations)) == 4


def test_a_squash_of_a_squash_deletes_both_sets(three_migrations: Path):
    assert invoke("squashmigrations", "fakeapp", "0001", "0002")[0] == 0
    assert invoke("squashmigrations", "fakeapp", "0001", "0003")[0] == 0
    assert len(migration_files(three_migrations)) == 5
    assert invoke("cleanmigrations", "--yes")[0] == 0
    left = migration_files(three_migrations)
    assert len(left) == 1 and "squashed_0003" in left[0]


def test_a_backup_says_how_long_it_lasts_and_backups_can_be_listed_and_restored(
    models_project: Path,
):
    assert invoke("makemigrations")[0] == 0
    exit_code, output = invoke("migrate", "--backup")
    assert exit_code == 0, output
    assert "Backup: /snapshots/1" in output and "Memgraph keeps 3 snapshots" in output

    exit_code, output = invoke("backups")
    assert exit_code == 0 and "/snapshots/1" in output and "62KiB" in output

    exit_code, output = invoke("restore", "/snapshots/1", input="n\n")
    assert exit_code != 0 and backend().RESTORED == []
    exit_code, output = invoke("restore", "/snapshots/1", "--yes")
    assert exit_code == 0, output
    assert backend().RESTORED == ["/snapshots/1"]
    exit_code, output = invoke("restore", "/nowhere", "--yes")
    assert exit_code != 0 and "not a snapshot" in output
