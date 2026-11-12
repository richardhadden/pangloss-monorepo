"""`pangloss merge`, `pangloss unmerge`, `pangloss merges` and what `pangloss check-data` says of merged entities, run
against the database. (The commands run their own event loop, so these tests are not async themselves.)"""

from types import SimpleNamespace
from typing import no_type_check
from uuid import uuid7

import pytest
from pangloss_cli import migrations
from pangloss_cli.merges import cli

from pangloss_testing.live import run_command, run_connected

from .helpers import run
from .merge_support import declare, make, merged_into, person, ref
from .test_merge_check_data import point_at

pytestmark = pytest.mark.requires("cypher")

USER = "pangloss_default_user"


@no_type_check
def test_a_merge_and_its_undoing_from_the_command_line(
    clear_database, db_driver, command_backend
):
    m = declare()

    async def seed():
        a = await person(m, "John Smith")
        b = await person(m, "Jon Smyth")
        mention = await make(m.Mention, "Of both", of=ref(b), others=[ref(a), ref(b)])
        return a, b, mention

    a, b, mention = run_connected(command_backend, seed)

    dry = run_command(
        cli, command_backend, "merge", "Person", str(a.id), str(b.id),
        "--user", USER, "--dry-run",
    )  # fmt: skip
    assert dry.exit_code == 0, dry.output
    assert "would write 1 documents and entities" in dry.output
    assert "1 name both in one relation" in dry.output
    assert merged_into(db_driver, b.id) is None

    done = run_command(
        cli, command_backend, "merge", "Person", str(a.id), str(b.id), "--user", USER
    )  # fmt: skip
    assert done.exit_code == 0, done.output
    assert "1 references moved in 1 documents and entities, 1 dropped" in done.output
    assert f"names the survivor once where it named both: Mention {mention.id}" in (
        done.output
    )
    assert merged_into(db_driver, b.id) == str(a.id)
    merge_id = run(db_driver, "MATCH (m:PGMerge) RETURN m.id AS id")[0]["id"]
    assert f"merge {merge_id}" in done.output

    listed = run_command(cli, command_backend, "merges")
    assert listed.exit_code == 0, listed.output
    assert merge_id in listed.output and "Jon Smyth -> Person John Smith" in (
        listed.output
    )
    assert "1 in all" in listed.output
    assert (
        "No merges"
        in run_command(cli, command_backend, "merges", "--state", "undone").output
    )

    would = run_command(
        cli, command_backend, "unmerge", merge_id, "--user", USER, "--dry-run"
    )
    assert would.exit_code == 0, would.output
    assert "2 references would go back" in would.output
    assert merged_into(db_driver, b.id) == str(a.id)
    undone = run_command(cli, command_backend, "unmerge", merge_id, "--user", USER)
    assert undone.exit_code == 0, undone.output
    assert "2 references went back" in undone.output
    assert "The survivor's fields are as they were before the merge" in undone.output
    assert merged_into(db_driver, b.id) is None
    again = run_command(cli, command_backend, "unmerge", merge_id, "--user", USER)
    assert again.exit_code == 1 and "Not undone" in again.output


@no_type_check
def test_pairs_from_a_file_are_merged_until_one_cannot_be(
    clear_database, db_driver, command_backend, tmp_path
):
    m = declare()

    async def seed():
        return [await person(m, name) for name in "ABCDEF"]

    a, b, c, d, e, f = run_connected(command_backend, seed)
    pairs = tmp_path / "pairs.txt"
    pairs.write_text(
        f"# survivor, absorbed\n{a.id} {b.id}\n\n{c.id},{d.id}\n{a.id}\t{b.id}\n{e.id} {f.id}\n"
    )
    result = run_command(
        cli, command_backend, "merge", "Person", "--pairs", str(pairs), "--user", USER
    )
    # the third names an entity that is merged already: it stops there, and what was merged stays
    assert result.exit_code == 1, result.output
    assert "not merged" in result.output and "was merged into" in result.output
    assert merged_into(db_driver, b.id) == str(a.id)
    assert merged_into(db_driver, d.id) == str(c.id)
    assert merged_into(db_driver, f.id) is None

    # what cannot be read, or is not asked for properly, writes nothing
    pairs.write_text(f"{e.id}\n")
    bad = run_command(
        cli, command_backend, "merge", "Person", "--pairs", str(pairs), "--user", USER
    )
    assert bad.exit_code == 1 and "line 1: expected two ids" in bad.output
    for arguments in (
        ("merge", "Person", str(e.id), "--user", USER),
        ("merge", "Person", str(e.id), str(f.id), "--pairs", str(pairs), "--user", USER),
        ("merge", "Nothing", str(e.id), str(f.id), "--user", USER),
        ("merge", "Person", str(e.id), str(uuid7()), "--user", USER),
        ("merge", "Person", str(e.id), str(f.id), "--user", "nobody_of_this_name"),
    ):  # fmt: skip
        refused = run_command(cli, command_backend, *arguments)
        assert refused.exit_code != 0, (arguments, refused.output)
    assert merged_into(db_driver, f.id) is None


@no_type_check
def test_a_merge_over_the_limit_is_made_only_when_asked_for_as_large(
    clear_database, db_driver, command_backend, monkeypatch
):
    from pangloss_core import settings as core_settings

    m = declare()

    async def seed():
        a, b = await person(m, "A"), await person(m, "B")
        for index in range(5):
            await make(m.Mention, f"Of B {index}", of=ref(b))
        return a, b

    a, b = run_connected(command_backend, seed)
    monkeypatch.setattr(core_settings.SETTINGS, "MERGE_LIMIT", 2)
    arguments = ("merge", "Person", str(a.id), str(b.id), "--user", USER)
    refused = run_command(cli, command_backend, *arguments)
    assert refused.exit_code == 1 and "more than 2 (MERGE_LIMIT)" in refused.output
    assert merged_into(db_driver, b.id) is None
    dry = run_command(cli, command_backend, *arguments, "--dry-run")
    assert "over the limit of 2: --large" in dry.output
    done = run_command(cli, command_backend, *arguments, "--large")
    assert done.exit_code == 0, done.output
    assert "5 references moved in 5 documents and entities" in done.output


@no_type_check
def test_check_data_reports_and_moves_what_is_on_merged_entities(
    clear_database, db_driver, command_backend, capsys
):
    m = declare()

    async def seed():
        a, b = await person(m, "A"), await person(m, "B")
        late = await make(m.Mention, "Late", of=ref(a))
        await m.Person.merge(absorb=b.id, into=a.id)
        return a, b, late

    a, b, late = run_connected(command_backend, seed)
    project = SimpleNamespace(require_database=lambda: command_backend)

    assert migrations.report_merged_check(project, False, None) is False
    assert "Nothing refers to an entity that was merged" in capsys.readouterr().out

    point_at(db_driver, late, "of", a, b)
    assert migrations.report_merged_check(project, False, None) is True
    said = capsys.readouterr().err
    assert "1 references are on entities that were merged into others" in said
    assert (
        f"Mention {late.id}: Mention.of -> Person {b.id} (B), merged into {a.id}"
        in (said)
    )
    assert "--move-merged moves them" in said

    assert migrations.report_merged_check(project, True, USER) is False
    said = capsys.readouterr().out
    assert "1 documents and entities written" in said
    assert "Nothing refers to an entity that was merged" in said
    assert run(
        db_driver,
        "MATCH (:Mention {id: $d})-[:of]->(p) RETURN p.id AS id",
        d=str(late.id),
    ) == [{"id": str(a.id)}]
