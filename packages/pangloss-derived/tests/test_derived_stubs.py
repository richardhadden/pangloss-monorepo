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


class Meeting(Document):
    participants: list[Agent]
"""

DERIVED = """
from typing import Annotated

from pangloss_derived import DerivedEdge, Object, Subject, SymmetricLabel, Var, rule

from rulesapp.models import Agent, Group, MemberOf, Person


class SameFamily(DerivedEdge):
    _meta = DerivedEdge.Meta(symmetric=True)
    first: Annotated[Person, SymmetricLabel("member")]
    second: Annotated[Person, SymmetricLabel("member")]
    family: Group


class Knew(DerivedEdge):
    first: Annotated[Agent, Subject()]
    second: Annotated[Agent, Object(reverse_name="known_by")]


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
from rulesapp.models import Agent, Group, Meeting, MemberOf, Person, Place


def rules(a: Var[Person], b: Var[Person], f: Var[Group], p: Var[Place], y: Var[int], s: Var[str]) -> None:
    SameFamily.Derive(first=a, second=b, family=f).when(MemberOf.Where(member=a, group=f, year=y))
    SameFamily.Derive(first=a, second=b, family=p)
    SameFamily.Derive(first=a, second=b, family=f).when(MemberOf.Where(member=f))
    SameFamily.Derive(first=a, second=b, family=f).when(MemberOf.Where(year=s))
    Knew.Derive(first=a, second=f)
    SameFamily.Derive(first=a, second=b)


def of_a_trait(a: Var[Agent], b: Var[Person], p: Var[Place]) -> None:
    Knew.Derive(first=a, second=b).when(Meeting.Where(participants=a), Meeting.Where(participants=b))
    MemberOf.Where(member=a)
    Meeting.Where(participants=p)
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
    # so is 12: a Var[Person] and a Var[Group] are both a Var[Agent]. 17 is right: a variable of the trait, where the
    # field holds anything with the trait; 18: an agent for a person, as a group is an agent too; 19: a Place for an
    # agent)
    assert lines == ["9", "10", "11", "13", "18", "19"], result.stdout


DECLARING_MODELS = """
from pangloss_derived import DerivesEdge, RuleType
from pangloss_models import Document, Entity, Trait

exchange = RuleType("exchange")


class Agent(Trait):
    pass


class Person(Entity, Agent):
    pass


class Group(Entity, Agent):
    pass


class Place(Entity):
    pass


class Transfer(Document):
    _derives = [
        DerivesEdge(
            "GaveTo",
            subject="given_by",
            object="given_to",
            reverse_name="received_from",
            qualifiers={"year": "year"},
            types=[exchange],
        )
    ]
    given_by: Agent
    given_to: Agent
    year: int
"""

DECLARING_USAGE = """
from pangloss_models import Var
from declaring.models import Agent, GaveTo, Person, Place, Transfer


def rules(a: Var[Person], b: Var[Agent], p: Var[Place], y: Var[int]) -> None:
    GaveTo.Derive(given_by=a, given_to=b, year=y).when(Transfer.Where(given_by=a))
    GaveTo.Derive(given_by=a, given_to=p, year=y)
    GaveTo.Derive(given_by=a, given_to=b)
    GaveTo.Where(year=1500)
    GaveTo.Where(yeer=1500)


async def reads(person: Person.View) -> None:
    page = await GaveTo.list(entity=person)
    for edge in page.results:
        edge.qualifiers.year
"""


@pytest.mark.skipif(
    shutil.which("ty", path=str(__import__("pathlib").Path(sys.executable).parent))
    is None,
    reason="no ty",
)
def test_an_edge_declared_on_a_document_class_is_in_the_stub_of_its_module(
    tmp_path, monkeypatch
):
    package = tmp_path / "declaring"
    package.mkdir()
    (package / "__init__.py").write_text("")
    (package / "models.py").write_text(textwrap.dedent(DECLARING_MODELS))
    monkeypatch.syspath_prepend(str(tmp_path))
    for name in ("declaring", "declaring.models"):
        sys.modules.pop(name, None)
    module = importlib.import_module("declaring.models")
    assert not hasattr(module, "GaveTo")
    initialise(bind_database=False)
    # (once the models are initialised, the class is where its document class is)
    from pangloss_derived import DerivedEdge

    assert module.GaveTo is DerivedEdge.named("GaveTo")
    written, _ = typestubs.write_stubs(tmp_path)
    assert {p.name for p in written} == {"models.pyi"}
    stub = (package / "models.pyi").read_text()
    assert "class GaveTo(pangloss_derived.declare.DerivedEdge):" in stub
    assert "class Derive(pangloss_derived.check.DeriveBase):" in stub
    assert "qualifiers: GaveTo.Qualifiers" in stub
    (tmp_path / "usage.py").write_text(textwrap.dedent(DECLARING_USAGE))
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
    # (8: a place for an agent; 9: the year not given; 11: a filter by a field there is not. 7, 10 and the reads
    # are right: the class can be imported from its document class's module, with its head, filter and views)
    assert lines == ["8", "9", "11"], result.stdout


THROUGH_MODELS = """
from pangloss_models import Conjunction, Document, EdgeModel, Entity, ReifiedRelation, ViaEdge


class Share(EdgeModel):
    percent: int


class Certainty(EdgeModel):
    value: int


class Either[T](Conjunction):
    either: list[ViaEdge[T, Share]]


class Identification[T](ReifiedRelation[T]):
    identified_by: str
    score: int = 0


class Person(Entity):
    pass


class Transfer(Document):
    given_by: Person | Identification[Person] | Either[Person | Identification[Person]]
    given_to: Person
    witnesses: list[ViaEdge[Person, Certainty]]
"""

THROUGH_USAGE = """
from pangloss_models import Compare, Rel, Text, Through, Var
from throughapp.models import Certainty, Either, Identification, Person, Share, Transfer


def rules(a: Var[Person], p: Var[int], s: Var[str]) -> None:
    Transfer.Where(given_by=Rel(is_=a, through=[Through(Either, edge=Share.Where(percent=p))]))
    Transfer.Where(given_by=Rel(is_=a, through=[Either, Through(Identification, where=Identification.Where(identified_by=s))]))
    Transfer.Where(witnesses=Rel(is_=a, edge=Certainty.Where(value=Compare[int](gte=3))))
    Through(Either, edge=Share.Where(percent=Compare[int](gte=60)))
    Identification.Where(identified_by=Text(eq="Smith"), score=p)
    Share.Where(percent=s)
    Share.Where(percentt=p)
    Identification.Where(score=s)
    Identification.Where(target=a)
    Through(Either, edge=Person.Where())
    Through(Either, where=Share.Where())
    Rel(is_=a, edge=Identification.Where())
"""


@pytest.mark.skipif(
    shutil.which("ty", path=str(__import__("pathlib").Path(sys.executable).parent))
    is None,
    reason="no ty",
)
def test_what_is_asked_of_the_way_of_a_relation_is_typed(tmp_path, monkeypatch):
    """An edge model and a wrapper have a `Where` in the stubs, of their own values; `Through` and `Rel(edge=)` take
    the right kind of each"""
    package = tmp_path / "throughapp"
    package.mkdir()
    (package / "__init__.py").write_text("")
    (package / "models.py").write_text(textwrap.dedent(THROUGH_MODELS))
    monkeypatch.syspath_prepend(str(tmp_path))
    for name in ("throughapp", "throughapp.models"):
        sys.modules.pop(name, None)
    importlib.import_module("throughapp.models")
    initialise(bind_database=False)
    written, _ = typestubs.write_stubs(tmp_path)
    assert {p.name for p in written} == {"models.pyi"}
    stub = (package / "models.pyi").read_text()
    assert "class Where(pangloss_models.search_where.EdgeWhere)" in stub
    assert "class Where(pangloss_models.search_where.WrapperWhere)" in stub
    (tmp_path / "usage.py").write_text(textwrap.dedent(THROUGH_USAGE))
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
    # (7 to 11 are right. 12: a str for an int; 13: a field the edge model has not; 14: a str for an int, of a
    # wrapper; 15: what a wrapper points at is not one of its values; 16: a pattern of an entity for an edge; 17: one
    # of an edge for a wrapper; 18: one of a wrapper for an edge)
    assert lines == ["12", "13", "14", "15", "16", "17", "18"], result.stdout


DOCUMENT_MODELS = """
from pangloss_models import Document, EdgeModel, Embedded, Entity, ReifiedRelation, ViaEdge

from pangloss_derived import DerivedDocument, DerivedFrom


class Certainty(EdgeModel):
    value: int


class InRole[T](ReifiedRelation[T]):
    role: str


class Person(Entity):
    pass


class Place(Entity):
    pass


class When(Embedded):
    year: int


class Statement(Document):
    _meta = Document.Meta(abstract=True, create_directly=False)


class ChildOf(Statement):
    child: Person
    parent: Person


class Sibling(Statement):
    people: list[Person | InRole[Person]]
    closest: ViaEdge[Person, Certainty] | None = None
    when: When | None = None
    certainty: int = 100


class Factoid(Document):
    statements: list[Statement]


class DerivedFactoid(Document, DerivedDocument):
    sources: list[DerivedFrom[Factoid]]
    statements: list[Statement]
"""

DOCUMENT_USAGE = """
from pangloss_derived import Var, Via, unordered

from documentapp.models import Certainty, ChildOf, DerivedFactoid, InRole, Person, Place, Sibling, When

a, b, where, n, s = Var("a", Person), Var("b", Person), Var("where", Place), Var("n", int), Var("s", str)
DerivedFactoid.Derive(label="x", statements=[Sibling.Template(label="x", people=[a, b])]).when(ChildOf.Where(child=a), unordered(a, b))
Sibling.Template(label=s, people=[a, InRole.Template(target=[b], role=s)], certainty=n, when=When.Template(year=n))
Sibling.Template(label="x", people=[], closest=Via(a, Certainty.Template(value=n)))
DerivedFactoid.Derive(label="x", statements=[ChildOf.Template(label="x", child=a, parent=b)])
Sibling.Template(label="x", people=[where])
Sibling.Template(label="x", people=[a], certainty=s)
Sibling.Template(label="x", people=[a], colour="red")
Sibling.Template(label="x")
DerivedFactoid.Derive(label="x", statements=[a])
DerivedFactoid.Derive(label="x", statements=[], sources=[])
When.Template(year=s)
"""


@pytest.mark.skipif(
    shutil.which("ty", path=str(__import__("pathlib").Path(sys.executable).parent))
    is None,
    reason="no ty",
)
def test_a_template_is_typed(tmp_path, monkeypatch):
    """The classes a derived document can hold have a `Template` in the stubs, and the derived class a `Derive`: a
    type checker takes a variable where a `Create` takes a reference or a value, and refuses one of the wrong class"""
    package = tmp_path / "documentapp"
    package.mkdir()
    (package / "__init__.py").write_text("")
    (package / "models.py").write_text(textwrap.dedent(DOCUMENT_MODELS))
    monkeypatch.syspath_prepend(str(tmp_path))
    for name in ("documentapp", "documentapp.models"):
        sys.modules.pop(name, None)
    importlib.import_module("documentapp.models")
    initialise(bind_database=False)
    written, _ = typestubs.write_stubs(tmp_path)
    assert {p.name for p in written} == {"models.pyi"}
    stub = (package / "models.pyi").read_text()
    assert "class Template(pangloss_derived.templates.TemplateBase)" in stub
    assert "class Derive(pangloss_derived.templates.DeriveDocumentBase)" in stub
    # (the template of a subclass is one of its parent's)
    assert "class Template(Statement.Template)" in stub
    assert "people: list[" in stub and "pangloss_models.search.Var[Person]" in stub
    (tmp_path / "usage.py").write_text(textwrap.dedent(DOCUMENT_USAGE))
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
    # (7 to 10 are right. 11: a place where a person goes; 12: a str for an int; 13: a field the class has not; 14: a
    # field that has to be given; 15: an entity where a statement goes; 16: the sources, which the worker fills; 17: a
    # str for an int, of an embedded object)
    assert lines == ["11", "12", "13", "14", "15", "16", "17"], result.stdout
