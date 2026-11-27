"""Whether vectors find a pair of statements that the rule cannot (step 6.4 of
implementation_docs/spaces-and-comparison-plan.md), on the planted world for comparison, with no database (as
`spaces_graph.py`: the world a graph in memory, the structural network of the graph part, a whole rebuild).

    uv run python notes/similarity-evaluation/compare_vectors.py [--people 5000] [--seeds 1 2 3]

A birth is told twice (the planted cases `birth_*`); `person` is its only identifying field, so with another node in
that field of the second telling the rule (6.3) finds no pair. Three worlds, the same but for that node:

    same        the person themself (what the rule finds: the control)
    mention     the person's mention: a `Person` of its own, named once elsewhere with their family and group (two
                entities not yet reconciled: "one event if X and X' are one person")
    stand-in    a stand-in (`Mention`, a document of that factoid alone: not reconciled at all)

Printed for each: where the other telling is among the first's nearest births (first, in ten), its cosine, and the
cosine of the nearest birth that is not it (what a threshold has to tell it from).
"""

import argparse
import copy
import statistics
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "packages/pangloss-fastrp/tests"))  # fmt: skip

import spaces_graph  # noqa: E402

WORLDS = ("same", "mention", "stand-in")


def declared():
    import conftest

    conftest.make_settings()
    from pangloss_fastrp import maps
    from pangloss_models import hooks, spaces
    from pangloss_testing.similar_models import declare, mention_stand_in

    stand_in = mention_stand_in()
    hooks.stand_ins.append(stand_in)
    try:
        declare(compared=True, stand_in=True)
        maps.forget()
        return maps.build_maps(), spaces.registered_spaces()
    finally:
        hooks.stand_ins.remove(stand_in)


def measure(world, maps, known):
    from pangloss_fastrp.maths import rebuild

    mention_of = {mention.person: mention for mention in world.mentions}
    births = [v for v in world.verdicts if v.case.startswith("birth")]
    chosen = [v for v in births if world.statement(v.a)["person"]["id"] in mention_of]
    by_label = {factoid["label"]: n for n, factoid in enumerate(world.factoids)}
    out = {}
    for which in WORLDS:
        changed = copy.copy(world)
        changed.factoids = list(world.factoids)
        changed._factoids = None
        for verdict in chosen:
            told = world.told[verdict.b]
            factoid = copy.deepcopy(world.factoids[by_label[told.factoid]])
            [statement] = factoid["statements"]
            mention = mention_of[statement["person"]["id"]]
            if which == "mention":
                statement["person"] = {"type": "Person", "id": mention.id}
            elif which == "stand-in":
                statement["person"] = {"type": "Mention", "label": mention.label, "mentioned_type": "Person"}  # fmt: skip
            changed.factoids[by_label[told.factoid]] = factoid
        graph, way_maps = spaces_graph.graph_of(changed, maps, known, "stop-not")
        vectors = spaces_graph.unit(rebuild(graph, way_maps))
        ids = [id for id, node in graph.node.items() if node.type == "Birth" and id in vectors]  # fmt: skip
        row = {id: n for n, id in enumerate(ids)}
        matrix = np.stack([vectors[id] for id in ids])
        first = ten = 0
        own, other = [], []
        for verdict in chosen:
            scores = matrix @ vectors[verdict.a]
            scores[row[verdict.a]] = -2.0
            score = float(scores[row[verdict.b]])
            rank = int((scores > score).sum()) + 1
            first += rank == 1
            ten += rank <= 10
            own.append(score)
            scores[row[verdict.b]] = -2.0
            other.append(float(scores.max()))
        out[which] = (len(chosen), first, ten, own, other, len(ids))
    return out


def main() -> None:
    from pangloss_testing import planted

    parser = argparse.ArgumentParser()
    parser.add_argument("--people", type=int, default=5000)
    parser.add_argument("--seeds", type=int, nargs="+", default=[1, 2, 3])
    args = parser.parse_args()
    maps, known = declared()
    runs = []
    for seed in args.seeds:
        world = planted.world(seed=seed, people=args.people, compared=True)
        runs.append(measure(world, maps, known))
        n, *_, births = runs[-1]["same"]
        print(f"seed {seed}: {len(world.people)} people, {births} births told, {n} told twice of a person with a mention", flush=True)  # fmt: skip
    print(f"\n{'':10}{'pairs':>7}{'first':>8}{'in ten':>8}   the pair's cosine (10%, median, 90%)   the nearest other birth's (10%, median, 90%)")  # fmt: skip
    for which in WORLDS:
        n = sum(run[which][0] for run in runs)
        first = sum(run[which][1] for run in runs)
        ten = sum(run[which][2] for run in runs)
        own = sorted(x for run in runs for x in run[which][3])
        other = sorted(x for run in runs for x in run[which][4])

        def spread(values):
            return f"{values[len(values) // 10]:.2f}, {statistics.median(values):.2f}, {values[9 * len(values) // 10]:.2f}"

        print(f"{which:<10}{n:>7}{first / n:>8.2f}{ten / n:>8.2f}   {spread(own):<38}   {spread(other)}")  # fmt: skip
    for threshold in (0.5, 0.6, 0.7, 0.8):
        cells = []
        for which in WORLDS:
            own = [x for run in runs for x in run[which][3]]
            other = [x for run in runs for x in run[which][4]]
            cells.append(f"{which}: pair above {sum(x >= threshold for x in own) / len(own):.2f}, another birth above {sum(x >= threshold for x in other) / len(other):.2f}")  # fmt: skip
        print(f"at {threshold}: " + "; ".join(cells))


if __name__ == "__main__":
    main()
