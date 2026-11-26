"""What the graph part of similarity does with statements in semantic spaces, on the planted world for comparison
(`pangloss_testing.planted.world(compared=True)`): step 5.3 of implementation_docs/spaces-and-comparison-plan.md.
No database: the world's payloads are made a graph in memory (`pangloss_fastrp.memory.MemoryReader`), the maps are
those of the declared models (`pangloss_fastrp.maps.build_maps`), and the vectors a whole rebuild by the pure maths.

    uv run python notes/similarity-evaluation/spaces_graph.py [--people 1500] [--seeds 1 2 3]

The ways compared (each a rule for the joins of a statement, by what the walk says of it):

    through     every space a plain wrapper: what is denied, ordered or reported joins as what is asserted (today,
                for a space with no `FastRPMeta`)
    stop-not    `FastRPMeta(stop=True)` on `Negative` as it is today: the chain from the factoid ends at the space;
                the statement inside keeps its own joins (step 0.2)
    cut-not     a denied statement (the walk: -1) joins nothing at all: it is left out of the graph
    by-walk     as cut-not, and a statement neither asserted nor denied joins at a weight: by its degree where it
                leans for (expected 0.8, likely 0.6, possible 0.4, none entered and no default 0.5), 0 where it
                leans against or neither way
    asserted    only what is asserted (the walk: 1): the network of what the sources say happened

What is printed: (1) how alike two entities come out that a planted case ties only by what did not happen, or only
by what was prescribed; (2) whether the other statement of a planted pair is among a statement's ten nearest
statements (what comparison's pairs by vectors need); (3) how far the ten nearest people of a person are those of
`asserted`.
"""

import argparse
import collections
import dataclasses
import random
import sys
import typing
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "packages/pangloss-fastrp/tests"))  # fmt: skip

WAYS = ("through", "stop-not", "cut-not", "by-walk", "asserted")
DEGREE_WEIGHT = {"expected": 0.8, "likely": 0.6, "possible": 0.4, "unlikely": 0.2, "impossible": 0.0, None: 0.5}  # fmt: skip
STATEMENTS = ("Activity", "Transfer", "MemberOf", "ChildOf", "Sibling", "Birth", "Making", "MakingOfPicture", "Attendance", "Order", "Rule")  # fmt: skip


def declared():
    """The models for comparison, and the graph part's maps of them"""
    import conftest  # (pangloss-fastrp's tests: settings for the models alone)

    conftest.make_settings()
    from pangloss_fastrp import maps
    from pangloss_models import spaces
    from pangloss_testing.similar_models import declare

    declare(compared=True)
    maps.forget()
    return maps.build_maps(), spaces.registered_spaces()


def weight_of(signature, way: str) -> float:
    """The weight of a statement's joins, by the way and what the walk says of it; 0: it is left out"""
    if signature.veridical == 1 or way in ("through", "stop-not"):
        return 1.0
    if signature.veridical == -1 or way == "asserted":
        return 0.0
    if way == "cut-not":
        return 1.0
    return DEGREE_WEIGHT[signature.degree] if signature.lean == "for" else 0.0


def graph_of(world, maps, known, way: str):
    """The world as a graph in memory, by the way; and the maps to embed it with"""
    from pangloss_fastrp.maths import END, Edge, Node
    from pangloss_fastrp.memory import MemoryReader
    from pangloss_models.spaces import signature

    graph = MemoryReader()
    kinds, weights = dict(maps.kinds), dict(maps.class_weight)
    documents, field_weight = dict(maps.documents), dict(maps.field_weight)
    if way != "through":
        kinds["Negative"] = END
    count = [0]
    for entity in world.entities:
        graph.add(Node(entity["id"], entity["type"]))

    def is_reference(value: dict) -> bool:
        return "id" in value and set(value) <= {"type", "id", "edge_properties"}

    def add(payload: dict, path: list[dict]) -> str | None:
        type_name = payload["type"]
        count[0] += 1
        id = payload.get("label") if type_name in STATEMENTS else None
        id = f"{id or type_name} #{count[0]}" if id not in world.told else id
        if type_name in STATEMENTS and any(e["kind"] == "space" for e in path):
            weight = weight_of(signature(path, known), way)
            if weight == 0.0:
                return None
            if weight != 1.0:
                # (a class of its own for the weight: the maps weigh by class)
                weighted = f"{type_name}@{weight}"
                kinds[weighted], documents[weighted] = kinds[type_name], True
                weights[weighted] = weight * weights.get(type_name, 1.0)
                for key, value in list(field_weight.items()):
                    if key.startswith(f"{type_name}."):
                        field_weight[f"{weighted}.{key.split('.', 1)[1]}"] = value
                type_name = weighted
        graph.add(Node(id, type_name))
        kind = "space" if payload["type"] in known else "document"
        for field, value in payload.items():
            for inner in value if isinstance(value, list) else [value]:
                if not isinstance(inner, dict) or "type" not in inner:
                    continue
                properties = inner.get("edge_properties", {})
                if is_reference(inner):
                    graph.link(Edge(id, inner["id"], field, properties))
                    continue
                entry = {"kind": kind, "type": payload["type"], "id": id, "field": field}  # fmt: skip
                if kind == "space" and payload.get("how_likely"):
                    entry["degree"] = payload["how_likely"]
                child = add(inner, [*path, entry])
                if child is not None:
                    graph.link(Edge(id, child, field, properties))
        return id

    for factoid in world.factoids:
        add(factoid, [])
    return graph, dataclasses.replace(
        maps,
        kinds=kinds,
        class_weight=weights,
        documents=documents,
        field_weight=field_weight,
    )


def unit(vectors: dict[str, np.ndarray]) -> dict[str, np.ndarray]:
    """The vectors at length one; those of length nothing left out"""
    made = {}
    for id, vector in vectors.items():
        length = float(np.linalg.norm(vector))
        if length > 0:
            made[id] = vector / length
    return made


def entity_pairs(world) -> dict[str, list[tuple[str, str]]]:
    """Two entities a planted case ties, by the case"""
    found: dict[str, list[tuple[str, str]]] = collections.defaultdict(list)
    for told in world.told.values():
        statement = world.statement(told.label)
        if told.case.startswith("absence"):
            found[told.case].append((statement["attended_by"]["id"], statement["assembly_of"]["id"]))  # fmt: skip
    for verdict in world.verdicts:
        if (
            world.told[verdict.a].order is not None
            and verdict.relation != "orders_at_odds"
        ):
            thing = world.statement(verdict.a)
            found[verdict.case].append((thing["given_by"]["id"], thing["given_to"]["id"]))  # fmt: skip
    rng = random.Random(world.seed)
    people = [person.id for person in world.people]
    found["two people at random"] = [tuple(rng.sample(people, 2)) for _ in range(2000)]  # fmt: skip
    groups = [group["id"] for group in world.groups]
    found["a person and a group at random"] = [(rng.choice(people), rng.choice(groups)) for _ in range(2000)]  # fmt: skip
    return found


def measure(world, maps, known) -> dict[str, typing.Any]:
    from pangloss_fastrp.maths import rebuild

    people = [person.id for person in world.people]
    pairs = entity_pairs(world)
    out: dict[str, typing.Any] = {"alike": {}, "found": {}, "none": {}, "people": {}}
    nearest_people: dict[str, np.ndarray] = {}
    for way in WAYS:
        graph, way_maps = graph_of(world, maps, known, way)
        vectors = unit(rebuild(graph, way_maps))
        # (1) how alike the two entities of a case are
        for case, both in pairs.items():
            scores = [float(vectors[a] @ vectors[b]) for a, b in both if a in vectors and b in vectors]  # fmt: skip
            out["alike"][case, way] = (sum(scores) / len(scores) if scores else float("nan"), len(both))  # fmt: skip
        # (2) the other statement of a pair among a statement's ten nearest statements
        statements = [id for id, node in graph.node.items() if node.type.split("@")[0] in STATEMENTS and id in vectors]  # fmt: skip
        row = {id: n for n, id in enumerate(statements)}
        matrix = np.stack([vectors[id] for id in statements])
        found, none = collections.Counter(), collections.Counter()
        for verdict in world.verdicts:
            if verdict.a not in row or verdict.b not in row:
                none[verdict.relation] += 1
                continue
            scores = matrix @ vectors[verdict.a]
            scores[row[verdict.a]] = -2.0
            if int((scores >= scores[row[verdict.b]]).sum()) <= 10:
                found[verdict.relation] += 1
        out["found"][way], out["none"][way] = found, none
        # (3) the ten nearest people of each person
        of_people = np.stack([vectors.get(id, np.zeros(way_maps.dimension)) for id in people])  # fmt: skip
        scores = of_people @ of_people.T
        np.fill_diagonal(scores, -2.0)
        nearest_people[way] = np.argsort(-scores, axis=1)[:, :10]
    for way in WAYS:
        same = [len(set(a) & set(b)) for a, b in zip(nearest_people[way], nearest_people["asserted"], strict=True)]  # fmt: skip
        out["people"][way] = sum(same) / (10 * len(same))
    out["pairs"] = collections.Counter(verdict.relation for verdict in world.verdicts)
    return out


def main() -> None:
    from pangloss_testing import planted

    parser = argparse.ArgumentParser()
    parser.add_argument("--people", type=int, default=1500)
    parser.add_argument("--seeds", type=int, nargs="+", default=[1, 2, 3])
    args = parser.parse_args()
    maps, known = declared()
    runs = []
    for seed in args.seeds:
        world = planted.world(seed=seed, people=args.people, compared=True)
        runs.append(measure(world, maps, known))
        print(f"seed {seed}: {len(world.people)} people, {len(world.factoids)} factoids, {len(world.verdicts)} pairs", flush=True)  # fmt: skip
    head = "".join(f"{way:>12}" for way in WAYS)

    print(f"\n(1) How alike two entities are (mean cosine; n over all seeds)\n{'':44}{head}")  # fmt: skip
    for case in [key[0] for key in runs[0]["alike"] if key[1] == WAYS[0]]:
        cells = [np.nanmean([run["alike"][case, way][0] for run in runs]) for way in WAYS]  # fmt: skip
        n = sum(run["alike"][case, WAYS[0]][1] for run in runs)
        print(f"{case:<36}{n:>7} " + "".join(f"{cell:>12.3f}" for cell in cells))

    print(f"\n(2) The other statement of a pair among the ten nearest statements (share; in brackets: one of the two has no vector)\n{'':30}{head}")  # fmt: skip
    for relation in sorted(runs[0]["pairs"]):
        total = sum(run["pairs"][relation] for run in runs)
        cells = []
        for way in WAYS:
            found = sum(run["found"][way][relation] for run in runs)
            none = sum(run["none"][way][relation] for run in runs)
            cells.append(f"{found / total:.2f}" + (f"({none / total:.2f})" if none else ""))  # fmt: skip
        print(f"{relation:<22}{total:>7} " + "".join(f"{cell:>12}" for cell in cells))

    print(f"\n(3) The ten nearest people of a person that are also those of `asserted` (share)\n{'':30}{head}")  # fmt: skip
    print(f"{'':30}" + "".join(f"{np.mean([run['people'][way] for run in runs]):>12.3f}" for way in WAYS))  # fmt: skip


if __name__ == "__main__":
    main()
