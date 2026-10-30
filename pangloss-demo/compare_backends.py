"""Time the same workload on Memgraph and on Neo4j, through the models of the demo (see docs/backend-comparison.md).

    python compare_backends.py memgraph [--entities 6000] [--factoids 2000] [--repeat 5]
    python compare_backends.py neo4j    [same]

Each run starts a scratch container of its own (fresh, with the same limits: `--cpus`, `--memory`), loads the data, times
the operations, and prints one JSON line of results (`--out FILE` also writes it). The container is removed at the end.
The ports (7695, 7696) are not those of the tests.
"""

import argparse
import asyncio
import datetime
import json
import random
import statistics
import subprocess
import sys
import time
import typing

import neo4j as neo4j_driver
import pangloss_core.settings as core_settings
import pydantic
from demo_app import models
from pangloss_core.settings import BaseSettings
from pangloss_models import initialise
from pangloss_users import current_request_username
from pydantic import AnyHttpUrl

parser = argparse.ArgumentParser()
parser.add_argument("backend", choices=["memgraph", "neo4j"])
parser.add_argument("--entities", type=int, default=6000)
parser.add_argument("--factoids", type=int, default=2000)
parser.add_argument("--repeat", type=int, default=5)
parser.add_argument("--concurrency", type=int, default=4)
parser.add_argument("--cpus", default="4")
parser.add_argument("--memory", default="4g")
parser.add_argument("--neo4j-heap", default="2g")
parser.add_argument("--neo4j-pagecache", default="1g")
parser.add_argument("--out")
args = parser.parse_args()

CONFIG = {
    "memgraph": dict(
        module="pangloss_memgraph.databases.memgraph",
        settings="MemgraphDatabaseSettings",
        image="memgraph/memgraph-mage:3.14.0",
        port=7695,
        auth=("test", "test"),
        database="memgraph",
        env=["-e", "MEMGRAPH_USER=test", "-e", "MEMGRAPH_PASSWORD=test"],
        command=[
            "--log-level=WARNING",
            "--storage-properties-on-edges=true",
            "--experimental-enabled=commit-lock-narrowing",
        ],
    ),
    "neo4j": dict(
        module="pangloss_neo4j.databases.neo4j",
        settings="Neo4jDatabaseSettings",
        image="neo4j:2026.10.1",
        port=7696,
        auth=("neo4j", "test-password"),
        database="neo4j",
        # (Neo4j's heap is sized by itself, and 100,000 entities and 30,000 factoids ran it out of memory in 4g:
        # so, a heap and a page cache of our own, `--neo4j-heap` and `--neo4j-pagecache`)
        env=["-e", "NEO4J_AUTH=neo4j/test-password",
             "-e", f"NEO4J_server_memory_heap_initial__size={args.neo4j_heap}",
             "-e", f"NEO4J_server_memory_heap_max__size={args.neo4j_heap}",
             "-e", f"NEO4J_server_memory_pagecache_size={args.neo4j_pagecache}"],
        command=[],
    ),
}[args.backend]

NAME = f"pangloss-compare-{args.backend}"
rng = random.Random(1)


def start_container() -> None:
    subprocess.run(["docker", "rm", "-f", NAME], capture_output=True)
    subprocess.run(
        ["docker", "run", "-d", "--name", NAME, "--cpus", args.cpus, "--memory", args.memory,
         "-p", f"{CONFIG['port']}:7687", *CONFIG["env"], CONFIG["image"], *CONFIG["command"]],
        check=True, capture_output=True,
    )  # fmt: skip
    uri = f"bolt://localhost:{CONFIG['port']}"
    deadline = time.time() + 180
    while True:
        try:
            driver = neo4j_driver.GraphDatabase.driver(uri, auth=CONFIG["auth"])
            driver.verify_connectivity()
            driver.close()
            return
        except Exception:
            if time.time() > deadline:
                raise
            time.sleep(1)


def stop_container() -> None:
    subprocess.run(["docker", "rm", "-f", NAME], capture_output=True)


def milliseconds(since: float) -> float:
    return (time.perf_counter() - since) * 1000


def summary(samples: list[float]) -> dict[str, float]:
    ordered = sorted(samples)
    return {
        "n": len(ordered),
        "median_ms": round(statistics.median(ordered), 2),
        "p95_ms": round(ordered[min(len(ordered) - 1, int(len(ordered) * 0.95))], 2),
        "min_ms": round(ordered[0], 2),
    }


async def timed(label: str, make, repeat: int, results: dict) -> None:
    """Run `make()` (a coroutine) `repeat` times, one at a time, recording each"""
    samples = []
    try:
        await make()  # (a warm-up)
        for _ in range(repeat):
            start = time.perf_counter()
            await make()
            samples.append(milliseconds(start))
    except Exception as error:  # (a search that is too slow at size: the timeout)
        results["serial"][label] = {"error": f"{type(error).__name__}: {error}"[:120]}
        print(f"  {label}: FAILED {results['serial'][label]}", flush=True)
        return
    results["serial"][label] = summary(samples)
    print(f"  {label}: {results['serial'][label]}", flush=True)


async def concurrently(jobs, concurrency: int) -> float:
    """Run the coroutine factories `concurrency` at a time; the seconds taken"""
    semaphore = asyncio.Semaphore(concurrency)
    results = [None] * len(jobs)

    async def one(i, job):
        async with semaphore:
            results[i] = await job()

    start = time.perf_counter()
    await asyncio.gather(*(one(i, j) for i, j in enumerate(jobs)))
    return time.perf_counter() - start, results


def date(year):
    return {"when": datetime.date(year, rng.randint(1, 12), rng.randint(1, 28)), "precision": "day"}


def ref(e):
    return {"type": e.type, "id": e.id}


def statement(agents, places, year, n):
    agent = rng.choice(agents)
    common = dict(label=f"Statement {n}", text=f"Something happened, number {n}", date=date(year),
                  places=[ref(rng.choice(places))])  # fmt: skip
    if rng.random() < 0.7:
        return dict(
            type="Activity",
            activity_type=rng.choice(["meeting", "journey", "battle", "ceremony", "correspondence"]),
            carried_out_by={**ref(agent), "edge_properties": {"level": rng.randint(1, 5)}},
            participants=[{"type": "InRole", "role": rng.choice(["leader", "witness", "participant"]),
                           "target": [ref(rng.choice(agents))]} for _ in range(rng.randint(0, 2))],
            **common,
        )  # fmt: skip
    return dict(type="Transfer", item="silver", quantity=str(rng.randint(1, 100)),
                given_by=ref(agent), given_to=ref(rng.choice(agents)), **common)  # fmt: skip


def factoid_values(i, agents, places, sources):
    year = rng.randint(700, 900)
    statements = []
    for k in range(rng.randint(2, 3)):
        s = statement(agents, places, year, i * 10 + k)
        roll = rng.random()
        if roll < 0.1:
            statements.append({"type": "Negative", "contents": [s]})
        elif roll < 0.2:
            statements.append({"type": "Causes", "cause": s, "result": statement(agents, places, year, i * 10 + 5 + k)})
        else:
            statements.append(s)
    return dict(
        label=f"Factoid {i}", year=year, statements=statements,
        source={"type": "AtPage", "page": f"p. {i % 400}", "target": [ref(rng.choice(sources))]},
    )  # fmt: skip


def new_person(label):
    return models.Person.Create(
        label=label, known_as={"value": f"Known {label}", "certainty": 3}, born=date(800), aliases=[]
    ).save()


async def main() -> dict:
    uri = f"bolt://localhost:{CONFIG['port']}"
    module = __import__(CONFIG["module"], fromlist=["settings"])  # noqa: F841
    import importlib

    def backend_module(name):
        return importlib.import_module(f"{CONFIG['module']}.{name}")

    settings_type = getattr(backend_module("settings"), CONFIG["settings"])
    Settings = pydantic.create_model(
        "Settings",
        __base__=BaseSettings[settings_type],
        PROJECT_NAME=(str, "Compare"),
        BACKEND_CORS_ORIGINS=(list[typing.Any], []),
        INSTALLED_APPS=(list[str], []),
        DATABASE_MODULE=(str, CONFIG["module"]),
        DATABASE=(settings_type, settings_type(DB_URL=uri, DB_USERNAME=CONFIG["auth"][0],
                                               DB_PASSWORD=CONFIG["auth"][1], DATABASE_NAME=CONFIG["database"])),
        INTERFACE_LANGUAGES=(list[str], []),
        DEFAULT_INTERFACE_LANGUAGES=(str, "en"),
        AUTHJWT_SECRET_KEY=(str, "a secret for the comparison, of a decent length"),
        ENTITY_BASE_URL=(AnyHttpUrl, AnyHttpUrl("http://compare.test/")),
    )  # fmt: skip
    settings = Settings()
    core_settings.SETTINGS = settings
    database = backend_module("database").Database(settings=settings)
    await database._initialise_driver()
    await backend_module("initialise_database").initialise_database(database)
    initialise()
    current_request_username.set("compare")
    driver = neo4j_driver.GraphDatabase.driver(uri, auth=CONFIG["auth"])
    driver.execute_query("MERGE (:PGUser {username: 'compare'})", database_=CONFIG["database"])

    results: dict = {"backend": args.backend, "entities": args.entities, "factoids": args.factoids,
                     "serial": {}, "concurrent": {}, "load": {}}  # fmt: skip
    n = args.entities
    counts = dict(people=int(n * 0.6), groups=int(n * 0.15), places=int(n * 0.2))
    counts["sources"] = n - sum(counts.values())

    print("loading", flush=True)
    makers = {
        "people": lambda i: models.Person.Create(
            label=f"Person {i}", known_as={"value": f"Known {i}", "certainty": rng.randint(1, 5)},
            born=date(rng.randint(600, 900)), aliases=[f"alias {i}a"],
        ).save(),
        "groups": lambda i: models.Group.Create(label=f"Group {i}", name=f"Group-{i}").save(),
        "places": lambda i: models.Place.Create(
            label=f"Place {i}",
            coordinates={"latitude": rng.uniform(-60, 60), "longitude": rng.uniform(-10, 40)},
        ).save(),
        "sources": lambda i: models.Source.Create(label=f"Source {i}", author=f"Author {i % 50}",
                                                  written=datetime.date(800 + i % 200, 1, 1)).save(),
    }  # fmt: skip
    created: dict[str, list] = {}
    for kind, count in counts.items():
        seconds, created[kind] = await concurrently(
            [(lambda i=i, kind=kind: makers[kind](i)) for i in range(count)], args.concurrency
        )
        results["load"][kind] = {"count": count, "seconds": round(seconds, 2), "per_second": round(count / seconds)}
        print(f"  {kind}: {count} in {seconds:.1f}s ({count / seconds:.0f}/s)", flush=True)
    agents = created["people"] + created["groups"]
    values = [factoid_values(i, agents, created["places"], created["sources"]) for i in range(args.factoids)]
    seconds, factoids = await concurrently(
        [(lambda v=v: models.Factoid.Create(**v).save()) for v in values], args.concurrency
    )
    results["load"]["factoids"] = {"count": args.factoids, "seconds": round(seconds, 2),
                                   "per_second": round(args.factoids / seconds)}  # fmt: skip
    print(f"  factoids: {args.factoids} in {seconds:.1f}s ({args.factoids / seconds:.0f}/s)", flush=True)

    r = args.repeat
    pick = random.Random(2)
    people, facts = created["people"], factoids

    print("serial operations", flush=True)
    counter = iter(range(10**9))
    await timed("create a person", lambda: new_person(f"New {next(counter)}"), r * 4, results)
    await timed("create a factoid (3 statements)",
                lambda: models.Factoid.Create(**factoid_values(next(counter), agents, created["places"], created["sources"])).save(),
                r * 2, results)  # fmt: skip
    await timed("get a person", lambda: models.Person.get(id=pick.choice(people).id), r * 8, results)
    await timed("get a factoid (whole document)", lambda: models.Factoid.get(id=pick.choice(facts).id), r * 4, results)
    await timed("get a person for edit", lambda: models.Person.get_for_edit(pick.choice(people).id), r * 4, results)
    await timed("list people, page 1", lambda: models.Person.list(), r * 2, results)
    await timed("list people, page 20", lambda: models.Person.list(page_number=20), r * 2, results)
    await timed("list statements (all kinds)", lambda: models.Statement.list(), r * 2, results)
    await timed("search people: 'Person 1234'", lambda: models.Person.list("Person 1234"), r * 4, results)
    await timed("search people: 'Perso' (prefix, many hits)", lambda: models.Person.list("Perso"), r * 2, results)
    await timed("search factoids: 'Factoid 77'", lambda: models.Factoid.list("Factoid 77"), r * 4, results)
    await timed("search groups: 'Group 99'", lambda: models.Group.list("Group 99"), r * 2, results)

    print("concurrent reads (8 at once)", flush=True)
    ids = [pick.choice(facts).id for _ in range(400)]
    seconds, _ = await concurrently([(lambda i=i: models.Factoid.get(id=i)) for i in ids], 8)
    results["concurrent"]["400 factoid gets, 8 at once"] = {"seconds": round(seconds, 2), "per_second": round(400 / seconds)}
    pids = [pick.choice(people).id for _ in range(1000)]
    seconds, _ = await concurrently([(lambda i=i: models.Person.get(id=i)) for i in pids], 8)
    results["concurrent"]["1000 person gets, 8 at once"] = {"seconds": round(seconds, 2), "per_second": round(1000 / seconds)}
    seconds, _ = await concurrently([(lambda k=k: models.Person.list(f"Person {k}")) for k in range(200)], 8)
    results["concurrent"]["200 searches, 8 at once"] = {"seconds": round(seconds, 2), "per_second": round(200 / seconds)}
    seconds, _ = await concurrently(
        [(lambda: new_person(f"Burst {next(counter)}")) for _ in range(400)], 8
    )
    results["concurrent"]["400 person creates, 8 at once"] = {"seconds": round(seconds, 2), "per_second": round(400 / seconds)}
    for label, value in results["concurrent"].items():
        print(f"  {label}: {value}", flush=True)

    print("delete", flush=True)
    victims = [pick.choice(facts).id for _ in range(50)]
    start = time.perf_counter()
    for victim in dict.fromkeys(victims):
        await models.Factoid.delete(victim)
    results["serial"]["delete a factoid"] = {"n": len(set(victims)),
                                              "mean_ms": round(milliseconds(start) / len(set(victims)), 2)}  # fmt: skip

    driver.close()
    await database.close()
    return results


if __name__ == "__main__":
    start_container()
    try:
        output = asyncio.run(main())
    finally:
        stop_container()
    text = json.dumps(output)
    print("RESULT " + text)
    if args.out:
        with open(args.out, "w") as handle:
            handle.write(text)
    sys.exit(0)
