"""Pairs of statements through the nearest ENTITIES (step 6.4 of implementation_docs/spaces-and-comparison-plan.md,
as the user decided it): for each identifying entity X of a statement, the entities nearest it by a profile that
knows names, and the rule of 6.3 with each such X' in X's place. On the planted world for comparison, with no
database (as `compare_vectors.py`): the graph part a whole rebuild of the structural network in memory, the name
part by `pangloss_names.maths`, a profile's score `Σ w·cos / Σ w` (what `nearest` gives where both have every part).

    uv run python notes/similarity-evaluation/compare_entities.py [--people 5000] [--seeds 1 2 3]

The world is the one of `compare_vectors.py`'s row "mention": a birth told twice, the second telling naming the
person's mention (a `Person` of its own: two entities not yet reconciled), so that the rule finds no pair.

Printed:

(1) for each mention and its person, where the one is among the other's nearest people, its score, and the score of
    the nearest person who is not it;
(2) by `COMPARE_NEAR` and `COMPARE_NEAR_K`: the share of the right entities kept, and how many wrong ones a person
    is given;
(3) end to end, for every statement of a compared class: the planted births found and read as the truth has them,
    and the other pairs it brings (through the right entity, and through a wrong one), by what the verdict says.
"""

import argparse
import collections
import copy
import dataclasses
import statistics
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "packages/pangloss-fastrp/tests"))  # fmt: skip
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "packages/pangloss-compare/tests"))  # fmt: skip

import compare_vectors  # noqa: E402
import spaces_graph  # noqa: E402

PROFILES = {
    "name alone": (1.0, 0.0),
    "who (name 1, graph 0.25)": (1.0, 0.25),
    "name 1, graph 0.5": (1.0, 0.5),
    "graph alone": (0.0, 1.0),
}
WHO = "who (name 1, graph 0.25)"
NEARS = (0.5, 0.6, 0.7, 0.75, 0.8, 0.85, 0.9)
KS = (3, 5, 10)
MOST = max(KS)


def changed_world(world):
    """The world with the second telling of each birth told twice naming the person's mention, where there is one;
    and the pairs so changed"""
    mention_of = {mention.person: mention for mention in world.mentions}
    births = [v for v in world.verdicts if v.case.startswith("birth")]
    chosen = [v for v in births if world.statement(v.a)["person"]["id"] in mention_of]
    by_label = {factoid["label"]: n for n, factoid in enumerate(world.factoids)}
    changed = copy.copy(world)
    changed.factoids = list(world.factoids)
    changed._factoids = None
    for verdict in chosen:
        told = world.told[verdict.b]
        factoid = copy.deepcopy(world.factoids[by_label[told.factoid]])
        [statement] = factoid["statements"]
        statement["person"] = {"type": "Person", "id": mention_of[statement["person"]["id"]].id}  # fmt: skip
        changed.factoids[by_label[told.factoid]] = factoid
    return changed, chosen


def graph_vectors(world, maps, known):
    """The ids of the people (the mentions among them) and their graph vectors, a row each at length one (zeros
    where there is none)"""
    from pangloss_fastrp.maths import rebuild

    graph, way_maps = spaces_graph.graph_of(world, maps, known, "stop-not")
    vectors = spaces_graph.unit(rebuild(graph, way_maps))
    ids = [e["id"] for e in world.entities if e["type"] == "Person"]
    zero = np.zeros(way_maps.dimension, dtype=np.float32)
    return ids, np.stack([vectors.get(id, zero) for id in ids]).astype(np.float32)


def name_vectors(world, table):
    """The name vectors of the people, in the same order"""
    from pangloss_names import maths as names

    labels = [e["label"] for e in world.entities if e["type"] == "Person"]
    rarity = names.Rarity.of(names.words([label], table) for label in labels)
    by_name = np.zeros((len(labels), 256), dtype=np.float32)
    for n, label in enumerate(labels):
        made = names.vector([label], rarity, 256, table)
        if made is not None:
            by_name[n] = made
    return by_name


def nearest(by_graph, by_name, weights, most):
    """For each person, the `most` nearest others and their scores, nearest first"""
    name, graph = weights
    found = np.zeros((len(by_graph), most), dtype=np.int64)
    scores = np.zeros((len(by_graph), most), dtype=np.float32)
    for start in range(0, len(by_graph), 1000):
        rows = slice(start, start + 1000)
        chunk = (name * (by_name[rows] @ by_name.T) + graph * (by_graph[rows] @ by_graph.T)) / (name + graph)  # fmt: skip
        chunk[np.arange(chunk.shape[0]), np.arange(start, start + chunk.shape[0])] = -2.0  # fmt: skip
        top = np.argpartition(-chunk, most, axis=1)[:, :most]
        order = np.argsort(-np.take_along_axis(chunk, top, axis=1), axis=1)
        found[rows] = np.take_along_axis(top, order, axis=1)
        scores[rows] = np.take_along_axis(chunk, found[rows], axis=1)
    return found, scores


def score_of(by_graph, by_name, weights, a, b):
    name, graph = weights
    return float(name * (by_name[a] @ by_name[b]) + graph * (by_graph[a] @ by_graph[b])) / (name + graph)  # fmt: skip


def place_of(by_graph, by_name, weights, a, b):
    """Where `b` is among the people nearest `a` (1: the nearest), those as near counted before it"""
    name, graph = weights
    scores = (name * (by_name @ by_name[a]) + graph * (by_graph @ by_graph[a])) / (name + graph)  # fmt: skip
    scores[a] = -2.0
    return int((scores >= scores[b] - 1e-6).sum())


def in_place(statement, old: str, new: str):
    """The statement with `new` wherever it names `old`"""
    fields = {name: frozenset(new if e == old else e for e in found) for name, found in statement.fields.items()}  # fmt: skip
    return dataclasses.replace(statement, fields=fields)


def end_to_end(world, chosen, ids, found, scores, t, maths):
    """For each `COMPARE_NEAR` and `COMPARE_NEAR_K`: what the pairs through the nearest people are"""
    statements, event_of = t.statements_of(world)
    row = {id: n for n, id in enumerate(ids)}
    same = {}
    for mention in world.mentions:
        same[mention.id], same[mention.person] = mention.person, mention.id
    truth = {frozenset((v.a, v.b)): v for v in world.verdicts}
    wanted = {frozenset((v.a, v.b)) for v in chosen}
    naming = collections.defaultdict(list)
    for number, statement in enumerate(statements):
        for field in t.RULES[statement.type].identifying:
            for entity in statement.fields.get(field, ()):
                naming[field, entity].append(number)
    by_rule = {frozenset((a.id, b.id)) for a, b in t.pairs_by_rule(statements)}
    out = {}
    relations = collections.defaultdict(collections.Counter)
    for near in NEARS:
        for k in KS:
            count = collections.Counter()
            right_found = set()
            for number, statement in enumerate(statements):
                # (each other statement once: through the right entity where it is reached through several)
                reached: dict[int, tuple[str, str]] = {}
                for field in t.RULES[statement.type].identifying:
                    for entity in statement.fields.get(field, ()):
                        if entity not in row:
                            continue
                        count["searches"] += 1
                        for other, score in zip(found[row[entity]][:k], scores[row[entity]][:k], strict=True):  # fmt: skip
                            if score < near:
                                break
                            other_id = ids[other]
                            count["entities given"] += 1
                            for n in naming.get((field, other_id), ()):
                                against = statements[n]
                                if n == number or frozenset((statement.id, against.id)) in by_rule:  # fmt: skip
                                    continue
                                if not maths.common_class(statement, against):
                                    continue
                                if n not in reached or same.get(entity) == other_id:
                                    reached[n] = (entity, other_id)
                shown = False
                for n, (entity, other_id) in reached.items():
                    against = statements[n]
                    pair = frozenset((statement.id, against.id))
                    said = maths.verdict(statement, in_place(against, other_id, entity), t.RULES)  # fmt: skip
                    through = "right" if same.get(entity) == other_id else "wrong"
                    related = said.relation not in ("two", "nothing")
                    shown = shown or related
                    count[through, "pairs"] += 1
                    count[through, "said to be related"] += related
                    if related:
                        relations[near, k][through, statement.type, said.relation] += 1
                    # (the same with "once per" not taken as certain: the logistic decides, as of any two)
                    rules = t.RULES[maths.common_class(statement, against)]
                    if rules.once_per:
                        loose = {name: dataclasses.replace(r, once_per=None) for name, r in t.RULES.items()}  # fmt: skip
                        weighed = maths.verdict(statement, in_place(against, other_id, entity), loose)  # fmt: skip
                    else:
                        weighed = said
                    if weighed.relation not in ("two", "nothing"):
                        count[through, "weighed"] += 1
                        if pair in wanted and weighed.relation == truth[pair].relation:
                            count["planted", "weighed"] += 1
                    if pair in wanted:
                        planted = truth[pair]
                        if said.relation == planted.relation and sorted(said.fields) == sorted(planted.fields):  # fmt: skip
                            right_found.add((pair, statement.id == planted.a))
                    elif through == "right":
                        count["right", "rightly one event or not"] += said.one_event == (event_of[statement.id] == event_of[against.id])  # fmt: skip
                count["statements"] += 1
                count["statements with a pair"] += bool(reached)
                count["statements shown a pair"] += shown
            count["planted, from the first telling"] = sum(1 for _, first in right_found if first)  # fmt: skip
            count["planted, from the second telling"] = sum(1 for _, first in right_found if not first)  # fmt: skip
            out[near, k] = count
    return out, relations, len(statements)


def main() -> None:
    import test_compare_maths as t
    from pangloss_compare import maths
    from pangloss_names import maths as names
    from pangloss_testing import planted

    parser = argparse.ArgumentParser()
    parser.add_argument("--people", type=int, default=5000)
    parser.add_argument("--seeds", type=int, nargs="+", default=[1, 2, 3])
    args = parser.parse_args()
    maps, known = compare_vectors.declared()
    places = collections.defaultdict(list)
    own = collections.defaultdict(list)
    other = collections.defaultdict(list)
    kept = collections.Counter()
    wrong = collections.defaultdict(list)
    ends = collections.Counter()
    relations = collections.defaultdict(collections.Counter)
    pairs = statements = 0
    for seed in args.seeds:
        started = time.perf_counter()
        world, chosen = changed_world(planted.world(seed=seed, people=args.people, compared=True))  # fmt: skip
        pairs += len(chosen)
        ids, by_graph = graph_vectors(world, maps, known)
        row = {id: n for n, id in enumerate(ids)}
        for with_table in (False, True):
            by_name = name_vectors(world, names.variants_table(world.variants) if with_table else {})  # fmt: skip
            for profile, weights in PROFILES.items():
                key = (profile, with_table)
                found, scores = nearest(by_graph, by_name, weights, MOST + 1)
                for mention in world.mentions:
                    a, b = row[mention.person], row[mention.id]
                    for one, two in ((a, b), (b, a)):
                        places[key].append(place_of(by_graph, by_name, weights, one, two))  # fmt: skip
                        score = score_of(by_graph, by_name, weights, one, two)
                        own[key].append(score)
                        others = [s for n, s in zip(found[one], scores[one], strict=True) if n != two]  # fmt: skip
                        other[key].append(float(others[0]))
                        for near in NEARS:
                            for k in KS:
                                inside = two in found[one][:k] and score >= near
                                kept[key, near, k] += inside
                kept[key, "asked"] += 2 * len(world.mentions)
                for near in NEARS:
                    for k in KS:
                        above = (scores[:, :k] >= near).sum(axis=1)
                        wrong[key, near, k].append(float(above.sum()))
                wrong[key, "people"].append(len(ids))
                if profile == WHO and with_table:
                    result, related, count = end_to_end(world, chosen, ids, found, scores, t, maths)  # fmt: skip
                    statements += count
                    for cell, counted in related.items():
                        relations[cell].update(counted)
                    for cell, counted in result.items():
                        for name, value in counted.items():
                            ends[cell, name] += value
        print(f"seed {seed}: {len(world.people)} people, {len(world.mentions)} mentions, {len(chosen)} births told twice whose second telling names the mention ({time.perf_counter() - started:.0f} s)", flush=True)  # fmt: skip

    print(
        "\n(1) A mention and its person: where the one is among the other's nearest people (both ways about)"
    )
    print(f"{'':44}{'first':>7}{'in 3':>7}{'in 5':>7}{'in 10':>7}   its score (10%, median, 90%)   the nearest other's (10%, median, 90%)")  # fmt: skip

    def spread(values):
        values = sorted(values)
        return f"{values[len(values) // 10]:.2f}, {statistics.median(values):.2f}, {values[9 * len(values) // 10]:.2f}"  # fmt: skip

    for with_table in (False, True):
        print("  with the table of variants" if with_table else "  without the table of variants")  # fmt: skip
        for profile in PROFILES:
            key = (profile, with_table)
            found = np.array(places[key])
            print(f"    {profile:<40}" + "".join(f"{(found <= most).mean():>7.2f}" for most in (1, 3, 5, 10)) + f"   {spread(own[key]):<28}   {spread(other[key])}")  # fmt: skip

    for with_table in (False, True):
        key = (WHO, with_table)
        people = sum(wrong[key, "people"])
        print(f"\n(2) `{WHO}`, {'with' if with_table else 'without'} the table of variants: the right one kept (share), and the people a search gives besides (mean a person)")  # fmt: skip
        print(f"{'COMPARE_NEAR':>14}" + "".join(f"{f'k = {k}':>22}" for k in KS))
        for near in NEARS:
            cells = []
            for k in KS:
                right = kept[key, near, k]
                given = sum(wrong[key, near, k])
                cells.append(f"{right / kept[key, 'asked']:.2f}, {(given - right) / people:.2f} others")  # fmt: skip
            print(f"{near:>14}" + "".join(f"{cell:>22}" for cell in cells))

    print(f"\n(3) End to end, `{WHO}` with the table: every statement of a compared class ({statements:,}), {pairs} planted births the rule cannot find. A pair is shown where the verdict, with the one read as the other, is neither `two` nor `nothing`")  # fmt: skip
    print(f"{'near':>6}{'k':>4}   {'planted births read right':<28}{'other pairs through the right entity':<40}{'pairs through a wrong entity':<32}{'statements':<24}{'searches, entities':<22}{'"once per" weighed, not certain'}")  # fmt: skip
    print(f"{'':13}{'from the 1st, the 2nd':<28}{'worked out, shown, rightly one or two':<40}{'worked out, shown':<32}{'with a pair shown':<24}{'a statement':<22}{'planted right (of both ways), wrong shown'}")  # fmt: skip
    for near in NEARS:
        for k in KS:
            cell = (near, k)
            first, second = ends[cell, "planted, from the first telling"], ends[cell, "planted, from the second telling"]  # fmt: skip
            right, right_related = ends[cell, ("right", "pairs")], ends[cell, ("right", "said to be related")]  # fmt: skip
            judged = ends[cell, ("right", "rightly one event or not")]
            others = right - first - second
            bad, bad_related = ends[cell, ("wrong", "pairs")], ends[cell, ("wrong", "said to be related")]  # fmt: skip
            print(
                f"{near:>6}{k:>4}   {f'{first / pairs:.2f}, {second / pairs:.2f}':<28}"
                f"{f'{others:,}, {right_related - first - second:,}, {judged / others if others else 1:.3f}':<40}"
                f"{f'{bad:,}, {bad_related:,}':<32}"
                f"{ends[cell, 'statements shown a pair'] / ends[cell, 'statements']:<24.4f}"
                + f"{ends[cell, 'searches'] / ends[cell, 'statements']:.1f}, {ends[cell, 'entities given'] / ends[cell, 'statements']:.1f}".ljust(
                    22
                )
                + f"{ends[cell, ('planted', 'weighed')] / (2 * pairs):.2f}, {ends[cell, ('wrong', 'weighed')]:,}"
            )
    for cell in ((0.6, 5), (0.7, 5), (0.8, 5)):
        print(f"\nThe pairs shown at {cell[0]}, k = {cell[1]}, by the entity they came through, the class and what the verdict says:")  # fmt: skip
        for (through, kind, relation), n in sorted(relations[cell].items()):
            print(f"    {through:<7}{kind:<18}{relation:<24}{n:>7,}")


if __name__ == "__main__":
    main()
