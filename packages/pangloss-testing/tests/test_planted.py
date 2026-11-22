"""The planted world (`pangloss_testing.planted`): the same seed gives the same world, and its truth names only what
is in it (implementation_docs/similarity-build-plan.md, step 8.1)"""

import json

from pangloss_testing import planted


def references(value):
    """Every `{"type", "id"}` in a payload, below its top"""
    if isinstance(value, dict):
        if set(value) >= {"type", "id"}:
            yield value["type"], value["id"]
        for inner in value.values():
            yield from references(inner)
    elif isinstance(value, list):
        for inner in value:
            yield from references(inner)


def test_the_same_seed_gives_the_same_world_and_another_seed_another():
    first, again, other = (
        planted.world(seed=3),
        planted.world(seed=3),
        planted.world(seed=4),
    )
    assert json.dumps(first.records()) == json.dumps(again.records())
    assert json.dumps(first.truth()) == json.dumps(again.truth())
    assert json.dumps(first.records()) != json.dumps(other.records())


def test_every_reference_of_a_factoid_is_to_an_entity_of_the_world():
    world = planted.world(seed=1, people=300)
    known = {(entity["type"], entity["id"]) for entity in world.entities}
    assert len(known) == len(world.entities)
    for factoid in world.factoids:
        assert {
            ref for statement in factoid["statements"] for ref in references(statement)
        } <= known


def test_the_truth_names_only_what_is_in_the_world():
    world = planted.world(seed=1, people=300)
    people = {person.id for person in world.people}
    assert world.mentions and all(
        mention.person in people for mention in world.mentions
    )
    assert not {mention.id for mention in world.mentions} & people
    assert set(world.years) == {factoid["label"] for factoid in world.factoids}
    assert all(set(ids) <= people for ids in world.namesakes.values())
    # (a mention is named by exactly one factoid, and nothing else says who it is)
    named = [
        id for factoid in world.factoids for _, id in references(factoid["statements"])
    ]
    assert all(named.count(mention.id) == 1 for mention in world.mentions)


def test_the_world_has_what_makes_names_hard():
    world = planted.world(seed=1, people=300)
    assert 250 <= len(world.people) <= 400
    shared = sum(len(ids) for ids in world.namesakes.values())
    assert shared >= len(world.people) // 10, (
        "too few people share a name for a name alone to be put to the test"
    )
    kinds = {mention.kind for mention in world.mentions}
    assert kinds == set(planted.KINDS)
    by_id = {person.id: person for person in world.people}
    for mention in world.mentions:
        person = by_id[mention.person]
        given, surname = mention.label.split(" ", 1)
        assert given == person.given or given in planted.GIVEN[person.given]
        if mention.kind in ("same", "variant"):
            assert surname == person.surname
        else:
            assert surname != person.surname


def test_another_spelling_is_the_same_for_the_same_choice_and_differs_from_the_name():
    assert planted.respelled("Meyer", 1) == planted.respelled("Meyer", 1) == "Meier"
    assert planted.respelled("Xo", 0) == "Xo"


# -- with dates (step 9.2) --


def without_dates(factoids):
    return [
        {
            **factoid,
            "statements": [
                {key: value for key, value in statement.items() if key != "when"}
                for statement in factoid["statements"]
            ],
        }
        for factoid in factoids
    ]


def test_a_dated_world_is_the_same_world_with_dates_and_more_reports_after_it():
    plain, dated = planted.world(seed=2), planted.world(seed=2, dated=True)
    assert plain.people == dated.people and plain.mentions == dated.mentions
    assert without_dates(dated.factoids[: len(plain.factoids)]) == plain.factoids
    assert len(dated.factoids) > len(plain.factoids)
    assert (plain.dates, plain.events, plain.series) == ({}, {}, {})
    again = planted.world(seed=2, dated=True)
    assert json.dumps(again.records()) == json.dumps(dated.records())
    assert json.dumps(again.truth()) == json.dumps(dated.truth())


def test_every_statement_of_a_dated_world_says_when_as_its_factoid_s_truth_has_it():
    world = planted.world(seed=1, people=300, dated=True)
    assert set(world.dates) == set(world.years)
    kinds = set()
    for factoid in world.factoids:
        said = world.dates[factoid["label"]]
        assert all(statement["when"] == said for statement in factoid["statements"])
        kinds.add((said["type"], *sorted(said)))
        if said["type"] == "DateRange":
            year = world.years[factoid["label"]]
            assert said["not_before"]["year"] <= year <= said["not_after"]["year"]
        else:
            assert said["year"] == world.years[factoid["label"]]
    # (a day, a month, a year, and some years it was within)
    assert len(kinds) == 4


def test_the_truth_of_the_events_names_factoids_of_the_world_each_once():
    world = planted.world(seed=1, people=300, dated=True)
    labels = {factoid["label"] for factoid in world.factoids}
    reports = [label for said in world.events.values() for label in said]
    assert set(reports) <= labels and len(reports) == len(set(reports))
    assert all(len(said) == 2 for said in world.events.values())
    # (the reports of one event are of one year, and of the same one who did it)
    by_label = {factoid["label"]: factoid for factoid in world.factoids}
    for said in world.events.values():
        assert len({world.years[label] for label in said}) == 1
        doers = {
            json.dumps(
                by_label[label]["statements"][0].get("carried_out_by")
                or by_label[label]["statements"][0]["given_by"]
            )
            for label in said
        }
        assert len(doers) == 1


def test_what_happened_year_after_year_is_reported_twice_each_year_and_differs_only_in_its_date():
    world = planted.world(seed=1, people=300, dated=True)
    assert world.series
    by_label = {factoid["label"]: factoid for factoid in world.factoids}
    for events in world.series.values():
        assert 6 <= len(events) <= 12
        years = [world.years[world.events[event][0]] for event in events]
        assert years == list(range(years[0], years[0] + len(years)))
        told = {
            json.dumps(without_dates([by_label[label]])[0]["statements"])
            for event in events
            for label in world.events[event]
        }
        assert len(told) == 1
        # (a payment is never said as some years it was within: that would be more than one of them)
        assert all(
            world.dates[label]["type"] == "ExactDate"
            for event in events
            for label in world.events[event]
        )
