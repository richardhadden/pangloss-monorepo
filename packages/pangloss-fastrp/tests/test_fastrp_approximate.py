"""The approximate vectors a refresh past the cap writes (`pangloss_fastrp.approximate`), on graphs in memory: on a
planted hub, the vectors of a document written beside it, from one ring and the vectors stored before it was written,
are close to the exact ones (implementation_docs/similarity-build-plan.md, step 5.3). No database."""

import dataclasses
import random

import numpy as np
import pytest

from pangloss_fastrp import maths
from pangloss_fastrp.approximate import approximate
from pangloss_fastrp.maths import Edge, GraphMaps, Node
from pangloss_fastrp.testing import MemoryReader, oracle

MAPS = GraphMaps(
    kinds={"Factoid": "stop", "Transfer": "stop", "Person": "stop"},
    documents={"Factoid": True, "Transfer": True},
    dimension=128,
)


def cosine(a, b) -> float:
    return float(np.dot(a, b) / np.linalg.norm(a) / np.linalg.norm(b))


def hub(
    seed: int, documents: int = 60, people: int = 30
) -> tuple[MemoryReader, list[str]]:
    """A person, `hub`, whom most of the transfers of `documents` factoids are given by; the others are given by and
    to one of `people` more"""
    chance = random.Random(seed)
    reader = MemoryReader()
    reader.add(Node("hub", "Person"))
    others = [f"person {n}" for n in range(people)]
    for person in others:
        reader.add(Node(person, "Person"))
    for n in range(documents):
        factoid, statement = f"factoid {n}", f"transfer {n}"
        reader.add(Node(factoid, "Factoid"))
        reader.add(Node(statement, "Transfer"))
        reader.link(Edge(factoid, statement, "statements"))
        by = "hub" if chance.random() < 0.8 else chance.choice(others)
        reader.link(Edge(statement, by, "given_by"))
        reader.link(Edge(statement, chance.choice(others), "given_to"))
    return reader, others


def written_beside_the_hub(reader: MemoryReader, to: str) -> list[str]:
    """A new factoid: a transfer given by the hub to one person"""
    reader.add(Node("new factoid", "Factoid"))
    reader.add(Node("new transfer", "Transfer"))
    reader.link(Edge("new factoid", "new transfer", "statements"))
    reader.link(Edge("new transfer", "hub", "given_by"))
    reader.link(Edge("new transfer", to, "given_to"))
    return ["new factoid", "new transfer"]


def approximated(reader: MemoryReader, stops: list[str], stored, maps: GraphMaps):
    return approximate(stops, maths.joins(reader, maps, stops), stored, maps)


@pytest.mark.parametrize("seed", range(5))
def test_on_a_planted_hub_the_approximate_vectors_of_a_document_written_beside_it_are_close_to_the_exact_ones(
    seed,
):
    reader, others = hub(seed)
    stored = oracle(reader, MAPS)
    written = written_beside_the_hub(reader, others[seed])
    exact = oracle(reader, MAPS)
    made = approximated(reader, written, stored, MAPS)
    assert set(made) == set(written)
    for stop in written:
        assert cosine(made[stop], exact[stop]) >= 0.9, stop


def test_with_one_step_the_approximation_is_exact():
    """(the first step is from the seeds of the neighbours alone, which are made from their ids)"""
    maps = dataclasses.replace(MAPS, steps=[1.0])
    reader, others = hub(0)
    stored = oracle(reader, maps)
    written = written_beside_the_hub(reader, others[0])
    exact = oracle(reader, maps)
    made = approximated(reader, written, stored, maps)
    for stop in written:
        assert np.allclose(made[stop], exact[stop], atol=1e-9)


def test_what_is_stored_of_the_stops_written_is_not_used_and_one_joined_to_nothing_has_none():
    reader, others = hub(1)
    stored = dict(oracle(reader, MAPS))
    written = written_beside_the_hub(reader, others[1])
    reader.add(Node("alone", "Person"))
    stops = [*written, "alone"]
    first = approximated(reader, stops, stored, MAPS)
    stored |= {stop: np.ones(MAPS.dimension) for stop in stops}
    again = approximated(reader, stops, stored, MAPS)
    assert set(first) == set(written)
    for stop in written:
        assert np.allclose(first[stop], again[stop])


def test_an_entity_written_with_the_document_is_worked_out_with_it():
    """(an entity the document makes, `create_new`, is a head written in the same batch, and has nothing stored)"""
    reader, others = hub(2)
    stored = oracle(reader, MAPS)
    written = written_beside_the_hub(reader, others[2])
    reader.add(Node("newcomer", "Person"))
    reader.link(Edge("new transfer", "newcomer", "given_to"))
    exact = oracle(reader, MAPS)
    made = approximated(reader, [*written, "newcomer"], stored, MAPS)
    assert set(made) == {*written, "newcomer"}
    for stop in written:
        assert cosine(made[stop], exact[stop]) >= 0.9, stop
