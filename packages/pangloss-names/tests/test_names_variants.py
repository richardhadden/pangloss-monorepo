"""The table of name variants, `NAMES_VARIANTS` (implementation_docs/similarity-build-plan.md, step 8.5): a CSV file of
canonical forms and their variants, read once, checked at `initialise()` by the file and the line, and in the name
part's signature by its content alone"""

from pathlib import Path
from types import SimpleNamespace
from typing import no_type_check

import pytest
from pangloss_core.settings import configure
from pangloss_models import Document, Entity, ModelRegistry, initialise
from pangloss_models.exceptions import PanglossInitialisationError
from pangloss_names import settings
from pangloss_names.part import PART

APPS = ["pangloss_vectors", "pangloss_fastrp", "pangloss_names"]


@no_type_check
def people():
    class Person(Entity):
        pass

    class Letter(Document):
        pass

    initialise()


def written(tmp_path: Path, text: str, name: str = "variants.csv") -> Path:
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return path


def given(path: Path | str | None) -> SimpleNamespace:
    return SimpleNamespace(NAMES_VARIANTS=path)


# -- read -----------------------------------------------------------------------------------------------------------


def test_the_forms_and_their_variants_are_read_with_blank_lines_and_comments_skipped(
    tmp_path,
):
    path = written(
        tmp_path,
        "# given names\n"
        "Johannes,Johann,Hans,Jan\n"
        "\n"
        "  # another comment\n"
        "Margaret, Margareta ,Greta\n",
    )
    assert settings.variants(given(path)) == {
        "Johannes": ["Johann", "Hans", "Jan"],
        "Margaret": ["Margareta", "Greta"],
    }


def test_the_table_the_part_makes_is_folded_each_variant_to_its_form(
    project_settings, tmp_path
):
    path = written(tmp_path, "Jóhannes,HANS,Jan\n")
    configure(project_settings(NAMES_VARIANTS=str(path)))
    assert PART.table() == {"hans": "johannes", "jan": "johannes"}


def test_a_variant_that_folds_to_its_own_form_is_left_out(tmp_path):
    path = written(tmp_path, "Johannes,JOHANNES,Hans\n")
    assert settings.variants(given(path)) == {"Johannes": ["Hans"]}


def test_a_byte_order_mark_is_no_part_of_the_first_form(tmp_path):
    path = tmp_path / "variants.csv"
    path.write_text("Johannes,Hans\n", encoding="utf-8-sig")
    assert settings.variants(given(path)) == {"Johannes": ["Hans"]}


def test_no_setting_gives_an_empty_table():
    assert settings.variants(SimpleNamespace()) == {}
    assert settings.variants(given(None)) == {}


def test_a_relative_path_is_taken_from_the_directory_of_the_settings_module(
    tmp_path, monkeypatch
):
    import sys
    import types

    written(tmp_path, "Johannes,Hans\n")
    module = types.ModuleType("names_variants_project_settings")
    module.__file__ = str(tmp_path / "settings.py")
    monkeypatch.setitem(sys.modules, module.__name__, module)
    Settings = type("Settings", (), {"__module__": module.__name__})
    project = Settings()
    project.NAMES_VARIANTS = "variants.csv"
    assert settings.variants_path(project) == tmp_path / "variants.csv"
    assert settings.variants(project) == {"Johannes": ["Hans"]}


def test_the_table_is_read_once_for_the_settings_and_again_after_a_reset(
    project_settings, tmp_path
):
    path = written(tmp_path, "Johannes,Hans\n")
    configure(project_settings(NAMES_VARIANTS=str(path)))
    assert settings.variants() == {"Johannes": ["Hans"]}
    path.write_text("Johannes,Jan\n", encoding="utf-8")
    # (remembered: the file is not read again)
    assert settings.variants() == {"Johannes": ["Hans"]}
    ModelRegistry._reset()
    assert settings.variants() == {"Johannes": ["Jan"]}


# -- refused, by the file and the line -------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "text,line,why",
    [
        ("Johannes,Hans\nMargaret\n", 2, "'Margaret' has no variant"),
        ("Johannes,Hans\n\n# x\nMargaret,\n", 4, "a cell is one word, and '' is none"),
        (
            "Johannes,Hans Peter\n",
            1,
            "a cell is one word, and 'Hans Peter' is 2 (hans peter)",
        ),
        ("Johannes Paul,Hans\n", 1, "'Johannes Paul' is 2"),
        (
            "Johannes,Jan\nJanus,Jan\n",
            2,
            "'Jan' is a variant of two canonical forms: of 'Janus' here and of 'Johannes' on line 1",
        ),
        (
            "Johannes,Hans\nHans,Hansi\n",
            1,
            "'Hans' is given as a variant of 'Johannes' and is itself a canonical form (line 2)",
        ),
        (
            "Johannes,Hans\nJOHANNES,Jan\n",
            2,
            "the canonical form 'JOHANNES' is on line 1 too",
        ),
    ],
)
def test_a_wrong_line_is_refused_by_the_file_and_its_line(tmp_path, text, line, why):
    path = written(tmp_path, text)
    with pytest.raises(PanglossInitialisationError) as refused:
        settings.variants(given(path))
    message = str(refused.value)
    assert message.startswith(f"NAMES_VARIANTS: {path}, line {line}: "), message
    assert why in message, message


def test_a_file_that_is_not_there_is_refused_by_its_path(tmp_path):
    path = tmp_path / "missing.csv"
    with pytest.raises(PanglossInitialisationError, match="there is no such file"):
        settings.variants(given(path))


def test_a_file_that_is_not_utf_8_is_refused(tmp_path):
    path = tmp_path / "variants.csv"
    path.write_bytes("Jürgen,Juergen\n".encode("latin-1"))
    with pytest.raises(PanglossInitialisationError, match="is not UTF-8"):
        settings.variants(given(path))


def test_a_setting_that_is_not_a_path_is_refused():
    with pytest.raises(PanglossInitialisationError, match="is the path of a CSV file"):
        settings.variants(given(3))  # ty: ignore[invalid-argument-type]


def test_a_wrong_table_is_refused_at_initialise_when_the_app_is_installed(
    project_settings, tmp_path
):
    path = written(tmp_path, "Johannes,Hans\nMargaret\n")
    configure(project_settings(INSTALLED_APPS=APPS, NAMES_VARIANTS=str(path)))
    with pytest.raises(PanglossInitialisationError, match=r"line 2: .* has no variant"):
        people()


def test_a_wrong_table_is_not_read_at_initialise_when_the_app_is_not_installed(
    project_settings, tmp_path
):
    path = written(tmp_path, "Margaret\n")
    configure(project_settings(NAMES_VARIANTS=str(path)))
    people()


# -- the signature ---------------------------------------------------------------------------------------------------


def signatures() -> dict[str, str]:
    from pangloss_fastrp.part import PART as GRAPH
    from pangloss_vectors.class_part import PART as CLASS

    return {
        "name": PART.signature(),
        "class": CLASS.signature(),
        "graph": GRAPH.signature(),
    }


def test_a_changed_file_changes_the_name_part_s_signature_and_no_other_s(
    project_settings, tmp_path
):
    path = written(tmp_path, "Johannes,Hans\n")
    configure(project_settings(INSTALLED_APPS=APPS, NAMES_VARIANTS=str(path)))
    people()
    before = signatures()

    path.write_text("Johannes,Hans,Jan\n", encoding="utf-8")
    ModelRegistry._reset()
    people()
    after = signatures()
    assert after["name"] != before["name"]
    assert (after["class"], after["graph"]) == (before["class"], before["graph"])


def test_a_comment_a_blank_line_the_order_or_the_case_changes_nothing(
    project_settings, tmp_path
):
    path = written(tmp_path, "Johannes,Hans,Jan\nMargaret,Greta\n")
    configure(project_settings(INSTALLED_APPS=APPS, NAMES_VARIANTS=str(path)))
    people()
    before = PART.signature()
    hashed = settings.variants_hash()

    path.write_text(
        "# the given names\n\nmargaret,GRETA\nJohannes,Jan,Hans\n", encoding="utf-8"
    )
    ModelRegistry._reset()
    people()
    assert PART.signature() == before
    assert settings.variants_hash() == hashed


def test_no_table_keeps_the_signature_of_the_empty_table(project_settings):
    """(a project with no table has the signature it had before the setting existed)"""
    from pangloss_vectors.parts import signature_of

    people()
    assert settings.variants_hash() == signature_of({})
