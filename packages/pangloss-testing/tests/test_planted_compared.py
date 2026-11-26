"""The planted world for comparison (`planted.world(compared=True)`, on `similar_models.declare(compared=True)`):
the same seed gives the same world, each case is there in a share near the one asked, and the truth holds, read from
the payloads and by the walk (implementation_docs/spaces-and-comparison-plan.md, step 5.1). No database."""

import collections
import json
import typing

import pytest
from pangloss_core import BaseSettings, DatabaseSettings
from pangloss_models import ModelRegistry, spaces
from pydantic import AnyHttpUrl, create_model

from pangloss_testing import planted
from pangloss_testing.similar_models import declare

PAIRED = [case for case in planted.COMPARED if not case.startswith("absence")]


@pytest.fixture(scope="module")
def world():
    return planted.world(seed=1, people=300, compared=True)


@pytest.fixture(scope="module")
def large():
    return planted.world(seed=2, people=5000, compared=True)


@pytest.fixture
def models():
    """The models declared for comparison, with settings for the models alone (no connection)"""
    Settings: typing.Any = create_model(
        "Settings",
        __base__=BaseSettings,
        PROJECT_NAME=(str, "Test"),
        BACKEND_CORS_ORIGINS=(list[typing.Any], []),
        INSTALLED_APPS=(
            list[str],
            ["pangloss_derived", "pangloss_library", "pangloss_criteria"],
        ),
        STORAGE=(str | None, "pangloss_sdk.storage:api"),
        DATABASE=(DatabaseSettings, DatabaseSettings()),
        INTERFACE_LANGUAGES=(list[str], ["en"]),
        DEFAULT_INTERFACE_LANGUAGE=(str, "en"),
        AUTHJWT_SECRET_KEY=(str, "asdf"),
        ENTITY_BASE_URL=(AnyHttpUrl, AnyHttpUrl("http://test.com/")),
    )
    Settings()
    ModelRegistry._reset()
    yield declare(compared=True)
    ModelRegistry._reset()


def references(value):
    """Every `{"type", "id"}` in a payload"""
    if isinstance(value, dict):
        if set(value) >= {"type", "id"}:
            yield value["type"], value["id"]
        for inner in value.values():
            yield from references(inner)
    elif isinstance(value, list):
        for inner in value:
            yield from references(inner)


def day_of(statement) -> tuple[int, int, int]:
    said = statement["when"]
    return (said["year"], said["month"], said["day"])


# -- the world --


def test_the_same_seed_gives_the_same_world_and_another_seed_another():
    first, again, other = (
        planted.world(seed=3, compared=True),
        planted.world(seed=3, compared=True),
        planted.world(seed=4, compared=True),
    )
    assert json.dumps(first.records()) == json.dumps(again.records())
    assert json.dumps(first.truth()) == json.dumps(again.truth())
    assert json.dumps(first.records()) != json.dumps(other.records())


def test_a_compared_world_is_the_dated_world_and_what_is_added_comes_after_it():
    dated, compared = (
        planted.world(seed=2, dated=True),
        planted.world(seed=2, compared=True),
    )
    assert dated.people == compared.people and dated.mentions == compared.mentions
    assert compared.factoids[: len(dated.factoids)] == dated.factoids
    assert (dated.events, dated.series) == (compared.events, compared.series)
    assert (dated.told, dated.verdicts, dated.liveness) == ({}, [], {})
    assert (dated.sources, dated.things) == ([], [])
    added = compared.factoids[len(dated.factoids) :]
    assert added and all("source" in factoid for factoid in added)
    assert {t.factoid for t in compared.told.values()} == {f["label"] for f in added}


def test_every_reference_is_to_an_entity_of_the_world_and_every_factoid_has_its_year(
    world,
):
    known = {(entity["type"], entity["id"]) for entity in world.entities}
    assert len(known) == len(world.entities)
    for factoid in world.factoids:
        assert set(references(factoid)) <= known
    labels = [factoid["label"] for factoid in world.factoids]
    assert len(set(labels)) == len(labels)
    assert set(world.years) == set(world.dates) == set(labels)


def test_each_case_is_there_in_a_share_near_the_one_asked(large):
    families = len({person.family for person in large.people})
    pairs = collections.Counter(verdict.case for verdict in large.verdicts)
    assert set(pairs) == set(PAIRED)
    for case in PAIRED:
        asked = planted.COMPARED[case] * families
        # (a case is left out of a family that cannot have it: no fellow of a group, no child left to be born)
        assert 0.6 * asked <= pairs[case] <= 1.3 * asked, case
    assemblies = collections.Counter(
        told.case for told in large.told.values() if told.case.startswith("absence")
    )
    rolls = sum(1 for f in large.factoids if f["label"].startswith("The roll"))
    assert rolls >= 0.9 * len(large.groups)
    assert assemblies["absence_expected"] >= rolls
    assert 0.35 * rolls <= assemblies["absence_unexpected"] <= 0.65 * rolls
    # (every relation is planted)
    assert {verdict.relation for verdict in large.verdicts} == set(planted.RELATIONS)


def test_an_order_and_what_came_of_it_are_in_one_factoid_three_times_in_ten(large):
    answered = [v for v in large.verdicts if v.relation in ("carried_out", "carried_out_otherwise", "not_carried_out", "breach", "complied", "permission_used")]  # fmt: skip
    together = sum(1 for verdict in answered if verdict.same_factoid)
    assert 0.2 * len(answered) <= together <= 0.4 * len(answered)
    apart = [v for v in large.verdicts if not v.same_factoid]
    same = sum(1 for verdict in apart if verdict.same_source)
    assert 0.12 * len(apart) <= same <= 0.28 * len(apart)


# -- the truth, from the payloads --


def test_a_statement_is_found_by_its_label_which_no_other_has(world):
    def labels(value):
        if isinstance(value, dict):
            if "label" in value and value.get("type") != "Factoid":
                yield value["label"]
            value = list(value.values())
        if isinstance(value, list):
            for inner in value:
                yield from labels(inner)

    added = [f for f in world.factoids if "source" in f]
    found = [label for factoid in added for label in labels(factoid["statements"])]
    assert sorted(found) == sorted(world.told)
    assert len(set(found)) == len(found)
    for label, told in world.told.items():
        assert world.statement(label)["label"] == label == told.label


def test_a_verdict_pairs_two_statements_and_says_where_they_are(world):
    source = {f["label"]: f["source"]["id"] for f in world.factoids if "source" in f}
    seen = set()
    for verdict in world.verdicts:
        a, b = world.told[verdict.a], world.told[verdict.b]
        assert verdict.relation == planted.RELATION_OF[verdict.case]
        assert a.case == b.case == verdict.case
        assert verdict.same_factoid == (a.factoid == b.factoid)
        assert verdict.same_source == (source[a.factoid] == source[b.factoid])
        assert (a.event != b.event) == (verdict.relation == "two")
        assert world.relation(verdict.a, verdict.b) == verdict.relation
        assert world.relation(verdict.b, verdict.a) == verdict.relation
        assert frozenset((verdict.a, verdict.b)) not in seen
        seen.add(frozenset((verdict.a, verdict.b)))
    # (two statements of one event are a pair of the truth; any other two are of two events)
    by_event = collections.defaultdict(list)
    for told in world.told.values():
        by_event[told.event].append(told.label)
    for labels in by_event.values():
        assert len(labels) <= 2
        if len(labels) == 2:
            assert frozenset(labels) in seen
    first, second = world.verdicts[0], world.verdicts[1]
    assert world.relation(first.a, second.b) == "two"
    with pytest.raises(KeyError):
        world.relation(first.a, "No such statement")


def test_two_that_disagree_differ_in_the_fields_said_and_in_nothing_else(large):
    for verdict in large.verdicts:
        if verdict.relation not in ("agree", "disagree"):
            continue
        a, b = large.statement(verdict.a), large.statement(verdict.b)
        if verdict.case.startswith("making"):
            # (the general class and the specific one: the field narrowed is the same field)
            assert (a["type"], b["type"]) == ("Making", "MakingOfPicture")
            b = {**b, "made": b["picture_made"]}
        else:
            assert a["type"] == b["type"]
        differing = {
            field
            for field in (set(a) | set(b)) - {"label", "type", "picture_made", "when"}
            if a.get(field) != b.get(field)
        }
        if "when" in verdict.fields:
            # (said to the day by both, and not the same day)
            assert day_of(a) != day_of(b)
            differing.add("when")
        if verdict.case in ("gathering_agree", "entered_twice"):
            # (the second names some of the people of the first, and no one else)
            assert all(p in a["participants"] for p in b["participants"])
            differing.discard("participants")
        assert differing == set(verdict.fields), verdict


def test_a_person_is_born_once_however_often_it_is_told(large):
    born = collections.Counter(
        large.statement(told.label)["person"]["id"]
        for told in large.told.values()
        if told.case.startswith("birth")
    )
    assert born and set(born.values()) == {2}


def test_what_came_of_an_order_is_by_the_one_ordered_and_after_it(large):
    seen = collections.Counter()
    for verdict in large.verdicts:
        thing, outcome = large.statement(verdict.a), large.statement(verdict.b)
        prescribed = large.told[verdict.a]
        if prescribed.order is None:
            continue
        seen[verdict.case] += 1
        order = large.statement(prescribed.order)
        space = order["thing_ordered"] if order["type"] == "Order" else order["ruled"]
        assert space["contents"] == [thing] and prescribed.spaces == (space["type"],)
        assert thing["given_by"] in (order.get("ordered_to") or order["binds"])
        assert (thing["given_by"], thing["given_to"]) == (outcome["given_by"], outcome["given_to"])  # fmt: skip
        if verdict.relation == "orders_at_odds":
            other = large.statement(large.told[verdict.b].order)
            assert (order["type"], other["type"]) == ("Order", "Rule")
            assert other["ruled"]["contents"] == [outcome]
            assert thing["given_to"] == other["ruled_by"]
            continue
        assert day_of(outcome) >= day_of(order)
        if verdict.relation in ("carried_out", "not_carried_out"):
            assert day_of(outcome) == day_of(thing)
        elif verdict.relation == "carried_out_otherwise":
            assert day_of(outcome) > day_of(thing) and verdict.fields == ("when",)
        else:
            assert "when" not in thing
        assert large.told[verdict.b].spaces == (("Negative",) if verdict.relation in ("not_carried_out", "complied") else ())  # fmt: skip
    assert set(seen) == {case for case in PAIRED if case.startswith(("order", "forbidden", "permission"))}  # fmt: skip


def test_what_is_said_not_to_be_so_has_its_liveness_and_nothing_else_has(large):
    denied = {t.label for t in large.told.values() if "Negative" in t.spaces}
    assert set(large.liveness) == denied
    members = collections.defaultdict(set)
    for factoid in large.factoids:
        for statement in factoid["statements"]:
            if statement["type"] == "MemberOf":
                members[statement["group"]["id"]].add(statement["member"]["id"])
    grounds = collections.Counter()
    for label, live in large.liveness.items():
        told, statement = large.told[label], large.statement(label)
        grounds[live.grounds] += 1
        if told.case.startswith("absence"):
            member = (
                statement["attended_by"]["id"]
                in members[statement["assembly_of"]["id"]]
            )
            assert (live.value, live.grounds) == ((1.0, "member") if member else (0.0, "none"))  # fmt: skip
            assert told.case == ("absence_expected" if member else "absence_unexpected")
        else:
            assert live.value == 1.0
            assert live.grounds == {"order_not": "ordered", "forbidden_kept": "forbidden"}.get(told.case, "reported")  # fmt: skip
    assert set(grounds) == {"reported", "ordered", "forbidden", "member", "none"}
    # (those present at an assembly are its members, and no one is both there and not)
    for factoid in large.factoids:
        if not factoid["label"].startswith("The roll"):
            continue
        there = [s["attended_by"]["id"] for s in factoid["statements"] if s["type"] == "Attendance"]  # fmt: skip
        away = [s["contents"][0]["attended_by"]["id"] for s in factoid["statements"] if s["type"] == "Negative"]  # fmt: skip
        [group] = {s["assembly_of"]["id"] for s in factoid["statements"] if s["type"] == "Attendance"}  # fmt: skip
        assert set(there) <= members[group] and not set(there) & set(away)
        assert len(set(there + away)) == len(there + away)


# -- the truth, on the models and by the walk --


def test_every_record_of_the_world_is_a_create_of_the_models(models, world):
    for record in world.records():
        getattr(models, record["type"]).Create(**record)


def paths(factoid) -> dict[str, list[dict]]:
    """The path of each statement of a factoid's payload, by its label: as it would be stored, a statement's label
    standing for its id"""
    found: dict[str, list[dict]] = {}

    def walk(node, path):
        if node["type"] in ("Negative", "Hypothetical", "Must", "Reported", "Believed", "Ordered", "Forbidden", "Permitted", "Obliged"):  # fmt: skip
            entry = {"kind": "space", "type": node["type"], "id": f"space {len(path)}", "field": "contents"}  # fmt: skip
            if node.get("how_likely"):
                entry["degree"] = node["how_likely"]
            for inner in node["contents"]:
                walk(inner, [*path, entry])
            return
        found[node["label"]] = path
        for field in ("thing_ordered", "ruled"):
            if field in node:
                walk(node[field], [*path, {"kind": "document", "type": node["type"], "id": node["label"], "field": field}])  # fmt: skip

    for statement in factoid["statements"]:
        walk(statement, [{"kind": "document", "type": "Factoid", "id": factoid["label"], "field": "statements"}])  # fmt: skip
    return found


def test_the_walk_reads_each_pair_as_the_truth_says(models, large):
    known = spaces.registered_spaces()
    by_label = {factoid["label"]: factoid for factoid in large.factoids}
    signatures = {}
    for factoid in {told.factoid for told in large.told.values()}:
        for label, path in paths(by_label[factoid]).items():
            signatures[label] = spaces.signature(path, known)
            assert [e["type"] for e in path if e["kind"] == "space"] == list(large.told[label].spaces)  # fmt: skip
    assert set(signatures) == set(large.told)

    for verdict in large.verdicts:
        a, b = signatures[verdict.a], signatures[verdict.b]
        said = (a.veridical, a.lean, b.veridical, b.lean)
        match verdict.relation:
            case "agree" | "disagree" | "two":
                assert said == (1, None, 1, None), verdict
            case "contradiction":
                assert said == (1, None, -1, None), verdict
            case "support":
                assert said == (1, None, 0, "for"), verdict
            case "tension":
                assert said == (1, None, 0, "against"), verdict
            case "compatible":
                assert said == (0, "for", 0, "for"), verdict
            case "at_odds":
                assert said == (0, "for", 0, "against"), verdict
            case "carried_out" | "carried_out_otherwise":
                assert said == (0, "for", 1, None), verdict
                assert (a.force, a.degree) == ("necessity", "expected")
            case "not_carried_out":
                assert said == (0, "for", -1, None), verdict
                assert a.force == "necessity"
            case "breach":
                assert said == (0, "against", 1, None), verdict
            case "complied":
                assert said == (0, "against", -1, None), verdict
            case "permission_used":
                assert said == (0, "for", 1, None), verdict
                assert a.force == "possibility"
            case "orders_at_odds":
                assert said == (0, "against", 0, "for"), verdict
                assert (a.flavour, b.flavour) == ("command", "statute")
                assert (b.fit, b.prescribed_by) == ("prescribes", large.told[verdict.b].order)  # fmt: skip
        if large.told[verdict.a].order is not None:
            assert (a.fit, a.prescribed_by) == ("prescribes", large.told[verdict.a].order)  # fmt: skip
            assert b.fit == "describes" or verdict.relation == "orders_at_odds"
        else:
            assert (a.fit, b.fit) == ("describes", "describes")

    # (a degree entered on a possibility is the statement's; with none entered there is none: the class has no default)
    entered = collections.Counter()
    for told in large.told.values():
        if told.case == "gathering_might":
            if told.spaces:
                [item] = by_label[told.factoid]["statements"]
                assert signatures[told.label].degree == item.get("how_likely")
                entered[item.get("how_likely")] += 1
    assert set(entered) == {None, "possible", "likely"}
    # (what is said not to be so is denied, or, inside what is only reported or believed, leant against)
    for label in large.liveness:
        assert (signatures[label].veridical, signatures[label].lean) in ((-1, None), (0, "against"))  # fmt: skip
