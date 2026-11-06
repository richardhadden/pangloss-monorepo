"""The entity a typology makes, where a type checker and an SDK look for it: in the module of the typology, by its
name, and in the module's stub"""

import importlib
import shutil
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest
from pangloss_core import ClientSettings
from pangloss_models import initialise, typestubs
from pangloss_typology import Typology, TypologyMeta

MODELS = """
from pangloss_models import Entity
from pangloss_typology import Typed, Typology, TypologyMeta


class RoleTypology(Typology):
    _typology_meta = TypologyMeta(name="RoleType")


class Person(Entity):
    has_type: list[Typed[RoleTypology]]
"""

USAGE = """
import uuid

from typesapp.models import Person, RoleType, RoleTypology


def use(i: uuid.UUID) -> None:
    secretary = RoleType.Create(label="Secretary", is_subtype_of=[])
    RoleTypology.Type.Create(label="Clerk", is_subtype_of=[])
    Person.Create(label="Ada", has_type=[RoleType.ReferenceSet(id=i)])
    RoleType.Create(label="Wrong", is_subtype_of=3)
    print(secretary.label)
"""


@pytest.fixture
def app(tmp_path, monkeypatch):
    package = tmp_path / "typesapp"
    package.mkdir()
    (package / "__init__.py").write_text("")
    (package / "models.py").write_text(textwrap.dedent(MODELS))
    monkeypatch.syspath_prepend(str(tmp_path))
    for name in ("typesapp", "typesapp.models"):
        sys.modules.pop(name, None)
    module = importlib.import_module("typesapp.models")
    initialise(bind_database=False)
    yield tmp_path, module
    for name in ("typesapp", "typesapp.models"):
        sys.modules.pop(name, None)


def test_the_entity_is_in_the_module_of_its_typology_by_its_name(app):
    _, module = app
    assert module.RoleType is module.RoleTypology.Type
    assert module.RoleType.__module__ == "typesapp.models"


def test_a_name_the_module_uses_for_something_else_is_left_alone():
    here = sys.modules[__name__]
    here.TakenType = "something else"
    try:

        class TakenTypology(Typology):
            _typology_meta = TypologyMeta(name="TakenType")

        assert here.TakenType == "something else"
        assert TakenTypology.Type.__name__ == "TakenType"
    finally:
        del here.TakenType


def test_the_stub_declares_the_entity_and_fields_of_its_type_name_it(app):
    root, module = app
    written, _ = typestubs.write_stubs(root)
    stub = written[0].read_text()

    assert "\nclass RoleType(pangloss_models.model_bases.entity.Entity):" in stub
    assert "    Type: typing.ClassVar[type[RoleType]]" in stub
    # (not `typing.Any`, as when the class could not be named)
    assert "has_type: list[RoleType.ReferenceSet]" in stub


@pytest.mark.skipif(
    shutil.which("ty", path=str(Path(sys.executable).parent)) is None, reason="no ty"
)
def test_a_type_checker_takes_typed_and_the_entity_and_checks_its_fields(app):
    root, _ = app
    typestubs.write_stubs(root)
    (root / "usage.py").write_text(textwrap.dedent(USAGE))
    ty = shutil.which("ty", path=str(Path(sys.executable).parent))
    assert ty is not None
    result = subprocess.run(
        [
            ty,
            "check",
            "--python",
            sys.prefix,
            "--output-format",
            "concise",
            "--ignore=unused-type-ignore-comment",
            f"--extra-search-path={root}",
            "usage.py",
            "typesapp",
        ],
        capture_output=True,
        text=True,
        cwd=root,
    )
    errors = [line for line in result.stdout.splitlines() if "error[" in line]
    # (only the wrong value: `Typed[RoleTypology]` in the module, the import of `RoleType`, `RoleTypology.Type`
    # and the reference to a type are all taken)
    assert len(errors) == 1 and "usage.py:11:" in errors[0], result.stdout


def test_the_languages_of_the_labels_are_a_setting_the_models_are_made_from():
    from pangloss_core.settings import model_setting, model_settings

    assert {"INTERFACE_LANGUAGES", "DEFAULT_INTERFACE_LANGUAGE"} <= model_settings
    # (a client has not got the server's settings: what its SDK says of them is used)
    saved = sys.modules["pangloss_core.settings"].__dict__.get("SETTINGS")
    try:
        ClientSettings(
            INSTALLED_APPS=[],
            STORAGE="pangloss_sdk.storage:api",
            MODEL_SETTINGS={"INTERFACE_LANGUAGES": ["en", "fr"]},
        )
        assert model_setting("INTERFACE_LANGUAGES", []) == ["en", "fr"]
        assert model_setting("DEFAULT_INTERFACE_LANGUAGE", "en") == "en"

        class PlaceTypology(Typology):
            _typology_meta = TypologyMeta(name="PlaceType")

        initialise(bind_database=False)
        assert "label_fr" in PlaceTypology.Type.Create.model_fields
        assert "label_de" not in PlaceTypology.Type.Create.model_fields
    finally:
        sys.modules["pangloss_core.settings"].SETTINGS = saved
