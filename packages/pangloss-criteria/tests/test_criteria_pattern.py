"""`SearchPattern`: a pattern of structured search as a value of a model, what a stored one may hold, and the ids it
names (implementation_docs/matches-criteria.md, "The model")"""

import json
from uuid import UUID

import pytest
from pangloss_criteria import SearchPattern, check_stored
from pangloss_criteria.pattern import FORMAT, ids_named, walk, with_ids
from pangloss_models import (
    Document,
    EdgeModel,
    Entity,
    Match,
    ModelRegistry,
    PanglossSearchError,
    ReifiedRelation,
    SemanticSpace,
    Through,
    ViaEdge,
    export_models,
    initialise,
    literals,
)
from pangloss_models.search_where import IncomingFrom, Rel, Text
from pydantic import ValidationError

MAX = "01a1c564-7def-70f0-bd21-410a35c82ab1"
SEC = "01a1c564-7def-70f0-bd21-410a35c82ab2"
ANN = "01a1c564-7def-70f0-bd21-410a35c82ab3"


def models():
    class Certainty(EdgeModel):
        percent: int

    class Person(Entity):
        gender: str | None = None

    class Monk(Person):
        pass

    class Office(Entity):
        pass

    class Doubtful[T](SemanticSpace[T]):
        pass

    class Guess[T](ReifiedRelation[T]):
        wording: str | None = None

    class HoldsOffice(Document):
        holder: list[Person | Doubtful[Person] | Guess[Person]]
        office: Office
        employer: ViaEdge[Person, Certainty]
        year: int | None = None

    class Described(Document):
        wording: str | None = None
        criteria: SearchPattern | None = None
        others: list[SearchPattern] = []

    initialise()
    return Person, Monk, Office, HoldsOffice, Described


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


# --- what it is made from ----------------------------------------------------------------------------------------------


def test_it_is_made_from_the_json_of_a_search():
    models()

    pattern = SearchPattern(SECRETARY)

    assert pattern.type == "Person"
    assert pattern.where == SECRETARY["where"]
    assert pattern.data == SECRETARY
    assert pattern == SearchPattern(json.loads(json.dumps(SECRETARY)))
    assert repr(pattern).startswith("SearchPattern({'type': 'Person'")


def test_it_is_made_from_a_where_of_a_model_which_gives_the_type():
    Person, Monk, Office, HoldsOffice, Described = models()

    pattern = SearchPattern(
        Person.Where(
            incoming_=[
                IncomingFrom(
                    field="holder",
                    where=HoldsOffice.Where(
                        office=Rel(is_=UUID(SEC)), employer=Rel(is_=MAX)
                    ),
                )
            ]
        )
    )

    assert pattern.type == "Person"
    (incoming,) = pattern.where["$incoming"]
    assert incoming["type"] == "HoldsOffice" and incoming["field"] == "holder"
    assert incoming["where"]["office"] == {"is": SEC}
    assert incoming["where"]["employer"] == {"is": MAX}
    # (plain JSON: it can be stored)
    assert json.loads(pattern.text()) == pattern.data


def test_it_is_made_from_a_match_and_from_its_own_text():
    models()

    from_match = SearchPattern(Match(type="Person", where={"gender": {"eq": "f"}}))

    assert from_match.data == {"type": "Person", "where": {"gender": {"eq": "f"}}}
    assert SearchPattern(from_match.text()) == from_match
    assert SearchPattern(from_match) == from_match
    assert hash(SearchPattern(from_match.text())) == hash(from_match)


def test_a_where_of_no_condition_is_every_one_of_the_type():
    models()

    assert SearchPattern({"type": "Person"}).where == {}
    assert SearchPattern({"type": "Person", "where": None}).where == {}


@pytest.mark.parametrize(
    "given, why",
    [
        ({"where": {}}, "needs the 'type'"),
        ({"type": "", "where": {}}, "needs the 'type'"),
        ({"type": "Person", "where": []}, "'where' of a search pattern is an object"),
        ({"type": "Person", "order_by": [{"field": "label"}]}, "'order_by'"),
        ({"type": "Person", "exclude_wrappers": ["Guess"]}, "'exclude_wrappers'"),
        ({"type": "Person", "page": 2}, "'page'"),
        (17, "not a int"),
        ("{not json", "is JSON"),
        ("[1, 2]", "not a list"),
    ],
)
def test_what_is_not_a_pattern_is_refused(given, why):
    models()

    with pytest.raises(ValueError, match=why):
        SearchPattern(given)


def test_the_text_is_the_same_for_the_same_pattern_however_it_was_written():
    models()

    one = SearchPattern(
        {"type": "Person", "where": {"gender": {"eq": "f"}, "label": {"contains": "a"}}}
    )
    other = SearchPattern(
        {"where": {"label": {"contains": "a"}, "gender": {"eq": "f"}}, "type": "Person"}
    )

    assert one.text() == other.text() and one == other
    assert " " not in one.text()


# --- as a field of a model ---------------------------------------------------------------------------------------------


def test_it_is_a_literal_type_stored_as_text_and_exported_with_its_format():
    Person, Monk, Office, HoldsOffice, Described = models()

    assert literals.is_literal_type(SearchPattern)
    assert literals.codec_for(SearchPattern).describe() == {
        "type": "str",
        "format": FORMAT,
    }
    assert literals.search_kind_of(SearchPattern) is None
    fields = {f["name"]: f for f in export_models()["models"]["Described"]["fields"]}
    assert fields["criteria"]["kind"] == "literal"
    assert fields["criteria"]["type"] == {"type": "str", "format": "search-pattern"}
    assert fields["others"]["kind"] == "list"
    assert fields["others"]["item"] == {"type": "str", "format": "search-pattern"}


def test_a_model_takes_it_as_json_as_a_where_or_as_a_pattern():
    Person, Monk, Office, HoldsOffice, Described = models()

    as_json = Described.Create(label="D", criteria=SECRETARY)
    as_where = Described.Create(label="D", criteria=Person.Where(gender=Text(eq="f")))
    as_pattern = Described.Create(label="D", criteria=SearchPattern(SECRETARY))

    assert isinstance(as_json.criteria, SearchPattern)
    assert as_json.criteria == as_pattern.criteria == SearchPattern(SECRETARY)
    assert as_where.criteria.data == {
        "type": "Person",
        "where": {"gender": {"eq": "f"}},
    }
    assert Described.Create(label="D").criteria is None
    with pytest.raises(ValidationError, match="needs the 'type'"):
        Described.Create(label="D", criteria={"where": {}})


def test_it_is_written_as_text_and_read_back_from_it():
    from pangloss_cypher.values import convert_type_for_writing

    Person, Monk, Office, HoldsOffice, Described = models()

    written = Described.Create(label="D", criteria=SECRETARY)._to_db_model()

    assert isinstance(written.criteria, SearchPattern)
    stored = convert_type_for_writing(written.criteria)
    assert isinstance(stored, str) and json.loads(stored) == SECRETARY
    # (what a database gives back: the text)
    read = Described.View(
        id=MAX, type="Described", label="D", criteria=stored, others=[stored]
    )
    assert read.criteria == SearchPattern(SECRETARY)
    assert read.others == [SearchPattern(SECRETARY)]


def test_it_is_json_in_what_the_api_gives_and_in_what_history_keeps():
    Person, Monk, Office, HoldsOffice, Described = models()

    view = Described.View(id=MAX, type="Described", label="D", criteria=SECRETARY)

    assert view.model_dump(mode="json", by_alias=True)["criteria"] == SECRETARY
    assert json.loads(view.model_dump_json())["criteria"] == SECRETARY
    assert view.model_dump()["criteria"] == SECRETARY
    # (and what was read can be sent back)
    again = Described.Update(**view.model_dump(mode="json"))
    assert again.criteria == SearchPattern(SECRETARY)


def test_its_json_schema_says_it_is_an_object_of_this_format():
    Person, Monk, Office, HoldsOffice, Described = models()

    schema = Described.Create.model_json_schema()

    found = json.dumps(schema)
    assert '"format": "search-pattern"' in found


# --- what a stored pattern may hold ------------------------------------------------------------------------------------


def test_a_pattern_that_fits_the_models_is_checked_to_its_conditions():
    Person, Monk, Office, HoldsOffice, Described = models()

    checked = check_stored(SearchPattern(SECRETARY), [Person])

    assert len(checked) == 1 and checked[0].kind == "incoming"


def test_the_type_must_be_one_that_is_described_or_a_class_below_it():
    Person, Monk, Office, HoldsOffice, Described = models()

    check_stored(SearchPattern({"type": "Monk"}), [Person])
    check_stored(SearchPattern({"type": "Person"}), [Office, Person])
    check_stored(SearchPattern({"type": "Office"}))  # (anything, if nothing is said)
    with pytest.raises(
        PanglossSearchError,
        match="type: 'Office' is not what is described here \\(Person\\)",
    ):
        check_stored(SearchPattern({"type": "Office"}), [Person])
    # (a class above the one described would find what cannot be put here)
    with pytest.raises(
        PanglossSearchError,
        match="type: 'Person' is not what is described here \\(Monk\\)",
    ):
        check_stored(SearchPattern({"type": "Person"}), [Monk])
    with pytest.raises(
        PanglossSearchError, match="type: There is no model called 'Nobody'"
    ):
        check_stored(SearchPattern({"type": "Nobody"}), [Person])
    with pytest.raises(
        PanglossSearchError,
        match="type: 'Certainty' is not a document or an entity type",
    ):
        check_stored(SearchPattern({"type": "Certainty"}))


def test_what_a_search_would_refuse_is_refused_with_the_path_in_the_pattern():
    Person, Monk, Office, HoldsOffice, Described = models()

    def refused(where):
        with pytest.raises(PanglossSearchError) as error:
            check_stored(SearchPattern({"type": "Person", "where": where}), [Person])
        return str(error.value)

    assert "age: Person has no field 'age'" in refused({"age": {"gt": 3}})
    assert "$incoming.salary: HoldsOffice has no field 'salary'" in refused(
        {"$incoming": [{"type": "HoldsOffice", "where": {"salary": {"gt": 1}}}]}
    )
    assert "$incoming.year.contains: not an operator for this field" in refused(
        {"$incoming": [{"type": "HoldsOffice", "where": {"year": {"contains": "1"}}}]}
    )
    assert "$incoming.year.eq: 'x' is not a valid int" in refused(
        {"$incoming": [{"type": "HoldsOffice", "where": {"year": {"eq": "x"}}}]}
    )
    assert "HoldsOffice has no relation 'office' that can point at a Person" in refused(
        {"$incoming": [{"type": "HoldsOffice", "field": "office"}]}
    )
    assert "'$nonsense' is not supported" in refused({"$nonsense": 1})
    assert (
        "$incoming[0].where.employer.is: 'not-a-uuid' is not the id of an entity"
        in refused(
            {
                "$incoming": [
                    {"type": "HoldsOffice", "where": {"employer": {"is": "not-a-uuid"}}}
                ]
            }
        )
    )


def test_a_condition_on_the_way_or_on_an_edge_is_allowed_as_in_any_search():
    Person, Monk, Office, HoldsOffice, Described = models()

    check_stored(
        SearchPattern(
            {
                "type": "HoldsOffice",
                "where": {
                    "holder": {
                        "is": ANN,
                        "through": [
                            {"type": "Guess", "where": {"wording": {"exists": True}}}
                        ],
                    },
                    "employer": {
                        "is": MAX,
                        "edge": {
                            "type": "Certainty",
                            "where": {"percent": {"gte": 60}},
                        },
                    },
                    "$any_of": [
                        {"year": {"lt": 1500}},
                        {"$not": {"year": {"exists": True}}},
                    ],
                },
            }
        )
    )
    # (and written with the classes of a typed search)
    Guess = ModelRegistry.all_models()["Guess"]
    typed = SearchPattern(
        HoldsOffice.Where(holder=Rel(is_=ANN, through=[Through(Guess)]))
    )
    assert typed.where["holder"]["through"] == [{"type": "Guess"}]
    check_stored(typed)


@pytest.mark.parametrize(
    "where, path, key",
    [
        ({"$same_as": {"is": ANN}}, "\\$same_as", "$same_as"),
        ({"$derived": {"type": "Kin"}}, "\\$derived", "$derived"),
        (
            {
                "$incoming": [
                    {"type": "HoldsOffice", "where": {"employer": {"$var": "a"}}}
                ]
            },
            "\\$incoming\\[0\\].where.employer.\\$var",
            "$var",
        ),
        ({"$any_of": [{"$is": {"$var": "a"}}]}, "\\$any_of\\[0\\].\\$is", "$is"),
        (
            {
                "$incoming": [
                    {
                        "type": "HoldsOffice",
                        "where": {"year": {"eq": {"$document": {"field": "year"}}}},
                    }
                ]
            },
            "\\$incoming\\[0\\].where.year.eq.\\$document",
            "$document",
        ),
    ],
)
def test_what_only_a_stored_pattern_may_not_hold_is_refused_with_its_path_and_why(
    where, path, key
):
    Person, Monk, Office, HoldsOffice, Described = models()

    with pytest.raises(
        PanglossSearchError, match=f"^{path}: '\\{key}' cannot be in a stored pattern: "
    ):
        check_stored(SearchPattern({"type": "Person", "where": where}), [Person])


def test_a_through_that_names_a_wrapper_it_is_evaluated_without_is_refused():
    Person, Monk, Office, HoldsOffice, Described = models()
    through_guess = SearchPattern(
        {
            "type": "Person",
            "where": {
                "$incoming": [
                    {
                        "type": "HoldsOffice",
                        "where": {"holder": {"is": ANN, "through": ["Guess"]}},
                    }
                ]
            },
        }
    )

    check_stored(through_guess, [Person])
    check_stored(through_guess, [Person], exclude_wrappers=["Doubtful"])
    with pytest.raises(
        PanglossSearchError,
        match="holder.through: 'Guess' is a wrapper the search leaves out",
    ):
        check_stored(through_guess, [Person], exclude_wrappers=["Guess"])
    with pytest.raises(PanglossSearchError, match="exclude_wrappers: 'Person' is not"):
        check_stored(through_guess, [Person], exclude_wrappers=["Person"])


def test_a_pattern_that_cannot_be_read_as_a_search_says_where():
    models()

    with pytest.raises(PanglossSearchError, match="where"):
        check_stored(
            SearchPattern({"type": "Person", "where": {"gender": {"nonsense": 1}}})
        )


# --- the ids a pattern names --------------------------------------------------------------------------------------------


def test_the_ids_a_pattern_names_are_found_wherever_they_are():
    models()
    pattern = SearchPattern(
        {
            "type": "Person",
            "where": {
                "$incoming": [
                    {
                        "type": "HoldsOffice",
                        "where": {
                            "office": {"is": SEC},
                            "$any_of": [
                                {"employer": {"is_any": [MAX, ANN]}},
                                {"$not": {"employer": {"is": MAX}}},
                            ],
                        },
                    }
                ],
                # (not an id: the value of a field called `is` is not there, and a text is a text)
                "gender": {"eq": MAX},
            },
        }
    )

    assert sorted(ids_named(pattern)) == sorted([SEC, MAX, ANN])
    assert ids_named(SearchPattern({"type": "Person"})) == []


def test_ids_are_replaced_and_a_list_that_names_one_twice_by_it_has_it_once():
    models()
    pattern = SearchPattern(
        {
            "type": "Person",
            "where": {
                "$incoming": [
                    {
                        "type": "HoldsOffice",
                        "where": {
                            "office": {"is": SEC},
                            "employer": {"is_any": [MAX, ANN]},
                        },
                    }
                ]
            },
        }
    )

    replaced = with_ids(pattern, {MAX: ANN, SEC: MAX})

    (incoming,) = replaced.where["$incoming"]
    assert incoming["where"]["office"] == {"is": MAX}
    assert incoming["where"]["employer"] == {"is_any": [ANN]}
    # (the pattern given is not changed, and with nothing to replace it is itself)
    assert pattern.where["$incoming"][0]["where"]["office"] == {"is": SEC}
    assert with_ids(pattern, {}) is pattern


def test_walking_a_pattern_gives_each_key_with_its_path():
    models()

    paths = [path for path, _, _ in walk(SearchPattern(SECRETARY).where)]

    # (the keys of a pattern are kept in order)
    assert paths == [
        "$incoming",
        "$incoming[0].field",
        "$incoming[0].type",
        "$incoming[0].where",
        "$incoming[0].where.employer",
        "$incoming[0].where.employer.is",
        "$incoming[0].where.office",
        "$incoming[0].where.office.is",
    ]


# --- through a migration (`LiteralCodec.migrate`) ----------------------------------------------------------------------


def _employed_by_max() -> dict:
    return {
        "type": "Person",
        "where": {
            "$incoming": [
                {
                    "type": "HoldsOffice",
                    "field": "holder",
                    "where": {"employer": {"is": MAX}, "year": {"gt": 1490}},
                }
            ]
        },
    }


def test_the_codec_brings_a_stored_pattern_through_a_change_in_the_form_it_was_given():
    from pangloss_criteria.pattern import CODEC, migrated
    from pangloss_models.migrations import build_snapshot
    from pangloss_models.migrations import changes as c

    models()
    initialise()
    before = build_snapshot()
    rename = c.RenameField(model="HoldsOffice", old="year", new="when")
    text = SearchPattern(_employed_by_max()).text()
    assert literals.codec_of_format(FORMAT) is not None
    assert literals.codec_of_format(FORMAT).migrate is CODEC.migrate is migrated

    # as the database keeps it: text, its keys in order
    made = migrated(text, rename, before)
    assert isinstance(made, str) and made == SearchPattern(json.loads(made)).text()
    assert json.loads(made)["where"]["$incoming"][0]["where"]["when"] == {"gt": 1490}
    # as a version in history has it: the JSON
    made = migrated(_employed_by_max(), rename, before)
    assert made["where"]["$incoming"][0]["where"]["when"] == {"gt": 1490}
    # one it does not alter is given back as it is
    other = c.RenameField(model="Office", old="label", new="name")
    assert migrated(text, other, before) is text
    assert migrated(text, c.RunPython(function="a:b"), before) is text


def test_the_codec_says_what_a_change_makes_wrong_and_keeps_the_condition():
    from pangloss_criteria.pattern import migrated
    from pangloss_models import ValueNotMigrated
    from pangloss_models.migrations import build_snapshot
    from pangloss_models.migrations import changes as c

    models()
    initialise()
    before = build_snapshot()
    removed = c.RemoveField(model="HoldsOffice", name="employer", field_kind="relation")
    text = SearchPattern(_employed_by_max()).text()
    with pytest.raises(ValueNotMigrated) as raised:
        migrated(text, removed, before)
    assert raised.value.kind == "pattern"
    assert raised.value.path == "$incoming.employer"
    assert raised.value.reason == "the field 'employer' of HoldsOffice was removed"
    assert raised.value.value == text
