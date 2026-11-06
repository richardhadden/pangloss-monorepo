"""Models declared with `pangloss_interface` (`InterfaceMeta`, `Slider`): the SDK ships them with those names from
`pangloss_sdk.no_interface`, as a client does not have the interface"""

import subprocess
import sys

import pangloss_interface
import pytest
from pangloss_core import ClientSettings
from pangloss_sdk_server import check, publish
from pangloss_sdk_server.builder import SdkBuildError, build_package
from pangloss_sdk_server.closure import closure_of
from pangloss_sdk_server.sources import STAND_IN_NAMES, shipped_source
from server_support import load_models, settings_for, write

MODELS = """
    from typing import Annotated

    from annotated_types import Ge, Le
    from pangloss_interface import (
        InterfaceMeta,
        Slider,
    )
    from pangloss_library import WeightedAlternative
    from pangloss_models import Document, Entity


    class Person(Entity):
        _interface_meta = InterfaceMeta(colour="rose")


    class Statement(Document):
        text: str
        certainty: Annotated[int, Ge(1), Le(5), Slider()]
        about: WeightedAlternative[Person]
"""


@pytest.fixture
def shown(project):
    """The project, with models that say how the interface shows them"""
    write(project, {"shop/models.py": MODELS})
    return project


def test_the_import_is_pointed_at_the_stand_in_and_nothing_else_changes():
    source = (
        "from pangloss_interface import InterfaceMeta\n"
        "from pangloss_interface.meta import (\n    Collapse,\n)\n"
        "lazy from pangloss_interface import Slider\n"
        "x = InterfaceMeta(colour='rose')  # from pangloss_interface import this\n"
    )
    assert shipped_source(source) == (
        "from pangloss_sdk.no_interface import InterfaceMeta\n"
        "from pangloss_sdk.no_interface import (\n    Collapse,\n)\n"
        "lazy from pangloss_sdk.no_interface import Slider\n"
        "x = InterfaceMeta(colour='rose')  # from pangloss_interface import this\n"
    )


def test_the_stand_in_has_the_names_the_builder_lets_through():
    import pangloss_sdk.no_interface as stand_in

    assert set(STAND_IN_NAMES) == set(stand_in.__all__)
    assert set(STAND_IN_NAMES) <= set(pangloss_interface.__all__)
    # (here the interface is installed: they are the real ones)
    assert stand_in.InterfaceMeta is pangloss_interface.InterfaceMeta


def test_models_declared_with_the_interface_are_not_a_problem(shown):
    assert not closure_of(shown, ["shop.models"]).problems


def test_a_name_that_is_not_for_models_is_a_problem_that_says_which(project):
    write(
        project,
        {
            "shop/helpers.py": "from pangloss_interface import NavLink, InterfaceMeta\nSHOUT = 1\n"
        },
    )
    problems = closure_of(project, ["shop.models"]).problems
    assert len(problems) == 1
    assert "NavLink of `pangloss_interface` cannot be shipped" in problems[0]
    assert "helpers.py:1" in problems[0]


def test_importing_the_module_itself_is_a_problem(project):
    write(project, {"shop/helpers.py": "import pangloss_interface\nSHOUT = 1\n"})
    problems = closure_of(project, ["shop.models"]).problems
    assert len(problems) == 1
    assert "import the names" in problems[0]
    with pytest.raises(SdkBuildError):
        build_package(project, settings_for())


def test_the_package_and_its_stubs_do_not_name_the_interface(shown):
    load_models()
    package = build_package(shown, settings_for())

    for name in (
        "shop/models.py",
        "shop/models.pyi",
        "shop_sdk/sync_stubs/shop/models.pyi",
    ):
        text = package.files[name].decode()
        assert "pangloss_interface" not in text, name
        assert "from pangloss_sdk.no_interface import" in text, name
    # (the rest as the project wrote it)
    assert '_interface_meta = InterfaceMeta(colour="rose")' in (
        package.files["shop/models.py"].decode()
    )


def test_the_sdk_builds_and_passes_the_check_on_a_client_without_the_interface(shown):
    load_models()

    built = publish.build(shown, settings_for())

    assert built.changed
    # (the check ran in a process where `pangloss_interface` cannot be imported; again, to see what it made)
    schemas = check.run_in_clean_process(built.directory, "shop_sdk")
    assert set(schemas) == {"Person", "Statement"}
    assert "certainty" in schemas["Statement"]["Create"]["properties"]


def test_without_the_interface_the_stand_ins_take_anything_and_the_slot_is_a_slot(
    tmp_path,
):
    script = """
import sys

class Blocker:
    def find_spec(self, name, path=None, target=None):
        if name.split(".")[0] == "pangloss_interface":
            raise ImportError("a client does not have " + name)

sys.meta_path.insert(0, Blocker())

from typing import Annotated
from pangloss_core import ClientSettings
ClientSettings(INSTALLED_APPS=[], STORAGE="pangloss_sdk.storage:api")
from pangloss_models import Entity, initialise
from pangloss_sdk.no_interface import Collapse, Colour, InterfaceMeta, Slider
import pangloss_library

class Thing(Entity):
    _interface_meta = InterfaceMeta(colour="rose", collapse=Collapse(blocking=["x"]), anything=1)
    size: Annotated[int, Slider(unit="%")]

class Smaller(Thing):
    pass

initialise()
assert type(Thing._interface_meta).__name__ == "InterfaceMeta"
assert type(Smaller._interface_meta).__name__ == "InterfaceMeta"
assert pangloss_library.WeightedAlternative._interface_meta is None
assert Thing.Create(label="a", size=3).size == 3
print("fine")
"""
    result = subprocess.run(
        [sys.executable, "-c", script], capture_output=True, text=True, cwd=tmp_path
    )
    assert result.returncode == 0, result.stderr[-2000:]
    assert result.stdout.strip() == "fine"


def test_the_settings_the_models_are_made_from_go_to_the_client_in_the_manifest(
    project, monkeypatch
):
    from pangloss_core import settings as core_settings

    # (a model that has a field for each of a setting's values, as a type of `pangloss-typology` has a label
    # for each language)
    write(
        project,
        {
            "shop/models.py": """
                from pangloss_core.settings import model_setting
                from pangloss_models import Entity


                class Person(Entity):
                    __annotations__ = {
                        f"name_{code}": "str | None" for code in model_setting("SHOP_LANGUAGES", [])
                    }
                    locals().update({f"name_{code}": None for code in model_setting("SHOP_LANGUAGES", [])})
            """
        },
    )
    monkeypatch.setattr(core_settings, "model_settings", {"SHOP_LANGUAGES"})
    settings = settings_for(SHOP_LANGUAGES=["de", "fr"])
    # (the server's settings, for the models made here: the fixture makes new ones for the next test)
    ClientSettings(
        INSTALLED_APPS=[],
        STORAGE="pangloss_sdk.storage:api",
        MODEL_SETTINGS={"SHOP_LANGUAGES": ["de", "fr"]},
    )
    load_models()

    built = publish.build(project, settings)

    assert built.manifest["model_settings"] == {"SHOP_LANGUAGES": ["de", "fr"]}
    # (the check passed: the client, with only the manifest, made the same `Person`)
    schemas = check.run_in_clean_process(built.directory, "shop_sdk")
    assert {"nameDe", "nameFr"} <= set(schemas["Person"]["Create"]["properties"])


def test_the_models_of_a_package_the_project_builds_on_are_compared_and_not_missed(
    shown,
):
    """The client has `WeightedAlternative`'s package, and may have head models from such a package (`ZoteroBacked`):
    they are not "models the server does not have" """
    server = {"Person": {"Create": {"a": 1}}, "Elsewhere": {"Create": {"b": 2}}}
    assert check.differences(server, {"Person": {"Create": {"a": 1}}}) == [
        "Elsewhere: the server has it, the SDK does not"
    ]
