"""What each shape the joined graph has a rule for is stored as, seen (step 0.1 of
implementation_docs/similarity-build-plan.md).

Writes one document of each shape of `pangloss_testing.similar_models` on a scratch Memgraph and prints its nodes
and edges. **It empties the database it is pointed at**: a scratch container, never :7687 (the tests) or :7688 (the
demo).

    docker run -d --name pangloss-memgraph-similar -p 7702:7687 -e MEMGRAPH_USER=test -e MEMGRAPH_PASSWORD=test \
        memgraph/memgraph-mage:3.14.0 --storage-properties-on-edges=true
    uv run python notes/similarity-evaluation/stored_shapes.py [bolt://localhost:7702]
"""

import asyncio
import sys
import typing

import neo4j
import pangloss_core.settings as core_settings
import pydantic
from pangloss_core import BaseSettings
from pangloss_users import current_request_username
from pydantic import AnyHttpUrl

URI = sys.argv[1] if len(sys.argv) > 1 else "bolt://localhost:7702"
AUTH = ("test", "test")
if URI.endswith((":7687", ":7688")):
    sys.exit("Not the tests' database nor the demo's: a scratch one")

# What is not said again for every node and edge
QUIET = {"id", "label", "meta", "head_node_id", "head_node_type", "created_when"}
KINDS = {
    "Document",
    "Entity",
    "ReifiedRelation",
    "ReifiedRelationDocument",
    "Conjunction",
    "SemanticSpace",
    "Embedded",
}


def settings():
    from pangloss_memgraph import MemgraphDatabaseSettings

    Settings = pydantic.create_model(
        "Settings",
        __base__=BaseSettings[MemgraphDatabaseSettings],
        PROJECT_NAME=(str, "Shapes"),
        BACKEND_CORS_ORIGINS=(list[typing.Any], []),
        INSTALLED_APPS=(
            list[str],
            ["pangloss_derived", "pangloss_library", "pangloss_criteria"],
        ),
        STORAGE=(str | None, "pangloss_memgraph:storage"),
        DATABASE=(
            MemgraphDatabaseSettings,
            MemgraphDatabaseSettings(
                DB_URL=URI,
                DB_USERNAME=AUTH[0],
                DB_PASSWORD=AUTH[1],
                DATABASE_NAME="memgraph",
            ),
        ),
        INTERFACE_LANGUAGES=(list[str], []),
        DEFAULT_INTERFACE_LANGUAGE=(str, "en"),
        AUTHJWT_SECRET_KEY=(str, "a secret for scratch work, of a decent length"),
        ENTITY_BASE_URL=(AnyHttpUrl, AnyHttpUrl("http://test.com/")),
    )
    return Settings()


def query(driver, cypher, **params):
    records, _, _ = driver.execute_query(cypher, parameters_=params)
    return [r.data() for r in records]


def short(value):
    text = str(value)
    return text if len(text) < 60 else text[:57] + "..."


def properties(found: dict) -> str:
    kept = {k: short(v) for k, v in sorted(found.items()) if k not in QUIET}
    return "{" + ", ".join(f"{k}: {v}" for k, v in kept.items()) + "}" if kept else ""


def show(driver, title: str, head_id) -> None:
    """The tree of a head: each node (labels, type, properties), and each edge out of a node of the tree"""
    print(f"\n=== {title}")
    nodes = query(
        driver,
        "MATCH (n) WHERE n.id = $id OR n.head_node_id = $id "
        "RETURN n.id AS id, labels(n) AS labels, properties(n) AS p ORDER BY n.id",
        id=str(head_id),
    )
    names = {}
    for n in nodes:
        kind = sorted(KINDS & set(n["labels"]))
        names[n["id"]] = f"{n['p'].get('type')}«{n['p'].get('label', '')}»"
        print(
            f"  NODE {names[n['id']]} kind={kind} labels={sorted(n['labels'])} {properties(n['p'])}"
        )
    edges = query(
        driver,
        "MATCH (a)-[e]->(b) WHERE a.id IN $ids OR b.id IN $ids "
        "RETURN a.id AS a_id, a.type AS at, a.label AS al, type(e) AS field, properties(e) AS p, "
        "       b.id AS b_id, b.type AS bt, b.label AS bl, labels(b) AS b_labels, labels(a) AS a_labels "
        "ORDER BY coalesce(p.reverse, false), a_id, field",
        ids=list(names),
    )
    for e in edges:
        if any(label.startswith("PG") and label != "PGIndexableNode" and label != "PGCitation"
               for label in [*e["a_labels"], *e["b_labels"]]) and not (
            {"PGIndexableNode"} & set(e["a_labels"]) and {"PGIndexableNode"} & set(e["b_labels"])
        ):
            # (records of who did what, pending work, urls: said once, by label)
            other = e["b_labels"] if e["a_id"] in names else e["a_labels"]
            print(f"  (record) {e['field']} {sorted(other)} {properties(e['p'])}")
            continue
        print(
            f"  EDGE {e['at']}«{e['al'] or ''}» -[{e['field']} {properties(e['p'])}]-> {e['bt']}«{e['bl'] or ''}»"
        )


async def main() -> None:
    driver = neo4j.GraphDatabase.driver(URI, auth=AUTH)
    driver.verify_connectivity()
    query(driver, "MATCH (n) DETACH DELETE n")
    current_request_username.set("shapes")
    query(driver, "MERGE (:PGUser {username: 'shapes'})")

    made = settings()
    core_settings.configure(made)
    from pangloss_memgraph.databases.memgraph import database as database_module
    from pangloss_memgraph.databases.memgraph import initialise_database

    database = database_module.Database(settings=made)
    database_module.install(database)

    from pangloss_testing.similar_models import declare

    m = declare()
    with database_module.using(database):
        await initialise_database.initialise_database(database)

    from pangloss_criteria import run_pending
    from pangloss_derived.worker import run_pending_derivations

    def ref(item, kind="Person"):
        return {"type": kind, "id": item.id}

    people = {}
    for name in ["Ada", "Ben", "Cy", "Dee", "Eve", "Fay", "Gus", "Parent"]:
        people[name] = await m.Person.Create(label=name).save()
    group = await m.Group.Create(label="The guild").save()
    place = await m.Place.Create(label="York").save()

    # 1. Two wrappers and a share before a person, plain and inside a space
    alternatives = {
        "type": "Identification",
        "target": [
            {
                "type": "WeightedAlternative",
                "alternatives": [
                    {**ref(people["Ben"]), "edge_properties": {"percent": 70}},
                    {**ref(people["Cy"]), "edge_properties": {"percent": 30}},
                ],
            }
        ],
    }
    transfer = {
        "type": "Transfer",
        "label": "Ada gave to Ben or Cy",
        "given_by": ref(people["Ada"]),
        "given_to": alternatives,
    }
    plain = await m.Factoid.Create(label="A gift", statements=[transfer]).save()
    show(driver, "1a. Agent | Identification[WeightedAlternative[Person]]", plain.id)
    denied = await m.Factoid.Create(
        label="No gift",
        statements=[{"type": "Negative", "contents": [transfer]}],
    ).save()
    show(driver, "1b. The same inside a Negative", denied.id)

    # 2-4. A class below a wrapper, a wrapper's own relation, a field that subclasses a parent's
    activity = await m.Factoid.Create(
        label="A meeting",
        statements=[
            {
                "type": "Activity",
                "label": "Ada met Dee and Eve",
                "carried_out_by": ref(people["Ada"]),
                "participants": [
                    {
                        "type": "InRole",
                        "role": "guest",
                        "at": {"type": "Place", "id": place.id},
                        "target": [ref(people["Dee"])],
                    },
                    {
                        "type": "Sworn",
                        "role": "witness",
                        "oath": "on the book",
                        "target": [ref(people["Eve"])],
                    },
                ],
            }
        ],
    ).save()
    show(driver, "2-4. InRole with `at`, Sworn below InRole, carried_out_by", activity.id)

    # 5. A description, evaluated by its worker (who is a member of the guild)
    members = await m.Factoid.Create(
        label="Members",
        statements=[
            {
                "type": "MemberOf",
                "label": f"{name} of the guild",
                "member": ref(people[name]),
                "group": {"type": "Group", "id": group.id},
            }
            for name in ["Fay", "Gus"]
        ],
    ).save()
    described = await m.Factoid.Create(
        label="A gift from a member",
        statements=[
            {
                "type": "Transfer",
                "label": "A member gave to Ada",
                "given_by": {
                    "type": "MatchesCriteria",
                    "wording": "a member of the guild",
                    "criteria": {
                        "type": "Person",
                        "where": {
                            "$incoming": [
                                {
                                    "type": "MemberOf",
                                    "field": "member",
                                    "where": {"group": {"is": str(group.id)}},
                                }
                            ]
                        },
                    },
                },
                "given_to": ref(people["Ada"]),
            }
        ],
    ).save()
    print("\ncriteria worker:", await run_pending())
    show(driver, "5. MatchesCriteria, evaluated", described.id)

    # 6. A citation
    statement_id = (await m.Factoid.get(plain.id)).statements[0].id
    inference = await m.Factoid.Create(
        label="An inference",
        statements=[
            {
                "type": "Inference",
                "label": "So Ada knew Ben or Cy",
                "evidence": [{"type": "Transfer", "id": statement_id}],
            }
        ],
    ).save()
    show(driver, "6. Cites[Statement]", inference.id)

    # 7. A claim of identity (a wrapper that is a document), then the merge
    same = await m.Factoid.Create(
        label="Two names",
        statements=[
            {
                "type": "SameEntity",
                "label": "Dee is Eve",
                "target": [ref(people["Dee"]), ref(people["Eve"])],
            }
        ],
    ).save()
    show(driver, "7a. SameEntity[Person]", same.id)
    # (Cy into Ben is refused: the alternatives of 1a would name one person twice)
    await m.Person.merge(absorb=people["Eve"].id, into=people["Dee"].id)
    show(driver, "7b. Eve, merged into Dee", people["Eve"].id)
    show(driver, "7c. The claim again, after the merge", same.id)
    show(driver, "7d. 2-4 again, after the merge", activity.id)

    # 8. A derived shortcut and a derived document
    for child in ["Fay", "Gus"]:
        await m.Factoid.Create(
            label=f"{child}'s parent",
            statements=[
                {
                    "type": "ChildOf",
                    "label": f"{child}, child of Parent",
                    "child": ref(people[child]),
                    "parent": ref(people["Parent"]),
                }
            ],
        ).save()
    print("\nderived worker:", await run_pending_derivations())
    print("criteria worker:", await run_pending())
    show(driver, "8a. Fay: the shortcut of SameGroup", people["Fay"].id)
    for row in query(
        driver, "MATCH (d:DerivedFactoid) RETURN d.id AS id, labels(d) AS labels"
    ):
        show(driver, "8b. The derived document", row["id"])
    print("\n=== 8c. The nodes of derived edges")
    for row in query(
        driver,
        "MATCH (d:PGDerived) OPTIONAL MATCH (d)-[e]->(x) "
        "RETURN labels(d) AS labels, d.type AS type, collect(type(e) + '->' + coalesce(x.label, '?')) AS out",
    ):
        print(" ", row)

    print("\n=== Every label, and how many nodes have it")
    for row in query(
        driver,
        "MATCH (n) UNWIND labels(n) AS label RETURN label, count(*) AS nodes ORDER BY label",
    ):
        print(f"  {row['label']}: {row['nodes']}")
    print("\n=== Pending work left")
    for row in query(
        driver, "MATCH (p:PGPending) RETURN properties(p) AS p LIMIT 20"
    ):
        print(" ", row["p"])
    await database.close()
    driver.close()
    _ = members


asyncio.run(main())
