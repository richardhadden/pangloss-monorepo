"""What the live tests of the graph part share: a document of every shape of `pangloss_testing.similar_models` written
(the payloads of `notes/similarity-evaluation/stored_shapes.py`, copied), the graph vectors stored and the oracle's,
the indexes of the models and of the vectors made as a project's migrations would make them, and the plan of a query"""

from typing import Any, no_type_check

import numpy as np
from pangloss_cypher.migrations import apply_changes
from pangloss_models.indexes import model_indexes
from pangloss_models.migrations import changes as c
from pangloss_models.migrations.files import EMPTY_SNAPSHOT
from pangloss_testing.backends import under_test
from pangloss_testing.live import run
from pangloss_testing.under_test.database import current
from pangloss_vectors import VectorRow, meta, store, structure
from pangloss_vectors.parts import profiles

from pangloss_fastrp.cypher_reader import load_all
from pangloss_fastrp.maps import graph_maps
from pangloss_fastrp.testing import oracle

NAMES = ["Ada", "Ben", "Cy", "Dee", "Eve", "Fay", "Gus", "Parent"]


def ref(item: Any, kind: str = "Person") -> dict[str, Any]:
    return {"type": kind, "id": item.id}


def alternatives(ben: Any, cy: Any) -> dict[str, Any]:
    """Ben at 70%, Cy at 30%, through an identification"""
    return {
        "type": "Identification",
        "target": [
            {
                "type": "WeightedAlternative",
                "alternatives": [
                    {**ref(ben), "edge_properties": {"percent": 70}},
                    {**ref(cy), "edge_properties": {"percent": 30}},
                ],
            }
        ],
    }


def transfer(people: dict[str, Any]) -> dict[str, Any]:
    return {
        "type": "Transfer",
        "label": "Ada gave to Ben or Cy",
        "given_by": ref(people["Ada"]),
        "given_to": alternatives(people["Ben"], people["Cy"]),
    }


def meeting(people: dict[str, Any], place: Any) -> dict[str, Any]:
    return {
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


def described(people: dict[str, Any], group: Any) -> dict[str, Any]:
    """A transfer from someone described: a member of the group"""
    return {
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


@no_type_check
async def write_shapes(m, db_driver, published: bool | None = None) -> dict[str, str]:
    """A document of every shape, the criteria and derived workers run after: the ids by name (the people by theirs;
    `group`, `place`; the factoids `gift`, `no gift`, `meeting`, `members`, `member gift`, `inference`, `two names`,
    `Fay's parent`, `Gus's parent`; the statements in them `transfer`, `denied`, `activity`, `fay member`,
    `gus member`, `member transfer`, `inference statement`, `same`; the derived `siblings` and its `sibling`).
    `published`: given to each factoid's `save` (with `declare(reviewed=True)`)"""
    from pangloss_criteria import run_pending
    from pangloss_derived.worker import run_pending_derivations

    saved = {} if published is None else {"published": published}
    ids: dict[str, str] = {}
    people = {}
    for name in NAMES:
        people[name] = await m.Person.Create(label=name).save()
        ids[name] = str(people[name].id)
    group = await m.Group.Create(label="The guild").save()
    place = await m.Place.Create(label="York").save()
    ids |= {"group": str(group.id), "place": str(place.id)}

    async def factoid(name: str, statements: list) -> Any:
        made = await m.Factoid.Create(label=name, statements=statements).save(**saved)
        ids[name] = str(made.id)
        return await m.Factoid.get(made.id)

    gift = await factoid("gift", [transfer(people)])
    ids["transfer"] = str(gift.statements[0].id)
    denied = await factoid(
        "no gift", [{"type": "Negative", "contents": [transfer(people)]}]
    )
    ids["denied"] = str(denied.statements[0].contents[0].id)
    met = await factoid("meeting", [meeting(people, place)])
    ids["activity"] = str(met.statements[0].id)
    members = await factoid(
        "members",
        [
            {
                "type": "MemberOf",
                "label": f"{name} of the guild",
                "member": ref(people[name]),
                "group": ref(group, "Group"),
            }
            for name in ["Fay", "Gus"]
        ],
    )
    ids["fay member"] = str(members.statements[0].id)
    ids["gus member"] = str(members.statements[1].id)
    gave = await factoid("member gift", [described(people, group)])
    ids["member transfer"] = str(gave.statements[0].id)
    inference = await factoid(
        "inference",
        [
            {
                "type": "Inference",
                "label": "So Ada knew Ben or Cy",
                "evidence": [{"type": "Transfer", "id": ids["transfer"]}],
            }
        ],
    )
    ids["inference statement"] = str(inference.statements[0].id)
    same = await factoid(
        "two names",
        [
            {
                "type": "SameEntity",
                "label": "Dee is Eve",
                "target": [ref(people["Dee"]), ref(people["Eve"])],
            }
        ],
    )
    ids["same"] = str(same.statements[0].id)
    for child in ["Fay", "Gus"]:
        made = await factoid(
            f"{child}'s parent",
            [
                {
                    "type": "ChildOf",
                    "label": f"{child}, child of Parent",
                    "child": ref(people[child]),
                    "parent": ref(people["Parent"]),
                }
            ],
        )
        ids[f"{child} child"] = str(made.statements[0].id)
    await run_pending()
    await run_pending_derivations()
    await run_pending()
    for row in run(
        db_driver,
        "MATCH (d:DerivedFactoid)-[:statements]->(s) RETURN d.id AS id, s.id AS sibling",
    ):
        ids["siblings"], ids["sibling"] = row["id"], row["sibling"]
    return ids


# ---------------------------------------------------------------------------
# Vectors
# ---------------------------------------------------------------------------


async def stored(db_driver) -> dict[str, list[float]]:
    """The graph vectors in use, by item"""
    found = await store.states()
    state = found.parts.get("graph")
    if state is None:
        return {}
    return {
        row["of"]: row["vector"]
        for row in run(
            db_driver,
            "MATCH (v:PGVector {part: 'graph', generation: $generation}) RETURN v.of AS of, v.vector AS vector",
            generation=state.generation,
        )
    }


async def fresh_oracle() -> dict[str, np.ndarray]:
    """What a whole rebuild would give now"""
    graph = graph_maps()
    return oracle(await load_all(graph), graph)


def differences(
    have: dict[str, list[float]], want: dict[str, np.ndarray], tolerance: float = 1e-5
) -> list[str]:
    """What differs between stored vectors and the oracle's, in words (empty if nothing)"""
    found = []
    for of in sorted(set(have) - set(want)):
        found.append(f"{of}: stored, and the oracle has none")
    for of in sorted(set(want) - set(have)):
        found.append(f"{of}: the oracle has one, and none is stored")
    for of in sorted(set(have) & set(want)):
        gap = float(np.max(np.abs(np.asarray(have[of]) - want[of])))
        if gap > tolerance:
            found.append(f"{of}: differs by {gap:.2e}")
    return found


async def set_in_use(rows) -> None:
    """The writer of a refresh: the vectors in use, in place"""
    await store.set_vectors("graph", list(rows))


def rows_of(vectors: dict[str, Any], types: dict[str, str]) -> list[VectorRow]:
    return [
        VectorRow(of, types[of], [float(x) for x in vector])
        for of, vector in sorted(vectors.items())
    ]


# ---------------------------------------------------------------------------
# Indexes, as the migrations make them (the database is emptied between tests; its indexes are not)
# ---------------------------------------------------------------------------


def _index_names(db_driver) -> list[str]:
    # (not in a transaction: Memgraph refuses its list in one)
    with db_driver.session(database=under_test().database) as session:
        if under_test().name == "neo4j":
            rows = session.run(
                "SHOW INDEXES YIELD name, type WHERE type = 'VECTOR' RETURN name"
            ).data()
            return [r["name"] for r in rows]
        return [r["index_name"] for r in session.run("SHOW VECTOR INDEX INFO").data()]


def drop_vector_indexes(db_driver) -> None:
    """The tests' own vector indexes dropped (as `pangloss-vectors`' live tests do), and on Memgraph the deleted
    nodes collected (it keeps them in a vector index)"""
    with db_driver.session(database=under_test().database) as session:
        for name in _index_names(db_driver):
            if name.startswith("pgv_"):
                drop = (
                    f"DROP INDEX {name} IF EXISTS"
                    if under_test().name == "neo4j"
                    else f"DROP VECTOR INDEX {name}"
                )
                session.run(drop).consume()
        if under_test().name == "memgraph":
            session.run("FREE MEMORY").consume()


async def make_vector_indexes() -> list[str]:
    """The vector index of each profile, and of each profile and group, as the project's migrations would make
    them (`pangloss-vectors`' `vectors_live_support.make_vector_indexes`)"""
    entries = []
    for name, weights in profiles().items():
        if not weights:
            continue
        lay = store.layout(name, weights)
        entries.append(
            structure.vector_entry(lay.index_name, lay.label, lay.dimension, "test")
        )
        for group in meta.groups():
            entries.append(
                structure.vector_entry(
                    lay.group_index_name(group),
                    lay.group_label(group),
                    lay.dimension,
                    "test",
                )
            )
    await apply_changes(
        current(),
        EMPTY_SNAPSHOT,
        [
            c.AddIndex(index={k: v for k, v in entry.items() if k != "app"})
            for entry in entries
        ],
    )
    return [entry["name"] for entry in entries]


async def make_model_indexes(db_driver) -> None:
    """The indexes of the registered models (a label of each class, `PGCitation(target_id)` and the like), as the
    migrations make them; those there already are left"""
    there = existing_indexes(db_driver)
    wanted = [
        entry
        for entry in model_indexes()
        if (entry["label"], tuple(entry["properties"])) not in there
    ]
    if wanted:
        await apply_changes(
            current(), EMPTY_SNAPSHOT, [c.AddIndex(index=entry) for entry in wanted]
        )


def existing_indexes(db_driver) -> set[tuple[str, tuple[str, ...]]]:
    with db_driver.session(database=under_test().database) as session:
        if under_test().name == "neo4j":
            rows = session.run(
                "SHOW INDEXES YIELD labelsOrTypes, properties, entityType "
                "WHERE entityType = 'NODE' RETURN labelsOrTypes AS labels, properties"
            ).data()
            return {
                (row["labels"][0], tuple(row["properties"] or ()))
                for row in rows
                if row["labels"]
            }
        rows = session.run("SHOW INDEX INFO").data()
        found = set()
        for row in rows:
            properties = row.get("property")
            if isinstance(properties, str):
                properties = [properties]
            found.add((row.get("label"), tuple(properties or ())))
        return found


# ---------------------------------------------------------------------------
# Plans
# ---------------------------------------------------------------------------


def plan_of(db_driver, query: str, **parameters: Any) -> list[str]:
    """The operators of the plan of a query (`EXPLAIN`), each with what it says of itself, from the top"""
    with db_driver.session(database=under_test().database) as session:
        if under_test().name == "neo4j":
            plan = session.run("EXPLAIN " + query, **parameters).consume().plan
            found: list[str] = []

            def walk(step: dict, depth: int) -> None:
                arguments = step.get("args") or step.get("arguments") or {}
                details = arguments.get("Details", "")
                found.append(
                    f"{'  ' * depth}{step.get('operatorType', step.get('operator_type'))} {details}".rstrip()
                )
                for child in step.get("children", []):
                    walk(child, depth + 1)

            walk(plan, 0)
            return found
        rows = session.run("EXPLAIN " + query, **parameters).data()
        return [list(row.values())[0] for row in rows]


# Operators that read every node, or every node of a label
SCANS = {
    "memgraph": {"ScanAll", "ScanAllByLabel"},
    "neo4j": {"AllNodesScan", "NodeByLabelScan"},
}


def operator(step: str) -> str:
    """The name of a step's operator (Memgraph's `| * Expand (n)-[e]->(m)`, Neo4j's `NodeIndexSeek@neo4j ...`)"""
    words = step.replace("|", " ").replace("*", " ").split()
    return words[0].split("@")[0] if words else ""


def scans_in(plan: list[str]) -> list[str]:
    """The steps of a plan that scan all nodes, or a label"""
    bad = SCANS[under_test().name]
    return [step for step in plan if operator(step) in bad]
