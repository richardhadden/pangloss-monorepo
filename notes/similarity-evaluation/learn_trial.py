"""Before phase 11 (`pangloss-learn`) has steps: is there anything to learn? (2026-11-23, no database)

On the planted world in memory (as `packages/pangloss-reconcile/tests/test_reconcile_planted.py` makes it: the name
part's and the graph part's vectors, the candidates the 50 nearest by each part), each mention's candidates get
features, and a logistic regression (numpy alone, Newton's steps with a ridge) is fitted on the decisions of N
mentions: the person chosen is a yes, the others of the ten shown (by the hand-set score) are a no. Measured on the
mentions it was not fitted on:

1. right first / among five, by the hand-set score (name 1, graph 0.25) and by the fitted model, for several N;
2. "someone new": for half the mentions the person is taken out of the candidates; can the answer "none of these"
   be told, by the best hand-set score (the AUC of 10.3) and by a second fitted model over the top of the list.

    uv run python notes/similarity-evaluation/learn_trial.py [people [shown]] > notes/similarity-evaluation/learn_trial.txt
"""

import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

import numpy as np

sys.path.insert(
    0, str(Path(__file__).parents[2] / "packages" / "pangloss-reconcile" / "tests")
)
import test_reconcile_planted as base  # noqa: E402
from pangloss_fastrp import maths as graph_maths  # noqa: E402
from pangloss_names import maths as name_maths  # noqa: E402
from pangloss_testing import planted  # noqa: E402

FETCH = 50
SHOWN = int(sys.argv[2]) if len(sys.argv) > 2 else 10
HAND = (1.0, 0.25)
SHARED = 0.3


def fit(x: np.ndarray, y: np.ndarray, ridge: float = 1.0) -> np.ndarray:
    """Logistic regression: the weights (the last is the constant) by Newton's steps, with a ridge on all but it"""
    x = np.hstack([x, np.ones((len(x), 1))])
    w = np.zeros(x.shape[1])
    penalty = np.eye(x.shape[1]) * ridge
    penalty[-1, -1] = 0
    for _ in range(50):
        p = 1 / (1 + np.exp(-(x @ w)))
        gradient = x.T @ (p - y) + penalty @ w
        hessian = (x * (p * (1 - p))[:, None]).T @ x + penalty
        step = np.linalg.solve(hessian + 1e-9 * np.eye(len(w)), gradient)
        w -= step
        if np.abs(step).max() < 1e-8:
            break
    return w


def said(w: np.ndarray, x: np.ndarray) -> np.ndarray:
    return 1 / (1 + np.exp(-(np.hstack([x, np.ones((len(x), 1))]) @ w)))


def auc(scores: np.ndarray, yes: np.ndarray) -> float:
    order = np.argsort(scores, kind="stable")
    ranks = np.empty(len(scores))
    ranks[order] = np.arange(1, len(scores) + 1)
    for value in np.unique(scores):  # ties share a rank
        same = scores == value
        ranks[same] = ranks[same].mean()
    n_yes, n_no = yes.sum(), (~yes).sum()
    return float((ranks[yes].sum() - n_yes * (n_yes + 1) / 2) / (n_yes * n_no))


def refs(value: Any, found: set[str]) -> set[str]:
    if isinstance(value, dict):
        if "id" in value and not (set(value) - {"type", "id", "edge_properties"}):
            found.add(value["id"])
        for inner in value.values():
            refs(inner, found)
    elif isinstance(value, list):
        for inner in value:
            refs(inner, found)
    return found


def world_features(seed: int, people: int):
    """For each mention: the candidates' rows of features (name cosine, graph cosine, entities shared), which row is
    the person (or -1), and the hand-set score of each row"""
    world = planted.world(seed=seed, people=people)
    table = name_maths.variants_table(world.variants)
    labels = [p.label for p in world.people] + [m.label for m in world.mentions]
    rarity = name_maths.Rarity.of(name_maths.words([label], table) for label in labels)

    def name_of(label: str) -> np.ndarray:
        return np.asarray(
            name_maths.vector([label], rarity, base.NAME_DIMENSION, table), dtype=float
        )

    built = graph_maths.rebuild(base.laid_out(world), base.MAPS)
    zero = np.zeros(base.MAPS.dimension)
    ids = [p.id for p in world.people]
    names = base.unit(np.array([name_of(p.label) for p in world.people]))
    graphs = base.unit(np.array([np.asarray(built.get(i, zero), float) for i in ids]))

    named_in: dict[str, set[int]] = defaultdict(set)
    named_by: list[set[str]] = []
    for n, factoid in enumerate(world.factoids):
        named_by.append(refs(factoid, set()))
        for id in named_by[-1]:
            named_in[id].add(n)

    out = []
    for mention in world.mentions:
        own_name = name_of(mention.label)
        own_graph = np.asarray(built.get(mention.id, zero), float)
        by_name = names @ (own_name / max(np.linalg.norm(own_name), 1e-12))
        by_graph = graphs @ (own_graph / max(np.linalg.norm(own_graph), 1e-12))
        rows = sorted(
            {int(n) for n in np.argsort(-by_name, kind="stable")[:FETCH]}
            | {int(n) for n in np.argsort(-by_graph, kind="stable")[:FETCH]}
        )
        (home,) = named_in[mention.id]
        beside = named_by[home] - {mention.id}
        shared = [
            sum(
                1
                for other in beside
                # (as the service counts: a candidate the document itself names does not share itself)
                if other != ids[n] and (named_in[other] & named_in[ids[n]]) - {home}
            )
            for n in rows
        ]
        features = np.column_stack(
            [by_name[rows], by_graph[rows], np.log1p(np.array(shared, float))]
        )
        hand = (HAND[0] * by_name[rows] + HAND[1] * by_graph[rows]) / sum(HAND)
        who = [ids[n] for n in rows]
        truth = who.index(mention.person) if mention.person in who else -1
        out.append((features, truth, hand, who))
    return out


def widened(features: np.ndarray, which: str) -> np.ndarray:
    name, graph, shared = features.T
    if which == "name, graph":
        return np.column_stack([name, graph])
    if which == "name, graph, shared":
        return features
    return np.column_stack([name, graph, shared, name * graph, name * shared])


def place(order_key: np.ndarray, who: list[str], truth: int) -> int:
    if truth < 0:
        return 10**6
    order = sorted(range(len(who)), key=lambda n: (-order_key[n], who[n]))
    return order.index(truth) + 1


def top(scores: np.ndarray, features: np.ndarray) -> list[float]:
    """What the head of a list looks like: the best score, the gap to the second, the best one's features"""
    order = np.argsort(-scores, kind="stable")
    first = order[0]
    second = scores[order[1]] if len(order) > 1 else 0.0
    return [scores[first], scores[first] - second, *features[first]]


def main(people: int) -> None:
    print(f"people={people}, candidates the {FETCH} nearest by each part, shown {SHOWN}")
    for seed in (1, 2, 3):
        data = world_features(seed, people)
        rng = np.random.default_rng(seed)
        order = rng.permutation(len(data))
        test = [data[n] for n in order[len(order) // 2 :]]
        pool = [data[n] for n in order[: len(order) // 2]]
        print(f"\nseed {seed}: {len(data)} mentions, fitted on up to {len(pool)}, measured on {len(test)}")

        def rate(key, most):
            return sum(place(key(f, h), w, t) <= most for f, t, h, w in test) / len(test)

        print(
            f"  hand-set name 1, graph 0.25:   first {rate(lambda f, h: h, 1):6.1%}"
            f"   in five {rate(lambda f, h: h, 5):6.1%}"
        )
        # (a set weight for the shared entities, with no decisions at all: `log1p(shared)` beside name 1, graph 0.25)
        for weight in (0.05, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.8):

            def set_by_hand(f, h, weight=weight):
                return h * sum(HAND) + weight * f[:, 2]

            print(
                f"  hand-set with shared at {weight:4.2f}:      first {rate(set_by_hand, 1):6.1%}"
                f"   in five {rate(set_by_hand, 5):6.1%}"
            )
        for which in ("name, graph", "name, graph, shared", "with products"):
            for n in (25, 50, 100, 200, len(pool)):
                if n > len(pool):
                    continue
                xs, ys = [], []
                for features, truth, hand, who in pool[:n]:
                    shown = np.argsort(-hand, kind="stable")[:SHOWN]
                    xs.append(widened(features[shown], which))
                    ys.append((shown == truth).astype(float))
                w = fit(np.vstack(xs), np.concatenate(ys))

                def key(f, h, w=w, which=which):
                    return said(w, widened(f, which))

                print(
                    f"  fitted [{which}] on {n:4d}: first {rate(key, 1):6.1%}   in five {rate(key, 5):6.1%}"
                    + (f"   weights {np.round(w, 2).tolist()}" if n == len(pool) else "")
                )

        # -- someone new: the person taken out of half the lists ----------------------------------------------------
        w = fit(
            np.vstack([widened(f[np.argsort(-h, kind="stable")[:SHOWN]], "name, graph, shared") for f, t, h, _ in pool]),
            np.concatenate([(np.argsort(-h, kind="stable")[:SHOWN] == t).astype(float) for f, t, h, _ in pool]),
        )

        def heads(items):
            rows, new = [], []
            for n, (features, truth, hand, who) in enumerate(items):
                gone = n % 2 == 0 or truth < 0
                keep = np.array([k for k in range(len(who)) if not (gone and k == truth)])
                f, h = features[keep], hand[keep]
                with_shared = h * sum(HAND) + SHARED * f[:, 2]
                rows.append([*top(h, f), *top(said(w, f), f), *top(with_shared, f)])
                new.append(gone)
            return np.array(rows), np.array(new)

        fit_rows, fit_new = heads(pool)
        test_rows, test_new = heads(test)
        print(f"  someone new ({test_new.mean():.0%} of the measured lists have the person taken out):")
        print(f"    AUC by the best hand-set score:        {auc(-test_rows[:, 0], test_new):.3f}")
        print(f"    AUC by the best fitted likelihood:     {auc(-test_rows[:, 5], test_new):.3f}")
        print(f"    AUC by the best hand-set score with shared at {SHARED}: {auc(-test_rows[:, 10], test_new):.3f}")
        print(f"    AUC by that one's gap to the next:      {auc(-test_rows[:, 11], test_new):.3f}")
        print(f"    AUC by the best one's shared entities:  {auc(-test_rows[:, 14], test_new):.3f}")
        print(f"    AUC by the best one's name cosine:      {auc(-test_rows[:, 12], test_new):.3f}")
        hand_rows = np.column_stack([fit_rows[:, 10:15]]), np.column_stack([test_rows[:, 10:15]])
        for n in (50, 200, len(pool)):
            if n <= len(pool):
                by_hand = fit(hand_rows[0][:n], fit_new[:n].astype(float))
                p = said(by_hand, hand_rows[1])
                print(f"    a model over the hand-set head alone, fitted on {n:4d}: AUC {auc(p, test_new):.3f}, right {((p > 0.5) == test_new).mean():.1%}")
        for n in (50, 200, len(pool)):
            if n > len(pool):
                continue
            second = fit(fit_rows[:n], fit_new[:n].astype(float))
            p = said(second, test_rows)
            right = ((p > 0.5) == test_new).mean()
            print(f"    a second model over the head, fitted on {n:4d}: AUC {auc(p, test_new):.3f}, right {right:.1%}")


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 3000)
