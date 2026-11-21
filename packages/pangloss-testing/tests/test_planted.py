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
