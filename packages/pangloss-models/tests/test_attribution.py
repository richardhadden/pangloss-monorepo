"""`Attribution(by=..., to=...)` (`pangloss_models.markers`): kept on the definition of the field that holds a space
in each shape of annotation, read back by `attribution_of` and `attributions`, checked at `initialise()`
(`check_attributions`: each refusal by its message, a misspelt name with its fix) and exported as the field's
`attribution`. (Each refused class has a name of its own: a fix finds its class in the source by name)"""

from typing import Annotated, no_type_check

import pytest
from pangloss_models import (
    Attribution,
    Document,
    Embedded,
    Entity,
    PanglossModelError,
    ReifiedRelation,
    SemanticSpace,
    export_models,
    initialise,
)
from pangloss_models.diagnostics import _did_you_mean_fixes
from pangloss_models.markers import attribution_of, attributions


@no_type_check
def declare_base():
    class Person(Entity):
        pass

    class Reported[T](SemanticSpace[T]):
        pass

    class Negative[T](SemanticSpace[T]):
        pass

    class InRole[T](ReifiedRelation[T]):
        pass

    class Statement(Document):
        pass

    return Person, Reported, Negative, InRole, Statement


def refused() -> PanglossModelError:
    with pytest.raises(PanglossModelError) as raised:
        initialise(bind_database=False)
    return raised.value


def fields_of(name: str) -> dict:
    return {field["name"]: field for field in export_models()["models"][name]["fields"]}


# --- kept on the definition ---------------------------------------------------------------


@no_type_check
def test_the_marker_is_kept_on_the_definition_in_each_shape_of_annotation():
    Person, Reported, Negative, _, Statement = declare_base()

    class Report(Document):
        reporter: Person
        hearers: list[Person]
        one: Annotated[Reported[Statement], Attribution(by="reporter")]
        many: Annotated[list[Reported[Statement]], Attribution(to="hearers")]
        mixed: Annotated[
            list[Statement | Negative[Statement]],
            Attribution(by="reporter", to="hearers"),
        ]
        perhaps: Annotated[Reported[Statement] | None, Attribution(by="reporter")]

    initialise(bind_database=False)
    fields = Report._meta.fields
    assert attribution_of(fields["one"]) == Attribution(by="reporter")
    assert attribution_of(fields["many"]) == Attribution(to="hearers")
    assert attribution_of(fields["mixed"]) == Attribution(by="reporter", to="hearers")
    assert attribution_of(fields["perhaps"]) == Attribution(by="reporter")
    assert fields["perhaps"].optional
    assert attribution_of(fields["reporter"]) is None
    assert attributions(Report) == {
        "one": Attribution(by="reporter"),
        "many": Attribution(to="hearers"),
        "mixed": Attribution(by="reporter", to="hearers"),
        "perhaps": Attribution(by="reporter"),
    }


def test_the_marker_is_frozen_keyword_only_and_compared_by_its_names():
    assert Attribution(by="a", to="b") == Attribution(by="a", to="b")
    assert Attribution(by="a") != Attribution(to="a")
    assert hash(Attribution(by="a")) == hash(Attribution(by="a"))
    with pytest.raises(TypeError):
        Attribution("a")  # ty: ignore[too-many-positional-arguments]
    with pytest.raises(AttributeError):
        Attribution(by="a").by = "b"  # ty: ignore[invalid-assignment]


@no_type_check
def test_a_subclass_inherits_the_marker_and_may_have_another_field_of_its_own():
    Person, Reported, Negative, _, Statement = declare_base()

    class Order(Document):
        ordered_by: Person
        ordered_to: list[Person]
        thing_ordered: Annotated[
            Reported[Statement], Attribution(by="ordered_by", to="ordered_to")
        ]

    class Countermand(Order):
        # (two attributed fields, naming the same person fields)
        refused: Annotated[Negative[Statement], Attribution(by="ordered_to")]

    initialise(bind_database=False)
    assert attributions(Order) == {
        "thing_ordered": Attribution(by="ordered_by", to="ordered_to")
    }
    assert attributions(Countermand) == {
        "thing_ordered": Attribution(by="ordered_by", to="ordered_to"),
        "refused": Attribution(by="ordered_to"),
    }
    assert attributions(Person) == {}


# --- what is accepted ---------------------------------------------------------------------


@no_type_check
def test_the_names_may_be_one_field_and_reach_an_entity_behind_a_wrapper_or_among_documents():
    Person, Reported, _, InRole, Statement = declare_base()

    class Place(Entity):
        pass

    class Letter(Document):
        pass

    class Belief(Document):
        holder: Person | None
        roles: list[InRole[Person]]
        either: list[Person | Place]
        or_a_letter: list[Person | Letter]
        same: Annotated[Reported[Statement], Attribution(by="holder", to="holder")]
        through: Annotated[Reported[Statement], Attribution(by="roles")]
        union: Annotated[Reported[Statement], Attribution(by="either")]
        mixed: Annotated[Reported[Statement], Attribution(to="or_a_letter")]

    initialise(bind_database=False)
    assert len(attributions(Belief)) == 4


# --- the refusals -------------------------------------------------------------------------


@no_type_check
def test_an_attribution_that_names_no_field_is_refused():
    _, Reported, _, _, Statement = declare_base()

    class NamesNone(Document):
        said: Annotated[Reported[Statement], Attribution()]

    message = str(refused())
    assert "NamesNone.said" in message
    assert "names no field" in message


@no_type_check
def test_an_attribution_on_a_field_that_holds_no_space_is_refused():
    Person, _, _, InRole, Statement = declare_base()

    class OnPlainRelation(Document):
        by: Person
        said: Annotated[list[Statement | InRole[Person]], Attribution(by="by")]

    message = str(refused())
    assert "OnPlainRelation.said" in message
    assert "holds a semantic space" in message


@no_type_check
def test_an_attribution_on_a_literal_field_is_refused():
    Person, _, _, _, _ = declare_base()

    class OnLiteral(Document):
        by: Person
        said: Annotated[str, Attribution(by="by")]

    message = str(refused())
    assert "OnLiteral.said" in message
    assert "holds a semantic space" in message


@no_type_check
def test_an_attribution_on_an_embedded_field_is_refused_and_not_lost():
    Person, _, _, _, _ = declare_base()

    class Folio(Embedded):
        number: int

    class OnEmbedded(Document):
        by: Person
        at: Annotated[Folio, Attribution(by="by")]

    message = str(refused())
    assert "OnEmbedded.at" in message
    assert "holds a semantic space" in message


@no_type_check
def test_a_misspelt_name_is_refused_with_the_closest_field_as_its_fix():
    Person, Reported, _, _, Statement = declare_base()

    class Misspelt(Document):
        ordered_by: Person
        thing_ordered: Annotated[Reported[Statement], Attribution(by="orderd_by")]

    error = refused()
    message = str(error)
    assert "Misspelt.thing_ordered" in message
    assert "has no field 'orderd_by'" in message
    assert "Did you mean 'ordered_by'?" in message
    assert error.at_string is not None
    (fix,) = _did_you_mean_fixes(Misspelt, "thing_ordered", error.at_string)
    assert fix.title == 'Change to "ordered_by"'
    (edit,) = fix.edits
    assert (edit.old_text, edit.new_text) == ('"orderd_by"', '"ordered_by"')


@no_type_check
def test_a_name_of_a_field_of_no_other_class_is_refused():
    _, Reported, _, _, Statement = declare_base()

    class Elsewhere(Document):
        said: Annotated[Reported[Statement], Attribution(to="nobody_at_all")]

    message = str(refused())
    assert "Elsewhere.said: Attribution(to='nobody_at_all')" in message
    assert "has no field" in message


@no_type_check
def test_naming_the_marked_field_itself_is_refused():
    _, Reported, _, _, Statement = declare_base()

    class Itself(Document):
        said: Annotated[Reported[Statement], Attribution(by="said")]

    message = str(refused())
    assert "Itself.said: Attribution(by='said')" in message
    assert "names the field it is on" in message


@no_type_check
def test_a_name_of_a_relation_only_to_documents_is_refused():
    _, Reported, _, InRole, Statement = declare_base()

    class Letter(Document):
        pass

    class ToDocuments(Document):
        letters: list[Letter | InRole[Letter]]
        said: Annotated[Reported[Statement], Attribution(by="letters")]

    message = str(refused())
    assert "ToDocuments.said: Attribution(by='letters')" in message
    assert "reaches only documents" in message


@no_type_check
def test_a_name_of_a_literal_is_refused():
    _, Reported, _, _, Statement = declare_base()

    class ToLiteral(Document):
        written_by: str
        said: Annotated[Reported[Statement], Attribution(by="written_by")]

    message = str(refused())
    assert "ToLiteral.said: Attribution(by='written_by')" in message
    assert "ToLiteral.written_by is not a relation" in message


@no_type_check
def test_two_attributions_on_one_field_are_refused():
    Person, Reported, _, _, Statement = declare_base()

    class Twice(Document):
        by: Person
        said: Annotated[Reported[Statement], Attribution(by="by"), Attribution(to="by")]

    message = str(refused())
    assert "Twice.said has 2 Attribution markers" in message


@no_type_check
def test_a_subclass_in_which_the_named_field_no_longer_reaches_an_entity_is_refused_by_its_own_name():
    Person, Reported, _, _, Statement = declare_base()

    class Mention(Document):
        pass

    class Claim(Document):
        claimed_by: Person | Mention
        claim: Annotated[Reported[Statement], Attribution(by="claimed_by")]

    class NarrowedClaim(Claim):
        claimed_by: Mention

    message = str(refused())
    assert "NarrowedClaim.claim: Attribution(by='claimed_by')" in message
    assert "reaches only documents" in message


# --- the export ---------------------------------------------------------------------------


@no_type_check
def test_the_export_names_each_field_by_name_and_key_and_is_absent_without_one():
    Person, Reported, _, _, Statement = declare_base()

    class Order(Document):
        ordered_by: Person
        ordered_to: list[Person]
        thing_ordered: Annotated[
            Reported[Statement], Attribution(by="ordered_by", to="ordered_to")
        ]
        believed: Annotated[Reported[Statement], Attribution(by="ordered_by")]
        addressed: Annotated[Reported[Statement], Attribution(to="ordered_to")]
        plain: Reported[Statement]

    initialise(bind_database=False)
    fields = fields_of("Order")
    assert fields["thing_ordered"]["attribution"] == {
        "by": {"name": "ordered_by", "key": "orderedBy"},
        "to": {"name": "ordered_to", "key": "orderedTo"},
    }
    assert fields["believed"]["attribution"] == {
        "by": {"name": "ordered_by", "key": "orderedBy"},
        "to": None,
    }
    assert fields["addressed"]["attribution"] == {
        "by": None,
        "to": {"name": "ordered_to", "key": "orderedTo"},
    }
    # (absent, not null; and not said again among the field's markers)
    for name in ("plain", "ordered_by", "ordered_to"):
        assert "attribution" not in fields[name]
    assert "markers" not in fields["thing_ordered"]


@no_type_check
def test_a_subclass_exports_the_attribution_it_inherits():
    Person, Reported, _, _, Statement = declare_base()

    class Order(Document):
        ordered_by: Person
        thing_ordered: Annotated[Reported[Statement], Attribution(by="ordered_by")]

    class RoyalOrder(Order):
        pass

    initialise(bind_database=False)
    assert fields_of("RoyalOrder")["thing_ordered"]["attribution"] == {
        "by": {"name": "ordered_by", "key": "orderedBy"},
        "to": None,
    }
