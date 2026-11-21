"""The quality of the name part, held to floors: on the planted world (`pangloss_testing.planted`), who a mention is
must be among the nearest by name alone. The floors are a little under what was measured on 2026-11-21
(notes/similarity-evaluation/names_planted.txt; at 1,500 people and the dimension 256, on five seeds: among the five
nearest 84.5% to 91.1% without the table of variants, 95.5% to 98.3% with it). A change that costs quality fails
here (implementation_docs/similarity-build-plan.md, step 8.2)"""

import numpy as np
import pytest
from pangloss_names import maths
from pangloss_testing import planted

DIMENSION = 256


def found(seed: int, with_table: bool):
    world = planted.world(seed=seed, people=1500)
    table = maths.variants_table(world.variants) if with_table else {}
    names = [p.label for p in world.people] + [m.label for m in world.mentions]
    rarity = maths.Rarity.of(maths.words([name], table) for name in names)
    vectors = np.array(
        [maths.vector([name], rarity, DIMENSION, table) for name in names]
    )
    people = len(world.people)
    return planted.places(world, vectors[:people], vectors[people:])


@pytest.mark.parametrize("seed", [1, 2, 3])
def test_who_a_mention_is_is_among_the_five_nearest_by_name_alone(seed):
    assert planted.within(found(seed, with_table=False), 5) > 0.80


@pytest.mark.parametrize("seed", [1, 2, 3])
def test_with_the_table_of_variants_nearly_every_mention_finds_its_person(seed):
    places = found(seed, with_table=True)
    assert planted.within(places, 5) > 0.93
    assert planted.within(places, 10) > 0.98


@pytest.mark.parametrize("seed", [1, 2, 3])
def test_the_table_of_variants_helps_the_mentions_under_a_variant(seed):
    def share(places):
        return planted.within([p for p in places if p[2] in ("variant", "both")], 5)

    assert (
        share(found(seed, with_table=True))
        > share(found(seed, with_table=False)) + 0.05
    )
