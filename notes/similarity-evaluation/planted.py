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
BASE_APPS = ["pangloss_derived", "pangloss_library", "pangloss_criteria"]
VECTOR_APPS = ["pangloss_vectors", "pangloss_fastrp", "pangloss_names", "pangloss_dates_vectors"]


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
    declare(dated=DATED, stand_in=STAND_IN)
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


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    commands = parser.add_subparsers(dest="command", required=True)
    w = commands.add_parser("write")
    w.add_argument("dir")
    w.add_argument("--people", type=int, default=32_000)
    w.add_argument("--seed", type=int, default=1)
    w.add_argument("--dated", action="store_true")
    for name in ("empty", "load", "recover", "rebuild", "base", "names", "time", "reports", "reconcile", "learn", "suggest"):
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
    STAND_IN = bool(getattr(args, "stand_in", False))
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
    commands_by_name = {"reports": reports, "load": load, "recover": recover, "rebuild": rebuild, "base": base, "names": by_name, "time": by_time, "reconcile": reconcile, "learn": learn, "suggest": suggest}
    asyncio.run(commands_by_name[args.command](args))


main()
