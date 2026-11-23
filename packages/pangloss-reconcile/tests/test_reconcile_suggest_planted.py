"""The seeded floor of what is suggested (implementation_docs/similarity-build-plan.md, "Testing the next phases", 4;
step 10.5c), with no database: what `notes/similarity-evaluation/planted.py suggest` measures through the service,
done in memory on the planted world of `test_reconcile_planted.py` (1,500 people; name 1, graph 0.25, shared 1.5).

Each mention's candidates are scored as that file scores them; of every second mention the person is taken out
("someone new"). The list is the dialog's (those not under the least score, 0.15, the first `candidates.DISPLAYED`),
decided by `suggest.decide` at the defaults (`RECONCILE_SUGGEST_ABOVE` 0.6, `_MOST` 3, `_WITHIN` 0.7) with no fit.
Held: of the suggestions made for mentions whose person is in the world, the share that hold the person (a floor);
of the mentions whose person was taken out, the share that get a suggestion all the same (a ceiling)."""

import pytest
from pangloss_reconcile import settings
from pangloss_reconcile.candidates import DISPLAYED
from pangloss_reconcile.score import ranked
from pangloss_reconcile.suggest import decide
from test_reconcile_planted import WITH_SHARED, scored

SEEDS = (1, 2, 3)

# Measured here on seeds 1, 2 and 3 (2026-11-23, 287, 291 and 292 mentions, every second taken out): of the 144, 146
# and 146 mentions whose person is there, a suggestion made for 92, 97 and 96, holding the person 92, 96 and 96 times
# (100%, 99.0%, 100%), first 81, 88 and 87 times; of the 143, 145 and 146 taken out, a suggestion made for 23, 31 and
# 25 (16.1%, 21.4%, 17.1%). (Main through the service at size, 32,137 people: 98.5% of those made held the person,
# and 18.5% of those taken out had one)
HOLD_FLOOR = 0.97
NEW_CEILING = 0.24


def measured(seed: int) -> dict[str, float]:
    """Of the world of `seed`: how many suggestions were made for mentions whose person is there, how many of them
    hold the person and put them first, and the share of mentions taken out given one"""
    _, found = scored(seed, WITH_SHARED)
    least = settings.DEFAULT_LEAST_SCORE
    made = holds = first = there = gone_made = gone = 0
    for n, (mention, candidates) in enumerate(found):
        taken_out = n % 2 == 1
        order = [
            id
            for id in ranked(
                {id: c.score for id, c in candidates.items()}, len(candidates)
            )
            if not (taken_out and id == mention.person)
        ]
        shown = [
            (id, "Person", candidates[id].score)
            for id in order
            if candidates[id].score >= least
        ][:DISPLAYED]
        decision = decide(
            shown,
            above=settings.DEFAULT_SUGGEST_ABOVE,
            most=settings.DEFAULT_SUGGEST_MOST,
            within=settings.DEFAULT_SUGGEST_WITHIN,
        )
        if taken_out:
            gone += 1
            gone_made += decision.suggested
            continue
        there += 1
        if decision.suggested:
            made += 1
            ids = [a.id for a in decision.alternatives]
            holds += mention.person in ids
            first += ids[0] == mention.person
    return {
        "there": there,
        "made": made,
        "holds": holds,
        "first": first,
        "gone": gone,
        "gone_made": gone_made,
        "hold_share": holds / made,
        "new_share": gone_made / gone,
    }


@pytest.fixture(scope="module")
def suggested() -> dict[int, dict[str, float]]:
    """(made once for the module: what is suggested in each seed's world)"""
    return {seed: measured(seed) for seed in SEEDS}


@pytest.mark.parametrize("seed", SEEDS)
def test_of_the_suggestions_made_nearly_all_hold_the_person(suggested, seed):
    found = suggested[seed]
    # (and some are made: a threshold no candidate reaches would hold this vacuously)
    assert found["made"] > found["there"] / 3, found
    assert found["hold_share"] > HOLD_FLOOR, found


@pytest.mark.parametrize("seed", SEEDS)
def test_few_of_the_mentions_of_someone_taken_out_get_a_suggestion(suggested, seed):
    found = suggested[seed]
    assert found["new_share"] < NEW_CEILING, found
