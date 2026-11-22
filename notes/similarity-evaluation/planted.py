"""The planted world (`pangloss_testing.planted`) at size, in a scratch database: step 8.1 of
implementation_docs/similarity-build-plan.md. The models are `pangloss_testing.similar_models`.

    uv run python notes/similarity-evaluation/planted.py write DIR [--people 32000] [--seed 1]
        DIR/planted.jsonl (JSON Lines for a bulk load: the entities, then the factoids) and DIR/truth.json
    uv run python notes/similarity-evaluation/planted.py load DIR memgraph bolt://localhost:7706
        the file loaded as `pangloss memgraph bulk-load` (or `neo4j bulk-load`) loads it, into an EMPTY database
        (`planted.py empty memgraph URL` deletes everything in one, the vectors' indexes too)
    uv run python notes/similarity-evaluation/planted.py rebuild memgraph bolt://localhost:7706
        the indexes of the vectors made, and every part rebuilt (`pangloss vectors rebuild`)
    uv run python notes/similarity-evaluation/planted.py base DIR memgraph bolt://localhost:7706 [--weights graph=1,class=0.1]
        the figure every later part is compared with: for each mention, where the person it is stands among the
        people nearest it (the other mentions left out), by the stored vectors of the parts and the weights

    uv run python notes/similarity-evaluation/planted.py names DIR memgraph bolt://localhost:7706 --profiles '{"who": {"name": 1, "graph": 0.25}}'
        step 8.6: a search by a name at size, and what a new person costs (it writes people)

    uv run python notes/similarity-evaluation/planted.py time DIR memgraph bolt://localhost:7702 --dated
        step 9.2: an event's other reports among a factoid's nearest, by the stored graph and class vectors with
        the time vectors made here from the truth (`pangloss_dates_vectors.maths`), at several widths, dimensions
        and weights

`--dated` (every command): the world with dates (`planted.world(dated=True)`), the models with `Statement.when`.

**A scratch database only**, never :7687 (the tests) or :7688 (the demo):

    docker run -d --name pangloss-memgraph-planted -p 7706:7687 -e MEMGRAPH_USER=test -e MEMGRAPH_PASSWORD=test \
        memgraph/memgraph-mage:3.14.0 --storage-properties-on-edges=true
    docker run -d --name pangloss-neo4j-planted -p 7707:7687 -e NEO4J_AUTH=neo4j/test-password \
        -e NEO4J_server_memory_heap_max__size=4g -e NEO4J_server_memory_pagecache_size=1g neo4j:2026.10.1
"""

import argparse
import asyncio
import json
import sys
import time
import typing
from pathlib import Path

AUTH = {"memgraph": ("test", "test"), "neo4j": ("neo4j", "test-password")}
USER = "planted"
DATED = False
BASE_APPS = ["pangloss_derived", "pangloss_library", "pangloss_criteria"]
VECTOR_APPS = ["pangloss_vectors", "pangloss_fastrp", "pangloss_names"]


def settings(backend: str, url: str, apps: list[str], extras: dict | None = None):
    import pydantic
    from pangloss_core import BaseSettings
    from pydantic import AnyHttpUrl

    if url.endswith((":7687", ":7688")):
        sys.exit("Not the tests' database nor the demo's: a scratch one")
    if backend == "memgraph":
        from pangloss_memgraph import MemgraphDatabaseSettings as Database

        name = "memgraph"
    else:
        from pangloss_neo4j import Neo4jDatabaseSettings as Database

        name = "neo4j"
    user, password = AUTH[backend]
    Settings = pydantic.create_model(
        "Settings",
        __base__=BaseSettings[Database],
        PROJECT_NAME=(str, "Planted"),
        BACKEND_CORS_ORIGINS=(list[typing.Any], []),
        INSTALLED_APPS=(list[str], apps),
        STORAGE=(str | None, f"pangloss_{backend}:storage"),
        DATABASE=(Database, Database(DB_URL=url, DB_USERNAME=user, DB_PASSWORD=password, DATABASE_NAME=name)),
        INTERFACE_LANGUAGES=(list[str], []),
        DEFAULT_INTERFACE_LANGUAGE=(str, "en"),
        AUTHJWT_SECRET_KEY=(str, "a secret for scratch work, of a decent length"),
        ENTITY_BASE_URL=(AnyHttpUrl, AnyHttpUrl("http://planted.test/")),
        # (a load and a rebuild at size have many writes past the usual half second: not said each time)
        SLOW_QUERY_MS=(int, 60_000),
        **{key: (type(value), value) for key, value in (extras or {}).items()},
    )
    return Settings()


def installed(names: list[str]) -> list[str]:
    """Those of the apps that are there to import (a later phase's package is no error before it exists)"""
    import importlib.util

    return [name for name in names if importlib.util.find_spec(name) is not None]


async def connected(backend: str, url: str, apps: list[str], extras: dict | None = None):
    """The settings made, the models declared, the database connected and its structure made: the storage"""
    import neo4j
    import pangloss_core.settings as core_settings
    from pangloss_core import storage_of

    if DATED:
        apps = [*apps, "pangloss_dates"]
    core_settings.configure(settings(backend, url, apps, extras))
    storage = storage_of()
    storage.setup.create_database(core_settings.SETTINGS)
    await storage.setup.connect()
    from pangloss_testing.similar_models import declare

    declare(dated=DATED)
    await storage.setup.setup_database()
    with neo4j.GraphDatabase.driver(url, auth=AUTH[backend]) as driver:
        driver.execute_query("MERGE (:PGUser {username: $name})", name=USER)
    from pangloss_users import current_request_username

    current_request_username.set(USER)
    return storage


def empty(args) -> None:
    """Everything in the scratch database deleted, its vector indexes too"""
    import neo4j

    if args.url.endswith((":7687", ":7688")):
        sys.exit("Not the tests' database nor the demo's: a scratch one")
    with neo4j.GraphDatabase.driver(args.url, auth=AUTH[args.backend]) as driver, driver.session() as session:
        if args.backend == "memgraph":
            for row in session.run("SHOW VECTOR INDEX INFO").data():
                session.run(f"DROP VECTOR INDEX {row['index_name']}").consume()
        else:
            for row in session.run("SHOW INDEXES YIELD name, type WHERE type = 'VECTOR' RETURN name").data():
                session.run(f"DROP INDEX {row['name']} IF EXISTS").consume()
        while session.run("MATCH (n) WITH n LIMIT 50000 DETACH DELETE n RETURN count(*) AS n").single()["n"]:
            pass
        if args.backend == "memgraph":
            session.run("FREE MEMORY").consume()
    print("emptied")


def write(args) -> None:
    from pangloss_testing import planted

    began = time.perf_counter()
    world = planted.world(seed=args.seed, people=args.people, dated=DATED)
    out = Path(args.dir)
    out.mkdir(parents=True, exist_ok=True)
    records = world.records()
    with open(out / "planted.jsonl", "w", encoding="utf-8") as file:
        for record in records:
            file.write(json.dumps(record, ensure_ascii=False) + "\n")
    (out / "truth.json").write_text(json.dumps(world.truth(), ensure_ascii=False), encoding="utf-8")
    kinds: dict[str, int] = {}
    for mention in world.mentions:
        kinds[mention.kind] = kinds.get(mention.kind, 0) + 1
    print(f"seed {args.seed}: {len(world.people):,} people, {len(world.mentions):,} mentions "
          f"({', '.join(f'{k} {n:,}' for k, n in sorted(kinds.items()))}), {len(world.groups):,} groups, "
          f"{len(world.places):,} places, {len(world.factoids):,} factoids; {len(records):,} records; "
          f"{len(world.namesakes):,} names that more than one person has "
          f"({sum(len(v) for v in world.namesakes.values()):,} people); {time.perf_counter() - began:.1f} s")
    if DATED:
        print(f"dated: {len(world.events):,} events with more than one report, {len(world.series):,} things that "
              f"happened year after year ({sum(len(v) for v in world.series.values()):,} of those events)")


async def load(args) -> None:
    from pangloss_core import backend as core_backend
    from pangloss_models.bulk_upload import read_records, upload, validate

    storage = await connected(args.backend, args.url, BASE_APPS)
    file = Path(args.dir) / "planted.jsonl"
    counts = validate(read_records(file))
    total = sum(counts.values())
    print(f"{total:,} records: " + ", ".join(f"{n:,} {name}" for name, n in counts.items()))
    if args.backend == "memgraph":
        from pangloss_memgraph.databases.memgraph.bulk import bulk_ingest
    else:
        from pangloss_neo4j.databases.neo4j.bulk import bulk_ingest
    began = time.perf_counter()

    def progress(done: int) -> None:
        if done % 20_000 == 0:
            print(f"  {done:,} of {total:,}, {time.perf_counter() - began:.0f} s", flush=True)

    async with bulk_ingest(who=USER):
        await upload(read_records(file), concurrency=args.concurrency, progress=progress)
    seconds = time.perf_counter() - began
    print(f"wrote {total:,} records in {seconds:.0f} s ({total / seconds:.0f} a second), switches and constraints "
          "included")
    database = core_backend.current().database()

    @database.read_transaction
    async def count(tx):
        nodes = await (await tx.run("MATCH (n) RETURN count(n) AS n")).single()
        edges = await (await tx.run("MATCH ()-[r]->() RETURN count(r) AS n")).single()
        return nodes["n"], edges["n"]

    nodes, edges = await count()
    print(f"in the database: {nodes:,} nodes, {edges:,} edges")
    await storage.setup.disconnect()


async def make_indexes() -> list[str]:
    """What the migrations of `pangloss_vectors` and of a project would make: the plain indexes of the vectors' nodes,
    and the vector index of each profile"""
    from pangloss_core import backend as core_backend
    from pangloss_cypher.migrations import apply_changes
    from pangloss_models.migrations import changes as c
    from pangloss_models.migrations.files import EMPTY_SNAPSHOT
    from pangloss_vectors import meta, store, structure
    from pangloss_vectors.parts import profiles

    entries = list(structure.INDEXES)
    for name, weights in profiles().items():
        if not weights:
            continue
        lay = store.layout(name, weights)
        entries.append(structure.vector_entry(lay.index_name, lay.label, lay.dimension, "planted"))
        for group in meta.groups():
            entries.append(
                structure.vector_entry(lay.group_index_name(group), lay.group_label(group), lay.dimension, "planted")
            )
    await apply_changes(
        core_backend.current().database(),
        EMPTY_SNAPSHOT,
        [c.AddIndex(index={k: v for k, v in e.items() if k != "app"}) for e in entries],
    )
    return [str(e.get("name") or f"{e['label']}({e['properties'][0]})") for e in entries]


def extras_of(args) -> dict:
    found = {}
    if getattr(args, "profiles", None):
        found["VECTORS_PROFILES"] = json.loads(args.profiles)
    if getattr(args, "variants", None):
        found["NAMES_VARIANTS"] = args.variants
    return found


async def rebuild(args) -> None:
    storage = await connected(args.backend, args.url, BASE_APPS + installed(VECTOR_APPS), extras_of(args))
    from pangloss_vectors import rebuild as rebuild_module

    began = time.perf_counter()
    print("indexes:", ", ".join(await make_indexes()), f"({time.perf_counter() - began:.1f} s)")
    began = time.perf_counter()
    done = await rebuild_module.rebuild(args.part)
    print(f"rebuild: {time.perf_counter() - began:.1f} s in all")
    for p in done.parts:
        print(f"  part {p.part}: generation {p.generation}, {p.count:,} vectors, {p.seconds:.1f} s")
    for p in done.profiles:
        print(f"  profile {p.profile}: generation {p.generation}, {p.count:,} vectors, {p.seconds:.1f} s")
    await storage.setup.disconnect()


async def part_vectors(part: str, type_name: str = "Person") -> dict[str, list[float]]:
    """The vectors in use of a part, of the items of one class, by id (read in pages)"""
    from pangloss_core import backend as core_backend
    from pangloss_vectors import store

    state = (await store.states()).parts.get(part)
    if state is None:
        sys.exit(f"The part {part!r} has no vectors: rebuild first")
    database = core_backend.current().database()
    found: dict[str, list[float]] = {}
    after = ""
    while True:

        @database.read_transaction
        async def page(tx, after=after):
            result = await tx.run(
                "MATCH (v:PGVector) WHERE v.of > $after AND v.part = $part AND v.generation = $generation "
                "AND v.type = $type RETURN v.of AS of, v.vector AS vector ORDER BY v.of LIMIT 5000",
                after=after, part=part, generation=state.generation, type=type_name,
            )
            return [(row["of"], row["vector"]) async for row in result]

        rows = await page()
        if not rows:
            return found
        found.update(rows)
        after = rows[-1][0]


def ranks(truth: dict, vectors: dict[str, dict[str, list[float]]], weights: dict[str, float]):
    """For each mention, the place of the person it is among the people (not the mentions), nearest first, by
    `Σ w·cos / Σ w` over the parts (what a profile's combined vector gives): 1 is right first, those as near as
    the person counted before them. With its kind"""
    import numpy as np

    people = [p["id"] for p in truth["people"]]
    mentions = [m for m in truth["mentions"]]
    row = {id: n for n, id in enumerate(people)}
    total = np.zeros((len(mentions), len(people)), dtype=np.float32)
    for part, weight in weights.items():
        have = vectors[part]
        dimension = len(next(iter(have.values())))

        def unit(ids):
            made = np.array([have.get(i) or [0.0] * dimension for i in ids], dtype=np.float32)
            lengths = np.linalg.norm(made, axis=1, keepdims=True)
            return made / np.where(lengths == 0, 1, lengths)

        total += weight * (unit([m["id"] for m in mentions]) @ unit(people).T)
    found = []
    for n, mention in enumerate(mentions):
        scores = total[n]
        right = scores[row[mention["person"]]]
        # (everyone as near as the right person is counted before them: namesakes have the same name vector, and
        # the worst case is what a reader of a list would meet)
        found.append((int((scores >= right - 1e-6).sum()), mention["kind"]))
    return found


def said(found) -> str:
    def line(places) -> str:
        count = len(places)
        first = sum(1 for p in places if p == 1)
        five = sum(1 for p in places if p <= 5)
        ten = sum(1 for p in places if p <= 10)
        return (f"{count:,} mentions: right first {100 * first / count:.1f}%, in the first five "
                f"{100 * five / count:.1f}%, in the first ten {100 * ten / count:.1f}%")

    lines = ["  all: " + line([p for p, _ in found])]
    for kind in sorted({k for _, k in found}):
        lines.append(f"  {kind}: " + line([p for p, k in found if k == kind]))
    return "\n".join(lines)


async def base(args) -> None:
    storage = await connected(args.backend, args.url, BASE_APPS + installed(VECTOR_APPS), extras_of(args))
    truth = json.loads((Path(args.dir) / "truth.json").read_text(encoding="utf-8"))
    from pangloss_vectors import nearest

    wanted = [
        {name: float(weight) for name, weight in (pair.split("=") for pair in one.split(","))}
        for one in args.weights
    ]
    began = time.perf_counter()
    vectors = {part: await part_vectors(part) for part in sorted({p for w in wanted for p in w})}
    print(f"read the vectors of {', '.join(f'{p} ({len(v):,})' for p, v in vectors.items())} of Person in "
          f"{time.perf_counter() - began:.1f} s")
    for weights in wanted:
        print("weights", ", ".join(f"{k} {v:g}" for k, v in weights.items()))
        print(said(ranks(truth, vectors, weights)))
    # (what a search costs: the exact scan of a class no group covers, step 7a.4)
    times = []
    for mention in truth["mentions"][:: max(1, len(truth["mentions"]) // 20)][:20]:
        began = time.perf_counter()
        got = await nearest(mention["id"], types=["Person"], k=10)
        times.append(time.perf_counter() - began)
        assert got.status == "ok", got
    times.sort()
    print(f"nearest(types=['Person'], k=10), {len(times)} mentions: median {times[len(times) // 2] * 1000:.0f} ms, "
          f"slowest {times[-1] * 1000:.0f} ms")
    await storage.setup.disconnect()


async def by_name(args) -> None:
    """Step 8.6: a search by a name at size (`pangloss_names.search`, from each of a sample of mentions' labels):
    where the person is among the people found, through the profile's index and narrowed to `Person` (an exact scan
    here, as `Person` is no group), against the exact ranking by the stored name vectors; and what a new person
    costs: the write, and the worker's turn after it"""
    storage = await connected(args.backend, args.url, BASE_APPS + installed(VECTOR_APPS), extras_of(args))
    truth = json.loads((Path(args.dir) / "truth.json").read_text(encoding="utf-8"))
    import statistics

    import pangloss_names
    from pangloss_models import ModelRegistry
    from pangloss_vectors.worker import run_pending

    mention_ids = {m["id"] for m in truth["mentions"]}
    sample = truth["mentions"][:: max(1, len(truth["mentions"]) // args.sample)][: args.sample]
    name_vectors = await part_vectors("name")
    exact = dict(zip([m["id"] for m in truth["mentions"]], ranks(truth, {"name": name_vectors}, {"name": 1.0})))
    for label, types in (("through the profile's index", None), ("narrowed to Person (an exact scan)", ["Person"])):
        times, places = [], []
        for mention in sample:
            began = time.perf_counter()
            got = await pangloss_names.search(mention["label"], types=types, k=args.k)
            times.append(time.perf_counter() - began)
            assert got.status == "ok", got
            people = [hit.id for hit in got.hits if hit.id not in mention_ids]
            places.append(people.index(mention["person"]) + 1 if mention["person"] in people else None)
        times.sort()
        found = [p for p in places if p is not None]
        print(f"search by a name, k={args.k}, {label}: {len(sample)} mentions' labels; the person among the people "
              f"found {100 * len(found) / len(sample):.1f}%, among the first five of them "
              f"{100 * sum(1 for p in found if p <= 5) / len(sample):.1f}%; median {times[len(times) // 2] * 1000:.0f} ms, "
              f"slowest {times[-1] * 1000:.0f} ms")
    wanted = [exact[m["id"]][0] for m in sample]
    print(f"  by the stored name vectors exactly, namesakes counted before the person: among the first five "
          f"{100 * sum(1 for p in wanted if p <= 5) / len(sample):.1f}%, among the first {args.k} "
          f"{100 * sum(1 for p in wanted if p <= args.k) / len(sample):.1f}%")
    Person = ModelRegistry.all_models()["Person"]
    await run_pending()
    writes, turns = [], []
    for n in range(args.writes):
        began = time.perf_counter()
        await Person.Create(label=f"Balthasar Quittenbaum {n}").save()
        writes.append(time.perf_counter() - began)
        began = time.perf_counter()
        await run_pending()
        turns.append(time.perf_counter() - began)
    print(f"a new person, {args.writes} times: the write {statistics.median(writes) * 1000:.0f} ms at the median, "
          f"the worker's turn after it {statistics.median(turns) * 1000:.0f} ms (slowest {max(turns) * 1000:.0f} ms)")
    got = await pangloss_names.search("Baltasar Quittenbaum", types=["Person"], k=3)
    print("  found after it:", [round(hit.score, 3) for hit in got.hits])
    await storage.setup.disconnect()


async def by_time(args) -> None:
    """Step 9.2: of a factoid that reports an event, the share of the event's other reports among its nearest
    factoids, by `Σ w·cos / Σ w` over the stored graph and class vectors and the time vectors made here"""
    sys.path.insert(0, "packages/pangloss-dates-vectors/tests")
    import numpy as np
    import time_planted_support as support
    from pangloss_dates_vectors import maths
    from pangloss_testing import planted

    storage = await connected(args.backend, args.url, BASE_APPS + installed(VECTOR_APPS), extras_of(args))
    world = planted.world(seed=args.seed, people=args.people, dated=True)
    from pangloss_core import backend as core_backend

    database = core_backend.current().database()

    @database.read_transaction
    async def ids(tx):
        result = await tx.run("MATCH (f:Factoid) RETURN f.label AS label, f.id AS id")
        return {row["label"]: row["id"] async for row in result}

    id_of = await ids()
    labels = [f["label"] for f in world.factoids]
    assert set(labels) <= set(id_of), "the database does not hold this world: load it with the same seed and people"

    def unit(have):
        dimension = len(next(iter(have.values())))
        made = np.array([have.get(id_of[label]) or [0.0] * dimension for label in labels], dtype=np.float32)
        lengths = np.linalg.norm(made, axis=1, keepdims=True)
        return made / np.where(lengths == 0, 1, lengths)

    stored = {part: unit(await part_vectors(part, "Factoid")) for part in ("graph", "class")}
    series = set(support.series_of(world))
    once = set(support.other_reports(world)) - series
    print(f"{len(labels):,} factoids; {len(once):,} reports of an event told twice, {len(series):,} of something "
          "that happened year after year; the share of an event's other reports among a report's nearest")

    def line(name, parts):
        def scores(rows):
            return sum(weight * (vectors[rows] @ vectors.T) for vectors, weight in parts)

        cells = []
        for only in (once, series):
            cells.append(" ".join(
                f"{100 * support.found_among(world, labels, scores, most, only):5.1f}%" for most in (1, 3, 10)
            ))
        print(f"  {name:<46} told twice (first, in 3, in 10) {cells[0]} | year after year {cells[1]}")

    graph, classes = stored["graph"], stored["class"]
    line("graph", [(graph, 1)])
    line("graph + class 0.1", [(graph, 1), (classes, 0.1)])
    for width, dimension in ((1, 256), (1, 128), (2, 512), (2, 128), (2, 64), (2, 32), (3, 128), (5, 64)):
        ring = maths.Ring(dimension, width)
        times = support.time_vectors(world, labels, ring).astype(np.float32)
        print(f" width {width}, {dimension} places (round in {ring.years:g} years)")
        line("time alone", [(times, 1)])
        for weight in (0.25, 0.5, 1):
            line(f"graph + class 0.1 + time {weight:g}", [(graph, 1), (classes, 0.1), (times, weight)])
    await storage.setup.disconnect()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    commands = parser.add_subparsers(dest="command", required=True)
    w = commands.add_parser("write")
    w.add_argument("dir")
    w.add_argument("--people", type=int, default=32_000)
    w.add_argument("--seed", type=int, default=1)
    w.add_argument("--dated", action="store_true")
    for name in ("empty", "load", "rebuild", "base", "names", "time"):
        c = commands.add_parser(name)
        c.add_argument("--dated", action="store_true")
        if name == "time":
            c.add_argument("--people", type=int, default=32_000)
            c.add_argument("--seed", type=int, default=1)
        if name in ("load", "base", "names"):
            c.add_argument("dir")
        c.add_argument("backend", choices=["memgraph", "neo4j"])
        c.add_argument("url")
        c.add_argument("--profiles", help="VECTORS_PROFILES, as JSON")
        c.add_argument("--variants", help="NAMES_VARIANTS: a file")
        if name == "load":
            c.add_argument("--concurrency", type=int, default=8)
        if name == "rebuild":
            c.add_argument("--part")
        if name == "base":
            c.add_argument("--weights", action="append", default=None)
        if name == "names":
            c.add_argument("--sample", type=int, default=300)
            c.add_argument("--writes", type=int, default=20)
            c.add_argument("-k", type=int, default=20)
    args = parser.parse_args()
    global DATED
    DATED = args.dated or args.command == "time"
    if args.command == "write":
        write(args)
        return
    if args.command == "empty":
        empty(args)
        return
    if args.command == "base" and not args.weights:
        args.weights = ["graph=1,class=0.1", "graph=1"]
    commands_by_name = {"load": load, "rebuild": rebuild, "base": base, "names": by_name, "time": by_time}
    asyncio.run(commands_by_name[args.command](args))


main()
