"""The verdict on two statements (`pangloss_compare.maths`; implementation_docs/spaces-and-comparison-plan.md, step
6.2): each row of the table of relations by a case written by hand, and a floor on the planted world for comparison
(`planted.world(compared=True)`). No database."""

import collections
import dataclasses
import datetime
import itertools
import typing

import pytest
from pangloss_compare import maths
from pangloss_compare.maths import Prescribed, Rules, Span, Told, verdict
from pangloss_core import BaseSettings, DatabaseSettings
from pangloss_models import ModelRegistry, spaces
from pangloss_models.spaces import Signature
from pangloss_testing import planted
from pangloss_testing.similar_models import declare
from pydantic import AnyHttpUrl, create_model

# -- statements written by hand --

RULES = {
    "Birth": Rules(("person",), once_per="person"),
    "Making": Rules(("made_by", "made"), once_per="made"),
    "MakingOfPicture": Rules(("made_by", "made"), once_per="made"),
    "Activity": Rules(("carried_out_by", "participants")),
    "Transfer": Rules(("given_by", "given_to"), recurs=True),
    "Going": Rules(("goer", "to")),
    "Attendance": Rules(("attended_by", "assembly_of")),
    "Order": Rules(("ordered_by", "ordered_to")),
    "Rule": Rules(("ruled_by", "binds")),
}


def said(veridical=1, lean=None, degree=None, fit="describes", force=None, flavour=None):  # fmt: skip
    return Signature(veridical, lean, degree, fit, None, force, flavour)


ASSERTED = said()
DENIED = said(-1)
REPORTED = said(0, "for", "likely")
REPORTED_NOT = said(0, "against", "likely")
MIGHT = said(0, "for", None, force="possibility", flavour="epistemic")
ORDERED = said(0, "for", "expected", "prescribes", "necessity", "command")
FORBIDDEN = said(0, "against", "expected", "prescribes", "necessity", "command")
PERMITTED = said(0, "for", None, "prescribes", "possibility", "command")
OBLIGED = said(0, "for", "likely", "prescribes", "necessity", "statute")


def day(year, month=None, number=None) -> Span:
    """A date said to the day, the month or the year"""
    first = datetime.date(year, month or 1, number or 1)
    if number:
        last = first
    elif month:
        last = datetime.date(year + (month == 12), month % 12 + 1, 1) - datetime.timedelta(days=1)  # fmt: skip
    else:
        last = datetime.date(year, 12, 31)
    return Span(first.toordinal(), last.toordinal())


COUNT = itertools.count()


def told(kind, signature=ASSERTED, when=None, head=None, source=None, prescribed=None, above=(), **fields):  # fmt: skip
    values = {
        name: frozenset([value] if isinstance(value, str) else value)
        for name, value in fields.items()
    }
    return Told(
        f"s{next(COUNT)}",
        (kind, *above),
        signature,
        values,
        {} if when is None else {"when": when},
        head,
        source,
        prescribed,
    )


MAY_DAY = day(1500, 5, 1)


def gathering(signature=ASSERTED, when=MAY_DAY, people=("b", "c"), **more):  # fmt: skip
    return told("Activity", signature, when, carried_out_by="a", participants=people, **more)  # fmt: skip


def relation(a, b) -> str:
    return verdict(a, b, RULES).relation


# -- one event or two --


def test_two_that_tell_the_same_agree_and_a_second_that_names_fewer_still_agrees():
    assert relation(gathering(), gathering()) == "agree"
    assert relation(gathering(), gathering(people=("b",), when=day(1500))) == "agree"


def test_a_field_told_otherwise_is_a_disagreement_on_that_field():
    found = verdict(gathering(), gathering(people=("b", "d")), RULES)
    assert (found.relation, found.fields) == ("disagree", ("participants",))
    assert found.how == {"participants": "different"}
    # (a field that is not identifying: the place)
    here = gathering(place="rome")
    found = verdict(here, gathering(place="venice"), RULES)
    assert (found.relation, found.fields) == ("disagree", ("place",))
    # (and one that says no place is silent on it)
    assert relation(here, gathering()) == "agree"


def test_dates_agree_where_they_overlap_and_disagree_beyond_both_uncertainties():
    assert relation(gathering(when=day(1500, 5, 1)), gathering(when=day(1500, 5))) == "agree"  # fmt: skip
    assert relation(gathering(when=day(1500)), gathering(when=day(1500, 5))) == "agree"
    found = verdict(gathering(when=day(1500, 5, 1)), gathering(when=day(1500, 5, 9)), RULES)  # fmt: skip
    assert (found.relation, found.fields) == ("disagree", ("when",))
    # (a year later is another gathering of the same people)
    assert relation(gathering(when=day(1500, 5, 1)), gathering(when=day(1501, 6, 1))) == "two"  # fmt: skip
    # (and with no date said by one, the date says nothing)
    assert relation(gathering(), gathering(when=None)) == "agree"


def test_no_identifying_entity_in_common_is_two_events():
    other = told("Activity", when=day(1500, 5, 1), carried_out_by="x", participants=("y",))  # fmt: skip
    assert relation(gathering(), other) == "two"


def test_once_per_the_same_entity_is_one_event_whatever_the_rest():
    born = told("Birth", when=day(1500, 5, 1), person="a", place="rome")
    again = told("Birth", when=day(1504, 1, 1), person="a", place="venice")
    found = verdict(born, again, RULES)
    assert (found.relation, found.likelihood) == ("disagree", 1.0)
    assert set(found.fields) == {"place", "when"}
    assert relation(born, told("Birth", when=day(1500, 5, 1), person="b", place="rome")) == "two"  # fmt: skip


def test_a_general_and_a_specific_class_are_compared_on_the_general_ones_fields():
    made = told("Making", made_by="a", made="thing")
    painted = told("MakingOfPicture", above=("Making",), made_by="a", made="thing")
    found = verdict(made, painted, RULES)
    assert (found.relation, found.common) == ("agree", "Making")
    by_another = told("MakingOfPicture", above=("Making",), made_by="b", made="thing")
    assert verdict(made, by_another, RULES).fields == ("made_by",)
    # (another thing by the same maker is another making)
    assert relation(made, told("Making", made_by="a", made="another")) == "two"


def test_classes_neither_of_which_is_above_the_other_are_not_compared():
    assert relation(told("Birth", person="a"), told("Attendance", attended_by="a")) == "nothing"  # fmt: skip
    # (nor is a class with no rules)
    assert relation(told("Naming", person="a"), told("Naming", person="a")) == "nothing"


def test_what_recurs_is_another_event_whenever_the_dates_are_apart():
    dues = told("Transfer", when=day(1500, 3, 1), given_by="a", given_to="guild")
    assert relation(dues, told("Transfer", when=day(1500, 3), given_by="a", given_to="guild")) == "agree"  # fmt: skip
    assert relation(dues, told("Transfer", when=day(1501, 3, 1), given_by="a", given_to="guild")) == "two"  # fmt: skip
    assert relation(dues, told("Transfer", when=day(1500, 3, 9), given_by="a", given_to="guild")) == "two"  # fmt: skip


def test_two_that_assert_in_one_factoid_are_less_likely_one_event():
    apart = verdict(gathering(head="f1"), gathering(head="f2"), RULES)
    together = verdict(gathering(head="f1"), gathering(head="f1"), RULES)
    assert together.likelihood < apart.likelihood
    assert (apart.within, together.within) == (None, "factoid")
    # (an assertion against a denial: neutral)
    denied = verdict(gathering(head="f1"), gathering(DENIED, head="f1"), RULES)
    assert denied.likelihood == pytest.approx(apart.likelihood)
    # (and other sources count for one event)
    sources = verdict(gathering(head="f1", source="x"), gathering(head="f2", source="y"), RULES)  # fmt: skip
    assert sources.likelihood > apart.likelihood


# -- the table: two that describe --


@pytest.mark.parametrize(
    ("first", "second", "expected"),
    [
        (ASSERTED, ASSERTED, "agree"),
        (DENIED, DENIED, "agree"),
        (ASSERTED, DENIED, "contradiction"),
        (ASSERTED, REPORTED, "support"),
        (ASSERTED, MIGHT, "support"),
        (ASSERTED, REPORTED_NOT, "tension"),
        (DENIED, REPORTED, "tension"),
        (DENIED, REPORTED_NOT, "support"),
        (REPORTED, MIGHT, "compatible"),
        (REPORTED_NOT, REPORTED_NOT, "compatible"),
        (REPORTED, REPORTED_NOT, "at_odds"),
        (said(0, "neither"), ASSERTED, "nothing"),
        (said(0, "neither"), DENIED, "nothing"),
    ],
)
def test_the_two_signatures_make_the_relation(first, second, expected):
    assert relation(gathering(first), gathering(second)) == expected
    assert relation(gathering(second), gathering(first)) == expected


def test_a_not_is_held_against_the_same_thing_only():
    met = gathering(when=day(1500, 5, 1))
    assert relation(met, gathering(DENIED, when=day(1500, 5, 9))) == "nothing"
    assert relation(met, gathering(DENIED, people=("b", "d"))) == "nothing"
    assert relation(met, gathering(REPORTED_NOT, people=("b", "d"))) == "nothing"
    # (what is reported with another detail still supports that it happened, and says the detail)
    found = verdict(met, gathering(REPORTED, people=("b", "d")), RULES)
    assert (found.relation, found.fields) == ("support", ("participants",))


def test_a_source_that_contradicts_itself_is_said_to():
    found = verdict(gathering(head="f1", source="x"), gathering(DENIED, head="f1", source="x"), RULES)  # fmt: skip
    assert (found.relation, found.within) == ("contradiction", "factoid")
    found = verdict(gathering(head="f1", source="x"), gathering(DENIED, head="f2", source="x"), RULES)  # fmt: skip
    assert (found.relation, found.within) == ("contradiction", "source")


# -- the table: what is prescribed and what came of it --

TUESDAY, WEDNESDAY = day(1500, 6, 2), day(1500, 6, 3)
BY_MAX = Prescribed(by=frozenset({"max"}), to=frozenset({"john"}), at=day(1500, 5, 20))


def going(signature=ASSERTED, when=TUESDAY, goer="john", prescribed=None, **more):
    return told("Going", signature, when, prescribed=prescribed, goer=goer, to="shops", **more)  # fmt: skip


def ordered(signature=ORDERED, when=TUESDAY, prescribed=BY_MAX, **more):
    return going(signature, when, prescribed=prescribed, **more)


def test_an_order_carried_out_and_a_day_late():
    """Maximilian orders John Smith to go to the shops on Tuesday; John Smith went on Tuesday, or on Wednesday"""
    order = ordered()
    found = verdict(order, going(), RULES)
    assert (found.relation, found.fields, found.reported) == ("carried_out", (), False)
    late = going(when=WEDNESDAY)
    found = verdict(order, late, RULES)
    assert (found.relation, found.fields) == ("carried_out_otherwise", ("when",))
    assert found.how == {"when": "late"}
    # (the prescription is first, whichever way the two are given)
    again = verdict(late, order, RULES)
    assert (again.relation, again.first, again.second) == ("carried_out_otherwise", order.id, late.id)  # fmt: skip
    early = verdict(order, going(when=day(1500, 5, 28)), RULES)
    assert early.how == {"when": "early"}
    # (with no date in the order, any going after it answers it)
    assert relation(ordered(when=None), going(when=day(1500, 9, 1))) == "carried_out"


def test_the_prescribed_details_are_targets():
    order = told("Going", ORDERED, TUESDAY, prescribed=BY_MAX, goer="john", to="shops", place="market", companions=("x", "y"))  # fmt: skip
    elsewhere = told("Going", when=TUESDAY, goer="john", to="shops", place="harbour")
    assert verdict(order, elsewhere, RULES).how == {"place": "different"}
    in_part = told("Going", when=TUESDAY, goer="john", to="shops", companions=("x",))
    assert verdict(order, in_part, RULES).how == {"companions": "in_part"}


def test_done_by_another_or_before_it_was_prescribed_is_done_but_not_carried_out():
    order = ordered()
    assert relation(order, going(goer="peter")) == "done_not_carried_out"
    assert relation(order, going(when=day(1500, 5, 1))) == "done_not_carried_out"
    # (another's going on another day is another going)
    assert relation(order, going(goer="peter", when=day(1500, 8, 1))) == "two"
    # (and another thing altogether is)
    assert relation(order, told("Going", when=TUESDAY, goer="john", to="church")) == "two"  # fmt: skip


def test_what_recurs_and_was_done_before_the_order_is_another_time():
    give = Prescribed(frozenset({"max"}), frozenset({"john"}), day(1500, 5, 20))
    order = told("Transfer", ORDERED, None, prescribed=give, given_by="john", given_to="guild")  # fmt: skip
    before = told("Transfer", when=day(1499, 1, 1), given_by="john", given_to="guild")
    assert relation(order, before) == "two"
    assert relation(order, told("Transfer", when=day(1500, 7, 1), given_by="john", given_to="guild")) == "carried_out"  # fmt: skip


def test_an_order_not_carried_out():
    found = verdict(ordered(), going(DENIED), RULES)
    assert found.relation == "not_carried_out"
    # (that another did not go says nothing of the order)
    assert relation(ordered(), going(DENIED, goer="peter")) == "nothing"


def test_an_order_not_to_is_breached_or_complied_with():
    forbidden = ordered(FORBIDDEN, when=None)
    assert relation(forbidden, going(when=day(1500, 7, 1))) == "breach"
    assert relation(forbidden, going(DENIED, when=day(1500, 7, 1))) == "complied"
    # (of the one it applied to, after it was forbidden)
    assert relation(forbidden, going(goer="peter", when=day(1500, 7, 1))) == "two"
    assert relation(forbidden, going(when=day(1500, 1, 1))) == "nothing"


def test_a_permission_is_used_never_carried_out_or_breached():
    allowed = ordered(PERMITTED, when=None)
    assert relation(allowed, going(when=day(1500, 7, 1))) == "permission_used"
    assert relation(allowed, going(DENIED)) == "nothing"
    # (allowed not to)
    may_not = ordered(said(0, "against", None, "prescribes", "possibility", "command"), when=None)  # fmt: skip
    assert relation(may_not, going(DENIED)) == "permission_used"
    assert relation(may_not, going(when=day(1500, 7, 1))) == "nothing"


def test_what_is_only_reported_of_a_prescription_has_its_relation_as_reported():
    found = verdict(ordered(), going(REPORTED), RULES)
    assert (found.relation, found.reported) == ("carried_out", True)
    found = verdict(ordered(), going(REPORTED_NOT), RULES)
    assert (found.relation, found.reported) == ("not_carried_out", True)
    found = verdict(ordered(FORBIDDEN, when=None), going(REPORTED, when=day(1500, 7, 1)), RULES)  # fmt: skip
    assert (found.relation, found.reported) == ("breach", True)


def test_an_orientation_before_is_answered_by_what_came_before():
    ratified = dataclasses.replace(BY_MAX, orientation="before")
    order = ordered(when=None, prescribed=ratified)
    assert relation(order, going(when=day(1500, 5, 1))) == "carried_out"
    assert relation(order, going(when=day(1500, 7, 1))) == "done_not_carried_out"


def test_when_it_was_prescribed_is_not_judged_where_a_date_is_missing():
    undated = dataclasses.replace(BY_MAX, at=None)
    assert relation(ordered(when=None, prescribed=undated), going(when=day(1400, 1, 1))) == "carried_out"  # fmt: skip
    assert relation(ordered(when=None), going(when=None)) == "carried_out"


# -- the table: two prescriptions --

BY_GUILD = Prescribed(by=frozenset({"guild"}), to=frozenset({"john"}))


def test_ordered_and_forbidden_by_one_authority_conflict():
    assert relation(ordered(when=None), ordered(FORBIDDEN, when=None)) == "conflict"
    # (obliged, and permitted not to)
    may_not = said(0, "against", None, "prescribes", "possibility", "command")
    assert relation(ordered(when=None), ordered(may_not, when=None)) == "conflict"
    # (permitted and forbidden)
    assert relation(ordered(PERMITTED, when=None), ordered(FORBIDDEN, when=None)) == "conflict"  # fmt: skip


def test_two_possibilities_never_conflict_and_two_that_point_one_way_are_compatible():
    may_not = said(0, "against", None, "prescribes", "possibility", "command")
    assert relation(ordered(PERMITTED, when=None), ordered(may_not, when=None)) == "compatible"  # fmt: skip
    assert relation(ordered(when=None), ordered(PERMITTED, when=None)) == "compatible"
    assert relation(ordered(when=None), ordered(OBLIGED, when=None, prescribed=BY_GUILD)) == "compatible"  # fmt: skip


def test_another_flavour_or_another_authority_is_two_orders_at_odds():
    statute = ordered(OBLIGED, when=None, prescribed=BY_GUILD)
    assert relation(ordered(FORBIDDEN, when=None), statute) == "orders_at_odds"
    # (the same flavour, another authority)
    other = ordered(when=None, prescribed=BY_GUILD)
    assert relation(ordered(FORBIDDEN, when=None), other) == "orders_at_odds"
    # (the same authority, another flavour)
    assert relation(ordered(FORBIDDEN, when=None), ordered(OBLIGED, when=None)) == "orders_at_odds"  # fmt: skip
    # (of another thing: nothing to do with each other)
    church = told("Going", OBLIGED, prescribed=BY_GUILD, goer="john", to="church")
    assert relation(ordered(FORBIDDEN, when=None), church) == "two"


# -- the degree weighs --


def test_the_strength_is_the_likelihood_times_how_far_each_side_commits():
    both = verdict(gathering(), gathering(), RULES)
    assert both.strength == pytest.approx(both.likelihood)
    reported = verdict(gathering(), gathering(REPORTED), RULES)
    assert reported.strength == pytest.approx(reported.likelihood * maths.DEGREES["likely"])  # fmt: skip
    # (no degree said: the middle)
    might = verdict(gathering(), gathering(MIGHT), RULES)
    assert might.strength == pytest.approx(might.likelihood * maths.DEGREES[None])
    assert verdict(gathering(), told("Birth", person="a"), RULES).strength == 0.0


def test_a_failure_to_carry_out_is_the_more_notable_the_higher_the_orders_degree():
    weak = said(0, "for", "possible", "prescribes", "necessity", "command")
    strong = verdict(ordered(), going(DENIED), RULES).strength
    assert strong > verdict(ordered(weak), going(DENIED), RULES).strength > 0


def test_an_order_supports_a_report_that_it_happened_until_a_statement_tells():
    order = ordered()
    reported = verdict(order, going(REPORTED), RULES)
    assert reported.strength > 0
    [alone] = maths.settled([reported])
    assert not alone.superseded
    # (once another statement tells what happened, it decides)
    told_so = verdict(order, going(DENIED), RULES)
    first, second = maths.settled([reported, told_so])
    assert (first.superseded, second.superseded) == (True, False)
    # (of that prescription only)
    other = verdict(ordered(), going(REPORTED), RULES)
    assert not maths.settled([other, told_so])[0].superseded


# -- the parts --


def test_entities_compare_as_same_partly_different_or_silent():
    f = frozenset
    assert maths.compare_entities(f("a"), f("a")) == "same"
    assert maths.compare_entities(f("ab"), f("a")) == "same"
    assert maths.compare_entities(f("ab"), f("ac")) == "partly"
    assert maths.compare_entities(f("a"), f("b")) == "different"
    assert maths.compare_entities(f(), f("b")) == "silent"


def test_the_gap_is_beyond_both_uncertainties_and_signed():
    assert maths.gap(Span(10, 20), Span(15, 30)) == 0
    assert maths.gap(Span(10, 20), Span(12, 14)) == 0
    assert maths.gap(Span(10, 20), Span(25, 30)) == 5
    assert maths.gap(Span(25, 30), Span(10, 20)) == -5


def test_a_span_is_a_dates_widest_bounds():
    from pangloss_dates.bounds import Bounds

    assert Span.of(Bounds(1, 3, 7, 9)) == Span(1, 9)


def test_given_weights_take_the_place_of_the_hand_set_ones():
    a, b = gathering(), gathering()
    assert verdict(a, b, RULES, {"bias": -5.0}).relation == "two"
    assert set(maths.features(a, b, maths.compare_fields(a, b, RULES["Activity"]), RULES["Activity"])) == set(maths.WEIGHTS)  # fmt: skip


def test_every_relation_given_is_one_of_the_table():
    cases = [ASSERTED, DENIED, REPORTED, REPORTED_NOT, ORDERED, FORBIDDEN, PERMITTED, OBLIGED]  # fmt: skip
    seen = set()
    for first, second in itertools.product(cases, repeat=2):
        for when in (TUESDAY, WEDNESDAY, day(1500, 1, 1)):
            for goer in ("john", "peter"):
                a = going(first, prescribed=BY_MAX if first.fit == "prescribes" else None)  # fmt: skip
                b = going(second, when, goer, prescribed=BY_GUILD if second.fit == "prescribes" else None)  # fmt: skip
                seen.add(verdict(a, b, RULES).relation)
    assert seen <= set(maths.RELATIONS)
    assert seen >= set(maths.RELATIONS) - {"agree", "disagree", "contradiction", "support", "tension", "at_odds"} - {"conflict"}  # fmt: skip


# -- the planted world --


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


ABOVE = {"MakingOfPicture": ("MakingOfPicture", "Making")}
NARROWS = {"picture_made": "made"}
SPACES = ("Negative", "Hypothetical", "Must", "Reported", "Believed", "Ordered", "Forbidden", "Permitted", "Obliged")  # fmt: skip
# The field that holds a space, and those its `Attribution` names
HOLDS = {
    "Order": ("thing_ordered", "ordered_by", "ordered_to"),
    "Rule": ("ruled", "ruled_by", "binds"),
}


def span(date) -> Span:
    if date["type"] == "DateRange":
        return Span(span(date["not_before"]).earliest, span(date["not_after"]).latest)
    return day(date["year"], date.get("month"), date.get("day"))


def entities(value):
    """The entities a field's value names: through wrappers, less a wrapper's own relation (`InRole.at`)"""
    if isinstance(value, dict):
        if set(value) == {"type", "id"}:
            yield value["id"]
        else:
            for key, inner in value.items():
                if key != "at":
                    yield from entities(inner)
    elif isinstance(value, list):
        for inner in value:
            yield from entities(inner)


def statements_of(world) -> tuple[list[Told], dict[str, str]]:
    """Every statement of the world of a compared class, as the verdict reads one, and the event each tells of: a
    statement added for comparison by its label, any other by its factoid's"""
    known, grounds = spaces.registered_spaces(), spaces.registered_grounds()
    reports = {label: event for event, labels in world.events.items() for label in labels}  # fmt: skip
    found: list[Told] = []
    event_of: dict[str, str] = {}

    def walk(factoid, node, path, holder=None):
        if node["type"] in SPACES:
            entry = {"kind": "space", "type": node["type"], "id": f"space {len(path)}", "field": "contents"}  # fmt: skip
            if node.get("how_likely"):
                entry["degree"] = node["how_likely"]
            for inner in node["contents"]:
                walk(factoid, inner, [*path, entry], holder)
            return
        kind = node["type"]
        if kind in RULES:
            holding = HOLDS.get(kind, ("",))[0]
            fields = {
                NARROWS.get(key, key): frozenset(entities(value))
                for key, value in node.items()
                if key not in ("type", "label", "when", holding)
            }
            signature = spaces.signature(path, known, grounds)
            prescribed = None
            if signature.fit == "prescribes" and holder is not None:
                _, by, to = HOLDS[holder["type"]]
                prescribed = Prescribed(
                    frozenset(entities(holder[by])),
                    frozenset(entities(holder[to])),
                    span(holder["when"]) if "when" in holder else None,
                )
            label = node["label"]
            id = label if label in world.told else f"{factoid['label']} / {len(found)}"
            found.append(
                Told(
                    id,
                    ABOVE.get(kind, (kind,)),
                    signature,
                    {name: value for name, value in fields.items() if value},
                    {"when": span(node["when"])} if "when" in node else {},
                    factoid["label"],
                    factoid.get("source", {}).get("id"),
                    prescribed,
                )
            )
            event_of[id] = (
                world.told[label].event
                if label in world.told
                else reports.get(factoid["label"], id)
            )
        for field in ("thing_ordered", "ruled"):
            if field in node:
                walk(factoid, node[field], [*path, {"kind": "document", "type": kind, "id": node["label"], "field": field}], node)  # fmt: skip

    for factoid in world.factoids:
        for statement in factoid["statements"]:
            if statement["type"] != "SameEntity":
                walk(factoid, statement, [{"kind": "document", "type": "Factoid", "id": factoid["label"], "field": "statements"}])  # fmt: skip
    return found, event_of


def pairs_by_rule(statements: list[Told]):
    """The pairs step 6.3 gives: statements of related classes that name one entity in the same identifying field"""
    naming = collections.defaultdict(list)
    for number, statement in enumerate(statements):
        for field in RULES[statement.type].identifying:
            for entity in statement.fields.get(field, ()):
                naming[(field, entity)].append(number)
    seen = set()
    for numbers in naming.values():
        for pair in itertools.combinations(numbers, 2):
            a, b = statements[pair[0]], statements[pair[1]]
            if pair not in seen and maths.common_class(a, b):
                seen.add(pair)
                yield a, b


def test_the_verdict_on_the_planted_world(models):
    """Measured 2026-11-27 at 5,000 people on seeds 1 to 3: of the planted pairs 99.87 to 99.96% have the truth's
    relation and fields; of all pairs by rule (71,000 to 74,000) 99.66 to 99.78% are rightly one event or two. The
    world cannot be read right every time: a gift by the one ordered to the one named, told elsewhere, answers the
    order as far as the data says; two gatherings of the same people within one year said only by the year are
    one as far as it says"""
    from pangloss_compare.meta import compared_classes

    # (the rules written here by hand are the models' own)
    declared = {
        name: Rules(tuple(meta.identifying), meta.once_per, meta.recurs)
        for name, meta in compared_classes().items()
    }
    assert declared == {name: rules for name, rules in RULES.items() if name != "Going"}  # fmt: skip
    world = planted.world(seed=2, people=2000, compared=True)
    statements, event_of = statements_of(world)
    truth = {frozenset((v.a, v.b)): v for v in world.verdicts}
    assert len(statements) > 5000

    planted_right, others_right, others = collections.Counter(), 0, 0
    cases = collections.Counter()
    for a, b in pairs_by_rule(statements):
        found = verdict(a, b, RULES)
        said_so = truth.get(frozenset((a.id, b.id)))
        if said_so is not None:
            cases[said_so.case] += 1
            if found.relation == said_so.relation and sorted(found.fields) == sorted(said_so.fields):  # fmt: skip
                planted_right[said_so.case] += 1
                # (the prescription first, as the truth has it; within one factoid or source as it says)
                if found.relation in maths.ANSWERS:
                    assert (found.first, found.second) == (said_so.a, said_so.b)
                assert (found.within == "factoid") == said_so.same_factoid
                assert (found.within is not None) == said_so.same_source
        else:
            others += 1
            others_right += found.one_event == (event_of[a.id] == event_of[b.id])
    # (every planted pair is a pair by rule)
    assert sum(cases.values()) == len(world.verdicts)
    assert sum(planted_right.values()) / len(world.verdicts) > 0.99
    for case, count in cases.items():
        floor = 0.85 if case == "entered_twice" else 0.95
        assert planted_right[case] / count >= floor, case
    assert others > 20_000
    assert others_right / others > 0.99
