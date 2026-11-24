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

    uv run python notes/similarity-evaluation/planted.py reports memgraph bolt://localhost:7706 --profiles '{"when": {"graph": 1, "class": 0.1, "time": 0.5}}'
        step 9.3 at size: an event's other report through the stored profile, and what a new dated factoid costs
        (it writes factoids). After `rebuild ... --dated --profiles` of the same

    uv run python notes/similarity-evaluation/planted.py reconcile memgraph bolt://localhost:7702 --dated --people 6000 --profiles '{"who": {"name": 1, "graph": 0.25}}'
        step 10.3: the candidates of the service (`pangloss_reconcile`) for a sample of mentions, each posed again
        as a payload with a stand-in, not written; right first and among five by several weights, "someone new".
        After `rebuild ... --stand-in --profiles` of the same (the models then have `Mention`)

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
import uuid
import sys
import time
import typing
from pathlib import Path

AUTH = {"memgraph": ("test", "test"), "neo4j": ("neo4j", "test-password")}
USER = "planted"
DATED = False
STAND_IN = False
# (`rebuild --worker-models` and `worker`: the models the worker of step 10.5g is measured on, `worker_models`)
TOOLCHAIN = False
BASE_APPS = ["pangloss_derived", "pangloss_library", "pangloss_criteria"]
VECTOR_APPS = ["pangloss_vectors", "pangloss_fastrp", "pangloss_names", "pangloss_dates_vectors"]
# (step 10.5g: review, so that a factoid written is unpublished and the worker takes it, and reconciliation)
WORKER_APPS = [*BASE_APPS, "pangloss_review", *VECTOR_APPS, "pangloss_reconcile"]


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
        # (a value may be given with its type, `(type, value)`: one that may be None)
        **{
            key: value if isinstance(value, tuple) else (type(value), value)
            for key, value in (extras or {}).items()
        },
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
        apps = ["pangloss_dates", *apps]
    else:
        apps = [app for app in apps if app != "pangloss_dates_vectors"]
    core_settings.configure(settings(backend, url, apps, extras))
    storage = storage_of()
    storage.setup.create_database(core_settings.SETTINGS)
    await storage.setup.connect()
    from pangloss_testing.similar_models import declare, mention_stand_in

    if STAND_IN:
        from pangloss_models import hooks

        hooks.stand_ins.append(mention_stand_in())
    declare(dated=DATED, stand_in=STAND_IN, reviewed=TOOLCHAIN, suggested=TOOLCHAIN)
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


async def recover(args) -> None:
    """A Memgraph bulk load that stopped at its end (at size, the text indexes made again can fail with "Cannot get
    unique access to the storage" while a snapshot is being written): `pangloss memgraph bulk-recover`"""
    storage = await connected(args.backend, args.url, BASE_APPS)
    from pangloss_memgraph.databases.memgraph.bulk import restore

    await restore()
    print("recovered")
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
    if args.worker_models:
        storage = await connected(args.backend, args.url, installed(WORKER_APPS), worker_extras(args))
    else:
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


async def reports(args) -> None:
    """Step 9.3 at size: through the stored profile (`--profiles '{"when": {"graph": 1, "class": 0.1, "time": 0.5}}'`),
    for a sample of the reports of an event, where the event's other report is among the factoids `nearest` finds
    (through the profile's index, and narrowed to `Factoid`, an exact scan); and what a new dated factoid costs"""
    import statistics

    from pangloss_models import ModelRegistry
    from pangloss_testing import planted
    from pangloss_vectors import nearest
    from pangloss_vectors.worker import run_pending

    sys.path.insert(0, "packages/pangloss-dates-vectors/tests")
    import time_planted_support as support

    storage = await connected(args.backend, args.url, BASE_APPS + installed(VECTOR_APPS), extras_of(args))
    world = planted.world(seed=args.seed, people=args.people, dated=True)
    from pangloss_core import backend as core_backend

    database = core_backend.current().database()

    @database.read_transaction
    async def ids(tx):
        result = await tx.run("MATCH (f:Factoid) RETURN f.label AS label, f.id AS id")
        return {row["label"]: row["id"] async for row in result}

    id_of = await ids()
    others = support.other_reports(world)
    series = set(support.series_of(world))
    for name, labels in (("told twice", sorted(set(others) - series)), ("year after year", sorted(series))):
        sample = labels[:: max(1, len(labels) // args.sample)][: args.sample]
        for how, types, k in (("through the profile's index", None, 40), ("narrowed to Factoid (an exact scan)", ["Factoid"], 10)):
            places, times = [], []
            for label in sample:
                began = time.perf_counter()
                got = await nearest(id_of[label], profile=args.profile, types=types, k=k)
                times.append(time.perf_counter() - began)
                assert got.status == "ok", got
                found = [hit.id for hit in got.hits if hit.type == "Factoid"]
                [other] = others[label]
                places.append(found.index(id_of[other]) + 1 if id_of[other] in found else None)
            times.sort()
            share = lambda most: 100 * sum(1 for p in places if p is not None and p <= most) / len(places)  # noqa: E731
            print(f"{name}, {len(sample)} reports, {how}, k={k}: the other report first {share(1):.1f}%, in 3 "
                  f"{share(3):.1f}%, in 10 {share(10):.1f}%; median {times[len(times) // 2] * 1000:.0f} ms, slowest "
                  f"{times[-1] * 1000:.0f} ms")
    Factoid = ModelRegistry.all_models()["Factoid"]
    payload = next(f for f in world.factoids if f["label"].startswith("A gathering"))
    await run_pending()
    writes, turns = [], []
    for n in range(args.writes):
        began = time.perf_counter()
        await Factoid.Create(**{**payload, "label": f"A gathering told again {n}"}).save()
        writes.append(time.perf_counter() - began)
        began = time.perf_counter()
        await run_pending()
        turns.append(time.perf_counter() - began)
    print(f"a new dated factoid, {args.writes} times: the write {statistics.median(writes) * 1000:.0f} ms at the "
          f"median, the worker's turn after it {statistics.median(turns) * 1000:.0f} ms (slowest "
          f"{max(turns) * 1000:.0f} ms)")
    await storage.setup.disconnect()


def _with_stand_in(value, mention_id: str, label: str):
    """A payload with each reference to the mention's own person replaced by a stand-in of that label"""
    if isinstance(value, dict):
        if value.get("id") == mention_id and value.get("type") == "Person":
            return {"type": "Mention", "label": label, "mentioned_type": "Person"}
        return {key: _with_stand_in(item, mention_id, label) for key, item in value.items()}
    if isinstance(value, list):
        return [_with_stand_in(item, mention_id, label) for item in value]
    return value


async def reconcile(args) -> None:
    """Step 10.3: the service's candidates (`pangloss_reconcile.candidates_of`) for a sample of the mentions. Each
    mention's own factoid is posed again as a payload with a stand-in (`Mention`) in the place of the mention's
    person, planned and not written; the candidates are asked widely, the other mentions' own people left out (as
    `base` leaves them out), and the place of the person it is taken, by several weights of the parts' scores.
    The world in the database has the mention's person and factoid too (the measure of 8.6 has the same)"""
    global STAND_IN
    STAND_IN = True
    extras = {
        **extras_of(args),
        "RECONCILE_PROFILE": args.profile,
        "RECONCILE_FETCH": args.fetch,
        # (the service's own cut and its own weight of what is shared are off: every candidate found is weighed here)
        "RECONCILE_LEAST_SCORE": 0,
        "RECONCILE_WEIGHTS": {"shared": 0},
    }
    storage = await connected(
        args.backend, args.url, BASE_APPS + installed(VECTOR_APPS) + ["pangloss_reconcile"], extras
    )
    import statistics

    from pangloss_cypher.write_functions import to_db_model
    from pangloss_cypher.write_plan import plan_create
    from pangloss_models import ModelRegistry
    from pangloss_reconcile.candidates import candidates_of
    from pangloss_testing import planted

    world = planted.world(seed=args.seed, people=args.people, dated=DATED)
    mention_ids = {m.id for m in world.mentions}
    namesakes = {i for ids in world.namesakes.values() for i in ids}
    Factoid = ModelRegistry.all_models()["Factoid"]
    of_mention = {}
    for factoid in world.factoids:
        text = json.dumps(factoid)
        for m in world.mentions:
            if m.id in text:
                of_mention[m.id] = factoid
    sample = world.mentions[:: max(1, len(world.mentions) // args.sample)][: args.sample]
    from pangloss_reconcile.reasons import shared

    # (a request by stage: each part's `unknown`, each search, the reading of the candidates' vectors)
    import pangloss_vectors.search as search_module
    import pangloss_vectors.store as store_module
    from pangloss_vectors.parts import parts as registered

    stages: dict[str, list[float]] = {}

    def timed(name, function):
        async def run(*a, **k):
            began = time.perf_counter()
            try:
                return await function(*a, **k)
            finally:
                stages.setdefault(name, []).append(time.perf_counter() - began)
        return run

    for part_name, made in registered().items():
        if callable(getattr(made, "unknown", None)):
            object.__setattr__(made, "unknown", timed(f"unknown: {part_name}", made.unknown))
    original_nearest = search_module.nearest

    async def nearest(*a, **k):
        began = time.perf_counter()
        try:
            return await original_nearest(*a, **k)
        finally:
            stages.setdefault("nearest by " + "+".join(k.get("vector") or {}), []).append(time.perf_counter() - began)

    search_module.nearest = nearest
    store_module.read_part = timed("read_part (each part)", store_module.read_part)

    rows, times, reason_times, person_reasons, all_times = [], [], [], [], []

    async def stored_id(label: str) -> str:
        from pangloss_core import backend

        @backend.current().database().read_transaction
        async def read(tx):
            result = await tx.run("MATCH (h:HeadNode {label: $label}) WHERE h:Factoid RETURN h.id AS id", label=label)
            return [str(r["id"]) async for r in result]

        (found_id,) = await read()
        return found_id

    for m in sample:
        payload = _with_stand_in(of_mention[m.id], m.id, m.label)
        payload = {k: v for k, v in payload.items() if k not in ("id", "create_new")}
        plan = plan_create(to_db_model(Factoid.Create(**payload)))
        began = time.perf_counter()
        found = await candidates_of(plan, see_unpublished=True, limit=4 * args.fetch)
        times.append(time.perf_counter() - began)
        assert len(found) == 1 and found[0].status == "ok", found
        rows.append((m, [c for c in found[0].candidates if c.id not in mention_ids]))
        # (the reasons of the ten best, as a request of limit 10 asks them)
        began = time.perf_counter()
        reasons = await shared(plan, [c.id for c in found[0].candidates[:10]], True, 5)
        reason_times.append(time.perf_counter() - began)
        person_reasons.append(len(reasons.get(m.person, [])))
        # (step 11.2: how many of the document's entities each candidate found is named with, all of them asked)
        # (the mention's factoid is stored too, in this measure: it is the document asked about, and is left out as
        # the stored route leaves its own document out; without this the people it names share one another by it)
        object.__setattr__(plan.head, "id", uuid.UUID(await stored_id(of_mention[m.id]["label"])))
        began = time.perf_counter()
        every = await shared(plan, [c.id for c in found[0].candidates], True, 10**6)
        all_times.append((time.perf_counter() - began, len(found[0].candidates)))
        for c in found[0].candidates:
            c.scores["shared"] = (lambda n: n / (n + 2))(len(every.get(c.id, [])))
            # (the shared entities counted in proportion to the name's cosine: `byname` in the weights)
            c.scores["byname"] = c.scores.get("name", 0.0) * c.scores["shared"]
    all_times.sort()
    print(f"the shared entities of every candidate found (step 11.2): {statistics.median(t for t, _ in all_times) * 1000:.0f} ms "
          f"at the median, slowest {all_times[-1][0] * 1000:.0f} ms, for {statistics.median(n for _, n in all_times):.0f} "
          f"candidates at the median; in the weights below `shared` is n / (n + 2)")
    for name, found_times in sorted(stages.items()):
        print(f"  stage {name}: {statistics.median(found_times) * 1000:.0f} ms at the median, "
              f"{len(found_times) / len(sample):.1f} a request")
    times.sort()
    reason_times.sort()
    print(f"the reasons of ten candidates: {statistics.median(reason_times) * 1000:.0f} ms at the median, slowest "
          f"{reason_times[-1] * 1000:.0f} ms; the person shares {statistics.mean(person_reasons):.1f} entities "
          f"at the mean (where among the ten)")
    print(f"{len(sample)} mentions of {len(world.mentions)}, {args.fetch} candidates asked of each part, profile "
          f"{args.profile}: a request {statistics.median(times) * 1000:.0f} ms at the median, slowest "
          f"{times[-1] * 1000:.0f} ms; the person among those found (by any part) "
          f"{100 * sum(1 for m, cs in rows if any(c.id == m.person for c in cs)) / len(rows):.1f}%")
    parts_seen = sorted({name for _, cs in rows for c in cs for name in c.scores})
    print("parts scored:", ", ".join(parts_seen))
    for spec in args.weights:
        weights = {k: float(v) for k, v in (pair.split("=") for pair in spec.split(","))}
        total = sum(weights.values())
        places, shared_places = [], []
        best_known, best_new = [], []
        for m, cs in rows:
            scored = sorted(
                ((sum(w * c.scores.get(k, 0.0) for k, w in weights.items()) / total, c.id) for c in cs),
                key=lambda pair: (-pair[0], pair[1]),
            )
            ids = [i for _, i in scored]
            place = ids.index(m.person) + 1 if m.person in ids else None
            places.append(place)
            if m.person in namesakes:
                shared_places.append(place)
            # ("someone new": the best score with the person there, and with the person taken away)
            if scored:
                best_known.append(scored[0][0])
                without = [value for value, i in scored if i != m.person]
                if without:
                    best_new.append(without[0])
        def share(found, at):
            return 100 * sum(1 for p in found if p is not None and p <= at) / max(1, len(found))
        # (AUC: how often a mention whose person is there has a higher best score than one whose person is not)
        import bisect
        ordered = sorted(best_new)
        wins = sum(bisect.bisect_left(ordered, v) + 0.5 * (bisect.bisect_right(ordered, v) - bisect.bisect_left(ordered, v)) for v in best_known)
        auc = wins / max(1, len(best_known) * len(ordered))
        print(f"  {spec}: right first {share(places, 1):.1f}%, among five {share(places, 5):.1f}%; of the "
              f"{len(shared_places)} whose name several people have: {share(shared_places, 1):.1f}% / "
              f"{share(shared_places, 5):.1f}%; someone new, by the best score: AUC {auc:.2f} (median best "
              f"{statistics.median(best_known):.2f} with the person, {statistics.median(best_new):.2f} without)")
    await storage.setup.disconnect()


async def learn(args) -> None:
    """Step 11.7: learning from decisions, through the package's own code. A sample of the mentions, each posed
    again as a payload with a stand-in (as `reconcile` does) and asked of the service as it is set (the default
    weights and least score, five displayed); of every second one the person is taken out of what was found
    ("someone new"). Half are kept as decisions made with the truth (`decisions.write_example`: the person taken if
    among the rows kept, none otherwise) and learnt from (`fits.learn`); on the other half the fit's "none of these"
    model is asked (`learning.head_features`, `Model.score`) and compared with the truth, and with what the best
    score alone says; and its ranking model with the hand-set order. The examples and fits it writes are removed"""
    global STAND_IN
    STAND_IN = True
    extras = {
        **extras_of(args),
        "RECONCILE_PROFILE": args.profile,
        "RECONCILE_FETCH": args.fetch,
        "RECONCILE_LEARN_FROM": args.learn_from,
    }
    storage = await connected(
        args.backend, args.url, BASE_APPS + installed(VECTOR_APPS) + ["pangloss_reconcile"], extras
    )
    import bisect
    import datetime

    from pangloss_core import backend
    from pangloss_cypher.write_functions import to_db_model
    from pangloss_cypher.write_plan import plan_create
    from pangloss_learn import Model
    from pangloss_models import ModelRegistry
    from pangloss_reconcile import decisions, fits, learning
    from pangloss_reconcile import settings as reconcile_settings
    from pangloss_reconcile.candidates import candidates_of
    from pangloss_testing import planted
    from pangloss_vectors import store

    database = backend.current().database()

    @database.write_transaction
    async def clear(tx):
        for label in ("PGReconcileExample", "PGReconcileShown", "PGReconcileModel"):
            await (await tx.run(f"MATCH (n:{label}) DELETE n")).consume()

    @database.read_transaction
    async def stored_ids(tx):
        result = await tx.run("MATCH (h:HeadNode) WHERE h:Factoid RETURN h.label AS label, h.id AS id")
        return {r["label"]: str(r["id"]) async for r in result}

    await clear()
    import pangloss_reconcile.reasons as reasons_module

    own: dict = {}
    original_shared = reasons_module.shared

    async def shared_but_own(plan, *a, **k):
        was = plan.head.id
        object.__setattr__(plan.head, "id", own["id"])
        try:
            return await original_shared(plan, *a, **k)
        finally:
            object.__setattr__(plan.head, "id", was)

    reasons_module.shared = shared_but_own
    world = planted.world(seed=args.seed, people=args.people, dated=DATED)
    mention_ids = {m.id for m in world.mentions}
    Factoid = ModelRegistry.all_models()["Factoid"]
    of_mention = {}
    for factoid in world.factoids:
        text = json.dumps(factoid)
        for m in world.mentions:
            if m.id in text:
                of_mention[m.id] = factoid
    by_label = await stored_ids()
    sample = world.mentions[:: max(1, len(world.mentions) // args.sample)][: args.sample]
    now = decisions.today(await store.states())
    least = reconcile_settings.least_score()
    weights = reconcile_settings.weights()
    print(f"{len(sample)} mentions of {len(world.mentions)}, profile {args.profile}, weights {weights}, least score "
          f"{least}, {args.shown} displayed; of every second the person is taken out")

    held = []
    kept = 0
    for n, m in enumerate(sample):
        payload = _with_stand_in(of_mention[m.id], m.id, m.label)
        payload = {k: v for k, v in payload.items() if k not in ("id", "create_new")}
        plan = plan_create(to_db_model(Factoid.Create(**payload)))
        # (the mention's own factoid is stored too: it is the document asked about, and is left out of what is
        # shared, as the stored route leaves its own document out; the parts are asked of the plan as it is)
        own["id"] = uuid.UUID(by_label[of_mention[m.id]["label"]])
        found = await candidates_of(plan, see_unpublished=True, limit=args.shown)
        assert len(found) == 1 and found[0].status == "ok", found
        gone = n % 2 == 1
        best = [c for c in found[0].best if c.id not in mention_ids and not (gone and c.id == m.person)]
        shown = {c.id for c in [c for c in best if c.score >= least][: args.shown]}
        rows = [
            {"id": c.id, "type": c.type, "scores": dict(c.scores), "shared": len(c.shared), "score": c.score,
             "displayed": c.id in shown}
            for c in best
        ]
        taken = m.person if any(row["id"] == m.person for row in rows) else None
        if n % 4 < 2:
            record = {**now, "rows": json.dumps(rows)}

            @database.write_transaction
            async def write(tx, record=record, taken=taken, stand_in=m.id):
                await decisions.write_example(tx, stand_in, datetime.datetime.now(datetime.UTC), record, taken)

            await write()
            kept += 1
        else:
            held.append(learning.Decision(m.id, tuple(rows), taken))

    print(f"{kept} decisions kept, {len(held)} held out")
    learnt = await fits.learn()
    for line in learnt.lines():
        print("  " + line)
    fit = await fits.in_use()
    if fit is None:
        written = await fits.fits()
        fit = written[0] if written else None
        print("  (no fit in use: the newest fit written is measured all the same)" if fit else "  (no fit)")
    if fit is not None:
        ranking_features = learning.ranking_features(weights)
        if fit["none"]:
            model = Model.from_json(fit["none"])
            scored = []
            for decision in held:
                features = learning.head_features(decision.rows)
                if features is not None:
                    scored.append((model.score(features), features["best"], learning.none_taken(decision)))
            yes = [s for s in scored if s[2]]
            no = [s for s in scored if not s[2]]

            def auc(column, sign):
                ordered = sorted(sign * s[column] for s in no)
                wins = sum(
                    bisect.bisect_left(ordered, sign * s[column])
                    + 0.5 * (bisect.bisect_right(ordered, sign * s[column]) - bisect.bisect_left(ordered, sign * s[column]))
                    for s in yes
                )
                return wins / max(1, len(yes) * len(no))

            right = sum(1 for s in scored if (s[0] >= 0.5) == s[2])
            commoner = max(len(yes), len(no))
            print(f'  "none of these", on {len(scored)} lists held out ({len(yes)} of them with none of those displayed '
                  f"the one; {len(held) - len(scored)} with nothing displayed): the model AUC {auc(0, 1):.2f}, the best "
                  f"score alone AUC {auc(1, -1):.2f}; called rightly at a half {100 * right / max(1, len(scored)):.1f}%, "
                  f"always the commoner {100 * commoner / max(1, len(scored)):.1f}%")
            print("  the model: " + ", ".join(f"{name} {weight:+.2f}" for name, weight in zip(model.features, model.weights))
                  + f", constant {model.constant:+.2f}")
        if fit["ranking"]:
            model = Model.from_json(fit["ranking"])
            hand = fitted = counted = 0
            for decision in held:
                rows = [row for row in decision.rows if not learning.lacking([row], ranking_features)]
                if decision.taken is None or not rows:
                    continue
                counted += 1
                hand += max(rows, key=lambda row: row["score"])["id"] == decision.taken
                fitted += max(rows, key=lambda row: model.score(row["scores"]))["id"] == decision.taken
            print(f"  the ranking, on {counted} lists held out whose person is among the rows kept: right first by the "
                  f"score set by hand {100 * hand / max(1, counted):.1f}%, by the fitted model {100 * fitted / max(1, counted):.1f}%")
            print("  the model: " + ", ".join(f"{name} {weight:+.2f}" for name, weight in zip(model.features, model.weights))
                  + f", constant {model.constant:+.2f}")
    await clear()
    await storage.setup.disconnect()


async def suggest(args) -> None:
    """Step 10.5c: what the worker would suggest, by threshold. A sample of the mentions, each posed again as a
    payload with a stand-in and asked of the service as the dialog is answered (`--shown` displayed, the least score
    applied); of every second one the person is taken out ("someone new"). Half are kept as decisions and learnt
    from (as `learn`), so that the other half can be decided with and without a fit's "probably new". On the held
    half, for each `RECONCILE_SUGGEST_ABOVE` and `RECONCILE_SUGGEST_WITHIN` (`pangloss_reconcile.suggest.decide`,
    at most `--most` alternatives): for the mentions whose person is in the database, how often a suggestion is
    made, has the person first, has the person among its alternatives; for those whose person is not, how often
    one is made all the same; and how many alternatives a suggestion has"""
    global STAND_IN
    STAND_IN = True
    extras = {
        **extras_of(args),
        "RECONCILE_PROFILE": args.profile,
        "RECONCILE_FETCH": args.fetch,
        "RECONCILE_LEARN_FROM": args.learn_from,
    }
    storage = await connected(
        args.backend, args.url, BASE_APPS + installed(VECTOR_APPS) + ["pangloss_reconcile"], extras
    )
    import datetime

    from pangloss_core import backend
    from pangloss_cypher.write_functions import to_db_model
    from pangloss_cypher.write_plan import plan_create
    from pangloss_learn import Model
    from pangloss_models import ModelRegistry
    from pangloss_reconcile import decisions, fits, learning
    from pangloss_reconcile import settings as reconcile_settings
    from pangloss_reconcile.candidates import candidates_of
    from pangloss_reconcile.suggest import decide
    from pangloss_testing import planted

    if args.unconfirmed:
        # (what `reasons.py` costs when a class of guesses is registered, as with `pangloss-library`: the walk up
        # from every node with an edge to a candidate; the planted world holds no such node, so the answers are
        # the same and only the time differs)
        from pangloss_models import hooks

        hooks.unconfirmed.append(lambda: ["IdentificationByToolchain"])
    from pangloss_vectors import store

    database = backend.current().database()

    @database.write_transaction
    async def clear(tx):
        for label in ("PGReconcileExample", "PGReconcileShown", "PGReconcileModel"):
            await (await tx.run(f"MATCH (n:{label}) DELETE n")).consume()

    @database.read_transaction
    async def stored_ids(tx):
        result = await tx.run("MATCH (h:HeadNode) WHERE h:Factoid RETURN h.label AS label, h.id AS id")
        return {r["label"]: str(r["id"]) async for r in result}

    await clear()
    import pangloss_reconcile.reasons as reasons_module

    own: dict = {}
    original_shared = reasons_module.shared

    async def shared_but_own(plan, *a, **k):
        was = plan.head.id
        object.__setattr__(plan.head, "id", own["id"])
        try:
            return await original_shared(plan, *a, **k)
        finally:
            object.__setattr__(plan.head, "id", was)

    reasons_module.shared = shared_but_own
    world = planted.world(seed=args.seed, people=args.people, dated=DATED)
    mention_ids = {m.id for m in world.mentions}
    Factoid = ModelRegistry.all_models()["Factoid"]
    of_mention = {}
    for factoid in world.factoids:
        text = json.dumps(factoid)
        for m in world.mentions:
            if m.id in text:
                of_mention[m.id] = factoid
    by_label = await stored_ids()
    sample = world.mentions[:: max(1, len(world.mentions) // args.sample)][: args.sample]
    now = decisions.today(await store.states())
    least = reconcile_settings.least_score()
    print(f"{len(sample)} mentions of {len(world.mentions)}, profile {args.profile}, weights "
          f"{reconcile_settings.weights()}, least score {least}, {args.shown} displayed, at most {args.most} "
          "alternatives; of every second the person is taken out")

    held = []
    kept = 0
    began = time.perf_counter()
    for n, m in enumerate(sample):
        payload = _with_stand_in(of_mention[m.id], m.id, m.label)
        payload = {k: v for k, v in payload.items() if k not in ("id", "create_new")}
        plan = plan_create(to_db_model(Factoid.Create(**payload)))
        own["id"] = uuid.UUID(by_label[of_mention[m.id]["label"]])
        found = await candidates_of(plan, see_unpublished=True, limit=args.shown)
        assert len(found) == 1 and found[0].status == "ok", found
        gone = n % 2 == 1
        best = [c for c in found[0].best if c.id not in mention_ids and not (gone and c.id == m.person)]
        shown = [c for c in best if c.score >= least][: args.shown]
        shown_ids = {c.id for c in shown}
        rows = [
            {"id": c.id, "type": c.type, "scores": dict(c.scores), "shared": len(c.shared), "score": c.score,
             "displayed": c.id in shown_ids}
            for c in best
        ]
        taken = m.person if any(row["id"] == m.person for row in rows) else None
        if n % 4 < 2:
            record = {**now, "rows": json.dumps(rows)}

            @database.write_transaction
            async def write(tx, record=record, taken=taken, stand_in=m.id):
                await decisions.write_example(tx, stand_in, datetime.datetime.now(datetime.UTC), record, taken)

            await write()
            kept += 1
        else:
            held.append((m, gone, [(c.id, c.type, c.score) for c in shown], [r for r in rows if r["displayed"]]))
    print(f"{kept} decisions kept, {len(held)} held out; a mention asked in "
          f"{(time.perf_counter() - began) / max(1, len(sample)):.2f} s")
    await fits.learn()
    fit = await fits.in_use()
    if fit is None:
        written = await fits.fits()
        fit = written[0] if written else None
    model = Model.from_json(fit["none"]) if fit is not None and fit["none"] else None
    new_above = reconcile_settings.new_above()

    def table(with_fit: bool) -> None:
        here = [h for h in held if not h[1]]
        new = [h for h in held if h[1]]
        print(f"  {'with' if with_fit else 'without'} a fit's \"probably new\" (above {new_above}); {len(here)} "
              f"mentions whose person is in the database, {len(new)} whose person is not")
        print("  above within | made   first  among  | made for someone new | of those made, hold the person | "
              "alternatives")
        for above in (0.15, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 1.0):
            for within in (0.5, 0.7, 0.85):
                made = first = among = wrong = count = 0
                for m, gone, shown, rows in held:
                    likely = None
                    if with_fit and model is not None and rows:
                        likely = learning.none_likelihood(model, rows)
                    decision = decide(shown, above=above, most=args.most, within=within,
                                      probably_new=likely is not None and likely > new_above)
                    if not decision.suggested:
                        continue
                    count += len(decision.alternatives)
                    if gone:
                        wrong += 1
                        continue
                    made += 1
                    first += decision.alternatives[0].id == m.person
                    among += any(a.id == m.person for a in decision.alternatives)
                every = made + wrong
                print(f"  {above:5.2f} {within:6.2f} | {100 * made / max(1, len(here)):5.1f}% "
                      f"{100 * first / max(1, len(here)):5.1f}% {100 * among / max(1, len(here)):5.1f}% | "
                      f"{100 * wrong / max(1, len(new)):19.1f}% | {100 * among / max(1, every):28.1f}% | "
                      f"{count / max(1, every):.2f}")

    table(False)
    if model is not None:
        table(True)
    else:
        print("  (no fit with a \"none of these\" model: not decided with one)")
    await clear()
    await storage.setup.disconnect()


# --- step 10.5g: the worker measured at size ----------------------------------------------------------------------


def worker_extras(args) -> dict:
    """The settings the worker is measured with (and the rebuild before it made with): the profile `who` as in 10.5c,
    the defaults of the decision (0.6, 0.7, 3), nothing marked on save until a push says so, and no judge until a
    wave asks for one (both changed on the settings while the command runs)"""
    return {
        **extras_of(args),
        "RECONCILE_PROFILE": getattr(args, "profile", None) or "who",
        "RECONCILE_FETCH": getattr(args, "fetch", None) or 50,
        "RECONCILE_SUGGEST_ON_SAVE": False,
        "RECONCILE_SUGGEST_WITH": (str | None, None),
        "RECONCILE_SUGGEST_TIMEOUT": 60.0,
    }


async def unchanged_judge(asked):
    """(`RECONCILE_SUGGEST_WITH = "__main__:unchanged_judge"`, the second wave) a judge that answers at once that the
    decision stands: what asking one costs the worker"""
    from pangloss_reconcile import Unchanged

    return Unchanged()


def say(*parts) -> None:
    print(*parts, flush=True)


def tests_running() -> bool:
    """Whether a test run is going (another builder's: it skews every time). (`[b]in`: a shell whose own command line
    holds the pattern, such as one waiting with it, is not matched)"""
    import subprocess

    return subprocess.run(["pgrep", "-f", "[b]in/pytest"], capture_output=True).returncode == 0


async def quiet(what: str) -> None:
    """Wait, looking each minute, until no test run is going, before something that is timed"""
    waited = 0
    while tests_running():
        if waited == 0:
            say(f"  (before {what}: a test run is going; waiting for it to end)")
        await asyncio.sleep(60)
        waited += 60
    if waited:
        say(f"  (waited {waited // 60} min for a test run to end)")


def median(values) -> float:
    import statistics

    return statistics.median(values) if values else float("nan")


def p90(values) -> float:
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int(0.9 * len(ordered)))] if ordered else float("nan")


class Measured:
    """What the command's wrappers record, for the phase in hand: times by name, what each stand-in was answered and
    decided (by its id), what became of each head the worker did, and when"""

    def __init__(self) -> None:
        self.times: dict[str, list[float]] = {}
        self.found: dict[str, dict] = {}
        self.decided: dict[str, list] = {}
        self.outcomes: dict[str, dict] = {}
        self.vectored: dict[str, float] = {}
        self.updates: dict[str, float] = {}
        self.unconfirmed_off = False
        self.skip_still_mine: typing.Callable[[str], bool] = lambda head: False

    def add(self, name: str, seconds: float) -> None:
        self.times.setdefault(name, []).append(seconds)


NOW = {"measured": Measured()}
# (the vectors worker's batch: its default, 200, makes one read transaction of the graph part that outlasts Memgraph's
# transaction timeout at this size, seen at the first run: `--vectors-batch`)
VECTORS_BATCH = [50]


def measured() -> Measured:
    return NOW["measured"]


def instrument(by_head: dict, mention_ids: set[str], least: float) -> None:
    """Wrap what the worker calls, once: each wrapper times its call into the phase's `Measured`. And the one that
    changes what the worker is answered: `candidates_of` with the mentions' own people left out, and of a mention whose
    person is "someone new" that person too (10.5c's `suggest` filters `best` so)"""
    import dataclasses as dc

    import pangloss_models.rewriting as rewriting
    import pangloss_reconcile.candidates as candidates_module
    import pangloss_reconcile.reasons as reasons_module
    import pangloss_reconcile.stored as stored_module
    import pangloss_reconcile.suggest as suggest_module
    import pangloss_vectors.parts as parts_module
    import pangloss_vectors.search as search_module
    import pangloss_vectors.store as store_module
    import pangloss_vectors.worker as vectors_worker
    from pangloss_models import hooks
    from pangloss_reconcile import suggesting

    def timed(module, attribute, name):
        original = getattr(module, attribute)

        async def run(*a, **k):
            began = time.perf_counter()
            try:
                return await original(*a, **k)
            finally:
                measured().add(name, time.perf_counter() - began)

        setattr(module, attribute, run)
        return original

    timed(suggesting, "_shape_of", "trial of the shape (a stand-in)")
    timed(suggesting, "tried_of", "tried_of")
    timed(suggesting, "cited_targets", "cited_targets")
    timed(suggesting, "_candidates", "candidates (a head)")
    timed(suggesting, "judged", "judged (a stand-in)")
    timed(rewriting, "read_head", "read_head")
    timed(stored_module, "plan_of_view", "plan_of_view")
    original_rewrite = rewriting.rewrite

    async def rewrite(model, id, *a, **k):
        began = time.perf_counter()
        try:
            return await original_rewrite(model, id, *a, **k)
        finally:
            seconds = time.perf_counter() - began
            measured().add("the update (rewrite)", seconds)
            measured().updates[str(id)] = seconds

    rewriting.rewrite = rewrite
    timed(parts_module, "unknown_vectors", "  unknown_vectors (the parts' unknown)")
    timed(search_module, "nearest", "  nearest (each part alone)")
    timed(store_module, "read_part", "  read_part (each part)")
    timed(suggesting.Worker, "_complete", "complete (mark, tried)")
    original_of = suggesting.Judging.of

    async def judging_of(*a, **k):
        began = time.perf_counter()
        try:
            return await original_of(*a, **k)
        finally:
            measured().add("Judging.of (a head)", time.perf_counter() - began)

    suggesting.Judging.of = staticmethod(judging_of)

    original_shared = reasons_module.shared

    async def shared(*a, **k):
        began = time.perf_counter()
        swapped = None
        if measured().unconfirmed_off:
            swapped = hooks.unconfirmed_classes
            hooks.unconfirmed_classes = lambda: []
        try:
            return await original_shared(*a, **k)
        finally:
            if swapped is not None:
                hooks.unconfirmed_classes = swapped
            measured().add("  shared (reasons)", time.perf_counter() - began)

    reasons_module.shared = shared

    original_candidates_of = candidates_module.candidates_of

    async def candidates_of(plan, *, see_unpublished, limit=10, only=None):
        found = await original_candidates_of(plan, see_unpublished=see_unpublished, limit=limit, only=only)
        info = by_head.get(str(plan.head.id))
        excluded = mention_ids | ({info["person"]} if info and info["gone"] else set())
        made = []
        for one in found:
            best = tuple(c for c in one.best if c.id not in excluded)
            kept = [c for c in best if c.score >= least][:limit]
            one = dc.replace(one, candidates=kept, best=best)
            measured().found[one.unknown.id] = {
                "head": str(plan.head.id),
                "status": one.status,
                "candidates": [[c.id, c.score, dict(c.scores), len(c.shared)] for c in kept],
            }
            made.append(one)
        return made

    candidates_module.candidates_of = candidates_of

    original_decide_for = suggest_module.decide_for

    def decide_for(found, fit):
        began = time.perf_counter()
        decision = original_decide_for(found, fit)
        measured().add("decision", time.perf_counter() - began)
        measured().decided[found.unknown.id] = [
            decision.reason, [[a.id, a.type, a.percent] for a in decision.alternatives]
        ]
        return decision

    suggest_module.decide_for = decide_for

    original_still_mine = suggesting.still_mine

    def still_mine(head_id, token):
        check = original_still_mine(head_id, token)
        if measured().skip_still_mine(head_id):

            async def nothing(tx):
                return None

            return nothing

        async def timed_check(tx):
            began = time.perf_counter()
            try:
                await check(tx)
            finally:
                measured().add("still_mine's check (in the update)", time.perf_counter() - began)

        return timed_check

    suggesting.still_mine = still_mine

    original_process = suggesting.Worker.process

    async def process(self, claimed, seen=None):
        began = time.perf_counter()
        outcome = None
        try:
            outcome = await original_process(self, claimed, seen)
            return outcome
        finally:
            seconds = time.perf_counter() - began
            measured().add("a head, in all", seconds)
            measured().outcomes[claimed[0]] = {
                "what": outcome.what if outcome else "raised",
                "why": outcome.why if outcome else "",
                "suggestions": outcome.suggestions if outcome else 0,
                "seconds": seconds,
                "at": time.time(),
                "skipped_still_mine": measured().skip_still_mine(claimed[0]),
            }

    suggesting.Worker.process = process

    # (when the vectors worker has done a head: the end of the first batch that held it)
    original_read_batch = vectors_worker.read_batch
    claimed_now: list[list[str]] = [[]]

    async def read_batch(tx, claimed):
        claimed_now[0] = [head for head, _ in claimed]
        return await original_read_batch(tx, claimed)

    vectors_worker.read_batch = read_batch
    original_batch = vectors_worker.Worker.process_batch

    async def process_batch(self):
        claimed_now[0] = []
        done = await original_batch(self)
        at = time.time()
        for head in claimed_now[0]:
            measured().vectored.setdefault(head, at)
        return done

    vectors_worker.Worker.process_batch = process_batch


async def make_structure() -> None:
    """The indexes and constraints the migrations of review, the library and reconciliation would make (a bulk-loaded
    world has never been migrated): each made if it is not there"""
    from pangloss_core import backend as core_backend
    from pangloss_cypher.migrations import apply_changes
    from pangloss_models.migrations import changes as c
    from pangloss_models.migrations.files import EMPTY_SNAPSHOT, load

    made, there = 0, 0
    for app, names in (
        ("pangloss_review", ["0001_initial", "0003_uri_claims"]),
        ("pangloss_library", ["0005_addindex_createmodel_identificationbytoolchainfromtext_creat"]),
        ("pangloss_reconcile", ["0001_initial", "0002_models", "0003_suggested"]),
    ):
        for name in names:
            for change in load(app, name).changes:
                if not isinstance(change, (c.AddIndex, c.AddConstraint)):
                    continue
                try:
                    await apply_changes(core_backend.current().database(), EMPTY_SNAPSHOT, [change])
                    made += 1
                except Exception:  # noqa: BLE001
                    there += 1
    say(f"structure: {made} indexes and constraints made, {there} there already (or refused)")


def mention_factoids(world) -> dict[str, dict]:
    """The factoid that names each mention (each names one), by the mention's id"""
    ids = {m.id for m in world.mentions}
    found: dict[str, dict] = {}

    def walk(value, factoid):
        if isinstance(value, dict):
            if value.get("type") == "Person" and value.get("id") in ids:
                found[value["id"]] = factoid
            for inner in value.values():
                walk(inner, factoid)
        elif isinstance(value, list):
            for inner in value:
                walk(inner, factoid)

    for factoid in world.factoids:
        walk(factoid["statements"], factoid)
    return found


def place_of_mention(payload: dict) -> str:
    """Where the stand-in of a pushed factoid sits: `carried_out_by` (an activity with nobody else: no suggestion goes
    there) or `participants`"""
    [activity] = payload["statements"]
    return "carried_out_by" if activity["carried_out_by"].get("type") == "Mention" else "participants"


async def push(state, wave: int, mentions: list, on: bool, of_mention: dict) -> None:
    """A wave written as an upload writes it (`bulk_upload.upload`, eight at once, as `load`): each mention's own
    factoid with the mention's person in a stand-in's place, labelled with the wave; marked on save or not (`on`,
    `RECONCILE_SUGGEST_ON_SAVE`). Of every second mention the person is "someone new". Its heads kept in `state`"""
    import pangloss_core.settings as core_settings
    import pangloss_models.bulk_upload as bulk_upload
    from pangloss_core import backend as core_backend

    core_settings.SETTINGS.RECONCILE_SUGGEST_ON_SAVE = on
    suffix = f" [wave {wave}]"
    records, of_label = [], {}
    for n, m in enumerate(mentions):
        payload = _with_stand_in(of_mention[m.id], m.id, m.label)
        payload = {k: v for k, v in payload.items() if k not in ("id", "create_new")}
        payload["label"] = payload["label"] + suffix
        records.append((n + 1, payload))
        of_label[payload["label"]] = {
            "mention": m.id, "person": m.person, "label": m.label, "kind": m.kind, "gone": n % 2 == 1,
            "wave": wave, "place": place_of_mention(payload),
        }
    saves: list[float] = []
    original_creator = bulk_upload.creator

    class Timed:
        def __init__(self, create):
            self.create = create

        async def save(self):
            began = time.perf_counter()
            done = await self.create.save()
            saves.append(time.perf_counter() - began)
            info = of_label[self.create.label]
            info["pushed_at"] = time.time()
            # (known at once: a worker running beside the push, in the server, is answered by it)
            if getattr(done, "id", None) is not None:
                state["by_head"][str(done.id)] = {**info, "head": str(done.id)}
            return done

    def creator(number, record):
        type_name, create = original_creator(number, record)
        return type_name, Timed(create)

    bulk_upload.creator = creator
    began = time.perf_counter()
    try:
        await bulk_upload.upload(records, concurrency=8)
    finally:
        bulk_upload.creator = original_creator
        core_settings.SETTINGS.RECONCILE_SUGGEST_ON_SAVE = False
    seconds = time.perf_counter() - began
    database = core_backend.current().database()

    @database.read_transaction
    async def ids(tx):
        result = await tx.run(
            "MATCH (h:HeadNode) WHERE h:Factoid AND h.label ENDS WITH $suffix RETURN h.label AS label, h.id AS id",
            suffix=suffix,
        )
        return {row["label"]: str(row["id"]) async for row in result}

    for label, head in (await ids()).items():
        if label in of_label:
            state["by_head"][head] = {**of_label[label], "head": head}
    places = [info["place"] for info in of_label.values()]
    state.setdefault("pushes", {})[str(wave)] = {
        "count": len(records), "seconds": seconds, "on": on, "median": median(saves), "p90": p90(saves),
        "most": max(saves), "participants": places.count("participants"),
        "carried_out_by": places.count("carried_out_by"),
    }
    say(f"push of wave {wave} ({len(records):,} factoids, marked on save: {'yes' if on else 'no'}): {seconds:.1f} s, "
        f"{len(records) / seconds:.1f} a second with 8 writers; a save {median(saves) * 1000:.0f} ms at the median, "
        f"90% {p90(saves) * 1000:.0f} ms, most {max(saves) * 1000:.0f} ms; the stand-in in a participant's place "
        f"{places.count('participants'):,}, as `carried_out_by` {places.count('carried_out_by'):,}")


async def vectors_drained(what: str) -> float:
    """The vectors worker run to its end (`run_pending`), timed"""
    from pangloss_vectors import worker as vectors_worker
    from pangloss_vectors.worker import run_pending

    await quiet(f"the vectors worker ({what})")
    vectors_worker.worker.settings.batch = VECTORS_BATCH[0]
    began = time.perf_counter()
    done = await run_pending()
    seconds = time.perf_counter() - began
    say(f"the vectors worker, {what}: {done:,} heads in {seconds:.1f} s"
        + (f" ({60 * done / seconds:.0f} a minute)" if done and seconds else ""))
    return seconds


async def counts() -> dict[str, int]:
    """The marks of the two kinds, and how many are claimed"""
    from pangloss_core import backend as core_backend
    from pangloss_cypher import pending

    database = core_backend.current().database()

    @database.read_transaction
    async def read(tx):
        made = {}
        for kind in ("reconcile", "vectors"):
            found = await pending.count(tx, kind)
            made[kind] = int(found["pending"])
            made[kind + " claimed"] = int(found["claimed"])
        return made

    return await read()


class Monitor:
    """A line each `every` seconds while a phase runs: the backlog of each worker, what the reconcile worker has done,
    and whether a test run is going (then the phase's times are not to be trusted, and it is said)"""

    def __init__(self, label: str, every: float = 30.0, heads: typing.Collection[str] = ()):
        self.label, self.every, self.heads = label, every, set(heads)
        self.began = time.perf_counter()
        self.overlapped = False
        self.task = None

    async def line(self) -> None:
        from pangloss_reconcile import suggesting

        found = await counts()
        m = measured()
        done = len(m.outcomes)
        stats = suggesting.worker.stats
        running = tests_running()
        self.overlapped |= running
        said = (f"  {time.perf_counter() - self.began:7.0f} s: reconcile marks {found['reconcile']:,} "
                f"({found['reconcile claimed']} claimed), vectors marks {found['vectors']:,}; heads done {done:,}, "
                f"suggestions {stats.suggestions:,}")
        if self.heads:
            said += f", of the push vectored {sum(1 for h in self.heads if h in m.vectored):,}"
        say(said + ("; A TEST RUN IS GOING" if running else ""))

    async def loop(self) -> None:
        while True:
            await asyncio.sleep(self.every)
            try:
                await self.line()
            except Exception as error:  # noqa: BLE001
                say(f"  (the line failed: {error})")

    def __enter__(self):
        self.task = asyncio.get_running_loop().create_task(self.loop())
        return self

    def __exit__(self, *exc):
        self.task.cancel()
        if self.overlapped:
            say(f"  ** a test run went on during {self.label}: its times are not clean **")


def stage_lines(m: Measured, heads: int, stand_ins: int) -> None:
    """The time of each stage the wrappers timed, at the median and in all, and per head"""
    for name in sorted(m.times, key=lambda n: (n.startswith("  "), n)):
        values = m.times[name]
        say(f"    {name}: {len(values):,} calls, median {median(values) * 1000:.1f} ms, 90% {p90(values) * 1000:.1f} ms, "
            f"in all {sum(values):.1f} s ({sum(values) / max(1, heads) * 1000:.0f} ms a head)")


def worker_lines(label: str, m: Measured, seconds: float, heads_of_wave: typing.Mapping[str, typing.Any]) -> None:
    """What a run of the reconcile worker did: heads and mentions a minute, by outcome, by stage"""
    from pangloss_reconcile import suggesting

    outcomes = m.outcomes
    asked = len(m.found)
    say(f"{label}: {len(outcomes):,} heads in {seconds:.1f} s: {60 * len(outcomes) / seconds:.1f} documents a minute, "
        f"{60 * asked / seconds:.1f} mentions asked a minute ({asked:,} asked); stats {suggesting.worker.stats}")
    by_what: dict[str, list[float]] = {}
    for head, outcome in outcomes.items():
        key = outcome["what"] + (f" (wave {heads_of_wave[head]['wave']})" if head in heads_of_wave else " (another)")
        by_what.setdefault(key, []).append(outcome["seconds"])
    for key, values in sorted(by_what.items()):
        say(f"    {key}: {len(values):,} heads, median {median(values) * 1000:.0f} ms, 90% {p90(values) * 1000:.0f} ms")
    stage_lines(m, len(outcomes), asked)


async def drained_apart(state, label: str, heads_of_wave: set[str]) -> float:
    """The reconcile worker run to its end in this process (`suggesting.drain`), the vectors worker before it, with a
    line each 30 s"""
    from pangloss_reconcile import suggesting

    await quiet(label)
    began = time.perf_counter()
    with Monitor(label):
        await suggesting.drain()
    seconds = time.perf_counter() - began
    worker_lines(label, measured(), seconds, state["by_head"])
    for wave in sorted({i["wave"] for h, i in state["by_head"].items() if h in measured().outcomes}):
        done = [o for h, o in measured().outcomes.items() if state["by_head"].get(h, {}).get("wave") == wave]
        if len(done) > 1:
            span = max(o["at"] for o in done) - min(o["at"] - o["seconds"] for o in done)
            say(f"    wave {wave}: {len(done):,} heads in {span:.0f} s, {60 * len(done) / max(span, 1e-9):.1f} a minute")
    return seconds


def as_state(m: Measured) -> dict:
    return {"times": m.times, "found": m.found, "decided": m.decided, "outcomes": m.outcomes, "vectored": m.vectored,
            "updates": m.updates}


def save_state(path: Path, state: dict) -> None:
    path.write_text(json.dumps(state), encoding="utf-8")


async def ask_stored(heads: list[str]) -> None:
    """Each head's stand-ins asked as the worker asks them (`candidates_of(plan_of_view(...), see_unpublished=True,
    limit=DISPLAYED, only=...)`) and decided, nothing written: those in a place that takes a suggestion (a participant)"""
    from uuid import UUID

    from pangloss_models import ModelRegistry
    from pangloss_models.rewriting import read_head
    from pangloss_reconcile.candidates import DISPLAYED
    import pangloss_reconcile.candidates as candidates_module
    import pangloss_reconcile.suggest as suggest_module
    from pangloss_reconcile.stored import plan_of_view
    from pangloss_reconcile.suggesting import _above, place_of
    from pangloss_vectors.unknowns import unknowns_of

    Factoid = ModelRegistry.all_models()["Factoid"]
    for head in heads:
        view = await read_head(Factoid, UUID(head))
        plan = await plan_of_view(Factoid, view)
        above = _above(plan)
        ids = [u.id for u in unknowns_of(plan) if "carried_out_by" not in place_of(u.id, above)]
        if not ids:
            continue
        for found in await candidates_module.candidates_of(plan, see_unpublished=True, limit=DISPLAYED, only=ids):
            suggest_module.decide_for(found, None)


async def written_suggestions(heads: list[str]) -> dict[str, list]:
    """The suggestions written in these heads, read from the database: by head, the alternatives [person, per cent]"""
    from pangloss_core import backend as core_backend

    database = core_backend.current().database()

    @database.read_transaction
    async def read(tx):
        result = await tx.run(
            """
            UNWIND $heads AS h
            MATCH (s:IdentificationByToolchainFromText {head_node_id: h})-[t:target]->(w)-[a:alternatives]->(p:Person)
            WHERE coalesce(t.reverse, false) = false AND coalesce(a.reverse, false) = false
            RETURN h, s.id AS s, p.id AS p, a.percent AS percent
            """,
            heads=heads,
        )
        made: dict[str, list] = {}
        async for row in result:
            made.setdefault(str(row["h"]), []).append([str(row["p"]), row["percent"]])
        return made

    found = await read()
    for alternatives in found.values():
        alternatives.sort(key=lambda pair: (-(pair[1] or 0), pair[0]))
    return found


async def tried_count(heads: list[str]) -> int:
    from pangloss_core import backend as core_backend

    database = core_backend.current().database()

    @database.read_transaction
    async def read(tx):
        record = await (await tx.run(
            "UNWIND $heads AS h MATCH (t:PGReconcileTried {head: h}) RETURN count(t) AS n", heads=heads
        )).single()
        return int(record["n"])

    return await read()


async def what_was_suggested(state, wave: int, phase: str) -> dict:
    """Of a wave's mentions: for those whose person is in the database, a suggestion written, the person first, among
    its alternatives; for those whose person is not, a suggestion written all the same; left for no place, for a low
    score or "new"; tried rows; alternatives per suggestion. Compared with 10.5c at 0.6 / 0.7 / 3"""
    heads = {h: info for h, info in state["by_head"].items() if info["wave"] == wave}
    written = await written_suggestions(sorted(heads))
    recorded = state["phases"][phase]
    found_by_head = {f["head"]: (sid, f) for sid, f in recorded["found"].items()}
    here = [h for h, i in heads.items() if not i["gone"]]
    new = [h for h, i in heads.items() if i["gone"]]
    reasons: dict[str, int] = {}
    statuses: dict[str, int] = {}
    for h in heads:
        if h in found_by_head:
            sid, f = found_by_head[h]
            statuses[f["status"]] = statuses.get(f["status"], 0) + 1
            reason = recorded["decided"].get(sid, ["not decided"])[0]
        else:
            reason = "no place (carried_out_by)" if heads[h]["place"] == "carried_out_by" else "not asked"
        reasons[reason] = reasons.get(reason, 0) + 1
    made_here = [h for h in here if h in written]
    first = [h for h in made_here if written[h][0][0] == heads[h]["person"]]
    among = [h for h in made_here if any(p == heads[h]["person"] for p, _ in written[h])]
    made_new = [h for h in new if h in written]
    placed_here = [h for h in here if heads[h]["place"] == "participants"]
    placed_new = [h for h in new if heads[h]["place"] == "participants"]
    alternatives = [len(written[h]) for h in written]
    tried = await tried_count(sorted(heads))
    # (does what was written agree with what the worker decided, as recorded)
    agree = sum(
        1 for h in written
        if h in found_by_head
        and sorted([a[0], a[2]] for a in recorded["decided"].get(found_by_head[h][0], [None, []])[1])
        == sorted([p, percent] for p, percent in written[h])
    )

    def pct(part, whole):
        return f"{100 * len(part) / max(1, len(whole)):.1f}%"

    say(f"what was suggested, wave {wave} ({len(heads):,} mentions: {len(here):,} whose person is in the database, "
        f"{len(new):,} whose person is not; in a participant's place {len(placed_here) + len(placed_new):,}):")
    say(f"  person in the database: a suggestion written {pct(made_here, here)} (of those in a place that takes one "
        f"{pct(made_here, placed_here)}), the person first {pct(first, here)}, among its alternatives "
        f"{pct(among, here)}; of the suggestions written for them, holding the person {pct(among, made_here)}")
    say(f"  person not in the database: a suggestion written all the same {pct(made_new, new)} (of those in a place "
        f"that takes one {pct(made_new, placed_new)})")
    say("  every mention by what was decided: " + ", ".join(f"{k} {v:,}" for k, v in sorted(reasons.items()))
        + "; candidates' status: " + ", ".join(f"{k} {v:,}" for k, v in sorted(statuses.items())))
    say(f"  tried rows of the wave's heads {tried:,}; alternatives per suggestion {sum(alternatives) / max(1, len(alternatives)):.2f} "
        f"({len(alternatives):,} suggestions); written as decided {agree:,} of {len(written):,}")
    say("  10.5c at 0.6 / 0.7 / 3, without a fit (planted_suggest_memgraph.txt, 200 + 200 mentions asked as payloads): "
        "made 34.0%, first 31.0%, among 33.5%, made for someone new 18.5%, 2.88 alternatives")
    return {"here": len(here), "new": len(new), "made_here": len(made_here), "first": len(first),
            "among": len(among), "made_new": len(made_new), "reasons": reasons, "tried": tried,
            "alternatives": sum(alternatives) / max(1, len(alternatives))}


def compare_waves(state) -> None:
    """The second wave's mentions as they were asked before the first wave's suggestions were written (`before`) and as
    the worker asked them after (`after`): the decision, the candidates and their scores, part by part"""
    before = state["phases"]["ask_second"]
    after = state["phases"]["first"]
    common = sorted(set(before["found"]) & set(after["found"]))
    decision_differs, order_differs = [], []
    by_part: dict[str, int] = {}
    largest: dict[str, float] = {}
    shared_counts = 0
    example = None
    for sid in common:
        b, a = before["found"][sid], after["found"][sid]
        if before["decided"].get(sid) != after["decided"].get(sid):
            decision_differs.append(sid)
        if [c[0] for c in b["candidates"]] != [c[0] for c in a["candidates"]]:
            order_differs.append(sid)
        bs = {c[0]: c for c in b["candidates"]}
        differs_here = False
        for c in a["candidates"]:
            if c[0] not in bs:
                continue
            old = bs[c[0]]
            if old[3] != c[3]:
                shared_counts += 1
                differs_here = True
            for part in set(old[2]) | set(c[2]):
                gap = abs(old[2].get(part, 0.0) - c[2].get(part, 0.0))
                if gap > 1e-9:
                    by_part[part] = by_part.get(part, 0) + 1
                    largest[part] = max(largest.get(part, 0.0), gap)
                    differs_here = True
        if (differs_here or sid in decision_differs) and example is None:
            example = (sid, b, a, before["decided"].get(sid), after["decided"].get(sid))
    say(f"the two waves: {len(common):,} mentions of the second wave asked before the first wave's suggestions were "
        f"written and after (by the worker): the decision differs for {len(decision_differs):,}, the order of the "
        f"candidates for {len(order_differs):,}; candidates whose count of what is shared differs {shared_counts:,}; "
        "scores that differ by part (candidates; the largest gap): "
        + (", ".join(f"{p} {n:,} ({largest[p]:.2g})" for p, n in sorted(by_part.items())) or "none"))
    if example is not None:
        sid, b, a, db, da = example
        say(f"  for example the stand-in {sid}: before {db}, after {da}")
        for name, f in (("before", b), ("after", a)):
            say(f"    {name}: " + "; ".join(
                f"{c[0][:8]} {c[1]:.4f} " + " ".join(f"{k} {v:.4f}" for k, v in sorted(c[2].items())) + f" shared {c[3]}"
                for c in f["candidates"]))


async def unconfirmed_cost(world, mentions: list, of_mention: dict) -> None:
    """6a: what `reasons.py`'s condition on unconfirmed classes costs a request at size: each mention posed as a
    payload with a stand-in (not written), asked with the condition and without it (`hooks.unconfirmed_classes`
    emptied for `shared` alone), in turn, the first first for one mention and second for the next"""
    from pangloss_cypher.write_functions import to_db_model
    from pangloss_cypher.write_plan import plan_create
    from pangloss_models import ModelRegistry
    import pangloss_reconcile.candidates as candidates_module

    Factoid = ModelRegistry.all_models()["Factoid"]
    await quiet("the cost of the condition on unconfirmed classes")
    whole: dict[bool, list[float]] = {True: [], False: []}
    shared_times: dict[bool, list[float]] = {True: [], False: []}
    with Monitor("6a"):
        for n, m in enumerate(mentions):
            payload = _with_stand_in(of_mention[m.id], m.id, m.label)
            payload = {k: v for k, v in payload.items() if k not in ("id", "create_new")}
            plan = plan_create(to_db_model(Factoid.Create(**payload)))
            for with_it in ((True, False) if n % 2 == 0 else (False, True)):
                measured().unconfirmed_off = not with_it
                measured().times.pop("  shared (reasons)", None)
                began = time.perf_counter()
                await candidates_module.candidates_of(plan, see_unpublished=True, limit=5)
                whole[with_it].append(time.perf_counter() - began)
                shared_times[with_it].extend(measured().times.get("  shared (reasons)", []))
    measured().unconfirmed_off = False
    for with_it in (True, False):
        say(f"6a. a request, {len(mentions)} mentions as payloads, {'with' if with_it else 'without'} the condition on "
            f"unconfirmed classes: median {median(whole[with_it]) * 1000:.0f} ms, 90% {p90(whole[with_it]) * 1000:.0f} ms; "
            f"of it `shared` median {median(shared_times[with_it]) * 1000:.1f} ms, 90% {p90(shared_times[with_it]) * 1000:.1f} ms, "
            f"most {max(shared_times[with_it]) * 1000:.1f} ms")


async def marked_stored() -> None:
    """6b: `mark_stored` over every stored factoid (`pangloss reconcile suggest`): its page query, the whole time, marks a
    second"""
    from pangloss_core import backend as core_backend
    from pangloss_reconcile import suggesting

    await quiet("mark_stored")
    database = core_backend.current().database()
    labels = suggesting.stand_in_labels()

    @database.read_transaction
    async def page(tx, label):
        began = time.perf_counter()
        rows = [r async for r in await tx.run(suggesting.STORED_PAGE_QUERY.format(label=label), after="", page=suggesting.PAGE)]
        return len(rows), time.perf_counter() - began

    @database.read_transaction
    async def stand_ins(tx, label):
        record = await (await tx.run(f"MATCH (s:{label}) RETURN count(s) AS n")).single()
        return int(record["n"])

    for label in labels:
        heads, seconds = await page(label)
        say(f"6b. the page query of `mark_stored` for {label} ({await stand_ins(label):,} stand-ins of the label): the "
            f"first page ({heads:,} heads) {seconds * 1000:.0f} ms")
    began = time.perf_counter()
    done = await suggesting.mark_stored()
    seconds = time.perf_counter() - began
    say(f"6b. mark_stored over every stored factoid: {done}, {seconds:.2f} s, {done.marked / seconds:.0f} marks a second")


async def in_server(state, wave: int, mentions: list, of_mention: dict) -> None:
    """3: the vectors worker and the reconcile worker as the server runs them (`pangloss_api.background.Supervisor`, the
    two `BackgroundTask`s the apps' `configure_app` add, `worker.run` of each in this loop), from the push on: the push
    in the same loop, with a line each 30 s, until both backlogs are empty"""
    import pangloss_core.settings as core_settings
    from pangloss_api.background import BackgroundTask, Supervisor
    from pangloss_reconcile import suggesting
    from pangloss_vectors import worker as vectors_worker

    await quiet("the workers in the server")
    vectors_worker.worker.settings.batch = VECTORS_BATCH[0]
    supervisor = Supervisor(
        core_settings.SETTINGS,
        [BackgroundTask("vectors", vectors_worker.worker.run), BackgroundTask("reconcile", suggesting.worker.run)],
    )
    began = time.perf_counter()
    started = time.time()
    supervisor.start()
    monitor = Monitor("the workers in the server")
    with monitor:
        await push(state, wave, mentions, True, of_mention)
        heads = {h for h, i in state["by_head"].items() if i["wave"] == wave}
        monitor.heads = heads
        pushed = time.perf_counter() - began
        say(f"  the push ended at {pushed:.0f} s")
        while True:
            found = await counts()
            if (not found["reconcile"] and not found["vectors"]
                    and all(h in measured().outcomes for h in heads)):
                break
            if time.perf_counter() - began > 6 * 3600:
                say("  ** stopped after six hours with work left **")
                break
            await asyncio.sleep(5)
    await supervisor.stop()
    seconds = time.perf_counter() - began
    m = measured()
    infos = state["by_head"]
    done = [h for h in heads if h in m.outcomes]
    last = max((m.outcomes[h]["at"] for h in done if m.outcomes[h]["what"] == "written"), default=None)
    vectors_lag = [m.vectored[h] - infos[h]["pushed_at"] for h in heads if h in m.vectored and "pushed_at" in infos[h]]
    reconcile_lag = [m.outcomes[h]["at"] - m.vectored[h] for h in done if h in m.vectored]
    whole_lag = [m.outcomes[h]["at"] - infos[h]["pushed_at"] for h in done if "pushed_at" in infos[h]]
    say(f"3. in the server: {len(heads):,} pushed; all done after {seconds:.0f} s (the push {pushed:.0f} s); the last "
        f"suggestion written {last - started:.0f} s after the push began" if last else "3. no suggestion written")
    for name, values in (("written to vectored (the vectors worker's lag)", vectors_lag),
                         ("vectored to done by the reconcile worker (its lag behind the vectors worker)", reconcile_lag),
                         ("written to done by the reconcile worker", whole_lag)):
        if values:
            say(f"  {name}: median {median(values):.0f} s, 90% {p90(values):.0f} s, most {max(values):.0f} s")
    # (the lag by the order of the push: does it grow)
    ordered = sorted((infos[h]["pushed_at"], h) for h in done if "pushed_at" in infos[h])
    for start in range(0, len(ordered), max(1, len(ordered) // 10)):
        chunk = ordered[start:start + max(1, len(ordered) // 10)]
        lags = [m.outcomes[h]["at"] - at for at, h in chunk]
        vlags = [m.vectored[h] - at for at, h in chunk if h in m.vectored]
        say(f"  pushed {start + 1:,} to {start + len(chunk):,}: written to vectored median {median(vlags):.0f} s, "
            f"written to done median {median(lags):.0f} s")
    say(f"  statuses of the tasks: {supervisor.status()}")
    worker_lines("the reconcile worker in the server", m, seconds, state["by_head"])


async def worker(args) -> None:
    """Step 10.5g: the worker that suggests (`pangloss_reconcile.suggesting`) at size, on the world as loaded and rebuilt
    (`rebuild --dated --worker-models --profiles ...` first). Three pushes of `--push` mentions each (each mention's own
    factoid with the person in a stand-in's place, unpublished), and the costs the earlier steps asked for. The phases,
    in order (each kept in `--state`, so that `--resume` goes on after the last done):

    push_first      the first wave, marked on save (the push timed)
    push_second     the second wave, not marked (the same push without the marking)
    vectors         the vectors worker run to its end
    ask_second      of the second wave every `--compare-every`th asked as the worker asks it, nothing written: before
                    the first wave's suggestions
    mark            `mark_stored` over every stored factoid (6b): the second wave marked, after the first
    first           the reconcile worker apart, a line each 30 s: the first wave, then the second (every second head of
                    it written without `still_mine`, 6c); then the vectors worker on what it wrote
    judge           6d: a small fourth wave (`--judge-push` mentions) pushed, marked, and done with a judge that answers
                    `Unchanged()` at once
    unconfirmed     6a: payload requests with and without the condition on unconfirmed classes
    server          the third wave (`--server-push` mentions) pushed with both workers running as the server runs them
    and then what was suggested, of each wave, and the two waves compared"""
    global STAND_IN, TOOLCHAIN
    STAND_IN = TOOLCHAIN = True
    storage = await connected(args.backend, args.url, installed(WORKER_APPS), worker_extras(args))
    import pangloss_core.settings as core_settings
    from pangloss_core import backend as core_backend
    from pangloss_reconcile import fits, suggesting
    from pangloss_reconcile import settings as reconcile_settings
    from pangloss_testing import planted
    from pangloss_vectors import store

    from pangloss_reconcile.suggesting import profile_status

    state_path = Path(args.state)
    state = json.loads(state_path.read_text(encoding="utf-8")) if args.resume and state_path.exists() else {
        "by_head": {}, "phases": {}, "done": []}
    world = planted.world(seed=args.seed, people=args.people, dated=DATED)
    of_mention = mention_factoids(world)
    mention_ids = {m.id for m in world.mentions}
    least = reconcile_settings.least_score()
    instrument(state["by_head"], mention_ids, least)
    n, at = args.push, args.offset
    waves = {1: world.mentions[at:at + n], 2: world.mentions[at + n:at + 2 * n], 3: world.mentions[at + 2 * n:at + 3 * n]}
    sample = world.mentions[at + 3 * n:at + 3 * n + args.sample]
    waves[4] = world.mentions[at + 3 * n + args.sample:at + 3 * n + args.sample + args.judge_push]
    VECTORS_BATCH[0] = args.vectors_batch
    say(f"{len(world.mentions):,} mentions of {len(world.people):,} people; three waves of {n:,} from {at:,}, a sample "
        f"of {len(sample):,} after them and a wave of as many for the judge; profile {reconcile_settings.profile()}, weights {reconcile_settings.weights()}, "
        f"least score {least}; suggest above {reconcile_settings.suggest_above()}, within "
        f"{reconcile_settings.suggest_within()}, at most {reconcile_settings.suggest_most()}; {args.backend} {args.url}")
    states = await store.states()
    status = profile_status(states)
    if status != "ok":
        sys.exit(f"The profile is {status}: rebuild with --worker-models first")
    if await fits.in_use() is not None:
        sys.exit("A fit is in use: the figures are of the worker without one, as 10.5c's")
    database = core_backend.current().database()

    def phase(name):
        return name not in state["done"]

    def finished(name, m: Measured, **more):
        state["phases"][name] = {**as_state(m), **more}
        state["done"].append(name)
        save_state(state_path, state)
        NOW["measured"] = Measured()
        NOW["measured"].skip_still_mine = lambda head: False

    if not state["done"]:
        await make_structure()

        @database.read_transaction
        async def foreign(tx):
            result = await tx.run("MATCH (p:PGPending) RETURN p.kind AS kind, count(p) AS n")
            return {row["kind"]: int(row["n"]) async for row in result}

        stale = {k: v for k, v in (await foreign()).items() if k not in ("reconcile", "vectors")}
        if stale:
            from pangloss_cypher import pending

            @database.read_transaction
            async def count_reconcile(tx):
                began = time.perf_counter()
                await pending.count(tx, "reconcile")
                return time.perf_counter() - began

            with_them = [await count_reconcile() for _ in range(5)]

            @database.write_transaction
            async def clear(tx):
                record = await (await tx.run(
                    "MATCH (p:PGPending) WHERE p.kind IN $kinds WITH p LIMIT 50000 DELETE p RETURN count(*) AS n",
                    kinds=sorted(stale),
                )).single()
                return int(record["n"])

            while await clear():
                pass
            without = [await count_reconcile() for _ in range(5)]
            say(f"the marks the bulk load left for workers never run ({stale}) deleted: a count of the reconcile marks "
                f"took {median(with_them) * 1000:.0f} ms with them, {median(without) * 1000:.1f} ms after (PGPending is "
                "found by its label, the kind is not indexed)")

    if phase("push_first"):
        await quiet("the first push")
        with Monitor("the first push"):
            await push(state, 1, waves[1], True, of_mention)
        finished("push_first", measured())
    if phase("push_second"):
        await quiet("the second push")
        with Monitor("the second push"):
            await push(state, 2, waves[2], False, of_mention)
        finished("push_second", measured())
    if phase("vectors"):
        seconds = await vectors_drained("after the two pushes")
        finished("vectors", measured(), seconds=seconds)
    second_heads = sorted(h for h, i in state["by_head"].items() if i["wave"] == 2)
    first_heads = {h for h, i in state["by_head"].items() if i["wave"] == 1}
    if phase("ask_second"):
        await quiet("the second wave asked")
        began = time.perf_counter()
        with Monitor("the second wave asked"):
            await ask_stored(second_heads[:: args.compare_every])
        seconds = time.perf_counter() - began
        asked = len(measured().found)
        say(f"the second wave asked as the worker asks it, nothing written (every {args.compare_every}): {asked:,} "
            f"stand-ins of {len(second_heads[:: args.compare_every]):,} "
            f"heads in {seconds:.0f} s ({seconds / max(1, asked):.2f} s a stand-in)")
        stage_lines(measured(), len(second_heads[:: args.compare_every]), asked)
        finished("ask_second", measured(), seconds=seconds)
    if phase("mark"):
        # (the second wave marked now, after the first: the worker does the oldest marks first, so the whole first
        # wave is written before any of the second is asked)
        say(f"status before: {await suggesting.status()}")
        await marked_stored()
        say(f"status after: {await suggesting.status()}")
        finished("mark", measured())
    if phase("first"):
        # (6c: every second head of the second wave written without the check `still_mine` adds)
        order = {h: k for k, h in enumerate(second_heads)}
        measured().skip_still_mine = lambda head: head in order and order[head] % 2 == 1
        seconds = await drained_apart(
            state, "2. the reconcile worker apart, the first wave and then the second (and 6c)", first_heads
        )
        m = measured()
        last_first = max((o["at"] for h, o in m.outcomes.items() if h in first_heads), default=0)
        first_second = min((o["at"] - o["seconds"] for h, o in m.outcomes.items() if h in order), default=0)
        say(f"  the first wave's last head ended {last_first - first_second:+.1f} s from the second wave's first "
            "(negative: none of the second was begun before the first was done)")
        updates = {True: [], False: []}
        for h, seconds_ in m.updates.items():
            if m.outcomes.get(h, {}).get("what") == "written":
                updates[m.outcomes[h]["skipped_still_mine"]].append(seconds_)
        for skipped in (False, True):
            say(f"6c. the update, {'without' if skipped else 'with'} still_mine: {len(updates[skipped]):,} updates, "
                f"median {median(updates[skipped]) * 1000:.1f} ms, 90% {p90(updates[skipped]) * 1000:.1f} ms")
        checks = m.times.get("still_mine's check (in the update)", [])
        say(f"6c. still_mine's check alone: {len(checks):,}, median {median(checks) * 1000:.1f} ms, "
            f"90% {p90(checks) * 1000:.1f} ms")
        finished("first", m, seconds=seconds)
        await vectors_drained("after the two waves' suggestions")
    if phase("judge"):
        # (6d, on a small wave of its own: a judge configured changes the digest of "tried", so a head of an earlier
        # wave marked again would be asked again under it; here only this wave is marked)
        await quiet("the judge's wave")
        await push(state, 4, waves[4], True, of_mention)
        await vectors_drained("after the judge's wave")
        core_settings.SETTINGS.RECONCILE_SUGGEST_WITH = "__main__:unchanged_judge"
        try:
            seconds = await drained_apart(state, "6d. the reconcile worker apart, with a judge that answers Unchanged()",
                                          {h for h, i in state["by_head"].items() if i["wave"] == 4})
        finally:
            core_settings.SETTINGS.RECONCILE_SUGGEST_WITH = None
        m = measured()
        judged = m.times.get("judged (a stand-in)", [])
        of = m.times.get("Judging.of (a head)", [])
        say(f"6d. a judge that answers Unchanged() at once (async): Judging.of {len(of):,} heads, median "
            f"{median(of) * 1000:.0f} ms; judged {len(judged):,} stand-ins, median {median(judged) * 1000:.0f} ms; "
            f"what it adds, in all, {(sum(of) + sum(judged)) / max(1, len(judged)) * 1000:.0f} ms a mention")
        finished("judge", m, seconds=seconds)
        await vectors_drained("after the judge's wave's suggestions")
    if phase("unconfirmed"):
        await unconfirmed_cost(world, sample, of_mention)
        finished("unconfirmed", measured())
    if phase("server"):
        await in_server(state, 3, waves[3][: args.server_push], of_mention)
        finished("server", measured())
    say("")
    results = {}
    for wave, name in ((1, "first"), (2, "first"), (4, "judge"), (3, "server")):
        results[wave] = await what_was_suggested(state, wave, name)
    compare_waves(state)
    state["results"] = results
    save_state(state_path, state)
    from pangloss_review.reconcile import background_done

    await background_done()
    await storage.setup.disconnect()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    commands = parser.add_subparsers(dest="command", required=True)
    w = commands.add_parser("write")
    w.add_argument("dir")
    w.add_argument("--people", type=int, default=32_000)
    w.add_argument("--seed", type=int, default=1)
    w.add_argument("--dated", action="store_true")
    for name in ("empty", "load", "recover", "rebuild", "base", "names", "time", "reports", "reconcile", "learn", "suggest", "worker"):
        c = commands.add_parser(name)
        c.add_argument("--dated", action="store_true")
        if name == "reconcile":
            c.add_argument("--profile", default="who")
            c.add_argument("--sample", type=int, default=300)
            c.add_argument("--fetch", type=int, default=50)
            c.add_argument("--people", type=int, default=32_000)
            c.add_argument("--seed", type=int, default=1)
            c.add_argument("--weights", action="append", default=None)
        if name == "suggest":
            c.add_argument("--most", type=int, default=3)
            c.add_argument("--unconfirmed", action="store_true")
        if name in ("learn", "suggest"):
            c.add_argument("--profile", default="who")
            c.add_argument("--sample", type=int, default=400)
            c.add_argument("--fetch", type=int, default=50)
            c.add_argument("--shown", type=int, default=5)
            c.add_argument("--learn-from", type=int, default=50)
            c.add_argument("--people", type=int, default=32_000)
            c.add_argument("--seed", type=int, default=1)
        if name == "rebuild":
            c.add_argument("--stand-in", action="store_true")
            c.add_argument("--worker-models", action="store_true", help="the models `worker` is measured on")
        if name == "worker":
            c.add_argument("--push", type=int, default=2000, help="mentions in each of the three waves")
            c.add_argument("--offset", type=int, default=0, help="the first mention of the first wave")
            c.add_argument("--sample", type=int, default=200, help="mentions after the waves, for 6a")
            c.add_argument("--profile", default="who")
            c.add_argument("--fetch", type=int, default=50)
            c.add_argument("--people", type=int, default=32_000)
            c.add_argument("--seed", type=int, default=1)
            c.add_argument("--state", required=True, help="a JSON file the phases are kept in")
            c.add_argument("--resume", action="store_true", help="go on after the last phase kept in --state")
            c.add_argument("--vectors-batch", type=int, default=50, help="the vectors worker's batch")
            c.add_argument("--compare-every", type=int, default=2, help="of the second wave, every Nth asked first")
            c.add_argument("--server-push", type=int, default=1000, help="mentions of the third wave (the server)")
            c.add_argument("--judge-push", type=int, default=100, help="mentions of the fourth wave (the judge)")
        if name == "reports":
            c.add_argument("--profile", default="when")
            c.add_argument("--sample", type=int, default=300)
            c.add_argument("--writes", type=int, default=20)
        if name in ("time", "reports"):
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
    DATED = args.dated or args.command in ("time", "reports")
    global STAND_IN
    STAND_IN = bool(getattr(args, "stand_in", False)) or bool(getattr(args, "worker_models", False))
    global TOOLCHAIN
    TOOLCHAIN = bool(getattr(args, "worker_models", False))
    if args.command == "reconcile" and not args.weights:
        args.weights = ["name=1", "graph=1", "name=1,graph=0.1", "name=1,graph=0.25", "name=1,graph=0.5", "name=1,graph=1"]
    if args.command == "write":
        write(args)
        return
    if args.command == "empty":
        empty(args)
        return
    if args.command == "base" and not args.weights:
        args.weights = ["graph=1,class=0.1", "graph=1"]
    commands_by_name = {"reports": reports, "load": load, "recover": recover, "rebuild": rebuild, "base": base, "names": by_name, "time": by_time, "reconcile": reconcile, "learn": learn, "suggest": suggest, "worker": worker}
    asyncio.run(commands_by_name[args.command](args))


main()
