"""Load a large synthetic dataset into the demo project, to try how Pangloss behaves at size.

    python bulk_load.py [entities] [factoids] [concurrency]     # (from this directory)

Defaults: 100,000 entities (60% people, 15% groups, 20% places, 5% sources) and 30,000 factoids with
2 or 3 statements each, written four at a time. Needs a set-up database and a user called `demo`
(`pangloss users create`). **Point the demo's settings at a database you can throw away**: it is
not made to be run twice (the entities have fixed URLs). See docs/large-data.md.
"""

import asyncio
import datetime
import random
import sys
import time

from demo_app import models
from pangloss_cli.project import load_project
from pangloss_models import initialise
from pangloss_users import current_request_username

N_ENTITIES = int(sys.argv[1]) if len(sys.argv) > 1 else 100_000
N_FACTOIDS = int(sys.argv[2]) if len(sys.argv) > 2 else 30_000
CONCURRENCY = int(sys.argv[3]) if len(sys.argv) > 3 else 4
rng = random.Random(1)


def date(year, precision="day"):
    return {
        "when": datetime.date(year, rng.randint(1, 12), rng.randint(1, 28)),
        "precision": precision,
    }


async def run(jobs, label):
    """Run coroutine factories with bounded concurrency; return results in order"""
    sem = asyncio.Semaphore(CONCURRENCY)
    results = [None] * len(jobs)
    done = 0
    start = time.perf_counter()

    async def one(i, job):
        nonlocal done
        async with sem:
            results[i] = await job()
        done += 1
        if done % 5000 == 0:
            rate = done / (time.perf_counter() - start)
            print(f"  {label}: {done}/{len(jobs)}  ({rate:.0f}/s)", flush=True)

    await asyncio.gather(*(one(i, j) for i, j in enumerate(jobs)))
    print(f"{label}: {len(jobs)} in {time.perf_counter() - start:.1f}s", flush=True)
    return results


def person(i):
    return lambda: models.Person.Create(
        id=f"https://example.org/smoke/person/{i}",
        create_new=True,
        label=f"Person {i}",
        known_as={"value": f"Known {i}", "certainty": rng.randint(1, 5)},
        born=date(rng.randint(600, 900), "year"),
        aliases=[f"alias {i}a", f"alias {i}b"][: rng.randint(0, 2)],
    ).save()


def group(i):
    return lambda: models.Group.Create(label=f"Group {i}", name=f"Group-{i}").save()


def place(i):
    return lambda: models.Place.Create(
        label=f"Place {i}",
        coordinates={
            "latitude": rng.uniform(-60, 60),
            "longitude": rng.uniform(-10, 40),
        },
    ).save()


def source(i):
    return lambda: models.Source.Create(
        id=f"https://example.org/smoke/source/{i}",
        create_new=True,
        label=f"Source {i}",
        author=f"Author {i % 50}",
        written=datetime.date(800 + i % 200, 1, 1),
    ).save()


def ref(e):
    return {"type": e.type, "id": e.id}


def statement(agents, places, year, n):
    a = rng.choice(agents)
    common = dict(
        label=f"Statement {n}",
        text=f"Something happened, number {n}",
        date=date(year),
        places=[ref(rng.choice(places))],
    )
    if rng.random() < 0.7:
        return dict(
            type="Activity",
            activity_type=rng.choice(
                ["meeting", "journey", "battle", "ceremony", "correspondence"]
            ),
            carried_out_by={**ref(a), "edge_properties": {"level": rng.randint(1, 5)}},
            participants=[
                {
                    "type": "InRole",
                    "role": rng.choice(["leader", "witness", "participant"]),
                    "target": [ref(rng.choice(agents))],
                }
                for _ in range(rng.randint(0, 2))
            ],
            **common,
        )
    return dict(
        type="Transfer",
        item="silver",
        quantity=str(rng.randint(1, 100)),
        given_by=ref(a),
        given_to=ref(rng.choice(agents)),
        **common,
    )


def factoid(i, agents, places, sources):
    year = rng.randint(700, 900)
    n = i * 10
    statements = []
    for k in range(rng.randint(2, 3)):
        s = statement(agents, places, year, n + k)
        roll = rng.random()
        if roll < 0.08:
            statements.append({"type": "Negative", "contents": [s]})
        elif roll < 0.15:
            statements.append({"type": "Hypothetical", "contents": [s]})
        elif roll < 0.2:
            statements.append(
                {
                    "type": "Causes",
                    "cause": s,
                    "result": statement(agents, places, year, n + 5 + k),
                }
            )
        else:
            statements.append(s)
    return lambda: models.Factoid.Create(
        label=f"Factoid {i}",
        year=year,
        source={
            "type": "AtPage",
            "page": f"p. {i % 400}",
            "target": [ref(rng.choice(sources))],
        },
        statements=statements,
    ).save()


async def main():
    project = load_project()
    backend = project.require_database()
    project.import_models()
    initialise()
    current_request_username.set("demo")
    await backend.connect()
    try:
        t0 = time.perf_counter()
        n_people = int(N_ENTITIES * 0.6)
        n_groups = int(N_ENTITIES * 0.15)
        n_places = int(N_ENTITIES * 0.2)
        n_sources = N_ENTITIES - n_people - n_groups - n_places
        people = await run([person(i) for i in range(n_people)], "people")
        groups = await run([group(i) for i in range(n_groups)], "groups")
        places = await run([place(i) for i in range(n_places)], "places")
        sources = await run([source(i) for i in range(n_sources)], "sources")
        agents = people + groups
        print(f"entities done in {time.perf_counter() - t0:.0f}s", flush=True)
        await run(
            [factoid(i, agents, places, sources) for i in range(N_FACTOIDS)], "factoids"
        )
        print(f"total {time.perf_counter() - t0:.0f}s")
    finally:
        await backend.disconnect()


asyncio.run(main())
