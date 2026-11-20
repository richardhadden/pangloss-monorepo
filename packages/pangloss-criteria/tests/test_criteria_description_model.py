"""`Description`, a shared description, and the field of a mention that cites it (implementation_docs/matches-criteria.md,
"Shared descriptions"): what may be written of them, before anything is saved"""

import importlib
from typing import no_type_check

import pangloss_criteria.models
import pytest
from pangloss_criteria import CriteriaMeta, SearchPattern
from pangloss_models import Document, Entity, PanglossWriteRefused, initialise
from pydantic import ValidationError

SHARED_ID = "01a1c564-7def-70f0-bd21-410a35c82ab9"


def models():
    importlib.reload(pangloss_criteria.models)
    Description = pangloss_criteria.models.Description

    class Person(Entity):
        _criteria_meta = CriteriaMeta(allowed=True)

    class Office(Entity):
        pass

    class Activity(Document):
        carried_out_by: list[Person]

    initialise()
    return Description, Person, Activity


PEOPLE = {"type": "Person", "where": {}}


@no_type_check
def test_a_shared_description_has_a_label_and_criteria_of_an_entity_class():
    Description, Person, Activity = models()
    made = Description.Create(label="Maximilian's secretary", criteria=PEOPLE)
    assert made.criteria == SearchPattern(PEOPLE)
    made._to_db_model()
    with pytest.raises(ValidationError):
        Description.Create(label="No criteria")
    with pytest.raises(ValidationError):
        Description.Create(criteria=PEOPLE)
    # (of a document class, or of a field the class does not have: checked as a stored pattern is)
    for wrong in (
        {"type": "Activity", "where": {}},
        {"type": "Person", "where": {"nothing": {"eq": 1}}},
        {"type": "Person", "where": {"$var": "x"}},
    ):
        with pytest.raises(ValidationError, match="criteria"):
            Description.Create(label="Wrong", criteria=wrong)._to_db_model()


@no_type_check
def test_it_is_not_in_search_everything_and_not_reviewed():
    Description, Person, Activity = models()
    assert Description._meta.global_search is False
    assert getattr(Description, "_review_meta", None) is None


@no_type_check
def test_its_page_and_form_are_the_modules_and_the_export_says_so():
    from pangloss_interface.meta import export_definitions

    Description, Person, Activity = models()
    meta = export_definitions()["models"]["Description"]["interfaceMeta"]
    assert meta["itemPage"] == {
        "module": "pangloss_criteria",
        "name": "DescriptionPage",
    }
    assert meta["hideOnForms"] == ["criteria"]


@no_type_check
def test_a_mention_may_cite_one_and_need_hold_nothing_else():
    Description, Person, Activity = models()
    Activity_ = Activity
    made = Activity_.Create(
        label="A letter",
        carried_out_by=[
            {
                "type": "MatchesCriteria",
                "description": {"type": "Description", "id": SHARED_ID},
            }
        ],
    )
    (mention,) = made.carried_out_by
    assert str(mention.description.target_id) == SHARED_ID
    assert mention.criteria is None
    written = made._to_db_model().carried_out_by[0]
    # (what T stands for, kept for a change of the shared description; the rest is worked out before the save)
    assert written.stands_for == ["Person"]
    assert written.criteria_hash is None


@no_type_check
def test_a_mention_with_no_criteria_no_description_and_no_mark_is_refused():
    Description, Person, Activity = models()
    with pytest.raises(PanglossWriteRefused, match="shared description"):
        from pangloss_cypher.write_functions import to_db_model

        to_db_model(
            Activity.Create(
                label="A letter",
                carried_out_by=[{"type": "MatchesCriteria", "wording": "N. N."}],
            )
        )


@no_type_check
def test_its_own_criteria_beside_a_description_are_checked_as_a_pattern_of_their_own():
    Description, Person, Activity = models()
    from pangloss_cypher.write_functions import to_db_model

    with pytest.raises(PanglossWriteRefused, match="criteria"):
        to_db_model(
            Activity.Create(
                label="A letter",
                carried_out_by=[
                    {
                        "type": "MatchesCriteria",
                        "description": {"type": "Description", "id": SHARED_ID},
                        "criteria": {"type": "Person", "where": {"nothing": {"eq": 1}}},
                    }
                ],
            )
        )
