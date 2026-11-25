"""What a semantic space says of its contents (`SemanticSpace.Meta(logical=Modal(...), ...)`), where a type checker
reads it: the stub of a module keeps the module's imports and its `_meta = ...`, so `Modal` and the five keywords
are checked against `pangloss_models` itself, and nothing has to be made for them"""

import importlib
import shutil
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest
from pangloss_models import initialise, typestubs

MODELS = """
from pangloss_models import Document, Entity, Modal, SemanticSpace


class Person(Entity):
    pass


class Ordered[T](SemanticSpace[T]):
    _meta = SemanticSpace.Meta(
        logical=Modal("necessity", "command"), veridical=0, fit="prescribes", degree="likely"
    )


class Order(Document):
    ordered: Ordered[Person]
"""

USAGE = """
from pangloss_models import Modal, SemanticSpace

from spaceapp.models import Ordered


def use() -> None:
    SemanticSpace.Meta(
        logical=Modal("necessity", "command", of_not=True), veridical=-1, fit="describes", unary=True, degree=None
    )
    SemanticSpace.Meta(logical="not")
    print(Ordered._meta.logical, Modal("possibility", "epistemic").of_not)
    SemanticSpace.Meta(veridical=2)
    SemanticSpace.Meta(fit="orders")
    SemanticSpace.Meta(degree="sure")
    Modal("must", "command")
"""

TY = shutil.which("ty", path=str(Path(sys.executable).parent))


@pytest.fixture
def app(tmp_path, monkeypatch):
    package = tmp_path / "spaceapp"
    package.mkdir()
    (package / "__init__.py").write_text("")
    (package / "models.py").write_text(textwrap.dedent(MODELS))
    monkeypatch.syspath_prepend(str(tmp_path))
    for name in ("spaceapp", "spaceapp.models"):
        sys.modules.pop(name, None)
    importlib.import_module("spaceapp.models")
    initialise(bind_database=False)
    yield tmp_path
    for name in ("spaceapp", "spaceapp.models"):
        sys.modules.pop(name, None)


def test_the_stub_keeps_the_import_of_modal_and_the_meta(app):
    written, _ = typestubs.write_stubs(app)
    stub = written[0].read_text()
    assert "from pangloss_models import Document, Entity, Modal, SemanticSpace" in stub
    assert "class Ordered[T](SemanticSpace[T]):\n    _meta = ..." in stub


@pytest.mark.skipif(TY is None, reason="no ty")
def test_a_type_checker_takes_the_five_keywords_and_refuses_what_they_cannot_be(app):
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
            "spaceapp",
        ],
        capture_output=True,
        check=False,
        text=True,
        cwd=app,
    )
    errors = [line for line in result.stdout.splitlines() if "error[" in line]
    # (the module and its stub, and the first three uses, are taken; only the four wrong values are refused)
    assert sorted(int(line.split(":")[1]) for line in errors) == [13, 14, 15, 16], (
        result.stdout
    )
