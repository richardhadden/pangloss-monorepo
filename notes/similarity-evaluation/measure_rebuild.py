"""Step 2.5's measurement: one whole `rebuild` (twice: the second also drops the first's generations) and ten
`nearest`, on the scratch Memgraph `pangloss-memgraph-similar` (bolt://localhost:7702, test/test), which is emptied
first. 100,000 heads of five classes made by plain Cypher (the class part reads only id, type and labels).

    cd /Users/rhadden/Development/pangloss-monorepo && uv run python /tmp/vectors_measure/measure_rebuild.py
"""

import asyncio
import random
import sys
import time
import typing
import uuid

import neo4j

URI, AUTH = "bolt://localhost:7702", ("test", "test")
COUNTS = {
    "Person": 40_000,
    "Saint": 10_000,
    "Birth": 20_000,
    "CreationOfPainting": 20_000,
    "CreationOfArtwork": 10_000,
}
LABELS = {
    "Person": "HeadNode:PGIndexableNode:Entity:Person",
    "Saint": "HeadNode:PGIndexableNode:Entity:Person:Saint",
    "Birth": "HeadNode:PGIndexableNode:Document:Event:Birth",
    "CreationOfPainting": "HeadNode:PGIndexableNode:Document:Event:Creation:CreationOfArtwork:CreationOfPainting",
    "CreationOfArtwork": "HeadNode:PGIndexableNode:Document:Event:Creation:CreationOfArtwork",
}


def settings() -> typing.Any:
    from pangloss_core import BaseSettings
    from pangloss_memgraph.databases.memgraph.settings import MemgraphDatabaseSettings
    from pydantic import AnyHttpUrl

    class Settings(BaseSettings[MemgraphDatabaseSettings]):
        PROJECT_NAME: str = "Measure"
        BACKEND_CORS_ORIGINS: list[typing.Any] = []
        INSTALLED_APPS: list[str] = ["measure_models", "pangloss_vectors"]
        STORAGE: str | None = "pangloss_memgraph:storage"
        DATABASE: MemgraphDatabaseSettings = MemgraphDatabaseSettings(
            DB_URL=URI, DB_USERNAME=AUTH[0], DB_PASSWORD=AUTH[1], DATABASE_NAME="memgraph"
        )
        INTERFACE_LANGUAGES: list[str] = ["en"]
        DEFAULT_INTERFACE_LANGUAGE: str = "en"
        AUTHJWT_SECRET_KEY: str = "a secret for the measurement, of a decent length"
        ENTITY_BASE_URL: AnyHttpUrl = AnyHttpUrl("http://example.com/")

    return Settings()


def empty(driver: neo4j.Driver) -> None:
    with driver.session() as s:
        for r in s.run("SHOW VECTOR INDEX INFO").data():
            s.run(f"DROP VECTOR INDEX {r['index_name']}").consume()
        while True:
            n = s.run("MATCH (n) WITH n LIMIT 50000 DETACH DELETE n RETURN count(*) AS n").single()["n"]
            if not n:
                break
        s.run("FREE MEMORY").consume()


def fill(driver: neo4j.Driver) -> dict[str, list[str]]:
    ids: dict[str, list[str]] = {}
    with driver.session() as s:
        for type_name, count in COUNTS.items():
            ids[type_name] = [str(uuid.uuid4()) for _ in range(count)]
            for start in range(0, count, 20_000):
                s.run(
                    f"UNWIND $rows AS row CREATE (:{LABELS[type_name]} {{id: row.id, type: $type, label: row.label}})",
                    rows=[
                        {"id": i, "label": f"{type_name} {start + n}"}
                        for n, i in enumerate(ids[type_name][start : start + 20_000])
                    ],
                    type=type_name,
                ).consume()
    return ids


class Timed:
    """Seconds spent in some functions of the store, while a rebuild runs"""

    def __init__(self) -> None:
        self.seconds: dict[str, float] = {}

    def wrap(self, module, name: str) -> None:
        original = getattr(module, name)

        async def timed(*args, **kwargs):
            began = time.perf_counter()
            try:
                return await original(*args, **kwargs)
            finally:
                self.seconds[name] = self.seconds.get(name, 0) + time.perf_counter() - began

        setattr(module, name, timed)


async def main() -> None:
    sys.path.insert(0, "/tmp/vectors_measure")
    import pangloss_core.settings as core_settings

    core_settings.configure(settings())
    from pangloss_core import storage_of

    storage = storage_of()
    storage.setup.create_database(core_settings.SETTINGS)
    await storage.setup.connect()
    driver = neo4j.GraphDatabase.driver(URI, auth=AUTH)

    began = time.perf_counter()
    empty(driver)
    print(f"emptied in {time.perf_counter() - began:.1f} s")

    import measure_models  # noqa: F401
    from pangloss_models import initialise

    initialise()
    print("structure:", len(await storage.setup.setup_database()), "entries")
    # (what the migrations of pangloss_vectors and of the project would make: the plain indexes of the vectors'
    # nodes, and the vector indexes of the profile and of the group Person)
    from pangloss_cypher.migrations import apply_changes
    from pangloss_memgraph.databases.memgraph.database import current
    from pangloss_models.migrations import changes as c
    from pangloss_models.migrations.files import EMPTY_SNAPSHOT
    from pangloss_vectors import structure

    entries = [*structure.INDEXES, *structure.indexes()]
    await apply_changes(
        current(),
        EMPTY_SNAPSHOT,
        [c.AddIndex(index={k: v for k, v in e.items() if k != "app"}) for e in entries],
    )
    print("indexes of the vectors made:", ", ".join(e.get("name") or f"{e['label']}({e['properties'][0]})" for e in entries))
    with driver.session() as s:
        plan = s.run(
            "EXPLAIN UNWIND $rows AS row MERGE (v:PGVector {of: row.of, part: $part, generation: $generation}) "
            "SET v.type = row.type, v.vector = row.vector",
            rows=[], part="class", generation=1,
        ).value()
        print("plan of the write of a part's vectors:", " / ".join(line.strip() for line in plan))

    began = time.perf_counter()
    ids = fill(driver)
    print(f"made {sum(COUNTS.values()):,} heads ({', '.join(f'{k} {v:,}' for k, v in COUNTS.items())}) "
          f"in {time.perf_counter() - began:.1f} s")
    with driver.session() as s:
        print("nodes in the database:", s.run("MATCH (n) RETURN count(n) AS n").single()["n"])

    from pangloss_vectors import nearest, store
    from pangloss_vectors.class_part import PART
    from pangloss_vectors import rebuild as rebuild_module

    print("class part: dimension", PART.dimension())
    for run_number in (1, 2):
        timed = Timed()
        names = ("write_generation", "combine", "switch", "drop_older", "drop_older_profile")
        originals = {name: getattr(store, name) for name in names}
        for name in names:
            timed.wrap(store, name)
        began = time.perf_counter()
        done = await rebuild_module.rebuild()
        whole = time.perf_counter() - began
        for name, original in originals.items():
            setattr(store, name, original)
        print(f"\nrebuild {run_number}: {whole:.1f} s in all")
        for p in done.parts:
            print(f"  part {p.part}: generation {p.generation}, {p.count:,} vectors, {p.seconds:.1f} s "
                  f"(of it dropping {p.dropped:,} older)")
        for p in done.profiles:
            print(f"  profile {p.profile}: generation {p.generation}, {p.count:,} vectors, {p.seconds:.1f} s "
                  f"(of it dropping {p.dropped:,} older)")
        for name, seconds in timed.seconds.items():
            print(f"  in store.{name}: {seconds:.1f} s")
        part_reading = whole - sum(timed.seconds.values())
        print(f"  else (the class part reading the heads, the lease, states): {part_reading:.1f} s")

    random.seed(5)
    everything = [i for group in ids.values() for i in group]
    for group in (None, "Person"):
        times = []
        sizes = []
        for of in random.sample(everything, 10):
            began = time.perf_counter()
            found = await nearest(of, group=group, k=10)
            times.append(time.perf_counter() - began)
            sizes.append(len(found.hits))
            assert found.status == "ok", found
        times.sort()
        print(f"\nnearest, k=10, group={group}: ten calls, median {times[5] * 1000:.0f} ms, "
              f"fastest {times[0] * 1000:.0f} ms, slowest {times[-1] * 1000:.0f} ms; hits {sorted(set(sizes))}")

    driver.close()
    await storage.setup.disconnect()


asyncio.run(main())
