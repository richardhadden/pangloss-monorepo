"""The pairs through near entities, the parts with no database in them (`pangloss_compare.near`, `compare.near_entries`,
the settings `COMPARE_PROFILE`, `COMPARE_NEAR_K`, `COMPARE_NEAR`; implementation_docs/spaces-and-comparison-plan.md,
step 6.4): each refusal by its message, the other read with X' as X, `two` and `nothing` not given, a statement
reached through two entities, the cut."""

import dataclasses
from types import SimpleNamespace

import pytest
from pangloss_compare import near, settings
from pangloss_compare.compare import Named, near_entries
from pangloss_compare.judgements import Judgement
from pangloss_compare.maths import Prescribed, Verdict
from pangloss_compare.near import NearPair, Through
from pangloss_models.exceptions import PanglossInitialisationError

from test_compare_maths import ORDERED, RULES, day, told

# (the apps `pangloss_testing.similar_models` is declared with, as `conftest.APPS`)
APPS = ["pangloss_derived", "pangloss_library", "pangloss_criteria"]


def given(**values) -> SimpleNamespace:
    """Settings as plain values (a settings object, once made, is the process's)"""
    return SimpleNamespace(INSTALLED_APPS=values.pop("INSTALLED_APPS", APPS), **values)


# ---------------------------------------------------------------------------
# The settings
# ---------------------------------------------------------------------------


def test_the_settings_default_to_no_profile_five_and_six_tenths():
    assert settings.near_profile(given()) is None
    assert settings.near_k(given()) == 5
    assert settings.near_floor(given()) == 0.6
    # (and with vectors installed, but no reconciliation: still no profile)
    assert settings.near_profile(given(INSTALLED_APPS=[*APPS, "pangloss_vectors"])) is None  # fmt: skip


@pytest.mark.parametrize("value", [0, -1, True, 2.5, "5", None])
def test_compare_near_k_is_a_whole_number_of_one_or_more(value):
    with pytest.raises(PanglossInitialisationError, match="COMPARE_NEAR_K is a whole number of 1 or more"):  # fmt: skip
        settings.near_k(given(COMPARE_NEAR_K=value))


@pytest.mark.parametrize("value", [-0.1, 1.5, True, "0.6", None])
def test_compare_near_is_a_number_from_0_to_1(value):
    with pytest.raises(PanglossInitialisationError, match="COMPARE_NEAR is a number from 0 to 1"):  # fmt: skip
        settings.near_floor(given(COMPARE_NEAR=value))
    assert settings.near_floor(given(COMPARE_NEAR=1)) == 1.0
    assert settings.near_floor(given(COMPARE_NEAR=0)) == 0.0


def test_compare_profile_is_text():
    with pytest.raises(PanglossInitialisationError, match="COMPARE_PROFILE is the name of a profile"):  # fmt: skip
        settings.near_profile(given(COMPARE_PROFILE=3))


def test_compare_profile_is_refused_without_pangloss_vectors():
    with pytest.raises(
        PanglossInitialisationError,
        match="COMPARE_PROFILE names 'who', but pangloss_vectors is not installed",
    ):
        settings.near_profile(given(COMPARE_PROFILE="who"))


def test_compare_profile_names_a_profile_of_vectors_profiles():
    import pangloss_vectors  # noqa: F401  (the class part registered)

    with_vectors = [*APPS, "pangloss_vectors"]
    with pytest.raises(
        PanglossInitialisationError,
        match=r"COMPARE_PROFILE names 'who', which is not a profile: the profiles are default, kinds \(VECTORS_PROFILES\)",
    ):
        settings.near_profile(
            given(
                INSTALLED_APPS=with_vectors,
                VECTORS_PROFILES={"kinds": {"class": 1}},
                COMPARE_PROFILE="who",
            )
        )
    import pangloss_names  # noqa: F401  (the name part registered)

    named = given(
        INSTALLED_APPS=[*with_vectors, "pangloss_names"],
        VECTORS_PROFILES={"who": {"name": 1, "class": 0.25}},
        COMPARE_PROFILE="who",
    )
    assert settings.near_profile(named) == "who"


def test_compare_profile_weighs_a_part_that_knows_names():
    """Near entities are those that may be one another: a profile of the classes alone, or of a name part at weight
    0, is refused; the part is told by its class, whatever it is called"""
    import pangloss_names  # noqa: F401  (the name part registered)

    with_vectors = [*APPS, "pangloss_vectors", "pangloss_names"]
    assert settings.name_parts() == ["name"]
    for weights in ({"class": 1}, {"class": 1, "name": 0}):
        with pytest.raises(
            PanglossInitialisationError,
            match=r"COMPARE_PROFILE names 'kinds', which weighs no part that knows names \(name\)",
        ):
            settings.near_profile(
                given(
                    INSTALLED_APPS=with_vectors,
                    VECTORS_PROFILES={"kinds": weights},
                    COMPARE_PROFILE="kinds",
                )  # fmt: skip
            )


def test_without_compare_profile_reconciliation_s_choice_is_taken(monkeypatch):
    import pangloss_names  # noqa: F401  (the name part registered)
    from pangloss_reconcile import settings as reconcile_settings

    asked = []

    def chosen(settings_given):
        asked.append(settings_given)
        return "who"

    monkeypatch.setattr(reconcile_settings, "profile", chosen)
    with_both = given(
        INSTALLED_APPS=[*APPS, "pangloss_vectors", "pangloss_reconcile"],
        VECTORS_PROFILES={"who": {"name": 1}, "kinds": {"class": 1}},
    )
    assert settings.near_profile(with_both) == "who"
    assert asked == [with_both]
    # (reconciliation's choice that weighs no part of names is no refusal: no profile, no pairs through near entities)
    monkeypatch.setattr(reconcile_settings, "profile", lambda settings_given: "kinds")
    assert settings.near_profile(with_both) is None
    # (nor where no part of names is registered at all, `pangloss_names` not installed: the project starts, at
    # `initialise()` too)
    monkeypatch.setattr(reconcile_settings, "profile", chosen)
    monkeypatch.setattr(settings, "name_parts", lambda: [])
    assert settings.near_profile(with_both) is None
    import pangloss_core.settings as core_settings

    monkeypatch.setattr(core_settings, "SETTINGS", given(INSTALLED_APPS=[*with_both.INSTALLED_APPS, "pangloss_compare"], VECTORS_PROFILES=with_both.VECTORS_PROFILES), raising=False)  # fmt: skip
    settings.check()
    # (but COMPARE_PROFILE set to it is refused)
    with pytest.raises(PanglossInitialisationError, match="COMPARE_PROFILE names 'who', which weighs no part that knows names"):  # fmt: skip
        settings.near_profile(given(INSTALLED_APPS=with_both.INSTALLED_APPS, VECTORS_PROFILES=with_both.VECTORS_PROFILES, COMPARE_PROFILE="who"))  # fmt: skip
    monkeypatch.undo()
    monkeypatch.setattr(reconcile_settings, "profile", chosen)
    # (reconciliation installed, vectors not: none, and reconciliation is not asked, nor any part)
    assert settings.near_profile(given(INSTALLED_APPS=[*APPS, "pangloss_reconcile"])) is None  # fmt: skip
    assert len(asked) == 3


@pytest.mark.parametrize("value", [-0.5, True, "1", None, float("inf"), float("nan")])
def test_compare_learn_margin_is_a_number_of_0_or_more(value):
    with pytest.raises(PanglossInitialisationError, match="COMPARE_LEARN_MARGIN is a number of 0 or more"):  # fmt: skip
        settings.learn_margin(given(COMPARE_LEARN_MARGIN=value))
    assert settings.learn_margin(given()) == 1.0
    assert settings.learn_margin(given(COMPARE_LEARN_MARGIN=0)) == 0.0
    assert settings.learn_margin(given(COMPARE_LEARN_MARGIN=2.5)) == 2.5


def test_the_settings_are_checked_at_initialise(monkeypatch):
    import pangloss_core.settings as core_settings

    installed = [*APPS, "pangloss_compare"]
    for name, value, message in [
        ("COMPARE_NEAR_K", 0, "COMPARE_NEAR_K"),
        ("COMPARE_NEAR", 2, "COMPARE_NEAR is"),
        ("COMPARE_LEARN_MARGIN", -1, "COMPARE_LEARN_MARGIN"),
        ("COMPARE_PROFILE", "who", "pangloss_vectors is not installed"),
    ]:
        monkeypatch.setattr(core_settings, "SETTINGS", given(INSTALLED_APPS=installed, **{name: value}), raising=False)  # fmt: skip
        with pytest.raises(PanglossInitialisationError, match=message):
            settings.check()
    monkeypatch.setattr(core_settings, "SETTINGS", given(INSTALLED_APPS=installed), raising=False)  # fmt: skip
    settings.check()
    # (not installed: not checked)
    monkeypatch.setattr(core_settings, "SETTINGS", given(COMPARE_NEAR_K=0), raising=False)  # fmt: skip
    settings.check()


# ---------------------------------------------------------------------------
# The other read with X' as X
# ---------------------------------------------------------------------------


def test_the_other_is_read_with_each_near_entity_as_the_one_it_is_near():
    other = told(
        "Transfer",
        given_by=["ada2"],
        given_to=["ben2", "cy"],
        prescribed=Prescribed(by=frozenset({"ada2"}), to=frozenset({"ben2", "dee"})),
    )
    pair = NearPair(
        other.id,
        (
            Through("given_by", "ada", "ada2", 0.9),
            Through("given_to", "ben", "ben2", 0.8),
        ),
    )
    read = near.substituted(other, pair)
    assert read.fields == {
        "given_by": frozenset({"ada"}),
        "given_to": frozenset({"ben", "cy"}),
    }
    assert read.prescribed == Prescribed(by=frozenset({"ada"}), to=frozenset({"ben", "dee"}))  # fmt: skip
    # (nothing else changes, and the other itself is not changed)
    assert dataclasses.replace(read, fields=other.fields, prescribed=other.prescribed) == other  # fmt: skip
    assert other.fields["given_by"] == frozenset({"ada2"})


def test_an_entity_near_two_is_read_as_the_nearer():
    other = told("Birth", person=["ada2"])
    pair = NearPair(
        other.id,
        (Through("person", "ada", "ada2", 0.9), Through("person", "eda", "ada2", 0.7)),
    )
    assert near.substituted(other, pair).fields == {"person": frozenset({"ada"})}


# ---------------------------------------------------------------------------
# Which pairs, in what order
# ---------------------------------------------------------------------------


def test_a_statement_reached_through_two_entities_is_one_pair_with_both_reasons():
    found, more = near.candidates(
        {
            "s1": {("carried_out_by", "ada2"), ("participants", "ben2")},
            "s2": {("participants", "ben2")},
        },
        {
            "carried_out_by": {"ada2": (("ada", 0.7),)},
            "participants": {"ben2": (("ben", 0.9),)},
        },
        own="s0",
        by_rule=[],
        most=10,
    )
    assert not more
    assert found == [
        NearPair(
            "s1",
            (
                Through("participants", "ben", "ben2", 0.9),
                Through("carried_out_by", "ada", "ada2", 0.7),
            ),
        ),  # fmt: skip
        NearPair("s2", (Through("participants", "ben", "ben2", 0.9),)),
    ]


def test_the_statement_itself_and_the_pairs_by_rule_are_left_out_and_the_rest_cut_nearest_first():
    near_ben = {"participants": {"b2": (("b", 0.7),), "b3": (("b", 0.9),), "b4": (("b", 0.7),)}}  # fmt: skip
    named = {
        "own": {("participants", "b2")},
        "ruled": {("participants", "b3")},
        "z": {("participants", "b2")},
        "y": {("participants", "b4")},
        "x": {("participants", "b3")},
    }
    found, more = near.candidates(named, near_ben, own="own", by_rule=["ruled"], most=2)  # fmt: skip
    # (one of each near entity in turn, the nearest first: b3's, then b2's, then b4's; of two as near, by id)
    assert [p.id for p in found] == ["x", "z"]
    assert more
    found, more = near.candidates(named, near_ben, own="own", by_rule=["ruled"], most=3)  # fmt: skip
    assert [p.id for p in found] == ["x", "y", "z"] and not more
    # (a statement naming an entity in a field it was not found for is no pair)
    assert near.candidates({"w": {("carried_out_by", "b2")}}, near_ben, own="own", by_rule=[], most=5) == ([], False)  # fmt: skip


def test_the_places_are_shared_among_the_near_entities_in_turn_across_fields():
    """A namesake nearer than the right one, named in many statements, does not take every place: one statement of
    each near entity, the nearest first, then the second of each; across the identifying fields too"""
    searched = {
        "carried_out_by": {"namesake": (("ada", 0.9),), "right": (("ada", 0.7),)},
        "participants": {"ben2": (("ben", 0.8),)},
    }
    named = {
        **{f"n{k}": {("carried_out_by", "namesake")} for k in range(1, 6)},
        "r1": {("carried_out_by", "right")},
        "r2": {("carried_out_by", "right")},
        "b1": {("participants", "ben2")},
        # (one reached through both: one place, one pair with both reasons)
        "nb": {("carried_out_by", "namesake"), ("participants", "ben2")},
    }
    found, more = near.candidates(named, searched, own="own", by_rule=[], most=4)
    # (the first turn: the namesake's first (n1), ben2's first (b1), the right one's first (r1); then the second turn)
    assert {p.id for p in found} == {"n1", "b1", "r1", "n2"} and more
    assert [p.id for p in found] == ["n1", "n2", "b1", "r1"]
    found, more = near.candidates(named, searched, own="own", by_rule=[], most=6)
    # (the second turn: n2, then ben2's second (nb), then r2)
    assert {p.id for p in found} == {"n1", "b1", "r1", "n2", "nb", "r2"} and more
    (both,) = [p for p in found if p.id == "nb"]
    assert [t.near for t in both.by] == ["namesake", "ben2"]
    found, more = near.candidates(named, searched, own="own", by_rule=[], most=100)
    assert len(found) == 9 and not more


def test_a_source_that_is_an_x_prime_the_pair_is_found_through_is_read_as_x():
    """Two accounts each by the one who did it: Ada's own (her source Ada) and her namesake's (source Ada2), found
    through Ada2 as the doer. With Ada2 read as Ada in the source too, the sources do not differ, and the two are
    within one source"""
    from pangloss_compare import maths

    statement = dataclasses.replace(told("Activity", carried_out_by=["ada"], participants=["ben"]), source="ada")  # fmt: skip
    other = dataclasses.replace(told("Activity", carried_out_by=["ada2"], participants=["ben"]), source="ada2")  # fmt: skip
    pair = NearPair(other.id, (Through("carried_out_by", "ada", "ada2", 0.9),))
    assert near.not_both(statement, other, pair) == pair
    read = near.substituted(other, pair)
    assert read.source == "ada" and read.fields["carried_out_by"] == frozenset({"ada"})
    rules = RULES["Activity"]
    plain = maths.features(statement, other, maths.compare_fields(statement, other, rules), rules)  # fmt: skip
    assert plain["sources_differ"] == 1.0
    assert maths.features(statement, read, maths.compare_fields(statement, read, rules), rules)["sources_differ"] == 0.0  # fmt: skip
    assert (
        maths.verdict(
            near.substituted(statement, pair, source_only=True), read, RULES
        ).within
        == "source"
    )
    # (of the statement asked about, the source only: its fields are as they are)
    assert near.substituted(statement, pair, source_only=True) == statement


def test_no_pair_through_an_x_prime_a_statement_names_beside_x():
    """A statement naming both X and X' is the best sign they are two: S, Ada gives to her namesake; O, the namesake
    gives to Ada. Through Ada2 (as giver) O would read "Ada gives to Ada": no pair. A pair reached also through
    another entity is still given through that one"""
    gift = told("Transfer", given_by=["ada"], given_to=["ada2"])
    back = told("Transfer", given_by=["ada2"], given_to=["ada"])
    through_ada2 = Through("given_by", "ada", "ada2", 0.9)
    assert near.not_both(gift, back, NearPair(back.id, (through_ada2,))) is None
    entries = near_entries(gift, [NearPair(back.id, (through_ada2,))], {back.id: back}, RULES, None, {}, named(gift, back))  # fmt: skip
    assert entries == []
    # (a gift reached through Ada2 and through Ben2; the other names Ben beside Ben2: only Ada2 is left)
    met = told("Transfer", given_by=["ada"], given_to=["ben"])
    other = told("Transfer", given_by=["ada2"], given_to=["ben2", "ben"])
    both = NearPair(
        other.id,
        (
            Through("given_by", "ada", "ada2", 0.9),
            Through("given_to", "ben", "ben2", 0.8),
        ),  # fmt: skip
    )
    assert near.not_both(met, other, both) == NearPair(other.id, (both.by[0],))
    (entry,) = near_entries(met, [both], {other.id: other}, RULES, None, {}, named(met, other))  # fmt: skip
    assert [r["near"]["id"] for r in entry.as_json()["by"]] == ["ada2"]
    assert entry.verdict.relation == "agree"
    # (and the source counts as named: an other whose source is X)
    sourced = dataclasses.replace(told("Transfer", given_by=["ada2"], given_to=["ben"]), source="ada")  # fmt: skip
    assert near.not_both(met, sourced, NearPair(sourced.id, (both.by[0],))) is None


def test_only_a_relation_that_is_neither_two_nor_nothing_is_shown():
    for relation, shown in [("agree", True), ("disagree", True), ("carried_out", True), ("two", False), ("nothing", False)]:  # fmt: skip
        assert near.shown(Verdict(relation, "a", "b")) is shown, relation


def named(*told_) -> dict[str, Named]:
    return {t.id: Named(t.id, t.type, f"label of {t.id}") for t in told_}


def test_a_birth_of_a_namesake_told_otherwise_disagrees_and_a_gathering_far_apart_is_not_given():
    """Once per person stays certain: with Ada's namesake read as Ada, a birth a century later is one birth told
    otherwise; a gathering of hers a century later is another gathering"""
    birth = told("Birth", when=day(1500), person=["ada"], place=["mill"])
    other_birth = told("Birth", when=day(1600), person=["ada2"], place=["rome"])
    gathering = told("Activity", when=day(1500, 5, 1), carried_out_by=["ada"], participants=["ben"])  # fmt: skip
    far = told("Activity", when=day(1600, 5, 1), carried_out_by=["ada2"], participants=["cy"])  # fmt: skip
    entities = {
        "ada": Named("ada", "Person", "Ada"),
        "ada2": Named("ada2", "Person", "Ada"),
    }

    (entry,) = near_entries(
        birth,
        [NearPair(other_birth.id, (Through("person", "ada", "ada2", 0.83),))],
        {other_birth.id: other_birth},
        RULES,
        None,
        {},
        {**named(birth, other_birth), **entities},
    )
    assert entry.verdict.relation == "disagree"
    assert set(entry.verdict.fields) == {"when", "place"}
    answer = entry.as_json()
    assert answer["found"] == "near" and answer["superseded"] is False
    assert answer["by"] == [
        {
            "field": "person",
            "kind": "near",
            "entity": {"id": "ada", "type": "Person", "label": "Ada"},
            "near": {"id": "ada2", "type": "Person", "label": "Ada"},
            "score": 0.83,
        }
    ]

    assert (
        near_entries(
            gathering,
            [NearPair(far.id, (Through("carried_out_by", "ada", "ada2", 0.83),))],
            {far.id: far},
            RULES,
            None,
            {},
            {**named(gathering, far), **entities},
        )
        == []
    )


def test_a_person_s_judgement_overrides_a_near_pair_as_a_rule_pair():
    import datetime

    birth = told("Birth", when=day(1500), person=["ada"])
    other = told("Birth", when=day(1500), person=["ada2"])
    judged = Judgement(
        id="j",
        type="StatementJudgement",
        verdict="two_events",
        fields=(),
        note="",
        created_by=({"username": "ann"},),
        created_when=datetime.datetime(2026, 11, 27, tzinfo=datetime.UTC),
        changed_since_cited=False,
    )
    (entry,) = near_entries(
        birth,
        [NearPair(other.id, (Through("person", "ada", "ada2", 0.9),))],
        {other.id: other},
        RULES,
        None,
        {other.id: [judged]},
        named(birth, other),
    )
    answer = entry.as_json()
    assert answer["relation"] == "two" and answer["judged"] == "two_events"
    assert answer["workedOut"]["relation"] == "agree"


def test_what_answers_an_order_given_to_a_namesake_is_read_with_the_namesake_as_the_one_ordered():
    """An order to Ada's namesake, and Ada's giving: read with the namesake as Ada, carried out"""
    ordered = told(
        "Transfer",
        ORDERED,
        when=day(1500, 5, 2),
        given_by=["ada2"],
        given_to=["ben"],
        prescribed=Prescribed(
            by=frozenset({"max"}), to=frozenset({"ada2"}), at=day(1500, 5, 1)
        ),  # fmt: skip
    )
    gave = told("Transfer", when=day(1500, 5, 2), given_by=["ada"], given_to=["ben"])
    (entry,) = near_entries(
        gave,
        [NearPair(ordered.id, (Through("given_by", "ada", "ada2", 0.9),))],
        {ordered.id: ordered},
        RULES,
        None,
        {},
        named(gave, ordered),
    )
    assert entry.verdict.relation == "carried_out"
    assert entry.verdict.first == ordered.id
