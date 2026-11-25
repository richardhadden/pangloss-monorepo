"""`Attribution(by=..., to=...)` on a field that holds a space, where a type checker reads it: the stub of a module
keeps the module's imports, and the field's annotation is checked against `pangloss_models` itself"""

import importlib
import shutil
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest
from pangloss_models import initialise, typestubs

MODELS = """
from typing import Annotated

from pangloss_models import Attribution, Document, Entity, SemanticSpace


class Person(Entity):
    pass


class Ordered[T](SemanticSpace[T]):
    pass


class Statement(Document):
    pass


class Order(Statement):
    ordered_by: Person
    ordered_to: list[Person]
    thing_ordered: Annotated[Ordered[Statement], Attribution(by="ordered_by", to="ordered_to")]
"""

USAGE = """
from pangloss_models import Attribution

from attributionapp.models import Order


def use() -> None:
    print(Order.thing_ordered, Attribution(by="a"), Attribution(to="b").to)
    Attribution("a")
    Attribution(by=1)
"""

TY = shutil.which("ty", path=str(Path(sys.executable).parent))


@pytest.fixture
def app(tmp_path, monkeypatch):
    package = tmp_path / "attributionapp"
    package.mkdir()
    (package / "__init__.py").write_text("")
    (package / "models.py").write_text(textwrap.dedent(MODELS))
    monkeypatch.syspath_prepend(str(tmp_path))
    for name in ("attributionapp", "attributionapp.models"):
        sys.modules.pop(name, None)
    importlib.import_module("attributionapp.models")
    initialise(bind_database=False)
    yield tmp_path
    for name in ("attributionapp", "attributionapp.models"):
        sys.modules.pop(name, None)


def test_the_stub_keeps_the_import_of_attribution(app):
    written, _ = typestubs.write_stubs(app)
    stub = written[0].read_text()
    assert (
        "from pangloss_models import Attribution, Document, Entity, SemanticSpace"
        in stub
    )
    assert (
        "    thing_ordered: Annotated[Ordered[Statement], "
        "Attribution(by='ordered_by', to='ordered_to')]" in stub
    )


@pytest.mark.skipif(TY is None, reason="no ty")
def test_a_type_checker_takes_the_attribution_and_refuses_what_it_cannot_be(app):
    typestubs.write_stubs(app)
    (app / "usage.py").write_text(textwrap.dedent(USAGE))
    assert TY is not None
    result = subprocess.run(
        [
            TY,
            "check",
            "--python",
            sys.prefix,
            "--output-format",
            "concise",
            "--ignore=unused-type-ignore-comment",
            f"--extra-search-path={app}",
            "usage.py",
            "attributionapp",
        ],
        capture_output=True,
        check=False,
        text=True,
        cwd=app,
    )
    errors = [line for line in result.stdout.splitlines() if "error[" in line]
    # (the module and its stub, and the first use, are taken; only the two wrong calls are refused)
    assert sorted(int(line.split(":")[1]) for line in errors) == [9, 10], result.stdout
