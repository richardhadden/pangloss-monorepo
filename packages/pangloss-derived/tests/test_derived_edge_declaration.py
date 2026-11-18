"""`DerivedEdge` classes, with no database: the two ends and how they are marked, qualifiers, values of a justification,
what is refused and how it is said, the classes made for each, and what a wrapper does to a derivation by default"""

from typing import Annotated, no_type_check

import pytest
from pangloss_models import (
    Conjunction,
    Document,
    Entity,
    ReifiedRelation,
    SemanticSpace,
    Trait,
    Var,
    hooks,
    initialise,
)

from pangloss_derived import (
    DerivedEdge,
    DerivedMeta,
    Object,
    PanglossDerivedError,
    PerJustification,
    Subject,
    SymmetricLabel,
    rule,
    translatable_models,
)
from pangloss_derived.check import derived_fields, rule_hash
from pangloss_derived.declare import default_derivation, derivation_of, is_exclusive
from pangloss_derived.registry import DerivedRegistry
from pangloss_derived.store import Found, digest


class Names(dict):
    """The classes a function declared, by name: `m.Person`"""

    __getattr__ = dict.__getitem__


@no_type_check
def models():
    class Agent(Trait):
        pass

    class Person(Entity, Agent):
        pass

    class Group(Entity, Agent):
        pass

    class Place(Entity):
        pass

    class Transfer(Document):
        given_by: Agent
        given_to: Agent
        year: int
        amount: int

    class MemberOf(Document):
        member: Person
        group: Group

    return Names(locals())


def declared(make):
    """Declare the models and what `make(m)` declares, and initialise"""
    m = models()
    made = make(m) or {}
    initialise(bind_database=False)
    return Names({**m, **made})


def refused(make) -> str:
    with pytest.raises(PanglossDerivedError) as error:
        declared(make)
    return str(error.value)


# ---------------------------------------------------------------------------
# The two ends
# ---------------------------------------------------------------------------


@no_type_check
def test_an_asymmetric_edge_has_a_subject_and_an_object():
    def make(m):
        class GaveTo(DerivedEdge):
            """Gave something to"""

            giver: Annotated[m.Agent, Subject()]
            receiver: Annotated[m.Agent, Object(reverse_name="received_from")]
            year: int

        return locals()

    GaveTo = declared(make)["GaveTo"]
    assert GaveTo._ends == ("giver", "receiver")
    assert GaveTo._reverse_name == "received_from"
    assert GaveTo._symmetric_label is None
    assert {n: (f.kind, f.role) for n, f in GaveTo._fields.items()} == {
        "giver": ("relation", "subject"),
        "receiver": ("relation", "object"),
        "year": ("literal", "qualifier"),
    }
    assert [f.name for f in GaveTo.qualifiers()] == ["year"]
    assert GaveTo.key_fields() == ["giver", "receiver", "year"]
    assert GaveTo.per_justification() == []


@no_type_check
def test_the_order_the_ends_are_declared_in_does_not_matter():
    def make(m):
        class ReceivedBy(DerivedEdge):
            year: int
            receiver: Annotated[m.Agent, Object()]
            giver: Annotated[m.Agent, Subject()]

        return locals()

    model = declared(make)["ReceivedBy"]
    assert model._ends == ("giver", "receiver")
    assert model._reverse_name is None


@no_type_check
def test_a_symmetric_edge_has_two_ends_of_one_label():
    def make(m):
        class SameGroup(DerivedEdge):
            _meta = DerivedEdge.Meta(symmetric=True)
            first: Annotated[m.Person, SymmetricLabel("member")]
            second: Annotated[m.Person, SymmetricLabel("member")]
            group: m.Group

        return locals()

    model = declared(make)["SameGroup"]
    assert model._ends == ("first", "second")
    assert model._symmetric_label == "member"
    assert model._reverse_name is None
    assert [f.name for f in model.qualifiers()] == ["group"]
    assert model._fields["group"].kind == "relation"


WRONG_ENDS = {
    "no ends": (
        lambda m: {"a": m.Person, "b": m.Person},
        False,
        "an edge has two ends: one field marked Subject() and one Object()",
    ),
    "only a subject": (
        lambda m: {"a": Annotated[m.Person, Subject()], "b": m.Person},
        False,
        "this has 1 Subject() and 0 Object()",
    ),
    "two subjects": (
        lambda m: {
            "a": Annotated[m.Person, Subject()],
            "b": Annotated[m.Person, Subject()],
            "c": Annotated[m.Person, Object()],
        },
        False,
        "this has 2 Subject() and 1 Object()",
    ),
    "two objects": (
        lambda m: {
            "a": Annotated[m.Person, Subject()],
            "b": Annotated[m.Person, Object()],
            "c": Annotated[m.Person, Object()],
        },
        False,
        "this has 1 Subject() and 2 Object()",
    ),
    "a literal end": (
        lambda m: {
            "a": Annotated[m.Person, Subject()],
            "b": Annotated[int, Object()],
        },
        False,
        "b: an end of an edge is an entity (or a trait of entities), not <class 'int'>",
    ),
    "a marker without its brackets": (
        lambda m: {
            "a": Annotated[m.Person, Subject],
            "b": Annotated[m.Person, Object()],
        },
        False,
        "a: write Subject(), with the brackets",
    ),
    "two markers on a field": (
        lambda m: {
            "a": Annotated[m.Person, Subject(), Object()],
            "b": Annotated[m.Person, Object()],
        },
        False,
        "a: a field is one thing of the edge, not Subject and Object",
    ),
    "a subject on a symmetric class": (
        lambda m: {
            "a": Annotated[m.Person, Subject()],
            "b": Annotated[m.Person, Object()],
        },
        True,
        "the ends of a symmetric class are marked with a SymmetricLabel",
    ),
    "a symmetric class with no label": (
        lambda m: {"a": m.Person, "b": m.Person},
        True,
        "a symmetric class needs its two ends marked, each with the same SymmetricLabel",
    ),
    "a symmetric class with one label": (
        lambda m: {"a": Annotated[m.Person, SymmetricLabel("x")], "b": m.Person},
        True,
        "a symmetric class needs its two ends marked",
    ),
    "symmetric ends of two types": (
        lambda m: {
            "a": Annotated[m.Person, SymmetricLabel("x")],
            "b": Annotated[m.Group, SymmetricLabel("x")],
        },
        True,
        "the two ends of a symmetric class (a, b) must be of the same type",
    ),
    "a symmetric label that is not a name": (
        lambda m: {
            "a": Annotated[m.Person, SymmetricLabel("a member")],
            "b": Annotated[m.Person, SymmetricLabel("a member")],
        },
        True,
        "a SymmetricLabel is a name (letters, digits and _): not 'a member'",
    ),
    "a value of a justification that is an entity": (
        lambda m: {
            "a": Annotated[m.Person, Subject()],
            "b": Annotated[m.Person, Object()],
            "c": Annotated[m.Group, PerJustification()],
        },
        False,
        "c: a PerJustification() field is a literal",
    ),
    "a document as a field": (
        lambda m: {
            "a": Annotated[m.Person, Subject()],
            "b": Annotated[m.Person, Object()],
            "c": m.Transfer,
        },
        False,
        "c: a field of a DerivedEdge class is an entity (or a trait of entities) or a literal",
    ),
    "a list as a field": (
        lambda m: {
            "a": Annotated[m.Person, Subject()],
            "b": Annotated[m.Person, Object()],
            "c": list[int],
        },
        False,
        "c: a field of a DerivedEdge class is an entity",
    ),
    "a field with a name of the stored edge": (
        lambda m: {
            "a": Annotated[m.Person, Subject()],
            "b": Annotated[m.Person, Object()],
            "pg_subject": str,
        },
        False,
        "a field cannot be called 'pg_subject'",
    ),
    "a field with a name of the view": (
        lambda m: {
            "a": Annotated[m.Person, Subject()],
            "b": Annotated[m.Person, Object()],
            "qualifiers": str,
        },
        False,
        "a field cannot be called 'qualifiers'",
    ),
}


@no_type_check
@pytest.mark.parametrize("case", list(WRONG_ENDS))
def test_a_class_without_exactly_two_ends_is_refused(case):
    fields, symmetric, message = WRONG_ENDS[case]

    def make(m):
        namespace = {
            "__annotations__": fields(m),
            "__module__": __name__,
            "_meta": DerivedEdge.Meta(symmetric=symmetric),
        }
        type("Wrong", (DerivedEdge,), namespace)

    said = refused(make)
    assert said.startswith("Wrong: "), said
    assert message in said, said


@no_type_check
def test_a_qualifier_may_be_called_subject():
    """(why the stored names are `pg_subject` and `pg_object`)"""

    def make(m):
        class Discussed(DerivedEdge):
            speaker: Annotated[m.Person, Subject()]
            hearer: Annotated[m.Person, Object()]
            subject: str
            object: m.Place

        return locals()

    model = declared(make)["Discussed"]
    assert model._ends == ("speaker", "hearer")
    assert [f.name for f in model.qualifiers()] == ["subject", "object"]


@no_type_check
def test_a_reverse_name_is_a_name_and_is_not_taken():
    with pytest.raises(ValueError, match="is a name"):
        Object(reverse_name="received from")

    def clash_with_a_class(m):
        class Knows(DerivedEdge):
            a: Annotated[m.Person, Subject()]
            b: Annotated[m.Person, Object(reverse_name="KnownBy")]

        class KnownBy(DerivedEdge):
            a: Annotated[m.Person, Subject()]
            b: Annotated[m.Person, Object()]

    assert (
        "Knows: the reverse_name 'KnownBy' is also the name of a derived class"
        in refused(clash_with_a_class)
    )
    from pangloss_models import ModelRegistry

    ModelRegistry._reset()

    def clash_with_another(m):
        class Knows(DerivedEdge):
            a: Annotated[m.Person, Subject()]
            b: Annotated[m.Person, Object(reverse_name="known_by")]

        class Taught(DerivedEdge):
            a: Annotated[m.Person, Subject()]
            b: Annotated[m.Person, Object(reverse_name="known_by")]

    assert "the reverse_name 'known_by' is also the reverse_name of Knows" in refused(
        clash_with_another
    )


@no_type_check
def test_a_meta_that_is_not_a_meta_is_refused_when_the_class_is_declared():
    with pytest.raises(TypeError, match="must be a DerivedEdge.Meta"):

        class Wrong(DerivedEdge):
            _meta = {"symmetric": True}


@no_type_check
def test_the_old_meta_options_are_gone():
    with pytest.raises(TypeError):
        DerivedEdge.Meta(ends=("a", "b"))
    with pytest.raises(TypeError):
        DerivedEdge.Meta(reverse_names={"a": "b"})
    import pangloss_derived

    assert not hasattr(pangloss_derived, "Derived")


# ---------------------------------------------------------------------------
# Subclasses
# ---------------------------------------------------------------------------


@no_type_check
def test_an_abstract_parent_gives_its_ends_to_its_subclasses():
    def make(m):
        class Tie(DerivedEdge):
            _meta = DerivedEdge.Meta(abstract=True, symmetric=True)
            first: Annotated[m.Person, SymmetricLabel("party")]
            second: Annotated[m.Person, SymmetricLabel("party")]

        class SameGroup(Tie):
            group: m.Group

        class Fought(Tie):
            _meta = DerivedEdge.Meta(symmetric=True, max_per_seed=7)
            year: int

        return locals()

    m = declared(make)
    assert m.Tie._meta.abstract
    assert not m.SameGroup._meta.abstract and m.SameGroup._meta.symmetric
    assert m.SameGroup._ends == ("first", "second")
    assert m.SameGroup._symmetric_label == "party"
    assert m.Fought._meta.max_per_seed == 7
    assert sorted(DerivedRegistry.concrete_classes()) == ["Fought", "SameGroup"]


@no_type_check
def test_an_abstract_parent_may_leave_the_ends_to_its_subclasses():
    def make(m):
        class Dated(DerivedEdge):
            _meta = DerivedEdge.Meta(abstract=True)
            year: int

        class GaveIn(Dated):
            giver: Annotated[m.Agent, Subject()]
            receiver: Annotated[m.Agent, Object()]

        return locals()

    m = declared(make)
    assert m.GaveIn._ends == ("giver", "receiver")
    assert m.GaveIn.key_fields() == ["year", "giver", "receiver"]
    assert not hasattr(m.Dated, "_ends")


@no_type_check
def test_a_concrete_subclass_without_ends_is_refused():
    def make(m):
        class Dated(DerivedEdge):
            _meta = DerivedEdge.Meta(abstract=True)
            year: int

        class Nothing(Dated):
            month: int

    assert "Nothing: an edge has two ends" in refused(make)


@no_type_check
def test_a_subclass_can_narrow_an_end():
    def make(m):
        class GaveTo(DerivedEdge):
            giver: Annotated[m.Agent, Subject()]
            receiver: Annotated[m.Agent, Object()]

        class PersonGaveTo(GaveTo):
            giver: Annotated[m.Person, Subject()]

        return locals()

    m = declared(make)
    assert m.PersonGaveTo._fields["giver"].model is m.Person
    assert m.PersonGaveTo._fields["receiver"].model is m.Agent
    assert m.GaveTo._fields["giver"].model is m.Agent


# ---------------------------------------------------------------------------
# The classes made
# ---------------------------------------------------------------------------


@no_type_check
def edge_classes(m):
    class GaveTo(DerivedEdge):
        """Gave something to"""

        giver: Annotated[m.Agent, Subject()]
        receiver: Annotated[m.Agent, Object(reverse_name="received_from")]
        year: int
        place: m.Place
        likelihood: Annotated[int, PerJustification()]

    class SameGroup(DerivedEdge):
        """In one group"""

        _meta = DerivedEdge.Meta(symmetric=True)
        first: Annotated[m.Person, SymmetricLabel("member")]
        second: Annotated[m.Person, SymmetricLabel("member")]
        group: m.Group

    return locals()


@no_type_check
def test_the_view_has_the_ends_as_fields_and_the_rest_as_qualifiers():
    m = declared(edge_classes)
    GaveTo = m.GaveTo
    assert set(GaveTo.View.model_fields) >= {
        "id",
        "type",
        "ends",
        "symmetric",
        "plain",
        "giver",
        "receiver",
        "qualifiers",
        "context_labels",
        "justification_count",
        "justifications",
    }
    # (a qualifier is not a field of the view itself; a value of a justification is in neither)
    assert "year" not in GaveTo.View.model_fields
    assert "likelihood" not in GaveTo.View.model_fields
    assert list(GaveTo.Qualifiers.model_fields) == ["year", "place"]
    view = GaveTo.View(
        id="k",
        ends=["giver", "receiver"],
        giver={"id": "1", "type": "Person", "label": "A"},
        receiver={"id": "2", "type": "Group", "label": "G"},
        qualifiers={"year": 1500, "place": {"id": "3", "type": "Place", "label": "P"}},
    )
    assert view.qualifiers.year == 1500 and view.qualifiers.place.label == "P"
    dumped = view.model_dump(by_alias=True, mode="json")
    assert dumped["type"] == "GaveTo" and dumped["ends"] == ["giver", "receiver"]
    assert dumped["qualifiers"] == {
        "year": 1500,
        "place": {"id": "3", "type": "Place", "label": "P"},
    }
    assert dumped["plain"] is True and dumped["symmetric"] is False
    assert dumped["justificationCount"] == 0 and dumped["contextLabels"] == []
    # (read back, as the SDK does)
    assert GaveTo.View.model_validate(dumped) == view


@no_type_check
def test_the_where_filters_ends_and_qualifiers_and_not_a_value_of_a_justification():
    m = declared(edge_classes)
    GaveTo = m.GaveTo
    assert set(GaveTo.Where.model_fields) == {
        "giver",
        "receiver",
        "year",
        "place",
        "plain",
        "context_label",
        "rule_type",
    }
    where = GaveTo.Where(receiver="b", year=1500, plain=True)
    assert where.to_json() == {
        "type": "GaveTo",
        "where": {"receiver": "b", "year": 1500, "plain": True},
    }
    assert where.end_filters() == ["b"]
    with pytest.raises(ValueError):
        GaveTo.Where(likelihood=80)


@no_type_check
def test_the_head_of_a_rule_takes_every_field():
    m = declared(edge_classes)
    GaveTo = m.GaveTo
    assert list(GaveTo.Derive.model_fields) == [
        "giver",
        "receiver",
        "year",
        "place",
        "likelihood",
    ]


@no_type_check
def test_named_gives_a_class_by_its_name():
    m = declared(edge_classes)
    assert DerivedEdge.named("GaveTo") is m.GaveTo
    with pytest.raises(PanglossDerivedError, match="no derived edge called 'Gave'"):
        DerivedEdge.named("Gave")


@no_type_check
def test_what_is_translated_ends_as_one_label_and_the_reverse_name():
    m = declared(edge_classes)
    texts = {t.name: t for t in translatable_models()}
    assert texts["GaveTo"] == hooks.TranslatableModel(
        name="GaveTo",
        module=m.GaveTo.__module__,
        kind="DerivedEdge",
        description="Gave something to",
        fields={
            "giver": ("", ""),
            "receiver": ("", ""),
            "year": ("", ""),
            "place": ("", ""),
            "likelihood": ("", ""),
        },
        incoming=("received_from",),
    )
    assert texts["SameGroup"].fields == {"member": ("", ""), "group": ("", "")}
    assert texts["SameGroup"].incoming == ()


@no_type_check
def test_the_sections_of_an_entity_follow_what_it_can_be_of_an_edge():
    from pangloss_derived.read import sections_of

    m = declared(edge_classes)
    GaveTo, SameGroup = m.GaveTo, m.SameGroup
    # (a person gives and receives: the class from the giver, its reverse name from the receiver)
    assert sections_of(GaveTo, m.Person) == [
        ("GaveTo", "subject", ["giver"]),
        ("received_from", "object", ["receiver"]),
    ]
    # (a place only qualifies)
    assert sections_of(GaveTo, m.Place) == [("GaveTo:place", "qualifier", ["place"])]
    assert sections_of(SameGroup, m.Person) == [
        ("SameGroup", "ends", ["first", "second"])
    ]
    # (a group is at neither end of `SameGroup`, and at either of `GaveTo`)
    assert sections_of(SameGroup, m.Group) == [
        ("SameGroup:group", "qualifier", ["group"])
    ]
    assert [s[0] for s in sections_of(GaveTo, m.Group)] == [
        "GaveTo",
        "received_from",
    ]
    assert sections_of(SameGroup, m.Place) == []


# ---------------------------------------------------------------------------
# Rules of edges
# ---------------------------------------------------------------------------


@no_type_check
def gave_to_rule(m):
    made = edge_classes(m)
    GaveTo, Transfer, Agent = made["GaveTo"], m.Transfer, m.Agent

    @rule
    def gave_to(a: Var[Agent], b: Var[Agent], y: Var[int], n: Var[int]):
        return GaveTo.Derive(
            giver=a, receiver=b, year=y, place=None, likelihood=n
        ).when(Transfer.Where(given_by=a, given_to=b, year=y, amount=n))

    return made


@no_type_check
def test_a_relation_qualifier_needs_a_variable():
    with pytest.raises(PanglossDerivedError) as error:
        declared(gave_to_rule)
    assert "Rule gave_to: the head is not right" in str(error.value)
    assert "place" in str(error.value)


@no_type_check
def test_a_value_of_a_justification_is_not_in_the_key_of_the_edge():
    def make(m):
        class GaveTo(DerivedEdge):
            giver: Annotated[m.Agent, Subject()]
            receiver: Annotated[m.Agent, Object()]
            year: int
            likelihood: Annotated[int, PerJustification()]

        @rule
        def gave_to(a: Var[m.Agent], b: Var[m.Agent], y: Var[int], n: Var[int]):
            return GaveTo.Derive(giver=a, receiver=b, year=y, likelihood=n).when(
                m.Transfer.Where(given_by=a, given_to=b, year=y, amount=n)
            )

        return locals()

    declared(make)
    checked = DerivedRegistry.checked["gave_to"]

    def row(node, amount, year=1500):
        return {
            "fields": ["A", "B", year, amount],
            "nodes": [node],
            "heads": [node],
            "spaces": [[]],
            "through": [[] for _ in checked.edges],
            "props": [{} for _ in checked.edges],
            "paths": [[] for _ in checked.edges],
        }

    found = Found()
    found.add(checked, row("t1", 80))
    found.add(checked, row("t2", 60))
    found.add(checked, row("t3", 60, year=1501))
    # (two transfers of one year are one edge with two justifications; another year is another edge)
    assert len(found.facts) == 2
    key = digest("GaveTo", ["A", "B", 1500])
    assert found.facts[key].values == {"giver": "A", "receiver": "B", "year": 1500}
    values = sorted(
        (j.values["likelihood"], j.nodes[0])
        for j in found.justifications.values()
        if j.fact == key
    )
    assert values == [(60, "t2"), (80, "t1")]
    # (the same node found with another value is another justification: neither is lost)
    found.add(checked, row("t1", 70))
    assert sum(1 for j in found.justifications.values() if j.fact == key) == 3


@no_type_check
def test_the_hash_of_a_rule_changes_with_what_a_field_is_of_the_edge():
    def make(kind):
        def declare(m):
            class GaveTo(DerivedEdge):
                giver: Annotated[m.Agent, Subject()]
                receiver: Annotated[m.Agent, Object()]
                year: kind

            @rule
            def gave_to(a: Var[m.Agent], b: Var[m.Agent], y: Var[int]):
                return GaveTo.Derive(giver=a, receiver=b, year=y).when(
                    m.Transfer.Where(given_by=a, given_to=b, year=y)
                )

        return declare

    from pangloss_models import ModelRegistry

    declared(make(int))
    first = DerivedRegistry.checked["gave_to"].hash
    assert first == rule_hash(DerivedRegistry.checked["gave_to"])
    ModelRegistry._reset()
    declared(make(Annotated[int, PerJustification()]))
    assert DerivedRegistry.checked["gave_to"].hash != first


@no_type_check
def test_fields_are_read_from_the_class_as_declared():
    def make(m):
        class GaveTo(DerivedEdge):
            giver: Annotated[m.Agent, Subject()]
            receiver: Annotated[m.Agent, Object()]
            note: str | None

        return locals()

    model = declared(make)["GaveTo"]
    fields = derived_fields(model)
    assert fields["note"].kind == "literal" and fields["note"].model is str


# ---------------------------------------------------------------------------
# What a wrapper does by default
# ---------------------------------------------------------------------------


@no_type_check
def wrappers():
    class Negative[T](SemanticSpace[T]):
        pass

    class Quiet[T](SemanticSpace[T]):
        _derived_meta = DerivedMeta(derivation="transparent")

    class Identification[T](ReifiedRelation[T]):
        pass

    class Guess[T](Identification[T]):
        _derived_meta = DerivedMeta(derivation="qualify")

    class BetterGuess[T](Guess[T]):
        pass

    class Both[T](Conjunction):
        both: list[T]

    class Either[T](Conjunction):
        _derived_meta = DerivedMeta(exclusive=True)
        either: list[T]

    class Doubted[T](Conjunction):
        _derived_meta = DerivedMeta(derivation="qualify", exclusive=True)
        doubted: list[T]

    class Never[T](ReifiedRelation[T]):
        _derived_meta = DerivedMeta(derivation="block")

    return Names(locals())


@no_type_check
def test_a_reified_relation_and_a_conjunction_are_read_through_and_a_space_qualifies():
    w = wrappers()
    assert derivation_of(w.Negative) == "qualify"
    assert derivation_of(w.Identification) == "transparent"
    assert derivation_of(w.Both) == "transparent"
    # (exclusive says nothing of the derivation: one alternative at a time, and plain)
    assert derivation_of(w.Either) == "transparent" and is_exclusive(w.Either)
    assert not is_exclusive(w.Both)
    # (a class can say otherwise, and its subclasses follow it)
    assert derivation_of(w.Quiet) == "transparent"
    assert derivation_of(w.Guess) == "qualify"
    assert derivation_of(w.BetterGuess) == "qualify"
    assert derivation_of(w.Doubted) == "qualify" and is_exclusive(w.Doubted)
    assert derivation_of(w.Never) == "block"
    assert default_derivation(w.Guess) == "transparent"
    assert DerivedMeta().derivation is None


@no_type_check
def test_a_rule_records_only_the_wrappers_that_qualify():
    w = wrappers()

    class Person(Entity):
        pass

    class Saw(Document):
        seer: (
            Person
            | w.Identification[Person]
            | w.Guess[Person]
            | w.Never[Person]
            | w.Either[Person]
            | w.Doubted[Person]
        )
        seen: Person

    class Report(Document):
        statements: list[Saw | w.Negative[Saw] | w.Quiet[Saw]]

    class SawEdge(DerivedEdge):
        seer: Annotated[Person, Subject()]
        seen: Annotated[Person, Object()]

    @rule
    def saw(a: Var[Person], b: Var[Person]):
        return SawEdge.Derive(seer=a, seen=b).when(Saw.Where(seer=a, seen=b))

    @rule
    def saw_allowed(a: Var[Person], b: Var[Person]):
        return SawEdge.Derive(seer=a, seen=b).when(
            Saw.Where(seer=a, seen=b), allow=[w.Never], block=[w.Negative]
        )

    initialise(bind_database=False)
    checked = DerivedRegistry.checked["saw"]
    assert checked.transparent == {
        "Identification",
        "Both",
        "Either",
        "Quiet",
    }
    assert checked.blocked == {"Never"}
    assert checked.exclusive == {"Either", "Doubted"}
    allowed = DerivedRegistry.checked["saw_allowed"]
    assert allowed.blocked == {"Negative"}
    assert "Never" not in allowed.transparent
    assert checked.hash != allowed.hash


@no_type_check
def test_the_library_says_what_its_wrappers_do():
    """`pangloss-library`: an identification a person made is read through; a weighted alternative and a machine's
    suggestion qualify what is derived through them"""
    import importlib

    import pangloss_library.models as library

    library = importlib.reload(library)
    assert derivation_of(library.Identification) == "transparent"
    assert derivation_of(library.WeightedAlternative) == "qualify"
    assert is_exclusive(library.WeightedAlternative)
    assert derivation_of(library.IdentificationByToolchain) == "qualify"
    assert not is_exclusive(library.IdentificationByToolchain)

    class SuggestedReading[T](library.IdentificationByToolchain[T]):
        confirmed_as = "Identification"

    assert derivation_of(SuggestedReading) == "qualify"


@no_type_check
def test_derived_from_is_a_citation_that_does_not_protect():
    from pangloss_models import ModelRegistry
    from pangloss_models.citations import is_cites, protects

    from pangloss_derived import DerivedDocument, DerivedFrom

    class Source(Document):
        pass

    class Summary(Document, DerivedDocument):
        sources: list[DerivedFrom[Source]]

    initialise(bind_database=False)
    assert is_cites(DerivedFrom[Source]) and not protects(DerivedFrom[Source])
    (option,) = Summary._meta.fields["sources"].type_options
    assert option.annotated_type.__name__ == "PGUnprotectedCitation"
    assert option.protect is False and option.cited == {Source}
    # (and no citation that protects is declared for it)
    assert "PGCitation" not in ModelRegistry._model_dict


@no_type_check
def test_declaring_a_citation_class_of_ones_own_declares_no_model():
    """(a regression: `class DerivedFrom[Target](Cites[Target])` declared `PGCitation` in every project that has
    `pangloss-derived`, which then had a migration to make for a model it never used)"""
    from pangloss_models import Cites, ModelRegistry

    class RestsOn[Target](Cites[Target]):
        protect = False

    class Supports[Target](Cites[Target]):
        pass

    assert not [name for name in ModelRegistry._model_dict if name.startswith("PG")]
