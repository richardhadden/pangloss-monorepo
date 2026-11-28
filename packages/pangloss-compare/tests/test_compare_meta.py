"""Which statements are compared, and by which fields they tell of one event (`_compare_meta`,
implementation_docs/spaces-and-comparison-plan.md, step 6.1). No database."""

import importlib
from typing import Annotated, no_type_check

import pytest
from pangloss_compare import CompareMeta
from pangloss_compare.meta import (
    common_class,
    compare_meta,
    compared_classes,
    identifying_fields,
    orientation_of,
    related,
    space_compared,
)
from pangloss_models import (
    Conjunction,
    Document,
    EdgeModel,
    Entity,
    FieldSubclassing,
    PanglossMetaError,
    ReifiedRelation,
    RelationConfig,
    SemanticSpace,
    Trait,
    ViaEdge,
    initialise,
)


@no_type_check
def people():
    class Person(Entity):
        pass

    class Place(Entity):
        pass

    return Person, Place


# ---------------------------------------------------------------------------
# What is compared, and inheritance
# ---------------------------------------------------------------------------


@no_type_check
def test_a_class_with_no_setting_or_no_identifying_fields_is_not_compared():
    Person, _ = people()

    class Birth(Document):
        person: Person
        _compare_meta = CompareMeta(identifying=["person"], once_per="person")

    class Note(Document):
        about: Person

    class Remark(Document):
        about: Person
        _compare_meta = CompareMeta()

    initialise()
    assert compared_classes() == {
        "Birth": CompareMeta(identifying=["person"], once_per="person")
    }
    assert compare_meta(Note) is None
    assert compare_meta("Remark") is None
    assert compare_meta(Person) is None


@no_type_check
def test_a_subclass_has_its_parent_s_setting_and_its_own_replaces_it():
    Person, Place = people()

    class Event(Document):
        by: Person
        at: Place | None = None
        _compare_meta = CompareMeta(identifying=["by"])

    class Meeting(Event):
        pass

    class Visit(Event):
        _compare_meta = CompareMeta(identifying=["by", "at"], recurs=True)

    initialise()
    assert compare_meta(Meeting) == CompareMeta(identifying=["by"])
    assert compare_meta(Visit) == CompareMeta(identifying=["by", "at"], recurs=True)
    assert set(compared_classes()) == {"Event", "Meeting", "Visit"}


@no_type_check
def test_a_trait_s_setting_counts_for_the_documents_that_have_it():
    Person, _ = people()

    class Witnessed(Trait):
        _compare_meta = CompareMeta(identifying=["witness"])

    class Signing(Document, Witnessed):
        witness: Person

    initialise()
    assert compared_classes() == {"Signing": CompareMeta(identifying=["witness"])}
    assert identifying_fields(Signing) == {"witness": ["witness"]}


@no_type_check
def test_an_abstract_class_is_not_among_the_compared_classes_but_its_subclasses_are():
    Person, _ = people()

    class Statement(Document):
        _meta = Document.Meta(abstract=True)
        # (an abstract class need not have the fields: only the classes a node can be of are checked)
        _compare_meta = CompareMeta(identifying=["person"])

    class Birth(Statement):
        person: Person

    initialise()
    assert set(compared_classes()) == {"Birth"}


@no_type_check
def test_compared_false_leaves_a_class_and_its_subclasses_out_unless_they_set_their_own():
    Person, _ = people()

    class Event(Document):
        by: Person
        _compare_meta = CompareMeta(identifying=["by"])

    class Rumour(Event):
        _compare_meta = CompareMeta(identifying=["by"], compared=False)

    class Gossip(Rumour):
        pass

    class Report(Rumour):
        _compare_meta = CompareMeta(identifying=["by"])

    initialise()
    assert compare_meta(Rumour) is None
    assert compare_meta(Gossip) is None
    assert set(compared_classes()) == {"Event", "Report"}


@no_type_check
def test_a_class_left_out_is_not_checked():
    Person, _ = people()

    class Event(Document):
        _compare_meta = CompareMeta(identifying=["nothing"], compared=False)

    initialise()
    assert compared_classes() == {}


# ---------------------------------------------------------------------------
# Identifying fields: through wrappers, and narrowed
# ---------------------------------------------------------------------------


@no_type_check
def test_an_identifying_field_may_be_a_list_or_optional():
    Person, Place = people()

    class Meeting(Document):
        people: list[Person]
        at: Place | None = None
        _compare_meta = CompareMeta(identifying=["people", "at"])

    initialise()
    assert identifying_fields(Meeting) == {"people": ["people"], "at": ["at"]}


@no_type_check
def test_an_identifying_field_may_reach_its_entity_behind_a_reified_relation():
    Person, Place = people()

    class InRole[T](ReifiedRelation[T]):
        role: str
        # (a relation of the wrapper's own: not on the way to what it holds)
        at: Place | None = None

    class Activity(Document):
        participants: list[InRole[Person]]
        _compare_meta = CompareMeta(identifying=["participants"])

    initialise()
    assert identifying_fields(Activity) == {"participants": ["participants"]}


@no_type_check
def test_an_identifying_field_may_reach_its_entity_behind_an_identification_s_alternatives():
    import pangloss_library.models

    library = importlib.reload(pangloss_library.models)
    Person, _ = people()

    class Transfer(Document):
        given_to: library.Identification[library.WeightedAlternative[Person]]
        _compare_meta = CompareMeta(identifying=["given_to"])

    initialise()
    assert identifying_fields(Transfer) == {"given_to": ["given_to"]}


@no_type_check
def test_an_identifying_field_may_reach_its_entity_through_an_edge_model():
    Person, _ = people()

    class Certainty(EdgeModel):
        certainty: int

    class Pair[T](ReifiedRelation[T]):
        others: list[ViaEdge[T, Certainty]]

    class Meeting(Document):
        met: Pair[Person]
        _compare_meta = CompareMeta(identifying=["met"])

    initialise()
    assert identifying_fields(Meeting) == {"met": ["met"]}


@no_type_check
def test_a_narrowed_field_counts_as_the_field_it_narrows():
    Person, _ = people()

    class Thing(Entity):
        pass

    class Picture(Thing):
        pass

    class Making(Document):
        made_by: Person
        made: Thing
        _compare_meta = CompareMeta(identifying=["made_by", "made"], once_per="made")

    class MakingOfPicture(Making):
        picture_made: Annotated[
            Picture,
            RelationConfig(
                subclasses_parent_fields=[
                    FieldSubclassing("made", field_on_model=Making)
                ]
            ),
        ]

    initialise()
    # (the field definitions of the subclass hold `picture_made` in the place of `made`)
    assert "made" not in MakingOfPicture._meta.fields
    assert identifying_fields(MakingOfPicture) == {
        "made_by": ["made_by"],
        "made": ["picture_made"],
    }
    assert identifying_fields(Making) == {"made_by": ["made_by"], "made": ["made"]}
    assert compare_meta(MakingOfPicture) == compare_meta(Making)


@no_type_check
def test_a_field_narrowed_twice_counts_as_the_first():
    Person, _ = people()

    class Event(Document):
        involves: list[Person]
        _compare_meta = CompareMeta(identifying=["involves"])

    class Activity(Event):
        carried_out_by: Annotated[
            list[Person],
            RelationConfig(
                subclasses_parent_fields=[
                    FieldSubclassing("involves", field_on_model=Event)
                ]
            ),
        ]

    class Speech(Activity):
        spoken_by: Annotated[
            Person,
            RelationConfig(
                subclasses_parent_fields=[
                    FieldSubclassing("carried_out_by", field_on_model=Activity)
                ]
            ),
        ]

    initialise()
    assert identifying_fields(Speech) == {"involves": ["spoken_by"]}


# ---------------------------------------------------------------------------
# Spaces
# ---------------------------------------------------------------------------


@no_type_check
def test_a_space_is_compared_and_answered_after_unless_it_says_otherwise():
    Person, _ = people()

    class Negative[T](SemanticSpace[T]):
        _meta = SemanticSpace.Meta(logical="not")

    class Fiction[T](SemanticSpace[T]):
        _compare_meta = CompareMeta(compared=False)

    class Expected[T](SemanticSpace[T]):
        _meta = SemanticSpace.Meta(fit="prescribes")
        _compare_meta = CompareMeta(orientation="before")

    class Demanded[T](Expected[T]):
        pass

    class Birth(Document):
        person: Person
        _compare_meta = CompareMeta(identifying=["person"])

    class Factoid(Document):
        statements: list[
            Birth | Negative[Birth] | Fiction[Birth] | Expected[Birth] | Demanded[Birth]
        ]

    initialise()
    assert space_compared(Negative) and orientation_of(Negative) == "after"
    assert not space_compared(Fiction)
    # (a use of a generic space has its setting)
    assert not space_compared(Fiction[Birth])
    assert space_compared("Expected") and orientation_of(Expected) == "before"
    assert orientation_of(Demanded) == "before"
    assert orientation_of(Demanded[Birth]) == "before"
    with pytest.raises(ValueError, match="Birth is not a semantic space"):
        space_compared(Birth)


# ---------------------------------------------------------------------------
# Related classes
# ---------------------------------------------------------------------------


@no_type_check
def test_two_classes_are_related_when_the_same_or_one_is_above_the_other():
    Person, _ = people()

    class Making(Document):
        made_by: Person
        _compare_meta = CompareMeta(identifying=["made_by"])

    class MakingOfPicture(Making):
        pass

    class MakingOfStatue(Making):
        pass

    class Birth(Document):
        person: Person
        _compare_meta = CompareMeta(identifying=["person"])

    initialise()
    assert related(Making, Making) and common_class(Making, Making) is Making
    assert related(MakingOfPicture, Making)
    assert common_class(MakingOfPicture, Making) is Making
    assert common_class("Making", "MakingOfPicture") is Making
    # (two below one class are not related: neither is the other)
    assert not related(MakingOfPicture, MakingOfStatue)
    assert common_class(MakingOfPicture, MakingOfStatue) is None
    assert not related(Birth, Making) and common_class(Birth, Making) is None


# ---------------------------------------------------------------------------
# Refusals
# ---------------------------------------------------------------------------


@no_type_check
def test_the_setting_on_an_entity_is_refused():
    class Person(Entity):
        _compare_meta = CompareMeta(identifying=["label"])

    with pytest.raises(
        PanglossMetaError,
        match=r"^Person: CompareMeta is for a class of documents \(or a trait documents have\) or a semantic space, "
        r"and Person is an entity$",
    ):
        initialise()


@no_type_check
def test_the_setting_on_an_edge_model_is_refused():
    class Certainty(EdgeModel):
        certainty: int
        _compare_meta = CompareMeta()

    with pytest.raises(PanglossMetaError, match="^Certainty: .* is an edge model$"):
        initialise()


@no_type_check
def test_the_setting_on_a_reified_relation_is_refused():
    class InRole[T](ReifiedRelation[T]):
        role: str
        _compare_meta = CompareMeta()

    with pytest.raises(PanglossMetaError, match="^InRole: .* is a reified relation$"):
        initialise()


@no_type_check
def test_the_setting_on_a_conjunction_is_refused():
    class Causes[A, B](Conjunction):
        cause: A
        result: B
        _compare_meta = CompareMeta()

    with pytest.raises(PanglossMetaError, match="^Causes: .* is a conjunction$"):
        initialise()


@no_type_check
def test_a_trait_s_setting_on_an_entity_is_refused_by_the_trait():
    class Named(Trait):
        _compare_meta = CompareMeta(identifying=["x"])

    class Person(Entity, Named):
        pass

    with pytest.raises(
        PanglossMetaError,
        match=r"^Named: CompareMeta is for documents, and Person, which has the trait, is an entity$",
    ):
        initialise()


@no_type_check
@pytest.mark.parametrize(
    "setting, named",
    [
        (CompareMeta(identifying=["person"]), "`identifying`"),
        (CompareMeta(once_per="person"), "`once_per`"),
        (CompareMeta(recurs=True, compared=False), "`recurs`"),
    ],
)
def test_a_space_may_set_only_compared_and_orientation(setting, named):
    class Negative[T](SemanticSpace[T]):
        _compare_meta = setting

    with pytest.raises(
        PanglossMetaError,
        match=rf"^Negative: on a semantic space CompareMeta takes only `compared` and `orientation`, and this sets "
        rf"{named}: what tells of an event is said by the classes of the statements inside it$",
    ):
        initialise()


@no_type_check
def test_orientation_on_a_document_is_refused():
    Person, _ = people()

    class Order(Document):
        by: Person
        _compare_meta = CompareMeta(identifying=["by"], orientation="before")

    with pytest.raises(
        PanglossMetaError,
        match=r"^Order: CompareMeta\(orientation=\.\.\.\) is only for a semantic space .*, and this is a class of "
        r"documents$",
    ):
        initialise()


@no_type_check
def test_an_orientation_that_is_neither_after_nor_before_is_refused():
    class Ordered[T](SemanticSpace[T]):
        _compare_meta = CompareMeta(orientation="later")

    with pytest.raises(
        PanglossMetaError,
        match=r"^Ordered: CompareMeta\(orientation='later'\) is 'after' or 'before'$",
    ):
        initialise()


@no_type_check
def test_identifying_given_as_a_string_is_refused():
    Person, _ = people()

    class Birth(Document):
        person: Person
        _compare_meta = CompareMeta(identifying="person")

    with pytest.raises(
        PanglossMetaError,
        match=r"^Birth: CompareMeta\(identifying=\.\.\.\) is a list of the names of fields \(\['person'\]\), not "
        r"'person'$",
    ):
        initialise()


@no_type_check
def test_identifying_with_something_not_a_name_in_it_is_refused():
    Person, _ = people()

    class Birth(Document):
        person: Person
        _compare_meta = CompareMeta(identifying=[Person])

    with pytest.raises(
        PanglossMetaError, match=r"^Birth: .* has something else in it$"
    ):
        initialise()


@no_type_check
def test_a_field_the_class_has_not_is_refused_with_the_nearest_name():
    Person, _ = people()

    class Birth(Document):
        person: Person
        _compare_meta = CompareMeta(identifying=["persn"])

    with pytest.raises(
        PanglossMetaError,
        match=r"^Birth: CompareMeta\(identifying=\.\.\.\) names 'persn', which is not a field of Birth\. Did you "
        r"mean 'person'\?$",
    ):
        initialise()


@no_type_check
def test_a_field_a_subclass_has_not_is_refused_by_the_class_that_says_it():
    Person, _ = people()

    class Witnessed(Trait):
        _compare_meta = CompareMeta(identifying=["witness"])

    class Signing(Document, Witnessed):
        witness: Person

    class Sealing(Document, Witnessed):
        sealed_by: Person

    with pytest.raises(
        PanglossMetaError,
        match=r"^Witnessed: CompareMeta\(identifying=\.\.\.\) names 'witness', which is not a field of Sealing\.$",
    ):
        initialise()


@no_type_check
def test_a_field_of_text_is_refused():
    class Birth(Document):
        person: str
        _compare_meta = CompareMeta(identifying=["person"])

    with pytest.raises(
        PanglossMetaError,
        match=r"^Birth: CompareMeta\(identifying=\.\.\.\) names 'person', which in Birth is not a relation\. An "
        r"identifying field is a relation that reaches an entity \(`Person`, `list\[Person\]`, `Person \| None`, "
        r"or through a wrapper: `InRole\[Person\]`, `Identification\[WeightedAlternative\[Person\]\]`\)$",
    ):
        initialise()


@no_type_check
def test_a_field_that_reaches_only_documents_is_refused():
    class Negative[T](SemanticSpace[T]):
        _meta = SemanticSpace.Meta(logical="not")

    class Note(Document):
        text: str

    class Factoid(Document):
        notes: list[Note | Negative[Note]]
        _compare_meta = CompareMeta(identifying=["notes"])

    with pytest.raises(
        PanglossMetaError,
        match=r"^Factoid: CompareMeta\(identifying=\.\.\.\) names 'notes', which in Factoid is a relation that "
        r"reaches no entity\. ",
    ):
        initialise()


@no_type_check
def test_a_narrowing_field_that_reaches_no_entity_is_refused_by_its_name():
    Person, _ = people()

    class Note(Document):
        text: str

    class Statement(Document):
        about: list[Person | Note]
        _compare_meta = CompareMeta(identifying=["about"])

    class Comment(Statement):
        about_note: Annotated[
            list[Note],
            RelationConfig(
                subclasses_parent_fields=[
                    FieldSubclassing("about", field_on_model=Statement)
                ]
            ),
        ]

    with pytest.raises(
        PanglossMetaError,
        match=r"^Statement: CompareMeta\(identifying=\.\.\.\) names 'about', which in Comment \(as 'about_note', "
        r"which narrows it\) is a relation that reaches no entity\. ",
    ):
        initialise()


@no_type_check
def test_once_per_that_is_not_identifying_is_refused():
    Person, Place = people()

    class Birth(Document):
        person: Person
        place: Place
        _compare_meta = CompareMeta(identifying=["person"], once_per="place")

    with pytest.raises(
        PanglossMetaError,
        match=r"^Birth: CompareMeta\(once_per='place'\) is not one of identifying \(person\)\.$",
    ):
        initialise()


@no_type_check
def test_once_per_misspelt_is_refused_with_the_nearest_name():
    Person, _ = people()

    class Birth(Document):
        person: Person
        _compare_meta = CompareMeta(identifying=["person"], once_per="persons")

    with pytest.raises(PanglossMetaError, match=r"Did you mean 'person'\?$"):
        initialise()


@no_type_check
def test_once_per_and_recurs_together_are_refused():
    Person, _ = people()

    class Birth(Document):
        person: Person
        _compare_meta = CompareMeta(
            identifying=["person"], once_per="person", recurs=True
        )

    with pytest.raises(
        PanglossMetaError,
        match=r"^Birth: CompareMeta\(once_per='person', recurs=True\) says both that there is one for each "
        r"'person' and that it happens again and again: say one$",
    ):
        initialise()


# ---------------------------------------------------------------------------
# The models comparison is measured on
# ---------------------------------------------------------------------------


@no_type_check
def test_the_compared_test_models():
    from pangloss_testing.similar_models import declare

    m = declare(compared=True)
    assert compared_classes() == {
        "Activity": CompareMeta(identifying=["carried_out_by", "participants"]),
        "Attendance": CompareMeta(identifying=["attended_by", "assembly_of"]),
        "Birth": CompareMeta(identifying=["person"], once_per="person"),
        "Making": CompareMeta(identifying=["made_by", "made"], once_per="made"),
        "MakingOfPicture": CompareMeta(
            identifying=["made_by", "made"], once_per="made"
        ),
        "Order": CompareMeta(identifying=["ordered_by", "ordered_to"]),
        "Rule": CompareMeta(identifying=["ruled_by", "binds"]),
        "Transfer": CompareMeta(identifying=["given_by", "given_to"], recurs=True),
    }
    assert identifying_fields(m.MakingOfPicture) == {
        "made_by": ["made_by"],
        "made": ["picture_made"],
    }
    # (`participants` reaches its people behind `InRole`, `given_to` also behind an identification's alternatives)
    assert identifying_fields(m.Activity) == {
        "carried_out_by": ["carried_out_by"],
        "participants": ["participants"],
    }
    assert related(m.MakingOfPicture, m.Making)
    assert common_class(m.MakingOfPicture, m.Making) is m.Making
    assert not related(m.Birth, m.Attendance)
    for space in ("Negative", "Hypothetical", "Reported", "Ordered", "Forbidden"):
        assert space_compared(space) and orientation_of(space) == "after"


@no_type_check
def test_without_compared_the_test_models_have_no_setting():
    from pangloss_testing.similar_models import declare

    declare()
    assert compared_classes() == {}


# ---------------------------------------------------------------------------
# What the interface is told
# ---------------------------------------------------------------------------


@no_type_check
def test_the_interface_is_told_which_classes_are_compared():
    """`hooks.definition_extras`, registered when the package is imported: `compared` of each compared class (its
    subclasses by inheritance), nothing of the rest"""
    from pangloss_compare.meta import definition_extras
    from pangloss_models import hooks
    from pangloss_testing.similar_models import declare

    assert definition_extras in hooks.definition_extras
    m = declare(compared=True)
    for name in ("Birth", "Making", "MakingOfPicture", "Order", "Transfer"):
        assert definition_extras(getattr(m, name)) == {"compared": True}, name
    for name in (
        "Factoid",
        "Person",
        "Statement",
        "MemberOf",
        "StatementJudgement",
        "Negative",
        "Ordered",
    ):
        assert definition_extras(getattr(m, name)) == {}, name
