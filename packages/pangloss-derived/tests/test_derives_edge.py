"""`DerivesEdge` on a document class, with no database: the class and the rule each becomes, several document classes
that give one edge, what is refused and how it is said"""

from typing import Annotated, no_type_check

import pytest
from pangloss_models import (
    Conjunction,
    Document,
    Entity,
    ModelRegistry,
    ReifiedRelation,
    SemanticSpace,
    Trait,
    Var,
    initialise,
)
from pangloss_models.exceptions import PanglossMetaError

from pangloss_derived import (
    DerivedEdge,
    DerivesEdge,
    Object,
    PanglossDerivedError,
    RuleType,
    Subject,
    rule,
    translatable_models,
)
from pangloss_derived.derives import nearest_common
from pangloss_derived.registry import DerivedRegistry


class Names(dict):
    __getattr__ = dict.__getitem__


@no_type_check
def base():
    class Negative[T](SemanticSpace[T]):
        pass

    class InRole[T](ReifiedRelation[T]):
        role: str

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

    class Statement(Document):
        _meta = Document.Meta(abstract=True)

    return Names(locals())


def initialised(make):
    m = base()
    made = make(m) or {}
    initialise(bind_database=False)
    return Names({**m, **made})


def refused(make) -> str:
    with pytest.raises(PanglossDerivedError) as error:
        initialised(make)
    return str(error.value)


def shape(rule_name):
    """A checked rule as its patterns and relations, whatever its variables are called"""
    checked = DerivedRegistry.checked[rule_name]
    return (
        [(n.model.__name__, n.pattern, n.top) for n in checked.nodes.values()],
        [(e.field, e.wrapped) for e in checked.edges],
        [(v.field, v.many) for v in checked.values],
        checked.symmetric is not None,
        checked.symmetric_body,
        checked.type_names,
    )


# ---------------------------------------------------------------------------
# What a declaration becomes
# ---------------------------------------------------------------------------


@no_type_check
def test_a_declaration_is_the_class_and_the_rule_it_stands_for():
    exchange = RuleType("exchange", "What passed between agents")

    def declared(m):
        class Transfer(m.Statement):
            _derives = [
                DerivesEdge(
                    "GaveTo",
                    subject="given_by",
                    object="given_to",
                    reverse_name="received_from",
                    types=[exchange],
                )
            ]
            given_by: m.Agent
            given_to: m.Agent

        return locals()

    m = initialised(declared)
    GaveTo = DerivedEdge.named("GaveTo")
    assert issubclass(GaveTo, DerivedEdge)
    assert GaveTo._ends == ("given_by", "given_to")
    assert GaveTo._reverse_name == "received_from" and not GaveTo._meta.symmetric
    assert {n: (f.model, f.role) for n, f in GaveTo._fields.items()} == {
        "given_by": (m.Agent, "subject"),
        "given_to": (m.Agent, "object"),
    }
    assert GaveTo._declared_on == (m.Transfer,)
    assert list(DerivedRegistry.checked) == ["Transfer__GaveTo"]
    made = shape("Transfer__GaveTo")
    assert sorted(DerivedRegistry.triggers) == ["Transfer"]
    described = DerivedRegistry.checked["Transfer__GaveTo"].describe()
    assert described.startswith("GaveTo(a, b) :-")
    assert DerivedRegistry.rules["Transfer__GaveTo"].description == (
        "`given_by` and `given_to` of one Transfer"
    )

    # (the same, written out)
    ModelRegistry._reset()

    def written(m):
        class Transfer(m.Statement):
            given_by: m.Agent
            given_to: m.Agent

        class GaveTo(DerivedEdge):
            given_by: Annotated[m.Agent, Subject()]
            given_to: Annotated[m.Agent, Object(reverse_name="received_from")]

        @rule(types=[exchange], name="Transfer__GaveTo")
        def gave_to(a: Var[m.Agent], b: Var[m.Agent]):
            return GaveTo.Derive(given_by=a, given_to=b).when(
                Transfer.Where(given_by=a, given_to=b)
            )

    initialised(written)
    assert shape("Transfer__GaveTo") == made
    assert DerivedRegistry.checked["Transfer__GaveTo"].describe() == described


@no_type_check
def test_one_field_as_both_ends_pairs_its_items():
    def declared(m):
        class Activity(m.Statement):
            _derives = [
                DerivesEdge(
                    "CoParticipants",
                    subject="participants",
                    object="participants",
                    symmetric=True,
                )
            ]
            participants: list[m.Agent | m.InRole[m.Agent]]

        return locals()

    m = initialised(declared)
    edge = DerivedEdge.named("CoParticipants")
    assert edge._ends == ("first", "second") and edge._meta.symmetric
    # (by default the field's own name is the one name of the two ends)
    assert edge._symmetric_label == "participants"
    assert edge._fields["first"].model is m.Agent
    checked = DerivedRegistry.checked["Activity__CoParticipants"]
    assert checked.symmetric == ("a", "b") and checked.symmetric_body
    # (two patterns of the one document, each through the wrappers the field can have)
    assert [(e.source, e.field, e.wrapped) for e in checked.edges] == [
        ("v_doc", "participants", True),
        ("v_doc", "participants", True),
    ]
    assert checked.patterns == ["v_doc", "v_doc"]


@no_type_check
def test_a_label_and_the_names_of_the_ends_can_be_given():
    def declared(m):
        class Activity(m.Statement):
            _derives = [
                DerivesEdge(
                    "Met",
                    subject="participants",
                    object="participants",
                    symmetric=True,
                    label="participant",
                    ends=("one", "other"),
                    max_per_seed=50,
                    description="Took part in one activity",
                )
            ]
            participants: list[m.Person]

    initialised(declared)
    edge = DerivedEdge.named("Met")
    assert edge._ends == ("one", "other") and edge._symmetric_label == "participant"
    assert edge._meta.max_per_seed == 50
    assert edge.__doc__ == "Took part in one activity"
    assert (
        DerivedRegistry.rules["Activity__Met"].description
        == "Took part in one activity"
    )
    (texts,) = [t for t in translatable_models() if t.name == "Met"]
    assert texts.fields == {"participant": ("", "")}
    assert texts.description == "Took part in one activity"


@no_type_check
def test_a_symmetric_edge_of_two_fields_matches_both_orders():
    def declared(m):
        class Marriage(m.Statement):
            _derives = [
                DerivesEdge(
                    "MarriedTo", subject="husband", object="wife", symmetric=True
                )
            ]
            husband: m.Person
            wife: m.Person

    initialised(declared)
    edge = DerivedEdge.named("MarriedTo")
    assert edge._ends == ("husband", "wife") and edge._symmetric_label == "husband"
    checked = DerivedRegistry.checked["Marriage__MarriedTo"]
    # (the body is not the same with the two swapped: both orders are matched, and the ends put in order of id)
    assert checked.symmetric == ("a", "b") and not checked.symmetric_body


@no_type_check
def test_qualifiers_are_read_from_fields_of_the_document():
    def declared(m):
        class Transfer(m.Statement):
            _derives = [
                DerivesEdge(
                    "GaveTo",
                    subject="given_by",
                    object="given_to",
                    qualifiers={"year": "when", "at": "place", "kind": "kinds"},
                )
            ]
            given_by: m.Person
            given_to: m.Person | m.Negative[m.Group]
            when: int
            place: m.Place | m.InRole[m.Place]
            kinds: list[str]

    m = initialised(declared)
    edge = DerivedEdge.named("GaveTo")
    assert {n: (f.kind, f.model, f.role) for n, f in edge._fields.items()} == {
        "given_by": ("relation", m.Person, "subject"),
        # (a person, or a group inside a space: what they share)
        "given_to": ("relation", m.Agent, "object"),
        "year": ("literal", int, "qualifier"),
        "at": ("relation", m.Place, "qualifier"),
        "kind": ("literal", str, "qualifier"),
    }
    checked = DerivedRegistry.checked["Transfer__GaveTo"]
    assert sorted((v.field, v.var, v.many) for v in checked.values) == [
        ("kinds", "q_kind", True),
        ("when", "q_year", False),
    ]
    assert sorted((e.field, e.target, e.wrapped) for e in checked.edges) == [
        ("given_by", "v_a", False),
        ("given_to", "v_b", True),
        ("place", "v_q_at", True),
    ]
    assert list(checked.head) == ["given_by", "given_to", "year", "at", "kind"]


@no_type_check
def test_several_edges_of_one_document_class():
    def declared(m):
        class Sale(m.Statement):
            _derives = [
                DerivesEdge("SoldTo", subject="seller", object="buyer"),
                DerivesEdge("Witnessed", subject="witnesses", object="seller"),
                DerivesEdge(
                    "CoWitnesses",
                    subject="witnesses",
                    object="witnesses",
                    symmetric=True,
                ),
            ]
            seller: m.Person
            buyer: m.Person
            witnesses: list[m.Person]

    initialised(declared)
    assert sorted(DerivedRegistry.checked) == [
        "Sale__CoWitnesses",
        "Sale__SoldTo",
        "Sale__Witnessed",
    ]
    assert DerivedEdge.named("Witnessed")._ends == ("witnesses", "seller")


# ---------------------------------------------------------------------------
# Several document classes, one edge
# ---------------------------------------------------------------------------


@no_type_check
def test_two_document_classes_give_one_edge_by_the_names_of_its_ends():
    exchange = RuleType("exchange")
    trade = RuleType("trade")

    def declared(m):
        class Transfer(m.Statement):
            _derives = [
                DerivesEdge(
                    "GaveTo",
                    subject="given_by",
                    object="given_to",
                    ends=("giver", "receiver"),
                    reverse_name="received_from",
                    qualifiers={"year": "year"},
                    types=[exchange],
                )
            ]
            given_by: m.Person
            given_to: m.Person
            year: int

        class Sale(m.Statement):
            _derives = [
                DerivesEdge(
                    "GaveTo",
                    subject="seller",
                    object="buyer",
                    ends=("giver", "receiver"),
                    reverse_name="received_from",
                    qualifiers={"year": "sold_in"},
                    types=[exchange, trade],
                )
            ]
            seller: m.Group
            buyer: m.Person
            sold_in: int

        return locals()

    m = initialised(declared)
    edge = DerivedEdge.named("GaveTo")
    assert list(DerivedRegistry.classes) == ["GaveTo"]
    assert edge._ends == ("giver", "receiver")
    # (the class of each end: the nearest that the fields of all the declarations share)
    assert edge._fields["giver"].model is m.Agent
    assert edge._fields["receiver"].model is m.Person
    assert edge._declared_on == (m.Transfer, m.Sale)
    assert sorted(DerivedRegistry.checked) == ["Sale__GaveTo", "Transfer__GaveTo"]
    assert DerivedRegistry.checked["Sale__GaveTo"].type_names == ["exchange", "trade"]
    # (each rule's variables are of its own document's fields)
    assert DerivedRegistry.checked["Sale__GaveTo"].variables["a"].model is m.Group
    assert DerivedRegistry.checked["Transfer__GaveTo"].variables["a"].model is m.Person
    assert sorted(DerivedRegistry.triggers) == ["Sale", "Transfer"]
    assert sorted(DerivedRegistry.types) == ["exchange", "trade"]


DISAGREEMENTS = {
    "the names of the ends": ({}, {"subject": "seller", "object": "buyer"}),
    "symmetric": ({"symmetric": True}, {}),
    "the reverse name": ({"reverse_name": "got_from"}, {}),
    "the qualifiers": ({"qualifiers": {"year": "year"}}, {}),
    "max_per_seed": ({"max_per_seed": 5}, {}),
}


@no_type_check
@pytest.mark.parametrize("case", list(DISAGREEMENTS))
def test_declarations_of_one_edge_that_disagree_are_refused(case):
    first, second = DISAGREEMENTS[case]

    def declared(m):
        class Transfer(m.Statement):
            _derives = [
                DerivesEdge(
                    "GaveTo", **{"subject": "given_by", "object": "given_to", **first}
                )
            ]
            given_by: m.Person
            given_to: m.Person
            year: int

        class Sale(m.Statement):
            _derives = [
                DerivesEdge(
                    "GaveTo", **{"subject": "given_by", "object": "given_to", **second}
                )
            ]
            given_by: m.Person
            given_to: m.Person
            seller: m.Person
            buyer: m.Person
            year: int

    said = refused(declared)
    assert "GaveTo is declared on Transfer and on Sale, which do not agree" in said, (
        said
    )


@no_type_check
def test_a_qualifier_of_two_types_in_two_declarations_is_refused():
    def kinds(m):
        class Transfer(m.Statement):
            _derives = [
                DerivesEdge("GaveTo", subject="a", object="b", qualifiers={"q": "x"})
            ]
            a: m.Person
            b: m.Person
            x: int

        class Sale(m.Statement):
            _derives = [
                DerivesEdge("GaveTo", subject="a", object="b", qualifiers={"q": "x"})
            ]
            a: m.Person
            b: m.Person
            x: m.Place

    assert (
        "GaveTo: the qualifier 'q' is an entity in one declaration and a value in another"
        in refused(kinds)
    )
    ModelRegistry._reset()

    def types(m):
        class Transfer(m.Statement):
            _derives = [
                DerivesEdge("GaveTo", subject="a", object="b", qualifiers={"q": "x"})
            ]
            a: m.Person
            b: m.Person
            x: int

        class Sale(m.Statement):
            _derives = [
                DerivesEdge("GaveTo", subject="a", object="b", qualifiers={"q": "x"})
            ]
            a: m.Person
            b: m.Person
            x: str

    assert (
        "GaveTo: the qualifier 'q' is of different types in its declarations: int, str"
        in refused(types)
    )


# ---------------------------------------------------------------------------
# Subclasses
# ---------------------------------------------------------------------------


@no_type_check
def test_a_subclass_gives_its_parents_edge_and_has_no_rule_of_its_own():
    def declared(m):
        class Transfer(m.Statement):
            _derives = [DerivesEdge("GaveTo", subject="given_by", object="given_to")]
            given_by: m.Person
            given_to: m.Person

        class Bequest(Transfer):
            executor: m.Person

        class Sale(Transfer):
            _derives = [DerivesEdge("SoldBy", subject="given_to", object="broker")]
            broker: m.Person

        return locals()

    m = initialised(declared)
    assert sorted(DerivedRegistry.checked) == ["Sale__SoldBy", "Transfer__GaveTo"]
    # (the parent's rule is triggered by a write of either subclass)
    triggers = {
        head: sorted(seed.rule for seed in seeds)
        for head, seeds in DerivedRegistry.triggers.items()
    }
    assert triggers == {
        "Transfer": ["Transfer__GaveTo"],
        "Bequest": ["Transfer__GaveTo"],
        "Sale": ["Sale__SoldBy", "Transfer__GaveTo"],
    }
    assert m.Bequest._derives == m.Transfer._derives


@no_type_check
def test_an_abstract_document_class_declares_for_its_subclasses():
    def declared(m):
        class Exchange(m.Statement):
            _meta = Document.Meta(abstract=True)
            _derives = [DerivesEdge("GaveTo", subject="given_by", object="given_to")]
            given_by: m.Person
            given_to: m.Person

        class Gift(Exchange):
            pass

        class Loan(Exchange):
            pass

    initialised(declared)
    assert list(DerivedRegistry.checked) == ["Exchange__GaveTo"]
    # (a write of either: the abstract class is in the table too, though nothing is ever written as it)
    assert {"Gift", "Loan"} <= set(DerivedRegistry.triggers)


# ---------------------------------------------------------------------------
# With rules that are written
# ---------------------------------------------------------------------------


@no_type_check
def test_a_written_rule_can_feed_a_declared_edge():
    def declared(m):
        class Transfer(m.Statement):
            _derives = [DerivesEdge("GaveTo", subject="given_by", object="given_to")]
            given_by: m.Person
            given_to: m.Person

        class Bequest(m.Statement):
            left_by: m.Person
            heirs: list[m.Person]

        # (as a `derived.py` would, which is read after the declared edges are made: here, at `initialise`)
        @rule
        def bequests(a: Var[m.Person], b: Var[m.Person]):
            return (
                DerivedEdge.named("GaveTo")
                .Derive(given_by=a, given_to=b)
                .when(Bequest.Where(left_by=a, heirs=b))
            )

    initialised(declared)
    assert sorted(DerivedRegistry.checked) == ["Transfer__GaveTo", "bequests"]
    assert DerivedRegistry.checked["bequests"].model is DerivedEdge.named("GaveTo")


@no_type_check
def test_a_declared_edge_with_the_name_of_a_written_class_is_refused():
    def declared(m):
        class GaveTo(DerivedEdge):
            a: Annotated[m.Person, Subject()]
            b: Annotated[m.Person, Object()]

        class Transfer(m.Statement):
            _derives = [DerivesEdge("GaveTo", subject="given_by", object="given_to")]
            given_by: m.Person
            given_to: m.Person

    said = refused(declared)
    assert (
        "Transfer._derives, GaveTo: there is a DerivedEdge class GaveTo already" in said
    )


@no_type_check
def test_initialising_again_makes_the_same_again():
    def declared(m):
        class Transfer(m.Statement):
            _derives = [DerivesEdge("GaveTo", subject="given_by", object="given_to")]
            given_by: m.Person
            given_to: m.Person

    initialised(declared)
    first = DerivedRegistry.checked["Transfer__GaveTo"].hash
    initialise(bind_database=False)
    assert list(DerivedRegistry.classes) == ["GaveTo"]
    assert DerivedRegistry.checked["Transfer__GaveTo"].hash == first


@no_type_check
def test_a_type_of_rule_declared_with_the_models_outlives_the_registry():
    social = RuleType("social", "Who had to do with whom")
    ModelRegistry._reset()
    assert DerivedRegistry.types == {}

    def declared(m):
        class Activity(m.Statement):
            _derives = [
                DerivesEdge(
                    "Met", subject="who", object="who", symmetric=True, types=[social]
                )
            ]
            who: list[m.Person]

    initialised(declared)
    assert DerivedRegistry.types == {"social": social}
    from pangloss_derived.read import rules_of_type

    assert rules_of_type("social") == ["Activity__Met"]


# ---------------------------------------------------------------------------
# What is refused
# ---------------------------------------------------------------------------

WRONG_DECLARATIONS = {
    "a name that is not a name": (
        lambda: DerivesEdge("Gave to", subject="a", object="b"),
        "the name of the edge is the name of a class",
    ),
    "one field as both ends of an asymmetric edge": (
        lambda: DerivesEdge("Met", subject="who", object="who"),
        "the field 'who' is both ends: that needs symmetric=True",
    ),
    "a reverse name on a symmetric edge": (
        lambda: DerivesEdge(
            "Met", subject="a", object="b", symmetric=True, reverse_name="met_by"
        ),
        "a symmetric edge reads the same from both ends: it has no reverse_name",
    ),
    "a label on an asymmetric edge": (
        lambda: DerivesEdge("GaveTo", subject="a", object="b", label="party"),
        "`label` is the one name of the two ends of a symmetric edge",
    ),
    "one name for both ends": (
        lambda: DerivesEdge("GaveTo", subject="a", object="b", ends=("x", "x")),
        "`ends` is the names of the two ends",
    ),
    "three ends": (
        lambda: DerivesEdge("GaveTo", subject="a", object="b", ends=("x", "y", "z")),
        "`ends` is the names of the two ends",
    ),
    "a qualifier with the name of an end": (
        lambda: DerivesEdge("GaveTo", subject="a", object="b", qualifiers={"a": "c"}),
        "the qualifier 'a' has the name of an end",
    ),
    "a qualifier that is not a field's name": (
        lambda: DerivesEdge("GaveTo", subject="a", object="b", qualifiers={"y": 1}),
        "`qualifiers` gives each qualifier's name on the edge and the field",
    ),
    "a type that is not a RuleType": (
        lambda: DerivesEdge("GaveTo", subject="a", object="b", types=["social"]),
        "'social' is not a RuleType",
    ),
    "a field that is not a name": (
        lambda: DerivesEdge("GaveTo", subject=None, object="b"),
        "`subject` is the name of a field of the document class",
    ),
}


@pytest.mark.parametrize("case", list(WRONG_DECLARATIONS))
def test_a_declaration_that_cannot_be_right_is_refused_where_it_is_written(case):
    make, message = WRONG_DECLARATIONS[case]
    with pytest.raises(PanglossDerivedError) as error:
        make()
    assert message in str(error.value), str(error.value)
    assert str(error.value).startswith("DerivesEdge(")


def test_a_reverse_name_that_is_not_a_name_is_refused():
    with pytest.raises(ValueError, match="is a name"):
        DerivesEdge("GaveTo", subject="a", object="b", reverse_name="got from")


WRONG_FIELDS = {
    "a field there is not": (
        {"subject": "giver", "object": "given_to"},
        "Transfer._derives, GaveTo: Transfer has no field 'giver' (it has: ",
    ),
    "a literal as an end": (
        {"subject": "given_by", "object": "year"},
        "Transfer._derives, GaveTo: Transfer.year is not a relation to entities: an end of an edge is an entity",
    ),
    "a document as an end": (
        {"subject": "given_by", "object": "notes"},
        "Transfer.notes is not a relation to entities (it holds: Note)",
    ),
    "a document as a qualifier": (
        {"subject": "given_by", "object": "given_to", "qualifiers": {"n": "notes"}},
        "Transfer.notes is not a relation to entities (it holds: Note)",
    ),
    "a qualifier there is not": (
        {"subject": "given_by", "object": "given_to", "qualifiers": {"y": "yeer"}},
        "Transfer has no field 'yeer'",
    ),
}


@no_type_check
@pytest.mark.parametrize("case", list(WRONG_FIELDS))
def test_a_field_that_cannot_be_what_it_is_declared_as_is_refused(case):
    options, message = WRONG_FIELDS[case]

    def declared(m):
        class Note(Document):
            text: str

        class Transfer(m.Statement):
            _derives = [DerivesEdge("GaveTo", **options)]
            given_by: m.Person
            given_to: m.Person
            year: int
            notes: list[Note]

    said = refused(declared)
    assert message in said, said


@no_type_check
def test_what_is_not_a_document_class_or_not_a_list_of_declarations_is_refused():
    def on_an_entity(m):
        class Family(Entity):
            _derives = [DerivesEdge("Kin", subject="a", object="b")]

    assert "Family._derives: an edge is declared on a document class" in refused(
        on_an_entity
    )
    ModelRegistry._reset()

    def twice(m):
        class Transfer(m.Statement):
            _derives = [
                DerivesEdge("GaveTo", subject="given_by", object="given_to"),
                DerivesEdge("GaveTo", subject="given_to", object="given_by"),
            ]
            given_by: m.Person
            given_to: m.Person

    assert "Transfer._derives declares GaveTo twice" in refused(twice)
    ModelRegistry._reset()

    def not_declarations(m):
        class Transfer(m.Statement):
            _derives = ["GaveTo"]
            given_by: m.Person

    assert "Transfer._derives is a list of DerivesEdge(...): not 'GaveTo'" in refused(
        not_declarations
    )
    ModelRegistry._reset()
    m = base()
    with pytest.raises(PanglossMetaError, match="Transfer._derives must be a list"):

        class Transfer(m.Statement):
            _derives = DerivesEdge("GaveTo", subject="given_by", object="given_to")
            given_by: m.Person


@no_type_check
def test_the_nearest_class_that_some_classes_share():
    m = base()

    class Monk(m.Person):
        pass

    class Abbot(Monk):
        pass

    class Order(m.Group):
        pass

    assert nearest_common([m.Person]) is m.Person
    assert nearest_common([Abbot, Monk]) is Monk
    assert nearest_common([Abbot, m.Person, Monk]) is m.Person
    assert nearest_common([Abbot, Order]) is m.Agent
    # (nothing of the project's in common: any entity)
    assert nearest_common([Abbot, m.Place]) is Entity


@no_type_check
def test_a_field_that_holds_documents_too_gives_edges_of_its_entities():
    """(a mention not yet reconciled with an entity is a document, in a field of entities: it is at no end)"""

    def declared(m):
        class Mention(Document):
            text: str

        class Transfer(m.Statement):
            _derives = [DerivesEdge("GaveTo", subject="given_by", object="given_to")]
            given_by: m.Person | Mention
            given_to: list[m.Group | m.InRole[m.Person] | Mention]

    m = initialised(declared)
    edge = DerivedEdge.named("GaveTo")
    assert edge._fields["given_by"].model is m.Person
    assert edge._fields["given_to"].model is m.Agent


@no_type_check
def test_pangloss_check_says_what_is_wrong_with_a_declaration_at_its_class():
    """`pangloss check` (and so the language server) initialises the models and reports what that refuses"""
    from pangloss_models.diagnostics import check_models

    m = base()

    class Transfer(m.Statement):
        _derives = [DerivesEdge("GaveTo", subject="giver", object="given_to")]
        given_by: m.Person
        given_to: m.Person

    found = [d for d in check_models() if d.severity == "error"]
    assert len(found) == 1
    assert (
        "Transfer._derives, GaveTo: Transfer has no field 'giver'" in found[0].message
    )
    # (at the class it names, in this file)
    assert found[0].file is not None and found[0].file.endswith("test_derives_edge.py")
