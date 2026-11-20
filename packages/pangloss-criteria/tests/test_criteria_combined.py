"""The effective criteria of a mention that cites a shared description (`pattern.combined`, `effective.effective`):
the shared criteria and its own, and when they cannot be (implementation_docs/matches-criteria.md, "Shared
descriptions")"""

import pytest
from pangloss_criteria import SearchPattern, combined
from pangloss_criteria.analysis import analyse
from pangloss_criteria.effective import Shared, effective, fits_place
from pangloss_criteria.pattern import check_stored
from pangloss_models import Document, Entity, PanglossSearchError, initialise

MAX = "01a1c564-7def-70f0-bd21-410a35c82ab1"
SEC = "01a1c564-7def-70f0-bd21-410a35c82ab2"
SHARED_ID = "01a1c564-7def-70f0-bd21-410a35c82ab9"


@pytest.fixture
def models():
    class Person(Entity):
        gender: str | None = None

    class Monk(Person):
        pass

    class Group(Entity):
        pass

    class Office(Entity):
        pass

    class HoldsOffice(Document):
        holder: list[Person]
        office: Office
        employer: Person
        year: int | None = None

    initialise()


SECRETARY = SearchPattern(
    {
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
)


def test_with_no_criteria_of_its_own_the_effective_criteria_are_exactly_the_shared_ones(
    models,
):
    found = combined(SECRETARY, None)
    assert found is SECRETARY
    # (so that mentions that only cite it are identical criteria: one text, one hash)
    assert found.text() == SECRETARY.text()


def test_both_wheres_are_joined_in_the_grammars_conjunction(models):
    own = SearchPattern({"type": "Person", "where": {"gender": {"eq": "male"}}})
    found = combined(SECRETARY, own)
    assert found.type == "Person"
    assert found.where == {"$all": [SECRETARY.where, own.where]}
    # (a pattern a search reads: two conditions at the root, so not complete)
    items = check_stored(found)
    assert len(items) == 2
    assert not analyse(type("x", (), {}), []).complete
    assert MAX in found.text() and "male" in found.text()


def test_an_empty_where_is_left_out(models):
    narrowing = SearchPattern({"type": "Monk", "where": {}})
    found = combined(SECRETARY, narrowing)
    assert found.data == {"type": "Monk", "where": SECRETARY.where}
    empty = SearchPattern({"type": "Person", "where": {}})
    found = combined(
        empty, SearchPattern({"type": "Person", "where": {"gender": {"eq": "f"}}})
    )
    assert found.where == {"gender": {"eq": "f"}}
    assert combined(empty, empty).data == {"type": "Person", "where": {}}


def test_the_own_class_is_the_shared_one_or_below_it(models):
    combined(SECRETARY, SearchPattern({"type": "Monk", "where": {}}))
    with pytest.raises(PanglossSearchError, match="'Group' is not 'Person'"):
        combined(SECRETARY, SearchPattern({"type": "Group", "where": {}}))
    # (a class above the shared one would find what the shared criteria do not describe)
    monks = SearchPattern({"type": "Monk", "where": {}})
    with pytest.raises(PanglossSearchError, match="nor a class below it"):
        combined(monks, SearchPattern({"type": "Person", "where": {}}))
    with pytest.raises(PanglossSearchError, match="type"):
        combined(SECRETARY, SearchPattern({"type": "Nobody", "where": {}}))


def shared(criteria=SECRETARY, deleted=False) -> dict[str, Shared]:
    return {
        SHARED_ID: Shared(
            id=SHARED_ID,
            label="Maximilian's secretary",
            criteria=None if criteria is None else criteria.text(),
            deleted=deleted,
        )
    }


def test_effective_criteria_of_a_mention(models):
    # its own, alone
    assert effective(SECRETARY.text(), None, {}) == SECRETARY
    # none: a place of a mark that another place holds them for
    assert effective(None, None, {}) is None
    # the shared ones, and its own with them
    assert effective(None, SHARED_ID, shared()) == SECRETARY
    own = SearchPattern({"type": "Monk", "where": {}})
    assert effective(own.text(), SHARED_ID, shared()).type == "Monk"


def test_a_description_that_is_not_there_or_deleted_gives_no_criteria(models):
    with pytest.raises(PanglossSearchError, match="is not there"):
        effective(None, SHARED_ID, {})
    with pytest.raises(PanglossSearchError, match="is not there"):
        effective(None, SHARED_ID, shared(deleted=True))


def test_the_class_of_the_effective_criteria_is_one_the_place_takes(models):
    groups = SearchPattern({"type": "Group", "where": {}})
    assert effective(None, SHARED_ID, shared(groups), ["Group"]) == groups
    with pytest.raises(PanglossSearchError, match="not taken here"):
        effective(None, SHARED_ID, shared(groups), ["Person"])
    # (a class below one the place takes is taken)
    fits_place(SearchPattern({"type": "Monk", "where": {}}), ["Person"])
    # (a place whose classes are no longer all classes of the models, after a rename, is not checked)
    fits_place(groups, ["Person", "Renamed"])
    fits_place(groups, [])
