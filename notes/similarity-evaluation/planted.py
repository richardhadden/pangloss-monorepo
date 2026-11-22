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

    core_settings.configure(settings(backend, url, apps, extras))
    storage = storage_of()
    storage.setup.create_database(core_settings.SETTINGS)
    await storage.setup.connect()
    from pangloss_testing.similar_models import declare

    declare()
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
    world = planted.world(seed=args.seed, people=args.people)
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
    `Σ w·cos / Σ w` over the parts (what a profile's combined vector gives): 1 is right first. With its kind"""
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
        found.append((int((scores > right).sum()) + 1, mention["kind"]))
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


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    commands = parser.add_subparsers(dest="command", required=True)
    w = commands.add_parser("write")
    w.add_argument("dir")
    w.add_argument("--people", type=int, default=32_000)
    w.add_argument("--seed", type=int, default=1)
    for name in ("empty", "load", "rebuild", "base"):
        c = commands.add_parser(name)
        if name in ("load", "base"):
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
    args = parser.parse_args()
    if args.command == "write":
        write(args)
        return
    if args.command == "empty":
        empty(args)
        return
    if args.command == "base" and not args.weights:
        args.weights = ["graph=1,class=0.1", "graph=1"]
    asyncio.run({"load": load, "rebuild": rebuild, "base": base}[args.command](args))


main()
