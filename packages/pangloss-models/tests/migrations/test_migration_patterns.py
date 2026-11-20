"""A stored search pattern brought through each kind of change of a migration (`migrations.patterns`): by the snapshot
of the models before the change, with the snapshots and changes of real declared models"""

import copy
import uuid
from enum import Enum

import pytest
from migration_support import changes, snapshot_of
from pangloss_models import (
    Document,
    EdgeModel,
    Entity,
    ReifiedRelation,
    SemanticSpace,
    ViaEdge,
)
from pangloss_models.migrations import PossibleRename, apply_change
from pangloss_models.migrations import changes as c
from pangloss_models.migrations.patterns import Broken, may_alter, upgrade
from pangloss_models.search import Match, check_match, resolve_search_type

OFFICE = str(uuid.uuid4())
MAXIMILIAN = str(uuid.uuid4())


class Gender(Enum):
    MALE = "male"
    FEMALE = "female"
    OTHER = "other"


# The models, as a template: each test changes a part (`court(age="years")`) to make the models after a change
SOURCE = """
class {Certainty}(EdgeModel):
    {certainty}: int


class {Person}(Entity):
    gender: Gender | None = None
    {age}: int | None = None
    {extra}


class Saint({Person}):
    feast: {feast} = None


class Office(Entity):
    pass


class {Maybe}[T](ReifiedRelation[T]):
    {likelihood}: int = 1


class {Hearsay}[T](SemanticSpace[T]):
    pass


class HoldsOffice(Document):
    {holder}: {holder_type}
    office: list[ViaEdge[Office, {Certainty}]]
    year: {year} = None
    {employer}


class Factoid(Document):
    statements: list[HoldsOffice | {Hearsay}[HoldsOffice]]
"""

PARTS = {
    "Certainty": "Certainty",
    "certainty": "certainty",
    "Person": "Person",
    "age": "age",
    "extra": "",
    "feast": "str | None",
    "Maybe": "Maybe",
    "likelihood": "likelihood",
    "Hearsay": "Hearsay",
    "holder": "holder",
    "holder_type": "list[{Person} | {Maybe}[{Person}]]",
    "year": "int | None",
    "employer": "employer: {Person} | None = None",
}


def court(**changed: str):
    """A function that declares the models, with the parts given changed"""
    parts = {**PARTS, **changed}
    source = SOURCE.format(**{k: v.format(**parts) for k, v in parts.items()})

    def declare() -> None:
        namespace = {
            "__name__": __name__,
            "Document": Document,
            "EdgeModel": EdgeModel,
            "Entity": Entity,
            "Gender": Gender,
            "ReifiedRelation": ReifiedRelation,
            "SemanticSpace": SemanticSpace,
            "ViaEdge": ViaEdge,
        }
        exec(source, namespace)

    return declare


def secretary() -> dict:
    """Someone who held an office (through a `Maybe` or not, by an edge of certainty) under an employer older than
    30, in a year that is 1495 or not before 1490"""
    return {
        "type": "Person",
        "where": {
            "gender": {"eq": "male"},
            "$incoming": [
                {
                    "type": "HoldsOffice",
                    "field": "holder",
                    "through": ["Maybe"],
                    "where": {
                        "office": {
                            "is": OFFICE,
                            "edge": {
                                "type": "Certainty",
                                "where": {"certainty": {"gte": 50}},
                            },
                        },
                        "employer": {"type": "Person", "where": {"age": {"gt": 30}}},
                        "$any_of": [
                            {"year": {"eq": 1495}},
                            {"$not": {"year": {"lt": 1490}}},
                        ],
                    },
                }
            ],
        },
    }


def factoid() -> dict:
    """A factoid with a statement that is hearsay, of a year after 1400; somewhere in it, a saint holds an office
    through a `Maybe` of some likelihood; and it mentions Maximilian"""
    return {
        "type": "Factoid",
        "where": {
            "statements": {
                "through": ["Hearsay"],
                "type": "HoldsOffice",
                "where": {"year": {"gt": 1400}, "$spaces": ["Hearsay"]},
            },
            "$somewhere": [
                {
                    "type": "HoldsOffice",
                    "where": {
                        "holder": {
                            "through": [
                                {"type": "Maybe", "where": {"likelihood": {"gte": 2}}}
                            ],
                            "type": "Saint",
                            "where": {"feast": {"eq": "12"}, "age": {"lt": 90}},
                        }
                    },
                }
            ],
            "$mentions": {"is": MAXIMILIAN},
        },
    }


def holder_of(pattern: dict) -> dict:
    return pattern["where"]["$somewhere"][0]["where"]["holder"]


def incoming_of(pattern: dict) -> dict:
    return pattern["where"]["$incoming"][0]


def fits(pattern: dict) -> None:
    """The pattern is one a search of the models declared last takes"""
    model = resolve_search_type(pattern["type"])
    check_match(model, Match(type=pattern["type"], where=pattern["where"]))


def only(result, kind) -> list:
    found = [change for change in result.changes if isinstance(change, kind)]
    assert found, result.changes
    return found


def walk(old: dict, result, pattern: dict) -> tuple[dict, list[Broken]]:
    """The pattern brought through each change found, in order, by the snapshot before each"""
    state, broken = old, []
    for change in result.changes:
        upgraded = upgrade(pattern, change, state)
        pattern = upgraded.pattern
        if upgraded.broken is not None:
            broken.append(upgraded.broken)
        state = apply_change(state, change)
    return pattern, broken


def renamed_field(scope: str, old: str, new: str) -> PossibleRename:
    return PossibleRename(what="field", scope=scope, old=old, new=new)


def test_both_patterns_fit_the_models_as_they_are():
    snapshot_of(court())
    fits(secretary())
    fits(factoid())


def test_a_change_that_cannot_alter_a_pattern_leaves_it_equal_and_unchanged():
    old = snapshot_of(court())
    result = changes(court(), court(extra="nickname: str | None = None"))
    assert {change.kind for change in result.changes} == {"AddField"}
    pattern = secretary()
    for added in result.changes:
        assert not may_alter(added)
        upgraded = upgrade(pattern, added, old)
        assert upgraded.changed is False and upgraded.broken is None
        assert upgraded.pattern == pattern and upgraded.pattern is not pattern


@pytest.mark.parametrize(
    "change",
    [
        c.RunPython(function="x.y:z"),
        c.RunCypher(query="MATCH (n) RETURN n"),
        c.StateOnly(changes=(c.RenameField(model="Person", old="age", new="years"),)),
        c.RenameEnumMember(enum="Gender", old="MALE", new="MAN"),
        c.AddIndex(index={"kind": "label", "label": "Person", "properties": []}),
        c.AlterRelationTarget(model="HoldsOffice", name="holder", added=["entity:X"]),
        c.AlterCardinality(model="HoldsOffice", name="holder", many=False),
        c.AlterReverseName(model="HoldsOffice", name="holder", old="a", new="b"),
    ],
    ids=lambda change: change.kind,
)
def test_by_hand_and_what_names_nothing_of_a_pattern_change_nothing(change):
    old = snapshot_of(court())
    assert not may_alter(change)
    pattern = secretary()
    upgraded = upgrade(pattern, change, old)
    assert (upgraded.pattern, upgraded.changed, upgraded.broken) == (
        pattern,
        False,
        None,
    )


def test_the_pattern_given_is_never_changed():
    old = snapshot_of(court())
    pattern = secretary()
    kept = copy.deepcopy(pattern)
    upgraded = upgrade(pattern, c.RenameModel(old="Person", new="Human"), old)
    assert upgraded.changed and pattern == kept


# --- renames ------------------------------------------------------------------------------------------------------------


def test_a_renamed_class_is_renamed_wherever_a_pattern_names_it():
    old = snapshot_of(court())
    names = {
        "Person": "Human",
        "Maybe": "Perhaps",
        "Hearsay": "Rumour",
        "Certainty": "Confidence",
    }
    result = changes(
        court(),
        court(**names),
        confirmed=[
            PossibleRename(what="model", old=o, new=n) for o, n in names.items()
        ],
    )
    assert {(r.old, r.new) for r in only(result, c.RenameModel)} == set(names.items())

    person, broken = walk(old, result, secretary())
    assert broken == []
    assert person["type"] == "Human"
    assert incoming_of(person)["through"] == ["Perhaps"]
    assert incoming_of(person)["where"]["office"]["edge"]["type"] == "Confidence"
    assert incoming_of(person)["where"]["employer"]["type"] == "Human"

    found, broken = walk(old, result, factoid())
    assert broken == []
    assert found["where"]["statements"]["through"] == ["Rumour"]
    assert found["where"]["statements"]["where"]["$spaces"] == ["Rumour"]
    assert holder_of(found)["through"][0]["type"] == "Perhaps"
    # (the models declared now are those of the end: both fit them)
    fits(person)
    fits(found)


def test_a_renamed_field_is_renamed_in_its_class_and_those_below_it_and_nowhere_else():
    old = snapshot_of(court())
    result = changes(
        court(),
        court(age="years"),
        confirmed=[
            renamed_field("Person", "age", "years"),
            renamed_field("Saint", "age", "years"),
        ],
    )
    assert {r.model for r in only(result, c.RenameField)} == {"Person", "Saint"}
    pattern = secretary()
    # (an extension's key is its own, whatever it holds)
    pattern["where"]["$derived"] = {"type": "Person", "where": {"age": {"gt": 1}}}

    person, broken = walk(old, result, pattern)
    assert broken == []
    assert incoming_of(person)["where"]["employer"]["where"] == {"years": {"gt": 30}}
    assert person["where"]["$derived"] == {
        "type": "Person",
        "where": {"age": {"gt": 1}},
    }

    # a pattern of the class below, narrowed to inside a relation to the parent
    found, broken = walk(old, result, factoid())
    assert broken == []
    assert holder_of(found)["where"] == {"feast": {"eq": "12"}, "years": {"lt": 90}}
    fits(found)


def test_a_field_renamed_on_a_class_alone_is_renamed_in_the_patterns_of_those_below_it():
    old = snapshot_of(court())
    pattern = {"type": "Saint", "where": {"age": {"gt": 3}}}
    upgraded = upgrade(
        pattern, c.RenameField(model="Person", old="age", new="years"), old
    )
    assert upgraded.pattern == {"type": "Saint", "where": {"years": {"gt": 3}}}
    # (and not in those above it, nor of another class)
    office = {"type": "Office", "where": {"age": {"gt": 3}}}
    assert (
        upgrade(
            office, c.RenameField(model="Person", old="age", new="years"), old
        ).changed
        is False
    )


def test_a_renamed_relation_is_renamed_in_incoming_and_in_the_patterns_of_its_class():
    old = snapshot_of(court())
    result = changes(
        court(),
        court(holder="bearer"),
        confirmed=[renamed_field("HoldsOffice", "holder", "bearer")],
    )
    (rename,) = only(result, c.RenameField)
    person, broken = walk(old, result, secretary())
    assert broken == []
    assert incoming_of(person)["field"] == "bearer"
    found, _ = walk(old, result, factoid())
    assert set(found["where"]["$somewhere"][0]["where"]) == {"bearer"}
    fits(person)
    fits(found)
    # (twice is once: a pattern brought through the rename already is left as it is)
    again = upgrade(person, rename, old)
    assert again.changed is False and again.pattern == person


def test_a_renamed_value_of_a_wrapper_or_of_an_edge_is_renamed_in_through_and_edge():
    old = snapshot_of(court())
    result = changes(
        court(),
        court(likelihood="probability", certainty="confidence"),
        confirmed=[
            renamed_field("Maybe", "likelihood", "probability"),
            renamed_field("Certainty", "certainty", "confidence"),
        ],
    )
    person, broken = walk(old, result, secretary())
    assert broken == []
    assert incoming_of(person)["where"]["office"]["edge"]["where"] == {
        "confidence": {"gte": 50}
    }
    found, _ = walk(old, result, factoid())
    assert holder_of(found)["through"][0] == {
        "type": "Maybe",
        "where": {"probability": {"gte": 2}},
    }
    fits(person)
    fits(found)


# --- values -----------------------------------------------------------------------------------------------------------


def test_a_value_of_an_enum_that_changes_is_changed_where_it_is_compared():
    old = snapshot_of(court())
    change = c.AlterEnumMemberValue(enum="Gender", member="MALE", old="male", new="m")
    pattern = secretary()
    pattern["where"]["$all"] = [
        {"gender": {"in": ["male", "female"]}},
        {"gender": {"ne": "male"}},
    ]
    upgraded = upgrade(pattern, change, old)
    assert upgraded.changed and upgraded.broken is None
    where = upgraded.pattern["where"]
    assert where["gender"] == {"eq": "m"}
    assert where["$all"] == [
        {"gender": {"in": ["m", "female"]}},
        {"gender": {"ne": "m"}},
    ]


def test_a_value_compared_with_a_field_whose_type_changes_is_converted():
    old = snapshot_of(court())
    result = changes(court(), court(year="float | None"))
    (altered,) = only(result, c.AlterLiteralType)
    assert altered.model == "HoldsOffice"
    person, broken = walk(old, result, secretary())
    assert broken == []
    years = incoming_of(person)["where"]["$any_of"]
    assert years == [{"year": {"eq": 1495.0}}, {"$not": {"year": {"lt": 1490.0}}}]
    assert isinstance(years[0]["year"]["eq"], float)
    fits(person)


def test_a_value_that_cannot_be_converted_breaks_the_pattern_and_stays():
    old = snapshot_of(court())
    result = changes(court(), court(feast="int | None"))
    pattern = factoid()
    holder_of(pattern)["where"]["$all"] = [{"feast": {"in": ["12", "Michaelmas"]}}]

    found, broken = walk(old, result, pattern)
    (wrong,) = broken
    assert wrong.path == "$somewhere.holder.feast.in"
    assert wrong.reason.startswith("'Michaelmas' cannot be a value of Saint.feast now")
    # (what converts is converted; what does not is left, not dropped)
    assert holder_of(found)["where"] == {
        "feast": {"eq": 12},
        "age": {"lt": 90},
        "$all": [{"feast": {"in": [12, "Michaelmas"]}}],
    }


# --- wrappers -----------------------------------------------------------------------------------------------------------


def test_a_wrapper_that_becomes_another_is_renamed_in_through_of_the_field():
    old = snapshot_of(court())
    change = c.ChangeWrapper(
        model="HoldsOffice",
        name="holder",
        old_wrapper="Maybe",
        new_wrapper="Hearsay",
        wrapper_kind="reifiedRelation",
    )
    person = upgrade(secretary(), change, old)
    assert incoming_of(person.pattern)["through"] == ["Hearsay"]
    found = upgrade(factoid(), change, old)
    assert holder_of(found.pattern)["through"][0]["type"] == "Hearsay"
    # (of another field, it is not)
    other = c.ChangeWrapper(
        model="Factoid",
        name="other",
        old_wrapper="Hearsay",
        new_wrapper="Maybe",
        wrapper_kind="semanticSpace",
    )
    assert upgrade(factoid(), other, old).changed is False


# --- what breaks a pattern ----------------------------------------------------------------------------------------------


def test_a_removed_field_breaks_the_pattern_and_its_condition_stays():
    old = snapshot_of(court())
    result = changes(court(), court(employer=""))
    (removed,) = only(result, c.RemoveField)
    upgraded = upgrade(secretary(), removed, old)
    assert upgraded.broken == Broken(
        "$incoming.employer", "the field 'employer' of HoldsOffice was removed"
    )
    assert str(upgraded.broken) == (
        "$incoming.employer: the field 'employer' of HoldsOffice was removed"
    )
    assert upgraded.pattern == secretary() and upgraded.changed is False


def test_a_removed_relation_breaks_incoming_and_a_condition_inside_not():
    old = snapshot_of(court())
    change = c.RemoveField(model="HoldsOffice", name="holder", field_kind="relation")
    upgraded = upgrade(secretary(), change, old)
    assert upgraded.broken is not None and upgraded.broken.path == "$incoming"
    assert "'holder'" in upgraded.broken.reason
    # (inside `$not` too: never dropped)
    pattern = {"type": "HoldsOffice", "where": {"$not": {"holder": {"exists": True}}}}
    upgraded = upgrade(pattern, change, old)
    assert upgraded.broken == Broken(
        "holder", "the field 'holder' of HoldsOffice was removed"
    )
    assert upgraded.pattern == pattern


def test_a_deleted_class_breaks_a_pattern_that_names_it_anywhere():
    old = snapshot_of(court())
    saint = c.DeleteModel(model="Saint", model_kind="Entity")
    assert upgrade(factoid(), saint, old).broken == Broken(
        "$somewhere.holder", "the model Saint was deleted"
    )
    assert upgrade({"type": "Saint", "where": {}}, saint, old).broken == Broken(
        "type", "the model Saint was deleted"
    )
    space = c.DeleteModel(model="Hearsay", model_kind="SemanticSpace")
    assert upgrade(factoid(), space, old).broken == Broken(
        "statements.through", "the model Hearsay was deleted"
    )
    edge = c.DeleteModel(model="Certainty", model_kind="EdgeModel")
    assert upgrade(secretary(), edge, old).broken == Broken(
        "$incoming.office.edge", "the model Certainty was deleted"
    )


def test_a_removed_member_of_an_enum_breaks_a_pattern_that_compares_with_it():
    old = snapshot_of(court())
    change = c.RemoveEnumMember(enum="Gender", member="OTHER")
    pattern = {"type": "Person", "where": {"gender": {"in": ["male", "other"]}}}
    upgraded = upgrade(pattern, change, old)
    assert upgraded.broken == Broken("gender.in", "'other' (Gender.OTHER) was removed")
    assert upgraded.pattern == pattern
    assert upgrade(secretary(), change, old).broken is None


def test_a_relation_that_no_longer_passes_through_a_wrapper_breaks_through_it():
    old = snapshot_of(court())
    result = changes(court(), court(holder_type="list[{Person}]"))
    (narrowed,) = only(result, c.AlterRelationTarget)
    assert narrowed.removed and may_alter(narrowed)
    found, broken = walk(old, result, factoid())
    assert broken == [
        Broken(
            "$somewhere.holder.through",
            "HoldsOffice.holder no longer passes through Maybe",
        )
    ]
    assert holder_of(found) == holder_of(factoid())


def test_a_relation_that_no_longer_holds_a_class_breaks_the_patterns_of_it():
    old = snapshot_of(court())
    result = changes(court(), court(holder_type="list[Office]"))
    (narrowed,) = only(result, c.AlterRelationTarget)
    found, broken = walk(old, result, factoid())
    assert broken[0] == Broken(
        "$somewhere.holder", "HoldsOffice.holder no longer holds a Saint"
    )
    person, broken = walk(old, result, secretary())
    assert broken == [
        Broken("$incoming", "HoldsOffice.holder no longer refers to a Person")
    ]
    assert narrowed.model == "HoldsOffice"


# --- `via`: the places of the way of a relation, in order ---------------------------------------------------------------


def by_way() -> dict:
    """A factoid in which someone holds an office by a `Maybe` of some likelihood, the office by an edge that is
    sure; and that mentions something by a `Hearsay`"""
    return {
        "type": "Factoid",
        "where": {
            "$somewhere": [
                {
                    "type": "HoldsOffice",
                    "where": {
                        "holder": {
                            "via": [
                                {"type": "Maybe", "where": {"likelihood": {"gte": 2}}}
                            ],
                        },
                        "office": {
                            "is": OFFICE,
                            "via": [
                                {
                                    "type": "Certainty",
                                    "where": {"certainty": {"gte": 50}},
                                }
                            ],
                        },
                    },
                }
            ],
            "$mentions": {"is": MAXIMILIAN, "via": [{"type": "Hearsay"}]},
        },
    }


def who_holds() -> dict:
    """Someone who holds an office by a `Maybe` of some likelihood"""
    return {
        "type": "Person",
        "where": {
            "$incoming": [
                {
                    "type": "HoldsOffice",
                    "field": "holder",
                    "via": [{"type": "Maybe", "where": {"likelihood": {"gte": 2}}}],
                }
            ]
        },
    }


def via_of(pattern: dict, field: str) -> list:
    return pattern["where"]["$somewhere"][0]["where"][field]["via"]


def test_the_classes_and_fields_of_a_via_are_renamed_as_those_of_through_and_edge_are():
    old = snapshot_of(court())
    names = {"Maybe": "Perhaps", "Hearsay": "Rumour", "Certainty": "Confidence"}
    result = changes(
        court(),
        court(**names, likelihood="probability", certainty="confidence"),
        confirmed=[
            *(PossibleRename(what="model", old=o, new=n) for o, n in names.items()),
            renamed_field("Perhaps", "likelihood", "probability"),
            renamed_field("Confidence", "certainty", "confidence"),
        ],
    )
    found, broken = walk(old, result, by_way())
    assert broken == []
    assert via_of(found, "holder") == [
        {"type": "Perhaps", "where": {"probability": {"gte": 2}}}
    ]
    assert via_of(found, "office") == [
        {"type": "Confidence", "where": {"confidence": {"gte": 50}}}
    ]
    assert found["where"]["$mentions"]["via"] == [{"type": "Rumour"}]
    person, broken = walk(old, result, who_holds())
    assert broken == []
    assert incoming_of(person)["via"] == [
        {"type": "Perhaps", "where": {"probability": {"gte": 2}}}
    ]
    fits(found)
    fits(person)


def test_a_wrapper_that_becomes_another_is_renamed_in_via_of_the_field():
    old = snapshot_of(court())
    change = c.ChangeWrapper(
        model="HoldsOffice",
        name="holder",
        old_wrapper="Maybe",
        new_wrapper="Hearsay",
        wrapper_kind="reifiedRelation",
    )
    found = upgrade(by_way(), change, old)
    assert via_of(found.pattern, "holder")[0]["type"] == "Hearsay"
    assert via_of(found.pattern, "office") == via_of(by_way(), "office")
    person = upgrade(who_holds(), change, old)
    assert incoming_of(person.pattern)["via"][0]["type"] == "Hearsay"
    # (of another field, it is not)
    other = c.ChangeWrapper(
        model="HoldsOffice",
        name="office",
        old_wrapper="Maybe",
        new_wrapper="Hearsay",
        wrapper_kind="reifiedRelation",
    )
    assert upgrade(by_way(), other, old).pattern == by_way()


def test_what_breaks_a_via():
    old = snapshot_of(court())
    # (a class it names is deleted)
    space = c.DeleteModel(model="Hearsay", model_kind="SemanticSpace")
    assert upgrade(by_way(), space, old).broken == Broken(
        "$mentions.via.0", "the model Hearsay was deleted"
    )
    edge = c.DeleteModel(model="Certainty", model_kind="EdgeModel")
    upgraded = upgrade(by_way(), edge, old)
    assert upgraded.broken == Broken(
        "$somewhere.office.via.0", "the model Certainty was deleted"
    )
    assert upgraded.pattern == by_way()
    # (a field of an item is removed)
    result = changes(court(), court(likelihood="other"))
    removed = only(result, c.RemoveField)
    assert removed
    _, broken = walk(old, result, by_way())
    assert broken == [
        Broken(
            "$somewhere.holder.via.0.Maybe.likelihood",
            "the field 'likelihood' of Maybe was removed",
        )
    ]
    # (the relation no longer passes through the wrapper)
    result = changes(court(), court(holder_type="list[{Person}]"))
    found, broken = walk(old, result, by_way())
    assert broken == [
        Broken(
            "$somewhere.holder.via.0",
            "HoldsOffice.holder no longer passes through Maybe",
        )
    ]
    assert via_of(found, "holder") == via_of(by_way(), "holder")
