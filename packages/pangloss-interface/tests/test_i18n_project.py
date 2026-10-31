"""Translation files for a small app: what is extracted from its models, `generate`, `gather`,
`check`, and the commands. The app is made in a temporary directory."""

import sys
import textwrap
from types import SimpleNamespace

import pytest
from pangloss_core import settings as core_settings
from pangloss_core.settings import ClientSettings
from pangloss_interface import cli as interface_cli
from pangloss_interface import translations_cli
from pangloss_interface.i18n import files, jsonc
from pangloss_interface.i18n.check import check, failing
from pangloss_interface.i18n.extract import extract, words
from pangloss_interface.i18n.gather import gather
from pangloss_interface.i18n.generate import generate, languages_of
from pangloss_interface.i18n.renames import rename_steps
from pangloss_interface.i18n.resolve import load_layers
from pangloss_models import initialise
from pangloss_models.export import export_models
from pangloss_models.model_registry import ModelRegistry
from typer.testing import CliRunner

MODELS = '''
    from enum import Enum

    from pangloss_models.model_bases.document import Document
    from pangloss_models.model_bases.edge_model import EdgeModel
    from pangloss_models.model_bases.entity import Entity
    from pydantic import Field


    class Colour(Enum):
        """The colours of ink"""

        RED_WINE = "red"
        BLUE = "blue"


    class Person(Entity):
        """A person in the sources.

        Not a group."""

        nickname: str = Field(title="Known as", description="What they were called")
        ink: Colour


    class Student(Person):
        pass


    class Teacher(Person):
        nickname: str = Field(title="Called")


    class Certainty(EdgeModel):
        level: int


    class Note(Document):
        text: str
        by: Person
'''


@pytest.fixture(scope="module")
def app(tmp_path_factory):
    """An importable app with models, initialised; the exported models; the root of its project"""
    root = tmp_path_factory.mktemp("i18nproject")
    package = root / "i18napp"
    package.mkdir()
    (package / "__init__.py").write_text("")
    (package / "models.py").write_text(textwrap.dedent(MODELS))

    saved = core_settings.__dict__.get("SETTINGS")
    ClientSettings(
        INSTALLED_APPS=["i18napp"], DATABASE_MODULE="pangloss_sdk.databases.api"
    )
    ModelRegistry._reset()
    sys.path.insert(0, str(root))
    try:
        import i18napp.models

        initialise()
        yield SimpleNamespace(root=root, exported=export_models(), package=package)
    finally:
        sys.path.remove(str(root))
        for name in [m for m in sys.modules if m.split(".")[0] == "i18napp"]:
            del sys.modules[name]
        ModelRegistry._reset()
        if saved is None:
            core_settings.__dict__.pop("SETTINGS", None)
        else:
            core_settings.SETTINGS = saved


@pytest.fixture
def clean(app):
    """The app without translation files, before and after"""
    import shutil

    for folder in (app.package / "translations", app.root / "translations"):
        shutil.rmtree(folder, ignore_errors=True)
    yield app
    for folder in (app.package / "translations", app.root / "translations"):
        shutil.rmtree(folder, ignore_errors=True)


APPS = ["i18napp"]
LANGUAGES = ["en", "de"]


@pytest.fixture
def extracted(app):
    return extract(app.exported, APPS)


def run_generate(app, extracted, **kw):
    return generate(app.root, extracted, APPS, "en", LANGUAGES, [], **kw)


def edit_file(app, edits):
    """Change texts in the app's models.jsonc as a person would: {path: text}"""
    folder = app.package / "translations"
    loaded = files.read_models_file(folder)
    loaded.texts.update(edits)
    (folder / files.MODELS_FILE).write_text(
        files.render_models_file(loaded.texts, loaded.obsolete, loaded.state, "en")
    )


# --- words -------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("name", "member", "result"),
    [
        ("BirthRecord", False, "Birth record"),
        ("birth_place", False, "Birth place"),
        ("HTTPError", False, "HTTP error"),
        ("year", False, "Year"),
        ("RED_WINE", True, "Red wine"),
        ("Person2", False, "Person2"),
    ],
)
def test_a_name_in_code_is_written_as_words(name, member, result):
    assert words(name, member) == result


# --- extract -----------------------------------------------------------------------------------


def test_the_texts_of_the_models_come_from_names_titles_and_docstrings(extracted):
    texts = extracted.texts

    assert texts[("models", "Person", "name")] == "Person"
    assert (
        texts[("models", "Person", "description")]
        == "A person in the sources.\n\nNot a group."
    )
    assert texts[("models", "Person", "plural")] == ""
    assert texts[("models", "Person", "help")] == ""
    # a verbose name and a help text, or the name as words
    assert texts[("models", "Person", "fields", "nickname", "name")] == "Known as"
    assert (
        texts[("models", "Person", "fields", "nickname", "help")]
        == "What they were called"
    )
    assert texts[("models", "Note", "fields", "text", "name")] == "Text"
    assert texts[("models", "Note", "fields", "text", "help")] == ""


def test_a_field_is_translated_where_it_is_declared_not_again_where_it_is_inherited(
    extracted,
):
    assert ("models", "Student", "fields", "nickname", "name") not in extracted.texts
    assert extracted.field_chain["Student"]["nickname"] == ["Person"]
    assert extracted.field_chain["Person"]["nickname"] == ["Person"]


def test_a_model_that_redeclares_a_field_has_its_own_empty_texts_and_the_base_behind_them(
    extracted,
):
    assert extracted.field_chain["Teacher"]["nickname"] == ["Teacher", "Person"]
    # (empty: until a person fills them in, the base's are used)
    for key in ("name", "plural", "help"):
        assert extracted.texts[("models", "Teacher", "fields", "nickname", key)] == ""
    assert (
        extracted.texts[("models", "Person", "fields", "nickname", "name")]
        == "Known as"
    )
    # a field it does not redeclare has none of its own
    assert ("models", "Teacher", "fields", "ink", "name") not in extracted.texts


def test_models_of_every_kind_are_translated_edge_models_too(extracted):
    assert extracted.kinds == {
        "Person": "Entity",
        "Student": "Entity",
        "Teacher": "Entity",
        "Note": "Document",
        "Certainty": "EdgeModel",
    }
    assert (
        extracted.texts[("models", "Certainty", "fields", "level", "name")] == "Level"
    )


def test_incoming_relations_have_names(extracted):
    incoming = {
        p[3] for p in extracted.texts if p[:3] == ("models", "Person", "incoming")
    }
    assert incoming  # (the relation from Note.by)
    name = min(incoming)
    assert extracted.texts[("models", "Person", "incoming", name, "name")] == words(
        name
    )
    assert ("models", "Person", "incoming", name, "plural") in extracted.texts


def test_enums_and_their_members_have_names(extracted):
    assert extracted.texts[("enums", "Colour", "name")] == "Colour"
    assert extracted.texts[("enums", "Colour", "description")] == "The colours of ink"
    assert (
        extracted.texts[("enums", "Colour", "members", "RED_WINE", "name")]
        == "Red wine"
    )
    assert extracted.texts[("enums", "Colour", "members", "BLUE", "name")] == "Blue"


def test_models_of_no_installed_app_are_left_out(app):
    nothing = extract(app.exported, ["another_app"])
    assert nothing.texts == {} and nothing.apps == {}


# --- generate ----------------------------------------------------------------------------------


def test_generate_writes_the_file_of_the_app_and_the_project_overrides(
    clean, extracted
):
    done = run_generate(clean, extracted)

    [result] = done.apps
    assert result.written and result.skipped is None
    folder = clean.package / "translations"
    assert (folder / "models.jsonc").is_file() and (folder / ".state.json").is_file()
    assert {p.name for p in done.created} == {"models.jsonc", "ui.jsonc"}
    assert jsonc.loads((clean.root / "translations" / "models.jsonc").read_text()) == {}

    data = jsonc.loads((folder / "models.jsonc").read_text())
    assert data["models"]["Person"]["en"]["fields"]["nickname"] == {
        "name": "Known as",
        "plural": "",
        "help": "What they were called",
    }
    assert data["models"]["Person"]["de"]["name"] == ""
    assert "de" in data["enums"]["Colour"] and "Student" in data["models"]
    # English beside the German, for the translator
    assert "// en: Known as" in (folder / "models.jsonc").read_text()


def test_a_second_run_writes_nothing(clean, extracted):
    run_generate(clean, extracted)
    before = (clean.package / "translations" / "models.jsonc").read_text()

    done = run_generate(clean, extracted)

    assert done.apps[0].written is False and done.created == []
    assert (clean.package / "translations" / "models.jsonc").read_text() == before


def test_what_a_person_wrote_is_kept_and_a_change_in_the_model_marks_it(
    clean, extracted
):
    run_generate(clean, extracted)
    edit_file(
        clean,
        {
            ("models", "Person", "de", "name"): "Person (Mensch)",
            ("models", "Person", "en", "name"): "Person or group",
        },
    )

    # the model's name for itself changes; and the description
    changed = extract(clean.exported, APPS)
    changed.texts[("models", "Person", "name")] = "Human"
    changed.texts[("models", "Person", "description")] = "A human"
    done = run_generate(clean, changed)

    report = done.apps[0].report
    loaded = files.read_models_file(clean.package / "translations")
    assert loaded.texts[("models", "Person", "en", "name")] == "Person or group"
    assert loaded.texts[("models", "Person", "de", "name")] == "Person (Mensch)"
    assert (
        loaded.texts[("models", "Person", "en", "description")] == "A human"
    )  # (unedited: follows)
    assert ("models", "Person", "en", "name") in report.review
    text = (clean.package / "translations" / "models.jsonc").read_text()
    assert "NEEDS REVIEW: the model has changed since this was edited" in text
    assert "NEEDS REVIEW: the en text has changed since this was translated" in text


def test_dry_run_writes_nothing(clean, extracted):
    done = run_generate(clean, extracted, dry_run=True)

    assert done.apps[0].report.added and not done.apps[0].written
    assert not (clean.package / "translations").exists()
    assert not (clean.root / "translations").exists()


def test_an_app_outside_the_project_is_not_written(clean, extracted, tmp_path):
    done = generate(
        tmp_path, extracted, APPS, "en", LANGUAGES, []
    )  # (another project's root)

    assert done.apps[0].skipped and not (clean.package / "translations").exists()


def test_a_file_that_is_not_what_it_should_be_is_said_so(clean, extracted):
    folder = clean.package / "translations"
    folder.mkdir()
    (folder / "models.jsonc").write_text('{"models": {"Person": {"en": {"name": 3}}}}')
    with pytest.raises(files.TranslationFileError, match="expected a text"):
        run_generate(clean, extracted)

    (folder / "models.jsonc").write_text('{"modles": {}}')
    with pytest.raises(files.TranslationFileError, match="unexpected modles"):
        run_generate(clean, extracted)

    (folder / "models.jsonc").write_text("{nope")
    with pytest.raises(files.TranslationFileError, match="models.jsonc"):
        run_generate(clean, extracted)


# --- gather and check ------------------------------------------------------------------------


def layers_of(app, extracted):
    return load_layers(app.root, extracted, APPS, "en", LANGUAGES)


def test_gather_has_every_language_complete_with_the_fallbacks(clean, extracted):
    run_generate(clean, extracted)
    edit_file(
        clean,
        {
            ("models", "Person", "de", "name"): "Mensch",
            ("models", "Person", "de", "fields", "nickname", "name"): "Genannt",
            ("models", "Person", "de", "fields", "nickname", "plural"): "Genannte",
        },
    )

    gathered = gather(layers_of(clean, extracted))

    assert gathered["default"] == "en" and gathered["languages"] == ["en", "de"]
    en, de = gathered["models"]["en"]["Person"], gathered["models"]["de"]["Person"]
    assert de["name"] == "Mensch" and en["name"] == "Person"
    # untranslated: the default language's text; a plural that is not there is the singular
    assert de["description"] == en["description"]
    assert en["plural"] == "Person" and de["plural"] == "Mensch"
    assert de["fields"]["nickname"] == {
        "name": "Genannt",
        "plural": "Genannte",
        "help": "What they were called",
    }
    # a model has the fields it inherits, with the texts of the model that declares them
    assert (
        gathered["models"]["en"]["Student"]["fields"]["nickname"]["name"] == "Known as"
    )
    assert (
        gathered["models"]["de"]["Student"]["fields"]["nickname"]["name"] == "Genannt"
    )
    assert gathered["enums"]["de"]["Colour"]["members"]["RED_WINE"] == {
        "name": "Red wine"
    }
    assert gathered["ui"]["de"]["log_in"] == "Anmelden"
    assert gathered["models"]["en"]["Person"]["kind"] == "Entity"
    assert gathered["ui"]["de"]["kind_entity"] == "Entität"
    english = gathered["ui"]["en"]
    assert (english["title"], english["log_in"], english["log_out"]) == (
        "Pangloss",
        "Log in",
        "Log out",
    )
    # (the words of the pages, which the interface reads with `t`)
    assert english["new_item"] == "New {type}"
    assert gathered["ui"]["de"]["new_item"] == "{type} anlegen"


def test_the_projects_overrides_win_over_the_app(clean, extracted):
    run_generate(clean, extracted)
    edit_file(clean, {("models", "Person", "de", "name"): "Mensch"})
    (clean.root / "translations" / "models.jsonc").write_text(
        '{"models": {"Person": {"de": {"name": "Person (Projekt)", "plural": ""}}}}'
    )
    (clean.root / "translations" / "ui.jsonc").write_text(
        '// the project\'s own\n{"log_in": {"de": "Einloggen"}}'
    )

    gathered = gather(layers_of(clean, extracted))

    assert gathered["models"]["de"]["Person"]["name"] == "Person (Projekt)"
    assert gathered["ui"]["de"]["log_in"] == "Einloggen"
    assert gathered["ui"]["de"]["log_out"] == "Abmelden"  # (the interface's own)


def test_check_lists_what_is_missing_but_not_a_plural(clean, extracted):
    run_generate(clean, extracted)

    problems = check(layers_of(clean, extracted))

    missing = {p.where for p in problems if p.kind == "missing" and p.language == "de"}
    assert "models/Person/name" in missing
    assert "models/Person/fields/nickname/help" in missing
    assert "models/Person/description" in missing
    assert "models/Person/help" not in missing  # (nothing in English to translate)
    assert not any(p.where.endswith("/plural") for p in problems)
    assert not any(
        p.where.startswith("ui/") for p in problems
    )  # (the interface has German)
    assert failing(problems, strict=False)

    # once it is all translated, nothing is missing
    texts = {
        p: "x"
        for p in files.read_models_file(clean.package / "translations").texts
        if p[2] == "de" and p[-1] != "plural"
    }
    edit_file(clean, texts)
    assert not [p for p in check(layers_of(clean, extracted)) if p.kind == "missing"]


def test_check_only_one_language(clean, extracted):
    run_generate(clean, extracted)
    assert check(layers_of(clean, extracted), "en") == []


def test_check_reports_texts_to_review_and_names_that_point_at_nothing(
    clean, extracted
):
    run_generate(clean, extracted)
    edit_file(clean, {("models", "Person", "de", "name"): "Mensch"})
    changed = extract(clean.exported, APPS)
    changed.texts[("models", "Person", "name")] = "Human"
    run_generate(clean, changed)
    (clean.root / "translations" / "models.jsonc").write_text(
        '{"models": {"Gone": {"de": {"name": "Weg"}}}}'
    )

    problems = check(layers_of(clean, changed))

    kinds = {(p.kind, p.where) for p in problems}
    assert ("review", "models/Person/name") in kinds
    assert ("unknown", "models/Gone/name") in kinds
    assert not failing([p for p in problems if p.kind != "missing"], strict=False)
    assert failing([p for p in problems if p.kind != "missing"], strict=True)


# --- the commands -------------------------------------------------------------------------------


@pytest.fixture
def commands(app, monkeypatch):
    settings = SimpleNamespace(
        INSTALLED_APPS=APPS,
        INTERFACE_LANGUAGES=["en", "de"],
        DEFAULT_INTERFACE_LANGUAGE="en",
    )
    project = SimpleNamespace(
        location=SimpleNamespace(root=app.root),
        require_settings=lambda: settings,
        settings_error=None,
    )
    monkeypatch.setattr(interface_cli, "export_project_models", lambda p: app.exported)
    monkeypatch.setattr(translations_cli, "unmigrated", lambda apps: [])
    monkeypatch.setattr(translations_cli, "rename_steps", lambda apps: [])
    runner = CliRunner()

    def invoke(*args):
        return runner.invoke(interface_cli.cli, ["translations", *args], obj=project)

    return invoke


def test_the_commands_generate_gather_and_check(clean, commands, tmp_path):
    done = commands("generate")
    assert done.exit_code == 0, done.output
    assert "i18napp: wrote i18napp/translations/models.jsonc" in done.output
    assert "added" in done.output

    out = tmp_path / "all.json"
    done = commands("gather", "--out", str(out))
    assert done.exit_code == 0, done.output
    assert jsonc.loads(out.read_text())["models"]["de"]["Person"]["name"] == "Person"

    done = commands("check")
    assert done.exit_code == 1  # (nothing is translated into German)
    assert "missing  de     models/Person/fields/nickname/name" in done.output

    assert commands("check", "--lang", "fr").exit_code == 1
    assert commands("generate", "--app", "other").exit_code == 1


def test_generate_warns_of_changes_with_no_migration_and_strict_stops(
    clean, commands, monkeypatch
):
    monkeypatch.setattr(
        translations_cli, "unmigrated", lambda apps: ["Rename the model A to B?"]
    )

    warned = commands("generate")
    assert warned.exit_code == 0 and "no migration" in warned.output
    assert "Rename the model A to B?" in warned.output

    assert commands("generate", "--strict").exit_code == 1


def test_a_broken_file_is_a_message_not_a_traceback(clean, commands):
    folder = clean.package / "translations"
    folder.mkdir()
    (folder / "models.jsonc").write_text("{nope")

    done = commands("gather")

    assert done.exit_code == 1 and "models.jsonc" in done.output
    assert "Traceback" not in done.output


# --- what the migrations say ------------------------------------------------------------------


def test_renames_are_read_from_the_migrations_in_order(monkeypatch):
    from pangloss_interface.i18n import renames
    from pangloss_models.migrations import changes as c

    migrations = [
        SimpleNamespace(
            changes=[
                c.RenameModel(old="Person", new="Human"),
                c.RenameField(model="Human", old="birth", new="born"),
            ]
        ),
        SimpleNamespace(
            changes=[
                c.AlterReverseName(model="Note", name="by", old="by_of", new="notes"),
                c.RenameEnum(old="Colour", new="Ink"),
                c.RenameEnumMember(enum="Ink", old="RED", new="CRIMSON"),
                c.AddEnumMember(enum="Ink", member="X"),
            ]
        ),
    ]
    monkeypatch.setattr(
        renames, "graph_of", lambda apps: SimpleNamespace(order=lambda: migrations)
    )

    steps = rename_steps(APPS)

    assert [(s.old, s.new) for s in steps] == [
        (("models", "Person"), ("models", "Human")),
        (("models", "Human", "fields", "birth"), ("models", "Human", "fields", "born")),
        (("models", "*", "incoming", "by_of"), ("models", "*", "incoming", "notes")),
        (("enums", "Colour"), ("enums", "Ink")),
        (("enums", "Ink", "members", "RED"), ("enums", "Ink", "members", "CRIMSON")),
    ]


def test_the_languages_of_the_settings_have_the_default_first_once():
    settings = SimpleNamespace(
        DEFAULT_INTERFACE_LANGUAGE="en", INTERFACE_LANGUAGES=["de", "en", "de", "fr"]
    )
    assert languages_of(settings) == ("en", ["en", "de", "fr"])
    empty = SimpleNamespace(DEFAULT_INTERFACE_LANGUAGE="en", INTERFACE_LANGUAGES=[])
    assert languages_of(empty) == ("en", ["en"])


# --- a model that narrows a field -------------------------------------------------------------


def test_a_model_that_narrows_a_field_can_give_its_own_text_and_falls_back_to_the_base(
    clean, extracted
):
    run_generate(clean, extracted)
    edit_file(
        clean,
        {
            ("models", "Person", "de", "fields", "nickname", "name"): "Genannt",
            ("models", "Teacher", "en", "fields", "nickname", "name"): "Taught as",
        },
    )

    gathered = gather(layers_of(clean, extracted))

    teacher = lambda language: gathered["models"][language]["Teacher"]["fields"][
        "nickname"
    ]
    assert teacher("en")["name"] == "Taught as"
    assert teacher("en")["help"] == "What they were called"  # (not given: the base's)
    # German: the German of the base, before the English of the teacher
    assert teacher("de")["name"] == "Genannt"
    # and the model it narrows is unchanged
    assert (
        gathered["models"]["en"]["Person"]["fields"]["nickname"]["name"] == "Known as"
    )


# --- a person's comments ---------------------------------------------------------------------


def test_a_comment_a_person_wrote_is_kept_when_the_file_is_written_again(
    clean, extracted
):
    run_generate(clean, extracted)
    path = clean.package / "translations" / "models.jsonc"
    lines = path.read_text().splitlines()
    marked = []
    seen_person = False
    commented_nickname = False
    for line in lines:
        if line.strip() == '"Person": {' and not seen_person:
            seen_person = True
            marked.append("    // ask Dr Weiss about this one")
        elif seen_person and not commented_nickname and line.strip() == '"nickname": {':
            commented_nickname = True
            marked.append("          // the Heidelberg usage: see the spreadsheet")
        marked.append(line)
    assert seen_person and commented_nickname
    text = "\n".join(["// TOP: the translator is Anna", *marked]) + "\n"
    path.write_text(text)

    # (the models change, so that the file is changed, not only read)
    changed = extract(clean.exported, APPS)
    changed.texts[("models", "Person", "description")] = "A human"
    run_generate(clean, changed)

    written = path.read_text()
    assert "// ask Dr Weiss about this one\n" in written
    assert written.count("// the Heidelberg usage: see the spreadsheet") == 1
    assert "// TOP: the translator is Anna" in written.split("{")[0]
    # the comment is above the key it was above, and the generator's own comments are not doubled
    assert (
        '// the Heidelberg usage: see the spreadsheet\n          "nickname": {'
        in written
        or '// the Heidelberg usage: see the spreadsheet\n            "nickname": {'
        in written
    )
    assert written.count("// en: Known as") == 1
    assert written.count("// TOP") == 1

    # and again, with nothing changed: nothing is written
    assert run_generate(clean, changed).apps[0].written is False


def test_a_comment_that_looks_like_the_generators_is_taken_to_be_its_own(
    clean, extracted
):
    run_generate(clean, extracted)
    path = clean.package / "translations" / "models.jsonc"
    text = path.read_text().replace(
        '    "Person": {', '    // en: this is not kept\n    "Person": {', 1
    )
    path.write_text(text)
    changed = extract(clean.exported, APPS)
    changed.texts[("models", "Person", "description")] = "A human"

    run_generate(clean, changed)

    assert "this is not kept" not in path.read_text()


def test_every_kind_of_model_has_words_in_the_interfaces_own_slots():
    import re
    from pathlib import Path

    import pangloss_interface
    from pangloss_interface.i18n import files as i18n_files

    types = (
        Path(pangloss_interface.__file__).parent
        / "js/interface-core/src/types/models.ts"
    ).read_text()
    block = re.search(r"export type ModelKind =(.*?);", types, re.DOTALL)
    assert block
    kinds = re.findall(r'"(\w+)"', block.group(1))
    ui = i18n_files.read_ui_file(
        Path(pangloss_interface.__file__).parent / "translations" / "ui.jsonc"
    )
    for kind in kinds:
        key = "kind_" + re.sub(r"(?<!^)(?=[A-Z])", "_", kind).lower()
        for slot in (key, f"{key}_plural"):
            assert ui[slot].get("en") and ui[slot].get("de"), slot
