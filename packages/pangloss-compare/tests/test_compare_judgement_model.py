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
