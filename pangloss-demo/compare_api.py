"""Time as many kinds of request as possible against the API of a project on Memgraph and on Neo4j (docs/backend-comparison.md).

    PYTHONPATH=pangloss-demo uv run python pangloss-demo/compare_api.py memgraph|neo4j [--entities 20000] [--factoids 6000] [--out FILE]

The real application (`create_app()`, with its lifespan, its middleware, authentication and the history recorder) is called in
this process through httpx, so a request is timed from the client to the client: the routes, the models' views, the backend's
Cypher. The installed apps are the demo's models, users, history, review, calendar, typology and dates; the backend is the only
thing that changes. Each backend runs in a fresh Docker container of its own (`--cpus`, `--memory`), removed at the end.

A request that does not answer 2xx is reported with its status, not timed.
"""

import argparse
import asyncio
import datetime
import importlib
import json
import logging
import random
import statistics
import subprocess
import tempfile
import time
import typing
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from pathlib import Path

import httpx2 as httpx
import neo4j as neo4j_driver
import pangloss_core.settings as core_settings
import pydantic
from pangloss_api.app import create_app
from pangloss_core.settings import BaseSettings
from pangloss_models.migrations.files import EMPTY_SNAPSHOT, load
from pangloss_models.model_bases.document import Document
from pangloss_models.model_bases.entity import Entity
from pangloss_testing.live import apply_changes
from pangloss_users import current_request_username, service as users
from pydantic import AnyHttpUrl

parser = argparse.ArgumentParser()
parser.add_argument("backend", choices=["memgraph", "neo4j"])
parser.add_argument("part", choices=["core", "extras"], help="core: the demo models, search, history, review; extras: dates, calendar, typology (the demo's Date is not theirs: two processes)")
parser.add_argument("--entities", type=int, default=20000)
parser.add_argument("--factoids", type=int, default=6000)
parser.add_argument("--events", type=int, default=3000)
parser.add_argument("--posts", type=int, default=1500)
parser.add_argument("--types", type=int, default=600)
parser.add_argument("--repeat", type=int, default=7)
parser.add_argument("--concurrency", type=int, default=4)
parser.add_argument("--cpus", default="4")
parser.add_argument("--memory", default="6g")
parser.add_argument("--neo4j-heap", default="2g")
parser.add_argument("--neo4j-pagecache", default="1g")
parser.add_argument("--out")
args = parser.parse_args()

CONFIG = {
    "memgraph": dict(
        module="pangloss_memgraph.databases.memgraph",
        app="pangloss_memgraph",
        settings="MemgraphDatabaseSettings",
        image="memgraph/memgraph-mage:3.14.0",
        port=7697,
        auth=("test", "test"),
        database="memgraph",
        env=["-e", "MEMGRAPH_USER=test", "-e", "MEMGRAPH_PASSWORD=test"],
        command=["--log-level=WARNING", "--storage-properties-on-edges=true",
                 "--experimental-enabled=commit-lock-narrowing"],
    ),
    "neo4j": dict(
        module="pangloss_neo4j.databases.neo4j",
        app="pangloss_neo4j",
        settings="Neo4jDatabaseSettings",
        image="neo4j:2026.10.1",
        port=7698,
        auth=("neo4j", "test-password"),
        database="neo4j",
        env=["-e", "NEO4J_AUTH=neo4j/test-password",
             "-e", f"NEO4J_server_memory_heap_initial__size={args.neo4j_heap}",
             "-e", f"NEO4J_server_memory_heap_max__size={args.neo4j_heap}",
             "-e", f"NEO4J_server_memory_pagecache_size={args.neo4j_pagecache}"],
        command=[],
    ),
}[args.backend]  # fmt: skip
NAME = f"pangloss-compare-api-{args.backend}-{args.part}"
PASSWORD = "a password for the comparison"
rng = random.Random(1)


# ---------------------------------------------------------------------------
# The models that are not the demo's
# ---------------------------------------------------------------------------


if args.part == "core":
    from demo_app import models as demo
    from pangloss_review.meta import ReviewMeta

    class Memo(Document):
        """(a document that is reviewed: the demo's are not)"""

        _review_meta = ReviewMeta(reviewable=True)

else:
    from pangloss_dates import julian
    from pangloss_dates import models as date_models
    from pangloss_dates.calendar import Calendar
    from pangloss_models.model_registry import ModelRegistry

    # (as the live tests do: the date models are registered afresh, so that the abstract `JulianDate` is the union of its kinds)
    from pangloss_calendar import models as calendar_models

    ModelRegistry._reset()
    for module in (date_models, julian, calendar_models):
        importlib.reload(module)
    from pangloss_calendar import graph as calendar_graph
    from pangloss_calendar.models import DateCharacterisation
    from pangloss_typology import Typed, Typology, TypologyMeta

    class RoleTypology(Typology):
        _typology_meta = TypologyMeta(name="RoleType", languages=["de"])

    class Post(Entity):
        has_type: list[Typed[RoleTypology]]

    class FeastDay(DateCharacterisation):
        pass

    # (no documents with dates: `Event.Create(when={"type": "JulianExactDate", ...})` is refused outside the live tests' set-up, which
    # I did not get to the bottom of, so a day has its characterisations and no hits)


# ---------------------------------------------------------------------------
# Container, timing
# ---------------------------------------------------------------------------


def start_container() -> None:
    subprocess.run(["docker", "rm", "-f", NAME], capture_output=True)
    subprocess.run(
        ["docker", "run", "-d", "--name", NAME, "--cpus", args.cpus, "--memory", args.memory,
         "-p", f"{CONFIG['port']}:7687", *CONFIG["env"], CONFIG["image"], *CONFIG["command"]],
        check=True, capture_output=True,
    )  # fmt: skip
    deadline = time.time() + 180
    while True:
        try:
            driver = neo4j_driver.GraphDatabase.driver(uri(), auth=CONFIG["auth"])
            driver.verify_connectivity()
            driver.close()
            return
        except Exception:
            if time.time() > deadline:
                raise
            time.sleep(1)


def stop_container() -> None:
    subprocess.run(["docker", "rm", "-f", NAME], capture_output=True)


def uri() -> str:
    return f"bolt://localhost:{CONFIG['port']}"


def milliseconds(since: float) -> float:
    return (time.perf_counter() - since) * 1000


def summary(samples: list[float]) -> dict[str, float]:
    ordered = sorted(samples)
    return {
        "n": len(ordered),
        "median_ms": round(statistics.median(ordered), 1),
        "p95_ms": round(ordered[min(len(ordered) - 1, int(len(ordered) * 0.95))], 1),
    }


async def concurrently(jobs: list[Callable[[], Awaitable]], concurrency: int):
    semaphore = asyncio.Semaphore(concurrency)
    results: list = [None] * len(jobs)

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
    return demo.Person.Create(
        label=label, known_as={"value": f"Known {label}", "certainty": 3}, born=date(800), aliases=[]
    )


def exact(year, month=None, day=None):
    return {"type": "JulianExactDate", "year": year, "month": month, "day": day}


def yearly(**rule):
    return {
        "type": "Recurrence", "calendar": "julian", "frequency": "yearly", "weekdays": [], "excluded_days": [],
        "start": {"type": "ExactDate", "calendar": "julian", "year": 1450},
        "end": {"type": "ExactDate", "calendar": "julian", "year": 1530, "month": 12, "day": 31},
        **rule,
    }  # fmt: skip


# ---------------------------------------------------------------------------
# Requests
# ---------------------------------------------------------------------------


@dataclass
class Case:
    group: str
    name: str
    make: Callable[[], dict]  # (method, url, and the rest of what httpx takes): made before it is timed
    repeat: int = 0
    expect: tuple[int, ...] = (200, 201, 204)


@dataclass
class Report:
    rows: dict[str, dict] = field(default_factory=dict)


async def run_cases(client: httpx.AsyncClient, cases: list[Case], report: Report) -> None:
    for case in cases:
        key = f"{case.group}: {case.name}"
        samples: list[float] = []
        status = None
        failure = None
        try:
            for i in range(-1, case.repeat or args.repeat):  # (the first, a warm-up)
                request = case.make()
                if hasattr(request, "__await__"):
                    request = await request
                method, url = request.pop("method"), request.pop("url")
                start = time.perf_counter()
                response = await client.request(method, url, **request)
                took = milliseconds(start)
                status = response.status_code
                if status not in case.expect:
                    failure = f"{status} {response.text[:100]}"
                    break
                if i >= 0:
                    samples.append(took)
        except Exception as error:  # noqa: BLE001
            failure = f"{type(error).__name__}: {error}"[:140]
        if failure or not samples:
            report.rows[key] = {"error": failure or "no samples"}
            print(f"  {key}: FAILED {failure}", flush=True)
        else:
            report.rows[key] = {**summary(samples), "status": status}
            print(f"  {key}: {report.rows[key]}", flush=True)


async def main() -> dict:
    settings_type = getattr(importlib.import_module(f"{CONFIG['module']}.settings"), CONFIG["settings"])
    apps = {
        "core": [CONFIG["app"], "demo_app", "pangloss_users", "pangloss_history", "pangloss_review"],
        "extras": [CONFIG["app"], "pangloss_users", "pangloss_dates", "pangloss_calendar", "pangloss_typology"],
    }[args.part]
    history = Path(tempfile.mkdtemp()) / "history.sqlite"
    Settings = pydantic.create_model(
        "Settings",
        __base__=BaseSettings[settings_type],
        PROJECT_NAME=(str, "Compare"),
        BACKEND_CORS_ORIGINS=(list[typing.Any], []),
        INSTALLED_APPS=(list[str], apps),
        DATABASE_MODULE=(str, CONFIG["module"]),
        DATABASE=(settings_type, settings_type(DB_URL=uri(), DB_USERNAME=CONFIG["auth"][0],
                                               DB_PASSWORD=CONFIG["auth"][1], DATABASE_NAME=CONFIG["database"])),
        INTERFACE_LANGUAGES=(list[str], ["en"]),
        DEFAULT_INTERFACE_LANGUAGES=(str, "en"),
        AUTHJWT_SECRET_KEY=(str, "a secret for the comparison, of a decent length"),
        ENTITY_BASE_URL=(AnyHttpUrl, AnyHttpUrl("http://compare.test/entity/")),
        MIGRATION_CHECK=(str, "off"),
        HISTORY_DB_PATH=(str, str(history)),
        CALENDAR_FIRST_YEAR=(int, 1450),
        CALENDAR_LAST_YEAR=(int, 1530),
        CALENDAR_DEFAULT=(str, "julian"),
    )  # fmt: skip
    settings = Settings()
    core_settings.SETTINGS = settings
    app = create_app()
    logging.disable(logging.INFO)
    report = Report()
    info: dict = {"backend": args.backend, "part": args.part, "load": {}, "scale": vars(args)}

    async with app.router.lifespan_context(app):
        database = importlib.import_module(f"{CONFIG['module']}.database").Database.default
        await importlib.import_module(f"{CONFIG['module']}.initialise_database").initialise_database(database)
        if args.part == "extras":
            migration = load("pangloss_calendar", "0001_initial")
            await apply_changes(database, EMPTY_SNAPSHOT, list(migration.changes))
        driver = neo4j_driver.GraphDatabase.driver(uri(), auth=CONFIG["auth"])

        await users.create_user("bench", "bench@example.com", PASSWORD, admin=True)
        await users.create_user("reviewer", "reviewer@example.com", PASSWORD, admin=True)
        current_request_username.set("bench")
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://compare.test", timeout=120) as client:
            login = await client.post("/api/users/token", data={"username": "bench", "password": PASSWORD})
            headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
            login = await client.post("/api/users/token", data={"username": "reviewer", "password": PASSWORD})
            reviewer = {"Authorization": f"Bearer {login.json()['access_token']}"}

            # ----------------------------------------------------------- the data
            started = time.perf_counter()
            if args.part == "core":
                print("loading", flush=True)
                n = args.entities
                counts = dict(people=int(n * 0.6), groups=int(n * 0.15), places=int(n * 0.2))
                counts["sources"] = n - sum(counts.values())
                makers = {
                    "people": lambda i: new_person(f"Person {i}").save(),
                    "groups": lambda i: demo.Group.Create(label=f"Group {i}", name=f"Group-{i}").save(),
                    "places": lambda i: demo.Place.Create(label=f"Place {i}", coordinates={
                        "latitude": rng.uniform(-60, 60), "longitude": rng.uniform(-10, 40)}).save(),
                    "sources": lambda i: demo.Source.Create(label=f"Source {i}", author=f"Author {i % 50}",
                                                            written=datetime.date(800 + i % 200, 1, 1)).save(),
                }  # fmt: skip
                created: dict[str, list] = {}
                for kind, count in counts.items():
                    seconds, created[kind] = await concurrently(
                        [(lambda i=i, kind=kind: makers[kind](i)) for i in range(count)], args.concurrency
                    )
                    info["load"][kind] = {"count": count, "per_second": round(count / seconds)}
                agents = created["people"] + created["groups"]
                values = [factoid_values(i, agents, created["places"], created["sources"]) for i in range(args.factoids)]
                seconds, factoids = await concurrently(
                    [(lambda v=v: demo.Factoid.Create(**v).save()) for v in values], args.concurrency
                )
                info["load"]["factoids"] = {"count": args.factoids, "per_second": round(args.factoids / seconds)}
                _, memos = await concurrently(
                    [(lambda i=i: Memo.Create(label=f"Memo {i}").save()) for i in range(300)], args.concurrency
                )
            else:
                # the typology: a tree of types, and posts that have them
                types = []
                for i in range(args.types):
                    parent = rng.choice(types).id if types and rng.random() < 0.85 else None
                    types.append(await RoleTypology.create(f"Type {i}", supertype=parent))
                seconds, posts = await concurrently(
                    [(lambda i=i: Post.Create(label=f"Post {i}", has_type=[{"type": "RoleType", "id": str(rng.choice(types).id)}]).save())
                     for i in range(args.posts)], args.concurrency)  # fmt: skip
                feasts = [await FeastDay.Create(label=f"Feast {i}", use="sarum",
                                                when=yearly(month=rng.randint(1, 12), month_day=rng.randint(1, 28))).save()
                          for i in range(20)]  # fmt: skip
                feasts.append(await FeastDay.Create(label="Pentecost", use="sarum", when=yearly(easter_offset=49)).save())
                await calendar_graph.seed(1450, 1530, Calendar.JULIAN)
            info["load"]["seconds"] = round(time.perf_counter() - started)
            print(f"loaded in {info['load']['seconds']}s", flush=True)

            # ------------------------------------------------- what the requests use
            counter = iter(range(10**9))
            pick = random.Random(2)

            def one(items):
                return pick.choice(items)


            def get(url, **params):
                return lambda: dict(method="GET", url=url() if callable(url) else url, params=params, headers=headers)

            def post_json(url, body):
                return lambda: dict(method="POST", url=url, json=body() if callable(body) else body, headers=headers)

            if args.part == "core":
                place, source = rng.choice(created["places"]), rng.choice(created["sources"])
                async def updatable(model_name, id):
                    """The body to put back with the label changed, and the ETag it is based on"""
                    found = await client.get(f"/api/{model_name}/{id}/edit", headers=headers)
                    body = found.json()
                    return body, found.headers.get("ETag")

                async def put_person():
                    target = one(created["people"])
                    body, tag = await updatable("Person", target.id)
                    body["label"] = f"Renamed {next(counter)}"
                    return dict(method="PUT", url=f"/api/Person/{target.id}", json=body, headers={**headers, "If-Match": tag or "*"})

                async def delete_person():
                    made = await new_person(f"Doomed {next(counter)}").save()
                    return dict(method="DELETE", url=f"/api/Person/{made.id}", headers=headers)

                def create_person():
                    body = new_person(f"Posted {next(counter)}").model_dump(mode="json", by_alias=True)
                    return dict(method="POST", url="/api/Person", json=body, headers=headers)

                def create_factoid():
                    body = demo.Factoid.Create(**factoid_values(10**6 + next(counter), agents, created["places"], created["sources"]))
                    return dict(method="POST", url="/api/Factoid", json=body.model_dump(mode="json", by_alias=True), headers=headers)

                def search(where, type_="Factoid"):
                    return post_json("/api/search", {"type": type_, "where": where, "page": 1, "page_size": 25})

                def person_url():
                    return f"/api/Person/{one(created['people']).id}"

                def factoid_url():
                    return f"/api/Factoid/{one(factoids).id}"

            if args.part == "core":
                cases: list[Case] = [
                    # reading what the models give
                    Case("read", "GET entity (Person)", get(person_url)),
                    Case("read", "GET entity for edit", get(lambda: person_url() + "/edit")),
                    Case("read", "GET document (Factoid, whole)", get(factoid_url)),
                    Case("read", "GET document for edit", get(lambda: factoid_url() + "/edit")),
                        Case("read", "GET missing id (404)", get(f"/api/Person/{'0' * 8}-0000-7000-8000-{'0' * 12}"), expect=(404,)),
                    # lists
                    Case("list", "Person page 1", get("/api/Person")),
                    Case("list", "Person page 100", get("/api/Person", page=100)),
                    Case("list", "Person page_size 100", get("/api/Person", page_size=100)),
                    Case("list", "Factoid page 1", get("/api/Factoid")),
                    Case("list", "Statement (abstract, all kinds)", get("/api/Statement")),
                        Case("list", "Group page 1", get("/api/Group")),
                Case("list", "Place page 1", get("/api/Place")),
                Case("list", "Person published=true", get("/api/Person", published="true")),
                    Case("list", "Person search 'Person 1234'", get("/api/Person", q="Person 1234")),
                    Case("list", "Person search prefix 'Perso'", get("/api/Person", q="Perso")),
                    Case("list", "Person search no hits", get("/api/Person", q="zzzzqq")),
                    Case("list", "Person deep search 'Known 99'", get("/api/Person", q="Known 99", deep="true"), repeat=3),
                    Case("list", "Factoid search 'Factoid 77'", get("/api/Factoid", q="Factoid 77")),
                        # autocomplete
                    Case("autocomplete", "Person 'Pers'", get("/api/autocomplete", q="Pers", type="Person")),
                    Case("autocomplete", "Person 'Person 12'", get("/api/autocomplete", q="Person 12", type="Person")),
                    Case("autocomplete", "Person and Group", get("/api/autocomplete", q="Gro", type=["Person", "Group"])),
                    # structured search
                    Case("search", "Factoid year = 800", search({"year": {"eq": 800}})),
                    Case("search", "Factoid year between", search({"year": {"between": [700, 705]}})),
                    Case("search", "Factoid label = ", search({"label": {"eq": "Factoid 1234"}})),
                    Case("search", "Factoid not year 800", search({"$not": {"year": {"eq": 800}}})),
                    Case("search", "Factoid year = or year =", search({"$any_of": [{"year": {"eq": 800}}, {"year": {"eq": 801}}]})),
                    Case("search", "Factoid source is", search({"source": {"is": str(source.id)}})),
                    Case("search", "Factoid source pattern", search({"source": {"type": "Source", "where": {"author": {"eq": "Author 7"}}}})),
                    Case("search", "Factoid: activity by person", search({"statements": {"type": "Activity", "where": {"carried_out_by": {"is": str(agents[0].id)}}}})),
                    Case("search", "Factoid: statement in a Negative", search({"statements": {"type": "Activity", "where": {"$spaces": ["Negative"]}}})),
                    Case("search", "Factoid mentions person", search({"$mentions": {"is": str(agents[0].id)}})),
                    Case("search", "Factoid mentions place", search({"$mentions": {"is": str(place.id)}})),
                    Case("search", "Factoid somewhere a transfer of silver", search({"$somewhere": [{"type": "Transfer", "where": {"item": {"eq": "silver"}}}]})),
                    Case("search", "Person incoming activity", search({"$incoming": [{"type": "Activity", "field": "carried_out_by"}]}, "Person")),
                    Case("search", "Person incoming statement of year 800", search({"$incoming": [{"type": "Statement", "where": {"year": {"eq": 800}}}]}, "Person")),
                    Case("search", "Person label contains", search({"label": {"contains": "person 4242"}}, "Person")),
                    Case("search", "Person: all", search({}, "Person")),
                    # writes
                    Case("write", "POST entity (Person)", create_person),
                    Case("write", "POST document (Factoid, 3 statements)", create_factoid),
                    Case("write", "PUT entity (rename)", put_person),
                    Case("write", "DELETE entity", delete_person),
                    # typology
                    # calendar
                    # users
                    Case("users", "GET /me", get("/api/users/me")),
                    Case("users", "GET users", get("/api/users")),
                    Case("users", "POST token (login)", lambda: dict(method="POST", url="/api/users/token", data={"username": "bench", "password": PASSWORD}), repeat=3),
                    Case("users", "POST access token", lambda: dict(method="POST", url="/api/users/me/tokens", json={"name": f"t{next(counter)}"}, headers=headers), expect=(200, 201)),
                    Case("users", "GET access tokens", get("/api/users/me/tokens")),
                ]
            else:
                cases = [
                    Case("typology", "GET tree (600 types)", get("/api/typology/RoleType/tree")),
                    Case("typology", "GET type with its entities", get(lambda: f"/api/typology/RoleType/{one(types).id}")),
                    Case("typology", "GET type path", get(lambda: f"/api/typology/RoleType/{one(types).id}/path")),
                    Case("typology", "PATCH type label", lambda: dict(method="PATCH", url=f"/api/typology/RoleType/{one(types).id}", json={"label": f"Type {next(counter)}"}, headers=headers)),
                    Case("typology", "list RoleType (entity route)", get("/api/RoleType")),
                Case("list", "Post search", get("/api/Post", q="Post 12")),
                    Case("calendar", "GET day", get("/api/calendar/day/J1500-03-02")),
                    Case("calendar", "GET day (another calendar)", get("/api/calendar/day/G1500-03-12", calendar="gregorian")),
                    Case("calendar", "GET month", get("/api/calendar/month/julian/1500/3")),
                    Case("calendar", "GET year", get("/api/calendar/year/julian/1500")),
                    Case("calendar", "GET easter", get("/api/calendar/easter/julian/1500")),
                    Case("calendar", "GET characterisations", get("/api/calendar/characterisations")),
                    Case("calendar", "GET days of a characterisation", get(lambda: f"/api/calendar/characterisations/{one(feasts).id}/days", **{"from": "J1500-01-01", "to": "J1500-12-31"})),
                    Case("calendar", "POST attach", lambda: dict(method="POST", url="/api/calendar/attach", json={"characterisation": str(one(feasts).id), "day": f"J1500-0{pick.randint(1, 9)}-{pick.randint(10, 28)}"}, headers=headers)),
                        Case("users", "GET /me", get("/api/users/me")),
                    Case("users", "GET users", get("/api/users")),
                    Case("users", "POST token (login)", lambda: dict(method="POST", url="/api/users/token", data={"username": "bench", "password": PASSWORD}), repeat=3),
                    Case("users", "POST access token", lambda: dict(method="POST", url="/api/users/me/tokens", json={"name": f"t{next(counter)}"}, headers=headers), expect=(200, 201)),
                    Case("users", "GET access tokens", get("/api/users/me/tokens")),
                ]
            await run_cases(client, cases, report)
            if args.part == "core":
                # history: the recorder is asynchronous; change a person twice, then read its history
                target = one(created["people"])
                for name in ("one", "two"):
                    body, tag = await updatable("Person", target.id)
                    body["label"] = f"History {name}"
                    await client.put(f"/api/Person/{target.id}", json=body, headers={**headers, "If-Match": tag or "*"})
                await asyncio.sleep(4)
                history_cases = [
                    Case("history", "GET versions", get(f"/api/Person/{target.id}/history")),
                    Case("history", "GET a version", get(f"/api/Person/{target.id}/history/1")),
                    Case("history", "GET a draft", get(f"/api/Person/{target.id}/history/1/draft")),
                    Case("history", "GET a diff", get(f"/api/Person/{target.id}/history/1/diff")),
                    Case("history", "POST restore", lambda: dict(method="POST", url=f"/api/Person/{target.id}/history/1/restore", headers={**headers, "If-Match": "*"}), repeat=3),
                ]
                await run_cases(client, history_cases, report)

                # review
                target = one(memos)
                review_cases = [
                    Case("review", "GET queue", get("/api/review/queue")),
                    Case("review", "GET queue (a status, a type)", get("/api/review/queue", status="checked", type="Factoid")),
                    Case("review", "GET detail", get(f"/api/review/{target.id}")),
                    Case("review", "POST comment", lambda: dict(method="POST", url=f"/api/review/{target.id}/comments", json={"text": f"c{next(counter)}"}, headers=headers), expect=(200, 201)),
                    Case("review", "POST status (by another user)", lambda: dict(method="POST", url=f"/api/review/{target.id}/status", json={"status": "checked"}, headers=reviewer)),
                ]
                await run_cases(client, review_cases, report)

            # ------------------------------------------------------ concurrency
            print("concurrent (8 at once)", flush=True)
            concurrent: dict[str, dict] = {}

            async def burst(label, count, make):
                async def one_request():
                    request = make()
                    if hasattr(request, "__await__"):
                        request = await request
                    method, url = request.pop("method"), request.pop("url")
                    response = await client.request(method, url, **request)
                    return response.status_code

                seconds, statuses = await concurrently([one_request] * count, 8)
                ok = sum(1 for s in statuses if s < 300)
                concurrent[label] = {"requests": count, "ok": ok, "seconds": round(seconds, 2), "per_second": round(count / seconds)}
                print(f"  {label}: {concurrent[label]}", flush=True)

            if args.part == "core":
                await burst("GET Person x 600", 600, lambda: get(person_url)())
                await burst("GET Factoid x 300", 300, lambda: get(factoid_url)())
                await burst("GET list Person?q= x 200", 200, lambda: get("/api/Person", q=f"Person {pick.randint(1, 9999)}")())
                await burst("autocomplete x 300", 300, lambda: get("/api/autocomplete", q=f"Pers{pick.randint(1, 99)}", type="Person")())
                await burst("POST search (year) x 150", 150, lambda: search({"year": {"eq": pick.randint(700, 900)}})())
                await burst("POST Person x 300", 300, create_person)
                await burst("PUT Person x 150", 150, put_person)
                await burst("mixed (80% reads, 20% writes) x 400", 400, lambda: create_person() if pick.random() < 0.2 else get(person_url)())
            else:
                await burst("GET calendar day x 200", 200, lambda: get(f"/api/calendar/day/J1500-0{pick.randint(1, 9)}-{pick.randint(10, 28)}")())
                await burst("GET typology type x 200", 200, lambda: get(lambda: f"/api/typology/RoleType/{one(types).id}")())
        driver.close()

    return {**info, "requests": report.rows, "concurrent": concurrent}


if __name__ == "__main__":
    start_container()
    try:
        output = asyncio.run(main())
    finally:
        stop_container()
    text = json.dumps(output)
    print("RESULT " + text)
    if args.out:
        Path(args.out).write_text(text)
