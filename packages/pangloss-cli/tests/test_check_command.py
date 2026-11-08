import json
import sys
from pathlib import Path

import pytest
from cli_support import write
from pangloss_cli.main import build_app
from pangloss_models import ModelRegistry
from typer.testing import CliRunner

runner = CliRunner()

# (the line numbers below are of this text, after its first, empty line)
BROKEN = """
    from pangloss_models import Document, Entity


    class Person(Entity):
        name: str
        anything: dict[str, str]


    class Statement(Document):
        about: Person
        weight: complex

        def label_upper(self) -> str:
            return self.label.upper()
"""


@pytest.fixture(autouse=True)
def clean_registry():
    ModelRegistry._reset()
    yield
    ModelRegistry._reset()


def check(*args: str):
    app = build_app(argv=[], environment={})
    result = runner.invoke(app, ["check", *args])
    return result.exit_code, result.stdout, result.stderr


def report() -> dict:
    return json.loads(check("--json")[1].strip().rsplit("\n", 1)[-1])


def test_every_refused_field_is_reported_at_its_name(project: Path):
    write(project, "fakeapp/models.py", BROKEN)

    code, out, _ = check("--json")
    assert code == 1
    found = {
        (d["line"], d["column"], d["end_column"]): d
        for d in json.loads(out.strip().rsplit("\n", 1)[-1])["diagnostics"]
    }

    assert set(found) == {(7, 4, 12), (12, 4, 10)}
    assert "Person.anything" in found[(7, 4, 12)]["message"]
    assert "Statement.weight" in found[(12, 4, 10)]["message"]
    assert all(d["severity"] == "error" for d in found.values())
    assert all(d["file"] == str(project / "fakeapp/models.py") for d in found.values())


def test_the_text_form_is_file_line_column(project: Path):
    write(project, "fakeapp/models.py", BROKEN)

    code, _, err = check()
    assert code == 1
    assert "models.py:7:5: error:" in err.replace(chr(10), "")


def test_a_field_refused_on_a_parent_is_reported_once_at_the_parent(project: Path):
    write(
        project,
        "fakeapp/models.py",
        """
        from pangloss_models import Entity


        class Parent(Entity):
            anything: dict[str, str]


        class Child(Parent):
            pass
        """,
    )

    assert [d["line"] for d in report()["diagnostics"]] == [6]


def test_a_warning_is_at_the_member_it_is_about_and_does_not_fail(project: Path):
    write(
        project,
        "fakeapp/models.py",
        """
        from pydantic import ConfigDict
        from pangloss_models import Entity


        class Person(Entity):
            model_config = ConfigDict(frozen=True)
        """,
    )

    code, out, _ = check("--json")
    assert code == 0
    (warning,) = json.loads(out.strip().rsplit("\n", 1)[-1])["diagnostics"]
    assert warning["severity"] == "warning"
    assert warning["line"] == 7
    assert (warning["column"], warning["end_column"]) == (4, 16)


def test_the_warning_about_a_model_config_can_be_fixed_by_removing_it(project: Path):
    write(
        project,
        "fakeapp/models.py",
        """
        from pydantic import ConfigDict
        from pangloss_models import Entity


        class Person(Entity):
            name: str
            model_config = ConfigDict(frozen=True)
        """,
    )

    (warning,) = report()["diagnostics"]
    (fix,) = warning["fixes"]
    assert fix["title"] == "Remove `model_config`"
    (edit,) = fix["edits"]
    assert (edit["line"], edit["column"], edit["end_line"], edit["end_column"]) == (
        8,
        0,
        9,
        0,
    )
    assert edit["old_text"] == "    model_config = ConfigDict(frozen=True)\n"
    assert edit["new_text"] == ""


def test_an_optional_list_of_relations_can_be_fixed_by_dropping_the_none(project: Path):
    write(
        project,
        "fakeapp/models.py",
        """
        from pangloss_models import Entity


        class Place(Entity):
            pass


        class Person(Entity):
            visited: list[Place] | None
        """,
    )

    (error,) = report()["diagnostics"]
    (fix,) = error["fixes"]
    assert fix["title"] == "Change to `list[Place]`"
    (edit,) = fix["edits"]
    assert edit["old_text"] == "list[Place] | None"
    assert edit["new_text"] == "list[Place]"
    assert (edit["line"], edit["column"], edit["end_column"]) == (10, 13, 31)


def test_a_list_that_holds_none_has_two_fixes(project: Path):
    write(
        project,
        "fakeapp/models.py",
        """
        from pangloss_models import Entity


        class Person(Entity):
            tags: list[str | None]
        """,
    )

    (error,) = report()["diagnostics"]
    fixes = {fix["title"]: fix["edits"][0] for fix in error["fixes"]}
    assert set(fixes) == {
        "Remove `None` from the items: `list[str]`",
        "Make the whole list optional: `list[str] | None`",
    }
    items = fixes["Remove `None` from the items: `list[str]`"]
    assert (items["old_text"], items["new_text"]) == ("str | None", "str")
    whole = fixes["Make the whole list optional: `list[str] | None`"]
    assert (whole["old_text"], whole["new_text"]) == (
        "list[str | None]",
        "list[str] | None",
    )


def test_a_fix_in_a_line_with_other_characters_before_it_has_character_columns(
    project: Path,
):
    write(
        project,
        "fakeapp/models.py",
        """
        from pangloss_models import Entity


        class Place(Entity):
            pass


        class Person(Entity):
            nömé_visited: list[Place] | None
        """,
    )

    (error,) = report()["diagnostics"]
    (edit,) = error["fixes"][0]["edits"]
    assert edit["column"] == len("    nömé_visited: ")


def test_the_report_has_the_options_of_the_metas_and_the_models(project: Path):
    write(
        project,
        "fakeapp/models.py",
        """
        from pangloss_models import Entity


        class Place(Entity):
            name: str
            _x = 1
        """,
    )

    schema = report()["schema"]
    options = {p["name"]: p for p in schema["calls"]["EntityMeta"]["parameters"]}
    assert {"abstract", "indexes", "create_with_id"} <= set(options)
    assert "Fields of this class to keep an index of" in options["indexes"]["doc"]
    assert schema["aliases"]["Entity.Meta"] == "EntityMeta"
    assert schema["aliases"]["Place.Meta"] == "EntityMeta"
    assert schema["models"]["Place"]["fields"] == {"name": "literal"}
    assert schema["models"]["Place"]["kind"] == "Entity"
    assert "RelationConfig" in schema["calls"] and "FieldBinding" in schema["calls"]


def test_a_syntax_error_is_at_its_line(project: Path):
    write(project, "fakeapp/models.py", "class Person(:\n    pass\n")

    (error,) = report()["diagnostics"]
    assert error["file"] == str(project / "fakeapp/models.py")
    assert error["line"] == 1


def test_what_fails_while_a_class_is_declared_is_at_the_line_in_the_project(
    project: Path,
):
    write(
        project,
        "fakeapp/models.py",
        """
        from pangloss_models import Entity


        raise ValueError("not at import, please")
        """,
    )

    (error,) = report()["diagnostics"]
    assert error["line"] == 5
    assert error["message"] == "ValueError: not at import, please"


def test_no_settings_is_a_diagnostic_with_no_place(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    code, out, _ = check("--json")
    assert code == 1
    (error,) = json.loads(out)["diagnostics"]
    assert error["file"] is None
    assert "No settings found" in error["message"]


def test_what_a_field_means_is_described(project: Path):
    write(
        project,
        "fakeapp/models.py",
        """
        from pangloss_models import Entity


        class Place(Entity):
            pass


        class Person(Entity):
            born_in: Place
            age: int = 3
        """,
    )

    fields = report()["fields"]
    assert "Relation to `Place` (exactly one)" in fields["Person.born_in"]
    assert "the reverse" in fields["Person.born_in"]
    assert "required" in fields["Person.born_in"]
    assert "A value stored on the node: `int`." in fields["Person.age"]
    assert "may be left out: `3`" in fields["Person.age"]


def test_stubs_are_written_only_if_the_models_are_sound(project: Path):
    write(project, "fakeapp/models.py", BROKEN)
    check("--json", "--write-stubs")
    assert not (project / "fakeapp/models.pyi").exists()

    ModelRegistry._reset()
    write(
        project,
        "fakeapp/models.py",
        "from pangloss_models import Entity\n\n\nclass Person(Entity):\n    pass\n",
    )
    del sys.modules["fakeapp.models"]
    code, _, _ = check("--json", "--write-stubs")
    assert code == 0
    assert (project / "fakeapp/models.pyi").exists()


def test_a_stub_that_has_not_changed_is_left_alone(project: Path):
    write(
        project,
        "fakeapp/models.py",
        "from pangloss_models import Entity\n\n\nclass Person(Entity):\n    pass\n",
    )
    check("--json", "--write-stubs")
    stub = project / "fakeapp/models.pyi"
    first = stub.stat().st_mtime_ns

    ModelRegistry._reset()
    check("--json", "--write-stubs")
    assert stub.stat().st_mtime_ns == first
