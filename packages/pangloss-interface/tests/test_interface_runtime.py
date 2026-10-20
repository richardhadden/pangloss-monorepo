import pytest
from pangloss_interface import runtime
from pangloss_interface.runtime import InterfaceRuntimeError, choose_runtime, find_runtime


def test_node_is_the_default():
    assert choose_runtime(None, {}) == "node"


def test_the_runtime_is_chosen_by_the_option_then_the_environment():
    environment = {"PANGLOSS_INTERFACE_RUNTIME": "bun"}
    assert choose_runtime(None, environment) == "bun"
    assert choose_runtime("node", environment) == "node"


def test_an_unknown_runtime_is_refused():
    with pytest.raises(InterfaceRuntimeError, match="deno"):
        choose_runtime("deno", {})


def test_node_needs_node_and_npm(monkeypatch):
    monkeypatch.setattr(runtime.shutil, "which", lambda name: None)
    with pytest.raises(InterfaceRuntimeError, match="Node.js"):
        find_runtime("node", {})


def test_node_commands(monkeypatch):
    monkeypatch.setattr(runtime.shutil, "which", lambda name: f"/bin/{name}")
    node = find_runtime("node", {})
    assert node.install() == ["/bin/npm", "install"]
    assert node.script("build") == ["/bin/npm", "run", "build"]
    assert node.script("dev", "--port", "3001") == [
        "/bin/npm", "run", "dev", "--", "--port", "3001",
    ]


def test_bun_commands(monkeypatch):
    monkeypatch.setattr(runtime.shutil, "which", lambda name: f"/bin/{name}")
    bun = find_runtime("bun", {})
    assert bun.install() == ["/bin/bun", "install"]
    assert bun.script("build") == ["/bin/bun", "run", "build"]


def test_bun_must_be_installed(monkeypatch):
    monkeypatch.setattr(runtime.shutil, "which", lambda name: None)
    with pytest.raises(InterfaceRuntimeError, match="Bun"):
        find_runtime("bun", {})
