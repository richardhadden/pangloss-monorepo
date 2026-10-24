"""`pangloss-sdk update`: what is run, for how the SDK was installed"""

import io
import json

import httpx2 as httpx
import pytest
from pangloss_sdk import auth, credentials, update
from pangloss_sdk import cli as sdk_cli

BASE = "http://pangloss.test"
WHEEL = f"{BASE}/api/sdk/download/demo_sdk-0.5-py3-none-any.whl"


class FakeDistribution:
    def __init__(
        self,
        name="demo-sdk",
        version="0.4",
        direct=None,
        requires=("pangloss-sdk>=0.1", "pydantic"),
    ):
        self.metadata = {"Name": name}
        self.version = version
        self.requires = list(requires)
        self._direct = direct
        self.files = []

    def read_text(self, filename):
        assert filename == "direct_url.json"
        return json.dumps(self._direct) if self._direct is not None else None


@pytest.fixture(autouse=True)
def no_terminal(monkeypatch):
    monkeypatch.setattr(auth, "can_prompt", lambda: False)
    monkeypatch.setattr(update, "can_prompt", lambda: False)
    monkeypatch.setattr(update.shutil, "which", lambda name: "/usr/bin/uv")


def server(latest="0.5", wants_login=True, accepts=("ada", "secret"), log=None):
    def handler(request: httpx.Request) -> httpx.Response:
        if log is not None:
            log.append((request.method, request.url.path))
        path = request.url.path
        if path == "/api/sdk/version":
            return httpx.Response(
                200, json={"distribution": "demo-sdk", "version": latest}
            )
        if path == "/api/users/token/refresh":
            return httpx.Response(200, json={"access_token": "fresh-access"})
        if path == "/api/sdk":
            if wants_login:
                import base64

                header = request.headers.get("authorization", "")
                good = (
                    "Basic "
                    + base64.b64encode(f"{accepts[0]}:{accepts[1]}".encode()).decode()
                )
                if header != good:
                    return httpx.Response(401)
            return httpx.Response(
                200,
                json={
                    "downloads": {
                        "wheel": f"{BASE}/api/sdk/download/demo_sdk-{latest}-py3-none-any.whl"
                    }
                },
            )
        return httpx.Response(404)

    return httpx.MockTransport(handler)


def command_of(plan: update.Plan) -> list[str]:
    assert plan.command is not None
    return plan.command


def from_server():
    return FakeDistribution(direct={"url": WHEEL, "archive_info": {}})


# --- finding the SDK -------------------------------------------------------------------------


def test_an_sdk_is_a_distribution_that_needs_pangloss_sdk(monkeypatch):
    others = [
        FakeDistribution("pangloss-sdk", requires=[]),
        FakeDistribution("pangloss-sdk-server", requires=["pangloss-sdk"]),
        FakeDistribution("pydantic", requires=["typing-extensions"]),
        FakeDistribution("Demo_SDK"),
    ]
    monkeypatch.setattr(update.metadata, "distributions", lambda: others)
    assert [d.metadata["Name"] for d in update.sdk_distributions()] == ["Demo_SDK"]


def test_choosing_needs_exactly_one_or_a_name():
    one, two = FakeDistribution("a-sdk"), FakeDistribution("b-sdk")
    assert update.choose(None, [one]) is one
    assert update.choose("B_sdk", [one, two]) is two
    with pytest.raises(update.UpdateError, match="several"):
        update.choose(None, [one, two])
    with pytest.raises(update.UpdateError, match="No Pangloss SDK"):
        update.choose(None, [])
    with pytest.raises(update.UpdateError, match="not installed"):
        update.choose("c-sdk", [one])


# --- how it was installed ---------------------------------------------------------------------


def test_an_index_install_is_upgraded_by_name():
    plan = update.make_plan(FakeDistribution())
    assert command_of(plan)[-1] == "demo-sdk" and "--upgrade" in command_of(plan)


def test_a_git_install_is_installed_again_from_the_repository():
    direct = {
        "url": f"{BASE}/api/sdk/git",
        "vcs_info": {"vcs": "git", "commit_id": "abc"},
    }
    assert (
        command_of(update.make_plan(FakeDistribution(direct=direct)))[-1]
        == f"git+{BASE}/api/sdk/git"
    )

    pinned = {
        "url": f"{BASE}/api/sdk/git",
        "vcs_info": {"vcs": "git", "requested_revision": "v0.4"},
    }
    plan = update.make_plan(FakeDistribution(direct=pinned))
    assert command_of(plan)[-1].endswith("@v0.4") and "stays there" in plan.message


def test_a_directory_install_is_left_to_the_directory():
    plan = update.make_plan(
        FakeDistribution(
            direct={"url": "file:///src/demo-sdk", "dir_info": {"editable": True}}
        )
    )
    assert (
        plan.command is None
        and "git pull" in plan.message
        and "editable" in plan.message
    )


# --- from the server's wheel -------------------------------------------------------------------


def test_the_latest_version_is_nothing_to_do():
    plan = update.make_plan(
        FakeDistribution(version="0.5", direct=from_server()._direct),
        transport=server(),
    )
    assert plan.command is None and "is the latest" in plan.message


def test_a_newer_one_is_installed_with_the_kept_login():
    credentials.save(BASE, {"token": "pgl_abc", "username": "ada"})
    plan = update.make_plan(from_server(), transport=server(accepts=("ada", "pgl_abc")))

    assert plan.message == "demo-sdk 0.4 -> 0.5"
    assert (
        command_of(plan)[-1]
        == "http://ada:pgl_abc@pangloss.test/api/sdk/download/demo_sdk-0.5-py3-none-any.whl"
    )
    # (what is shown does not have the password in it)
    assert plan.shown is not None
    assert "pgl_abc" not in plan.shown and plan.shown.endswith(
        "demo_sdk-0.5-py3-none-any.whl"
    )


def test_a_kept_refresh_token_is_exchanged_for_an_access_token_to_use_as_the_password():
    credentials.save(BASE, {"refresh_token": "r", "username": "ada"})
    plan = update.make_plan(
        from_server(), transport=server(accepts=("ada", "fresh-access"))
    )
    assert "ada:fresh-access@" in command_of(plan)[-1]


def test_with_no_kept_login_the_user_is_asked():
    asked = []

    def prompt(url, username):
        asked.append(url)
        return "ada", "secret"

    plan = update.make_plan(from_server(), transport=server(), prompt=prompt)
    assert asked == [BASE] and "ada:secret@" in command_of(plan)[-1]


def test_with_no_login_and_no_terminal_it_says_what_to_do():
    with pytest.raises(update.UpdateError, match="pangloss-sdk login"):
        update.make_plan(from_server(), transport=server())


def test_a_wrong_login_is_refused_before_anything_is_run():
    with pytest.raises(update.UpdateError, match="refused"):
        update.make_plan(
            from_server(),
            transport=server(),
            prompt=lambda url, username: ("ada", "wrong"),
        )


def test_a_server_that_gives_the_sdk_to_anyone_needs_no_login():
    plan = update.make_plan(from_server(), transport=server(wants_login=False))
    assert command_of(plan)[-1] == WHEEL and "@" not in command_of(plan)[-1]


def test_the_credentials_in_the_url_the_wheel_came_from_are_not_used_again():
    assert update.server_base(
        "http://ada:old@pangloss.test:8000/prefix/api/sdk/download/x.whl"
    ) == ("http://pangloss.test:8000/prefix")
    assert update.server_base("https://example.com/files/x.whl") is None


def test_a_different_sdk_on_the_server_is_not_installed_over_this_one():
    def handler(request):
        return httpx.Response(200, json={"distribution": "other-sdk", "version": "1.0"})

    with pytest.raises(update.UpdateError, match="not 'demo-sdk'"):
        update.make_plan(from_server(), transport=httpx.MockTransport(handler))


def test_a_server_that_cannot_be_reached_is_said_so():
    def handler(request):
        raise httpx.ConnectError("refused")

    with pytest.raises(update.UpdateError, match="could not be reached"):
        update.make_plan(from_server(), transport=httpx.MockTransport(handler))


# --- the command ---------------------------------------------------------------------------------


def test_the_command_runs_what_the_plan_says_and_dry_run_does_not(monkeypatch):
    ran = []
    monkeypatch.setattr(
        sdk_cli.subprocess,
        "run",
        lambda command, check: (
            ran.append(command) or type("R", (), {"returncode": 0})()
        ),
    )
    monkeypatch.setattr(update, "sdk_distributions", lambda: [FakeDistribution()])

    out = io.StringIO()
    assert sdk_cli.main(["update", "--dry-run"], out=out) == 0
    assert ran == [] and "$ uv pip install" in out.getvalue()

    assert sdk_cli.main(["update"], out=io.StringIO()) == 0
    assert ran and ran[0][-1] == "demo-sdk"


def test_a_problem_is_a_message_and_a_status_not_a_traceback(monkeypatch, capsys):
    monkeypatch.setattr(update, "sdk_distributions", list)
    assert sdk_cli.main(["update"], out=io.StringIO()) == 1
    assert "No Pangloss SDK" in capsys.readouterr().err


# --- stubs for the blocking SDK ----------------------------------------------------------------------


def test_sync_stubs_are_copied_to_a_directory_a_checker_uses_and_taken_away(
    tmp_path, monkeypatch, capsys
):
    from pathlib import PurePosixPath

    installed = tmp_path / "site"
    (installed / "demo_sdk/sync_stubs/demo_app").mkdir(parents=True)
    (installed / "demo_sdk/sync_stubs/demo_app/models.pyi").write_text(
        "class Person: ...\n"
    )
    (installed / "demo_sdk/sync_stubs/demo_app/__init__.py").write_text("")

    class Installed(FakeDistribution):
        def __init__(self):
            super().__init__()
            self.files = [
                PurePosixPath("demo_sdk/__init__.py"),
                PurePosixPath("demo_sdk/sync_stubs/demo_app/models.pyi"),
                PurePosixPath("demo_sdk/sync_stubs/demo_app/__init__.py"),
            ]

        def locate_file(self, path):
            return installed / path

    monkeypatch.setattr(update, "sdk_distributions", lambda: [Installed()])
    target = tmp_path / "typings"

    assert sdk_cli.main(["sync-stubs", str(target)], out=io.StringIO()) == 0
    assert (target / "demo_app/models.pyi").read_text() == "class Person: ...\n"
    assert (target / "demo_app/__init__.py").exists()
    assert not (target / "demo_sdk").exists()

    assert sdk_cli.main(["sync-stubs", str(target), "--remove"], out=io.StringIO()) == 0
    assert not (target / "demo_app/models.pyi").exists()


def test_an_sdk_without_blocking_stubs_says_so(monkeypatch, capsys):
    monkeypatch.setattr(update, "sdk_distributions", lambda: [FakeDistribution()])
    assert sdk_cli.main(["sync-stubs"], out=io.StringIO()) == 1
    assert "no blocking stubs" in capsys.readouterr().err
