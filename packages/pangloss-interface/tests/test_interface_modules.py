"""Interface modules: found, made, copied into the working directory, and checked against the models"""

import json
import shutil
import sys
from types import SimpleNamespace

import pytest
from pangloss_interface import cli as interface_cli
from pangloss_interface.modules import InterfaceModule, Manifest, discover, problems
from pangloss_interface.runtime import find_runtime
from pangloss_interface.scaffold import module_files
from pangloss_interface.workspace import prepare, working_directory
from typer.testing import CliRunner

runner = CliRunner()


@pytest.fixture
def apps(tmp_path, monkeypatch):
    """Two apps in a temporary directory: `withmod` has an interface module, `plain` does not"""
    for name in ("withmod", "plain"):
        package = tmp_path / "src" / name
        package.mkdir(parents=True)
        (package / "__init__.py").write_text("")
    monkeypatch.syspath_prepend(str(tmp_path / "src"))
    yield tmp_path / "src"
    for name in [n for n in sys.modules if n.split(".")[0] in ("withmod", "plain")]:
        del sys.modules[name]


def make_module(app_directory, app="withmod"):
    for name, text in module_files(app).items():
        path = app_directory / app / "interface" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)


def test_scaffold_files_are_for_the_app_and_have_the_peer_versions():
    files = module_files("my_app")
    assert set(files) >= {
        "package.json",
        "tsconfig.json",
        "README.md",
        "src/index.ts",
        "src/components/ExampleCard.tsx",
        "src/components/ExampleCard.test.tsx",
    }
    package = json.loads(files["package.json"])
    assert package["name"] == "@pangloss-module/my_app"
    assert {
        "solid-js",
        "@solidjs/web",
        "@solidjs/router",
        "@pangloss/interface-core",
    } <= set(package["peerDependencies"])
    assert 'name: "my_app"' in files["src/index.ts"]
    assert "{{app}}" not in "".join(files.values())


def test_without_the_example_the_manifest_names_nothing_that_is_not_there():
    files = module_files("my_app", with_example=False)
    assert not any("ExampleCard" in name for name in files)
    assert "ExampleCard" not in files["src/index.ts"]


def test_an_app_is_found_if_it_has_the_folder_with_a_package_json(apps):
    make_module(apps)
    found = discover(["plain", "withmod", "not_installed_at_all"])
    assert [m.app for m in found] == ["withmod"]
    assert found[0].package_name == "@pangloss-module/withmod"


def manifests(**given):
    return {"withmod": Manifest(name="withmod", components=("Page", "Card"), **given)}


def exported(**meta):
    return {
        "models": {
            "Manuscript": {
                "interfaceMeta": {
                    "colour": None,
                    "listPage": None,
                    "itemPage": None,
                    "viewCard": None,
                    "editCard": None,
                    **meta,
                }
            }
        }
    }


@pytest.fixture
def module(tmp_path):
    (tmp_path / "package.json").write_text(
        json.dumps({"peerDependencies": {"@pangloss/interface-core": "*"}})
    )
    return InterfaceModule("withmod", tmp_path)


def test_a_reference_to_a_component_that_exists_is_fine(module):
    ref = {"module": "withmod", "name": "Page"}
    assert problems([module], manifests(), exported(itemPage=ref)) == []


def test_a_reference_to_an_app_without_a_module_or_a_missing_key_says_so(module):
    wrong_app = problems(
        [module], manifests(), exported(itemPage={"module": "plain", "name": "Page"})
    )
    assert "Manuscript.item_page 'plain:Page'" in wrong_app[0]
    assert "pangloss interface new-module plain" in wrong_app[0]
    wrong_key = problems(
        [module], manifests(), exported(viewCard={"module": "withmod", "name": "Cardd"})
    )
    assert "'Cardd' is not in the components of withmod (Page, Card)" in wrong_key[0]


def test_a_manifest_must_carry_its_apps_name_and_be_readable(module):
    bad = {"withmod": Manifest(name="other")}
    assert "has to be the app's" in problems([module], bad, exported())[0]
    assert "could not be read" in problems([module], {}, exported())[0]


def test_routes_name_components_and_do_not_take_the_address_of_a_type(module):
    wrong = manifests(routes=({"path": "/Manuscript/chart", "component": "Nope"},))
    found = problems([module], wrong, exported())
    assert any("names component 'Nope'" in f for f in found)
    assert any("read as the type 'Manuscript'" in f for f in found)
    fine = manifests(routes=({"path": "/withmod/chart", "component": "Page"},))
    assert problems([module], fine, exported()) == []


def test_requirements_must_be_installed_and_must_not_circle(tmp_path):
    (tmp_path / "package.json").write_text(
        json.dumps({"peerDependencies": {"@pangloss/interface-core": "*"}})
    )
    a, b = InterfaceModule("a", tmp_path), InterfaceModule("b", tmp_path)
    data = {
        "a": Manifest("a", requires=("b",)),
        "b": Manifest("b", requires=("a",)),
    }
    assert any("in a circle" in f for f in problems([a, b], data, exported()))
    assert any(
        "requires 'zzz'" in f
        for f in problems([a], {"a": Manifest("a", requires=("zzz",))}, exported())
    )


def test_prepare_copies_the_modules_and_lists_them_and_forgets_those_that_go(
    apps, tmp_path
):
    make_module(apps)
    (apps / "withmod" / "interface" / "node_modules").mkdir()
    (apps / "withmod" / "interface" / "node_modules" / "x.js").write_text("")
    project_root = tmp_path / "project"
    modules = discover(["withmod"])
    prepare(project_root, {"models": {}, "enums": {}}, modules)
    directory = working_directory(project_root)
    assert (directory / "modules/withmod/src/index.ts").is_file()
    assert not (directory / "modules/withmod/node_modules").exists()
    package = json.loads((directory / "package.json").read_text())
    assert package["workspaces"][-1] == "modules/*"
    generated = (directory / "interface-app/src/generated/modules.ts").read_text()
    assert 'import module0 from "../../../modules/withmod/src/index";' in generated
    assert "modules: ModuleManifest[] = [module0]" in generated
    assert (
        '@source "../../../modules";'
        in (directory / "interface-app/src/generated/sources.css").read_text()
    )

    # (no longer installed: its files go, and the workspace is the package's again)
    prepare(project_root, {"models": {}, "enums": {}}, [])
    assert not (directory / "modules/withmod/src/index.ts").exists()
    assert (
        "modules/*"
        not in json.loads((directory / "package.json").read_text())["workspaces"]
    )
    assert "= [];" in (directory / "interface-app/src/generated/modules.ts").read_text()


def test_nothing_is_rewritten_when_nothing_has_changed(apps, tmp_path):
    make_module(apps)
    modules = discover(["withmod"])
    prepare(tmp_path, {"models": {}, "enums": {}}, modules)
    again = prepare(tmp_path, {"models": {}, "enums": {}}, modules)
    assert again.written == [] and again.removed == []


@pytest.fixture
def project(tmp_path, apps):
    settings = SimpleNamespace(INSTALLED_APPS=["withmod", "plain"])
    return SimpleNamespace(
        location=SimpleNamespace(root=tmp_path),
        require_settings=lambda: settings,
        settings_error=None,
    )


def test_new_module_makes_the_folder_and_will_not_overwrite_it(project, apps):
    first = runner.invoke(interface_cli.cli, ["new-module", "withmod"], obj=project)
    assert first.exit_code == 0, first.output
    assert (apps / "withmod/interface/src/index.ts").is_file()
    assert 'InterfaceMeta(view_card="withmod:ExampleCard")' in first.output
    again = runner.invoke(interface_cli.cli, ["new-module", "withmod"], obj=project)
    assert again.exit_code != 0 and "exists" in again.output
    # --force writes only what is missing
    (apps / "withmod/interface/src/index.ts").write_text("// mine\n")
    (apps / "withmod/interface/README.md").unlink()
    runner.invoke(interface_cli.cli, ["new-module", "withmod", "--force"], obj=project)
    assert (apps / "withmod/interface/src/index.ts").read_text() == "// mine\n"
    assert (apps / "withmod/interface/README.md").is_file()


def test_new_module_refuses_an_app_that_is_not_installed(project):
    result = runner.invoke(interface_cli.cli, ["new-module", "nope"], obj=project)
    assert result.exit_code != 0 and "INSTALLED_APPS" in result.output


@pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")
def test_the_manifests_are_read_through_vite_in_node(apps, tmp_path):
    """A real run: a module made by `new-module` is copied into the working directory and its
    manifest read by Vite's loader (needs the packages installed in the package's `js/`)"""
    from pangloss_interface.modules import read_manifests
    from pangloss_interface.paths import JS_ROOT

    if not (JS_ROOT / "node_modules").is_dir():
        pytest.skip("the packages are not installed: npm install in js/")
    make_module(apps)
    modules = discover(["withmod"])
    # (the package's own workspace is the working directory, with the module beside it)
    directory = tmp_path / "work"
    shutil.copytree(
        JS_ROOT,
        directory,
        ignore=shutil.ignore_patterns("dist", "node_modules"),
    )
    shutil.copytree(apps / "withmod" / "interface", directory / "modules" / "withmod")
    (directory / "node_modules").symlink_to(JS_ROOT / "node_modules")
    found = read_manifests(find_runtime(), directory, modules)
    assert found["withmod"].name == "withmod"
    assert found["withmod"].components == ("ExampleCard",)


def test_npm_ranges_as_peer_dependencies_are_understood():
    from pangloss_interface.modules import satisfies

    yes = [
        ("0.1.0", "*"),
        ("0.1.4", "^0.1.0"),
        ("0.1.0", "~0.1.0"),
        ("1.4.0", "^1.2.0"),
        ("0.1.0", ">=0.1.0"),
        ("0.1.0", ">=0.0.5 <0.2.0"),
        ("0.1.0", "0.1.x"),
        ("0.1.0", "^0.2.0 || ^0.1.0"),
        ("0.1.0", "0.1.0"),
    ]
    no = [
        ("0.2.0", "^0.1.0"),
        ("0.1.0", "^0.2.0"),
        ("2.0.0", "^1.2.0"),
        ("0.1.0", ">0.1.0"),
        ("0.1.0", "<0.1.0"),
        ("0.1.0", "0.2.x"),
        ("0.3.0", "~0.1.0"),
        ("0.0.4", "^0.0.3"),
    ]
    for version, wanted in yes:
        assert satisfies(version, wanted), (version, wanted)
    for version, wanted in no:
        assert not satisfies(version, wanted), (version, wanted)


def test_a_module_that_does_not_fit_this_version_of_the_library_is_reported(tmp_path):
    (tmp_path / "package.json").write_text(
        json.dumps({"peerDependencies": {"@pangloss/interface-core": "^9.0.0"}})
    )
    module = InterfaceModule("withmod", tmp_path)
    found = problems([module], manifests(), exported(), interface_version="0.1.0")
    assert "needs @pangloss/interface-core ^9.0.0, and this is 0.1.0" in found[0]
    (tmp_path / "package.json").write_text(json.dumps({"peerDependencies": {}}))
    assert (
        "no peerDependencies" in problems([module], manifests(), exported(), "0.1.0")[0]
    )


def test_a_nav_link_inside_the_interface_goes_to_a_type_or_a_module_route(tmp_path):
    (tmp_path / "package.json").write_text(
        json.dumps({"peerDependencies": {"@pangloss/interface-core": "*"}})
    )
    module = InterfaceModule("withmod", tmp_path)
    data = manifests(routes=({"path": "/withmod/month/:year", "component": "Page"},))

    def link(href, external=False):
        return {"label": "L", "href": href, "external": external}

    model = exported()
    model["nav"] = {
        "links": [
            link("/"),
            link("/Manuscript?q=x"),
            link("/withmod/month/1500"),
            link("https://example.org", external=True),
            link("/nowhere/at/all"),
        ]
    }
    found = problems([module], data, model, "0.1.0")
    assert len(found) == 1 and "'/nowhere/at/all'" in found[0]


def test_dev_link_uses_the_modules_where_they_are(apps, tmp_path):
    from pangloss_interface.workspace import prepare_linked

    make_module(apps)
    modules = discover(["withmod"])
    linked = prepare_linked(tmp_path, {"models": {}, "enums": {}}, modules)
    root = apps / "withmod" / "interface"
    assert linked.module_roots == [root]
    text = linked.modules.read_text()
    assert json.dumps(str(root / "src" / "index")) in text
    assert "modules: ModuleManifest[] = [module0]" in text
    assert f"@source {json.dumps(str(root))};" in linked.sources.read_text()
    # nothing is copied into the working directory
    assert not (working_directory(tmp_path) / "modules").exists()
