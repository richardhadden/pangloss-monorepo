"""`pangloss interface new-homepage`, `new-page`, and the addresses of a project's pages"""

from types import SimpleNamespace

import pytest
from pangloss_interface import cli as interface_cli
from pangloss_interface.pages import component_name, page_problems, slug_of
from pangloss_interface.paths import APP_PATH
from typer.testing import CliRunner

runner = CliRunner()


@pytest.fixture
def project(tmp_path):
    return SimpleNamespace(
        location=SimpleNamespace(root=tmp_path),
        require_settings=lambda: SimpleNamespace(INSTALLED_APPS=[]),
        settings_error=None,
    )


def invoke(project, *arguments):
    return runner.invoke(interface_cli.cli, list(arguments), obj=project)


def test_new_homepage_is_a_copy_of_the_default(project, tmp_path):
    result = invoke(project, "new-homepage")
    assert result.exit_code == 0, result.output
    assert (tmp_path / "pages" / "index.tsx").read_text() == (
        APP_PATH / "src" / "pages" / "Home.tsx"
    ).read_text()


def test_new_page_is_blank_and_named(project, tmp_path):
    result = invoke(project, "new-page", "Our Team")
    assert result.exit_code == 0, result.output
    assert "/our-team" in result.output
    text = (tmp_path / "pages" / "Our-Team.tsx").read_text()
    assert "export default function OurTeam()" in text
    assert "Our Team</h1>" in text
    assert "{{" not in text


@pytest.mark.parametrize("arguments", [("new-homepage",), ("new-page", "About")])
def test_a_file_is_not_written_over_without_force(project, tmp_path, arguments):
    assert invoke(project, *arguments).exit_code == 0
    written = next((tmp_path / "pages").iterdir())
    written.write_text("mine")
    refused = invoke(project, *arguments)
    assert refused.exit_code == 1
    assert written.read_text() == "mine"
    assert invoke(project, *arguments, "--force").exit_code == 0
    assert written.read_text() != "mine"


@pytest.mark.parametrize("name", ["1st", "a/b", "../up", "index", "Index"])
def test_names_that_cannot_be_pages(project, tmp_path, name):
    assert invoke(project, "new-page", name).exit_code == 1
    assert not (tmp_path / "pages").exists()


@pytest.mark.parametrize(
    ("stem", "slug"),
    [
        ("About", "about"),
        ("Our-Team", "our-team"),
        ("10-About", "about"),
        ("_Draft", "draft"),
        ("_10_Our_Team", "our-team"),
    ],
)
def test_addresses(stem, slug):
    assert slug_of(stem) == slug


def test_component_name():
    assert component_name("our team_now-ok") == "OurTeamNowOk"


def test_page_problems(tmp_path):
    pages = tmp_path / "pages"
    pages.mkdir()
    for name in ("index", "Person", "calendar", "About", "10-about", "Fine"):
        (pages / f"{name}.tsx").write_text("")
    wrong = page_problems(
        tmp_path,
        {"models": {"Person": {}}},
        ["/calendar/:year", "/:type"],
    )
    assert len(wrong) == 3
    joined = " ".join(wrong)
    assert "the model Person" in joined
    assert "the route /calendar/:year" in joined
    assert "pages/About.tsx" in joined or "pages/10-about.tsx" in joined
    assert not any("index" in message or "Fine" in message for message in wrong)


def test_no_pages_no_problems(tmp_path):
    assert page_problems(tmp_path, {"models": {}}, []) == []
