"""`git clone` of the SDK, with the real `git` against a real server (uvicorn on a free port)"""

import asyncio
import os
import shutil
import socket
import subprocess
import threading
import time
from urllib.parse import quote

import pytest
import uvicorn
from pangloss_sdk_server import current, gitrepo
from pangloss_users import service

from server_support import write
from test_serving import PASSWORD, make_app, user  # noqa: F401

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="git is not installed")


@pytest.fixture
def server(make_app):
    """The app, serving on a free port, until the test ends"""

    def start(**options):
        app = make_app(**options)
        sock = socket.socket()
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
        instance = uvicorn.Server(uvicorn.Config(app, log_level="warning"))
        thread = threading.Thread(target=instance.run, kwargs={"sockets": [sock]}, daemon=True)
        thread.start()
        deadline = time.time() + 10
        while not instance.started and time.time() < deadline:
            time.sleep(0.05)
        assert instance.started
        started.append((instance, thread, sock))
        return f"http://127.0.0.1:{port}"

    started: list = []
    yield start
    for instance, thread, sock in started:
        instance.should_exit = True
        thread.join(timeout=10)
        sock.close()


def git(*args, cwd, check=True):
    environment = {
        **os.environ,
        "GIT_TERMINAL_PROMPT": "0",
        "GIT_CONFIG_GLOBAL": "/dev/null",
        "GIT_CONFIG_NOSYSTEM": "1",
    }
    result = subprocess.run(
        ["git", "-c", "credential.helper=", *args],
        cwd=cwd,
        env=environment,
        capture_output=True,
        text=True,
    )
    if check:
        assert result.returncode == 0, result.stderr
    return result


def credentials(url: str, username="root", password=PASSWORD) -> str:
    return url.replace("http://", f"http://{quote(username, safe='')}:{quote(password, safe='')}@") + "/api/sdk/git"


def test_the_sdk_can_be_cloned_with_git(server, tmp_path):
    base = server()
    user("root", admin=True)

    git("clone", credentials(base), "sdk", cwd=tmp_path)

    clone = tmp_path / "sdk"
    assert (clone / "shop/models.py").is_file()
    assert (clone / "shop/models.pyi").is_file()
    assert (clone / "shop_sdk/manifest.json").is_file()
    assert (clone / "pyproject.toml").is_file()
    assert "shop/unrelated.py" not in git("ls-files", cwd=clone).stdout
    log = git("log", "--format=%an%n%B", cwd=clone).stdout
    assert "Pangloss" in log and "shop-sdk 0.1" in log and "fingerprint:" in log
    assert git("branch", "--show-current", cwd=clone).stdout.strip() == "main"
    assert "v0.1" in git("tag", cwd=clone).stdout
    assert "schema-" in git("tag", cwd=clone).stdout


def test_git_is_refused_without_the_right_login(server, tmp_path):
    base = server()
    user("root", admin=True)
    user("ada")

    for who, password in (("root", "wrong"), ("nobody", PASSWORD), ("ada", PASSWORD)):
        result = git("clone", credentials(base, who, password), f"c-{who}", cwd=tmp_path, check=False)
        assert result.returncode != 0, who
        assert not (tmp_path / f"c-{who}").exists() or not any((tmp_path / f"c-{who}").iterdir())


def test_a_personal_access_token_is_the_password(server, tmp_path):
    base = server()
    user("root", admin=True)
    _, token = asyncio.run(service.create_access_token("root", "git", "read"))

    git("clone", credentials(base, "root", token), "sdk", cwd=tmp_path)
    assert (tmp_path / "sdk/pyproject.toml").is_file()


def test_nothing_can_be_pushed(server, tmp_path):
    base = server()
    user("root", admin=True)
    git("clone", credentials(base), "sdk", cwd=tmp_path)
    clone = tmp_path / "sdk"
    (clone / "extra.txt").write_text("x")
    git("add", ".", cwd=clone)
    git("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-m", "x", cwd=clone)

    pushed = git("push", "origin", "main", cwd=clone, check=False)

    assert pushed.returncode != 0
    from pangloss_sdk_server import publish

    fresh = tmp_path / "again"
    git("clone", credentials(base), str(fresh), cwd=tmp_path)
    assert not (fresh / "extra.txt").exists()


def test_a_change_to_the_models_is_a_new_commit_that_git_pull_brings(server, project, tmp_path):
    base = server()
    user("root", admin=True)
    git("clone", credentials(base), "sdk", cwd=tmp_path)
    clone = tmp_path / "sdk"
    first = git("rev-parse", "HEAD", cwd=clone).stdout.strip()

    # (the models change; the next build, as the server would do it, commits)
    write(project, {"shop/helpers.py": "SHOUT = 'hello'\n"})
    from pangloss_core import settings as core_settings

    asyncio.run(current.ensure_built(core_settings.SETTINGS))

    git("pull", cwd=clone)
    second = git("rev-parse", "HEAD", cwd=clone).stdout.strip()
    assert second != first
    assert "hello" in (clone / "shop/helpers.py").read_text()
    assert git("rev-list", "--count", "HEAD", cwd=clone).stdout.strip() == "2"
    assert "v0.2" in git("tag", cwd=clone).stdout
    assert "shop-sdk 0.2" in git("log", "-1", "--format=%B", cwd=clone).stdout


def test_a_build_with_no_change_leaves_the_head_where_it_was(server, project, tmp_path):
    server()
    from pangloss_core import settings as core_settings
    from pangloss_sdk_server import config

    before = gitrepo.open_repository(
        gitrepo.repository_path(config.output_directory(project, core_settings.SETTINGS))
    ).refs.read_ref(gitrepo.BRANCH)
    asyncio.run(current.ensure_built(core_settings.SETTINGS, force=True))
    after = gitrepo.open_repository(
        gitrepo.repository_path(config.output_directory(project, core_settings.SETTINGS))
    ).refs.read_ref(gitrepo.BRANCH)
    assert before == after


def test_the_public_setting_needs_no_login(server, tmp_path):
    base = server(SDK_ACCESS="public")
    git("clone", base + "/api/sdk/git", "sdk", cwd=tmp_path)
    assert (tmp_path / "sdk/pyproject.toml").is_file()


def test_pip_installable_layout(server, tmp_path):
    """What is cloned has a pyproject with the packages named, ready for `pip install`"""
    base = server()
    user("root", admin=True)
    git("clone", credentials(base), "sdk", cwd=tmp_path)
    pyproject = (tmp_path / "sdk/pyproject.toml").read_text()
    assert 'name = "shop-sdk"' in pyproject and 'packages = ["shop", "shop_sdk"]' in pyproject
