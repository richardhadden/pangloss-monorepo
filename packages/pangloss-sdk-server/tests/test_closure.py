from pangloss_sdk_server.closure import closure_of
from server_support import write


def test_the_models_and_what_they_import_are_in_the_closure(project):
    closure = closure_of(project, ["shop.models"])

    assert set(closure.modules) == {"shop", "shop.models", "shop.helpers"}
    assert not closure.problems
    assert "shop.unrelated" not in closure.modules


def test_what_is_imported_from_outside_the_project_is_listed(project):
    write(
        project,
        {
            "shop/helpers.py": "import zstandard\nimport json\nfrom pydantic import BaseModel\n"
        },
    )
    closure = closure_of(project, ["shop.models"])
    assert {"zstandard", "pydantic", "pangloss_models"} <= closure.outside
    assert "json" not in closure.outside


def test_relative_imports_and_from_imports_of_modules_are_followed(project):
    write(
        project,
        {
            "shop/models.py": "from . import helpers\nfrom .extra import more\n",
            "shop/extra/__init__.py": "",
            "shop/extra/more.py": "from .. import unrelated\n",
        },
    )
    closure = closure_of(project, ["shop.models"])
    assert {"shop.helpers", "shop.extra", "shop.extra.more", "shop.unrelated"} <= set(
        closure.modules
    )


def test_imports_inside_functions_and_type_checking_blocks_count(project):
    write(
        project,
        {
            "shop/models.py": """
                from typing import TYPE_CHECKING
                if TYPE_CHECKING:
                    from shop import helpers
                def later():
                    import shop.unrelated
            """
        },
    )
    assert {"shop.helpers", "shop.unrelated"} <= set(
        closure_of(project, ["shop.models"]).modules
    )


def test_an_init_that_does_more_than_import_is_a_problem(project):
    write(project, {"shop/__init__.py": "import os\nconnect_to_the_database()\n"})
    problems = closure_of(project, ["shop.models"]).problems
    assert len(problems) == 1
    assert "__init__.py" in problems[0] and "more than import" in problems[0]


def test_an_init_of_docstring_imports_and_all_is_fine(project):
    write(
        project,
        {
            "shop/__init__.py": '"""Shop"""\nfrom shop.helpers import SHOUT\n__all__ = ["SHOUT"]\n'
        },
    )
    assert not closure_of(project, ["shop.models"]).problems


def test_a_server_only_import_is_a_problem_naming_the_module(project):
    write(
        project, {"shop/helpers.py": "import neo4j\nfrom pangloss_memgraph import x\n"}
    )
    problems = closure_of(project, ["shop.models"]).problems
    assert any("`shop.helpers` imports `neo4j`" in p for p in problems)
    assert any("imports `pangloss_memgraph`" in p for p in problems)


def test_a_virtual_environment_inside_the_project_is_not_the_project(project):
    write(
        project,
        {".venv/pyvenv.cfg": "", ".venv/lib/site-packages/shop/helpers.py": "X = 1\n"},
    )
    (project / "shop" / "helpers.py").unlink()
    closure = closure_of(project, ["shop.models"])
    assert "shop.helpers" not in closure.modules
