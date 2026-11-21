"""Step 3.5: the planted quality by the steps of FastRP, on world A of the package's planted test (6,000 kinships
of two of a family and a place, 12,000 mentions of three strangers and a place; of a person's 10 nearest people,
the share of their family; chance 1%).

    uv run python notes/similarity-evaluation/steps_planted.py
"""

import dataclasses
import sys

sys.path.insert(0, "packages/pangloss-fastrp/tests")
import test_fastrp_planted as planted  # noqa: E402

world = planted.World()
for _ in range(6000):
    family, a, b = world.kin()
    statement = world.statement("Kinship", family % planted.PLACES)
    for person in (a, b):
        world.relate(statement, person, 2)
for _ in range(12000):
    statement = world.statement("Mention", int(world.random.integers(0, planted.PLACES)))
    for person in world.strangers(3):
        world.relate(statement, person, 2)
for steps in ([0, 1], [0, 1, 1], [0, 1, 1, 1], [0, 1, 1, 1, 1, 1], [0, 1, 1, 1, 1, 1, 1, 1], [0, 0, 1], [0, 1, 0.5]):
    maps = dataclasses.replace(planted.MAPS, steps=tuple(float(s) for s in steps))
    print(f"steps {steps}: {planted.same_family(world, maps):.1f}% of the family")
