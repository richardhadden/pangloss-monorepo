"""Step 8.2's decisions, measured on the planted world (`pangloss_testing.planted`), by name alone and with no
database: the dimension of the name part, where rarity comes from, and what the table of variants is worth.

For each mention, the place of the person it is among the people (the other mentions left out), nearest first by the
cosine of their name vectors. People who have the very same vector as the right one (namesakes) are counted as
before it and after it in turn: "first" is the worst case (every namesake before), "first, ties shared" is one in
as many as tie.

    uv run python notes/similarity-evaluation/names_planted.py [people] [seed]
"""

import math
import sys
import time

import numpy as np
from pangloss_names import maths
from pangloss_testing import planted

PEOPLE = int(sys.argv[1]) if len(sys.argv) > 1 else 300
SEED = int(sys.argv[2]) if len(sys.argv) > 2 else 1


def grams(name, table) -> dict[str, int]:
    found: dict[str, int] = {}
    for word in maths.canonical(maths.fold(name), table):
        for gram in maths.trigrams(word):
            found[gram] = found.get(gram, 0) + 1
    return found


def vectors(names, way, dimension, table):
    """The vectors of the names. `way`: "word" (what `maths.vector` does: rarity by the word), "none" (every trigram
    weighs 1) or "trigram" (rarity by the trigram, counted here)"""
    made = np.zeros((len(names), dimension), dtype=np.float32)
    if way == "word":
        rarity = maths.Rarity.of(maths.words([name], table) for name in names)
        for n, name in enumerate(names):
            found = maths.vector([name], rarity, dimension, table)
            if found is not None:
                made[n] = found
        return made
    counted = [grams(name, table) for name in names]
    having: dict[str, int] = {}
    for found in counted:
        for gram in found:
            having[gram] = having.get(gram, 0) + 1
    for n, found in enumerate(counted):
        weights = {
            gram: count * (1.0 if way == "none" else 1.0 + math.log((len(names) + 1) / (having[gram] + 1)))
            for gram, count in found.items()
        }
        vector = maths.hashed(weights, dimension)
        length = np.linalg.norm(vector)
        if length:
            made[n] = vector / length
    return made


def places(world, people, mentions):
    """(worst place, how many tie with the right one) for each mention"""
    row = {p.id: n for n, p in enumerate(world.people)}
    found = []
    for start in range(0, len(world.mentions), 500):
        chunk = world.mentions[start : start + 500]
        scores = mentions[start : start + 500] @ people.T
        for n, mention in enumerate(chunk):
            right = scores[n, row[mention.person]]
            before = int((scores[n] > right + 1e-6).sum())
            tied = int((np.abs(scores[n] - right) <= 1e-6).sum())
            found.append((before, tied, mention.kind))
    return found


def said(found) -> str:
    def line(rows) -> str:
        count = len(rows)
        first = sum(1 for before, tied, _ in rows if before + tied == 1)
        shared = sum(1 / tied for before, tied, _ in rows if before == 0)
        five = sum(1 for before, tied, _ in rows if before + tied <= 5)
        fair_five = sum(min(1.0, max(0, 5 - before) / tied) for before, tied, _ in rows)
        return (f"first {100 * first / count:5.1f}%  first, ties shared {100 * shared / count:5.1f}%  "
                f"in five {100 * five / count:5.1f}%  in five, ties shared {100 * fair_five / count:5.1f}%")

    lines = [f"    all      {line(found)}"]
    for kind in planted.KINDS:
        lines.append(f"    {kind:8} {line([r for r in found if r[2] == kind])}")
    return "\n".join(lines)


def main() -> None:
    world = planted.world(seed=SEED, people=PEOPLE)
    people_names = [p.label for p in world.people]
    mention_names = [m.label for m in world.mentions]
    everyone = people_names + mention_names
    print(f"seed {SEED}: {len(people_names):,} people, {len(mention_names):,} mentions, "
          f"{len(world.namesakes):,} names shared by {sum(len(v) for v in world.namesakes.values()):,} people")
    table = maths.variants_table(world.variants)
    for with_table in (False, True):
        used = table if with_table else {}
        distinct = {word for name in everyone for word in maths.canonical(maths.fold(name), used)}
        print(f"\n{'with' if with_table else 'without'} the table of variants: {len(distinct):,} words in "
              f"{len(everyone):,} names")
        for label, way in (("no rarity", "none"), ("rarity by the trigram", "trigram"), ("rarity by the word", "word")):
            for dimension in (32, 64, 128, 256, 512, 2048):
                if way != "word" and dimension not in (256, 2048):
                    continue
                began = time.perf_counter()
                made = vectors(everyone, way, dimension, used)
                took = time.perf_counter() - began
                found = places(world, made[: len(people_names)], made[len(people_names) :])
                print(f"  {label}, dimension {dimension} ({took:.1f} s to make {len(everyone):,} vectors)")
                print(said(found) if way == "word" and dimension == 256 else said(found).split("\n")[0])


main()
