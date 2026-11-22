"""Before step 8.3: what the name and the graph give together on the large planted world, the graph vectors read
from the scratch Memgraph (as `planted.py base` left them) and the name vectors made here by `pangloss_names.maths`.
For each mention, the place of the person it is among the people, by `Σ w·cos / Σ w` (what a profile gives).

    uv run python notes/similarity-evaluation/names_with_graph.py /tmp/planted/large bolt://localhost:7706
"""

import json
import sys
from pathlib import Path

import neo4j
import numpy as np
from pangloss_names import maths

truth = json.loads((Path(sys.argv[1]) / "truth.json").read_text())
people = truth["people"]
mentions = truth["mentions"]
graph: dict[str, list[float]] = {}
with neo4j.GraphDatabase.driver(sys.argv[2], auth=("test", "test")) as driver, driver.session() as session:
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


zero = [0.0] * len(next(iter(graph.values())))
graph_people = unit([graph.get(p["id"], zero) for p in people])
graph_mentions = unit([graph.get(m["id"], zero) for m in mentions])
row = {p["id"]: n for n, p in enumerate(people)}
right = np.array([row[m["person"]] for m in mentions])
print(f"{len(people):,} people, {len(mentions):,} mentions; first counts every person as near as the right one before them")
for with_table in (False, True):
    table = maths.variants_table(truth["variants"]) if with_table else {}
    names = [p["label"] for p in people] + [m["label"] for m in mentions]
    rarity = maths.Rarity.of(maths.words([name], table) for name in names)
    made = np.array([maths.vector([name], rarity, 256, table) for name in names], dtype=np.float32)
    name_people, name_mentions = made[: len(people)], made[len(people) :]
    print("with the table of variants" if with_table else "without the table of variants")
    for name_weight, graph_weight in ((1, 0), (0, 1), (1, 0.25), (1, 0.5), (1, 1), (0.5, 1), (0.25, 1)):
        places = []
        for start in range(0, len(mentions), 500):
            chunk = slice(start, start + 500)
            scores = (name_weight * (name_mentions[chunk] @ name_people.T)
                      + graph_weight * (graph_mentions[chunk] @ graph_people.T))
            own = scores[np.arange(scores.shape[0]), right[chunk]]
            places += list((scores >= own[:, None] - 1e-6).sum(axis=1))
        places = np.array(places)
        print(f"  name {name_weight:g}, graph {graph_weight:g}: right first {100 * (places <= 1).mean():5.1f}%, "
              f"in five {100 * (places <= 5).mean():5.1f}%, in ten {100 * (places <= 10).mean():5.1f}%")
