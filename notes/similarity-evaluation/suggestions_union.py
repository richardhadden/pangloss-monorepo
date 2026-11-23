"""Step 10.5a, measured first: review's queries over the suggestions when they are of two classes.

`IdentificationByToolchainFromText` is a second class of suggestion in every project with the library, so review's
list (`pangloss_review.graph.suggestions`), its count (`task_counts`) and its read by id (`suggestions_by_id`) go
from the plain match of one label to the union of two (`_match_suggestions`, `has_a_label`). This asks what that
costs, on synthetic nodes of the stored shape and of the size `large-data.md` measured review at (145,000 heads,
12,000 suggestions, 24,000 other parts), with the query text review writes.

    uv run python notes/similarity-evaluation/suggestions_union.py memgraph bolt://localhost:7708 test test
    uv run python notes/similarity-evaluation/suggestions_union.py neo4j bolt://localhost:7709 neo4j scratch-pass

The database is emptied first: a scratch container only.
"""

import statistics
import sys
import time
import uuid

from neo4j import GraphDatabase

HEADS = 145_000
DOCUMENTS = 40_000
SUGGESTIONS = 12_000
OTHER_PARTS = 24_000
ONE = "IdentificationByToolchain"
TWO = "IdentificationByToolchainFromText"
RUNS = 7

VISIBLE = "NOT coalesce(head.deleted, false) AND ($see_unpublished OR coalesce(head.published, true))"
ASSIGNED = (
    "($assigned_to IS NULL OR coalesce(head.review_assigned_to, '') = $assigned_to)"
)
FIELDS = """{
    id: pair[0].id, type: pair[0].type, identified_by: pair[0].identified_by,
    toolchain_version: pair[0].toolchain_version, uris: coalesce(pair[0].uris, []),
    head_id: pair[1].id, head_type: pair[1].type, head_label: pair[1].label,
    assigned_to: pair[1].review_assigned_to
}"""


def match(labels: list[str], node: str) -> str:
    """As `pangloss_review.graph._match_suggestions`"""
    if len(labels) == 1:
        return f"MATCH ({node}:{labels[0]})"
    union = " UNION ALL ".join(
        f"MATCH ({node}:{label}) RETURN {node}" for label in labels
    )
    return f"CALL {{ {union} }}"


def is_one(labels: list[str], node: str) -> str:
    """As `pangloss_review.graph.has_a_label`"""
    if len(labels) == 1:
        return f"{node}:{labels[0]}"
    names = ", ".join(f"'{label}'" for label in labels)
    return f"any(label IN labels({node}) WHERE label IN [{names}])"


def page(labels: list[str]) -> str:
    return f"""
        {match(labels, "i")}
        WITH i
        MATCH (head:HeadNode {{id: i.head_node_id}})
        WHERE {VISIBLE} AND {ASSIGNED}
        WITH i, head
        ORDER BY i.id
        WITH collect([i, head]) AS found
        RETURN size(found) AS count, [pair IN found[$start .. $end] | {FIELDS}] AS results
    """


def count(labels: list[str]) -> str:
    return f"""
        {match(labels, "part")}
        WITH part
        MATCH (head:HeadNode {{id: part.head_node_id}})
        WHERE {VISIBLE} AND {ASSIGNED}
        RETURN count(part) AS count
    """


def by_id(labels: list[str]) -> str:
    return f"""
        UNWIND $ids AS id
        MATCH (i:PGIndexableNode {{id: id}})
        WHERE {is_one(labels, "i")}
        WITH i
        MATCH (head:HeadNode {{id: i.head_node_id}})
        WHERE {VISIBLE}
        RETURN i.id AS id, head.id AS head
    """


def load(session, kind: str, split: bool) -> list[str]:
    session.run("MATCH (n) DETACH DELETE n").consume()
    if kind == "memgraph":
        ddl = [
            "CREATE INDEX ON :HeadNode(id)",
            "CREATE INDEX ON :PGIndexableNode(id)",
            f"CREATE INDEX ON :{ONE}",
            f"CREATE INDEX ON :{TWO}",
        ]
    else:
        ddl = [
            "CREATE INDEX head_id IF NOT EXISTS FOR (n:HeadNode) ON (n.id)",
            "CREATE INDEX part_id IF NOT EXISTS FOR (n:PGIndexableNode) ON (n.id)",
        ]
    for statement in ddl:
        try:
            session.run(statement).consume()
        except Exception as error:  # (an index that is there already)
            print("  ", statement, "->", type(error).__name__)
    heads = [str(uuid.uuid7()) for _ in range(HEADS)]
    for start in range(0, HEADS, 20_000):
        session.run(
            """
            UNWIND $rows AS row
            CREATE (:HeadNode:PGIndexableNode {id: row.id, type: 'Factoid', label: row.label,
                                               published: row.published})
            """,
            rows=[
                {"id": id, "label": f"Head {n}", "published": n % 3 != 0}
                for n, id in enumerate(heads[start : start + 20_000], start)
            ],
        ).consume()
    documents = heads[:DOCUMENTS]
    suggestions = [str(uuid.uuid7()) for _ in range(SUGGESTIONS)]
    rows = [
        {
            "id": id,
            "head": documents[n % DOCUMENTS],
            "second": split and n % 2 == 1,
        }
        for n, id in enumerate(suggestions)
    ]
    for label, chosen in (
        (ONE, [row for row in rows if not row["second"]]),
        (TWO, [row for row in rows if row["second"]]),
    ):
        session.run(
            f"""
            UNWIND $rows AS row
            CREATE (:{label}:ReifiedRelation:PGIndexableNode {{
                id: row.id, type: '{label}', head_node_id: row.head, identified_by: 'toolchain',
                toolchain_version: '1', uris: []}})
            """,
            rows=chosen,
        ).consume()
    session.run(
        """
        UNWIND $rows AS row
        CREATE (:Unreconciled:PGIndexableNode {id: row.id, type: 'Unreconciled', head_node_id: row.head})
        """,
        rows=[
            {"id": str(uuid.uuid7()), "head": documents[n % DOCUMENTS]}
            for n in range(OTHER_PARTS)
        ],
    ).consume()
    if kind == "neo4j":
        # (a plan made before the indexes are sampled does not use them: 47 s and more for the page)
        session.run("CALL db.awaitIndexes(300)").consume()
        session.run("CALL db.resampleOutdatedIndexes()").consume()
        session.run("CALL db.clearQueryCaches()").consume()
        time.sleep(5)
    return suggestions


def timed(session, query: str, **params) -> tuple[float, int]:
    taken = []
    rows = 0
    for _ in range(RUNS):
        began = time.perf_counter()
        records = list(session.run(query, **params))
        taken.append((time.perf_counter() - began) * 1000)
        rows = records[0]["count"] if records and "count" in records[0].keys() else len(records)
    return statistics.median(taken[1:]), rows


def main() -> None:
    kind, uri, user, password = sys.argv[1:5]
    driver = GraphDatabase.driver(uri, auth=(user, password))
    print(f"{kind}: {HEADS:,} heads, {SUGGESTIONS:,} suggestions, {OTHER_PARTS:,} other parts")
    print("(medians of six runs after the first, in ms; the count or the rows found in brackets)")
    with driver.session() as session:
        for split in (False, True):
            suggestions = load(session, kind, split)
            ids = suggestions[100:150]
            said = "two classes, half each" if split else "one class"
            for name, labels in (("one label", [ONE]), ("two labels", [ONE, TWO])):
                if split and len(labels) == 1:
                    continue
                params = {"see_unpublished": True, "assigned_to": None}
                a, n = timed(session, page(labels), start=0, end=25, **params)
                b, m = timed(session, count(labels), **params)
                c, k = timed(session, by_id(labels), ids=ids, see_unpublished=True)
                print(
                    f"  stored as {said}; asked by {name}: a page {a:.1f} [{n}], "
                    f"the count {b:.1f} [{m}], 50 by id {c:.1f} [{k}]"
                )
    driver.close()


if __name__ == "__main__":
    main()
