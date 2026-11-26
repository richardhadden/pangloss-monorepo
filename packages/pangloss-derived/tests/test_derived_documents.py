"""Derived documents, with no database: what makes a class one, the templates a rule writes with (made, checked, kept
as data, filled), the rules between rules (no loop, each document's sources of a class its field takes), `unordered`,
what a rule that derives a document may derive through, and how each refusal is said"""

import json
import logging
import uuid
from typing import Annotated, no_type_check

import pytest
from annotated_types import Ge
from pangloss_models import (
    Cites,
    Conjunction,
    Document,
    EdgeModel,
    Embedded,
    Entity,
    ModelRegistry,
    ReifiedRelation,
    SemanticSpace,
    Trait,
    Var,
    ViaEdge,
    hooks,
    initialise,
)
from pangloss_models.export import export_models

from pangloss_derived import (
    DerivedDocument,
    DerivedDocumentMeta,
    DerivedEdge,
    DerivedFrom,
    DerivedMeta,
    PanglossDerivedError,
    SymmetricLabel,
    Via,
    distinct,
    rule,
    unordered,
    writing_derived,
)
from pangloss_derived.compile import compile_rule
from pangloss_derived.documents import (
    is_derived_document,
    settings_of,
    source_field,
)
from pangloss_derived.registry import DerivedRegistry
from pangloss_derived.store import Found
from pangloss_derived.templates import (
    TNode,
    TRef,
    TValue,
    TVar,
    TVia,
    describe,
    fill,
    nodes_of,
    written_classes,
)


class Names(dict):
    """The classes a function declared, by name: `m.Person`"""

    __getattr__ = dict.__getitem__


@pytest.fixture(autouse=True)
def a_dialect(monkeypatch):
    """The queries are made with a backend's dialect: Memgraph's, with no database behind it"""
    import pangloss_cypher.search_query
    import pangloss_derived.compile
    from pangloss_memgraph.databases.memgraph.dialect import MemgraphDialect

    dialect = MemgraphDialect()
    monkeypatch.setattr(pangloss_derived.compile, "dialect", lambda: dialect)
    monkeypatch.setattr(pangloss_cypher.search_query, "dialect", lambda: dialect)


@no_type_check
def base(sources=None, statements_alone=False, chained=False):
    """A factoid model: statements in factoids, and a derived factoid. `sources`: what the derived factoid's
    `DerivedFrom` takes, given the classes (by default the factoids people write); `chained`: it takes derived
    factoids as well, as a rule that reads them needs; `statements_alone`: a statement can be a document of its own"""

    class Certainty(EdgeModel):
        certainty: int

    class Note(EdgeModel):
        note: str = ""

    class Negative[T](SemanticSpace[T]):
        pass

    class InRole[T](ReifiedRelation[T]):
        role: str

    class Guess[T](ReifiedRelation[T]):
        """(as the library's identification by a toolchain: not read through without being named)"""

        _derived_meta = DerivedMeta(derivation="qualify")

    class Either[T](Conjunction):
        either: list[T]

    class Agent(Trait):
        pass

    class Person(Entity, Agent):
        pass

    class Group(Entity, Agent):
        pass

    class Place(Entity):
        pass

    class When(Embedded):
        year: Annotated[int, Ge(0)]
        about: bool = False

    class Statement(Document):
        _meta = Document.Meta(abstract=True, create_directly=statements_alone)

    class ChildOf(Statement):
        child: Person | InRole[Person] | Guess[Person]
        parent: Person

    class Sibling(Statement):
        people: list[Person | InRole[Person] | Either[Person]]
        closest: ViaEdge[Person, Certainty] | None = None
        when: When | None = None
        certainty: int = 100
        kind: str = "full"
        tags: list[str] = []

    class Cousin(Statement):
        people: list[Person]

    class Seen(Statement):
        noted: list[ViaEdge[Agent, Note]]

    class Residence(Statement):
        resident: Agent
        place: Place

    class Factoid(Document):
        statements: list[Statement | Negative[Statement]]

    made = locals()
    Taken = sources(Names(made)) if sources else Factoid

    if chained:

        class DerivedFactoid(Document, DerivedDocument):
            """What follows from what other factoids say, derived ones among them"""

            sources: list[DerivedFrom[Factoid | DerivedFactoid]]
            statements: list[Statement | Negative[Statement]]

    else:

        class DerivedFactoid(Document, DerivedDocument):
            """What follows from what other factoids say"""

            sources: list[DerivedFrom[Taken]]
            statements: list[Statement | Negative[Statement]]

    return Names({**made, "DerivedFactoid": DerivedFactoid})


def initialised(make=None, **options):
    m = base(**options)
    made = (make(m) or {}) if make else {}
    initialise(bind_database=False)
    return Names({**m, **made})


def refused(make, **options) -> str:
    with pytest.raises(PanglossDerivedError) as error:
        initialised(make, **options)
    return str(error.value)


@no_type_check
def siblings(m, **when):
    """The rule of the plan: two children of one parent are siblings"""

    @rule
    def siblings(a: Var[m.Person], b: Var[m.Person], p: Var[m.Person]):
        """Two children of one parent are siblings"""
        return m.DerivedFactoid.Derive(
            label="Siblings",
            statements=[m.Sibling.Template(label="Siblings", people=[a, b])],
        ).when(
            m.ChildOf.Where(child=a, parent=p),
            m.ChildOf.Where(child=b, parent=p),
            unordered(a, b),
            **when,
        )


@no_type_check
def one(m, statement, *patterns, variables=None, name="made", **when):
    """A rule that derives a factoid of one statement (a function of the variables), from a child and a parent"""
    annotations = variables or {"a": Var[m.Person], "p": Var[m.Person]}

    def function(**v):
        body = patterns or (lambda v: [m.ChildOf.Where(child=v["a"], parent=v["p"])],)
        return m.DerivedFactoid.Derive(label="Made", statements=[statement(v)]).when(
            *body[0](v), **when
        )

    # (a rule's variables are the parameters of its function)
    source = f"def {name}({', '.join(annotations)}):\n    return function({', '.join(f'{k}={k}' for k in annotations)})"
    scope = {"function": function}
    exec(source, scope)
    scope[name].__annotations__ = dict(annotations)
    rule(scope[name])


def pair(model, s, a, b):
    """The patterns of one statement (the variable `s`) that names both: a list relation takes one variable in a
    pattern, so there are two patterns of the one node"""
    return [model.Where(is_=s, people=a), model.Where(is_=s, people=b)]


def document(name="made"):
    return DerivedRegistry.documents[name]


def query(name):
    checked = DerivedRegistry.all_checked()[name]
    return compile_rule(checked, checked.seeds[0].node)


def person(m=None):
    return {"type": "Person", "id": str(uuid.uuid4())}


# ---------------------------------------------------------------------------
# What makes a class a derived document class
# ---------------------------------------------------------------------------


def test_a_document_class_with_the_trait_and_a_derived_from_field_is_one():
    m = initialised()
    assert is_derived_document(m.DerivedFactoid)
    assert not is_derived_document(m.Factoid) and not is_derived_document(m.Person)
    assert not is_derived_document(DerivedDocument)
    name, option = source_field(m.DerivedFactoid)
    assert name == "sources" and option.cited == {m.Factoid} and not option.protect
    # (what the worker records is in the database's models, and read: not something a person gives)
    fields = m.DerivedFactoid._meta.fields
    assert fields["derived_by"].db_field and fields["derived_context"].db_field
    assert "derived_by" not in m.DerivedFactoid.Create.model_fields
    assert "derived_by" in m.DerivedFactoid.CreateDB.model_fields
    # (and read with every reference to one: what a list or a search marks a derived document by)
    assert "derived_by" in m.DerivedFactoid.ReferenceView.model_fields
    assert "derived_context" in m.DerivedFactoid.ReferenceView.model_fields
    assert "derived_by" in m.DerivedFactoid.Where.model_fields
    # (and it gets the head of a rule, as a class of edges does)
    assert m.DerivedFactoid.Derive.__name__ == "DerivedFactoidDerive"
    assert list(m.DerivedFactoid.Derive.model_fields) == ["label", "statements"]


def test_the_settings_have_defaults_and_are_checked():
    m = initialised()
    assert settings_of(m.DerivedFactoid) == DerivedDocumentMeta()
    assert settings_of(m.DerivedFactoid).max_per_seed == 2_000
    assert DerivedDocumentMeta(converts_to=int).converts_to == (int,)
    assert DerivedDocumentMeta(converts_to=[int, str]).converts_to == (int, str)
    with pytest.raises(ValueError, match="at least 1"):
        DerivedDocumentMeta(max_per_seed=0)


@no_type_check
def test_the_settings_of_a_class_are_its_own():
    def declared(m):
        class Summary(Document, DerivedDocument):
            _derived_document_meta = DerivedDocumentMeta(
                max_per_seed=50, converts_to=m.Factoid
            )
            sources: list[DerivedFrom[m.Factoid]]
            text: str

        return locals()

    m = initialised(declared)
    assert settings_of(m.Summary).max_per_seed == 50
    assert settings_of(m.Summary).converts_to == (m.Factoid,)
    assert settings_of(m.DerivedFactoid).max_per_seed == 2_000


@no_type_check
def test_a_derived_from_field_without_the_trait_is_refused():
    def declared(m):
        class Summary(Document):
            sources: list[DerivedFrom[m.Factoid]]

    said = refused(declared)
    assert "Summary.sources is a DerivedFrom, which only the worker writes" in said
    assert "class Summary(Document, DerivedDocument)" in said and "Cites[...]" in said


@no_type_check
def test_another_citation_that_does_not_protect_is_not_a_derived_from():
    """A project's own citation with `protect = False` is one people write: its class is no derived document class"""

    class RestsOn[Target](Cites[Target]):
        protect = False

    def declared(m):
        class Summary(Document):
            sources: list[RestsOn[m.Factoid]]

        return locals()

    m = initialised(declared)
    assert not is_derived_document(m.Summary) and hooks.written_by_people(m.Summary)
    ModelRegistry._reset()

    # (and beside it the trait still wants its `DerivedFrom`)
    def with_the_trait(m):
        class Summary(Document, DerivedDocument):
            sources: list[RestsOn[m.Factoid]]

    assert "this has none" in refused(with_the_trait)


@no_type_check
def test_the_trait_without_a_derived_from_field_is_refused():
    def declared(m):
        class Summary(Document, DerivedDocument):
            text: str

    said = refused(declared)
    assert "Summary: a derived document class has one field of DerivedFrom" in said
    assert "this has none" in said


@no_type_check
def test_two_derived_from_fields_are_refused():
    def declared(m):
        class Summary(Document, DerivedDocument):
            sources: list[DerivedFrom[m.Factoid]]
            others: list[DerivedFrom[m.Factoid]]

    assert "this has sources, others" in refused(declared)


@no_type_check
def test_the_derived_from_field_is_a_list():
    def declared(m):
        class Summary(Document, DerivedDocument):
            source: DerivedFrom[m.Factoid]

    said = refused(declared)
    assert (
        "Summary.source: the DerivedFrom field of a derived document class is a list"
        in said
    )


@no_type_check
def test_a_derived_document_is_a_document_of_its_own():
    def declared(m):
        class Summary(Document, DerivedDocument):
            _meta = Document.Meta(create_directly=False)
            sources: list[DerivedFrom[m.Factoid]]

    said = refused(declared)
    assert "Summary: a derived document is a document of its own" in said
    assert "create_directly=False" in said


@no_type_check
def test_an_abstract_parent_may_leave_the_field_to_its_subclasses():
    def declared(m):
        class Derivation(Document, DerivedDocument):
            _meta = Document.Meta(abstract=True)

        class Summary(Derivation):
            sources: list[DerivedFrom[m.Factoid]]
            text: str

        return locals()

    m = initialised(declared)
    assert is_derived_document(m.Summary) and is_derived_document(m.Derivation)
    assert "Derive" in vars(m.Summary) and "Derive" not in vars(m.Derivation)


@no_type_check
def test_converts_to_names_document_classes_people_write():
    def an_entity(m):
        class Summary(Document, DerivedDocument):
            _derived_document_meta = DerivedDocumentMeta(converts_to=m.Person)
            sources: list[DerivedFrom[m.Factoid]]

    assert "Summary: converts_to names document classes" in refused(an_entity)
    ModelRegistry._reset()

    def a_derived_one(m):
        class Summary(Document, DerivedDocument):
            _derived_document_meta = DerivedDocumentMeta(converts_to=m.DerivedFactoid)
            sources: list[DerivedFrom[m.Factoid]]

    said = refused(a_derived_one)
    assert "DerivedFactoid is a derived document class too" in said


@no_type_check
def test_a_project_with_no_derived_document_has_no_templates():
    class Person(Entity):
        pass

    class ChildOf(Document):
        child: Person
        parent: Person

    initialise(bind_database=False)
    assert "Template" not in vars(ChildOf) and "Derive" not in vars(ChildOf)
    assert DerivedRegistry.documents == {} and DerivedRegistry.order == []


def test_people_do_not_write_a_derived_document_class():
    m = initialised()
    assert not hooks.written_by_people(m.DerivedFactoid)
    assert hooks.written_by_people(m.Factoid) and hooks.written_by_people(m.Person)
    exported = export_models()["models"]
    # (so the interface offers no "New"; a statement is not created directly because its class says so)
    # (a document of its own, which is searched as one; what it lacks is anyone to write it)
    assert exported["DerivedFactoid"]["createDirectly"] is True
    assert exported["DerivedFactoid"]["writtenByPeople"] is False
    assert exported["Factoid"]["createDirectly"] is True
    assert "writtenByPeople" not in exported["Factoid"]
    assert exported["Sibling"]["createDirectly"] is False


# ---------------------------------------------------------------------------
# The classes made
# ---------------------------------------------------------------------------


def test_a_template_is_made_for_every_class_a_derived_document_can_hold():
    m = initialised()
    made = {
        name
        for name, model in m.items()
        if isinstance(model, type) and "Template" in vars(model)
    }
    assert made == {
        "Statement",
        "ChildOf",
        "Sibling",
        "Cousin",
        "Seen",
        "Residence",
        "Negative",
        "InRole",
        "Guess",
        "Either",
        "When",
        "Certainty",
        "Note",
        "DerivedFactoid",
    }
    # (not an entity, which a template refers to; not a document the derived one cannot hold)
    assert "Template" not in vars(m.Person) and "Template" not in vars(m.Factoid)
    assert m.Sibling.Template._model is m.Sibling
    assert m.Sibling.Template.__name__ == "SiblingTemplate"
    assert m.Sibling.Template.__module__ == m.Sibling.__module__


@pytest.fixture
def stand_ins_for_a_person():
    """A document and a generic wrapper with computed candidates, each offered wherever a person goes"""
    stand_ins = [
        hooks.StandIn(
            document=name, stands_for=lambda model: model.__name__ == "Person"
        )
        for name in ("Described", "Placeholder")
    ]
    hooks.stand_ins.extend(stand_ins)
    yield
    for stand_in in stand_ins:
        hooks.stand_ins.remove(stand_in)


@no_type_check
def stand_in_classes():
    from pangloss_models import Computed

    class Described[T](ReifiedRelation[T]):
        said: str | None = None
        target: Annotated[list[T], Computed()] = []

    class Placeholder(Document):
        _meta = Document.Meta(create_directly=False)

    return Described, Placeholder


@no_type_check
def test_no_template_writes_a_stand_in_or_what_the_server_computes(
    stand_ins_for_a_person,
):
    """What stands in for an entity (an `Unreconciled`) is a task for a person, and the candidates of a description
    (`MatchesCriteria`) are found for it: a derived document holds neither, offered by a hook or written out"""
    Described, Placeholder = stand_in_classes()

    def more(m):
        class Mention(m.Statement):
            who: m.Group | Described[m.Group]

        siblings(m)
        return {"Mention": Mention}

    m = initialised(more)

    # (the relations of the statements do take them, as those of every document)
    taken = {
        getattr(o, "base_type", o.annotated_type).__name__
        for o in m.Sibling._meta.fields["people"].type_options
    }
    assert {"Described", "Placeholder"} <= taken
    assert "Template" not in vars(Described) and "Template" not in vars(Placeholder)
    # (nor is either in what a type checker is told a template's field takes)
    for model, field in (
        (m.Sibling, "people"),
        (m.Mention, "who"),
        (m.Cousin, "people"),
    ):
        (said,) = [
            item.annotation
            for item in model.Template.model_fields[field].metadata
            if type(item).__name__ == "StubAnnotation"
        ]
        assert "Described" not in str(said) and "Placeholder" not in str(said)
    # (the rule that writes people where they go is as it was)
    assert document("siblings").template.model is m.DerivedFactoid


@no_type_check
def test_a_rule_that_gives_one_all_the_same_is_refused(stand_ins_for_a_person):
    stand_in_classes()

    def declared(m):
        one(
            m,
            lambda v: m.Cousin.Template(
                label="x", people=[{"type": "Described", "said": "N. N."}]
            ),
        )

    assert "people[0]: takes a variable, a Template or a reference" in refused(declared)


def test_a_template_has_the_fields_of_a_create_but_the_citations():
    m = initialised()
    fields = m.Sibling.Template.model_fields
    assert list(fields) == [
        "label",
        "people",
        "closest",
        "when",
        "certainty",
        "kind",
        "tags",
    ]
    assert fields["label"].is_required() and fields["people"].is_required()
    assert not fields["closest"].is_required() and not fields["tags"].is_required()
    # (a wrapper's are those of its class without its parameters: its target is of whatever it is used with)
    assert list(m.InRole.Template.model_fields) == ["target", "role"]
    assert list(m.Negative.Template.model_fields) == ["contents"]
    assert list(m.Certainty.Template.model_fields) == ["certainty"]
    assert m.Certainty.Template.model_fields["certainty"].is_required()
    assert not m.Note.Template.model_fields["note"].is_required()
    # (the head of a rule: no `sources`, which the worker fills)
    assert "sources" not in m.DerivedFactoid.Derive.model_fields
    assert "derived_by" not in m.DerivedFactoid.Derive.model_fields


def test_the_template_of_a_subclass_is_one_of_its_parents():
    m = initialised()
    assert issubclass(m.Sibling.Template, m.Statement.Template)
    assert issubclass(m.ChildOf.Template, m.Statement.Template)
    assert not issubclass(m.Sibling.Template, m.ChildOf.Template)


def test_a_template_says_what_a_type_checker_is_to_take():
    from pangloss_models.typestubs import stub_annotation

    m = initialised()

    def said(model, field, cls="Template"):
        return stub_annotation(getattr(model, cls).model_fields[field])

    assert said(m.Sibling, "label") == Var[str] | str
    assert said(m.Sibling, "certainty") == Var[int] | int
    assert said(m.Sibling, "tags") == list[Var[str] | str]
    assert said(m.Sibling, "when") == m.When.Template | None
    assert said(m.When, "year") == Var[int] | int
    assert said(m.Certainty, "certainty") == Var[int] | int
    people = said(m.Sibling, "people")
    assert set(people.__args__[0].__args__) == {
        Var[m.Person],
        m.Person.ReferenceSet,
        m.InRole.Template,
        m.Either.Template,
    }
    closest = said(m.Sibling, "closest")
    assert set(closest.__args__) == {
        Var[m.Person],
        m.Person.ReferenceSet,
        Via,
        type(None),
    }
    statements = said(m.DerivedFactoid, "statements", "Derive")
    # (a relation to an abstract class is to each class below it)
    assert set(statements.__args__[0].__args__) == {
        m.ChildOf.Template,
        m.Sibling.Template,
        m.Cousin.Template,
        m.Seen.Template,
        m.Residence.Template,
        m.Negative.Template,
    }


def test_an_unknown_or_missing_field_is_said_with_the_rule():
    def unknown(m):
        one(m, lambda v: m.Sibling.Template(label="x", people=[v["a"]], colour="red"))

    said = refused(unknown)
    assert "Rule made: the head is not right" in said and "colour" in said
    ModelRegistry._reset()

    def missing(m):
        one(m, lambda v: m.Sibling.Template(label="x"))

    said = refused(missing)
    assert "Rule made: the head is not right" in said and "people" in said
    ModelRegistry._reset()

    def sources_given(m):
        @rule
        def made(a: Var[m.Person], p: Var[m.Person]):
            return m.DerivedFactoid.Derive(label="x", statements=[], sources=[]).when(
                m.ChildOf.Where(child=a, parent=p)
            )

    assert "sources" in refused(sources_given)


# ---------------------------------------------------------------------------
# A template as data
# ---------------------------------------------------------------------------


def test_a_rule_that_derives_a_document_is_checked_and_kept_apart():
    m = initialised(siblings)
    assert list(DerivedRegistry.documents) == ["siblings"]
    # (not a rule of edges; a write of what can hold a `ChildOf` leaves work for it all the same)
    assert DerivedRegistry.checked == {}
    assert {
        seed.rule for seeds in DerivedRegistry.triggers.values() for seed in seeds
    } == {"siblings"}
    assert "Factoid" in DerivedRegistry.triggers
    assert list(DerivedRegistry.all_checked()) == ["siblings"]
    checked = document("siblings")
    assert checked.document and checked.model is m.DerivedFactoid
    assert checked.symmetric is None and checked.unordered == (("a", "b"),)
    # (what a justification keeps: the variables of the template, in the order met)
    assert checked.head == {"a": ("var", "a"), "b": ("var", "b")}
    assert checked.max_per_seed == 2_000
    assert [n.model for n in checked.tops] == [m.ChildOf, m.ChildOf]
    assert checked.template == TNode(
        m.DerivedFactoid,
        {
            "label": TValue("Siblings"),
            "statements": (
                TNode(
                    m.Sibling,
                    {
                        "label": TValue("Siblings"),
                        "people": (TVar("a", True), TVar("b", True)),
                    },
                ),
            ),
        },
    )
    assert written_classes(checked.template) == [m.DerivedFactoid, m.Sibling]
    assert [n.type for n in nodes_of(checked.template)] == ["DerivedFactoid", "Sibling"]


def test_a_rule_is_explained_with_what_it_writes():
    initialised(siblings)
    assert document("siblings").describe() == (
        "DerivedFactoid{label: 'Siblings', statements: [Sibling{label: 'Siblings', people: [a, b]}]} :-\n"
        "    ChildOf(n_0),\n"
        "    ChildOf(n_1),\n"
        "    child(n_0, v_a),\n"
        "    parent(n_0, v_p),\n"
        "    child(n_1, v_b),\n"
        "    parent(n_1, v_p),\n"
        "    unordered(a, b)."
    )


def test_a_filled_template_is_what_a_create_takes():
    m = initialised(siblings)
    a, b = person(), person()
    payload = fill(document("siblings").template, {"a": a, "b": b})
    assert payload == {
        "type": "DerivedFactoid",
        "label": "Siblings",
        "statements": [{"type": "Sibling", "label": "Siblings", "people": [a, b]}],
    }
    made = m.DerivedFactoid.Create.model_validate({**payload, "sources": []})
    assert [str(p.id) for p in made.statements[0].people] == [a["id"], b["id"]]
    assert made.statements[0].certainty == 100  # (what was not given has its default)


@no_type_check
def test_every_kind_of_field_can_be_given():
    fixed = person()

    def declared(m):
        one(
            m,
            lambda v: m.Sibling.Template(
                label=v["text"],
                people=[
                    v["a"],
                    m.InRole.Template(target=[v["p"]], role=v["text"]),
                    m.Either.Template(either=[v["a"], fixed]),
                    fixed,
                ],
                closest=Via(v["a"], m.Certainty.Template(certainty=v["n"])),
                when=m.When.Template(year=v["n"], about=True),
                certainty=v["n"],
                kind="half",
                tags=["x", v["text"]],
            ),
            lambda v: [
                m.ChildOf.Where(child=v["a"], parent=v["p"]),
                m.Sibling.Where(people=v["a"], certainty=v["n"], kind=v["text"]),
            ],
            block=[m.DerivedFactoid],
            variables={
                "a": Var[m.Person],
                "p": Var[m.Person],
                "text": Var[str],
                "n": Var[int],
            },
        )

    m = initialised(declared)
    checked = document()
    assert list(checked.head) == ["text", "a", "p", "n"]
    statement = checked.template.fields["statements"][0]
    assert statement.fields["closest"] == TVia(
        TVar("a", True), {"certainty": TVar("n", False)}
    )
    assert statement.fields["tags"] == (TValue("x"), TVar("text", False))
    assert statement.fields["kind"] == TValue("half")
    role = statement.fields["people"][1]
    # (a wrapper is checked as the class it is with its parameters, and named in a payload without them)
    assert role.model is m.InRole[m.Person] and role.type == "InRole"
    assert written_classes(checked.template) == [
        m.DerivedFactoid,
        m.Sibling,
        m.InRole[m.Person],
        m.InRole,
        m.Either[m.Person],
        m.Either,
        m.When,
    ]

    a, p = person(), person()
    payload = fill(checked.template, {"a": a, "p": p, "text": "elder", "n": 70})
    made = m.DerivedFactoid.Create.model_validate({**payload, "sources": []})
    sibling = made.statements[0]
    assert sibling.label == "elder" and sibling.certainty == 70
    assert sibling.tags == ["x", "elder"] and sibling.kind == "half"
    assert sibling.when.year == 70 and sibling.when.about is True
    assert sibling.closest.edge_properties.certainty == 70
    assert str(sibling.closest.id) == a["id"]
    assert [type(x).__name__ for x in sibling.people] == [
        "PersonReferenceSet",
        "InRole[Person]Create",
        "Either[Person]Create",
        "PersonReferenceSet",
    ]
    assert sibling.people[1].role == "elder"
    assert str(sibling.people[1].target[0].id) == p["id"]
    assert str(sibling.people[3].id) == fixed["id"]
    assert "elder" in describe(checked.template) or "text" in describe(checked.template)


@no_type_check
def test_a_template_can_write_inside_a_semantic_space():
    def declared(m):
        @rule
        def not_siblings(a: Var[m.Person], p: Var[m.Person]):
            return m.DerivedFactoid.Derive(
                label="No siblings",
                statements=[
                    m.Negative.Template(
                        contents=[m.Sibling.Template(label="x", people=[a, p])]
                    )
                ],
            ).when(m.ChildOf.Where(child=a, parent=p))

    m = initialised(declared)
    template = document("not_siblings").template
    assert [n.type for n in nodes_of(template)] == [
        "DerivedFactoid",
        "Negative",
        "Sibling",
    ]
    payload = fill(template, {"a": person(), "p": person()})
    made = m.DerivedFactoid.Create.model_validate({**payload, "sources": []})
    assert made.statements[0].type == "Negative"
    assert made.statements[0].contents[0].type == "Sibling"


def test_a_reference_set_is_a_reference():
    def declared(m):
        one(
            m,
            lambda v: m.Sibling.Template(
                label="x",
                people=[
                    v["a"],
                    m.Person.ReferenceSet(type="Person", id=uuid.UUID(int=7)),
                ],
            ),
        )

    initialised(declared)
    people = document().template.fields["statements"][0].fields["people"]
    assert people[1] == TRef("Person", str(uuid.UUID(int=7)))


@no_type_check
def test_a_label_template_makes_the_label_unnecessary():
    def declared(m):
        class Summary(Document, DerivedDocument):
            _meta = Document.Meta(label_template="Of {subject}")
            sources: list[DerivedFrom[m.Factoid]]
            subject: m.Person

        @rule
        def summaries(a: Var[m.Person], p: Var[m.Person]):
            return Summary.Derive(subject=a).when(m.ChildOf.Where(child=a, parent=p))

        return locals()

    initialised(declared)
    assert document("summaries").template.fields == {"subject": TVar("a", True)}


def test_a_label_that_is_needed_and_not_given_is_said():
    def declared(m):
        @rule
        def made(a: Var[m.Person], p: Var[m.Person]):
            return m.DerivedFactoid.Derive(statements=[]).when(
                m.ChildOf.Where(child=a, parent=p)
            )

    said = refused(declared)
    assert "Rule made: the head is not right" in said and "label" in said


# ---------------------------------------------------------------------------
# What a template refuses
# ---------------------------------------------------------------------------


def test_a_variable_of_a_class_the_relation_does_not_take():
    def declared(m):
        one(
            m,
            lambda v: m.Sibling.Template(label="x", people=[v["a"], v["where"]]),
            lambda v: [
                m.ChildOf.Where(child=v["a"], parent=v["p"]),
                m.Residence.Where(resident=v["a"], place=v["where"]),
            ],
            variables={"a": Var[m.Person], "p": Var[m.Person], "where": Var[m.Place]},
        )

    said = refused(declared)
    assert said == (
        "Rule made: DerivedFactoid.statements[0].people[1]: takes Either, InRole, Person: the variable 'where' can "
        "be a Place"
    )


def test_a_variable_that_could_be_of_a_class_the_relation_does_not_take():
    def declared(m):
        one(
            m,
            lambda v: m.Sibling.Template(label="x", people=[v["who"]]),
            lambda v: [m.Residence.Where(resident=v["who"])],
            variables={"who": Var[m.Agent]},
        )

    said = refused(declared)
    assert "DerivedFactoid.statements[0].people[0]" in said
    assert "the variable 'who' can be a Group" in said
    assert "(it is declared a Agent: declare it of a narrower class, Var[...])" in said


def test_a_variable_that_a_pattern_narrows_is_of_the_narrower_class():
    def declared(m):
        one(
            m,
            lambda v: m.Sibling.Template(label="x", people=[v["who"]]),
            lambda v: [
                m.Residence.Where(resident=v["who"]),
                m.Person.Where(is_=v["who"]),
            ],
            variables={"who": Var[m.Agent]},
        )

    initialised(declared)
    assert document().template.fields["statements"][0].fields["people"] == (
        TVar("who", True),
    )


def test_a_variable_of_a_trait_goes_where_the_trait_goes():
    def declared(m):
        one(
            m,
            lambda v: m.Residence.Template(label="x", resident=v["who"], place=v["at"]),
            lambda v: [m.Residence.Where(resident=v["who"], place=v["at"])],
            variables={"who": Var[m.Agent], "at": Var[m.Place]},
            block=[m.DerivedFactoid],
        )

    initialised(declared)
    assert document().head == {"who": ("var", "who"), "at": ("var", "at")}


def test_a_value_where_an_entity_goes_and_an_entity_where_a_value_goes():
    def a_value(m):
        one(
            m,
            lambda v: m.Sibling.Template(label="x", people=[v["n"]]),
            lambda v: [m.Sibling.Where(people=v["a"], certainty=v["n"])],
            variables={"a": Var[m.Person], "n": Var[int]},
            block=[m.DerivedFactoid],
        )

    said = refused(a_value)
    assert (
        "people[0]: takes Either, InRole, Person: the variable 'n' is a value (int)"
        in said
    )
    ModelRegistry._reset()

    def an_entity(m):
        one(m, lambda v: m.Sibling.Template(label="x", people=[], kind=v["a"]))

    said = refused(an_entity)
    assert "statements[0].kind: is a value (str): the variable 'a' is a Person" in said
    ModelRegistry._reset()

    def another_value(m):
        one(
            m,
            lambda v: m.Sibling.Template(label="x", people=[], kind=v["n"]),
            lambda v: [m.Sibling.Where(people=v["a"], certainty=v["n"])],
            variables={"a": Var[m.Person], "n": Var[int]},
            block=[m.DerivedFactoid],
        )

    assert "statements[0].kind: a Var[int] cannot be a str" in refused(another_value)


def test_a_value_that_is_not_right_is_said_where_it_is():
    def declared(m):
        one(m, lambda v: m.Sibling.Template(label="x", people=[], certainty="many"))

    said = refused(declared)
    assert (
        "Rule made: DerivedFactoid.statements[0].certainty: 'many' is not right" in said
    )
    ModelRegistry._reset()

    def a_constraint(m):
        one(
            m,
            lambda v: m.Sibling.Template(
                label="x", people=[], when=m.When.Template(year=-5)
            ),
        )

    said = refused(a_constraint)
    assert "statements[0].when.year: -5 is not right" in said and "greater than" in said
    ModelRegistry._reset()

    def in_a_list(m):
        one(m, lambda v: m.Sibling.Template(label="x", people=[], tags=["a", 3]))

    assert "statements[0].tags: ['a', 3] is not right" in refused(in_a_list)
    ModelRegistry._reset()

    def not_a_list(m):
        one(m, lambda v: m.Sibling.Template(label="x", people=[], tags="a"))

    assert "statements[0].tags: is a list" in refused(not_a_list)


def test_a_nested_template_of_a_class_the_field_does_not_take():
    def declared(m):
        one(
            m,
            lambda v: m.Sibling.Template(
                label="x", people=[m.Cousin.Template(label="y", people=[v["a"]])]
            ),
        )

    said = refused(declared)
    assert "statements[0].people[0]: takes Either, InRole, Person: not a Cousin" in said
    ModelRegistry._reset()

    def an_abstract_one(m):
        one(m, lambda v: m.Statement.Template(label="x"))

    said = refused(an_abstract_one)
    assert "DerivedFactoid.statements[0]: Statement is abstract" in said
    ModelRegistry._reset()

    def a_wrong_wrapper(m):
        one(
            m,
            lambda v: m.Sibling.Template(
                label="x", people=[m.Negative.Template(contents=[])]
            ),
        )

    assert "people[0]: takes Either, InRole, Person: not a Negative" in refused(
        a_wrong_wrapper
    )


def test_what_is_inside_a_wrapper_is_checked_as_what_the_wrapper_holds_there():
    def declared(m):
        one(
            m,
            lambda v: m.Sibling.Template(
                label="x", people=[m.InRole.Template(target=[v["at"]], role="r")]
            ),
            lambda v: [m.Residence.Where(resident=v["a"], place=v["at"])],
            variables={"a": Var[m.Person], "at": Var[m.Place]},
            block=[m.DerivedFactoid],
        )

    said = refused(declared)
    assert (
        "statements[0].people[0].target[0]: takes Person: the variable 'at' can be a Place"
        in said
    )


def test_a_list_and_a_single_relation_are_told_apart():
    def not_a_list(m):
        one(m, lambda v: m.Sibling.Template(label="x", people=v["a"]))

    assert "statements[0].people: is a list: give a list" in refused(not_a_list)
    ModelRegistry._reset()

    def a_list(m):
        one(m, lambda v: m.Residence.Template(label="x", resident=[v["a"]], place=None))

    assert "statements[0].resident: is one, not a list" in refused(a_list)
    ModelRegistry._reset()

    def none(m):
        one(m, lambda v: m.Residence.Template(label="x", resident=None, place=None))

    assert "statements[0].resident: has to be given" in refused(none)
    ModelRegistry._reset()

    def something_else(m):
        one(m, lambda v: m.Sibling.Template(label="x", people=[42]))

    said = refused(something_else)
    assert (
        "people[0]: takes a variable, a Template or a reference" in said
        and "42" in said
    )


def test_an_optional_field_can_be_given_as_none():
    def declared(m):
        one(
            m,
            lambda v: m.Sibling.Template(label="x", people=[], closest=None, when=None),
        )

    m = initialised(declared)
    fields = document().template.fields["statements"][0].fields
    assert fields["closest"] == TValue(None) and fields["when"] == TValue(None)
    payload = fill(document().template, {})
    assert m.DerivedFactoid.Create.model_validate({**payload, "sources": []})


def test_the_properties_of_an_edge_are_given_with_via():
    def needed(m):
        one(m, lambda v: m.Sibling.Template(label="x", people=[], closest=v["a"]))

    said = refused(needed)
    assert (
        "statements[0].closest: the relation has the properties of a Certainty (certainty)"
        in said
    )
    assert "Via(..., Certainty.Template(...))" in said
    ModelRegistry._reset()

    def the_wrong_edge(m):
        one(
            m,
            lambda v: m.Sibling.Template(
                label="x", people=[], closest=Via(v["a"], m.Note.Template(note="n"))
            ),
        )

    said = refused(the_wrong_edge)
    assert (
        "closest: the relation has no properties of a Note (it has those of Certainty)"
        in said
    )
    ModelRegistry._reset()

    def no_edge(m):
        one(
            m,
            lambda v: m.Sibling.Template(
                label="x", people=[Via(v["a"], m.Note.Template(note="n"))]
            ),
        )

    assert (
        "people[0]: the relation has no properties of a Note (its edge has none)"
        in refused(no_edge)
    )
    ModelRegistry._reset()

    def not_a_template(m):
        one(
            m,
            lambda v: m.Sibling.Template(
                label="x", people=[], closest=Via(v["a"], {"certainty": 3})
            ),
        )

    assert "the edge is the Template of an edge model" in refused(not_a_template)
    ModelRegistry._reset()

    def a_wrong_value(m):
        one(
            m,
            lambda v: m.Sibling.Template(
                label="x",
                people=[],
                closest=Via(v["a"], m.Certainty.Template(certainty="high")),
            ),
        )

    assert "closest (Certainty.certainty): 'high' is not right" in refused(
        a_wrong_value
    )
    ModelRegistry._reset()

    def a_target_that_is_not_one(m):
        one(
            m,
            lambda v: m.Sibling.Template(
                label="x",
                people=[],
                closest=Via("Smith", m.Certainty.Template(certainty=1)),
            ),
        )

    assert "the target is a variable or a reference, not 'Smith'" in refused(
        a_target_that_is_not_one
    )


def test_an_edge_with_no_property_that_must_be_given_needs_no_via():
    fixed = person()

    def declared(m):
        one(
            m,
            lambda v: m.Seen.Template(
                label="x",
                noted=[v["a"], Via(fixed, m.Note.Template(note="seen")), fixed],
            ),
        )

    m = initialised(declared)
    # (a `Create` wants the properties of such an edge said, if only as none)
    assert document().template.fields["statements"][0].fields["noted"] == (
        TVia(TVar("a", True), {}),
        TVia(TRef("Person", fixed["id"]), {"note": TValue("seen")}),
        TVia(TRef("Person", fixed["id"]), {}),
    )
    payload = fill(document().template, {"a": person()})
    made = m.DerivedFactoid.Create.model_validate({**payload, "sources": []})
    assert made.statements[0].noted[1].edge_properties.note == "seen"


def test_an_embedded_object_is_written_out():
    def a_variable(m):
        one(
            m,
            lambda v: m.Sibling.Template(label="x", people=[], when=v["a"]),
        )

    assert "when: an embedded object is written out in a template" in refused(
        a_variable
    )
    ModelRegistry._reset()

    def not_a_template(m):
        one(m, lambda v: m.Sibling.Template(label="x", people=[], when={"year": 1}))

    assert "when: takes When.Template(...), not {'year': 1}" in refused(not_a_template)
    ModelRegistry._reset()

    def another_class(m):
        one(
            m,
            lambda v: m.Sibling.Template(
                label="x", people=[], when=m.Certainty.Template(certainty=1)
            ),
        )

    assert "when: takes When: not a Certainty" in refused(another_class)


def test_a_reference_to_a_class_the_relation_does_not_take():
    def declared(m):
        one(
            m,
            lambda v: m.Sibling.Template(
                label="x", people=[{"type": "Place", "id": str(uuid.uuid4())}]
            ),
        )

    assert (
        "people[0]: takes Either, InRole, Person: not a reference to a Place"
        in refused(declared)
    )


def test_a_document_that_was_matched_cannot_be_put_in_another():
    def a_document(m):
        @rule
        def made(s: Var[m.ChildOf], a: Var[m.Person]):
            return m.DerivedFactoid.Derive(label="x", statements=[s]).when(
                m.ChildOf.Where(is_=s, child=a)
            )

    said = refused(a_document)
    assert "DerivedFactoid.statements[0]: the variable 's' is a ChildOf" in said
    assert "which is part of the document it was found in" in said


def test_a_variable_made_by_hand_is_not_one_of_the_rule():
    def declared(m):
        stranger = Var("a", m.Person)
        one(m, lambda v: m.Sibling.Template(label="x", people=[stranger]))

    assert "people[0]: Var('a', Person) is not a variable of the rule" in refused(
        declared
    )


def test_a_variable_of_the_template_that_no_pattern_binds():
    def declared(m):
        one(
            m,
            lambda v: m.Sibling.Template(label="x", people=[v["a"], v["b"]]),
            variables={"a": Var[m.Person], "p": Var[m.Person], "b": Var[m.Person]},
        )

    said = refused(declared)
    assert said == (
        "Rule made: the variable 'b' (of the template of DerivedFactoid) is in no pattern of the body"
    )


@no_type_check
def test_a_citation_in_a_template_is_left_empty_or_refused():
    def declared(m):
        class Remark(m.Statement):
            about: list[Cites[m.Factoid]]
            text: str

        one(m, lambda v: Remark.Template(label="x", text="t"))
        return locals()

    m = initialised(declared)
    assert list(m.Remark.Template.model_fields) == ["label", "text"]
    remark = document().template.fields["statements"][0]
    assert remark.fields["about"] == ()
    payload = fill(document().template, {})
    made = m.DerivedFactoid.Create.model_validate({**payload, "sources": []})
    assert made.statements[0].about == []
    ModelRegistry._reset()

    def required(m):
        class Remark(m.Statement):
            about: Cites[m.Factoid]

        one(m, lambda v: Remark.Template(label="x"))

    said = refused(required)
    assert (
        "statements[0].about: is a citation that has to be given, and a template writes none"
        in said
    )


def test_a_derived_document_rests_on_documents():
    def declared(m):
        @rule
        def made(a: Var[m.Person]):
            return m.DerivedFactoid.Derive(
                label="x", statements=[m.Sibling.Template(label="x", people=[a])]
            ).when(m.Person.Where(is_=a))

    said = refused(declared)
    assert "Rule made: no pattern of the body is of a document" in said
    assert "would have no source" in said


def test_nothing_is_derived_as_an_abstract_class():
    def declared(m):
        class Derivation(Document, DerivedDocument):
            _meta = Document.Meta(abstract=True)
            sources: list[DerivedFrom[m.Factoid]]

        return locals()

    m = initialised(declared)
    assert "Derive" not in vars(m.Derivation)


# ---------------------------------------------------------------------------
# When a rule counts as changed
# ---------------------------------------------------------------------------


def hash_of(statement, when=lambda m: {}):
    ModelRegistry._reset()
    initialised(lambda m: one(m, lambda v: statement(m, v), **when(m)))
    return document().hash


def test_a_changed_template_is_a_changed_rule():
    def first(m, v):
        return m.Sibling.Template(label="x", people=[v["a"], v["p"]])

    same = hash_of(first)
    assert hash_of(first) == same
    assert (
        hash_of(lambda m, v: m.Sibling.Template(label="x", people=[v["p"], v["a"]]))
        != same
    )
    assert (
        hash_of(lambda m, v: m.Sibling.Template(label="y", people=[v["a"], v["p"]]))
        != same
    )
    assert (
        hash_of(
            lambda m, v: m.Sibling.Template(
                label="x", people=[v["a"], v["p"]], kind="half"
            )
        )
        != same
    )
    assert (
        hash_of(lambda m, v: m.Cousin.Template(label="x", people=[v["a"], v["p"]]))
        != same
    )
    # (and what it may derive through, and where it reads)
    assert hash_of(first, lambda m: {"allow": [m.Negative]}) != same
    assert hash_of(first, lambda m: {"block": [m.DerivedFactoid]}) != same


def test_the_hash_of_a_rule_of_edges_is_not_changed_by_documents():
    """(a rule of edges has no template: its hash is made of what it was made of before)"""
    import hashlib
    import json

    from pangloss_derived.check import plain

    def declared(m):
        class SameParent(DerivedEdge):
            _meta = DerivedEdge.Meta(symmetric=True)
            first: Annotated[m.Person, SymmetricLabel("child")]
            second: Annotated[m.Person, SymmetricLabel("child")]

        @rule
        def same_parent(a: Var[m.Person], b: Var[m.Person], p: Var[m.Person]):
            return SameParent.Derive(first=a, second=b).when(
                m.ChildOf.Where(child=a, parent=p), m.ChildOf.Where(child=b, parent=p)
            )

    initialised(declared)
    checked = DerivedRegistry.checked["same_parent"]
    assert not checked.document and checked.template is None
    text = json.dumps(
        {
            "class": "SameParent",
            "fields": [
                ["first", "relation", "Person", "subject"],
                ["second", "relation", "Person", "object"],
            ],
            "head": plain(checked.head),
            "nodes": {
                name: [n.model.__name__, plain(n.filters), n.pattern, n.top]
                for name, n in checked.nodes.items()
            },
            "edges": plain(checked.edges),
            "values": plain(checked.values),
            "constraints": [],
            "patterns": checked.patterns,
            "symmetric": checked.symmetric,
            "types": [],
            "blocked": sorted(checked.blocked),
            "transparent": sorted(checked.transparent),
            "spaces": checked.spaces,
            "grounds": checked.grounds,
            "statuses": sorted(checked.statuses),
            "exclusive": sorted(checked.exclusive),
        },
        sort_keys=True,
        default=str,
    )
    assert checked.hash == hashlib.sha256(text.encode()).hexdigest()[:16]


# ---------------------------------------------------------------------------
# Each document once: unordered
# ---------------------------------------------------------------------------


def test_unordered_matches_each_pair_once():
    initialised(siblings)
    text, _ = query("siblings")
    assert "v_a.id < v_b.id" in text
    assert document("siblings").unordered == (("a", "b"),)


def test_unordered_is_refused_where_the_body_is_not_the_same_with_the_two_swapped():
    def declared(m):
        @rule
        def made(a: Var[m.Person], b: Var[m.Person]):
            return m.DerivedFactoid.Derive(
                label="x", statements=[m.Sibling.Template(label="x", people=[a, b])]
            ).when(m.ChildOf.Where(child=a, parent=b), unordered(a, b))

    said = refused(declared)
    assert (
        "Rule made: unordered(a, b): the body is not the same with a and b swapped"
        in said
    )
    assert "one order of a pair would be found and the other lost" in said


def test_unordered_with_distinct_and_other_constraints_of_the_pair():
    def declared(m):
        @rule
        def made(a: Var[m.Person], b: Var[m.Person], p: Var[m.Person]):
            return m.DerivedFactoid.Derive(
                label="x", statements=[m.Sibling.Template(label="x", people=[a, b])]
            ).when(
                m.ChildOf.Where(child=a, parent=p),
                m.ChildOf.Where(child=b, parent=p),
                distinct(b, a),
                distinct(a, p),
                distinct(b, p),
                unordered(b, a),
            )

    initialised(declared)
    assert document().unordered == (("b", "a"),)
    assert "v_b.id < v_a.id" in query("made")[0]


def test_unordered_is_of_two_nodes():
    def values(m):
        @rule
        def made(a: Var[m.Person], x: Var[int], y: Var[int]):
            return m.DerivedFactoid.Derive(
                label="x", statements=[m.Sibling.Template(label="x", people=[a])]
            ).when(
                m.Sibling.Where(people=a, certainty=x),
                m.Sibling.Where(people=a, certainty=y),
                unordered(x, y),
                block=[m.DerivedFactoid],
            )

    said = refused(values)
    assert "unordered(x, y): x is a value (int)" in said
    ModelRegistry._reset()

    def one_variable(m):
        @rule
        def made(a: Var[m.Person], p: Var[m.Person]):
            return m.DerivedFactoid.Derive(
                label="x", statements=[m.Sibling.Template(label="x", people=[a])]
            ).when(m.ChildOf.Where(child=a, parent=p), unordered(a, a))

    assert "unordered(a, a): the two are one variable" in refused(one_variable)


def test_a_rule_that_would_derive_each_document_twice_is_told(caplog):
    def declared(m):
        @rule
        def made(a: Var[m.Person], b: Var[m.Person], p: Var[m.Person]):
            return m.DerivedFactoid.Derive(
                label="x", statements=[m.Sibling.Template(label="x", people=[a, b])]
            ).when(
                m.ChildOf.Where(child=a, parent=p),
                m.ChildOf.Where(child=b, parent=p),
                distinct(a, b),
            )

    with caplog.at_level(logging.WARNING, logger="pangloss.derived"):
        initialised(declared)
    (warning,) = [r.getMessage() for r in caplog.records if "swapped" in r.getMessage()]
    assert "Rule made: the body is the same with a and b swapped" in warning
    assert "add unordered(a, b)" in warning
    assert "v_a.id < v_b.id" not in query("made")[0]


def test_a_rule_that_says_unordered_or_is_not_symmetric_is_not_told(caplog):
    with caplog.at_level(logging.WARNING, logger="pangloss.derived"):
        initialised(siblings)
        ModelRegistry._reset()

        # (the body tells the two apart; and a variable that is not in the template gives no second document)
        def declared(m):
            @rule
            def made(a: Var[m.Person], b: Var[m.Person], p: Var[m.Person]):
                return m.DerivedFactoid.Derive(
                    label="x", statements=[m.Cousin.Template(label="x", people=[a, p])]
                ).when(
                    m.ChildOf.Where(child=a, parent=p),
                    m.ChildOf.Where(child=b, parent=p),
                )

        initialised(declared)
    assert not [r for r in caplog.records if "swapped" in r.getMessage()]


@no_type_check
def test_unordered_in_a_rule_of_edges():
    def declared(m):
        class SameParent(DerivedEdge):
            _meta = DerivedEdge.Meta(symmetric=True)
            first: Annotated[m.Person, SymmetricLabel("child")]
            second: Annotated[m.Person, SymmetricLabel("child")]

        @rule
        def same_parent(a: Var[m.Person], b: Var[m.Person], p: Var[m.Person]):
            return SameParent.Derive(first=a, second=b).when(
                m.ChildOf.Where(child=a, parent=p),
                m.ChildOf.Where(child=b, parent=p),
                distinct(a, b),
                unordered(a, b),
            )

    initialised(declared)
    checked = DerivedRegistry.checked["same_parent"]
    # (`distinct` of the two, in either order, leaves the body the same with them swapped)
    assert checked.symmetric_body and checked.unordered == (("a", "b"),)


# ---------------------------------------------------------------------------
# What a document may be derived through
# ---------------------------------------------------------------------------


@no_type_check
def edges_too(m):
    class Related(DerivedEdge):
        _meta = DerivedEdge.Meta(symmetric=True)
        first: Annotated[m.Person, SymmetricLabel("relative")]
        second: Annotated[m.Person, SymmetricLabel("relative")]

    @rule
    def related(a: Var[m.Person], p: Var[m.Person]):
        return Related.Derive(first=a, second=p).when(
            m.ChildOf.Where(child=a, parent=p)
        )

    return Related


def test_a_document_is_not_derived_through_what_qualifies_unless_the_rule_allows_it():
    def declared(m):
        edges_too(m)
        siblings(m)

    initialised(declared)
    edges, documents = DerivedRegistry.checked["related"], document("siblings")
    # (a fact from a `Negative` statement has a context label; a document would plainly say what was denied)
    assert "Negative" not in edges.blocked and "Negative" in documents.blocked
    assert "Guess" not in edges.blocked and "Guess" in documents.blocked
    # (what is read through as if it were not there is, by both)
    assert {"InRole", "Either"} <= documents.transparent
    assert {"InRole", "Either"} <= edges.transparent
    assert "$blocked" in query("siblings")[0] and "$blocked" not in query("related")[0]
    assert query("siblings")[1]["blocked"] == ["Guess", "Negative"]


def test_what_a_rule_allows_it_derives_through_and_records():
    m = initialised(lambda m: siblings(m, allow=[m.Negative]))
    checked = document("siblings")
    assert checked.blocked == {"Guess"}
    assert "Negative" not in checked.transparent
    found = Found()
    found.add(
        checked,
        {
            "fields": ["a-id", "b-id"],
            "nodes": ["s1", "s2"],
            "heads": ["f1", "f2"],
            "spaces": [["Negative"], []],
            "through": [["InRole"], [], [], []],
            "props": [{}, {}, {}, {}],
            "paths": [[], [], [], []],
            "walks": [
                [
                    "s1",
                    [
                        {
                            "kind": "document",
                            "type": "Factoid",
                            "id": "f1",
                            "field": "statements",
                        },
                        {
                            "kind": "space",
                            "type": "Negative",
                            "id": "n1",
                            "field": "contents",
                        },
                    ],
                    "ChildOf",
                ],
                ["s2", [], "ChildOf"],
            ],
            "ways": [[["InRole", "r1"]], [], [], []],
            "starts": [None, None, None, None],
        },
    )
    (justification,) = found.documents.values()
    assert justification.context_labels == ["Negative"]
    assert m.Negative.__name__ == "Negative"


def test_block_and_allow_name_what_they_can():
    def an_entity(m):
        siblings(m, block=[m.Person])

    said = refused(an_entity)
    assert (
        "Rule siblings: block=[Person]: block names a semantic space or other wrapper"
        in said
    )
    assert "or a document class" in said
    ModelRegistry._reset()

    def allowed(m):
        siblings(m, allow=[m.Factoid])

    assert "allow=[Factoid]: allow names a semantic space or other wrapper" in refused(
        allowed
    )


# ---------------------------------------------------------------------------
# What a justification of a document is
# ---------------------------------------------------------------------------


def row(**changes):
    return {
        "fields": ["a-id", "b-id"],
        "nodes": ["s1", "s2"],
        "heads": ["f2", "f1"],
        "spaces": [[], []],
        "through": [[], [], [], []],
        "props": [{}, {}, {}, {}],
        "paths": [[], [], [], []],
        "walks": [["s1", [], "ChildOf"], ["s2", [], "ChildOf"]],
        "ways": [[], [], [], []],
        "starts": [None, None, None, None],
        **changes,
    }


def test_each_justification_is_a_document_with_its_sources_and_values():
    initialised(siblings)
    checked = document("siblings")
    found = Found()
    found.add(checked, row())
    found.add(checked, row())  # (the same again is the same one)
    found.add(checked, row(nodes=["s1", "s3"], heads=["f2", "f2"]))
    found.add(checked, row(fields=["a-id", "c-id"]))
    assert found.facts == {} and found.rows == 4
    first, same_people, others = found.documents.values()
    assert first.rule == "siblings" and first.rule_hash == checked.hash
    assert first.fact == "" and first.values == {"a": "a-id", "b": "b-id"}
    assert first.nodes == ["s1", "s2"] and first.sources == ["f1", "f2"]
    assert first.context_labels == []
    # (the same siblings found in another source are another document: one for each justification)
    assert same_people.values == first.values and same_people.key != first.key
    assert same_people.sources == ["f2"]
    assert (
        others.key != first.key
        and others.values == {"a": "a-id", "c": "c-id"}
        or (others.values == {"a": "a-id", "b": "c-id"})
    )
    payload = fill(
        checked.template,
        {k: {"type": "Person", "id": v} for k, v in first.values.items()},
    )
    assert payload["statements"][0]["people"] == [
        {"type": "Person", "id": "a-id"},
        {"type": "Person", "id": "b-id"},
    ]


@no_type_check
def test_the_sources_of_a_document_are_documents_not_the_entities_of_its_patterns():
    def declared(m):
        @rule
        def made(a: Var[m.Person], p: Var[m.Person]):
            return m.DerivedFactoid.Derive(
                label="x", statements=[m.Sibling.Template(label="x", people=[a, p])]
            ).when(
                m.ChildOf.Where(child=a, parent=p),
                m.Person.Where(is_=p),
            )

    initialised(declared)
    checked = document()
    assert [n.kind for n in checked.tops] == ["document"]
    found = Found()
    found.add(
        checked,
        {
            "fields": ["a-id", "p-id"],
            "nodes": ["s1", "p-id"],
            "heads": ["f1", "p-id"],
            "spaces": [[], []],
            "through": [[], []],
            "props": [{}, {}],
            "paths": [[], []],
            "walks": [["s1", [], "ChildOf"]],
            "ways": [[], []],
            "starts": [None, None],
        },
    )
    (justification,) = found.documents.values()
    assert justification.sources == ["f1"] and justification.heads == ["f1", "p-id"]


# ---------------------------------------------------------------------------
# Rules that read what rules write: never in a loop
# ---------------------------------------------------------------------------


@no_type_check
def cousins(m, **when):
    @rule
    def cousins(
        s: Var[m.Sibling],
        a: Var[m.Person],
        b: Var[m.Person],
        c: Var[m.Person],
        d: Var[m.Person],
    ):
        """The children of siblings are cousins"""
        return m.DerivedFactoid.Derive(
            label="Cousins",
            statements=[m.Cousin.Template(label="Cousins", people=[c, d])],
        ).when(
            *pair(m.Sibling, s, a, b),
            m.ChildOf.Where(child=c, parent=a),
            m.ChildOf.Where(child=d, parent=b),
            **when,
        )


def test_a_rule_does_not_read_itself_by_the_class_of_its_document():
    """`siblings` reads `ChildOf` and writes a `Sibling`, in a document whose field could hold any statement: by
    class it would read what it writes, and a project with one derived class could have no rule at all"""
    initialised(siblings)
    assert DerivedRegistry.readers == {"siblings": []}
    assert DerivedRegistry.order == ["siblings"]


def test_a_rule_that_reads_what_it_writes_is_refused():
    def declared(m):
        @rule
        def echo(s: Var[m.Statement], a: Var[m.Person]):
            return m.DerivedFactoid.Derive(
                label="x", statements=[m.Sibling.Template(label="x", people=[a])]
            ).when(m.Residence.Where(resident=a), m.Statement.Where(is_=s))

    said = refused(declared, chained=True)
    assert said.startswith("Rule echo reads what it writes: ")
    assert (
        "echo writes a Sibling (in a DerivedFactoid), which a pattern of echo (Statement) can match"
        in said
    )
    assert "A derived document is not derived from itself" in said
    assert "block=[DerivedFactoid] in its .when(...)" in said


def test_blocking_the_derived_class_is_the_way_out():
    def declared(m):
        @rule
        def echo(s: Var[m.Statement], a: Var[m.Person]):
            return m.DerivedFactoid.Derive(
                label="x", statements=[m.Sibling.Template(label="x", people=[a])]
            ).when(
                m.Residence.Where(resident=a),
                m.Statement.Where(is_=s),
                block=[m.DerivedFactoid],
            )

    initialised(declared)
    checked = document("echo")
    assert checked.blocked_heads == {"DerivedFactoid"}
    assert DerivedRegistry.readers == {"echo": []}
    text, _ = query("echo")
    assert text.count("AND NOT hd_") == 2
    assert "NOT hd_n_0:`DerivedFactoid`" in text or "NOT hd_n_0:DerivedFactoid" in text
    assert "not in(DerivedFactoid)" in checked.describe()


def test_a_loop_of_two_rules_is_refused_and_names_both():
    def declared(m):
        @rule
        def up(s: Var[m.Sibling], a: Var[m.Person], b: Var[m.Person]):
            return m.DerivedFactoid.Derive(
                label="x", statements=[m.Cousin.Template(label="x", people=[a, b])]
            ).when(*pair(m.Sibling, s, a, b))

        @rule
        def down(s: Var[m.Cousin], a: Var[m.Person], b: Var[m.Person]):
            return m.DerivedFactoid.Derive(
                label="x", statements=[m.Sibling.Template(label="x", people=[a, b])]
            ).when(*pair(m.Cousin, s, a, b))

    said = refused(declared, chained=True)
    assert said.startswith("Rules up -> down -> up read what they write, in a loop: ")
    assert (
        "up writes a Cousin (in a DerivedFactoid), which a pattern of down (Cousin) can match"
        in said
    )
    assert (
        "down writes a Sibling (in a DerivedFactoid), which a pattern of up (Sibling) can match"
        in said
    )


def test_a_chain_is_allowed_and_built_in_order():
    def declared(m):
        # (declared first, built second: it reads what `siblings` writes)
        cousins(m)
        siblings(m)
        edges_too(m)

    initialised(declared, chained=True)
    assert DerivedRegistry.readers == {"cousins": [], "siblings": ["cousins"]}
    assert DerivedRegistry.order == ["siblings", "cousins", "related"]
    assert list(DerivedRegistry.documents) == ["cousins", "siblings"]
    assert list(DerivedRegistry.checked) == ["related"]


@no_type_check
def test_a_rule_of_edges_that_reads_derived_documents_comes_after_their_rule():
    def declared(m):
        class Kin(DerivedEdge):
            _meta = DerivedEdge.Meta(symmetric=True)
            first: Annotated[m.Person, SymmetricLabel("kin")]
            second: Annotated[m.Person, SymmetricLabel("kin")]

        @rule
        def kin(s: Var[m.Sibling], a: Var[m.Person], b: Var[m.Person]):
            return Kin.Derive(first=a, second=b).when(*pair(m.Sibling, s, a, b))

        @rule
        def plain_kin(s: Var[m.Sibling], a: Var[m.Person], b: Var[m.Person]):
            return Kin.Derive(first=a, second=b).when(
                *pair(m.Sibling, s, a, b), block=[m.DerivedFactoid]
            )

        siblings(m)

    initialised(declared)
    assert DerivedRegistry.readers == {"siblings": ["kin"]}
    assert DerivedRegistry.order == ["siblings", "kin", "plain_kin"]
    # (a rule of edges can keep to what people wrote, as a rule of documents can)
    assert DerivedRegistry.checked["plain_kin"].blocked_heads == {"DerivedFactoid"}
    assert DerivedRegistry.checked["kin"].blocked_heads == frozenset()
    assert "DerivedFactoid" in query("plain_kin")[0]
    assert "DerivedFactoid" not in query("kin")[0]
    assert (
        DerivedRegistry.checked["plain_kin"].hash != DerivedRegistry.checked["kin"].hash
    )


def test_a_rule_reads_a_wrapper_or_a_part_a_template_writes():
    """What a rule writes is every node of its template: one inside a semantic space as well"""

    def declared(m):
        @rule
        def denied(a: Var[m.Person], p: Var[m.Person]):
            return m.DerivedFactoid.Derive(
                label="x",
                statements=[
                    m.Negative.Template(
                        contents=[m.Cousin.Template(label="x", people=[a, p])]
                    )
                ],
            ).when(m.ChildOf.Where(child=a, parent=p))

        @rule
        def reader(s: Var[m.Cousin], a: Var[m.Person], b: Var[m.Person]):
            return m.DerivedFactoid.Derive(
                label="x", statements=[m.Sibling.Template(label="x", people=[a, b])]
            ).when(*pair(m.Cousin, s, a, b), allow=[m.Negative])

    initialised(declared, chained=True)
    assert DerivedRegistry.readers == {"denied": ["reader"], "reader": []}


# ---------------------------------------------------------------------------
# The sources a rule's documents can have
# ---------------------------------------------------------------------------


def test_a_pattern_that_can_be_a_document_of_its_own_is_refused():
    said = refused(siblings, statements_alone=True)
    assert said.startswith(
        "Rule siblings: a pattern of ChildOf can be found in a ChildOf (a document of its own), which "
        "DerivedFactoid.sources (DerivedFrom[Factoid]) does not take as a source."
    )
    assert "Let the field take it (DerivedFrom[Factoid | ChildOf])" in said
    assert "(block=[ChildOf] in its .when(...))" in said
    assert "say so on its class (_meta = Document.Meta(create_directly=False))" in said


def test_blocking_the_class_or_letting_the_field_take_it_is_accepted():
    initialised(lambda m: siblings(m, block=[m.ChildOf]), statements_alone=True)
    assert document("siblings").blocked_heads == {"ChildOf"}
    ModelRegistry._reset()
    initialised(
        siblings, statements_alone=True, sources=lambda m: m.Factoid | m.Statement
    )
    assert document("siblings").blocked_heads == frozenset()
    ModelRegistry._reset()
    # (blocking a parent blocks the classes below it)
    initialised(lambda m: siblings(m, block=[m.Statement]), statements_alone=True)
    assert document("siblings").blocked_heads == {"Statement"}


@no_type_check
def test_another_class_that_can_hold_the_pattern_is_refused():
    def declared(m):
        class Letter(Document):
            says: list[m.Statement]

        siblings(m)

    said = refused(declared)
    assert (
        "a pattern of ChildOf can be found in a Letter (which can hold a ChildOf)"
        in said
    )
    assert "DerivedFrom[Factoid | Letter]" in said and "block=[Letter]" in said
    assert "create_directly" not in said


def test_a_rule_that_reads_derived_documents_needs_a_field_that_takes_them():
    def declared(m):
        siblings(m)
        cousins(m)

    said = refused(declared)
    assert said.startswith(
        "Rule cousins: a pattern of Sibling can be found in a DerivedFactoid (the rule siblings writes a Sibling "
        "in one), which DerivedFactoid.sources (DerivedFrom[Factoid]) does not take as a source."
    )
    assert "DerivedFrom[Factoid | DerivedFactoid]" in said
    assert "block=[DerivedFactoid]" in said
    ModelRegistry._reset()

    # (only a rule that does read derived documents has to take them: `siblings` alone was accepted above)
    def reading_only_people(m):
        siblings(m)
        cousins(m, block=[m.DerivedFactoid])

    initialised(reading_only_people)
    assert DerivedRegistry.readers == {"siblings": [], "cousins": []}


@no_type_check
def test_two_derived_classes_each_with_its_own_sources():
    def declared(m):
        class Summary(Document, DerivedDocument):
            _derived_document_meta = DerivedDocumentMeta(max_per_seed=7)
            sources: list[DerivedFrom[m.DerivedFactoid]]
            about: list[m.Person]

        siblings(m)

        @rule
        def summaries(s: Var[m.Sibling], a: Var[m.Person], b: Var[m.Person]):
            return Summary.Derive(label="Summary", about=[a, b]).when(
                *pair(m.Sibling, s, a, b), block=[m.Factoid]
            )

        return locals()

    m = initialised(declared)
    assert DerivedRegistry.readers == {"siblings": ["summaries"], "summaries": []}
    assert document("summaries").max_per_seed == 7
    assert document("summaries").model is m.Summary
    ModelRegistry._reset()

    def not_blocked(m):
        class Summary(Document, DerivedDocument):
            sources: list[DerivedFrom[m.DerivedFactoid]]
            about: list[m.Person]

        siblings(m)

        @rule
        def summaries(s: Var[m.Sibling], a: Var[m.Person], b: Var[m.Person]):
            return Summary.Derive(label="Summary", about=[a, b]).when(
                *pair(m.Sibling, s, a, b)
            )

    said = refused(not_blocked)
    assert "Rule summaries: a pattern of Sibling can be found in a Factoid" in said


def test_the_registry_is_emptied_with_the_models():
    initialised(siblings)
    assert DerivedRegistry.documents and DerivedRegistry.order
    ModelRegistry._reset()
    assert DerivedRegistry.documents == {} and DerivedRegistry.order == []
    assert DerivedRegistry.readers == {} and DerivedRegistry.all_checked() == {}


# ---------------------------------------------------------------------------
# What the worker writes (without a database: what a document is to be, its ids, what is left on its head)
# ---------------------------------------------------------------------------


def test_the_id_of_a_document_is_of_its_key_and_its_class():
    from pangloss_derived.written import document_id

    first = document_id("key", "DerivedFactoid")
    assert first == document_id("key", "DerivedFactoid")
    assert uuid.UUID(first).version == 5
    # (another key, another class, or the id being another's: another id)
    others = {
        document_id("other", "DerivedFactoid"),
        document_id("key", "DerivedLetter"),
        document_id("key", "DerivedFactoid", 1),
        document_id("key", "DerivedFactoid", 2),
    }
    assert len(others) == 4 and first not in others
    assert document_id("key", "DerivedFactoid", 0) == first


@no_type_check
def test_the_nodes_of_a_document_written_by_the_worker_have_ids_worked_out():
    from pangloss_derived.documents import node_id

    def with_roles(m):
        one(
            m,
            lambda v: m.Sibling.Template(
                label="S",
                people=[
                    v["a"],
                    m.InRole[m.Person].Template(role="elder", target=[v["p"]]),
                ],
                when=m.When.Template(year=1800),
            ),
        )

    m = initialised(with_roles)
    a, p, source = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    payload = fill(
        document().template,
        {"a": {"type": "Person", "id": a}, "p": {"type": "Person", "id": p}},
    )
    payload["sources"] = [
        {"type": "PGUnprotectedCitation", "target_type": "Factoid", "target_id": source}
    ]
    id = uuid.uuid4()

    def written(make):
        with writing_derived("made", id=id):
            return make()._to_db_model()

    created = written(lambda: m.DerivedFactoid.Create.model_validate(payload))
    assert created.id == id
    (statement,) = created.statements
    assert statement.id == node_id(id, "statements/0")
    # (a reference to an entity is the entity's id; the wrapper around one is a node of the document)
    assert statement.people[0].id == a
    assert statement.people[1].id == node_id(id, "statements/0/people/1")
    assert statement.people[1].target[0].id == p
    assert statement.when.id == node_id(id, "statements/0/when")
    assert created.sources[0].id == node_id(id, "sources/0")
    assert created.sources[0].target_id == source
    # (an update gives each node the id it had: nothing that read the document loses what it found)
    updated = written(
        lambda: m.DerivedFactoid.Update.model_validate({**payload, "id": id})
    )
    assert updated.id == id
    assert updated.statements[0].id == statement.id
    assert updated.statements[0].people[1].id == statement.people[1].id
    assert updated.statements[0].when.id == statement.when.id
    assert updated.sources[0].id == created.sources[0].id
    # (another document: other ids, each as surely its own)
    other = uuid.uuid4()
    assert node_id(other, "statements/0") != node_id(id, "statements/0")
    assert node_id(id, "statements/1") != node_id(id, "statements/0")
    # (without an id given, as a test or a script writes one: the ids are made as for any document)
    with writing_derived("made"):
        free = m.DerivedFactoid.Create.model_validate(payload)._to_db_model()
    assert free.id != id and free.statements[0].id != statement.id
    assert free.derived_by == "made"


@no_type_check
def test_what_the_worker_leaves_on_the_head_of_a_document():
    from pangloss_derived.documents import CONTENT, head_properties

    m = initialised(siblings)
    assert head_properties(m.DerivedFactoid) == {}
    with writing_derived("siblings", published=False, content="abc"):
        assert head_properties(m.DerivedFactoid) == {"published": False, CONTENT: "abc"}
        # (only of a derived document)
        assert head_properties(m.Factoid) == {}
        assert hooks.properties_for_new_head(m.DerivedFactoid) == {
            "published": False,
            CONTENT: "abc",
        }
        assert hooks.properties_for_updated_head(m.DerivedFactoid) == {
            "published": False,
            CONTENT: "abc",
        }
    with writing_derived("siblings", published=True):
        assert head_properties(m.DerivedFactoid) == {"published": True}
    with writing_derived("siblings"):
        assert head_properties(m.DerivedFactoid) == {}


@no_type_check
def test_what_a_document_is_to_be_is_its_template_its_sources_and_their_state():
    from pangloss_derived.written import LeftOut, entity_variables, wanted

    def certain(m):
        one(
            m,
            lambda v: m.Sibling.Template(
                label="S", people=[v["a"], v["p"]], certainty=v["c"]
            ),
            lambda v: [
                m.ChildOf.Where(child=v["a"], parent=v["p"]),
                m.Sibling.Where(people=v["a"], certainty=v["c"]),
            ],
            variables={"a": Var[m.Person], "p": Var[m.Person], "c": Var[int]},
            # (it writes a `Sibling` and reads one: only what people wrote)
            block=[m.DerivedFactoid],
        )

    m = initialised(certain, chained=True)
    checked = document()
    assert entity_variables(checked.template) == {"a", "p"}
    a, p, one_id, two_id = (str(uuid.uuid4()) for _ in range(4))
    state = {
        "values": json.dumps({"a": a, "p": p, "c": 80}),
        "sources": [two_id, one_id],
        "context_labels": ["Negative"],
    }

    def node(type_name, **more):
        return {
            "type": type_name,
            "deleted": False,
            "published": True,
            "derived_context": None,
            "merged_into": None,
            **more,
        }

    nodes = {
        a: node("Person"),
        p: node("Person"),
        one_id: node("Factoid"),
        two_id: node("DerivedFactoid", derived_context=["Guess"]),
    }
    want = wanted(checked, state, nodes)
    assert want.payload["type"] == "DerivedFactoid" and want.payload["label"] == "Made"
    (statement,) = want.payload["statements"]
    assert statement["people"] == [
        {"type": "Person", "id": a},
        {"type": "Person", "id": p},
    ]
    assert statement["certainty"] == 80
    # (its sources in the order of their ids, each as its class; a citation that does not protect)
    assert want.payload["sources"] == [
        {
            "type": "PGUnprotectedCitation",
            "target_type": nodes[s]["type"],
            "target_id": s,
        }
        for s in sorted([one_id, two_id])
    ]
    # (what it passed through, and what the derived document it rests on passed through)
    assert want.context == ["Guess", "Negative"]
    assert want.published is True
    m.DerivedFactoid.Create.model_validate(want.payload)

    # (the same again is the same content; anything that changes what is written is another)
    assert wanted(checked, state, nodes).content == want.content
    other = {**state, "values": json.dumps({"a": a, "p": p, "c": 60})}
    assert wanted(checked, other, nodes).content != want.content
    plain = {**nodes, two_id: node("DerivedFactoid")}
    assert wanted(checked, state, plain).content != want.content
    assert wanted(checked, state, plain).context == ["Negative"]
    # (whether it is published is not content: a document published later is not written again)
    hidden = {**nodes, one_id: node("Factoid", published=False)}
    unpublished = wanted(checked, state, hidden)
    assert unpublished.published is False and unpublished.content == want.content

    # (something it rests on, or names, is gone: not written now)
    for gone in (
        {**nodes, one_id: node("Factoid", deleted=True)},
        {k: v for k, v in nodes.items() if k != two_id},
        {**nodes, a: node("Person", deleted=True)},
        {**nodes, p: node("Person", merged_into=str(uuid.uuid4()))},
        {k: v for k, v in nodes.items() if k != a},
    ):
        with pytest.raises(LeftOut):
            wanted(checked, state, gone)


@no_type_check
def test_a_write_by_the_worker_leaves_work_only_for_a_rule_that_reads_it():
    from pangloss_derived import pending_work_of

    def chain(m):
        siblings(m)

        @rule
        def cousins(s: Var[m.Sibling], a: Var[m.Person], b: Var[m.Person]):
            return m.DerivedFactoid.Derive(
                label="C", statements=[m.Cousin.Template(label="C", people=[a, b])]
            ).when(*pair(m.Sibling, s, a, b), unordered(a, b))

    m = initialised(chain, chained=True)
    assert DerivedRegistry.readers["siblings"] == ["cousins"]
    assert not DerivedRegistry.readers.get("cousins")
    # (a write by a person of anything a rule can be triggered by)
    assert pending_work_of(m.Factoid) == ["derive"]
    assert pending_work_of(m.DerivedFactoid) == ["derive"]
    assert pending_work_of(m.Place) == []
    with writing_derived("siblings"):
        assert pending_work_of(m.DerivedFactoid) == ["derive"]
    with writing_derived("cousins"):
        # (nothing reads what `cousins` writes)
        assert pending_work_of(m.DerivedFactoid) == []
        # (only its own documents: another write made meanwhile is a write)
        assert pending_work_of(m.Factoid) == ["derive"]
    # (a write "as the worker" for a rule there is not, as a test makes: as a person's)
    with writing_derived("some_rule"):
        assert pending_work_of(m.DerivedFactoid) == ["derive"]


@no_type_check
def test_the_references_of_derived_documents_do_not_count():
    from pangloss_derived import uncounted_classes

    class DerivedBase(Document, DerivedDocument):
        _meta = Document.Meta(abstract=True)

    initialised(siblings)
    assert uncounted_classes() == ["DerivedFactoid"]
    assert hooks.uncounted_classes() == ["DerivedFactoid"]


@no_type_check
def test_which_classes_a_citation_is_looked_at_for():
    from pangloss_derived.citing import classes_inside, is_derived

    initialised(siblings)
    # (the derived classes and what the templates write: a citation of anything else makes no read)
    assert classes_inside() == {"DerivedFactoid", "Sibling"}
    assert is_derived("DerivedFactoid") and not is_derived("Factoid")
    assert not is_derived(None) and not is_derived("Nothing")


@no_type_check
def test_a_citation_of_what_no_rule_writes_is_not_resolved_and_nothing_is_read():
    import asyncio

    from pangloss_derived import resolve_citation

    initialised(siblings)
    # (no database here: a read would fail)
    assert asyncio.run(resolve_citation("Factoid", uuid.uuid4(), None)) is None
    assert asyncio.run(resolve_citation("ChildOf", uuid.uuid4(), None)) is None


@no_type_check
def test_a_derived_document_class_asks_for_the_cited_basis():
    from pangloss_models import ModelRegistry, citations

    from pangloss_derived.documents import forget_cited_basis

    assert citations._basis_enabled is False

    class Person(Entity):
        pass

    class Factoid(Document):
        about: list[Person]

    class Essay(Document):
        see: list[Cites[Factoid]]

    # (a project with citations and no derived document: as it was)
    assert citations._basis_enabled is False

    class DerivedFactoid(Document, DerivedDocument):
        sources: list[DerivedFrom[Factoid]]
        about: list[Person]

    assert citations._basis_enabled is True
    initialise(bind_database=False)
    assert "PGCitedBasis" in ModelRegistry._model_dict
    assert sorted(
        o.annotated_type.__name__ for o in Essay._meta.fields["see"].type_options
    ) == ["PGCitation", "PGCitedBasis"]
    # (and what does not protect takes none: the worker's own field)
    assert [
        o.annotated_type.__name__
        for o in DerivedFactoid._meta.fields["sources"].type_options
    ] == ["PGUnprotectedCitation"]
    # (the models emptied: it goes with them)
    ModelRegistry._reset()
    assert citations._basis_enabled is False
    forget_cited_basis()
    assert citations._basis_enabled is False


@no_type_check
def test_the_counts_of_documents_add_up():
    from pangloss_derived.written import Counts

    total = Counts(made=1, same=2)
    total.add(Counts(made=2, deleted=1, left_out=4, failed=1))
    assert (total.made, total.deleted, total.same, total.left_out, total.failed) == (
        3,
        1,
        2,
        4,
        1,
    )
    # (what was written: not what was looked at and left)
    assert total.written == 4


@no_type_check
def test_a_template_does_not_ask_for_a_parent_field_its_class_narrows():
    """A field of the parent class that a field of the subclass narrows and fills (`subclasses_parent_fields`) is
    not a field of the subclass: its template neither needs it nor takes it"""
    from pangloss_models import FieldSubclassing, RelationConfig

    class Person(Entity):
        pass

    class Statement(Document):
        _meta = Document.Meta(abstract=True, create_directly=False)
        involves: list[Person]

    class ChildOf(Statement):
        child: Annotated[
            Person,
            RelationConfig(
                reverse_name="child_in",
                subclasses_parent_fields=[
                    FieldSubclassing("involves", field_on_model=Statement)
                ],
            ),
        ]
        parent: Annotated[Person, RelationConfig(reverse_name="parent_in")]

    class Sibling(Statement):
        people: Annotated[
            list[Person],
            RelationConfig(
                reverse_name="sibling_in",
                subclasses_parent_fields=[
                    FieldSubclassing("involves", field_on_model=Statement)
                ],
            ),
        ]

    class Factoid(Document):
        statements: list[Statement]

    class DerivedFactoid(Document, DerivedDocument):
        sources: list[DerivedFrom[Factoid]]
        statements: list[Statement]

    @rule
    def siblings(a: Var[Person], b: Var[Person], p: Var[Person]):
        return DerivedFactoid.Derive(
            label="Siblings", statements=[Sibling.Template(label="s", people=[a, b])]
        ).when(
            ChildOf.Where(child=a, parent=p),
            ChildOf.Where(child=b, parent=p),
            unordered(a, b),
            block=[DerivedFactoid],
        )

    initialise()
    assert "siblings" in DerivedRegistry.documents

    with pytest.raises(PanglossDerivedError, match="involves: is not a field"):
        DerivedRegistry.reset()
        ModelRegistry._reset()

        class Person2(Entity):
            pass

        class Statement2(Document):
            _meta = Document.Meta(abstract=True, create_directly=False)
            involves: list[Person2]

        class Kin(Statement2):
            people: Annotated[
                list[Person2],
                RelationConfig(
                    reverse_name="kin_in",
                    subclasses_parent_fields=[
                        FieldSubclassing("involves", field_on_model=Statement2)
                    ],
                ),
            ]

        class Record(Document):
            statements: list[Statement2]

        class DerivedRecord(Document, DerivedDocument):
            sources: list[DerivedFrom[Record]]
            statements: list[Statement2]

        @rule
        def kin(s: Var[Kin], a: Var[Person2]):
            return DerivedRecord.Derive(
                label="Kin",
                statements=[Kin.Template(label="k", people=[a], involves=[a])],
            ).when(Kin.Where(is_=s, people=a), block=[DerivedRecord])

        initialise()
