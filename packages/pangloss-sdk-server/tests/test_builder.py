import json

import pytest
from pangloss_sdk_server.builder import (
    SdkBuildError,
    apps_to_ship,
    build_package,
    names_for,
)
from server_support import load_models, settings_for, write


def test_the_package_has_the_models_stubs_manifest_and_client_module(project):
    settings = settings_for()
    load_models()

    package = build_package(project, settings)

    assert set(package.files) == {
        "shop/__init__.py",
        "shop/models.py",
        "shop/models.pyi",
        "shop/helpers.py",
        "shop/py.typed",
        "shop_sdk/sync_stubs/shop/__init__.py",
        "shop_sdk/sync_stubs/shop/models.pyi",
        "shop_sdk/sync_stubs/shop/helpers.py",
        "shop_sdk/__init__.py",
        "shop_sdk/py.typed",
        "shop_sdk/manifest.json",
        "pyproject.toml",
        "README.md",
    }
    # (the models as the project wrote them)
    assert package.files["shop/models.py"] == (project / "shop/models.py").read_bytes()
    assert b"class Create" in package.files["shop/models.pyi"]
    assert "unrelated" not in " ".join(package.files)


def test_the_manifest_and_pyproject_name_the_package(project):
    settings = settings_for()
    load_models()

    package = build_package(project, settings, build_number=3)
    manifest = json.loads(package.files["shop_sdk/manifest.json"])

    assert manifest["distribution"] == "shop-sdk"
    assert manifest["module"] == "shop_sdk"
    assert manifest["apps"] == ["shop"]
    assert manifest["modules"] == ["shop", "shop.helpers", "shop.models"]
    assert manifest["version"] == "0.3"
    assert manifest["fingerprint"] == package.fingerprint
    assert manifest["requires"][0].startswith("pangloss-sdk==")
    pyproject = package.files["pyproject.toml"].decode()
    assert 'name = "shop-sdk"' in pyproject
    assert 'version = "0.3"' in pyproject
    assert '"shop", "shop_sdk"' in pyproject
    assert "pangloss-sdk==" in pyproject


def test_the_fingerprint_is_stable_and_follows_the_content_not_the_build_number(
    project,
):
    settings = settings_for()
    load_models()

    first = build_package(project, settings, build_number=1)
    again = build_package(project, settings, build_number=7)
    assert first.fingerprint == again.fingerprint

    write(project, {"shop/helpers.py": "SHOUT = 'hello'\n"})
    assert build_package(project, settings).fingerprint != first.fingerprint


def test_dependencies_of_the_models_are_requirements(project):
    write(project, {"shop/helpers.py": "import zstandard\nSHOUT = 'x'\n"})
    load_models()
    requires = build_package(project, settings_for()).manifest["requires"]
    assert "zstandard" in requires
    assert not any(r.startswith("pydantic") for r in requires)

    extra = build_package(project, settings_for(SDK_EXTRA_REQUIREMENTS=["httpx2>=2"]))
    assert "httpx2>=2" in extra.manifest["requires"]


def test_an_import_with_no_known_package_is_an_error(project):
    write(project, {"shop/helpers.py": "import not_installed_anywhere\nSHOUT = 1\n"})
    with pytest.raises(SdkBuildError, match="not known") as error:
        build_package(project, settings_for())
    assert "not_installed_anywhere" in error.value.problems[0]


def test_what_cannot_be_shipped_is_an_error_with_the_reasons(project):
    write(project, {"shop/helpers.py": "import neo4j\nSHOUT = 1\n"})
    with pytest.raises(SdkBuildError) as error:
        build_package(project, settings_for())
    assert "neo4j" in error.value.problems[0]


def test_apps_are_chosen_by_the_settings(project):
    write(
        project,
        {
            "other/__init__.py": "",
            "other/models.py": "X = 1\n",
            "nomodels/__init__.py": "",
        },
    )
    installed = ["shop", "other", "nomodels", "pangloss_history", "missing"]

    assert apps_to_ship(project, installed, settings_for()) == ["shop", "other"]
    assert apps_to_ship(project, installed, settings_for(SDK_APPS=["shop"])) == ["shop"]
    assert apps_to_ship(
        project, installed, settings_for(SDK_EXCLUDE_APPS=["shop"])
    ) == ["other"]


def test_nothing_to_ship_is_an_error(project):
    with pytest.raises(SdkBuildError, match="nothing to ship"):
        build_package(project, settings_for(SDK_APPS=[]))


def test_the_name_can_be_set():
    assert names_for("My_Project") == ("my-project-sdk", "my_project_sdk")
    assert names_for("x", settings_for(SDK_NAME="Other.Name")) == (
        "other-name",
        "other_name",
    )
