"""The vectors a refresh past the cap writes (`part.refresh_ids`): approximate, for the stops written alone, from what
they are joined to and the vectors stored (implementation_docs/vectors.md, "Past the cap"). No database.

FastRP (`maths.embed`) is, for each stop `i` and each step `t` of `steps`,

    x_0(i) = seed(i),   x_t(i) = unit(Σ_j a_ij · x_{t-1}(j)),   vector(i) = Σ_t steps[t-1] · x_t(i)

over the joins `a_ij` of the joined graph. An exact vector needs the graph `len(steps)` joins out. Here only the joins
of the stops written are read (one ring: `S`, the stops written, and `J`, the stops they are joined to), and each step
of a stop of `S` is taken from:

- a stop of `S`: its own step before, worked out here (they are worked out together, step by step);
- a stop of `J`, at the first step: its seed (which is made from its id alone, so exact);
- a stop of `J`, at a later step: the direction of its **stored** vector (`unit(stored(j))`), in place of its step
  before, which only the graph beyond it could give; at the second step at half its weight (`FIRST_STEP_SHARE`),
  where it stands for the neighbour's first step, which is a mean of seeds and is nowhere in what is stored. A stop
  of `J` with no stored vector counts for nothing there.

So the first step is exact, and every later one is the step of FastRP taken from what is stored. The error is in how
far a neighbour's stored vector, the weighted sum of all its steps, points elsewhere than its one step before; and in
stored vectors that are themselves out of date. The half was chosen on simulated hubs (a person in every transfer of
sixty, 2026-11-21): with the default steps the cosine with the exact vector was at least 0.89 at full weight and 0.93
at half, of a document's head and its statement, over thirty seeds; with four steps a statement's is poorer (0.74 at
the least), with two steps 0.92. The pure test is `tests/test_fastrp_approximate.py`.
"""

from collections.abc import Iterable, Mapping, Sequence

import numpy as np

from pangloss_fastrp.maths import GraphMaps, seeds

# The weight of a stored direction at the second step (see the module)
FIRST_STEP_SHARE = 0.5


def _unit(vector: np.ndarray) -> np.ndarray:
    length = float(np.linalg.norm(vector))
    return vector / length if length > 0 else vector


def approximate(
    stops: Iterable[str],
    weights: Mapping[tuple[str, str], float],
    stored: Mapping[str, Sequence[float]],
    maps: GraphMaps,
) -> dict[str, np.ndarray]:
    """The approximate vector of each of `stops` that is joined to something, from `weights` (every join touching one
    of them, as `maths.joins(reader, maps, stops)` gives them) and the `stored` vectors of the stops they are joined
    to (by id; those of `stops` themselves are not used)"""
    written = set(stops)
    near: dict[str, dict[str, float]] = {i: {} for i in written}
    for (a, b), weight in weights.items():
        if a in near and b != a:
            near[a][b] = weight
        if b in near and a != b:
            near[b][a] = weight
    joined = sorted(i for i in written if near[i])
    if not joined:
        return {}
    ids = sorted(set(joined) | {j for i in joined for j in near[i]})
    seed = dict(zip(ids, seeds(ids, maps.dimension), strict=True))
    known = {
        j: _unit(np.asarray(stored[j], dtype=np.float64))
        for j in ids
        if j not in written and j in stored
    }
    step = {i: seed[i] for i in joined}
    made = {i: np.zeros(maps.dimension) for i in joined}
    for t, weight in enumerate(maps.steps, start=1):
        following = {}
        for i in joined:
            total = np.zeros(maps.dimension)
            for j, a in near[i].items():
                if j in written:
                    # (a stop written that is joined to nothing is never a neighbour: it has a join, this one)
                    total += a * (step[j] if j in step else seed[j])
                elif t == 1:
                    total += a * seed[j]
                elif j in known:
                    total += a * (FIRST_STEP_SHARE if t == 2 else 1.0) * known[j]
            following[i] = _unit(total)
        step = following
        for i in joined:
            made[i] += weight * step[i]
    return made
