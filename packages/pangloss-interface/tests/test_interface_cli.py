import json
from types import SimpleNamespace

import pytest
from pangloss_interface import cli as interface_cli
from pangloss_interface import runtime as runtime_module
from pangloss_interface.workspace import TRANSLATIONS_PATH, working_directory
from typer.testing import CliRunner

runner = CliRunner()

EXPORTED = {
    "models": {"Person": {"name": "Person", "kind": "Entity", "fields": []}},
    "enums": {},
}


SETTINGS = SimpleNamespace(
    INSTALLED_APPS=[], INTERFACE_LANGUAGES=["en", "de"], DEFAULT_INTERFACE_LANGUAGE="en"
)


@pytest.fixture
def project(tmp_path):
    return SimpleNamespace(
        location=SimpleNamespace(root=tmp_path),
        require_settings=lambda: SETTINGS,
        settings_error=None,
    )


@pytest.fixture
def commands(monkeypatch):
    """The commands that would be run, instead of running them; and the export of the
    models (which would need a project)"""
    ran = []
    monkeypatch.setattr(runtime_module.shutil, "which", lambda name: f"/bin/{name}")
    monkeypatch.setattr(
        interface_cli,
        "run",
        lambda command, cwd, environment=None: (
            ran.append((command, cwd, environment)) or 0
        ),
    )
    monkeypatch.setattr(
        interface_cli, "export_project_models", lambda project: EXPORTED
    )
    return ran


def invoke(project, *args):
    return runner.invoke(interface_cli.cli, list(args), obj=project)


def test_install_prepares_the_project_directory(commands, project):
    result = invoke(project, "install")
    assert result.exit_code == 0, result.output
    directory = working_directory(project.location.root)
    assert commands == [(["/bin/npm", "install"], directory, None)]

    # the package's JavaScript is there, with the definitions of the models
    assert (directory / "package.json").is_file()
    assert (directory / "interface-core" / "src" / "index.ts").is_file()
    models = (
        directory / "interface-app" / "src" / "generated" / "models.ts"
    ).read_text()
    assert 'export type ModelName = "Person";' in models
    assert "export const definitions: ModelDefinitions" in models
    # ... and not what is built or installed
    assert not (directory / "node_modules").exists()
    assert (directory / ".gitignore").read_text().startswith("node_modules")


def test_build_installs_if_needed_and_builds_in_the_app(commands, project):
    result = invoke(project, "build")
    assert result.exit_code == 0, result.output
    directory = working_directory(project.location.root)
    assert [c[0] for c in commands] == [
        ["/bin/npm", "install"],
        ["/bin/npm", "run", "build"],
    ]
    assert commands[1][1] == directory / "interface-app"

    # (not again, once installed)
    (directory / "node_modules").mkdir()
    commands.clear()
    assert invoke(project, "build").exit_code == 0
    assert [c[0] for c in commands] == [["/bin/npm", "run", "build"]]


def test_the_models_are_exported_before_it_is_built(commands, project, monkeypatch):
    seen = []

    def run_checking(command, cwd, environment=None):
        models = cwd / "src" / "generated" / "models.ts"
        seen.append(models.is_file() and "Person" in models.read_text())
        return 0

    monkeypatch.setattr(interface_cli, "run", run_checking)
    working_directory(project.location.root).joinpath("node_modules").mkdir(
        parents=True
    )
    assert invoke(project, "build").exit_code == 0
    assert seen == [True]


def test_dev_passes_on_the_api_url(commands, project):
    directory = working_directory(project.location.root)
    (directory / "node_modules").mkdir(parents=True)
    result = invoke(project, "dev", "--api-url", "http://api:9000", "--port", "3001")
    assert result.exit_code == 0, result.output
    assert commands == [
        (
            ["/bin/npm", "run", "dev", "--", "--port", "3001"],
            directory / "interface-app",
            {"PANGLOSS_API_URL": "http://api:9000"},
        )
    ]


def test_serve_needs_a_build(commands, project):
    result = invoke(project, "serve")
    assert result.exit_code == 1
    assert "pangloss interface build" in result.output

    entry = (
        working_directory(project.location.root) / "interface-app/dist/server/node.js"
    )
    entry.parent.mkdir(parents=True)
    entry.write_text("")
    assert (
        invoke(project, "serve", "--host", "0.0.0.0", "--port", "8080").exit_code == 0
    )
    command, cwd, environment = commands[-1]
    assert command == ["/bin/node", str(entry)]
    assert environment == {"HOST": "0.0.0.0", "PORT": "8080"}


def test_export_models_prints_or_writes(commands, project, tmp_path):
    result = invoke(project, "export-models", "--format", "json")
    assert json.loads(result.output) == EXPORTED

    result = invoke(project, "export-models")
    assert "export const definitions" in result.output

    target = tmp_path / "out.json"
    assert (
        invoke(
            project, "export-models", "--format", "json", "-o", str(target)
        ).exit_code
        == 0
    )
    assert json.loads(target.read_text()) == EXPORTED
    assert invoke(project, "export-models", "--format", "xml").exit_code == 1
    assert commands == []


def test_a_project_is_needed(commands):
    for obj in (
        None,
        SimpleNamespace(location=None, settings_error="No settings found"),
    ):
        result = invoke(obj, "build")
        assert result.exit_code == 1
        assert "No" in result.output
    assert commands == []


def test_a_failing_command_fails(project, monkeypatch):
    monkeypatch.setattr(runtime_module.shutil, "which", lambda name: f"/bin/{name}")
    monkeypatch.setattr(interface_cli, "run", lambda *args, **kwargs: 3)
    monkeypatch.setattr(
        interface_cli, "export_project_models", lambda project: EXPORTED
    )
    assert invoke(project, "install").exit_code == 3


def test_a_missing_runtime_is_explained(project, monkeypatch):
    monkeypatch.setattr(runtime_module.shutil, "which", lambda name: None)
    result = invoke(project, "install")
    assert result.exit_code == 1
    assert "Node.js" in result.output


def test_dev_link_runs_the_package_source_with_the_projects_models(
    commands, project, monkeypatch
):
    from pangloss_interface.paths import APP_PATH, JS_ROOT

    monkeypatch.setattr(interface_cli, "is_source_checkout", lambda: True)
    monkeypatch.setattr(interface_cli, "installed", lambda directory: True)
    result = invoke(project, "dev", "--link", "--api-url", "http://api:9000")
    assert result.exit_code == 0, result.output

    linked = working_directory(project.location.root) / "linked"
    models = linked / "models.ts"
    assert 'export type ModelName = "Person";' in models.read_text()
    assert commands == [
        (
            ["/bin/npm", "run", "dev", "--", "--port", "3000"],
            APP_PATH,
            {
                "PANGLOSS_API_URL": "http://api:9000",
                "PANGLOSS_MODELS_MODULE": str(models),
                "PANGLOSS_MODULES_MODULE": str(linked / "modules.ts"),
                "PANGLOSS_SOURCES_CSS": str(linked / "sources.css"),
                "PANGLOSS_MODULE_ROOTS": "",
            },
        )
    ]
    assert "= [];" in (linked / "modules.ts").read_text()
    # nothing is copied: the source of the package is what runs
    assert not (working_directory(project.location.root) / "interface-core").exists()
    assert JS_ROOT.is_dir()


def test_dev_link_needs_the_source(commands, project, monkeypatch):
    monkeypatch.setattr(interface_cli, "is_source_checkout", lambda: False)
    result = invoke(project, "dev", "--link")
    assert result.exit_code == 1
    assert "editable install" in result.output
    assert commands == []


def test_info_says_what_is_there_and_what_will_run_it(commands, project):
    before = invoke(project, "info")
    assert before.exit_code == 0, before.output
    assert "Prepared:   no" in before.output and "Built:      no" in before.output
    assert "Runtime:    node (/bin/node)" in before.output

    invoke(project, "install")
    directory = working_directory(project.location.root)
    (directory / "node_modules").mkdir()
    (directory / "interface-app/dist/server").mkdir(parents=True)
    (directory / "interface-app/dist/server/node.js").write_text("")
    after = invoke(project, "info").output
    assert (
        "Prepared:   yes" in after
        and "Installed:  yes" in after
        and "Built:      yes" in after
    )


def test_check_type_checks_with_the_models_and_checks_the_layers(commands, project):
    result = invoke(project, "check")
    assert result.exit_code == 0, result.output
    directory = working_directory(project.location.root)
    assert [c[0] for c in commands] == [
        ["/bin/npm", "install"],
        ["/bin/npm", "run", "typecheck"],
        ["/bin/npm", "run", "check:layers"],
    ]
    assert all(c[1] == directory for c in commands)
    # (with the project's models in place)
    assert (
        'ModelName = "Person"'
        in (directory / "interface-app/src/generated/models.ts").read_text()
    )


def test_models_that_cannot_be_initialised_are_explained(
    commands, project, monkeypatch
):
    from pangloss_models.exceptions import PanglossInitialisationError

    def broken(project):
        raise PanglossInitialisationError("Person.friend: no such model")

    monkeypatch.setattr(interface_cli, "export_project_models", broken)
    result = invoke(project, "build")
    assert result.exit_code == 1
    assert "Cannot initialise the models: Person.friend: no such model" in result.output


def test_the_translations_are_gathered_when_the_interface_is_prepared(
    commands, project
):
    result = invoke(project, "install")
    assert result.exit_code == 0, result.output

    gathered = working_directory(project.location.root) / TRANSLATIONS_PATH
    data = json.loads(gathered.read_text())
    assert data["languages"] == ["en", "de"]
    assert data["ui"]["de"]["log_in"] == "Anmelden"
    assert "wrote translations.json" in result.output


def test_translations_that_cannot_be_read_are_a_warning_and_the_interface_goes_on(
    commands, project
):
    folder = project.location.root / "translations"
    folder.mkdir()
    (folder / "models.jsonc").write_text("{nope")

    result = invoke(project, "install")

    assert result.exit_code == 0
    assert "Translations not gathered" in result.output
    assert not (working_directory(project.location.root) / TRANSLATIONS_PATH).exists()
