"""The planted figures of `notes/similarity-evaluation/wrapper_walks.py` as a regression, through `maths.joins` and
`maths.embed` (implementation_docs/graph-embeddings.md, "Chains of wrappers"): 2,000 people in 100 families of 20,
50 places, 128 dimensions, steps `[0, 1, 1]`, one world (seed 1) where the investigation took the mean of three. No
database; a few seconds."""

import dataclasses

import numpy as np
import pytest

from pangloss_fastrp import maths
from pangloss_fastrp.maths import Edge, GraphMaps, Node
from pangloss_fastrp.testing import MemoryReader

PEOPLE, FAMILY, PLACES = 2000, 20, 50
SEED = 1

MAPS = GraphMaps(
    kinds={
        "Person": "stop",
        "Place": "stop",
        "Kinship": "stop",
        "Mention": "stop",
        "InRole": "through",
        "Identification": "through",
        "Alternative": "through",
        "Group": "through",
    },
    held={
        "InRole": ["target"],
        "Identification": ["target"],
        "Alternative": ["alternatives"],
        "Group": ["target"],
    },
    shares={"Alternative.alternatives": ["percent", 100]},
)


class World:
    """People in families, places, and statements that name them (`wrapper_walks.World`)"""

    def __init__(self) -> None:
        self.random = np.random.default_rng(SEED)
        self.graph = MemoryReader()
        self.count = 0
        self.people = [self.node("Person") for _ in range(PEOPLE)]
        self.places = [self.node("Place") for _ in range(PLACES)]

    def node(self, type: str) -> str:
        self.count += 1
        id = f"{type}-{self.count:07d}"
        self.graph.add(Node(id, type))
        return id

    def edge(self, source: str, target: str, field: str, **properties) -> None:
        self.graph.link(Edge(source, target, field, properties))

    def statement(self, type: str, place: int) -> str:
        statement = self.node(type)
        self.edge(statement, self.places[place], "place")
        return statement

    def relate(self, statement: str, person: int, depth: int) -> None:
        """A person in the field `person`, through `depth` wrappers: InRole, Identification, an alternative"""
        source, field = statement, "person"
        for type in ["InRole", "Identification", "Alternative"][:depth]:
            wrapper = self.node(type)
            self.edge(source, wrapper, field)
            source = wrapper
            field = "alternatives" if type == "Alternative" else "target"
        shared = {"percent": 100} if field == "alternatives" else {}
        self.edge(source, self.people[person], field, **shared)

    def kin(self) -> tuple[int, int, int]:
        family = int(self.random.integers(0, PEOPLE // FAMILY))
        a, b = self.random.choice(FAMILY, 2, replace=False)
        return family, family * FAMILY + int(a), family * FAMILY + int(b)

    def strangers(self, count: int) -> list[int]:
        return [int(p) for p in self.random.choice(PEOPLE, count, replace=False)]


def same_family(world: World, maps: GraphMaps) -> float:
    """Of each person's 10 nearest people, the share of their family, in per cent"""
    found = maths.joins(world.graph, maps)
    ids = sorted({i for key in found for i in key})
    vectors = maths.embed(ids, found, maps)
    index = {i: n for n, i in enumerate(ids)}
    rows = vectors[[index[p] for p in world.people]]
    rows = rows / np.maximum(np.linalg.norm(rows, axis=1, keepdims=True), 1e-12)
    similar = rows @ rows.T
    np.fill_diagonal(similar, -2)
    nearest = np.argsort(-similar, axis=1)[:, :10]
    family = np.arange(PEOPLE) // FAMILY
    return float((family[nearest] == family[:, None]).mean()) * 100


@pytest.mark.parametrize("depth", [0, 1, 2, 3])
def test_the_family_is_found_however_many_wrappers_stand_between_a_statement_and_a_person(
    depth,
):
    """World A: 6,000 kinships (two of a family and a place), 12,000 mentions (three strangers and a place). Hopped
    over, 20% at every depth (chance 1%); walked, one wrapper was enough to lose it all"""
    world = World()
    for _ in range(6000):
        family, a, b = world.kin()
        statement = world.statement("Kinship", family % PLACES)
        for person in (a, b):
            world.relate(statement, person, depth)
    for _ in range(12000):
        statement = world.statement("Mention", int(world.random.integers(0, PLACES)))
        for person in world.strangers(3):
            world.relate(statement, person, depth)
    assert same_family(world, MAPS) >= 15


def world_b() -> World:
    """World B: 6,000 kinships, one person named outright and the other, in half of them, one of three candidates with
    likelihoods (the right one at 60% in 7 of 10, else at 25%), and six bystanders held by one conjunction;
    6,000 mentions of three strangers"""
    world = World()
    for _ in range(6000):
        family, a, b = world.kin()
        statement = world.statement("Kinship", family % PLACES)
        world.relate(statement, a, 0)
        if world.random.random() < 0.5:
            identification = world.node("Identification")
            alternative = world.node("Alternative")
            world.edge(statement, identification, "person")
            world.edge(identification, alternative, "target")
            likes = [60, 25, 15] if world.random.random() < 0.7 else [25, 60, 15]
            for person, like in zip([b, *world.strangers(2)], likes, strict=True):
                world.edge(
                    alternative, world.people[person], "alternatives", percent=like
                )
        else:
            world.relate(statement, b, 0)
        witnesses = world.node("Group")
        world.edge(statement, witnesses, "witnesses")
        for person in world.strangers(6):
            world.edge(witnesses, world.people[person], "target")
    for _ in range(6000):
        statement = world.statement("Mention", int(world.random.integers(0, PLACES)))
        for person in world.strangers(3):
            world.relate(statement, person, 0)
    return world


def test_shares_beat_flat_on_world_b_with_the_bystanders_quieted():
    """The investigation's 33.7% against 27.0%. (Without the bystanders quieted, shares alone did not beat flat
    there, 3.5% against 4.2%: the noise was the bystanders)"""
    world = world_b()
    quiet = {"Kinship.witnesses": 0.2}
    shared = same_family(world, dataclasses.replace(MAPS, field_weight=quiet))
    flat = same_family(world, dataclasses.replace(MAPS, field_weight=quiet, shares={}))
    assert shared > flat + 3, (shared, flat)
