"""The quality of the score, held to floors (implementation_docs/similarity-build-plan.md, "Testing the next phases",
4), with no database: on the planted world (`pangloss_testing.planted`), each of a sample of mentions is scored
against the people by `pangloss_reconcile.score`, name 1 and graph 0.25, its own vectors standing for an unknown's;
and with the entities shared at 1.5 (step 11.2: the name's cosine × n / (n + 2)), counted as `reasons.py` counts
them: the entities the mention's factoid names beside it that another factoid names with the candidate, a candidate
never sharing itself (worked out in memory, as `notes/similarity-evaluation/learn_trial.py`'s `world_features`
does).

The vectors are made in memory: the name part's by its maths (`pangloss_names.maths`, with the table of variants, the
rarity of every name of the world), the graph part's by a whole rebuild of FastRP (`pangloss_fastrp.maths.rebuild`)
over the world's payloads laid out as nodes and edges, by maps written here for the models of
`pangloss_testing.similar_models` (the defaults of `FastRPMeta`: every class and field at 1, the steps `[0, 1, 1]`,
128 dimensions). The candidates of a mention are found as the service finds them: the `FETCH` nearest people by
each part alone, the union, each scored. The mentions are in the graph as the people they are in the world (a
`Person` of their own in one hearing): the hearing is in the people's vectors too, where the service lays it over
the stored graph without it.

Measured here (2026-11-22, 1,500 people, every mention: the figures are by the floors below) and by main through the service at 6,000
people (notes/similarity-evaluation/planted_reconcile_memgraph_small.txt: name alone 71% first, 99% in five; name 1
with graph 0.25, 78% and 99.7%; of the names several people have, 43% first by name and 58% with the graph): the
floors are a little under what was measured here, for each seed. A change that costs quality fails here"""

from collections import defaultdict
from collections.abc import Mapping, Sequence
from typing import Any, NamedTuple

import numpy as np
import pytest
from pangloss_fastrp import maths as graph_maths
from pangloss_fastrp.maths import Edge, GraphMaps, Node
from pangloss_fastrp.memory import MemoryReader
from pangloss_names import maths as name_maths
from pangloss_reconcile.score import SHARED, part_scores, ranked, score, with_shared
from pangloss_testing import planted

PEOPLE = 1500
NAME_DIMENSION = 256
FETCH = 50
WITH_GRAPH = {"name": 1.0, "graph": 0.25}
WITH_SHARED = {"name": 1.0, "graph": 0.25, SHARED: 1.5}

# The floors, a little under what was measured here on seeds 1, 2 and 3 (2026-11-22, 287 to 292 mentions each):
# with the graph, right first 78.0%, 79.0%, 81.5%, among five 99.7%, 100%, 100%; of the names several people have,
# right first 56.6%, 60.4%, 65.1% with the graph and 34.6%, 34.9%, 41.6% by the name alone (whose namesakes tie,
# and are ranked by id). By the name alone, right first 68.3%, 65.6%, 70.2%, among five 98.3%, 98.6%, 99.7%
FIRST_FLOOR = 0.75
FIVE_FLOOR = 0.98
GRAPH_GAIN = 0.15
# With the entities shared too (2026-11-23, the same mentions; name 1, graph 0.25, shared 1.5 as the name's cosine
# × n / (n + 2)): right first 89.2%, 90.7%, 90.1% (11.1, 11.7 and 8.6 points above the graph alone), among five 100%
# on each seed; of the names several people have, right first 77.9%, 81.9%, 81.2%. (The first form, n / (n + 2) at
# 0.75 for everyone alike: 85.7%, 86.6%, 86.6%; the product at 1: 86.4%, 88.3%, 88.4%; at 2: 89.6%, 91.8%, 91.1%)
SHARED_FIRST_FLOOR = 0.88
SHARED_FIVE_FLOOR = 0.99
SHARED_NAMESAKES_FLOOR = 0.76
SHARED_GAIN = 0.08
NAME_ALONE = {"name": 1.0}

STATEMENTS = ["Activity", "Transfer", "MemberOf", "ChildOf", "Sibling"]

# (the models of `similar_models` as `pangloss_fastrp.maps` would make them, every weight its default)
MAPS = GraphMaps(
    kinds={
        "Person": "stop",
        "Group": "stop",
        "Place": "stop",
        "Factoid": "stop",
        **{name: "stop" for name in STATEMENTS},
        "InRole": "through",
        "Identification": "through",
        "WeightedAlternative": "through",
    },
    held={
        "InRole": ["target"],
        "Identification": ["target"],
        "WeightedAlternative": ["alternatives"],
    },
    shares={"WeightedAlternative.alternatives": ["percent", 100]},
    documents={"Factoid": True, **{name: True for name in STATEMENTS}},
)


def laid_out(world: planted.World) -> MemoryReader:
    """The world's entities and factoids as the nodes and forward edges they are stored as"""
    graph = MemoryReader()
    for entity in world.entities:
        graph.add(Node(entity["id"], entity["type"]))
    made = [0]

    def node(value: Mapping[str, Any]) -> str:
        made[0] += 1
        id = f"{value['type']}-{made[0]:07d}"
        graph.add(Node(id, value["type"]))
        for field, given in value.items():
            for item in given if isinstance(given, list) else [given]:
                if isinstance(item, Mapping) and "type" in item:
                    if set(item) - {"type", "id", "edge_properties"}:
                        graph.link(Edge(id, node(item), field))
                    else:
                        graph.link(
                            Edge(
                                id,
                                item["id"],
                                field,
                                dict(item.get("edge_properties") or {}),
                            )
                        )
        return id

    for factoid in world.factoids:
        node(factoid)
    return graph


def references(value: Any, found: set[str]) -> set[str]:
    """The ids a payload refers to (a value of `type` and `id` alone, as `laid_out` makes an edge of it)"""
    if isinstance(value, Mapping):
        if "id" in value and not (set(value) - {"type", "id", "edge_properties"}):
            found.add(value["id"])
        for inner in value.values():
            references(inner, found)
    elif isinstance(value, list):
        for inner in value:
            references(inner, found)
    return found


def unit(rows: np.ndarray) -> np.ndarray:
    return rows / np.maximum(np.linalg.norm(rows, axis=1, keepdims=True), 1e-12)


class Scored(NamedTuple):
    """A candidate of a mention as the service scores it: each part's cosine and `shared` (`score.with_shared`), how
    many of the document's entities it shares, and the score"""

    scores: dict[str, float]
    shared: int
    score: float


def ranks(seed: int, weights: Mapping[str, float]) -> list[tuple[int, bool]]:
    """For each mention: the place of the person it is among its candidates as the service ranks them (by score,
    then id: `score.ranked`; 1 is right first), and whether its name is one several people have. A person not found
    by either part is past every place (`FETCH` + 1)"""
    world, found = scored(seed, weights)
    shared = {id for ids in world.namesakes.values() for id in ids}
    places: list[tuple[int, bool]] = []
    for mention, candidates in found:
        order = ranked({id: c.score for id, c in candidates.items()}, len(candidates))
        place = (
            order.index(mention.person) + 1
            if mention.person in candidates
            else FETCH + 1
        )
        places.append((place, mention.person in shared))
    return places


def scored(
    seed: int, weights: Mapping[str, float]
) -> tuple[planted.World, list[tuple[planted.Mention, dict[str, Scored]]]]:
    """The world of a seed, and for each of its mentions its candidates (by id) found and scored as the service finds
    and scores them"""
    world = planted.world(seed=seed, people=PEOPLE)
    table = name_maths.variants_table(world.variants)
    labels = [p.label for p in world.people] + [m.label for m in world.mentions]
    rarity = name_maths.Rarity.of(name_maths.words([label], table) for label in labels)

    def name_of(label: str) -> np.ndarray:
        return np.asarray(
            name_maths.vector([label], rarity, NAME_DIMENSION, table), dtype=float
        )

    built = graph_maths.rebuild(laid_out(world), MAPS)
    zero = np.zeros(MAPS.dimension)

    def graph_of(id: str) -> np.ndarray:
        return np.asarray(built.get(id, zero), dtype=float)

    people = [p.id for p in world.people]
    vectors = {
        "name": np.array([name_of(p.label) for p in world.people]),
        "graph": np.array([graph_of(id) for id in people]),
    }
    units = {part: unit(rows) for part, rows in vectors.items()}
    # (which factoids name each entity, and what each factoid names: the shared entities, as `reasons.py` counts
    # them, are worked out from these)
    named_in: dict[str, set[int]] = defaultdict(set)
    named_by: list[set[str]] = []
    for n, factoid in enumerate(world.factoids):
        named_by.append(references(factoid, set()))
        for id in named_by[-1]:
            named_in[id].add(n)
    parts = [part for part in weights if part != SHARED]
    found: list[tuple[planted.Mention, dict[str, Scored]]] = []
    for mention in world.mentions:
        own = {"name": name_of(mention.label), "graph": graph_of(mention.id)}
        candidates: set[int] = set()
        for part in parts:
            if not own[part].any():
                continue
            near = units[part] @ (own[part] / np.linalg.norm(own[part]))
            candidates |= {int(n) for n in np.argsort(-near, kind="stable")[:FETCH]}
        # (the entities the mention's factoid names beside it; a candidate shares one when another factoid names
        # them both, and does not share itself)
        (home,) = named_in[mention.id]
        beside = named_by[home] - {mention.id}

        def sharing(id: str, beside: set[str] = beside, home: int = home) -> int:
            return sum(
                1
                for other in beside
                if other != id and (named_in[other] & named_in[id]) - {home}
            )

        of_mention: dict[str, Scored] = {}
        for n in candidates:
            n_shared = sharing(people[n])
            scores = with_shared(
                part_scores(
                    {part: list(own[part]) for part in parts},
                    {part: list(vectors[part][n]) for part in parts},
                    weights,
                ),
                n_shared,
                weights,
            )
            of_mention[people[n]] = Scored(scores, n_shared, score(scores, weights))
        found.append((mention, of_mention))
    return world, found


def share(
    found: Sequence[tuple[int, bool]], most: int, shared_only: bool = False
) -> float:
    chosen = [place for place, shared in found if shared or not shared_only]
    return sum(1 for place in chosen if place <= most) / len(chosen)


@pytest.fixture(scope="module")
def measured() -> dict[tuple[int, str], list[tuple[int, bool]]]:
    """(made once for the module: a world, its vectors and the scores, for each seed and weighing)"""
    return {
        (seed, name): ranks(seed, weights)
        for seed in (1, 2, 3)
        for name, weights in (
            ("with graph", WITH_GRAPH),
            ("name alone", NAME_ALONE),
            ("with shared", WITH_SHARED),
        )
    }


@pytest.mark.parametrize("seed", [1, 2, 3])
def test_with_the_name_and_the_graph_who_a_mention_is_is_mostly_first_and_nearly_always_among_five(
    measured, seed
):
    found = measured[(seed, "with graph")]
    assert share(found, 1) > FIRST_FLOOR, share(found, 1)
    assert share(found, 5) > FIVE_FLOOR, share(found, 5)


@pytest.mark.parametrize("seed", [1, 2, 3])
def test_the_graph_helps_the_mentions_whose_name_several_people_have(measured, seed):
    with_graph = share(measured[(seed, "with graph")], 1, shared_only=True)
    alone = share(measured[(seed, "name alone")], 1, shared_only=True)
    assert with_graph > alone + GRAPH_GAIN, (with_graph, alone)


@pytest.mark.parametrize("seed", [1, 2, 3])
def test_with_the_entities_shared_too_who_a_mention_is_is_first_more_often(
    measured, seed
):
    found = measured[(seed, "with shared")]
    assert share(found, 1) > SHARED_FIRST_FLOOR, share(found, 1)
    assert share(found, 5) > SHARED_FIVE_FLOOR, share(found, 5)
    namesakes = share(found, 1, shared_only=True)
    assert namesakes > SHARED_NAMESAKES_FLOOR, namesakes


@pytest.mark.parametrize("seed", [1, 2, 3])
def test_the_entities_shared_put_the_right_person_first_more_often_than_the_parts_alone(
    measured, seed
):
    lifted = share(measured[(seed, "with shared")], 1)
    without = share(measured[(seed, "with graph")], 1)
    assert lifted > without + SHARED_GAIN, (lifted, without)
