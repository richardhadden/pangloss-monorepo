"""What an installed app requires of the storage backend (`requires = {...}` in its package) is checked at start-up"""

import sys
import types

import pytest
from pangloss_core.storage import (
    Capabilities,
    PanglossStorageError,
    Storage,
    check_requirements,
)


@pytest.fixture
def project(monkeypatch):
    """Settings for a project on one of two backends (one runs Cypher), with some of three apps installed"""
    backends = types.ModuleType("requirements_backends")
    backends.plain = Storage(name="plain", package="nowhere")  # ty: ignore[unresolved-attribute]
    backends.cypher = Storage(  # ty: ignore[unresolved-attribute]
        name="cypher", package="nowhere", capabilities=Capabilities(cypher=True)
    )
    monkeypatch.setitem(sys.modules, "requirements_backends", backends)
    for name, requires in (
        ("needs_cypher", {"cypher"}),
        ("needs_nothing", None),
        ("needs_a_typo", {"cyper"}),
    ):
        app = types.ModuleType(name)
        if requires is not None:
            app.requires = requires  # ty: ignore[unresolved-attribute]
        monkeypatch.setitem(sys.modules, name, app)

    def settings(storage: str, *apps: str):
        return types.SimpleNamespace(
            STORAGE=f"requirements_backends:{storage}", INSTALLED_APPS=list(apps)
        )

    return settings


def test_an_app_that_needs_cypher_is_refused_by_a_backend_without_it(project):
    with pytest.raises(
        PanglossStorageError,
        match="needs_cypher needs a storage backend with cypher, which 'plain' does not have",
    ):
        check_requirements(project("plain", "needs_nothing", "needs_cypher"))


def test_an_app_that_needs_cypher_runs_on_a_backend_with_it(project):
    check_requirements(project("cypher", "needs_nothing", "needs_cypher"))


def test_an_app_that_requires_nothing_runs_anywhere(project):
    check_requirements(project("plain", "needs_nothing"))


def test_a_requirement_that_is_no_capability_is_reported(project):
    with pytest.raises(PanglossStorageError, match="cyper, which is not a capability"):
        check_requirements(project("cypher", "needs_a_typo"))
