"""Time structured searches on a large database, and try indexes (see docs/structured-search.md, step 5).

    python search_benchmark.py [--repeat 3] [--only NAME ...] [--profile] [--timeout 60]
    python search_benchmark.py --indexes label property head edge     # make these indexes first
    python search_benchmark.py --drop-indexes                         # drop what --indexes made

Run it in a copy of this directory whose settings point at a database loaded with `bulk_load.py` (and
**not at one you want to keep**: it makes and drops indexes). Each search is run `--repeat` times
through the models, and the shortest time is printed with the number found; `--profile` also prints
the plan of its query with the hits and time of each step, from Memgraph's `PROFILE`.
"""

import argparse
import asyncio
import time
from typing import Any

import neo4j
from demo_app import models
from pangloss_cli.project import load_project
from pangloss_memgraph.databases.memgraph.build_search_query import build_search_query
from pangloss_models import initialise
from pangloss_models.search import Match, check_match
from pangloss_users import current_request_username

parser = argparse.ArgumentParser()
parser.add_argument("--repeat", type=int, default=3)
parser.add_argument("--only", nargs="*", default=[])
parser.add_argument("--profile", action="store_true")
parser.add_argument("--explain", action="store_true", help="print the plan without running")
parser.add_argument("--timeout", type=int, default=120, help="seconds (a Memgraph setting)")
parser.add_argument("--indexes", nargs="*", default=[])
parser.add_argument("--drop-indexes", action="store_true")
args = parser.parse_args()

CLASS_LABELS = [
    "Person", "Group", "Place", "Source", "Factoid", "Activity", "Transfer", "Statement",
    "Entity", "Document", "Agent",
]  # fmt: skip
FIELD_PROPERTIES = [
    ("Factoid", "year"), ("Statement", "year"), ("Person", "label"), ("Group", "name"),
    ("Source", "author"), ("Factoid", "label"), ("Transfer", "item"),
    ("Activity", "activity_type"),
]  # fmt: skip
EDGE_TYPES = [
    "source", "statements", "carried_out_by", "participants", "involves", "places", "given_by",
    "given_to", "target", "contents", "cause", "result",
]  # fmt: skip

INDEX_SETS = {
    # a node of a class is found without looking at every node
    "label": [f"CREATE INDEX ON :{label}" for label in CLASS_LABELS],
    # the literal fields of a class
    "property": [f"CREATE INDEX ON :{l}({p})" for l, p in FIELD_PROPERTIES],
    # the nodes of a document by the id of the head (`$somewhere`, `$mentions`)
    "head": ["CREATE INDEX ON :PGIndexableNode(head_node_id)"],
    # an edge by its type (what starts from the edges of a relation)
    "edge": [f"CREATE EDGE INDEX ON :{t}" for t in EDGE_TYPES],
}  # fmt: skip


def settings_url():
    project = load_project()
    db = project.settings.DATABASE
    return str(db.DB_URL), (db.DB_USERNAME, db.DB_PASSWORD)


def run_cypher(driver, query, **params):
    with driver.session() as session:
        return [dict(r) for r in session.run(query, **params)]


def indexes_made(driver):
    return [
        r for r in run_cypher(driver, "SHOW INDEX INFO")
        if r["index type"] != "label_text (name: label_text)" or False
    ]  # fmt: skip


def make_indexes(driver, names):
    for name in names:
        for statement in INDEX_SETS[name]:
            start = time.perf_counter()
            try:
                run_cypher(driver, statement)
                print(f"  {statement}  ({time.perf_counter() - start:.1f}s)")
            except Exception as error:  # noqa: BLE001
                print(f"  {statement}  FAILED: {str(error)[:90]}")


def drop_indexes(driver):
    for statements in INDEX_SETS.values():
        for statement in statements:
            drop = statement.replace("CREATE", "DROP")
            try:
                run_cypher(driver, drop)
                print(f"  {drop}")
            except Exception:  # noqa: BLE001
                pass


def sample_ids(driver):
    """A busy person, an ordinary one, a place and a source"""
    busy = run_cypher(
        driver,
        "MATCH (p:Person)<-[:carried_out_by]-() RETURN p.id AS id, count(*) AS c ORDER BY c DESC LIMIT 1",
    )[0]
    ordinary = run_cypher(
        driver, "MATCH (p:Person {label: 'Person 4242'}) RETURN p.id AS id"
    )[0]
    place = run_cypher(driver, "MATCH (p:Place {label: 'Place 777'}) RETURN p.id AS id")[0]
    source = run_cypher(driver, "MATCH (p:Source {label: 'Source 77'}) RETURN p.id AS id")[0]
    print(f"a busy person is referred to by {busy['c']} activities")
    label = run_cypher(driver, "MATCH (p:Person {id: $id}) RETURN p.label AS label", id=busy["id"])[0]
    return busy["id"], ordinary["id"], place["id"], source["id"], label["label"]


def searches(busy, ordinary, place, source, busy_label):
    P, F, E, G, S, A = models.Person, models.Factoid, models.Place, models.Group, models.Source, models.Activity
    activity_of = lambda who: {"statements": {"type": "Activity", "where": {"carried_out_by": {"is": who}}}}  # noqa: E731
    return {
        # entities by a literal
        "person label contains": (P, {"label": {"contains": "person 4242"}}),
        "person label eq": (P, {"label": {"eq": "Person 4242"}}),
        "group name eq": (G, {"name": {"eq": "Group-77"}}),
        "source author eq (100 sources)": (S, {"author": {"eq": "Author 7"}}),
        "person: all": (P, {}),
        # documents by a literal
        "factoid year eq (~150)": (F, {"year": {"eq": 800}}),
        "factoid year between (~1000)": (F, {"year": {"between": [700, 705]}}),
        "factoid label eq": (F, {"label": {"eq": "Factoid 12345"}}),
        "factoid: all": (F, {}),
        "factoid: not year 800": (F, {"$not": {"year": {"eq": 800}}}),
        "factoid year eq or year eq": (F, {"$any_of": [{"year": {"eq": 800}}, {"year": {"eq": 801}}]}),
        # through relations
        "factoid source is": (F, {"source": {"is": source}}),
        "factoid source pattern": (F, {"source": {"type": "Source", "where": {"author": {"eq": "Author 7"}}}}),
        "factoid: an activity by a busy person": (F, activity_of(busy)),
        "factoid: an activity by an ordinary person": (F, activity_of(ordinary)),
        "factoid: statement in a Negative": (F, {"statements": {"type": "Activity", "where": {"$spaces": ["Negative"]}}}),
        "factoid: statements through Negative": (F, {"statements": {"through": ["Negative"]}}),
        # anywhere in the document
        "factoid mentions busy person": (F, {"$mentions": {"is": busy}}),
        "factoid mentions ordinary person": (F, {"$mentions": {"is": ordinary}}),
        "factoid mentions place": (F, {"$mentions": {"is": place}}),
        "factoid mentions a person by pattern": (F, {"$mentions": {"type": "Person", "where": {"label": {"eq": "Person 4242"}}}}),
        "factoid somewhere a transfer": (F, {"$somewhere": [{"type": "Transfer"}]}),
        "factoid somewhere a transfer of silver": (F, {"$somewhere": [{"type": "Transfer", "where": {"item": {"eq": "silver"}}}]}),
        "factoid somewhere a transfer given by busy": (F, {"$somewhere": [{"type": "Transfer", "where": {"given_by": {"is": busy}}}]}),
        # entities by what refers to them
        "person incoming activity, specific": (P, {"label": {"eq": "Person 4242"}, "$incoming": [{"type": "Activity"}]}),
        "hub incoming activity": (P, {"label": {"eq": busy_label}, "$incoming": [{"type": "Activity"}]}),
        "hub incoming activity of year 800": (P, {"label": {"eq": busy_label}, "$incoming": [{"type": "Activity", "where": {"year": {"eq": 800}}}]}),
        "hub incoming transfer (none)": (P, {"label": {"eq": busy_label}, "$incoming": [{"type": "Transfer"}]}),
        "person incoming activity (any person)": (P, {"$incoming": [{"type": "Activity", "field": "carried_out_by"}]}),
        "person incoming statement of year 800": (P, {"$incoming": [{"type": "Statement", "where": {"year": {"eq": 800}}}]}),
        "place incoming statement": (E, {"$incoming": [{"type": "Statement"}]}),
    }  # fmt: skip


def plan(driver, model, where):
    conditions = check_match(model, Match(where=where))  # type: ignore[arg-type]
    query, params = build_search_query(model, conditions, 1, 25)
    with driver.session() as session:
        rows = list(session.run("PROFILE " + query, **params))
    for row in rows:
        print(
            f"      {row['OPERATOR'][:70]:70} hits {row['ACTUAL HITS']:>9}  {row['RELATIVE TIME']:6.1f}%  {row['ABSOLUTE TIME']}"
        )


def explain(driver, model, where):
    conditions = check_match(model, Match(where=where))  # type: ignore[arg-type]
    query, params = build_search_query(model, conditions, 1, 25)
    with driver.session() as session:
        for row in session.run("EXPLAIN " + query, **params):
            print("      " + row["QUERY PLAN"])


async def main():
    url, auth = settings_url()
    driver = neo4j.GraphDatabase.driver(url, auth=auth)
    if args.drop_indexes:
        drop_indexes(driver)
        return
    if args.indexes:
        make_indexes(driver, args.indexes)
    run_cypher(driver, f"SET DATABASE SETTING 'query.timeout' TO '{args.timeout}'")
    project = load_project()
    backend = project.require_database()
    project.import_models()
    initialise()
    current_request_username.set("demo")
    await backend.connect()
    try:
        made = [
            f"{r['label']}({','.join(r['property']) if r['property'] else ''})" if r["index type"].startswith("label") else f"{r['index type']}:{r.get('label')}"
            for r in run_cypher(driver, "SHOW INDEX INFO")
        ]  # fmt: skip
        print("indexes:", len(made))
        ids = sample_ids(driver)
        for name, (model, where) in searches(*ids).items():
            if args.only and not any(o in name for o in args.only):
                continue
            if args.explain:
                print(name)
                explain(driver, model, where)
                continue
            best: float = float("inf")
            found: Any = None
            try:
                for _ in range(args.repeat):
                    start = time.perf_counter()
                    found = await model.search(Match(where=where), page_size=25)
                    took = time.perf_counter() - start
                    best = min(best, took)
                print(f"{name:52} {best * 1000:9.0f} ms   {found.count:>7} found")
            except Exception as error:  # noqa: BLE001
                print(f"{name:52} {'FAILED':>9}     {str(error)[:90]}")
            if args.profile:
                plan(driver, model, where)
    finally:
        await backend.disconnect()


asyncio.run(main())
