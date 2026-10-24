"""The stubs of the SDK: async and blocking, and checked with `ty` before they are published"""

import pytest
from pangloss_sdk_server import typecheck
from pangloss_sdk_server.builder import SYNC_STUBS, SdkBuildError, build_package
from pangloss_sdk_server.publish import shipped_models, write_files
from server_support import load_models, settings_for

needs_ty = pytest.mark.skipif(typecheck.find_ty() is None, reason="ty is not installed")


@pytest.fixture
def package(project, tmp_path):
    settings = settings_for()
    load_models()
    built = build_package(project, settings)
    directory = tmp_path / "package"
    write_files(directory, built.files)
    models = shipped_models(project, set(built.manifest["modules"]))
    return built, directory, models


def test_the_stub_next_to_the_models_is_async_and_the_other_is_blocking(package):
    built, _, _ = package
    asynchronous = built.files["shop/models.pyi"].decode()
    blocking = built.files[f"shop_sdk/{SYNC_STUBS}/shop/models.pyi"].decode()

    assert "async def get(cls, id: _pg_uuid.UUID" in asynchronous
    assert "async def save(self" in asynchronous
    assert "async def" not in blocking
    assert "def get(cls, id: _pg_uuid.UUID" in blocking and "def save(self" in blocking
    # (an entity can be got for editing; a document cannot)
    assert "get_for_edit" in blocking
    assert blocking.count("get_for_edit") == asynchronous.count("get_for_edit")


def test_a_model_with_a_method_called_list_does_not_shadow_the_type_list(package):
    built, _, _ = package
    stub = built.files["shop/models.pyi"].decode()
    assert "def list(cls" in stub
    # (the model's own fields that are lists name the builtin)
    assert (
        "_pg_builtins.list[" in stub
        or "list[" not in stub.split("class Person", 1)[1].split("class ", 1)[0]
    )


def test_the_blocking_directory_has_every_module_so_that_a_checker_takes_it_whole(
    package,
):
    built, _, _ = package
    shipped = {p for p in built.files if p.startswith(f"shop_sdk/{SYNC_STUBS}/")}
    assert shipped == {
        f"shop_sdk/{SYNC_STUBS}/shop/__init__.py",
        f"shop_sdk/{SYNC_STUBS}/shop/helpers.py",
        f"shop_sdk/{SYNC_STUBS}/shop/models.pyi",
    }


@needs_ty
def test_both_kinds_of_stub_type_check(package):
    built, directory, models = package
    assert (
        typecheck.check_types(directory, built.manifest["module"], models, "required")
        is None
    )


@needs_ty
def test_a_stub_with_the_wrong_type_is_an_error_that_names_the_kind(package):
    built, directory, models = package
    path = directory / "shop_sdk" / SYNC_STUBS / "shop" / "models.pyi"
    # (the blocking `get` made to say what the async one says)
    path.write_text(
        path.read_text().replace("    def get(cls", "    async def get(cls", 1)
    )

    with pytest.raises(SdkBuildError) as error:
        typecheck.check_types(directory, built.manifest["module"], models, "required")
    assert "do not type-check" in str(error.value)
    assert any(line.startswith("[sync]") for line in error.value.problems)
    assert not any(line.startswith("[async]") for line in error.value.problems)


@needs_ty
def test_a_stub_that_is_not_python_is_an_error(package):
    built, directory, models = package
    (directory / "shop" / "models.pyi").write_text("class Person(:\n")
    with pytest.raises(SdkBuildError):
        typecheck.check_types(directory, built.manifest["module"], models, "required")


def test_without_ty_auto_says_so_required_fails_and_off_does_not_look(
    package, monkeypatch
):
    built, directory, models = package
    monkeypatch.setattr(typecheck, "find_ty", lambda: None)

    note = typecheck.check_types(directory, built.manifest["module"], models, "auto")
    assert note is not None and "not type-checked" in note
    assert (
        typecheck.check_types(directory, built.manifest["module"], models, "off")
        is None
    )
    with pytest.raises(SdkBuildError, match="not installed"):
        typecheck.check_types(directory, built.manifest["module"], models, "required")
