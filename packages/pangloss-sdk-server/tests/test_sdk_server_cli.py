import pytest
from pangloss_cli.project import Project, SettingsLocation
from pangloss_sdk_server.cli import cli
from typer.testing import CliRunner

from server_support import settings_for, write

runner = CliRunner()


@pytest.fixture
def run(project):
    def invoke(*args):
        obj = Project(
            settings=settings_for(),  # type: ignore[arg-type]
            location=SettingsLocation(module="shop_settings", root=project),
        )
        return runner.invoke(cli, list(args), obj=obj)

    return invoke


def test_build_status_show(run, project):
    result = run("status")
    assert result.exit_code == 1 and "has not been built" in result.output

    result = run("build")
    assert result.exit_code == 0, result.output
    assert "shop-sdk 0.1 built" in result.output
    assert "apps: shop" in result.output

    assert "unchanged" in run("build").output

    result = run("status")
    assert result.exit_code == 0 and "Up to date" in result.output

    write(project, {"shop/helpers.py": "SHOUT = 'hello'\n"})
    result = run("status")
    assert result.exit_code == 2 and "have changed" in result.output
    assert "-SHOUT = 'hey'" in run("show", "--diff").output
    assert "shop/models.pyi" in run("show").output


def test_a_build_that_cannot_be_made_says_why(run, project):
    write(project, {"shop/helpers.py": "import neo4j\nSHOUT = 1\n"})
    result = run("build")
    assert result.exit_code == 1
    assert "Cannot build the SDK" in result.output
    assert "imports `neo4j`" in result.output
