"""`CriteriaMeta(allowed=True)` and `NoCriteria()`: a relation that takes an entity of a class that allows it takes a
description of one too, with no word of it in the annotation (implementation_docs/matches-criteria.md, "Stand-ins
that are generic")."""

import importlib
from typing import Annotated

import pangloss_criteria.models
import pytest
from pangloss_criteria import CriteriaMeta, NoCriteria, holders
from pangloss_criteria.meta import allows_criteria
from pangloss_models import (
    Document,
    EdgeModel,
    Entity,
    ModelRegistry,
    PanglossModelError,
    ReifiedRelation,
    Trait,
    ViaEdge,
    classes_stood_for,
    export_models,
    initialise,
)
from pydantic import ValidationError

MAX = "01a1c564-7def-70f0-bd21-410a35c82ab1"


def models():
    # (the registry was reset, and a module is only run once: its class is declared again)
    importlib.reload(pangloss_criteria.models)
    MatchesCriteria = pangloss_criteria.models.MatchesCriteria

    class Agent(Trait):
        pass

    class Person(Entity, Agent):
        _criteria_meta = CriteriaMeta(allowed=True)

    class Monk(Person):
        pass

    class Saint(Person):
        """(always known by name)"""

        _criteria_meta = CriteriaMeta(allowed=False)

    class Group(Entity, Agent):
        _criteria_meta = CriteriaMeta(allowed=True)

    class Place(Entity):
        pass

    class Certainty(EdgeModel):
        certainty: int = 100

    class InRole[T](ReifiedRelation[T]):
        role: str | None = None

    class HoldsOffice(Document):
        holder: Annotated[Person, NoCriteria()]
        employer: Annotated[Person, NoCriteria()]

    class Activity(Document):
        carried_out_by: list[Agent]
        witness: Person | None = None
        at: Place | None = None
        named: Annotated[Person, NoCriteria()] | None = None
        perhaps: list[ViaEdge[Person, Certainty]]
        in_role: list[InRole[Agent]]
        written_out: list[Group | MatchesCriteria[Group]]

    class Canonisation(Document):
        of: Saint
        at: Place

    initialise()
    return locals()


def descriptions_of(model, field: str) -> list[list[str]]:
    """The classes each description a relation takes stands among"""
    return sorted(
        sorted(
            o.annotated_type.__name__
            for o in option.parameter_type_options["T"].type_options
        )
        for option in model._meta.fields[field].type_options
        if getattr(getattr(option, "base_type", None), "__name__", "")
        == "MatchesCriteria"
    )


def described(type: str = "Person", **more) -> dict:
    return {"type": "MatchesCriteria", "criteria": {"type": type, "where": {}}, **more}


def activity(m, **given):
    return m["Activity"].Create(
        **{
            "label": "A",
            "carried_out_by": [],
            "perhaps": [],
            "in_role": [],
            "written_out": [],
            **given,
        }
    )


def test_a_class_says_whether_its_entities_may_be_described_and_a_subclass_follows_it():
    m = models()
    assert allows_criteria(m["Person"]) and allows_criteria(m["Group"])
    assert allows_criteria(m["Monk"])
    assert not allows_criteria(m["Saint"])
    assert not allows_criteria(m["Place"])
    # (a document is not described, whatever it says)
    assert not allows_criteria(m["Activity"])


def test_a_relation_takes_a_description_of_the_classes_that_allow_it():
    m = models()
    Activity = m["Activity"]
    # (through a trait: one description, of every class that allows it)
    assert descriptions_of(Activity, "carried_out_by") == [
        ["Group", "Monk", "Person", "Saint"]
    ]
    # (a class stands for those below it: a search for a person finds a saint, whatever the saint's class says)
    assert descriptions_of(Activity, "witness") == [["Monk", "Person", "Saint"]]
    assert descriptions_of(Activity, "at") == []
    # (a relation to the class that says no takes none)
    assert descriptions_of(m["Canonisation"], "of") == []
    # (through a wrapper)
    (in_role,) = Activity._meta.fields["in_role"].type_options
    assert sorted(
        getattr(o, "base_type", o.annotated_type).__name__
        for o in in_role.parameter_type_options["T"].type_options
    ) == ["Group", "MatchesCriteria", "Monk", "Person", "Saint"]


def test_a_field_refuses_it_with_no_criteria():
    m = models()
    assert descriptions_of(m["Activity"], "named") == []
    assert descriptions_of(m["HoldsOffice"], "holder") == []
    with pytest.raises(ValidationError):
        activity(m, named=described())
    assert activity(m, named={"type": "Person", "id": MAX}).named.type == "Person"


def test_a_description_written_in_the_annotation_is_the_one_there_is():
    m = models()
    assert descriptions_of(m["Activity"], "written_out") == [["Group"]]


def test_a_description_is_given_where_the_entity_goes():
    m = models()
    made = activity(
        m,
        carried_out_by=[
            {"type": "Person", "id": MAX},
            described(wording="N. N., secretarius"),
            described("Group", wording="a certain company"),
        ],
        witness=described("Monk"),
        in_role=[{"type": "InRole", "role": "scribe", "target": [described()]}],
    )
    assert [item.type for item in made.carried_out_by] == [
        "Person",
        "MatchesCriteria",
        "MatchesCriteria",
    ]
    assert made.carried_out_by[1].wording == "N. N., secretarius"
    assert made.witness.criteria.type == "Monk"
    assert made.in_role[0].target[0].type == "MatchesCriteria"
    # (not where the class does not allow it)
    with pytest.raises(ValidationError):
        activity(m, at=described("Place"))


def test_it_keeps_the_properties_of_the_relation():
    """ "perhaps (60%) the secretary" """
    m = models()
    made = activity(m, perhaps=[described(edge_properties={"certainty": 60})])
    (perhaps,) = made.perhaps
    assert perhaps.type == "MatchesCriteria"
    assert perhaps.edge_properties.certainty == 60


def test_its_criteria_are_of_a_class_the_relation_takes_and_that_allows_it():
    m = models()
    (description,) = activity(m, carried_out_by=[described()]).carried_out_by
    assert {c.__name__ for c in classes_stood_for(description, "T") or []} == {
        "Person",
        "Monk",
        "Saint",
        "Group",
    }
    saved = activity(m, witness=described("Monk"))._to_db_model()
    assert saved.witness.depends_on == ["Monk"]
    # (a group cannot witness; a place is no agent)
    for field, type in (("witness", "Group"), ("carried_out_by", "Place")):
        value = described(type)
        given = [value] if field == "carried_out_by" else value
        with pytest.raises(Exception) as refused:
            activity(m, **{field: given})._to_db_model()
        assert "criteria" in str(refused.value), (field, type)


def test_a_head_whose_relation_takes_a_description_by_the_setting_can_hold_one():
    m = models()
    assert holders.can_hold(m["Activity"])
    # (every field of it refuses, or is of a class that does not allow it)
    assert not holders.can_hold(m["HoldsOffice"])
    assert not holders.can_hold(m["Canonisation"])
    assert holders.pending_work_of(m["Activity"]) == ["criteria"]


def test_the_export_offers_it_as_a_reified_relation_of_the_field():
    models()
    fields = {
        field["name"]: field
        for field in export_models()["models"]["Activity"]["fields"]
    }
    (offered,) = [
        o
        for o in fields["carried_out_by"]["options"]
        if o.get("type") == "MatchesCriteria"
    ]
    (written,) = [
        o
        for o in fields["written_out"]["options"]
        if o.get("type") == "MatchesCriteria"
    ]
    assert offered["kind"] == written["kind"]
    assert sorted(o["type"] for o in offered["params"]["T"]["options"]) == [
        "Group",
        "Monk",
        "Person",
        "Saint",
    ]
    assert "MatchesCriteria" not in [o.get("type") for o in fields["named"]["options"]]


def test_a_class_that_allows_it_needs_the_app_that_declares_the_model():
    # (the registry was reset, and `pangloss_criteria.models` is not run again: the class is not declared)
    assert "MatchesCriteria" not in ModelRegistry._model_dict

    class Person(Entity):
        _criteria_meta = CriteriaMeta(allowed=True)

    class Activity(Document):
        carried_out_by: list[Person]

    with pytest.raises(PanglossModelError, match="INSTALLED_APPS"):
        initialise()


def test_without_the_setting_nothing_is_offered():
    importlib.reload(pangloss_criteria.models)

    class Person(Entity):
        pass

    class Activity(Document):
        carried_out_by: list[Person]

    initialise()
    assert descriptions_of(Activity, "carried_out_by") == []
    assert not holders.can_hold(Activity)
