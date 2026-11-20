"""`MatchesCriteria[T]` as a model: what a client writes and reads of it, what the server works out of its criteria
when it is written, and which classes can hold one (implementation_docs/matches-criteria.md, "The model")."""

import importlib
import pangloss_criteria.models
import pytest
from pangloss_criteria import holders
from pangloss_criteria.analysis import shape_of
from pangloss_criteria.models import classes_touched
from pangloss_criteria.pattern import SearchPattern, check_stored
from pangloss_models import (
    Cites,
    Conjunction,
    Document,
    EdgeModel,
    Embedded,
    Entity,
    ReifiedRelation,
    SemanticSpace,
    Trait,
    ViaEdge,
    classes_stood_for,
    export_models,
    initialise,
)
from pangloss_models.computed import computed_fields
from pangloss_users import see_unpublished
from pydantic import ValidationError

MAX = "01a1c564-7def-70f0-bd21-410a35c82ab1"
SEC = "01a1c564-7def-70f0-bd21-410a35c82ab2"
ONE = "01a1c564-7def-70f0-bd21-410a35c82ab3"


def criteria_class():
    # (the registry was reset, and a module is only run once: its class is declared again)
    importlib.reload(pangloss_criteria.models)
    return pangloss_criteria.models.MatchesCriteria


def models():
    MatchesCriteria = criteria_class()

    class Agent(Trait):
        pass

    class Person(Entity, Agent):
        pass

    class Group(Entity, Agent):
        pass

    class Office(Entity):
        pass

    class InRole[T](ReifiedRelation[T]):
        role: str | None = None

    class HoldsOffice(Document):
        holder: Person
        office: Office
        employer: Person

    class Activity(Document):
        carried_out_by: list[Person | MatchesCriteria[Person]]
        ordered_by: list[InRole[Person | Group | MatchesCriteria[Person | Group]]]
        place: Office | None = None

    initialise()
    return MatchesCriteria, Person, Group, Office, HoldsOffice, Activity


SECRETARY = {
    "type": "Person",
    "where": {
        "$incoming": [
            {
                "type": "HoldsOffice",
                "field": "holder",
                "where": {"office": {"is": SEC}, "employer": {"is": MAX}},
            }
        ]
    },
}


def described(criteria=SECRETARY, **more):
    return {"type": "MatchesCriteria", "criteria": criteria, **more}


def activity(Activity, *carried_out_by, ordered_by=()):
    return Activity.Create(
        label="A", carried_out_by=list(carried_out_by), ordered_by=list(ordered_by)
    )


# --- what is written and read -----------------------------------------------------------------------------------------


def test_a_client_writes_the_wording_and_the_criteria_and_nothing_else():
    MatchesCriteria, Person, Group, Office, HoldsOffice, Activity = models()

    made = activity(Activity, described(wording="N. N., secretarius"))

    (description,) = made.carried_out_by
    assert set(type(description).model_fields) == {
        "type",
        "wording",
        "criteria",
        "same_one",
    }
    assert description.wording == "N. N., secretarius"
    assert description.criteria == SearchPattern(SECRETARY)
    with pytest.raises(ValidationError):
        activity(Activity, described(candidates=[]))


def test_what_a_read_gave_is_taken_back_without_what_was_computed():
    MatchesCriteria, Person, Group, Office, HoldsOffice, Activity = models()

    made = activity(
        Activity,
        described(
            wording="N. N.",
            target=[{"type": "Person", "id": ONE, "label": "Waldauf"}],
            candidateCount=3,
            evaluatedWhen="2026-11-19T10:12:00Z",
            broken=None,
        ),
    )

    assert set(made.carried_out_by[0].model_dump()) == {
        "type",
        "wording",
        "criteria",
        "same_one",
    }


def test_a_read_has_the_candidates_and_what_is_said_of_them():
    MatchesCriteria, Person, Group, Office, HoldsOffice, Activity = models()

    view = Activity.View(
        id=ONE,
        type="Activity",
        label="A",
        ordered_by=[],
        carried_out_by=[
            {
                "type": "MatchesCriteria",
                "id": MAX,
                "wording": "N. N.",
                "criteria": SearchPattern(SECRETARY).text(),
                "target": [{"type": "Person", "id": SEC, "label": "Waldauf"}],
                "candidate_count": 3,
                "candidate_count_everyone": 1,
                "evaluated_when": "2026-11-19T10:12:00Z",
            }
        ],
    )

    (description,) = view.carried_out_by
    dumped = description.model_dump(mode="json", by_alias=True)
    assert set(dumped) == {
        "id",
        "type",
        "wording",
        "criteria",
        "sameOne",
        "target",
        "candidateCount",
        "evaluatedWhen",
        "broken",
        "brokenSince",
    }
    assert dumped["criteria"] == SECRETARY
    assert dumped["target"][0]["label"] == "Waldauf" and dumped["candidateCount"] == 3


def test_a_view_gives_one_count_the_readers_own():
    MatchesCriteria, Person, Group, Office, HoldsOffice, Activity = models()
    stored = {
        "id": ONE,
        "type": "Activity",
        "label": "A",
        "ordered_by": [],
        "carried_out_by": [
            {
                "type": "MatchesCriteria",
                "id": MAX,
                "criteria": SECRETARY,
                "candidate_count": 5,
                "candidate_count_everyone": 2,
            }
        ],
    }

    assert Activity.View(**stored).carried_out_by[0].candidate_count == 5
    token = see_unpublished.set(False)
    try:
        public = Activity.View(**stored)
        head = Activity.HeadView(
            **stored,
            meta={
                "created_when": "2026-11-19T10:00:00Z",
                "updated_by": None,
                "updated_when": None,
            },
        )
    finally:
        see_unpublished.reset(token)
    assert public.carried_out_by[0].candidate_count == 2
    assert head.carried_out_by[0].candidate_count == 2
    # (a description with no count kept for everyone, as a client's copy of a read: left as it is)
    del stored["carried_out_by"][0]["candidate_count_everyone"]
    token = see_unpublished.set(False)
    try:
        assert Activity.View(**stored).carried_out_by[0].candidate_count == 5
    finally:
        see_unpublished.reset(token)


def test_the_candidates_and_the_counts_are_computed_fields():
    MatchesCriteria, Person, Group, Office, HoldsOffice, Activity = models()

    fields = computed_fields(MatchesCriteria)

    assert sorted(fields.relations) == ["target"]
    assert sorted(fields.values) == [
        "broken",
        "broken_since",
        "candidate_count",
        "candidate_count_everyone",
        "evaluated_when",
    ]
    exported = {
        f["name"]: f for f in export_models()["models"]["MatchesCriteria"]["fields"]
    }
    assert exported["target"]["computed"] and exported["candidate_count"]["computed"]
    assert not exported["criteria"]["computed"] and not exported["wording"]["computed"]
    assert exported["criteria"]["type"] == {"type": "str", "format": "search-pattern"}
    assert exported["criteria_hash"]["dbField"] is True


# --- what the server works out when it is written ---------------------------------------------------------------------


def test_the_server_works_out_the_hash_the_names_and_the_classes_touched():
    MatchesCriteria, Person, Group, Office, HoldsOffice, Activity = models()

    written = activity(Activity, described())._to_db_model().carried_out_by[0]

    assert len(written.criteria_hash) == 40
    assert sorted(written.names) == sorted([SEC, MAX])
    assert written.depends_on == ["Person", "HoldsOffice"]
    # (`analysis`: one `$incoming` that names both: complete, and a write must name one of each to bear on it)
    assert written.reach == "local"
    assert sorted(written.anchors) == sorted([SEC, MAX])
    assert written.shape == shape_of(SearchPattern(SECRETARY))
    assert len(written.shape) == 40


def test_the_same_criteria_have_the_same_hash_however_they_were_written():
    MatchesCriteria, Person, Group, Office, HoldsOffice, Activity = models()
    reordered = {
        "where": {
            "$incoming": [
                {
                    "where": {"employer": {"is": MAX}, "office": {"is": SEC}},
                    "field": "holder",
                    "type": "HoldsOffice",
                }
            ]
        },
        "type": "Person",
    }
    other = {"type": "Person", "where": {"label": {"eq": "x"}}}

    def written(criteria):
        return activity(Activity, described(criteria))._to_db_model().carried_out_by[0]

    assert written(SECRETARY).criteria_hash == written(reordered).criteria_hash
    assert written(SECRETARY).names == written(reordered).names
    assert written(SECRETARY).criteria_hash != written(other).criteria_hash
    assert written(other).names == [] and written(other).depends_on == ["Person"]


def test_a_description_written_again_is_checked_and_worked_out_again():
    MatchesCriteria, Person, Group, Office, HoldsOffice, Activity = models()

    update = Activity.Update(
        id=ONE,
        label="A",
        ordered_by=[],
        carried_out_by=[described(id=MAX, wording="N. N.")],
    )

    written = update._to_db_model().carried_out_by[0]
    assert type(written).__name__.endswith("UpdateDB")
    assert len(written.criteria_hash) == 40 and written.depends_on == [
        "Person",
        "HoldsOffice",
    ]
    with pytest.raises(ValidationError, match="criteria: nothing: Person has no field"):
        Activity.Update(
            id=ONE,
            label="A",
            ordered_by=[],
            carried_out_by=[
                described({"type": "Person", "where": {"nothing": {"eq": 1}}}, id=MAX)
            ],
        )._to_db_model()


def test_the_classes_a_pattern_touches_are_those_of_every_pattern_in_it():
    MatchesCriteria, Person, Group, Office, HoldsOffice, Activity = models()
    pattern = SearchPattern(
        {
            "type": "Person",
            "where": {
                "$incoming": [
                    {
                        "type": "HoldsOffice",
                        "where": {"office": {"type": "Office", "where": {}}},
                    },
                    {
                        "type": "Activity",
                        "where": {
                            "ordered_by": {"is": ONE, "through": ["InRole"]},
                            "$not": {
                                "place": {
                                    "type": "Office",
                                    "where": {"label": {"eq": "x"}},
                                }
                            },
                        },
                    },
                ]
            },
        }
    )

    assert sorted(classes_touched(Person, check_stored(pattern))) == [
        "Activity",
        "HoldsOffice",
        "InRole",
        "Office",
        "Person",
    ]


# --- what may be described where --------------------------------------------------------------------------------------


def test_a_description_needs_criteria_of_a_class_it_stands_among():
    MatchesCriteria, Person, Group, Office, HoldsOffice, Activity = models()

    def refused(description):
        with pytest.raises(ValidationError) as error:
            activity(Activity, description)._to_db_model()
        return str(error.value)

    assert "a description needs the criteria it is of" in refused(
        {"type": "MatchesCriteria", "wording": "N. N."}
    )
    assert "criteria: type: 'Office' is not what is described here (Person)" in refused(
        described({"type": "Office"})
    )
    # (a group is not what carries the activity out, here; it may be what orders it)
    assert "criteria: type: 'Group' is not what is described here (Person)" in refused(
        described({"type": "Group"})
    )
    ordered = activity(
        Activity,
        ordered_by=[
            {
                "type": "InRole",
                "role": "patron",
                "target": [described({"type": "Group"})],
            }
        ],
    )._to_db_model()
    inner = ordered.ordered_by[0].target[0]
    assert inner.depends_on == ["Group"]
    assert sorted(c.__name__ for c in classes_stood_for(inner, "T") or []) == [
        "Group",
        "Person",
    ]


def test_the_classes_a_generic_stands_for_are_known_to_the_models_made_for_its_use():
    MatchesCriteria, Person, Group, Office, HoldsOffice, Activity = models()
    made = activity(
        Activity,
        described(),
        ordered_by=[{"type": "InRole", "target": [{"type": "Person", "id": ONE}]}],
    )

    assert classes_stood_for(made.carried_out_by[0], "T") == [Person]
    assert classes_stood_for(type(made.carried_out_by[0]), "T") == [Person]
    # (through the wrappers inside it: what an `InRole` here can be of in the end)
    assert sorted(
        c.__name__ for c in classes_stood_for(made.ordered_by[0], "T") or []
    ) == [
        "Group",
        "Person",
    ]
    # (not a use of a generic, or no such variable)
    assert classes_stood_for(made) is None
    assert classes_stood_for(made.carried_out_by[0], "X") is None
    assert classes_stood_for(MatchesCriteria.Create) is None


def test_criteria_that_would_pass_through_a_description_are_refused():
    MatchesCriteria, Person, Group, Office, HoldsOffice, Activity = models()
    through = {
        "type": "Person",
        "where": {"$incoming": [{"type": "Activity", "through": ["MatchesCriteria"]}]},
    }

    with pytest.raises(
        ValidationError, match="'MatchesCriteria' is a wrapper the search leaves out"
    ):
        activity(Activity, described(through))._to_db_model()
    # (through another wrapper is as in any search)
    activity(
        Activity,
        described(
            {
                "type": "Person",
                "where": {"$incoming": [{"type": "Activity", "through": ["InRole"]}]},
            }
        ),
    )._to_db_model()


# --- which classes can hold one ---------------------------------------------------------------------------------------


def test_a_head_can_hold_a_description_in_a_relation_of_its_own_or_through_a_wrapper():
    MatchesCriteria, Person, Group, Office, HoldsOffice, Activity = models()

    assert holders.can_hold(Activity) is True
    assert holders.can_hold(HoldsOffice) is False
    assert holders.can_hold(Person) is False
    assert holders.pending_work_of(Activity) == ["criteria"]
    # (it holds none, but criteria of a person reach it: `test_criteria_reached.py`)
    assert holders.pending_work_of(HoldsOffice) == ["criteria"]
    assert holders.description_labels() == ["MatchesCriteria"]


def test_a_head_can_hold_one_in_a_document_nested_in_it_at_any_depth():
    MatchesCriteria = criteria_class()

    class Certainty(EdgeModel):
        percent: int

    class Person(Entity):
        pass

    class Negative[T](SemanticSpace[T]):
        pass

    class Either[A, B](Conjunction):
        one: A
        other: B

    class Span(Embedded):
        length: int

    class Deed(Document):
        _meta = Document.Meta(create_directly=False)
        done_by: ViaEdge[Person, Certainty] | MatchesCriteria[Person]

    class Plain(Document):
        _meta = Document.Meta(create_directly=False)
        about: Person
        span: Span | None = None

    class Factoid(Document):
        statements: list[Plain | Negative[Either[Plain, Deed]]]

    class Summary(Document):
        of: list[Plain]

    class Review(Document):
        """Cites a document that holds one: that document is not part of this one"""

        evidence: list[Cites[Factoid]]

    initialise()

    assert holders.can_hold(Deed) is True
    assert holders.can_hold(Factoid) is True
    assert holders.can_hold(Plain) is False and holders.can_hold(Summary) is False
    assert holders.can_hold(Review) is False


def test_a_class_declared_below_it_is_a_description_too():
    MatchesCriteria = criteria_class()

    class Person(Entity):
        pass

    class Guessed[T](MatchesCriteria[T]):
        by: str | None = None

    class Activity(Document):
        carried_out_by: list[Person | Guessed[Person]]

    initialise()

    assert holders.description_labels() == ["Guessed", "MatchesCriteria"]
    assert holders.can_hold(Activity) is True
    made = Activity.Create(
        label="A",
        carried_out_by=[
            {"type": "Guessed", "by": "me", "criteria": {"type": "Person"}}
        ],
    )._to_db_model()
    assert made.carried_out_by[0].depends_on == ["Person"]


def test_with_no_description_among_the_models_nothing_can_hold_one():
    class Person(Entity):
        pass

    class Activity(Document):
        carried_out_by: list[Person]

    initialise()

    assert holders.can_hold(Activity) is False
    assert holders.description_labels() == []
    assert holders.pending_work_of(Activity) == []


def test_what_was_worked_out_of_the_models_is_forgotten_with_them():
    MatchesCriteria, Person, Group, Office, HoldsOffice, Activity = models()
    assert holders.can_hold(Activity) is True
    from pangloss_models import ModelRegistry

    ModelRegistry._reset()
    assert holders._holds == {}


def test_a_description_can_stand_with_an_edge_model():
    MatchesCriteria = criteria_class()

    class Certainty(EdgeModel):
        percent: int

    class Person(Entity):
        pass

    class Activity(Document):
        carried_out_by: list[ViaEdge[Person | MatchesCriteria[Person], Certainty]]

    initialise()

    made = Activity.Create(
        label="A",
        carried_out_by=[
            {
                "type": "MatchesCriteria",
                "criteria": {"type": "Person"},
                "edge_properties": {"percent": 60},
            }
        ],
    )._to_db_model()
    (description,) = made.carried_out_by
    assert description.edge_properties.percent == 60
    assert description.criteria_hash and classes_stood_for(description, "T") == [Person]


# --- the same one in several places of a document (`same_one`) ----------------------------------------------------------

MARK = "01a1c564-7def-70f0-bd21-410a35c82ab4"
OTHER_MARK = "01a1c564-7def-70f0-bd21-410a35c82ab5"


def placed_models():
    """A factoid of statements: who carried a letter, who was paid (through a role); who signed it (an official, a
    narrower class of person) and which group ordered it"""
    MatchesCriteria = criteria_class()

    class Person(Entity):
        pass

    class Official(Person):
        pass

    class Group(Entity):
        pass

    class InRole[T](ReifiedRelation[T]):
        role: str | None = None

    class HoldsOffice(Document):
        holder: Person
        office: Office
        employer: Person

    class Office(Entity):
        pass

    class Carrying(Document):
        _meta = Document.Meta(create_directly=False)
        carried_out_by: list[Person | MatchesCriteria[Person]]

    class Payment(Document):
        _meta = Document.Meta(create_directly=False)
        paid_to: list[InRole[Person | MatchesCriteria[Person]]]

    class Factoid(Document):
        statements: list[Carrying | Payment]
        signed_by: list[Official | MatchesCriteria[Official]]
        ordered_by: list[Group | MatchesCriteria[Group]]

    initialise()
    return MatchesCriteria, Factoid


def place(mark=MARK, criteria=None, **more):
    """A place of a description with a mark: with criteria (a holder) or none (a bare place)"""
    return {
        "type": "MatchesCriteria",
        "same_one": mark,
        **({"criteria": criteria} if criteria is not None else {}),
        **more,
    }


def factoid(Factoid, carried=(), paid=(), signed=(), ordered=()):
    return Factoid.Create(
        label="F",
        statements=[
            {"type": "Carrying", "label": "carried", "carried_out_by": list(carried)},
            {
                "type": "Payment",
                "label": "paid",
                "paid_to": [{"type": "InRole", "target": [p]} for p in paid],
            },
        ],
        signed_by=list(signed),
        ordered_by=list(ordered),
    )


def checked_before_create(made):
    """The checks a write runs before it writes (`@before_create`), with no database"""
    import asyncio

    from pangloss_models.write_checks import check_before_create

    db = made._to_db_model()
    asyncio.run(check_before_create(db))
    return db


def test_a_place_with_a_mark_needs_no_criteria_of_its_own():
    MatchesCriteria, Factoid = placed_models()

    written = checked_before_create(
        factoid(
            Factoid,
            carried=[place(criteria=SECRETARY, wording="N. N.")],
            paid=[place(wording="the same")],
        )
    )
    holder = written.statements[0].carried_out_by[0]
    bare = written.statements[1].paid_to[0].target[0]
    assert str(holder.same_one) == str(bare.same_one) == MARK
    assert holder.criteria_hash and holder.depends_on == ["Person", "HoldsOffice"]
    # (nothing of criteria on the place that has none: it takes its holder's result)
    assert bare.criteria is None and bare.wording == "the same"
    assert bare.criteria_hash is None and bare.reach is None and bare.shape is None
    assert bare.names == [] and bare.depends_on == [] and bare.anchors == []


def test_places_of_one_mark_may_be_in_any_field_at_any_depth_and_hold_the_same_criteria():
    MatchesCriteria, Factoid = placed_models()

    # (one holder, places at another depth and in another field of the head)
    checked_before_create(
        factoid(Factoid, carried=[place()], paid=[place(criteria=SECRETARY), place()])
    )
    # (two holders of equal criteria, written differently)
    reordered = {"where": SECRETARY["where"], "type": "Person"}
    checked_before_create(
        factoid(
            Factoid,
            carried=[place(criteria=SECRETARY)],
            paid=[place(criteria=reordered), place()],
        )
    )
    # (a mark on a lone holder; and two marks in one document, each with its holder)
    checked_before_create(
        factoid(
            Factoid,
            carried=[place(criteria=SECRETARY), place(OTHER_MARK, {"type": "Person"})],
            paid=[place(OTHER_MARK)],
        )
    )


def test_a_mark_that_no_place_holds_criteria_for_is_refused_at_the_place():
    from pangloss_models import PanglossWriteRefused

    MatchesCriteria, Factoid = placed_models()

    with pytest.raises(
        PanglossWriteRefused, match=f"^No place of this document with the mark {MARK}"
    ) as refused:
        checked_before_create(
            factoid(Factoid, carried=[place(OTHER_MARK, SECRETARY)], paid=[place()])
        )
    assert refused.value.path == (
        "statements",
        1,
        "paid_to",
        0,
        "target",
        0,
        "same_one",
    )


def test_places_of_one_mark_that_hold_other_criteria_are_refused():
    from pangloss_models import PanglossWriteRefused

    MatchesCriteria, Factoid = placed_models()

    with pytest.raises(
        PanglossWriteRefused, match=f"^The places with the mark {MARK} hold different"
    ) as refused:
        checked_before_create(
            factoid(
                Factoid,
                carried=[place(criteria=SECRETARY)],
                paid=[place(criteria={"type": "Person"})],
            )
        )
    assert refused.value.path == ("statements", 0, "carried_out_by", 0, "criteria")


def test_a_place_whose_field_does_not_take_what_the_criteria_are_of_is_refused():
    from pangloss_models import PanglossWriteRefused

    MatchesCriteria, Factoid = placed_models()

    # (criteria of a group, and a place that takes a person)
    with pytest.raises(
        PanglossWriteRefused,
        match=rf"^The criteria of the mark {MARK} are of Group, which is not taken here \(Official, Person\)$",
    ) as refused:
        checked_before_create(
            factoid(
                Factoid, carried=[place()], ordered=[place(criteria={"type": "Group"})]
            )
        )
    assert refused.value.path == ("statements", 0, "carried_out_by", 0, "same_one")
    # (criteria of a person, and a place that takes an official only: narrower)
    with pytest.raises(
        PanglossWriteRefused,
        match=rf"^The criteria of the mark {MARK} are of Person, which is not taken here \(Official\)$",
    ) as refused:
        checked_before_create(
            factoid(Factoid, carried=[place(criteria=SECRETARY)], signed=[place()])
        )
    assert refused.value.path == ("signed_by", 0, "same_one")
    # (the other way, criteria of an official in a place of a person, is a person all the same)
    checked_before_create(
        factoid(
            Factoid, carried=[place()], signed=[place(criteria={"type": "Official"})]
        )
    )


def test_a_place_with_no_criteria_and_no_mark_is_refused_as_before():
    MatchesCriteria, Factoid = placed_models()

    with pytest.raises(ValidationError, match="a description needs the criteria"):
        factoid(
            Factoid, carried=[{"type": "MatchesCriteria", "wording": "x"}]
        )._to_db_model()
