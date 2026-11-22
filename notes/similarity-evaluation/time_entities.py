"""Step 9.4: is a time vector for an entity worth having? On the dated planted world: who a mention is, among the
people, by the name (made here, with the table of variants), the graph (the stored vectors of the scratch
database) and a time vector of each person made here from the truth: of the dates of the factoids that name them,
either each date added (`dates`) or one period from the first to the last (`span`).

    uv run python notes/similarity-evaluation/time_entities.py bolt://localhost:7702 --people 6000
"""

import argparse
import sys

import neo4j
import numpy as np
from pangloss_dates_vectors import maths as time_maths
from pangloss_names import maths as name_maths
from pangloss_testing import planted

sys.path.insert(0, "packages/pangloss-dates-vectors/tests")
import time_planted_support as support  # noqa: E402

parser = argparse.ArgumentParser()
parser.add_argument("url")
parser.add_argument("--people", type=int, default=32_000)
parser.add_argument("--seed", type=int, default=1)
parser.add_argument("--user", default="test")
parser.add_argument("--password", default="test")
args = parser.parse_args()
world = planted.world(seed=args.seed, people=args.people, dated=True)
people, mentions = world.people, world.mentions


def references(value):
    if isinstance(value, dict):
        if set(value) >= {"type", "id"} and value["type"] == "Person":
            yield value["id"]
        for inner in value.values():
            yield from references(inner)
    elif isinstance(value, list):
        for inner in value:
            yield from references(inner)


named: dict[str, list[time_maths.Bounds]] = {}
for factoid in world.factoids:
    bounds = support.bounds_of(world.dates[factoid["label"]])
    for id in set(references(factoid["statements"])):
        named.setdefault(id, []).append(bounds)

graph: dict[str, list[float]] = {}
with neo4j.GraphDatabase.driver(args.url, auth=(args.user, args.password)) as driver, driver.session() as session:
    generation = session.run("MATCH (s:PGVectorState {part: 'graph'}) RETURN s.generation AS g").single()["g"]
    after = ""
    while True:
        rows = session.run(
            "MATCH (v:PGVector) WHERE v.of > $after AND v.part = 'graph' AND v.generation = $g AND v.type = 'Person' "
            "RETURN v.of AS of, v.vector AS vector ORDER BY v.of LIMIT 5000", after=after, g=generation,
        ).values()
        if not rows:
            break
        graph.update(rows)
        after = rows[-1][0]


def unit(rows):
    made = np.array(rows, dtype=np.float32)
    lengths = np.linalg.norm(made, axis=1, keepdims=True)
    return made / np.where(lengths == 0, 1, lengths)


ids = [p.id for p in people] + [m.id for m in mentions]
zero = [0.0] * len(next(iter(graph.values())))
graphs = unit([graph.get(id, zero) for id in ids])
table = name_maths.variants_table(world.variants)
labels = [p.label for p in people] + [m.label for m in mentions]
rarity = name_maths.Rarity.of(name_maths.words([label], table) for label in labels)
names = np.array([name_maths.vector([label], rarity, 256, table) for label in labels], dtype=np.float32)
ring = time_maths.Ring()
owners = [n for n, id in enumerate(ids) for _ in named.get(id, [])]
dates = time_maths.of_items([b for id in ids for b in named.get(id, [])], owners, len(ids), ring)
spans = unit([
    time_maths.vectors([(min(b[0] for b in named[id]), min(b[1] for b in named[id]),
                         max(b[2] for b in named[id]), max(b[3] for b in named[id]))], ring)[0]
    if id in named else np.zeros(ring.dimension)
    for id in ids
])
count = len(people)
right = np.array([{p.id: n for n, p in enumerate(people)}[m.person] for m in mentions])
print(f"{count:,} people, {len(mentions):,} mentions; {sum(1 for p in people if p.id in named):,} people and "
      f"{sum(1 for m in mentions if m.id in named):,} mentions named by a dated factoid; a place counts every person "
      "as near as the right one before them")


def said(parts) -> str:
    places = []
    for start in range(0, len(mentions), 500):
        chunk = slice(count + start, count + start + 500)
        scores = sum(weight * (vectors[chunk] @ vectors[:count].T) for vectors, weight in parts)
        own = scores[np.arange(scores.shape[0]), right[start : start + 500]]
        places += list((scores >= own[:, None] - 1e-6).sum(axis=1))
    places = np.array(places)
    return (f"right first {100 * (places == 1).mean():.1f}%, in five {100 * (places <= 5).mean():.1f}%, "
            f"in ten {100 * (places <= 10).mean():.1f}%")


for label, base in (("name 1", [(names, 1)]), ("name 1 + graph 0.25", [(names, 1), (graphs, 0.25)]),
                    ("name 1 + graph 0.1", [(names, 1), (graphs, 0.1)])):
    print(f"{label:<34} {said(base)}")
    for kind, times in (("dates", dates), ("span", spans)):
        for weight in (0.1, 0.25, 0.5):
            print(f"  + time ({kind}) {weight:<19g} {said([*base, (times, weight)])}")
