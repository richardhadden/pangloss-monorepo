"""The stubs of a `derived.py` (`pangloss make-stubs`): a type checker refuses a variable of the wrong class, in the head
of a rule and in its body, and takes one of the right class or a subclass"""

import importlib
import shutil
import subprocess
import sys
import textwrap

import pytest
from pangloss_models import initialise, typestubs

MODELS = """
from pangloss_models import Document, Entity, Trait


class Agent(Trait):
    pass


class Person(Entity, Agent):
    pass


class Group(Entity, Agent):
    pass


class Place(Entity):
    pass


class MemberOf(Document):
    member: Person
    group: Group
    year: int
"""

DERIVED = """
from pangloss_derived import Derived, Var, rule

from rulesapp.models import Agent, Group, MemberOf, Person


class SameFamily(Derived):
    _meta = Derived.Meta(symmetric=True)
    first: Person
    second: Person
    family: Group


class Knew(Derived):
    first: Agent
    second: Agent


@rule
def same_family(a: Var[Person], b: Var[Person], f: Var[Group]):
    return SameFamily.Derive(first=a, second=b, family=f).when(
        MemberOf.Where(member=a, group=f),
        MemberOf.Where(member=b, group=f),
    )
"""

USAGE = """
from pangloss_models import Var
from rulesapp.derived import Knew, SameFamily
from rulesapp.models import Group, MemberOf, Person, Place


def rules(a: Var[Person], b: Var[Person], f: Var[Group], p: Var[Place], y: Var[int], s: Var[str]) -> None:
    SameFamily.Derive(first=a, second=b, family=f).when(MemberOf.Where(member=a, group=f, year=y))
    SameFamily.Derive(first=a, second=b, family=p)
    SameFamily.Derive(first=a, second=b, family=f).when(MemberOf.Where(member=f))
    SameFamily.Derive(first=a, second=b, family=f).when(MemberOf.Where(year=s))
    Knew.Derive(first=a, second=f)
    SameFamily.Derive(first=a, second=b)
"""


@pytest.mark.skipif(
    shutil.which("ty", path=str(__import__("pathlib").Path(sys.executable).parent))
    is None,
    reason="no ty",
)
def test_a_variable_of_the_wrong_class_does_not_type_check(tmp_path, monkeypatch):
    package = tmp_path / "rulesapp"
    package.mkdir()
    (package / "__init__.py").write_text("")
    (package / "models.py").write_text(textwrap.dedent(MODELS))
    (package / "derived.py").write_text(textwrap.dedent(DERIVED))
    monkeypatch.syspath_prepend(str(tmp_path))
    for name in ("rulesapp", "rulesapp.models", "rulesapp.derived"):
        sys.modules.pop(name, None)
    importlib.import_module("rulesapp.models")
    importlib.import_module("rulesapp.derived")
    initialise(bind_database=False)
    written, _ = typestubs.write_stubs(tmp_path)
    assert {p.name for p in written} == {"models.pyi", "derived.pyi"}
    (tmp_path / "usage.py").write_text(textwrap.dedent(USAGE))
    ty = shutil.which("ty", path=str(__import__("pathlib").Path(sys.executable).parent))
    assert ty is not None
    result = subprocess.run(
        [
            ty,
            "check",
            "--python",
            sys.prefix,
            "--output-format",
            "concise",
            f"--extra-search-path={tmp_path}",
            "usage.py",
        ],
        capture_output=True,
        text=True,
        cwd=tmp_path,
    )
    lines = sorted(
        {
            line.split("usage.py:", 1)[1].split(":", 1)[0]
            for line in result.stdout.splitlines()
            if "usage.py:" in line
        },
        key=int,
    )
    # (9: a Place for a Group; 10: a Group for a person; 11: a str for an int; 13: a field not given. 8 is right, and
    # so is 12: a Var[Person] and a Var[Group] are both a Var[Agent])
    assert lines == ["9", "10", "11", "13"], result.stdout
