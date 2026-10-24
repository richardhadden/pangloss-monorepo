"""The client needs no server packages: models work with `ClientSettings` and without the
database driver (`neo4j`)."""

import subprocess
import sys
import textwrap
from importlib.metadata import PackageNotFoundError, requires

from packaging.requirements import Requirement

SERVER_ONLY = {"neo4j", "fastapi", "uvicorn", "pangloss-memgraph", "pangloss-api"}


def dependency_closure(name: str, seen: set[str] | None = None) -> set[str]:
    seen = set() if seen is None else seen
    try:
        requirements = requires(name) or []
    except PackageNotFoundError:
        return seen
    for text in requirements:
        requirement = Requirement(text)
        if requirement.marker and not requirement.marker.evaluate({"extra": ""}):
            continue
        key = requirement.name.lower().replace("_", "-")
        if key not in seen:
            seen.add(key)
            dependency_closure(key, seen)
    return seen


def test_the_sdk_does_not_depend_on_server_packages():
    assert not dependency_closure("pangloss-sdk") & SERVER_ONLY


def test_models_initialise_and_validate_without_neo4j():
    script = textwrap.dedent(
        """
        import sys

        class Blocker:
            def find_spec(self, name, path=None, target=None):
                if name == "neo4j" or name.startswith("neo4j."):
                    raise ImportError("neo4j is not installed here")

        sys.meta_path.insert(0, Blocker())

        from pangloss_core.settings import ClientSettings
        from pangloss_models import initialise
        from pangloss_models.model_bases.entity import Entity

        ClientSettings(
            INSTALLED_APPS=[], DATABASE_MODULE="pangloss_sdk.databases.api"
        )

        class Person(Entity):
            pass

        initialise()
        person = Person.Create(label="Ada")
        assert person.label == "Ada"
        assert "neo4j" not in sys.modules
        """
    )
    result = subprocess.run(
        [sys.executable, "-c", script], capture_output=True, text=True
    )
    assert result.returncode == 0, result.stderr
