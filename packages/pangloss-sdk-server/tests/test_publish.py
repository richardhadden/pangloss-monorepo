import json

import pytest
from pangloss_sdk_server import check, publish
from pangloss_sdk_server.builder import SdkBuildError, build_package

from server_support import load_models, settings_for, write


def output_of(project):
    return project / ".pangloss/sdk"


def test_a_build_writes_the_package_and_the_state(project):
    settings = settings_for()
    load_models()

    built = publish.build(project, settings)

    assert built.changed
    directory = output_of(project) / "package"
    assert built.directory == directory
    assert (directory / "shop/models.py").is_file()
    assert (directory / "shop/models.pyi").is_file()
    assert json.loads((directory / "shop_sdk/manifest.json").read_text())["version"] == "0.1"
    state = publish.read_state(output_of(project))
    assert state["fingerprint"] == built.manifest["fingerprint"]
    assert state["number"] == 1
    # (the check leaves nothing in the package)
    assert not list(directory.rglob("__pycache__"))
    assert not (output_of(project) / ".building").exists()


def test_a_build_with_no_change_does_nothing_and_force_builds_again(project):
    settings = settings_for()
    load_models()
    publish.build(project, settings)
    marker = output_of(project) / "package/marker"
    marker.write_text("x")

    again = publish.build(project, settings)
    assert not again.changed
    assert again.manifest["version"] == "0.1"
    assert marker.exists()

    forced = publish.build(project, settings, force=True)
    assert forced.changed
    assert forced.manifest["version"] == "0.1"  # (same content: same version)
    assert not marker.exists()


def test_a_change_is_a_new_version(project):
    settings = settings_for()
    load_models()
    publish.build(project, settings)

    write(project, {"shop/helpers.py": "SHOUT = 'hello'\n"})
    built = publish.build(project, settings)

    assert built.changed
    assert built.manifest["version"] == "0.2"
    assert publish.read_state(output_of(project))["number"] == 2


def test_a_package_that_fails_the_check_leaves_the_last_build(project):
    settings = settings_for()
    load_models()
    publish.build(project, settings)
    before = (output_of(project) / "package/shop/helpers.py").read_text()

    # (fine to read, and fails when it runs on a client: the check runs it isolated)
    write(
        project,
        {"shop/helpers.py": "import sys\nif sys.flags.isolated:\n    raise RuntimeError('only on a client')\nSHOUT = 1\n"},
    )
    with pytest.raises(SdkBuildError, match="clean client") as error:
        publish.build(project, settings)

    assert "only on a client" in error.value.problems[0]
    assert (output_of(project) / "package/shop/helpers.py").read_text() == before
    assert not (output_of(project) / ".building").exists()
    assert publish.read_state(output_of(project))["number"] == 1


def test_models_that_differ_from_the_servers_fail_the_check(project, monkeypatch):
    settings = settings_for()
    load_models()
    real = check.run_in_clean_process

    def altered(directory, module):
        schemas = real(directory, module)
        schemas["Person"]["Create"]["title"] = "Something else"
        return schemas

    monkeypatch.setattr(check, "run_in_clean_process", altered)
    with pytest.raises(SdkBuildError, match="not those of the server") as error:
        publish.build(project, settings)
    assert error.value.problems == ["Person.Create: the client's model is not the server's"]


def test_the_check_sees_the_models_of_the_clean_client(project):
    settings = settings_for()
    load_models()
    package = build_package(project, settings)
    directory = project / "elsewhere"
    publish.write_files(directory, package.files)

    schemas = check.run_in_clean_process(directory, "shop_sdk")

    assert set(schemas) == {"Person", "Statement"}
    assert set(schemas["Statement"]) >= {"Create", "Update", "HeadView", "ReferenceView"}
    assert "EditView" not in schemas["Statement"]  # (a document has no edit view)


def test_the_diff_shows_what_changed_since_the_build(project):
    settings = settings_for()
    load_models()
    publish.build(project, settings)
    assert publish.diff_against_built(build_package(project, settings), output_of(project)) == []

    write(project, {"shop/helpers.py": "SHOUT = 'hello'\n"})
    lines = publish.diff_against_built(build_package(project, settings), output_of(project))
    assert "-SHOUT = 'hey'" in lines and "+SHOUT = 'hello'" in lines
