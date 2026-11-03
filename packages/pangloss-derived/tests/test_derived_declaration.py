"""Rules checked against the models, with no database: what is refused and how it is said, the JSON of a body, the
table of what triggers a rule, and the query a rule compiles to"""

from typing import no_type_check

import pytest
from pangloss_models import initialise
from pangloss_models.exceptions import PanglossSearchError
from pangloss_models.model_bases.conjunction import Conjunction
from pangloss_models.model_bases.document import Document
from pangloss_models.model_bases.entity import Entity
from pangloss_models.model_bases.reified_relation import ReifiedRelation
from pangloss_models.model_bases.semantic_space import SemanticSpace
from pangloss_models.model_bases.trait import Trait
from pangloss_models.search import Match, Var, check_match

from pangloss_derived import (
    Derived,
    DerivedMeta,
    PanglossDerivedError,
    RuleType,
    distinct,
    rule,
)
from pangloss_derived.registry import DerivedRegistry


@no_type_check
def models():
    class Negative[T](SemanticSpace[T]):
        pass

    class Hypothetical[T](SemanticSpace[T]):
        _derived_meta = DerivedMeta(derivation="block")

    class Alternative[T](Conjunction):
        _derived_meta = DerivedMeta(exclusive=True)
        alternatives: list[T]

    class Identification[T](ReifiedRelation[T]):
        pass

    class Agent(Trait):
        pass

    class Person(Entity, Agent):
        pass

    class Group(Entity, Agent):
        pass

    class Place(Entity):
        pass

    class MemberOf(Document):
        member: Person | Identification[Alternative[Person]]
        group: Group
        year: int

    class Factoid(Document):
        statements: list[MemberOf | Negative[MemberOf] | Hypothetical[MemberOf]]

    class Letter(Document):
        sender: Agent

    class SameFamily(Derived):
        """Members of the same family"""

        _meta = Derived.Meta(symmetric=True)
        first: Person
        second: Person
        family: Group

    return locals()


def checked_with(make_rule):
    """Declare the models, then the rule made by `make_rule(m)`, and initialise"""
    m = models()
    make_rule(m)
    initialise(bind_database=False)
    return m


def refused(make_rule) -> str:
    with pytest.raises(PanglossDerivedError) as error:
        checked_with(make_rule)
    return str(error.value)


@no_type_check
def test_a_rule_is_checked_and_made_into_nodes_and_edges():
    def make(m):
        Person, Group, MemberOf, SameFamily = (
            m["Person"],
            m["Group"],
            m["MemberOf"],
            m["SameFamily"],
        )
        family = RuleType("family", "Ties of family")

        @rule(types=[family])
        def same_family(a: Var[Person], b: Var[Person], f: Var[Group]):
            return SameFamily.Derive(first=a, second=b, family=f).when(
                MemberOf.Where(member=a, group=f),
                MemberOf.Where(member=b, group=f),
            )

    checked_with(make)
    checked = DerivedRegistry.checked["same_family"]
    assert checked.type_names == ["family"]
    assert checked.patterns == ["n_0", "n_1"]
    assert [(e.source, e.field, e.target, e.wrapped) for e in checked.edges] == [
        ("n_0", "member", "v_a", True),
        ("n_0", "group", "v_f", False),
        ("n_1", "member", "v_b", True),
        ("n_1", "group", "v_f", False),
    ]
    assert checked.symmetric == ("a", "b")
    assert checked.blocked == {"Hypothetical"}
    assert checked.exclusive == {"Alternative"}
    assert "SameFamily(a, b, f) :-" in checked.describe()
    # (what can trigger it: a head that can hold a MemberOf, inside spaces too; not a person)
    assert sorted(DerivedRegistry.triggers) == ["Factoid", "MemberOf"]


@no_type_check
def test_wrong_rules_are_refused_naming_the_rule_and_the_field():
    def wrong_variable_class(m):
        Person, Group, Place, MemberOf, SameFamily = (
            m[k] for k in ("Person", "Group", "Place", "MemberOf", "SameFamily")
        )

        @rule
        def bad(a: Var[Person], b: Var[Person], f: Var[Place]):
            return SameFamily.Derive(first=a, second=b, family=f).when(
                MemberOf.Where(member=a, group=f)
            )

    assert "family: a Var[Place] cannot be a Group" in refused(wrong_variable_class)

    def wrong_in_a_pattern(m):
        Person, Group, MemberOf, SameFamily = (
            m[k] for k in ("Person", "Group", "MemberOf", "SameFamily")
        )

        @rule
        def bad(a: Var[Person], b: Var[Person], f: Var[Group]):
            return SameFamily.Derive(first=a, second=b, family=f).when(
                MemberOf.Where(member=f, group=f),
                MemberOf.Where(member=b, group=a),
            )

    message = refused(wrong_in_a_pattern)
    assert message.startswith(
        "Rule bad: pattern 1, MemberOf: member: a Var[Group] ('f') cannot be what this field holds"
    )

    def not_bound(m):
        Person, Group, MemberOf, SameFamily = (
            m[k] for k in ("Person", "Group", "MemberOf", "SameFamily")
        )

        @rule
        def bad(a: Var[Person], b: Var[Person], f: Var[Group]):
            return SameFamily.Derive(first=a, second=b, family=f).when(
                MemberOf.Where(member=a, group=f)
            )

    assert (
        "the variable 'b' (of SameFamily.second) is in no pattern of the body"
        in refused(not_bound)
    )

    def in_an_or(m):
        Person, Group, MemberOf, SameFamily = (
            m[k] for k in ("Person", "Group", "MemberOf", "SameFamily")
        )

        @rule
        def bad(a: Var[Person], b: Var[Person], f: Var[Group]):
            return SameFamily.Derive(first=a, second=b, family=f).when(
                MemberOf.Where(member=a, group=f) | MemberOf.Where(member=b, group=f),
            )

    assert "cannot be inside '$any_of'" in refused(in_an_or)

    def literal_of_the_wrong_type(m):
        Person, Group, MemberOf, SameFamily = (
            m[k] for k in ("Person", "Group", "MemberOf", "SameFamily")
        )

        @rule
        def bad(a: Var[Person], b: Var[Person], f: Var[Group], y: Var[str]):
            return SameFamily.Derive(first=a, second=b, family=f).when(
                MemberOf.Where(member=a, group=f, year=y),
                MemberOf.Where(member=b, group=f),
            )

    assert "year: a Var[str] ('y') cannot be a value of this field (int)" in refused(
        literal_of_the_wrong_type
    )

    def not_annotated(m):
        @rule
        def bad(a):
            return None

    assert "the parameter 'a' must be annotated as a variable" in refused(not_annotated)

    def one_variable_twice(m):
        Person, Group, MemberOf, SameFamily = (
            m[k] for k in ("Person", "Group", "MemberOf", "SameFamily")
        )

        @rule
        def bad(a: Var[Person], f: Var[Group]):
            return SameFamily.Derive(first=a, second=a, family=f).when(
                MemberOf.Where(member=a, group=f)
            )

    assert "the two symmetric fields of SameFamily are the one variable 'a'" in refused(
        one_variable_twice
    )

    def constraint_on_nothing(m):
        Person, Group, MemberOf, SameFamily = (
            m[k] for k in ("Person", "Group", "MemberOf", "SameFamily")
        )

        @rule
        def bad(a: Var[Person], b: Var[Person], c: Var[Person], f: Var[Group]):
            return SameFamily.Derive(first=a, second=b, family=f).when(
                MemberOf.Where(member=a, group=f),
                MemberOf.Where(member=b, group=f),
                distinct(a, c),
            )

    assert "the variable 'c' of distinct(a, c) is in no pattern of the body" in refused(
        constraint_on_nothing
    )


@no_type_check
def test_a_var_of_a_trait_and_of_a_class_of_it_are_both_taken():
    def make(m):
        Person, Letter = m["Person"], m["Letter"]

        class Wrote(Derived):
            writer: Person
            other: Person

        @rule
        def wrote(a: Var[Person], b: Var[Person]):
            return Wrote.Derive(writer=a, other=b).when(
                Letter.Where(sender=a), Letter.Where(sender=b)
            )

    checked_with(make)
    assert "wrote" in DerivedRegistry.checked


@no_type_check
def test_a_search_has_no_variables():
    m = models()
    initialise(bind_database=False)
    Person, MemberOf = m["Person"], m["MemberOf"]
    pattern = MemberOf.Where(member=Var("a", Person))
    assert pattern.to_json() == {"member": {"$var": "a"}}
    with pytest.raises(PanglossSearchError, match="is only in a rule, not in a search"):
        check_match(MemberOf, Match(type="MemberOf", where=pattern))


@no_type_check
def test_a_derived_class_cannot_be_made_and_its_fields_are_checked():
    m = models()
    initialise(bind_database=False)
    with pytest.raises(TypeError, match="is derived, not made"):
        m["SameFamily"]()

    class Wrong(Derived):
        things: list[str]

    with pytest.raises(
        PanglossDerivedError,
        match="Wrong.things: a field of a Derived class is an entity",
    ):
        initialise(bind_database=False)


@no_type_check
def test_whether_the_body_is_the_same_with_the_two_ends_swapped_is_known():
    from pangloss_derived import lt

    def make(m):
        Person, Group, MemberOf, SameFamily = (
            m[k] for k in ("Person", "Group", "MemberOf", "SameFamily")
        )

        @rule
        def same_family(a: Var[Person], b: Var[Person], f: Var[Group]):
            return SameFamily.Derive(first=a, second=b, family=f).when(
                MemberOf.Where(member=a, group=f),
                MemberOf.Where(member=b, group=f),
            )

        @rule
        def joined_later(
            a: Var[Person], b: Var[Person], f: Var[Group], y1: Var[int], y2: Var[int]
        ):
            """(not the same with a and b swapped: the second joined after the first)"""
            return SameFamily.Derive(first=a, second=b, family=f).when(
                MemberOf.Where(member=a, group=f, year=y1),
                MemberOf.Where(member=b, group=f, year=y2),
                lt(y1, y2),
            )

    checked_with(make)
    assert DerivedRegistry.checked["same_family"].symmetric_body is True
    assert DerivedRegistry.checked["joined_later"].symmetric_body is False


@no_type_check
def test_a_variable_of_a_list_field_is_checked_against_its_items():
    def make(m):
        class Tagged(Entity):
            tags: list[str]

        class SameTag(Derived):
            _meta = Derived.Meta(symmetric=True)
            first: Tagged
            second: Tagged
            tag: int

        @rule
        def same_tag(a: Var[Tagged], b: Var[Tagged], t: Var[int]):
            return SameTag.Derive(first=a, second=b, tag=t).when(
                Tagged.Where(is_=a, tags=t), Tagged.Where(is_=b, tags=t)
            )

    assert "tags: a Var[int] ('t') cannot be a value of this field (str)" in refused(
        make
    )


@no_type_check
def test_a_symmetric_label_names_both_symmetric_fields():
    from typing import Annotated

    from pangloss_models import hooks

    from pangloss_derived import SymmetricLabel, translatable_models
    from pangloss_derived.read import symmetric_label_of

    def make(m):
        Person, Group = m["Person"], m["Group"]

        class InGroup(Derived):
            """In one group"""

            _meta = Derived.Meta(
                symmetric=True, reverse_names={"first": "in_group_with"}
            )
            first: Annotated[Person, SymmetricLabel("member")]
            second: Person
            group: Group

    m = checked_with(make)
    model = DerivedRegistry.classes["InGroup"]
    assert symmetric_label_of(model) == {
        "name": "member",
        "fields": ["first", "second"],
    }
    assert symmetric_label_of(m["SameFamily"]) is None
    # (the interface's translations: the two ends as one field, and the reverse names)
    (texts,) = [t for t in translatable_models() if t.name == "InGroup"]
    assert texts == hooks.TranslatableModel(
        name="InGroup",
        module=model.__module__,
        kind="Derived",
        description="In one group",
        fields={"member": ("", ""), "group": ("", "")},
        incoming=("in_group_with",),
    )


@no_type_check
def test_a_symmetric_label_is_refused_on_a_class_that_is_not_symmetric():
    from typing import Annotated

    from pangloss_derived import SymmetricLabel

    def make(m):
        Person = m["Person"]

        class GaveTo(Derived):
            giver: Annotated[Person, SymmetricLabel("party")]
            receiver: Person

    assert "a SymmetricLabel is for the fields of a symmetric class" in refused(make)


@no_type_check
def test_a_symmetric_label_is_refused_on_another_field():
    from typing import Annotated

    from pangloss_derived import SymmetricLabel

    def make(m):
        Person, Group = m["Person"], m["Group"]

        class InGroup(Derived):
            _meta = Derived.Meta(symmetric=True)
            first: Person
            second: Person
            group: Annotated[Group, SymmetricLabel("group")]

    assert "not another" in refused(make)


@no_type_check
def test_two_symmetric_labels_that_disagree_are_refused():
    from typing import Annotated

    from pangloss_derived import SymmetricLabel

    def make(m):
        Person = m["Person"]

        class InGroup(Derived):
            _meta = Derived.Meta(symmetric=True)
            first: Annotated[Person, SymmetricLabel("member")]
            second: Annotated[Person, SymmetricLabel("fellow")]

    assert "different SymmetricLabels: ['fellow', 'member']" in refused(make)
