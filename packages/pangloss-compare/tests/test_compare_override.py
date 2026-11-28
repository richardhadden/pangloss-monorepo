"""A person's judgement over what is worked out, and the order of a statement's pairs (`pangloss_compare.compare`,
`judgements.newest_first`; implementation_docs/spaces-and-comparison-plan.md, step 6.5). No database."""

import datetime

from pangloss_compare.compare import (
    Entry,
    Named,
    Said,
    order_key,
    settle,
    overridden,
    worked_out,
)
from pangloss_compare.judgements import Judgement, newest_first
from pangloss_compare.maths import Verdict
from pangloss_compare.pairs import Pair

WHEN = datetime.datetime(2026, 11, 27, tzinfo=datetime.UTC)


def judgement(verdict: str, minutes: int = 0, id: str = "j", **more) -> Judgement:
    return Judgement(
        id=id,
        type="StatementJudgement",
        verdict=verdict,
        fields=more.pop("fields", ()),
        note="",
        created_by=({"username": "ann"},),
        created_when=more.pop("when", WHEN + datetime.timedelta(minutes=minutes)),
        changed_since_cited=more.pop("changed", False),
    )


DISAGREE = Verdict(
    "disagree", "a", "b", likelihood=0.9, fields=("place",), how={"place": "different"}, strength=0.9
)  # fmt: skip


def test_without_a_judgement_the_entry_says_what_is_worked_out():
    assert overridden(DISAGREE, []) == worked_out(DISAGREE)
    assert worked_out(DISAGREE) == Said("disagree", ("place",), {"place": "different"}, False)  # fmt: skip


def test_the_newest_judgement_decides_the_relation_and_fields():
    said = overridden(DISAGREE, [judgement("agree", 2), judgement("two_events", 1)])
    assert said == Said("agree", (), {}, False)


def test_two_events_is_the_relation_two_and_a_judgement_is_never_reported():
    reported = Verdict("carried_out", "o", "d", likelihood=0.9, reported=True, strength=0.5)  # fmt: skip
    assert overridden(DISAGREE, [judgement("two_events")]).relation == "two"
    said = overridden(reported, [judgement("carried_out_otherwise", fields=("when",))])
    assert said == Said("carried_out_otherwise", ("when",), {}, False)


def test_a_judgement_on_a_statement_changed_since_cited_still_overrides():
    assert overridden(DISAGREE, [judgement("agree", changed=True)]).relation == "agree"


def test_an_entry_keeps_the_maths_beside_the_judgement():
    entry = Entry(
        Named("b", "Birth"), DISAGREE, Pair("b", (("person", "p", "rule"),)), (judgement("agree"),)
    )  # fmt: skip
    made = entry.as_json()
    assert made["relation"] == "agree" and made["judged"] == "agree"
    assert made["workedOut"] == {"relation": "disagree", "fields": ["place"], "how": {"place": "different"}, "reported": False}  # fmt: skip
    assert made["likelihood"] == 0.9 and made["strength"] == 0.9
    assert made["by"] == [{"field": "person", "entity": {"id": "p", "type": None, "label": None}, "kind": "rule"}]  # fmt: skip
    assert made["found"] == "rule"


def test_field_names_are_camel_case_in_the_answer_and_a_reason_s_entity_is_a_chip():
    """Wherever the answer gives a field's name as a value: what is worked out (`fields`, `how`), what a person
    said, each judgement's `fields`, a reason's `field`; and a reason's entity by its id, class and label"""
    from pangloss_compare.compare import rule_reason

    otherwise = Verdict(
        "carried_out_otherwise",
        "o",
        "d",
        likelihood=0.8,
        fields=("given_to", "when"),
        how={"given_to": "different", "when": "late"},  # fmt: skip
    )
    reasons = (
        rule_reason("given_by", "p", "rule", {"p": Named("p", "Person", "Ada")}),
    )
    made = Entry(
        Named("d", "Transfer"),
        otherwise,
        Pair("d", (("given_by", "p", "rule"),)),
        (judgement("carried_out_otherwise", fields=("given_to",)),),
        reasons=reasons,
    ).as_json()
    assert made["fields"] == ["givenTo"] and made["how"] == {}
    assert made["workedOut"]["fields"] == ["givenTo", "when"]
    assert made["workedOut"]["how"] == {"givenTo": "different", "when": "late"}
    assert made["judgements"][0]["fields"] == ["givenTo"]
    assert made["by"] == [{"field": "givenBy", "entity": {"id": "p", "type": "Person", "label": "Ada"}, "kind": "rule"}]  # fmt: skip


def test_judgements_are_newest_first_one_with_no_time_last_then_by_id():
    found = newest_first(
        [
            judgement("agree", 0, id="a"),
            judgement("agree", 5, id="b"),
            judgement("agree", when=None, id="c"),
            judgement("agree", 5, id="d"),
        ]
    )
    assert [j.id for j in found] == ["d", "b", "a", "c"]


def test_pairs_are_strongest_first_then_by_id_and_two_and_nothing_last():
    verdicts = {
        "x": Verdict("agree", "s", "x", strength=0.5),
        "y": Verdict("contradiction", "s", "y", strength=0.9),
        "w": Verdict("agree", "s", "w", strength=0.5),
        "t": Verdict("two", "s", "t"),
        "n": Verdict("nothing", "s", "n"),
        "z": Verdict("support", "s", "z", strength=0.0),
    }
    ordered = sorted(verdicts, key=lambda id: order_key(verdicts[id], id))
    assert ordered == ["y", "w", "x", "z", "n", "t"]


def entry(other: str, verdict: Verdict, *judgements: Judgement) -> Entry:
    return Entry(Named(other, "Transfer", None, None, None, None), verdict, Pair(other, ()), tuple(judgements))  # fmt: skip


TOLD = Verdict("carried_out", "order", "a", likelihood=0.9, strength=0.7)
REPORTED = Verdict("carried_out", "order", "b", likelihood=0.9, reported=True, strength=0.4)  # fmt: skip
NOTHING = Verdict("nothing", "order", "c")


def superseded(*entries: Entry) -> list[bool]:
    return [e.superseded for e in settle(entries)]


def test_what_only_reports_is_superseded_once_another_entry_tells():
    assert superseded(entry("a", TOLD), entry("b", REPORTED)) == [False, True]
    assert superseded(entry("b", REPORTED)) == [False]


def test_a_pair_a_person_judged_is_never_superseded():
    judged = entry("b", REPORTED, judgement("carried_out"))
    assert superseded(entry("a", TOLD), judged) == [False, False]


def test_what_a_person_judged_two_events_tells_nothing():
    rejected = entry("a", TOLD, judgement("two_events"))
    assert superseded(rejected, entry("b", REPORTED)) == [False, False]


def test_a_persons_answer_tells_as_a_statement_does():
    answered = entry("c", NOTHING, judgement("not_carried_out"))
    assert superseded(answered, entry("b", REPORTED)) == [False, True]
    # (of that prescription only)
    other = Verdict("carried_out", "another order", "d", likelihood=0.9, reported=True)
    assert superseded(answered, entry("d", other)) == [False, False]


def test_the_three_verdicts_added_override_and_tell_what_came_of_the_prescription():
    """`complied`, `permission_used` and `done_not_carried_out` override the relation as the other verdicts of what
    came of a prescription do (no `how`, never reported), and in `settle` tell as an asserted answer does: a report
    of the same prescription no person judged is superseded (as by the maths' own `done_not_carried_out`)"""
    for verdict in ("complied", "permission_used", "done_not_carried_out"):
        said = overridden(REPORTED, [judgement(verdict, fields=("when",))])
        assert said == Said(verdict, ("when",), {}, False)
        answered = entry("c", NOTHING, judgement(verdict))
        assert superseded(answered, entry("b", REPORTED)) == [False, True], verdict
    done = Verdict("done_not_carried_out", "order", "d", likelihood=0.9, strength=0.6)
    assert superseded(entry("d", done), entry("b", REPORTED)) == [False, True]
    # (not checked against the kind of the pair: said of two that describe, it is the entry's relation all the same)
    assert overridden(DISAGREE, [judgement("complied")]).relation == "complied"


def test_every_source_a_ground_names_is_a_chip_by_label():
    """A head whose ground names several (`Told.sources`): the statement's `sources` gives each as a chip, by label
    then id; one the labels' statement did not find is left out; none, an empty list. (`source`, the first by id, is
    what the maths goes by)"""
    import asyncio

    from pangloss_compare.compare import _named
    from pangloss_compare.maths import Told
    from pangloss_models.spaces import Signature

    class Result:
        def __init__(self, rows):
            self.rows = rows

        def __aiter__(self):
            async def each():
                for row in self.rows:
                    yield row

            return each()

    class Tx:
        async def run(self, query, ids):
            known = {
                "s": ("Birth", "Ada is born"),
                "o": ("Birth", "Ada is born again"),
                "z": ("Chronicle", "the annals"),
                "y": ("Chronicle", "Bruges"),
            }
            return Result(
                [
                    {
                        "id": id,
                        "type": known[id][0],
                        "label": known[id][1],
                        "head": None,
                        "head_type": None,
                        "head_label": None,
                    }  # fmt: skip
                    for id in ids
                    if id in known
                ]
            )

    said = Signature(1, None, None, "describes", None, None, None)
    told = [
        Told(
            "s", ("Birth",), said, source="gone", sources=frozenset({"z", "y", "gone"})
        ),
        Told("o", ("Birth",), said),
    ]
    named = asyncio.run(_named(Tx(), told))
    assert named["s"].as_json()["sources"] == [
        {"id": "y", "type": "Chronicle", "label": "Bruges"},
        {"id": "z", "type": "Chronicle", "label": "the annals"},
    ]
    assert named["o"].as_json()["sources"] == []
    assert named["o"].as_json()["prescription"] is None
    # (what each says of its contents, as the page of two decides which verdicts fit)
    assert named["o"].as_json()["says"] == "asserts"


def test_judgements_made_at_the_same_instant_are_in_one_order():
    """Two judgements with the same creation time: the order is the same whatever order they come in (by id, the
    greater first), as learning's `newest` takes them"""
    from pangloss_compare.learning import newest  # noqa: F401  (the same rule: its docstring)

    a = judgement("agree", id="j-a", when=WHEN)
    b = judgement("disagree", id="j-b", when=WHEN)
    assert (
        [j.id for j in newest_first([a, b])]
        == [j.id for j in newest_first([b, a])]
        == ["j-b", "j-a"]
    )
