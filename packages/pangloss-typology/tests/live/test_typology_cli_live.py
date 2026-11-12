"""`pangloss typology load`, `dump` and `tree`, run against the database (on the backend under test)"""

import json
from typing import no_type_check

from pangloss_testing.live import run, run_command

from pangloss_typology.cli import cli
from test_typology_live import vocabulary

FILE = """// The roles of a chancery (a comment, as a .jsonc file may have)
[
  {"label": "Official", "label_de": "Beamter", "children": [
    {"label": "Secretary", "description": "Writes the letters"}
  ]},
  {"label": "Bard"}
]
"""


def typology(backend, *arguments):
    return run_command(cli, backend, *arguments)


@no_type_check
def test_a_file_is_loaded_shown_and_written_out_in_the_form_it_was_read(
    clear_database, command_backend, db_driver, tmp_path
):
    vocabulary()
    path = tmp_path / "roles.jsonc"
    path.write_text(FILE)

    loaded = typology(
        command_backend,
        "load",
        "RoleType",
        str(path),
        "--user",
        "pangloss_default_user",
    )
    assert loaded.exit_code == 0, loaded.output
    assert loaded.output.strip() == "3 made, 0 already there"
    # (again: what is there is left alone)
    again = typology(
        command_backend,
        "load",
        "RoleType",
        str(path),
        "--user",
        "pangloss_default_user",
    )
    assert again.output.strip() == "0 made, 3 already there"

    shown = typology(command_backend, "tree", "RoleType")
    assert shown.exit_code == 0, shown.output
    assert shown.output.splitlines() == ["Bard", "Official", "  Secretary"]

    dumped = typology(command_backend, "dump", "RoleType")
    assert dumped.exit_code == 0, dumped.output
    entries = json.loads(dumped.output)
    assert [e["label"] for e in entries] == ["Bard", "Official"]
    official = entries[1]
    assert official["label_de"] == "Beamter"
    assert official["children"][0]["label"] == "Secretary"
    assert official["children"][0]["description"] == "Writes the letters"

    # (and what `dump --to` writes, `load` reads: into an empty typology, the same hierarchy)
    out = tmp_path / "out.json"
    written = typology(command_backend, "dump", "RoleType", "--to", str(out))
    assert written.output.strip() == f"Written to {out}"
    assert json.loads(out.read_text()) == entries
    run(db_driver, "MATCH (t:RoleType) DETACH DELETE t")
    reloaded = typology(
        command_backend, "load", "RoleType", str(out), "--user", "pangloss_default_user"
    )
    assert reloaded.output.strip() == "3 made, 0 already there"
    assert typology(command_backend, "tree", "RoleType").output == shown.output
    assert json.loads(typology(command_backend, "dump", "RoleType").output) == entries


@no_type_check
def test_one_type_on_its_own_may_be_the_whole_file(
    clear_database, command_backend, tmp_path
):
    vocabulary()
    path = tmp_path / "one.json"
    path.write_text('{"label": "Herald"}')
    loaded = typology(
        command_backend,
        "load",
        "RoleType",
        str(path),
        "--user",
        "pangloss_default_user",
    )
    assert loaded.exit_code == 0, loaded.output
    assert loaded.output.strip() == "1 made, 0 already there"


@no_type_check
def test_what_cannot_be_loaded_is_said_and_nothing_is_made(
    clear_database, command_backend, db_driver, tmp_path
):
    vocabulary()
    good = tmp_path / "roles.json"
    good.write_text('[{"label": "Official"}]')

    unknown = typology(
        command_backend, "load", "Nothing", str(good), "--user", "pangloss_default_user"
    )
    assert unknown.exit_code == 2
    assert "No typology Nothing. Known: RoleType" in unknown.output

    nobody = typology(
        command_backend, "load", "RoleType", str(good), "--user", "nobody"
    )
    assert nobody.exit_code == 1
    assert "There is no user called 'nobody'" in nobody.output

    not_a_list = tmp_path / "number.json"
    not_a_list.write_text("42")
    refused = typology(
        command_backend,
        "load",
        "RoleType",
        str(not_a_list),
        "--user",
        "pangloss_default_user",
    )
    assert refused.exit_code == 2
    assert "The file must hold a list of types" in refused.output

    no_label = tmp_path / "unlabelled.json"
    no_label.write_text('[{"label": "Official", "children": [{"description": "?"}]}]')
    refused = typology(
        command_backend,
        "load",
        "RoleType",
        str(no_label),
        "--user",
        "pangloss_default_user",
    )
    assert refused.exit_code == 1
    assert "Every type in the file needs a label (in Official)" in refused.output

    other_language = tmp_path / "french.json"
    other_language.write_text('[{"label": "Official", "label_fr": "Fonctionnaire"}]')
    refused = typology(
        command_backend,
        "load",
        "RoleType",
        str(other_language),
        "--user",
        "pangloss_default_user",
    )
    assert refused.exit_code == 1
    assert "Official: no label in the language of label_fr" in refused.output

    assert run(db_driver, "MATCH (t:RoleType) RETURN count(t) AS n") == [{"n": 0}]
