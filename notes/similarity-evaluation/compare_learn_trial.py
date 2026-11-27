"""How many judgements of "one event or two" it takes to equal the weights set by hand, and to cut their mistakes by
a third (step 6.6 of implementation_docs/spaces-and-comparison-plan.md), on the planted world for comparison, with no
database. A judgement is taken to be the truth of the pair (a person who judges rightly).

    uv run python notes/similarity-evaluation/compare_learn_trial.py [--people 5000]

The pairs are those the rule (6.3) gives and the logistic decides (two that describe, not settled by `once_per`).
Fitted on judgements of one world (seed 1), counted on another (seed 2). Two ways of choosing what is judged:
`any` pair, or only pairs `shown` as likely enough to be looked at (a likelihood by hand of 0.2 or more). Counted
three ways: the fit on every pair of the other world; on those of it that would be shown; and a fit that has the
hand-set score among its features (its log odds), on every pair.
"""

import argparse
import random
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "packages/pangloss-compare/tests"))  # fmt: skip

SIZES = (25, 50, 100, 200, 400, 800, 1600, 3200)


def examples_of(world, t, maths):
    """Each pair the logistic decides: its features, the truth, and the likelihood by hand"""
    statements, event_of = t.statements_of(world)
    truth = {frozenset((v.a, v.b)): v for v in world.verdicts}
    rows = []
    for a, b in t.pairs_by_rule(statements):
        if maths.prescribes(a.signature) or maths.prescribes(b.signature):
            continue
        rules = t.RULES[maths.common_class(a, b)]
        compared = maths.compare_fields(a, b, rules)
        if rules.once_per and compared.identifying.get(rules.once_per) in ("same", "different"):  # fmt: skip
            continue
        if not any(how in ("same", "partly") for how in compared.identifying.values()):
            continue
        said = truth.get(frozenset((a.id, b.id)))
        one = said.relation != "two" if said else event_of[a.id] == event_of[b.id]
        features = maths.features(a, b, compared, rules)
        rows.append((features, one, maths.logistic(features, maths.WEIGHTS)))
    return rows


def with_hand(features, likelihood):
    """The features and the hand-set score among them, as its log odds (bounded)"""
    import math

    p = min(max(likelihood, 1e-6), 1 - 1e-6)
    return {**features, "by_hand": math.log(p / (1 - p))}


def main() -> None:
    import test_compare_maths as t
    from pangloss_compare import maths
    from pangloss_core import BaseSettings, DatabaseSettings
    from pangloss_learn import Example, Unfittable, fit
    from pangloss_models import ModelRegistry
    from pangloss_testing import planted
    from pangloss_testing.similar_models import declare
    from pydantic import AnyHttpUrl, create_model

    parser = argparse.ArgumentParser()
    parser.add_argument("--people", type=int, default=5000)
    args = parser.parse_args()
    create_model(
        "Settings", __base__=BaseSettings, PROJECT_NAME=(str, "Test"), BACKEND_CORS_ORIGINS=(list, []),
        INSTALLED_APPS=(list[str], ["pangloss_derived", "pangloss_library", "pangloss_criteria"]),
        STORAGE=(str | None, "pangloss_sdk.storage:api"), DATABASE=(DatabaseSettings, DatabaseSettings()),
        INTERFACE_LANGUAGES=(list[str], ["en"]), DEFAULT_INTERFACE_LANGUAGE=(str, "en"),
        AUTHJWT_SECRET_KEY=(str, "asdf"), ENTITY_BASE_URL=(AnyHttpUrl, AnyHttpUrl("http://test.com/")),
    )()  # fmt: skip
    ModelRegistry._reset()
    declare(compared=True)
    judged = examples_of(planted.world(seed=1, people=args.people, compared=True), t, maths)  # fmt: skip
    held = examples_of(planted.world(seed=2, people=args.people, compared=True), t, maths)  # fmt: skip
    names = [name for name in maths.WEIGHTS if name != "bias"]
    by_hand = sum((likelihood >= 0.5) != one for _, one, likelihood in held)
    print(f"{len(judged):,} pairs to judge (one event: {sum(one for _, one, _ in judged) / len(judged):.1%}); counted on {len(held):,} of another world")  # fmt: skip
    shown_by_hand = sum((p >= 0.5) != one for _, one, p in held if p >= 0.2)
    print(f"by hand among those shown (0.2 or more): {shown_by_hand} mistakes of {sum(p >= 0.2 for *_, p in held):,}")  # fmt: skip
    print(f"by hand: {by_hand} mistakes ({by_hand / len(held):.2%}); always 'two': {sum(one for _, one, _ in held)}")  # fmt: skip
    for which in ("any", "shown"):
        pool = judged if which == "any" else [row for row in judged if row[2] >= 0.2]
        print(f"\njudged: {which} pair ({len(pool):,}; one event {sum(one for _, one, _ in pool) / len(pool):.1%})")  # fmt: skip
        print(f"{'judgements':>12}{'mistakes (median of 7 draws)':>32}{'least':>8}{'most':>8}{'not fitted':>12}{'among those shown':>22}{'with the hand score in':>26}{'most':>8}")  # fmt: skip
        for size in SIZES:
            if size > len(pool):
                continue
            mistakes, among, stacked, refused = [], [], [], 0
            for draw in range(7):
                rows = random.Random(f"{which} {size} {draw}").sample(pool, size)
                try:
                    model = fit([Example(f, one) for f, one, _ in rows], names)
                    over = fit([Example(with_hand(f, p), one) for f, one, p in rows], [*names, "by_hand"])  # fmt: skip
                except Unfittable:
                    refused += 1
                    continue
                mistakes.append(sum((model.score(f) >= 0.5) != one for f, one, _ in held))  # fmt: skip
                among.append(sum((model.score(f) >= 0.5) != one for f, one, p in held if p >= 0.2))  # fmt: skip
                stacked.append(sum((over.score(with_hand(f, p)) >= 0.5) != one for f, one, p in held))  # fmt: skip
            if mistakes:
                print(f"{size:>12}{statistics.median(mistakes):>32.0f}{min(mistakes):>8}{max(mistakes):>8}{refused:>12}{statistics.median(among):>22.0f}{statistics.median(stacked):>26.0f}{max(stacked):>8}")  # fmt: skip
            else:
                print(f"{size:>12}{'':>32}{'':>8}{'':>8}{refused:>12}")


if __name__ == "__main__":
    main()
