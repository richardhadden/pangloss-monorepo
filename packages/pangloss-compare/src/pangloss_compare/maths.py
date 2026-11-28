"""How two statements stand to each other, with no database in it (implementation_docs/spaces-and-comparison-plan.md,
step 6.2; the table is implementation_docs/semantic-space-fields.md, "Contents find, spaces decide").

    verdict(a, b, rules) -> Verdict

`a` and `b` are statements read as plain data (`Told`): the class and those above it, the entities in each field
(a narrowed field under the name of the field it narrows; what is behind a wrapper as if it were in the field), the
dates as spans of days, the signature the walk gives the statement's path (`pangloss_models.spaces.signature`), its
head and its source, and, of what is prescribed, who prescribed it, to whom and when (`Prescribed`: the
`Attribution` of the field holding the space, read of the statement that holds it). `rules` is each compared
class's `CompareMeta` as plain data (`Rules`).

Three questions, asked in this order:

1. **What the two say of their contents** is the signatures': asserted, denied, neither and leaning for or
   against, or prescribed (`stance`, `prescribes`). One that leans neither way says nothing: `nothing`.
2. **Whether the contents are the same thing** is the fields': the entities of each field alike, different, or one
   silent (`compare_entities`: of two lists, alike when one holds the other), the dates overlapping or apart beyond
   both uncertainties (a date is read at its widest). Of two that describe, one event or two is `one_event`:
   certain by `once_per`, else a logistic set by hand (`WEIGHTS`). Of a prescription and what may answer it, the
   date is a target and not evidence: `answers`.
3. **The relation** is then the table's (`RELATIONS`).

What the brief of the step left open, as settled here:

- A denial is held against the same thing only: a pair one of which says "not" and whose fields differ is `nothing`
  ("they met on Tuesday" and "they did not meet on Wednesday" say nothing of each other).
- Two denials of one thing `agree`.
- What only reports the outcome of a prescription has the relation it would have were it asserted, with
  `reported=True` (the table's "reportedly carried out, or reportedly not").
- A permission whose thing is said not to have been done, an order not to whose thing another did, or did before:
  `nothing`.
- Two prescriptions of one thing that point the same way are `compatible`; pointing against each other they are a
  `conflict` within one flavour and authority and `orders_at_odds` otherwise; two possibilities never conflict.
- `strength` orders a list: the likelihood times how far each side commits (1 where it asserts or denies, else
  the weight of its degree, `DEGREES`).
"""

import dataclasses
import math
from collections.abc import Iterable, Mapping
from typing import Any

from pangloss_models.spaces import Signature

RELATIONS = (
    # of two that describe
    "agree", "disagree", "two",
    "contradiction", "support", "tension", "compatible", "at_odds",
    # of what is prescribed and what came of it
    "carried_out", "carried_out_otherwise", "done_not_carried_out", "not_carried_out",
    "breach", "complied", "permission_used",
    # of two prescriptions
    "conflict", "orders_at_odds",
    "nothing",
)  # fmt: skip

# Where a relation says what came of a prescription
ANSWERS = (
    "carried_out", "carried_out_otherwise", "done_not_carried_out", "not_carried_out",
    "breach", "complied", "permission_used",
)  # fmt: skip

ASSERTS, DENIES, FOR, AGAINST, NEITHER = "asserts", "denies", "for", "against", "neither"  # fmt: skip
SAME, PARTLY, DIFFERENT, SILENT = "same", "partly", "different", "silent"
LATE, EARLY, IN_PART = "late", "early", "in_part"

# How far a statement that neither asserts nor denies commits, by its degree (as the actual network weighs it:
# `pangloss_fastrp.settings.DEFAULT_DEGREE_WEIGHTS`)
DEGREES: dict[str | None, float] = {
    "impossible": 0.0,
    "unlikely": 0.2,
    "possible": 0.4,
    "likely": 0.6,
    "expected": 0.8,
    None: 0.5,
}


@dataclasses.dataclass(frozen=True)
class Span:
    """A date as days: its widest bounds (`Bounds.earliest_fuzzy`, `latest_fuzzy`)"""

    earliest: int
    latest: int

    @classmethod
    def of(cls, bounds: Any) -> Span:
        """Of a `pangloss_dates.bounds.Bounds`"""
        return cls(bounds.earliest_fuzzy, bounds.latest_fuzzy)

    @property
    def width(self) -> int:
        return self.latest - self.earliest


@dataclasses.dataclass(frozen=True)
class Prescribed:
    """Of a statement inside a space that prescribes: what the statement holding the space says"""

    by: frozenset[str] = frozenset()
    """Who prescribes (`Attribution.by`): the authority"""
    to: frozenset[str] = frozenset()
    """To whom (`Attribution.to`): those it applies to"""
    at: Span | None = None
    """When it was prescribed: the date of the statement holding the space"""
    orientation: str = "after"
    """Whether what answers it comes `after` it was prescribed, or `before` (`CompareMeta.orientation`)"""


@dataclasses.dataclass(frozen=True)
class Told:
    """A statement as plain data"""

    id: str
    classes: tuple[str, ...]
    """Its class and the compared classes above it, nearest first"""
    signature: Signature
    fields: Mapping[str, frozenset[str]] = dataclasses.field(default_factory=dict)
    """The ids of the entities in each field; a field that narrows another under the name of the one it narrows"""
    dates: Mapping[str, Span] = dataclasses.field(default_factory=dict)
    head: str | None = None
    """The id of its head (its factoid)"""
    source: str | None = None
    """Whose claim it is: what the head's ground names (`Signature.grounded_by`), read of the head; of several, the
    first by id (what "within the same source" and "sources differ" go by)"""
    prescribed: Prescribed | None = None
    sources: frozenset[str] = frozenset()
    """Every entity the head's ground names (`source` is one of them): for showing, not for the verdict"""

    @property
    def type(self) -> str:
        return self.classes[0]


@dataclasses.dataclass(frozen=True)
class Rules:
    """A class's `CompareMeta`"""

    identifying: tuple[str, ...]
    once_per: str | None = None
    recurs: bool = False


@dataclasses.dataclass(frozen=True)
class Verdict:
    relation: str
    """One of `RELATIONS`"""
    first: str
    second: str
    """The two statements' ids: of a prescription and what came of it, the prescription first"""
    likelihood: float = 0.0
    """Of two that describe: that they tell of one event. Of a prescription and another statement: that the other
    answers it"""
    fields: tuple[str, ...] = ()
    """The fields disagreed on; of what was carried out otherwise, the targets missed"""
    how: Mapping[str, str] = dataclasses.field(default_factory=dict)
    """Of each of `fields`: `different`, or of a target `late`, `early`, `in_part`"""
    reported: bool = False
    """What came of the prescription is only reported, not asserted or denied"""
    within: str | None = None
    """`"factoid"` where the two are of one head, `"source"` where of one source, else None"""
    strength: float = 0.0
    common: str | None = None
    """The nearest class both are"""
    superseded: bool = False
    """(`settled`) another statement tells what came of the prescription"""

    @property
    def one_event(self) -> bool:
        return self.relation not in ("two", "nothing")


# --- what a statement says of its contents ----------------------------------------------------------------


def stance(signature: Signature) -> str:
    if signature.veridical == 1:
        return ASSERTS
    if signature.veridical == -1:
        return DENIES
    return signature.lean or NEITHER


def prescribes(signature: Signature) -> bool:
    return signature.fit == "prescribes"


ORDER, PROHIBITION, PERMISSION = "order", "prohibition", "permission"


def prescription(signature: Signature) -> str | None:
    """What kind of prescription a statement is, as `_answered` tells them apart: a `permission` where the innermost
    modality is a possibility (used or not), else an `order` where it is for its contents (carried out or not) and a
    `prohibition` where it is against them (breached or complied with). None where it prescribes nothing, or leans
    neither way (it says nothing)"""
    if not prescribes(signature):
        return None
    said = stance(signature)
    if said == NEITHER:
        return None
    if signature.force == "possibility":
        return PERMISSION
    return ORDER if _positive(said) else PROHIBITION


def commitment(signature: Signature) -> float:
    """How far the statement commits to its contents, either way: 1 where it asserts or denies"""
    if signature.veridical != 0:
        return 1.0
    if signature.lean == NEITHER:
        return 0.0
    return DEGREES.get(signature.degree, DEGREES[None])


def _positive(said: str) -> bool:
    return said in (ASSERTS, FOR)


# --- the fields -------------------------------------------------------------------------------------------


def compare_entities(a: frozenset[str], b: frozenset[str]) -> str:
    """`silent` where either names none; `same` where they name the same, or one names all the other does (a
    second report that names fewer); `partly` where they share some and each names one the other does not; else
    `different`"""
    if not a or not b:
        return SILENT
    if a <= b or b <= a:
        return SAME
    return PARTLY if a & b else DIFFERENT


def gap(a: Span, b: Span) -> int:
    """The days from `a` to `b` beyond both uncertainties: 0 where they overlap, positive where `b` is after"""
    if b.earliest > a.latest:
        return b.earliest - a.latest
    if a.earliest > b.latest:
        return -(a.earliest - b.latest)
    return 0


def common_class(a: Told, b: Told) -> str | None:
    """The nearest class both are, when one's class is the other's or above it; else None"""
    if b.type in a.classes:
        return b.type
    if a.type in b.classes:
        return a.type
    return None


@dataclasses.dataclass(frozen=True)
class Compared:
    """Two statements field by field"""

    identifying: Mapping[str, str]
    others: Mapping[str, str]
    gaps: Mapping[str, int]
    """Of each date both say: `gap`"""
    widths: Mapping[str, int]
    """Of each date both say: the days from the earliest either allows to the latest"""

    @property
    def different(self) -> tuple[str, ...]:
        """The fields the two disagree on, entities first"""
        return (
            *(f for f, how in self.identifying.items() if how in (PARTLY, DIFFERENT)),
            *(f for f, how in self.others.items() if how in (PARTLY, DIFFERENT)),
            *(f for f, days in self.gaps.items() if days),
        )


def compare_fields(a: Told, b: Told, rules: Rules) -> Compared:
    identifying, others = {}, {}
    for field in sorted({*a.fields, *b.fields, *rules.identifying}):
        how = compare_entities(
            a.fields.get(field, frozenset()), b.fields.get(field, frozenset())
        )
        (identifying if field in rules.identifying else others)[field] = how
    both = sorted(set(a.dates) & set(b.dates))
    return Compared(
        identifying,
        others,
        {f: gap(a.dates[f], b.dates[f]) for f in both},
        {
            f: max(a.dates[f].latest, b.dates[f].latest)
            - min(a.dates[f].earliest, b.dates[f].earliest)
            for f in both
        },
    )


# --- one event or two -------------------------------------------------------------------------------------

# The logistic, set by hand and measured on the planted world (`tests/test_compare_maths.py`); step 6.6 learns it
# from people's judgements
WEIGHTS: dict[str, float] = {
    "bias": -1.0,
    "identifying_same": 1.2,  # for each identifying field alike
    "identifying_partly": -0.5,  # a list that shares some: one participant another person
    "identifying_different": -4.0,
    "other_same": 0.8,  # the place and the like
    "other_different": -1.0,
    "date_overlap": 3.0,  # at its most, where both say the day: less the wider the two together
    "date_apart": -0.9,  # times ln(1 + the weeks apart)
    "date_apart_recurs": -6.0,  # where the class recurs: any day apart, on top
    "recurs": -1.0,
    "sources_differ": 0.5,
    "same_factoid": -1.5,  # of two that both assert: a researcher splits a passage on purpose
}


def features(a: Told, b: Told, compared: Compared, rules: Rules) -> dict[str, float]:
    """What the logistic weighs, by the names of `WEIGHTS` (and what step 6.6 learns from)"""
    apart = [abs(days) for days in compared.gaps.values() if days]
    overlap = [
        1 / (1 + math.log1p(compared.widths[f] / 30))
        for f, days in compared.gaps.items()
        if not days
    ]
    both_assert = stance(a.signature) == ASSERTS and stance(b.signature) == ASSERTS
    known = a.source is not None and b.source is not None
    return {
        "bias": 1.0,
        "identifying_same": sum(h == SAME for h in compared.identifying.values()),
        "identifying_partly": sum(h == PARTLY for h in compared.identifying.values()),
        "identifying_different": sum(
            h == DIFFERENT for h in compared.identifying.values()
        ),
        "other_same": sum(h == SAME for h in compared.others.values()),
        "other_different": sum(
            h in (PARTLY, DIFFERENT) for h in compared.others.values()
        ),
        "date_overlap": max(overlap, default=0.0) if not apart else 0.0,
        "date_apart": math.log1p(max(apart) / 7) if apart else 0.0,
        "date_apart_recurs": float(bool(apart) and rules.recurs),
        "recurs": float(rules.recurs),
        "sources_differ": float(known and a.source != b.source),
        "same_factoid": float(both_assert and a.head is not None and a.head == b.head),
    }


def logistic(values: Mapping[str, float], weights: Mapping[str, float]) -> float:
    z = sum(weights.get(name, 0.0) * value for name, value in values.items())
    return 1 / (1 + math.exp(-max(-60.0, min(60.0, z))))


# What a fit of people's judgements has beside the terms set by hand: the hand-set likelihood itself, as its log
# odds. Measured (the plan, "6.6, measured before its brief"): people judge the pairs they are shown, which are
# those the hand-set score thinks likely; a fit of the terms alone on such judgements knows nothing of the rest and
# calls them one event. With this term it corrects the score where there are judgements and leaves it standing
# where there are none
BY_HAND = "by_hand"
ONE_EVENT, ANSWERS_IT = "one_event", "answers"


def log_odds(likelihood: float) -> float:
    """(bounded: a likelihood of 0 or 1 is not an infinite term)"""
    p = min(max(likelihood, 1e-6), 1 - 1e-6)
    return math.log(p / (1 - p))


def refitted(
    values: Mapping[str, float], by_hand: float, fitted: Mapping[str, float] | None
) -> float:
    """The likelihood by a fit (its weights, `bias` its constant, over the terms and `by_hand`), or the one by hand
    with none"""
    if fitted is None:
        return by_hand
    return logistic({**values, BY_HAND: log_odds(by_hand)}, fitted)


def by_rule(compared: Compared, rules: Rules) -> float | None:
    """Where the rules settle one event or two with no weighing: by `once_per` (1 or 0), or with no identifying
    entity in common (0). None where the logistic decides (the pairs a fit learns from)"""
    if rules.once_per is not None:
        once = compared.identifying.get(rules.once_per, SILENT)
        if once == SAME:
            return 1.0
        if once == DIFFERENT:
            return 0.0
    if not any(how in (SAME, PARTLY) for how in compared.identifying.values()):
        return 0.0
    return None


def one_event(
    a: Told,
    b: Told,
    compared: Compared,
    rules: Rules,
    weights: Mapping[str, float] | None = None,
    fitted: Mapping[str, float] | None = None,
) -> float:
    """The likelihood that two statements that describe tell of one event. **Once per**: the same entity in the
    once-per field is one event whatever the rest, another entity there another event. `fitted`: a fit of people's
    judgements (`refitted`)"""
    settled = by_rule(compared, rules)
    if settled is not None:
        return settled
    values = features(a, b, compared, rules)
    return refitted(values, logistic(values, WEIGHTS if weights is None else weights), fitted)  # fmt: skip


# --- what answers a prescription --------------------------------------------------------------------------

ANSWER_WEIGHTS: dict[str, float] = {
    "bias": 2.5,
    "missed_by": -0.48,  # times ln(1 + the days from the target): even at about half a year
    "by_another": -1.0,
    "out_of_order": -1.5,  # before it was prescribed (or after, of an orientation `before`)
}


def _doer_fields(prescription: Told, rules: Rules) -> list[str]:
    """The identifying fields in which what is prescribed names one of those it is prescribed to"""
    to = prescription.prescribed.to if prescription.prescribed else frozenset()
    return [f for f in rules.identifying if prescription.fields.get(f, frozenset()) & to]  # fmt: skip


def _in_order(prescription: Told, other: Told) -> bool:
    """Whether the other statement's date is on the right side of when it was prescribed. With either date
    missing it is not judged, and counts as in order"""
    told = prescription.prescribed
    if told is None or told.at is None or not other.dates:
        return True
    days = [gap(told.at, when) for when in other.dates.values()]
    if told.orientation == "before":
        return all(d <= 0 for d in days)
    return all(d >= 0 for d in days)


def _targets(prescription: Told, other: Told, compared: Compared) -> dict[str, str]:
    """The prescribed details the other statement misses: a date `late` or `early`, another field `different`,
    or `in_part` where it names some and not all of what was prescribed"""
    missed: dict[str, str] = {}
    for field, how in {**compared.identifying, **compared.others}.items():
        asked = prescription.fields.get(field, frozenset())
        done = other.fields.get(field, frozenset())
        if how in (PARTLY, DIFFERENT):
            missed[field] = DIFFERENT
        elif how == SAME and done < asked:
            missed[field] = IN_PART
    for field, days in compared.gaps.items():
        if days:
            missed[field] = LATE if days > 0 else EARLY
    return missed


# --- the verdict ------------------------------------------------------------------------------------------


def _within(a: Told, b: Told) -> str | None:
    if a.head is not None and a.head == b.head:
        return "factoid"
    if a.source is not None and a.source == b.source:
        return "source"
    return None


def verdict(
    a: Told,
    b: Told,
    rules: Mapping[str, Rules],
    weights: Mapping[str, float] | None = None,
    fitted: Mapping[str, Mapping[str, float]] | None = None,
) -> Verdict:
    """How `a` and `b` stand to each other. `rules`: the compared classes' rules, by name. `weights`: the
    logistic's, in place of `WEIGHTS` (not with `fitted`). `fitted`: fits of people's judgements (step 6.6), by `ONE_EVENT` and
    `ANSWERS_IT`, each the weights of its terms and of `BY_HAND`, with `bias` its constant"""
    if weights is not None and fitted:
        # (a fit corrects the likelihood by `WEIGHTS`: with other weights its term `by_hand` is of another score)
        raise ValueError("Give `weights` or `fitted`, not both")
    fitted = fitted or {}
    common = common_class(a, b)
    # (of a prescription and what came of it, the prescription first; of two, as given)
    if prescribes(b.signature) and not prescribes(a.signature):
        a, b = b, a
    made = dataclasses.replace(
        Verdict("nothing", a.id, b.id), within=_within(a, b), common=common
    )
    if common is None or common not in rules:
        return made
    said_a, said_b = stance(a.signature), stance(b.signature)
    if NEITHER in (said_a, said_b):
        return made
    of = rules[common]
    compared = compare_fields(a, b, of)
    if prescribes(a.signature) and prescribes(b.signature):
        found = _two_prescriptions(a, b, said_a, said_b, compared)
    elif prescribes(a.signature):
        found = _answered(a, b, said_a, said_b, compared, of, fitted.get(ANSWERS_IT))
    else:
        found = _told_twice(a, b, said_a, said_b, compared, of, weights, fitted.get(ONE_EVENT))  # fmt: skip
    relation, likelihood, fields, reported = found
    if relation in ("two", "nothing"):
        strength = 0.0
    else:
        strength = likelihood * commitment(a.signature) * commitment(b.signature)
    return dataclasses.replace(
        made,
        relation=relation,
        likelihood=likelihood,
        fields=tuple(fields),
        how=dict(fields),
        reported=reported,
        strength=strength,
    )


Found = tuple[str, float, dict[str, str], bool]


def _told_twice(
    a: Told,
    b: Told,
    said_a: str,
    said_b: str,
    compared: Compared,
    rules: Rules,
    weights: Mapping[str, float] | None,
    fitted: Mapping[str, float] | None = None,
) -> Found:
    likelihood = one_event(a, b, compared, rules, weights, fitted)
    if likelihood < 0.5:
        return "two", likelihood, {}, False
    different = dict.fromkeys(compared.different, DIFFERENT)
    negative = not (_positive(said_a) and _positive(said_b))
    if different and negative:
        # (a "not" is held against the same thing only)
        return "nothing", likelihood, different, False
    pair = {said_a, said_b}
    if pair == {ASSERTS} or pair == {DENIES}:
        relation = "disagree" if different else "agree"
    elif pair == {ASSERTS, DENIES}:
        relation = "contradiction"
    elif pair in ({ASSERTS, FOR}, {DENIES, AGAINST}):
        relation = "support"
    elif pair in ({ASSERTS, AGAINST}, {DENIES, FOR}):
        relation = "tension"
    elif pair == {FOR, AGAINST}:
        relation = "at_odds"
    else:
        relation = "compatible"
    return relation, likelihood, different, False


def answers(compared: Compared, rules: Rules, a: Told) -> bool:
    """Whether the other statement is of the thing `a` prescribes at all: the identifying fields that do not name
    those it was prescribed to are not different, and one identifying field is alike. Where not, the pair is of
    two things and nothing is weighed (nor learnt)"""
    doers = _doer_fields(a, rules)
    what = {f: how for f, how in compared.identifying.items() if f not in doers}
    return DIFFERENT not in what.values() and SAME in compared.identifying.values()


def answer_features(
    a: Told, b: Told, compared: Compared, rules: Rules
) -> dict[str, float]:
    """What the likelihood that `b` answers the prescription `a` weighs, by the names of `ANSWER_WEIGHTS`"""
    doers = _doer_fields(a, rules)
    missed = {f for f in _targets(a, b, compared) if f not in doers}
    days = max(
        (abs(d) for f, d in compared.gaps.items() if d and f in missed), default=0
    )
    return {
        "bias": 1.0,
        "missed_by": math.log1p(days),
        "by_another": float(any(compared.identifying[f] == DIFFERENT for f in doers)),
        "out_of_order": float(not _in_order(a, b)),
    }


def _answered(
    a: Told,
    b: Told,
    said_a: str,
    said_b: str,
    compared: Compared,
    rules: Rules,
    fitted: Mapping[str, float] | None = None,
) -> Found:
    """`a` prescribes, `b` describes: whether `b` answers `a`, and how"""
    doers = _doer_fields(a, rules)
    if not answers(compared, rules, a):
        # (not the thing prescribed)
        return "two", 0.0, {}, False
    by_another = any(compared.identifying[f] == DIFFERENT for f in doers)
    in_order = _in_order(a, b)
    missed = {f: how for f, how in _targets(a, b, compared).items() if f not in doers}
    values = answer_features(a, b, compared, rules)
    likelihood = refitted(values, logistic(values, ANSWER_WEIGHTS), fitted)
    reported = said_b in (FOR, AGAINST)
    wanted = _positive(said_a)
    done = _positive(said_b)
    necessity = a.signature.force != "possibility"
    on_target = bool(compared.gaps) and not any(compared.gaps.values())
    relation = "two"
    fields: dict[str, str] = {}
    if by_another:
        # (another's doing is the thing prescribed only where it is on the day prescribed; said not to have been,
        # it says nothing of those it was prescribed to)
        if necessity and wanted and done and on_target:
            relation = "done_not_carried_out"
        elif not done:
            relation = "nothing"
    elif not in_order:
        # (done already: of what is done again and again, another time)
        if necessity and wanted and done and not rules.recurs:
            relation = "done_not_carried_out"
        elif not done or not wanted:
            relation = "nothing"
    elif likelihood < 0.5:
        pass
    elif not necessity:
        # (a permission is used or not, never carried out or breached)
        relation = "permission_used" if done == wanted else "nothing"
    elif wanted and done:
        if missed:
            relation, fields = "carried_out_otherwise", missed
        else:
            relation = "carried_out"
    elif wanted:
        relation = "not_carried_out"
    else:
        relation = "breach" if done else "complied"
    return relation, likelihood, fields, reported and relation in ANSWERS


def _two_prescriptions(
    a: Told, b: Told, said_a: str, said_b: str, compared: Compared
) -> Found:
    if DIFFERENT in compared.identifying.values() or SAME not in compared.identifying.values():  # fmt: skip
        return "two", 0.0, {}, False
    if _positive(said_a) == _positive(said_b):
        return "compatible", 1.0, {}, False
    if a.signature.force == "possibility" and b.signature.force == "possibility":
        return "compatible", 1.0, {}, False
    by_a = a.prescribed.by if a.prescribed else frozenset()
    by_b = b.prescribed.by if b.prescribed else frozenset()
    one_authority = bool(by_a & by_b) and a.signature.flavour == b.signature.flavour
    return ("conflict" if one_authority else "orders_at_odds"), 1.0, {}, False


def settled(verdicts: Iterable[Verdict]) -> list[Verdict]:
    """Of the verdicts of one statement's pairs: once a statement tells what came of a prescription (asserts or
    denies it), what is only reported of the same prescription is `superseded`"""
    verdicts = list(verdicts)
    told = {v.first for v in verdicts if v.relation in ANSWERS and not v.reported}
    return [
        dataclasses.replace(v, superseded=True)
        if v.relation in ANSWERS and v.reported and v.first in told
        else v
        for v in verdicts
    ]
