"""`EventJudgement`, what a person says of two statements, and its check at `initialise()`
(`pangloss_compare.models`; implementation_docs/spaces-and-comparison-plan.md, step 6.5). No database."""

import importlib
from typing import no_type_check

import pytest
from pangloss_models import Cites, Document, Entity, PanglossModelError, initialise


@no_type_check
def base():
    """The package's models declared again (the registry is reset for each test)"""
    import pangloss_compare.models

    importlib.reload(pangloss_compare.models)
    return pangloss_compare.models.EventJudgement


@no_type_check
def statements():
    class Person(Entity):
        pass

    class Statement(Document):
        _meta = Document.Meta(abstract=True)

    class Birth(Statement):
        person: Person

    return Person, Statement, Birth


@no_type_check
def test_a_class_with_both_citing_fields_initialises_and_its_create_has_every_field():
    EventJudgement = base()
    _, Statement, _ = statements()

    class StatementJudgement(EventJudgement):
        statement: Cites[Statement]
        other: Cites[Statement]

    initialise()
    fields = set(StatementJudgement.Create.model_fields)
    assert {"statement", "other", "verdict", "fields", "note", "label"} <= fields
    # (the base is abstract: no routes, no nodes of its own; a label of every judgement)
    assert EventJudgement._meta.abstract is True
    assert not StatementJudgement._meta.abstract


@no_type_check
def test_a_verdict_is_one_of_the_seven():
    from pangloss_compare.models import VERDICTS

    EventJudgement = base()
    _, Statement, _ = statements()

    class StatementJudgement(EventJudgement):
        statement: Cites[Statement]
        other: Cites[Statement]

    initialise()
    assert VERDICTS == (
        "agree",
        "disagree",
        "two_events",
        "carried_out",
        "carried_out_otherwise",
        "not_carried_out",
        "breach",
    )
    them = {"type": "Birth", "id": "00000000-0000-0000-0000-000000000001"}
    made = StatementJudgement.Create(
        label="one", verdict="two_events", statement=them, other=them
    )
    assert made.fields == [] and made.note == ""
    with pytest.raises(ValueError):
        StatementJudgement.Create(
            label="one", verdict="maybe", statement=them, other=them
        )


@no_type_check
def test_a_class_without_the_citing_fields_is_refused_by_name():
    EventJudgement = base()
    _, Statement, _ = statements()

    class StatementJudgement(EventJudgement):
        statement: Cites[Statement]

    with pytest.raises(PanglossModelError) as refused:
        initialise()
    message = str(refused.value)
    assert message.startswith("StatementJudgement: ")
    assert "its field 'other' is missing" in message
    assert "`statement: Cites[Statement]` and `other: Cites[Statement]`" in message


@no_type_check
def test_a_list_of_citations_is_refused():
    EventJudgement = base()
    _, Statement, _ = statements()

    class StatementJudgement(EventJudgement):
        statement: list[Cites[Statement]]
        other: Cites[Statement]

    with pytest.raises(PanglossModelError, match="'statement' is a list"):
        initialise()


@no_type_check
def test_an_optional_citation_is_refused():
    EventJudgement = base()
    _, Statement, _ = statements()

    class StatementJudgement(EventJudgement):
        statement: Cites[Statement]
        other: Cites[Statement] | None = None

    with pytest.raises(PanglossModelError, match="'other' may be None"):
        initialise()


@no_type_check
def test_a_field_that_is_no_citation_is_refused():
    EventJudgement = base()
    Person, Statement, _ = statements()

    class StatementJudgement(EventJudgement):
        statement: Cites[Statement]
        other: Person

    with pytest.raises(PanglossModelError, match="'other' is not a citation"):
        initialise()


@no_type_check
def test_a_literal_field_is_refused():
    EventJudgement = base()
    _, Statement, _ = statements()

    class StatementJudgement(EventJudgement):
        statement: Cites[Statement]
        other: str

    with pytest.raises(PanglossModelError, match="'other' is not a citation"):
        initialise()


@no_type_check
def test_a_citation_that_does_not_protect_is_refused():
    EventJudgement = base()
    _, Statement, _ = statements()

    class Loosely[T](Cites[T]):
        protect = False

    class StatementJudgement(EventJudgement):
        statement: Cites[Statement]
        other: Loosely[Statement]

    with pytest.raises(PanglossModelError, match="does not protect"):
        initialise()


@no_type_check
def test_an_abstract_class_below_needs_no_fields_and_a_concrete_one_below_it_does():
    EventJudgement = base()
    _, Statement, _ = statements()

    class Judged(EventJudgement):
        _meta = Document.Meta(abstract=True)
        statement: Cites[Statement]

    class StatementJudgement(Judged):
        pass

    with pytest.raises(PanglossModelError, match="^StatementJudgement: .*'other' is missing"):  # fmt: skip
        initialise()


@no_type_check
def test_no_judgement_class_is_no_refusal():
    base()
    statements()
    initialise()


@no_type_check
def test_a_field_s_name_is_resolved_against_the_statements_classes_by_the_name_comparison_gives_it():
    """camelCase as `to_camel` gives a field's name, or the field's own, whatever capitals or digits it has; a
    narrowed field by the name of the field it narrows (as the verdict names it); none of either class: None"""
    from pangloss_compare import CompareMeta
    from pangloss_compare.models import python_name, resolved
    from pangloss_models import RelationConfig
    from pangloss_models.field_definitions import FieldSubclassing
    from typing import Annotated

    base()
    Person, Statement, Birth = statements()

    class Thing(Entity):
        pass

    class Picture(Thing):
        pass

    class Odd(Statement):
        field_2: str = ""
        source_URL: str = ""
        carried_out_by: Person

    class Making(Statement):
        made: Thing
        _compare_meta = CompareMeta(identifying=["made"])

    class MakingOfPicture(Making):
        picture_made: Annotated[
            Picture,
            RelationConfig(
                subclasses_parent_fields=[
                    FieldSubclassing("made", field_on_model=Making)
                ]
            ),  # fmt: skip
        ]

    initialise()
    for given, stored in [
        ("field2", "field_2"),
        ("field_2", "field_2"),
        ("source_URL", "source_URL"),
        ("sourceUrl", "source_URL"),  # (what `to_camel` gives of it, and so the route)
        ("carriedOutBy", "carried_out_by"),
        ("carried_out_by", "carried_out_by"),
    ]:
        assert resolved(given, [Birth, Odd]) == stored, given
    assert resolved("pictureMade", [MakingOfPicture]) == "made"
    assert resolved("made", [MakingOfPicture]) == "made"
    assert resolved("colourOfEyes", [Birth, Odd]) is None
    # (only where no class can be read: pydantic's conversion)
    assert python_name("givenTo") == "given_to" and python_name("field2") == "field2"


@no_type_check
def test_no_class_holds_a_judgement_as_a_part_of_it():
    """A judgement is never updated, and a document holding one would be written again with it: refused at
    `initialise()`, directly, in a list, or inside a space; citing one is not holding it"""
    from pangloss_models import SemanticSpace

    for holding in ("one", "many", "space"):
        ModelRegistry_reset()
        EventJudgement = base()
        _, Statement, _ = statements()

        class StatementJudgement(EventJudgement):
            statement: Cites[Statement]
            other: Cites[Statement]

        class Said[T](SemanticSpace[T]):
            pass

        if holding == "one":

            class Holder(Document):
                judged: StatementJudgement

        elif holding == "many":

            class Holder(Document):
                judged: list[StatementJudgement]

        else:

            class Holder(Document):
                judged: Said[StatementJudgement]

        with pytest.raises(PanglossModelError, match=r"Holder\.judged holds StatementJudgement, a judgement, as a part of it"):  # fmt: skip
            initialise()

    ModelRegistry_reset()
    EventJudgement = base()
    _, Statement, _ = statements()

    class CitedJudgement(EventJudgement):
        statement: Cites[Statement]
        other: Cites[Statement]

    class Review(Document):
        judgements: list[Cites[CitedJudgement]] = []

    initialise()


def ModelRegistry_reset():
    from pangloss_models import ModelRegistry

    ModelRegistry._reset()


@no_type_check
def test_a_judgement_refuses_any_update_and_checks_what_it_judges_before_it_is_made():
    """(`@before_update` and `@before_create`: run on the server by every write; the refusals themselves are tried
    live, `tests/live/test_compare_route_live.py`)"""
    from pangloss_models.write_checks import marked

    EventJudgement = base()
    assert set(marked(EventJudgement, "before_update")) == {"refuse_any_update"}
    assert set(marked(EventJudgement, "before_create")) == {"check_what_is_judged"}
