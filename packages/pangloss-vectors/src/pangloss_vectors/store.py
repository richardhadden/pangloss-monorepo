"""The vectors in the graph: what each part computed, the vector of each profile made from them, and their state.

    (:PGVector {of, part, type, generation, vector})          a part of an item (no edge to it, no vector index)
    (:PGVectorState {part, generation, built_at, count, stale, signature, graph_sees})      one for each part
    (:PGProfileVector:PGV_<profile>_<dimension>[:PGV_<profile>_<dimension>_<Group>...]
        {of, profile, type, generation, vector})                 the combined vector of an item, for one profile
    (:PGVectorProfile {profile, generation, signature, dimension, built_at, count})      one for each profile

`of` is the item's id and `type` its class. A profile's vector is its parts end to end, in the order of their names,
each at length one and scaled by the square root of its weight (`Layout.combine`); its label and its vector index
carry the profile and the dimension (`pgv_default_191`, on `PGV_default_191`), and each group of the item's class
(`meta.groups_of`) one label more, with a vector index of its own. (Memgraph refuses to make a vector index while
any node of the label has the property at another length, deleted nodes too: a class added to a project changes the
class part's dimension, and with the dimension in the label, vectors of another length are never under a label an
index is made on. notes/similarity-evaluation/README.md, "Which index a profile searches".)

**Generations.** A rebuild writes a new generation beside the one in use (`write_generation` of each part rebuilt,
then `combine` for each profile that weighs one of them, once, from all of them), and `switch` makes them the ones in
use: one transaction that sets `generation` on the state nodes and nothing else. What is in use is whatever the state says; nothing reads another generation. The old
one is then deleted in batches (`drop_generation`, `drop_profile_generation`). Generation numbers are counted once
for all parts and profiles (`next_generation`), so a number is never used twice.

Through `pangloss_core.backend.current()`, in Cypher both databases run. implementation_docs/similarity-build-plan.md,
step 2.2.
"""

import dataclasses
import datetime
import json
import math
from collections.abc import Iterable, Mapping, Sequence
from typing import Any

from pangloss_core import backend
from pangloss_models import PanglossRuntimeError

from pangloss_vectors import meta
from pangloss_vectors.parts import (
    Vector,
    VectorRow,
    part,
    profile,
    profiles,
    signature_of,
)

VECTOR = "PGVector"
STATE = "PGVectorState"
PROFILE_VECTOR = "PGProfileVector"
PROFILE_STATE = "PGVectorProfile"

# (rows in each transaction of a write, and nodes in each of a delete)
WRITE_PAGE = 1000
DROP_PAGE = 10_000


class VectorLengthError(ValueError):
    """A vector that is not of its part's dimension. Refused before anything is written: Memgraph refuses it on the
    write, and Neo4j writes it and silently leaves it out of the index"""


class RebuildDue(PanglossRuntimeError):
    """What was asked for needs a built generation that is not there, or that is not of today's dimension"""


# ---------------------------------------------------------------------------
# Names, and the combined vector (no database)
# ---------------------------------------------------------------------------


def _word(name: str, what: str) -> str:
    if not name.isidentifier():
        raise ValueError(f"{what} {name!r} is not a word: it cannot be in a label")
    return name


def profile_label(profile_name: str, dimension: int) -> str:
    """The label of every vector of the profile at this dimension (`PGV_default_191`)"""
    return f"PGV_{_word(profile_name, 'The profile')}_{int(dimension)}"


def group_label(profile_name: str, dimension: int, group: str) -> str:
    """The label of the profile's vectors of the items of a group (`PGV_default_191_Person`)"""
    return f"{profile_label(profile_name, dimension)}_{_word(group, 'The class')}"


def profile_index_name(profile_name: str, dimension: int) -> str:
    """The name of the profile's vector index (`pgv_default_191`)"""
    return f"pgv_{_word(profile_name, 'The profile')}_{int(dimension)}"


def group_index_name(profile_name: str, dimension: int, group: str) -> str:
    """The name of the vector index of a group (`pgv_default_191_person`)"""
    return f"{profile_index_name(profile_name, dimension)}_{_word(group, 'The class').lower()}"


def check_length(
    part_name: str, of: str, vector: Vector, dimension: int
) -> list[float]:
    """The vector as a list of floats, or `VectorLengthError` if it is not of the part's dimension"""
    if len(vector) != dimension:
        raise VectorLengthError(
            f"The {part_name} vector of {of} has {len(vector)} numbers; the part's dimension is {dimension}"
        )
    return [float(x) for x in vector]


@dataclasses.dataclass(frozen=True)
class Layout:
    """How a profile's vectors are made: its weights (the parts above zero, in the order of their names) and the
    dimension of each of those parts. `layout()` makes it from the registered parts"""

    profile: str
    weights: Mapping[str, float]
    dimensions: Mapping[str, int]

    def __post_init__(self) -> None:
        weights = {name: float(w) for name, w in sorted(self.weights.items()) if w > 0}
        object.__setattr__(self, "weights", weights)
        missing = sorted(set(weights) - set(self.dimensions))
        if missing:
            raise ValueError(
                f"The profile {self.profile!r} has no dimension for {', '.join(missing)}"
            )

    @property
    def dimension(self) -> int:
        """The sum of the dimensions of its parts"""
        return sum(int(self.dimensions[name]) for name in self.weights)

    @property
    def label(self) -> str:
        return profile_label(self.profile, self.dimension)

    @property
    def index_name(self) -> str:
        return profile_index_name(self.profile, self.dimension)

    def group_label(self, group: str) -> str:
        return group_label(self.profile, self.dimension, group)

    def group_index_name(self, group: str) -> str:
        return group_index_name(self.profile, self.dimension, group)

    def labels(self, type_name: str) -> list[str]:
        """The labels of the profile vector of an item of the class (`PGProfileVector` aside): the profile's, and one
        for each group the class is in"""
        return [self.label, *(self.group_label(g) for g in meta.groups_of(type_name))]

    def combine(self, vectors: Mapping[str, Vector | None]) -> list[float]:
        """The combined vector of an item from the vectors of its parts, by name: for each part of the profile in the
        order of their names, `sqrt(weight) × (the part's vector at length one)`, end to end; zeros for a part it has
        no vector of (or one of length zero).

        So the cosine of two combined vectors is the weighted mean of the cosines of their parts, `Σ w·cos / Σ w`, where
        both have every part: a weight says how much the likeness of that part counts. (A part one of them lacks adds
        nothing above the line and is left out of that one's sum below it.)"""
        combined: list[float] = []
        for name, weight in self.weights.items():
            dimension = int(self.dimensions[name])
            vector = vectors.get(name)
            if vector is None:
                combined += [0.0] * dimension
                continue
            values = check_length(name, "an item", vector, dimension)
            length = math.sqrt(sum(x * x for x in values))
            if length == 0:
                combined += [0.0] * dimension
                continue
            scale = math.sqrt(weight) / length
            combined += [x * scale for x in values]
        return combined

    def signature(self) -> str:
        """What a profile's vectors depend on: its weights and the signature of each of its parts (registered)"""
        return profile_signature(self.weights)


def profile_signature(weights: Mapping[str, float]) -> str:
    """`signature_of` the weights (those above zero) and each part's `signature()`"""
    kept = {name: float(w) for name, w in weights.items() if w > 0}
    return signature_of(kept, {name: part(name).signature() for name in sorted(kept)})


def layout(profile_name: str, weights: Mapping[str, float] | None = None) -> Layout:
    """The layout of a profile of the settings (or of the weights given), with the dimensions of the registered parts"""
    if weights is None:
        weights = profile(profile_name)
    return Layout(
        profile_name,
        weights,
        {name: part(name).dimension() for name, w in weights.items() if w > 0},
    )


def profiles_weighing(part_name: str) -> list[str]:
    """The profiles of the settings that weigh the part above zero"""
    return sorted(
        name for name, weights in profiles().items() if weights.get(part_name, 0) > 0
    )


# ---------------------------------------------------------------------------
# What is in use
# ---------------------------------------------------------------------------


@dataclasses.dataclass(frozen=True)
class PartState:
    part: str
    generation: int
    built_at: datetime.datetime | None
    count: int
    stale: int
    signature: str
    graph_sees: str


@dataclasses.dataclass(frozen=True)
class ProfileState:
    profile: str
    generation: int
    signature: str
    dimension: int
    built_at: datetime.datetime | None
    count: int
    weights: Mapping[str, float] = dataclasses.field(default_factory=dict)
    """The weights it was combined with (those above zero)"""
    removed: int = 0
    """Vectors of the generation in use deleted since it was built (by `delete_for`, `set_vectors`,
    `remove_vectors`): on Memgraph they may still hold places in the vector index, until the database collects them,
    so a search may ask for this many more (`search.nearest`)"""


@dataclasses.dataclass(frozen=True)
class States:
    parts: dict[str, PartState]
    profiles: dict[str, ProfileState]


def _database() -> Any:
    return backend.current().database()


async def _states(tx: Any) -> States:
    from pangloss_cypher.values import native_datetime

    result = await tx.run(
        f"MATCH (s:{STATE}) RETURN s.part AS part, s.generation AS generation, s.built_at AS built_at, "
        "s.count AS count, s.stale AS stale, s.signature AS signature, s.graph_sees AS graph_sees"
    )
    found_parts = {
        r["part"]: PartState(
            part=r["part"],
            generation=r["generation"],
            built_at=native_datetime(r["built_at"]),
            count=r["count"] or 0,
            stale=r["stale"] or 0,
            signature=r["signature"] or "",
            graph_sees=r["graph_sees"] or "",
        )
        async for r in result
    }
    result = await tx.run(
        f"MATCH (s:{PROFILE_STATE}) RETURN s.profile AS profile, s.generation AS generation, "
        "s.signature AS signature, s.dimension AS dimension, s.built_at AS built_at, s.count AS count, "
        "s.weights AS weights, s.removed AS removed"
    )
    found_profiles = {
        r["profile"]: ProfileState(
            profile=r["profile"],
            generation=r["generation"],
            signature=r["signature"] or "",
            dimension=r["dimension"],
            built_at=native_datetime(r["built_at"]),
            count=r["count"] or 0,
            # (JSON: Neo4j holds no map as a property)
            weights=json.loads(r["weights"]) if r["weights"] else {},
            removed=r["removed"] or 0,
        )
        async for r in result
    }
    return States(found_parts, found_profiles)


async def states() -> States:
    """The state of each part and of each profile that has been built: the generation in use and what it was built
    with"""
    database = _database()

    @database.read_transaction
    async def read(tx: Any) -> States:
        return await _states(tx)

    return await read()


async def next_generation() -> int:
    """A generation number not used yet, by any part or profile: one more than the highest in use or written (a
    rebuild that stopped part way leaves its generation, which is not used again)"""
    database = _database()

    @database.read_transaction
    async def read(tx: Any) -> int:
        found = await _states(tx)
        top = max(
            [0]
            + [s.generation for s in found.parts.values()]
            + [s.generation for s in found.profiles.values()]
        )
        for label in (VECTOR, PROFILE_VECTOR):
            # (only what is above the highest in use is read: the index of `generation` finds it)
            result = await tx.run(
                f"MATCH (v:{label}) WHERE v.generation > $top RETURN max(v.generation) AS top",
                top=top,
            )
            record = await result.single()
            if record and record["top"] is not None:
                top = max(top, record["top"])
        return top + 1

    return await read()


# ---------------------------------------------------------------------------
# A new generation
# ---------------------------------------------------------------------------


def _rows(part_name: str, rows: Iterable[VectorRow]) -> list[dict[str, Any]]:
    """The rows as the queries take them: checked against the part's dimension, those of classes with
    `include=False` left out"""
    dimension = part(part_name).dimension()
    return [
        {
            "of": str(row.of),
            "type": row.type,
            "vector": check_length(part_name, row.of, row.vector, dimension),
        }
        for row in rows
        if meta.included(row.type)
    ]


def _pages[T](items: Sequence[T], size: int) -> Iterable[Sequence[T]]:
    for start in range(0, len(items), size):
        yield items[start : start + size]


WRITE_PART_QUERY = f"""
UNWIND $rows AS row
MERGE (v:{VECTOR} {{of: row.of, part: $part, generation: $generation}})
SET v.type = row.type, v.vector = row.vector
"""


async def write_generation(
    part_name: str,
    generation: int,
    rows: Iterable[VectorRow],
    *,
    page: int = WRITE_PAGE,
) -> int:
    """Write vectors of a part into a generation that is not in use (a rebuild's), a page of rows in each
    transaction. Every vector is checked against the part's dimension first. Safe to run again: a row written twice
    is one vector. Gives how many were written"""
    found = await states()
    in_use = found.parts.get(part_name)
    if in_use is not None and in_use.generation == generation:
        raise ValueError(
            f"Generation {generation} is the one of the {part_name} part in use: `set_vectors` changes that"
        )
    checked = _rows(part_name, rows)
    database = _database()

    @database.write_transaction
    async def write(tx: Any, batch: Sequence[dict[str, Any]]) -> None:
        await (
            await tx.run(
                WRITE_PART_QUERY,
                rows=list(batch),
                part=part_name,
                generation=generation,
            )
        ).consume()

    for batch in _pages(checked, page):
        await write(batch)
    return len(checked)


@dataclasses.dataclass(frozen=True)
class Combined:
    """A generation of a profile's vectors, written by `combine`, to be switched to"""

    profile: str
    generation: int
    count: int
    dimension: int
    signature: str
    parts: Mapping[str, int]
    """The generation of each part it was made from"""
    weights: Mapping[str, float] = dataclasses.field(default_factory=dict)
    """The weights it was made with (those above zero)"""


@dataclasses.dataclass(frozen=True)
class Built:
    """A generation of a part's vectors, written, to be switched to"""

    part: str
    generation: int
    count: int
    signature: str
    graph_sees: str
    stale: int = 0


OFS_QUERY = f"""
MATCH (v:{VECTOR} {{part: $part, generation: $generation}})
RETURN DISTINCT v.of AS of
"""

READ_PARTS_QUERY = f"""
UNWIND $ofs AS of
MATCH (v:{VECTOR} {{of: of}})
WHERE any(pair IN $pairs WHERE pair.part = v.part AND pair.generation = v.generation)
RETURN v.of AS of, v.part AS part, v.type AS type, v.vector AS vector
"""


def _profile_write_query(lay: Layout, labels: Sequence[str]) -> str:
    """Writes the rows' profile vectors in place, with exactly these labels of the profile's (`PGProfileVector`
    aside): the profile's groups that are not among them are taken away, for an item whose class changed"""
    others = [
        lay.group_label(g) for g in meta.groups() if lay.group_label(g) not in labels
    ]
    remove = f"REMOVE n:{':'.join(others)} " if others else ""
    return (
        "UNWIND $rows AS row "
        f"MERGE (n:{PROFILE_VECTOR} {{of: row.of, profile: $profile, generation: $generation}}) "
        f"{remove}SET n:{':'.join(labels)}, n.type = row.type, n.vector = row.vector"
    )


DELETE_PROFILE_VECTORS_QUERY = f"""
UNWIND $ofs AS of
MATCH (n:{PROFILE_VECTOR} {{of: of, profile: $profile, generation: $generation}})
DETACH DELETE n
"""


async def _read_parts(
    tx: Any,
    ofs: Sequence[str],
    generations: Mapping[str, int],
    prefer: str | None = None,
) -> dict[str, tuple[str, dict[str, list[float]]]]:
    """The vectors of these items in these generations of the parts, by item: (its type, its vectors by part). The
    type is the one the part `prefer` wrote, if it has a vector of the item (a part being rebuilt read the classes
    from the graph just now; the others may be older)"""
    pairs = [{"part": p, "generation": g} for p, g in generations.items()]
    result = await tx.run(READ_PARTS_QUERY, ofs=list(ofs), pairs=pairs)
    found: dict[str, tuple[str, dict[str, list[float]]]] = {}
    async for r in result:
        type_name, vectors = found.get(r["of"], (r["type"], {}))
        if r["part"] == prefer:
            type_name = r["type"]
        vectors[r["part"]] = list(r["vector"])
        found[r["of"]] = (type_name, vectors)
    return found


async def _write_combined(
    tx: Any,
    lay: Layout,
    generation: int,
    read: Mapping[str, tuple[str, dict[str, list[float]]]],
    types: Mapping[str, str] | None = None,
) -> int:
    """Write the profile vectors of the items read, grouped by their labels (a statement for each set of labels);
    an item of a class with `include=False`, or whose combined vector is all zeros, has none (its old one goes).
    Gives how many were written"""
    by_labels: dict[tuple[str, ...], list[dict[str, Any]]] = {}
    gone: list[str] = []
    for of, (type_name, vectors) in read.items():
        type_name = (types or {}).get(of, type_name)
        vector = lay.combine(vectors)
        if not meta.included(type_name) or not any(vector):
            gone.append(of)
            continue
        labels = tuple(lay.labels(type_name))
        by_labels.setdefault(labels, []).append(
            {"of": of, "type": type_name, "vector": vector}
        )
    for labels, rows in by_labels.items():
        await (
            await tx.run(
                _profile_write_query(lay, labels),
                rows=rows,
                profile=lay.profile,
                generation=generation,
            )
        ).consume()
    if gone:
        await (
            await tx.run(
                DELETE_PROFILE_VECTORS_QUERY,
                ofs=gone,
                profile=lay.profile,
                generation=generation,
            )
        ).consume()
    return sum(len(rows) for rows in by_labels.values())


async def combine(
    profile_name: str,
    generation: int,
    *,
    using: Mapping[str, int] | None = None,
    page: int = WRITE_PAGE,
) -> Combined:
    """Write a new generation of a profile's vectors from the vectors of its parts: of each part the generation in
    `using` (the new one of a part being rebuilt), or else the one in use. In pages of items (by `of`), each read and
    written in transactions of its own; safe to run again. Gives what `switch` is to be told"""
    lay = layout(profile_name)
    found = await states()
    in_use = found.profiles.get(profile_name)
    if in_use is not None and in_use.generation == generation:
        raise ValueError(
            f"Generation {generation} is the one of the profile {profile_name!r} in use: write a new one"
        )
    generations = {
        name: (using or {}).get(
            name, found.parts[name].generation if name in found.parts else None
        )
        for name in lay.weights
    }
    known = {name: g for name, g in generations.items() if g is not None}
    database = _database()

    @database.read_transaction
    async def items(tx: Any) -> list[str]:
        ofs: set[str] = set()
        for name, part_generation in known.items():
            result = await tx.run(OFS_QUERY, part=name, generation=part_generation)
            ofs |= {r["of"] async for r in result}
        return sorted(ofs)

    rebuilt = [name for name in (using or {}) if name in known]
    prefer = rebuilt[0] if len(rebuilt) == 1 else None

    @database.read_transaction
    async def read(
        tx: Any, ofs: Sequence[str]
    ) -> dict[str, tuple[str, dict[str, list[float]]]]:
        return await _read_parts(tx, ofs, known, prefer)

    @database.write_transaction
    async def write(
        tx: Any, read_: Mapping[str, tuple[str, dict[str, list[float]]]]
    ) -> int:
        return await _write_combined(tx, lay, generation, read_)

    count = 0
    for ofs in _pages(await items() if known else [], page):
        count += await write(await read(ofs))
    return Combined(
        profile=profile_name,
        generation=generation,
        count=count,
        dimension=lay.dimension,
        signature=lay.signature(),
        parts=known,
        weights=dict(lay.weights),
    )


SWITCH_PART_QUERY = f"""
MERGE (s:{STATE} {{part: $part}})
SET s.generation = $generation, s.built_at = $at, s.count = $count, s.stale = $stale, s.signature = $signature,
    s.graph_sees = $graph_sees
"""

SWITCH_PROFILES_QUERY = f"""
UNWIND $profiles AS p
MERGE (s:{PROFILE_STATE} {{profile: p.profile}})
SET s.generation = p.generation, s.signature = p.signature, s.dimension = p.dimension, s.built_at = $at,
    s.count = p.count, s.weights = p.weights, s.removed = 0
"""


async def switch(
    built: Built | Sequence[Built] | None, combined: Sequence[Combined] = ()
) -> None:
    """Make new generations the ones in use, in one transaction that sets `generation` (and what they were built with)
    on the state nodes and does nothing else: of the parts `built` (one, several, or none) and of the profiles
    `combined`. Every profile of the settings that weighs one of the parts must be among them, made from that part's
    new generation, or it would be left combining vectors that are about to go"""
    if built is None:
        made_parts: list[Built] = []
    elif isinstance(built, Built):
        made_parts = [built]
    else:
        made_parts = list(built)
    given = {c.profile: c for c in combined}
    for made_part in made_parts:
        for name in profiles_weighing(made_part.part):
            made = given.get(name)
            if made is None or made.parts.get(made_part.part) != made_part.generation:
                raise ValueError(
                    f"The profile {name!r} weighs the {made_part.part} part: it has to be combined from generation "
                    f"{made_part.generation} of it and switched with it"
                )
    at = datetime.datetime.now(datetime.UTC)
    database = _database()

    @database.write_transaction
    async def write(tx: Any) -> None:
        for made_part in made_parts:
            await (
                await tx.run(
                    SWITCH_PART_QUERY,
                    part=made_part.part,
                    generation=made_part.generation,
                    at=at,
                    count=made_part.count,
                    stale=made_part.stale,
                    signature=made_part.signature,
                    graph_sees=made_part.graph_sees,
                )
            ).consume()
        if combined:
            await (
                await tx.run(
                    SWITCH_PROFILES_QUERY,
                    at=at,
                    profiles=[
                        {
                            "profile": c.profile,
                            "generation": c.generation,
                            "signature": c.signature,
                            "dimension": c.dimension,
                            "count": c.count,
                            "weights": json.dumps(dict(sorted(c.weights.items()))),
                        }
                        for c in combined
                    ],
                )
            ).consume()

    await write()


async def _drop(label: str, key: str, value: str, generation: int, page: int) -> int:
    database = _database()

    @database.write_transaction
    async def delete(tx: Any) -> int:
        result = await tx.run(
            f"MATCH (v:{label} {{{key}: $value, generation: $generation}}) WITH v LIMIT $limit "
            "DETACH DELETE v RETURN count(*) AS n",
            value=value,
            generation=generation,
            limit=page,
        )
        record = await result.single()
        return record["n"] if record else 0

    total = 0
    while True:
        gone = await delete()
        total += gone
        if gone < page:
            return total


async def drop_generation(
    part_name: str, generation: int, *, page: int = DROP_PAGE
) -> int:
    """Delete a generation of a part's vectors that is not in use, in batches. Gives how many went"""
    in_use = (await states()).parts.get(part_name)
    if in_use is not None and in_use.generation == generation:
        raise ValueError(f"Generation {generation} of the {part_name} part is in use")
    return await _drop(VECTOR, "part", part_name, generation, page)


async def drop_profile_generation(
    profile_name: str, generation: int, *, page: int = DROP_PAGE
) -> int:
    """Delete a generation of a profile's vectors that is not in use, in batches. Gives how many went"""
    in_use = (await states()).profiles.get(profile_name)
    if in_use is not None and in_use.generation == generation:
        raise ValueError(
            f"Generation {generation} of the profile {profile_name!r} is in use"
        )
    return await _drop(PROFILE_VECTOR, "profile", profile_name, generation, page)


async def _drop_below(label: str, key: str, value: str, keep: int, page: int) -> int:
    database = _database()

    # (a range of the index of `generation`: what is below the one kept is every older generation, the one that was
    # in use and any a rebuild that stopped part way left)
    @database.write_transaction
    async def delete(tx: Any) -> int:
        result = await tx.run(
            f"MATCH (v:{label}) WHERE v.generation < $keep AND v.{key} = $value WITH v LIMIT $limit "
            "DETACH DELETE v RETURN count(*) AS n",
            value=value,
            keep=keep,
            limit=page,
        )
        record = await result.single()
        return record["n"] if record else 0

    total = 0
    while True:
        gone = await delete()
        total += gone
        if gone < page:
            return total


async def drop_older(part_name: str, keep: int, *, page: int = DROP_PAGE) -> int:
    """Delete every generation of a part's vectors below `keep` (the one in use after a rebuild's switch), in batches.
    Gives how many went"""
    in_use = (await states()).parts.get(part_name)
    if in_use is not None and in_use.generation < keep:
        raise ValueError(
            f"Generation {in_use.generation} of the {part_name} part is in use"
        )
    return await _drop_below(VECTOR, "part", part_name, keep, page)


async def drop_older_profile(
    profile_name: str, keep: int, *, page: int = DROP_PAGE
) -> int:
    """Delete every generation of a profile's vectors below `keep`, in batches. Gives how many went"""
    in_use = (await states()).profiles.get(profile_name)
    if in_use is not None and in_use.generation < keep:
        raise ValueError(
            f"Generation {in_use.generation} of the profile {profile_name!r} is in use"
        )
    return await _drop_below(PROFILE_VECTOR, "profile", profile_name, keep, page)


# ---------------------------------------------------------------------------
# The generation in use
# ---------------------------------------------------------------------------


IN_USE_COUNTS_QUERIES = {
    kind: f"UNWIND $ofs AS of MATCH (v:{label} {{of: of}}) "
    f"RETURN v.{kind} AS name, v.generation AS generation, count(v) AS n"
    for kind, label in (("part", VECTOR), ("profile", PROFILE_VECTOR))
}

ADJUST_COUNT_QUERIES = {
    "part": f"UNWIND $rows AS row MATCH (s:{STATE} {{part: row.name}}) "
    "SET s.count = coalesce(s.count, 0) + row.delta",
    "profile": f"UNWIND $rows AS row MATCH (s:{PROFILE_STATE} {{profile: row.name}}) "
    "SET s.count = coalesce(s.count, 0) + row.delta, "
    "s.removed = coalesce(s.removed, 0) + CASE WHEN row.delta < 0 THEN -row.delta ELSE 0 END",
}


async def _in_use_counts(
    tx: Any, found: States, ofs: Sequence[str]
) -> dict[tuple[str, str], int]:
    """How many vectors in use these items have, by (`"part"` or `"profile"`, its name): of the generation each state
    says"""
    in_use = {
        "part": {name: s.generation for name, s in found.parts.items()},
        "profile": {name: s.generation for name, s in found.profiles.items()},
    }
    counts: dict[tuple[str, str], int] = {}
    for kind, query in IN_USE_COUNTS_QUERIES.items():
        async for r in await tx.run(query, ofs=list(ofs)):
            if in_use[kind].get(r["name"]) == r["generation"]:
                counts[(kind, r["name"])] = r["n"]
    return counts


async def _adjust_counts(
    tx: Any, before: Mapping[tuple[str, str], int], after: Mapping[tuple[str, str], int]
) -> None:
    """Move the states' `count` by what a change in place did to the vectors in use (so that the count stays that of
    the generation in use, which `search.nearest` asks the index for at most twice of)"""
    for kind, query in ADJUST_COUNT_QUERIES.items():
        rows = [
            {"name": key[1], "delta": after.get(key, 0) - before.get(key, 0)}
            for key in sorted(set(before) | set(after))
            if key[0] == kind and after.get(key, 0) != before.get(key, 0)
        ]
        if rows:
            await (await tx.run(query, rows=rows)).consume()


async def set_vectors(part_name: str, rows: Iterable[VectorRow]) -> int:
    """Replace the part's vectors of these items in the generation in use, and make their vectors of each profile that
    weighs the part again, in place, in the same transaction (a refresh after a write). `RebuildDue` if the part has
    no generation in use, or a profile's in use is of another dimension than today's. Gives how many were written"""
    given = list(rows)
    checked = _rows(part_name, given)
    # (the items of classes with `include=False`: whatever vectors they have go)
    dropped = sorted({str(row.of) for row in given} - {row["of"] for row in checked})
    weighing = {name: layout(name) for name in profiles_weighing(part_name)}
    database = _database()

    @database.write_transaction
    async def write(tx: Any) -> int:
        found = await _states(tx)
        in_use = found.parts.get(part_name)
        if in_use is None:
            raise RebuildDue(
                f"The {part_name} part has no vectors in use: it has to be rebuilt first"
            )
        for name, lay in weighing.items():
            state = found.profiles.get(name)
            if state is not None and state.dimension != lay.dimension:
                raise RebuildDue(
                    f"The vectors of the profile {name!r} in use are of dimension {state.dimension}; its parts now "
                    f"make {lay.dimension}: it has to be rebuilt"
                )
        touched = sorted({row["of"] for row in checked} | set(dropped))
        before = await _in_use_counts(tx, found, touched)
        await (
            await tx.run(
                WRITE_PART_QUERY,
                rows=checked,
                part=part_name,
                generation=in_use.generation,
            )
        ).consume()
        if dropped:
            await (
                await tx.run(
                    f"UNWIND $ofs AS of MATCH (v:{VECTOR} {{of: of}}) DETACH DELETE v",
                    ofs=dropped,
                )
            ).consume()
        types = {row["of"]: row["type"] for row in checked}
        ofs = sorted(types.keys() | set(dropped))
        for name, lay in weighing.items():
            state = found.profiles.get(name)
            if state is None:
                continue  # (not built: nothing of it is in use to keep up)
            generations = {
                p: found.parts[p].generation for p in lay.weights if p in found.parts
            }
            read = await _read_parts(tx, ofs, generations, part_name)
            for of in dropped:
                read.setdefault(of, ("", {}))
            await _write_combined(tx, lay, state.generation, read, types)
        await _adjust_counts(tx, before, await _in_use_counts(tx, found, touched))
        return len(checked)

    return await write()


async def remove_vectors(part_name: str, ids: Iterable[str]) -> int:
    """Delete the part's vectors of these items in the generation in use, and make their vectors of each profile that
    weighs the part again from the other parts, in place, in the same transaction (a refresh after which an item that
    is still there has no vector of this part: a graph part's item now joined to nothing). An item left with no
    vector of any part a profile weighs has none of the profile. Nothing if the part has no generation in use. Gives
    how many went"""
    ofs = sorted({str(i) for i in ids})
    if not ofs:
        return 0
    weighing = {name: layout(name) for name in profiles_weighing(part_name)}
    database = _database()

    @database.write_transaction
    async def remove(tx: Any) -> int:
        found = await _states(tx)
        in_use = found.parts.get(part_name)
        if in_use is None:
            return 0
        before = await _in_use_counts(tx, found, ofs)
        result = await tx.run(
            f"UNWIND $ofs AS of MATCH (v:{VECTOR} {{of: of, part: $part, generation: $generation}}) "
            "DETACH DELETE v RETURN count(*) AS n",
            ofs=ofs,
            part=part_name,
            generation=in_use.generation,
        )
        record = await result.single()
        for name, lay in weighing.items():
            state = found.profiles.get(name)
            if state is None or state.dimension != lay.dimension:
                continue  # (not built, or due for a rebuild: nothing of it in use to keep up)
            generations = {
                p: found.parts[p].generation for p in lay.weights if p in found.parts
            }
            read = await _read_parts(tx, ofs, generations)
            for of in ofs:
                read.setdefault(of, ("", {}))
            await _write_combined(tx, lay, state.generation, read)
        await _adjust_counts(tx, before, await _in_use_counts(tx, found, ofs))
        return record["n"] if record else 0

    return await remove()


async def delete_for(ids: Iterable[str]) -> int:
    """Delete every vector of these items, of every part and profile and generation (items deleted, or merged into
    another). Gives how many nodes went"""
    ofs = sorted({str(i) for i in ids})
    if not ofs:
        return 0
    database = _database()

    @database.write_transaction
    async def delete(tx: Any) -> int:
        found = await _states(tx)
        before = await _in_use_counts(tx, found, ofs)
        total = 0
        for label in (VECTOR, PROFILE_VECTOR):
            result = await tx.run(
                f"UNWIND $ofs AS of MATCH (v:{label} {{of: of}}) DETACH DELETE v RETURN count(*) AS n",
                ofs=ofs,
            )
            record = await result.single()
            total += record["n"] if record else 0
        await _adjust_counts(tx, before, {})
        return total

    return await delete()


async def read_in(tx: Any, of: str, found: States) -> dict[str, list[float]]:
    """`read`, in a transaction the caller has, with the states it read in it"""
    result = await tx.run(
        f"MATCH (v:{VECTOR} {{of: $of}}) RETURN v.part AS part, v.generation AS generation, v.vector AS vector",
        of=str(of),
    )
    return {
        r["part"]: list(r["vector"])
        async for r in result
        if r["part"] in found.parts
        and found.parts[r["part"]].generation == r["generation"]
    }


async def read(of: str) -> dict[str, list[float]]:
    """The vectors of an item in use, by part (the generation each part's state names)"""
    database = _database()

    @database.read_transaction
    async def get(tx: Any) -> dict[str, list[float]]:
        return await read_in(tx, of, await _states(tx))

    return await get()


async def read_profile(
    of: str, profile_name: str
) -> tuple[list[float], list[str]] | None:
    """The vector of an item in use for a profile, and its labels (`PGProfileVector` aside, in order); None if it
    has none"""
    database = _database()

    @database.read_transaction
    async def get(tx: Any) -> tuple[list[float], list[str]] | None:
        found = await _states(tx)
        state = found.profiles.get(profile_name)
        if state is None:
            return None
        result = await tx.run(
            f"MATCH (n:{PROFILE_VECTOR} {{of: $of, profile: $profile, generation: $generation}}) "
            "RETURN n.vector AS vector, labels(n) AS labels",
            of=str(of),
            profile=profile_name,
            generation=state.generation,
        )
        record = await result.single()
        if record is None:
            return None
        return list(record["vector"]), sorted(
            label for label in record["labels"] if label != PROFILE_VECTOR
        )

    return await get()
