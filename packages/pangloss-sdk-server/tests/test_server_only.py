"""`@server_only`: the body of a function is left out of the SDK, and what it imports is not read"""

import subprocess
import sys

import pytest
from pangloss_sdk_server.builder import build_package
from pangloss_sdk_server.closure import closure_of
from pangloss_sdk_server.sources import ServerOnlyProblem, shipped_source
from server_support import load_models, settings_for, write

SOURCE = '''\
from pangloss_models import server_only
from pangloss_models.model_bases.entity import Entity


class Person(Entity):
    @server_only
    async def ranking(self, depth: int = 2) -> int:
        """How well connected"""
        # (a comment in the body)
        import neo4j

        return neo4j.connect(depth)

    def label_length(self) -> int:
        return len(self.label)

    @classmethod
    @server_only
    def rebuild(cls):
        from pangloss_users import service

        service.go()
'''


def test_the_body_is_replaced_and_the_rest_of_the_file_is_as_written():
    shipped = shipped_source(SOURCE)

    assert "neo4j" not in shipped and "pangloss_users" not in shipped
    # (signature, decorators and docstring stay; the other method is untouched)
    assert (
        'async def ranking(self, depth: int = 2) -> int:\n        """How well connected"""'
        in shipped
    )
    assert "return len(self.label)" in shipped
    assert (
        "raise PanglossServerOnly('ranking' + ' is only available on the server')"
        in shipped
    )
    assert shipped.count("raise PanglossServerOnly") == 2
    compile(shipped, "shipped", "exec")


def test_an_unmarked_file_is_unchanged():
    assert shipped_source(
        "x = 1\n\nclass A:\n    def f(self):\n        import neo4j\n"
    ) == ("x = 1\n\nclass A:\n    def f(self):\n        import neo4j\n")


def test_a_body_on_the_line_of_the_def_is_refused():
    with pytest.raises(ServerOnlyProblem, match="own lines"):
        shipped_source("@server_only\ndef f(): return 1\n")


def test_the_imports_inside_a_server_only_function_are_not_followed(project):
    write(project, {"shop/models.py": SOURCE})
    closure = closure_of(project, ["shop.models"])
    assert closure.problems == []

    # (the same import in an ordinary function is still a problem)
    write(
        project,
        {
            "shop/models.py": SOURCE.replace(
                "    @server_only\n    async def ranking", "    async def ranking"
            )
        },
    )
    assert any(
        "neo4j" in problem for problem in closure_of(project, ["shop.models"]).problems
    )


def test_a_package_ships_the_replaced_body_and_works_on_a_client(project, tmp_path):
    write(project, {"shop/models.py": SOURCE.replace("pass\n", "pass\n")})
    load_models()

    package = build_package(project, settings_for())
    shipped = package.files["shop/models.py"].decode()
    assert "neo4j" not in shipped
    assert shipped != (project / "shop/models.py").read_text()

    # (on a client, calling it raises)
    shipped_directory = tmp_path / "client"
    write(shipped_directory, {"shop/__init__.py": "", "shop/models.py": shipped})
    script = (
        "import asyncio, sys\n"
        f"sys.path.insert(0, {str(shipped_directory)!r})\n"
        "from pangloss_models.exceptions import PanglossServerOnly\n"
        "from shop.models import Person\n"
        "try:\n"
        "    asyncio.run(Person.ranking(None))\n"
        "except PanglossServerOnly as error:\n"
        "    print('raised', error)\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", script], capture_output=True, text=True
    )
    assert "raised ranking is only available on the server" in result.stdout, (
        result.stderr
    )


def test_on_the_server_it_is_the_function():
    from pangloss_models import server_only

    @server_only
    def f():
        return 3

    assert f() == 3 and f.__pangloss_server_only__ is True
