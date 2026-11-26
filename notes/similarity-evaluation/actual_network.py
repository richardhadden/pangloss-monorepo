"""Step 5.4 of implementation_docs/spaces-and-comparison-plan.md, measured before anything is built: what a second
graph part would cost, in which a statement joins by what the walk says of it (the rule "by-walk" of step 5.3), and
how the nearest neighbours then differ. Nothing here is in a package: the second part is a trial, made in this file
of the graph part's own pieces (`pangloss_fastrp`), and registered only in the processes this file starts.

The trial part, `actual`: the graph part's reader, with each node's stored path read beside it; a nested document
whose path has a space is walked (`pangloss_models.spaces.signature`), and

    asserted (1)                    joins as in the structural network
    denied (-1)                     is out of the graph (as a deleted node is)
    neither, leaning for            joins at a weight by its degree (`DEGREE_WEIGHT`), as a class of its own
    neither, leaning against or not is out of the graph

On the planted world for comparison at size (`planted.py --compared`), in a scratch database, never :7687 or :7688:

    docker run -d --name pangloss-memgraph-compared -p 7716:7687 -e MEMGRAPH_USER=test -e MEMGRAPH_PASSWORD=test \
        memgraph/memgraph-mage:3.14.0 --storage-properties-on-edges=true
    docker run -d --name pangloss-neo4j-compared -p 7717:7687 -e NEO4J_AUTH=neo4j/test-password \
        -e NEO4J_server_memory_heap_max__size=4g -e NEO4J_server_memory_pagecache_size=1g neo4j:2026.10.1

    uv run python notes/similarity-evaluation/planted.py write DIR --compared --people 32000
    uv run python notes/similarity-evaluation/planted.py load DIR memgraph bolt://localhost:7716 --compared
    uv run python notes/similarity-evaluation/actual_network.py rebuild memgraph bolt://localhost:7716 structural
    uv run python notes/similarity-evaluation/actual_network.py refresh memgraph bolt://localhost:7716 structural
    uv run python notes/similarity-evaluation/actual_network.py rebuild memgraph bolt://localhost:7716 actual
    uv run python notes/similarity-evaluation/actual_network.py refresh memgraph bolt://localhost:7716 actual
    uv run python notes/similarity-evaluation/actual_network.py neighbours memgraph bolt://localhost:7716

`structural`: the parts `class` and `graph`, the profile `default` (graph 1, class 0.1), as a project has today.
`actual`: the trial part registered beside them and a second profile, `who_met` (actual 1, class 0.1); its `rebuild`
rebuilds the new part alone, which is what adding the part to a project would cost. `refresh` writes factoids of the
world again (the same ones in both phases) and times each turn of the vectors' worker.

    uv run python notes/similarity-evaluation/actual_network.py weights [--people 1500] [--seeds 1 2 3]

No database (`spaces_graph.py`'s graph in memory): the rule "by-walk" at several tables of weights.
"""

import argparse
import asyncio
import collections
import dataclasses
import json
import random
import statistics
import sys
import time
import types
import typing
from pathlib import Path

HERE = Path(__file__).resolve().parent
NAME = "actual"
# (the first guess of step 5.3: the weight of a statement that leans for, by its degree; none entered and no default 0.5)
DEGREE_WEIGHT = {"expected": 0.8, "likely": 0.6, "possible": 0.4, "unlikely": 0.2, "impossible": 0.0, None: 0.5}  # fmt: skip
PROFILES = {
    "structural": {"default": {"graph": 1, "class": 0.1}},
    "actual": {"default": {"graph": 1, "class": 0.1}, "who_met": {NAME: 1, "class": 0.1}},
}  # fmt: skip
APPS = ["pangloss_derived", "pangloss_library", "pangloss_criteria", "pangloss_vectors", "pangloss_fastrp"]  # fmt: skip
# (seconds, by what they were spent on; filled by the trial part and by the wrappers of the graph part)
SPENT: dict[str, float] = collections.defaultdict(float)


def planted_script() -> typing.Any:
    """`planted.py` as a module, without its `main()` run, for the world for comparison"""
    source = (HERE / "planted.py").read_text(encoding="utf-8").replace("\nmain()\n", "\n")  # fmt: skip
    module = types.ModuleType("planted_script")
    exec(compile(source, "planted.py", "exec"), module.__dict__)
    module.COMPARED = module.DATED = True
    return module


# ---------------------------------------------------------------------------
# The trial part
# ---------------------------------------------------------------------------


class Walk:
    """The weight of a node by its stored path, the walk asked once for each shape of path (a path without its ids)"""

    def __init__(self, graph: typing.Any):
        from pangloss_fastrp.maths import STOP
        from pangloss_models import spaces

        self.spaces = spaces.registered_spaces()
        self.grounds = spaces.registered_grounds()
        self.documents = {t for t, kind in graph.kinds.items() if kind == STOP and graph.documents.get(t)}  # fmt: skip
        self.shapes: dict[tuple, float] = {}
        self.read = self.in_spaces = 0
        self.weights: collections.Counter = collections.Counter()

    def weight(self, type_name: str, path: typing.Any) -> float:
        if path is None or type_name not in self.documents:
            return 1.0
        self.read += 1
        if isinstance(path, str):
            # (Neo4j keeps the path as JSON text)
            if '"space"' not in path:
                return 1.0
            path = json.loads(path)
        if not any(entry["kind"] == "space" for entry in path):
            return 1.0
        self.in_spaces += 1
        shape = tuple(tuple(sorted((k, v) for k, v in entry.items() if k != "id")) for entry in path)  # fmt: skip
        found = self.shapes.get(shape)
        if found is None:
            from pangloss_models.spaces import signature

            said = signature(path, self.spaces, self.grounds)
            if said.veridical == 1:
                found = 1.0
            elif said.veridical == -1 or said.lean != "for":
                found = 0.0
            else:
                found = DEGREE_WEIGHT[said.degree]
            self.shapes[shape] = found
        self.weights[found] += 1
        return found

    def apply(self, row: dict[str, typing.Any]) -> None:
        """A row of a node as the reader has it, changed by the walk: out (as deleted), or of the class of its weight"""
        weight = self.weight(row["type"], row.pop("path", None))
        if weight == 0.0:
            row["deleted"] = True
        elif weight != 1.0:
            row["type"] = f"{row['type']}@{weight}"


def actual_maps(graph: typing.Any) -> typing.Any:
    """The graph part's maps, with a class for each weight a nested document can join at"""
    from pangloss_fastrp.maths import STOP

    kinds, weights = dict(graph.kinds), dict(graph.class_weight)
    documents, field_weight, shares = dict(graph.documents), dict(graph.field_weight), dict(graph.shares)  # fmt: skip
    for type_name in [t for t, kind in graph.kinds.items() if kind == STOP and graph.documents.get(t)]:  # fmt: skip
        for weight in sorted(set(DEGREE_WEIGHT.values()) - {0.0, 1.0}):
            name = f"{type_name}@{weight}"
            kinds[name], documents[name] = STOP, True
            weights[name] = weight * graph.class_weight.get(type_name, 1.0)
            for held, table in ((graph.field_weight, field_weight), (graph.shares, shares)):  # fmt: skip
                for key, value in held.items():
                    if key.startswith(f"{type_name}."):
                        table[f"{name}.{key.split('.', 1)[1]}"] = value
    return dataclasses.replace(
        graph,
        kinds=kinds,
        class_weight=weights,
        documents=documents,
        field_weight=field_weight,
        shares=shares,
    )


def _maps() -> typing.Any:
    from pangloss_fastrp import maps

    return actual_maps(maps.graph_maps())


async def load_walked(graph: typing.Any, walk: Walk) -> typing.Any:
    """`cypher_reader.load_all`, with each node's stored path read in the page and walked"""
    from pangloss_core import backend
    from pangloss_fastrp import cypher_reader as cr
    from pangloss_fastrp.memory import MemoryReader

    current = backend.current()
    database = current.database()
    names = cr.used_properties(graph)
    edges_query = cr.load_edges_query(graph)
    page_query = cr.PAGE_QUERY.replace("n.target_id])", f"n.target_id, {current.dialect.meta_property('n', 'path')}])")  # fmt: skip
    assert page_query != cr.PAGE_QUERY
    columns = (*cr.PAGE_COLUMNS, "path")

    @database.read_transaction
    async def read(tx: typing.Any, after: str):
        nodes = await cr._one_row(tx, page_query, after=after, page=cr.PAGE)
        ids = [str(row[0]) for row in nodes]
        edges = await cr._one_row(tx, edges_query, ids=ids) if ids else []
        return nodes, edges

    rows: list[dict[str, typing.Any]] = []
    edges: list[typing.Any] = []
    after = ""
    while True:
        began = time.perf_counter()
        nodes, found = await read(after)
        SPENT["actual: read"] += time.perf_counter() - began
        began = time.perf_counter()
        page = [dict(zip(columns, row, strict=True)) for row in nodes]
        for row in page:
            walk.apply(row)
        SPENT["actual: walk"] += time.perf_counter() - began
        rows += page
        edges += cr.loaded_edges(found, names)
        if len(nodes) < cr.PAGE:
            break
        after = max(str(row[0]) for row in nodes)
    by_id = {str(row["id"]): row for row in rows}
    return MemoryReader(
        [cr.node_of(row, by_id.get(str(row["head"])) if row["head"] else None, graph) for row in rows],  # fmt: skip
        edges,
    )


def walked_reader(walk: Walk) -> type:
    from pangloss_core import backend
    from pangloss_fastrp import cypher_reader as cr

    nodes_query = cr.NODES_QUERY.rstrip() + f", {backend.current().dialect.meta_property('n', 'path')} AS path\n"  # fmt: skip

    class WalkedReader(cr.RememberingReader):
        """The reader of a refresh, each node's path read with it and walked"""

        def _each(self, query: str, ids: typing.Iterable[str]) -> list[dict[str, typing.Any]]:  # fmt: skip
            if query is not cr.NODES_QUERY:
                return super()._each(query, ids)
            rows = super()._each(nodes_query, ids)
            for row in rows:
                walk.apply(row)
            return rows

    return WalkedReader


async def refresh_walked(changed: typing.Any, write: typing.Any) -> typing.Any:
    """`part.refresh_ids` for the trial part: the same units, groups and cap, on the walked reader. A head past the
    cap alone is counted stale and given nothing (the graph part writes it an approximate vector)"""
    from pangloss_core import backend
    from pangloss_fastrp import cypher_reader as cr
    from pangloss_fastrp import maths, part
    from pangloss_fastrp.settings import refresh_cap
    from pangloss_vectors import store
    from pangloss_vectors.parts import Refreshed, VectorRow

    written = {str(item.id) for item in changed.written}
    units = sorted(
        [part.Unit(i, part.WRITTEN) for i in written]
        + [part.Unit(str(i), part.REMOVED) for i in changed.removed if str(i) not in written]  # fmt: skip
        + [part.Unit(str(i), part.BEFORE) for i in set(changed.before)]
    )
    if not units:
        return Refreshed()
    graph, cap = _maps(), refresh_cap()
    Reader = walked_reader(Walk(graph))

    def work(reader: typing.Any):
        def attempt(group: typing.Sequence[typing.Any]):
            heads = [u.id for u in group if u.kind != part.BEFORE]
            named = [u.id for u in group if u.kind == part.BEFORE]
            try:
                return maths.refresh(reader, graph, part.changed_stops(reader, graph, heads, named), cap)  # fmt: skip
            except maths.TooLarge:
                return None

        made, alone = part.in_groups(units, attempt)
        vectors: dict[str, typing.Any] = {}
        gone: set[str] = set()
        for found in made:
            for i in found.gone:
                vectors.pop(i, None)
            gone = (gone - set(found.vectors)) | found.gone
            vectors.update(found.vectors)
        return vectors, gone, {i: reader.seen[i].type for i in vectors}, alone

    database = backend.current().database()

    @database.read_transaction
    async def run(tx: typing.Any):
        reader = Reader(tx, asyncio.get_running_loop(), graph, cr.REMEMBERED_CAPS * cap)  # fmt: skip
        return await asyncio.to_thread(work, reader)

    vectors, gone, types_of, alone = await run()
    rows = [
        VectorRow(of=i, type=types_of[i].split("@")[0], vector=[float(x) for x in vector])  # fmt: skip
        for i, vector in sorted(vectors.items())
    ]
    for start in range(0, len(rows), 1000):
        await write(rows[start : start + 1000])
    if gone:
        await store.remove_vectors(NAME, sorted(gone))
    return Refreshed(written=len(rows), stale=len(alone))


class ActualPart:
    """The trial part: the graph part with the walk in its reader"""

    name = NAME
    local = True
    requires: frozenset[str] = frozenset()
    weight = 0.0

    def dimension(self) -> int:
        from pangloss_fastrp.settings import dimension

        return dimension()

    def signature(self) -> str:
        from pangloss_vectors.parts import signature_of

        return signature_of(_maps().plain(), {str(k): v for k, v in DEGREE_WEIGHT.items()})  # fmt: skip

    async def rebuild(self, write: typing.Any) -> int:
        from pangloss_fastrp import maths
        from pangloss_vectors.parts import VectorRow

        graph = _maps()
        walk = Walk(graph)
        reader = await load_walked(graph, walk)
        began = time.perf_counter()
        vectors = await asyncio.to_thread(maths.rebuild, reader, graph)
        SPENT["actual: maths"] += time.perf_counter() - began
        began = time.perf_counter()
        rows = [
            VectorRow(of=i, type=reader.node[i].type.split("@")[0], vector=[float(x) for x in vector])  # fmt: skip
            for i, vector in sorted(vectors.items())
        ]
        for start in range(0, len(rows), 1000):
            await write(rows[start : start + 1000])
        SPENT["actual: write"] += time.perf_counter() - began
        print(
            f"  the walk: {walk.read:,} nested documents' paths read, {walk.in_spaces:,} with a space in them, "
            f"{len(walk.shapes):,} shapes of path walked; by weight: "
            + ", ".join(f"{w:g}: {n:,}" for w, n in sorted(walk.weights.items()))
        )
        return len(rows)

    async def refresh(self, changed: typing.Any, write: typing.Any) -> typing.Any:
        return await refresh_walked(changed, write)

    async def overlay(self, plan: typing.Any) -> dict[str, typing.Any]:
        return {}


# ---------------------------------------------------------------------------
# The measurements in a database
# ---------------------------------------------------------------------------


def time_the_graph_part() -> None:
    """The graph part's own rebuild, by what it spends: its read, its maths, and the rest (the writing)"""
    from pangloss_fastrp import cypher_reader, maths

    load_all, rebuild = cypher_reader.load_all, maths.rebuild

    async def timed_load(*args: typing.Any, **kwargs: typing.Any):
        began = time.perf_counter()
        try:
            return await load_all(*args, **kwargs)
        finally:
            SPENT["graph: read"] += time.perf_counter() - began

    def timed_rebuild(*args: typing.Any, **kwargs: typing.Any):
        began = time.perf_counter()
        try:
            return rebuild(*args, **kwargs)
        finally:
            SPENT["graph: maths"] += time.perf_counter() - began

    cypher_reader.load_all, maths.rebuild = timed_load, timed_rebuild


async def connect(script: typing.Any, args: argparse.Namespace, phase: str) -> typing.Any:  # fmt: skip
    if phase == "actual":
        from pangloss_vectors.parts import register_part

        register_part(ActualPart())
    return await script.connected(args.backend, args.url, APPS, {"VECTORS_PROFILES": PROFILES[phase]})  # fmt: skip


async def rebuild(args: argparse.Namespace) -> None:
    script = planted_script()
    storage = await connect(script, args, args.phase)
    from pangloss_vectors import rebuild as rebuild_module

    time_the_graph_part()
    print(f"# {args.phase}, {args.backend} ({args.url})")
    began = time.perf_counter()
    print("indexes:", ", ".join(await script.make_indexes()), f"({time.perf_counter() - began:.1f} s)")  # fmt: skip
    began = time.perf_counter()
    done = await rebuild_module.rebuild(NAME if args.phase == "actual" else None)
    print(f"rebuild: {time.perf_counter() - began:.1f} s in all")
    for p in done.parts:
        print(f"  part {p.part}: generation {p.generation}, {p.count:,} vectors, {p.seconds:.1f} s")  # fmt: skip
    for p in done.profiles:
        print(f"  profile {p.profile}: generation {p.generation}, {p.count:,} vectors, {p.seconds:.1f} s")  # fmt: skip
    print("  of which: " + ", ".join(f"{what} {seconds:.1f} s" for what, seconds in sorted(SPENT.items())))  # fmt: skip
    await storage.setup.disconnect()


def sample_of(world: typing.Any, count: int) -> list[tuple[str, dict]]:
    """Factoids to write again, the same for the same world: half of the plain world, half with a statement in a
    space; each with what kind it is"""
    rng = random.Random(f"{world.seed} refresh")
    in_spaces = sorted({told.factoid for told in world.told.values() if told.spaces})
    by_label = {factoid["label"]: factoid for factoid in world.factoids}
    plain = [f for f in world.factoids if f["label"] not in set(in_spaces)]
    return [("plain", f) for f in rng.sample(plain, count // 2)] + [
        ("in a space", by_label[label]) for label in rng.sample(in_spaces, count - count // 2)  # fmt: skip
    ]


def said(values: list[float], unit: str = "ms") -> str:
    ordered = sorted(values)
    return (
        f"median {statistics.median(ordered):,.0f} {unit}, 90% {ordered[int(0.9 * (len(ordered) - 1))]:,.0f}, "
        f"most {ordered[-1]:,.0f}"
    )


async def refresh(args: argparse.Namespace) -> None:
    script = planted_script()
    storage = await connect(script, args, args.phase)
    from pangloss_models import ModelRegistry
    from pangloss_testing import planted
    from pangloss_vectors import parts
    from pangloss_vectors.worker import run_pending

    world = planted.world(seed=args.seed, people=args.people, compared=True)
    spent: dict[str, list[float]] = collections.defaultdict(list)
    wrote: dict[str, list[int]] = collections.defaultdict(list)
    turn: dict[str, float] = {}
    for made in parts.parts().values():
        original = type(made).refresh

        def wrap(original=original, name=made.name):
            async def timed(self, changed, write):
                began = time.perf_counter()
                done = await original(self, changed, write)
                turn[name] = (time.perf_counter() - began) * 1000
                turn[f"{name} written"] = done.written
                turn[f"{name} stale"] = done.stale
                return done

            return timed

        type(made).refresh = wrap()
    Factoid = ModelRegistry.all_models()["Factoid"]
    print(f"# refresh, {args.phase}, {args.backend} ({args.url}): parts {', '.join(parts.parts())}; profiles {', '.join(PROFILES[args.phase])}")  # fmt: skip
    began = time.perf_counter()
    print(f"before: {await run_pending()} heads pending, done in {time.perf_counter() - began:.1f} s")  # fmt: skip
    stale = 0
    for n, (kind, payload) in enumerate(sample_of(world, args.sample)):
        began = time.perf_counter()
        await Factoid.Create(**{**payload, "label": f"{payload['label']} (again, {args.phase} {n})"}).save()  # fmt: skip
        spent[f"{kind}: the write"].append((time.perf_counter() - began) * 1000)
        turn.clear()
        began = time.perf_counter()
        heads = await run_pending()
        total = (time.perf_counter() - began) * 1000
        assert heads == 1, heads
        spent[f"{kind}: the turn"].append(total)
        for name in parts.parts():
            spent[f"{kind}: refresh {name}"].append(turn.get(name, 0.0))
            wrote[f"{kind}: {name}"].append(int(turn.get(f"{name} written", 0)))
            stale += int(turn.get(f"{name} stale", 0))
        spent[f"{kind}: the rest of the turn"].append(total - sum(turn.get(name, 0.0) for name in parts.parts()))  # fmt: skip
    for what, values in spent.items():
        print(f"  {what:<34} {said(values)}  (n {len(values)})")
    for what, values in wrote.items():
        print(f"  vectors written, {what:<22} {said([float(v) for v in values], '')}")  # fmt: skip
    print(f"  stale: {stale}")
    await storage.setup.disconnect()


def named_unasserted(world: typing.Any) -> set[str]:
    """The ids of the entities a statement names that is in a space (whatever the walk says of it)"""
    found: set[str] = set()

    def ids(value: typing.Any) -> None:
        if isinstance(value, dict):
            if "id" in value and "type" in value:
                found.add(value["id"])
            for inner in value.values():
                ids(inner)
        elif isinstance(value, list):
            for inner in value:
                ids(inner)

    for told in world.told.values():
        if told.spaces:
            ids(world.statement(told.label))
    return found


def nearest_ten(matrix: typing.Any) -> typing.Any:
    """The rows of the ten nearest rows of each row, by cosine (the rows at length one), in blocks"""
    import numpy as np

    out = np.zeros((len(matrix), 10), dtype=np.int64)
    for start in range(0, len(matrix), 2000):
        scores = matrix[start : start + 2000] @ matrix.T
        scores[np.arange(len(scores)), np.arange(start, start + len(scores))] = -2.0
        top = np.argpartition(-scores, 10, axis=1)[:, :10]
        # (the ten in order, nearest first)
        order = np.argsort(-np.take_along_axis(scores, top, axis=1), axis=1)
        out[start : start + len(scores)] = np.take_along_axis(top, order, axis=1)
    return out


async def neighbours(args: argparse.Namespace) -> None:
    import numpy as np

    script = planted_script()
    storage = await connect(script, args, "actual")
    from pangloss_core import backend
    from pangloss_testing import planted

    sys.path.insert(0, str(HERE))
    import spaces_graph

    world = planted.world(seed=args.seed, people=args.people, compared=True)
    print(f"# neighbours, {args.backend} ({args.url}): {len(world.people):,} people, {len(world.factoids):,} factoids")  # fmt: skip

    database = backend.current().database()

    @database.read_transaction
    async def counts(tx: typing.Any):
        result = await tx.run(
            "MATCH (s:PGVectorState) WITH s.part AS part, s.generation AS generation "
            "MATCH (v:PGVector {generation: generation}) WHERE v.part = part "
            "RETURN part, v.type AS type, count(*) AS n ORDER BY part, type"
        )
        return [(row["part"], row["type"], row["n"]) async for row in result]

    try:
        by_part: dict[str, dict[str, int]] = collections.defaultdict(dict)
        for part, type_name, n in await counts():
            by_part[part][type_name] = n
        print("vectors by class (structural, actual):")
        for type_name in sorted(by_part["graph"]):
            a, b = by_part["graph"][type_name], by_part[NAME].get(type_name, 0)
            print(f"  {type_name:<18}{a:>9,}{b:>9,}" + (f"   ({1 - b / a:.1%} have none)" if b != a else ""))  # fmt: skip
    except Exception as error:  # (the count is a help, not the measurement)
        print(f"  (the count by class was not read: {error})")

    vectors: dict[str, dict[str, typing.Any]] = {}
    for part in ("graph", NAME):
        vectors[part] = {}
        for type_name in ("Person", "Group"):
            found = await script.part_vectors(part, type_name)
            vectors[part].update({i: np.asarray(v) for i, v in found.items()})
        vectors[part] = spaces_graph.unit(vectors[part])

    print("\nHow alike two entities are (mean cosine): structural, actual")
    for case, both in spaces_graph.entity_pairs(world).items():
        cells = []
        for part in ("graph", NAME):
            scores = [float(vectors[part][a] @ vectors[part][b]) for a, b in both if a in vectors[part] and b in vectors[part]]  # fmt: skip
            cells.append(sum(scores) / len(scores) if scores else float("nan"))
        print(f"  {case:<34}{len(both):>7}{cells[0]:>9.3f}{cells[1]:>9.3f}")

    people = [p.id for p in world.people if p.id in vectors["graph"]]
    none = [i for i in people if i not in vectors[NAME]]
    zero = np.zeros(len(next(iter(vectors["graph"].values()))))
    tens = {
        part: nearest_ten(np.stack([vectors[part].get(i, zero) for i in people]))
        for part in ("graph", NAME)
    }
    same = np.array([len(set(a) & set(b)) for a, b in zip(tens["graph"], tens[NAME], strict=True)])  # fmt: skip
    touched = named_unasserted(world)
    is_touched = np.array([i in touched for i in people])
    print(f"\nThe ten nearest people of a person, structural against actual ({len(people):,} people; {len(none):,} have no vector in the actual network)")  # fmt: skip
    for label, mask in (
        ("everyone", np.ones(len(people), dtype=bool)),
        ("named by a statement in a space", is_touched),
        ("named by none", ~is_touched),
    ):
        part = same[mask]
        print(
            f"  {label:<34}{int(mask.sum()):>7,}  shared {part.mean() / 10:.3f}; all ten the same {np.mean(part == 10):.3f}; "
            f"five or fewer the same {np.mean(part <= 5):.3f}; the nearest one the same "
            f"{np.mean(tens['graph'][mask][:, 0] == tens[NAME][mask][:, 0]):.3f}"
        )
    await storage.setup.disconnect()


# ---------------------------------------------------------------------------
# The weights, with no database
# ---------------------------------------------------------------------------

TABLES = {
    "first guess (0.8, 0.6, 0.4; none 0.5)": {"expected": 0.8, "likely": 0.6, "possible": 0.4, "unlikely": 0.2, "impossible": 0.0, None: 0.5},
    "in full (1 wherever it leans for)": {"expected": 1.0, "likely": 1.0, "possible": 1.0, "unlikely": 1.0, "impossible": 0.0, None: 1.0},
    "halved (0.4, 0.3, 0.2; none 0.25)": {"expected": 0.4, "likely": 0.3, "possible": 0.2, "unlikely": 0.1, "impossible": 0.0, None: 0.25},
    "steep (0.9, 0.5, 0.1; none 0.3)": {"expected": 0.9, "likely": 0.5, "possible": 0.1, "unlikely": 0.05, "impossible": 0.0, None: 0.3},
}  # fmt: skip


def weights(args: argparse.Namespace) -> None:
    import numpy as np
    from pangloss_fastrp.maths import rebuild as embed
    from pangloss_testing import planted

    sys.path.insert(0, str(HERE))
    import spaces_graph

    maps, known = spaces_graph.declared()
    ways = [("through", None), *[("by-walk", name) for name in TABLES], ("asserted", None)]  # fmt: skip
    alike: dict[tuple[str, int], list[float]] = collections.defaultdict(list)
    shared: dict[tuple[int, str], list[float]] = collections.defaultdict(list)
    counts: dict[str, int] = collections.Counter()
    for seed in args.seeds:
        world = planted.world(seed=seed, people=args.people, compared=True)
        pairs = spaces_graph.entity_pairs(world)
        people = [person.id for person in world.people]
        tens = []
        for n, (way, table) in enumerate(ways):
            if table is not None:
                spaces_graph.DEGREE_WEIGHT = TABLES[table]
            graph, way_maps = spaces_graph.graph_of(world, maps, known, way)
            vectors = spaces_graph.unit(embed(graph, way_maps))
            for case, both in pairs.items():
                scores = [float(vectors[a] @ vectors[b]) for a, b in both if a in vectors and b in vectors]  # fmt: skip
                alike[case, n].append(sum(scores) / len(scores) if scores else float("nan"))  # fmt: skip
                if n == 0:
                    counts[case] += len(both)
            tens.append(nearest_ten(np.stack([vectors.get(i, np.zeros(way_maps.dimension)) for i in people])))  # fmt: skip
        for n in range(len(ways)):
            for other, name in ((0, "through"), (len(ways) - 1, "asserted")):
                same = [len(set(a) & set(b)) for a, b in zip(tens[n], tens[other], strict=True)]  # fmt: skip
                shared[n, name].append(sum(same) / (10 * len(same)))
        print(f"seed {seed}: {len(world.people)} people, {len(world.factoids)} factoids", flush=True)  # fmt: skip
    print("\nThe ways: " + "; ".join(f"[{n}] {way if table is None else table}" for n, (way, table) in enumerate(ways)))  # fmt: skip
    head = "".join(f"{f'[{n}]':>9}" for n in range(len(ways)))
    print(f"\nHow alike two entities are (mean cosine)\n{'':44}{head}")
    for case in counts:
        print(f"{case:<36}{counts[case]:>7} " + "".join(f"{np.nanmean(alike[case, n]):>9.3f}" for n in range(len(ways))))  # fmt: skip
    for name in ("through", "asserted"):
        print(f"\nThe ten nearest people of a person that are also those of `{name}` (share)\n{'':44}" + "".join(f"{np.mean(shared[n, name]):>9.3f}" for n in range(len(ways))))  # fmt: skip


def main() -> None:
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("rebuild", "refresh", "neighbours"):
        c = commands.add_parser(name)
        c.add_argument("backend", choices=["memgraph", "neo4j"])
        c.add_argument("url")
        if name != "neighbours":
            c.add_argument("phase", choices=["structural", "actual"])
        c.add_argument("--people", type=int, default=32_000)
        c.add_argument("--seed", type=int, default=1)
        c.add_argument("--sample", type=int, default=40)
    w = commands.add_parser("weights")
    w.add_argument("--people", type=int, default=1500)
    w.add_argument("--seeds", type=int, nargs="+", default=[1, 2, 3])
    args = parser.parse_args()
    if args.command == "weights":
        weights(args)
        return
    asyncio.run({"rebuild": rebuild, "refresh": refresh, "neighbours": neighbours}[args.command](args))  # fmt: skip


if __name__ == "__main__":
    main()
