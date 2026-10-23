from types import SimpleNamespace
from uuid import uuid7

from history_support import record
from pangloss_history.cli import cli
from pangloss_history.store import SqliteStore
from typer.testing import CliRunner


def run(path, *args):
    obj = SimpleNamespace(settings=SimpleNamespace(HISTORY_DB_PATH=str(path)))
    return CliRunner().invoke(cli, list(args), obj=obj)


def test_list_show_and_diff(tmp_path):
    path = tmp_path / "h.sqlite3"
    id = uuid7()
    SqliteStore(path).append(
        [record(id, 1, content={"text": "one"}), record(id, 2, "update", content={"text": "two"})]
    )

    listed = run(path, "list", str(id))
    assert listed.exit_code == 0
    assert "v1  create" in listed.output and "v2  update" in listed.output and "john" in listed.output

    assert '"text": "one"' in run(path, "show", str(id), "1").output

    difference = run(path, "diff", str(id), "1")
    assert difference.exit_code == 0
    assert '~ text: "one" -> "two"' in difference.output
    assert "No differences" in run(path, "diff", str(id), "2", "--to", "2").output


def test_what_is_not_there_is_reported(tmp_path):
    missing = run(tmp_path / "none.sqlite3", "list", str(uuid7()))
    assert missing.exit_code == 1 and "no history yet" in missing.output

    path = tmp_path / "h.sqlite3"
    SqliteStore(path)
    assert run(path, "list", str(uuid7())).exit_code == 1
    assert run(path, "show", str(uuid7()), "1").exit_code == 1
