"""The Cypher of a `WritePlan` (`write_plan`), for the backend in use (its `dialect()` encodes the properties).

How the plan is stored is said here:

- a head node has the labels `HeadNode` and `PGIndexableNode`, and a record of its creation (`PGCreation`, with an edge
  to the user), or, for an update, of the update (`PGUpdate`);
- a node of a document has `PGIndexableNode`, and is `MERGE`d by its id;
- a relation is a pair of edges for each name it has: forward, and backward marked `{reverse: true}`, with the edge
  properties on both; the forward edges have the place of the value in the field's list, from 0 (`pg_position`), so
  that a list is read in the order it was written;
- a URL of an entity is a node of its own (`PGUrl`, unique), that the entity `has_url`;
- an existing node is matched by its id (or by a URL it has), and must have one of the allowed labels.

A plan is written as **a few statements, each over a list of rows** (`UNWIND $rows`), run one after another in the
write's transaction: the head; the nodes of the document; the entities written in it; their URLs; the edges. Usually
three. What differs from one write to the next is in the parameters: the classes of the nodes are a list in each row,
and the text of the statement for the edges depends only on which relations the write has (a part for each pair of
names: a database cannot take the type of an edge from a row), so the database plans a text once (Memgraph keeps the
plan of a query by its text).

(Until 2026-11-06 a plan was one statement, with a clause for every node and edge. The database's time for such a
statement grows much faster than its length: a document of 160 small nested documents, 2,985 clauses, took 27 seconds
to write, nearly all of it in the database, and one of 200 took 134. As rows, the time is in proportion to the size:
1,000 in a second, and an ordinary document as before. A statement for each set of labels and each pair of names was
tried first, 17 for an ordinary document: as fast for the large ones, but a round trip each, about 0.4 ms.)"""

import dataclasses
import datetime
import typing
import uuid
from collections.abc import Mapping

from pangloss_users import current_request_username

from pangloss_cypher.build_tree import POSITION
from pangloss_cypher.params import QueryParams
from pangloss_cypher.transactions import dialect
from pangloss_cypher.values import convert_type_for_writing
from pangloss_cypher.write_plan import (
    ExistingEntity,
    InlineEntity,
    InlineEntityKey,
    PlannedNode,
    ReferenceToExisting,
    Relation,
    WritePlan,
    plan_create,
)

HEAD_LABELS = ["HeadNode", "PGIndexableNode"]
TREE_LABELS = ["PGIndexableNode"]


class PropertyAssignments:
    """The properties to set on a node or edge, from a single parameter"""

    def __init__(
        self,
        params: QueryParams,
        properties: dict[str, typing.Any],
        *,
        node: bool = True,
    ):
        # (as the backend writes them: Neo4j cannot store a map as a property, and flattens `meta` and annotated values;
        # Memgraph adds the folded label of a node)
        self.identifier = params.add(dialect().encode_properties(properties, node=node))

    def set_items(self, variable: str, replace: bool = False) -> str:
        """What to put after `SET` to give `variable` the properties: replacing
        its properties (`=`), or adding to them (`+=`)"""
        return f"{variable} {'=' if replace else '+='} ${self.identifier}"


def labels_of(node: PlannedNode, extra_labels: list[str]) -> str:
    return ":".join([*node.labels, *extra_labels])


@dataclasses.dataclass
class Statement:
    """One statement of a write. It answers with how many rows it wrote (`written`), which must be `rows`, the number
    it was given: fewer is a node that it was to write to and did not find"""

    text: typing.LiteralString
    params: dict[str, typing.Any]
    rows: int = 1


def encoded(properties: dict[str, typing.Any], *, node: bool = True) -> typing.Any:
    """Properties as they are sent: as the backend stores them, each value of a type the driver takes"""
    return convert_type_for_writing(dialect().encode_properties(properties, node=node))


def new_record(when: str) -> dict[str, typing.Any]:
    """The properties of a record of a creation or an update (`when`: the name of its time)"""
    return convert_type_for_writing(
        {"id": str(uuid.uuid7()), when: datetime.datetime.now(datetime.UTC)}
    )


WRITTEN = "RETURN count(*) AS written"


def head_create_statement(head: PlannedNode, username: str) -> Statement:
    return Statement(
        typing.cast(
            typing.LiteralString,
            f"""
            MATCH (user:PGUser {{username: $username}})
            CREATE (head:{labels_of(head, HEAD_LABELS)})
            SET head = $properties
            CREATE (creation:PGCreation)
            SET creation = $creation
            CREATE (creation)-[:is_creation_of]->(head)
            CREATE (creation)-[:created_by]->(user)
            {WRITTEN}
            """,
        ),
        {
            "username": username,
            "properties": encoded(head.properties),
            "creation": new_record("created_when"),
        },
    )


HEAD_UPDATE = f"""
    MATCH (user:PGUser {{username: $username}})
    MATCH (head:HeadNode {{id: $id}})
    CREATE (update:PGUpdate)
    SET update = $update
    CREATE (update)-[:is_update_of]->(head)
    CREATE (update)-[:updated_by]->(user)
    {WRITTEN}
"""

# $rows: {id, url}
URLS = f"""
    UNWIND $rows AS row
    MATCH (entity:PGIndexableNode {{id: row.id}})
    CREATE (url:PGUrl {{url: row.url}})
    CREATE (entity)-[:has_url]->(url)
    {WRITTEN}
"""


# $rows: {id, labels, properties}: the nodes of the document, of any classes
def tree_nodes_statement(rows: list[dict]) -> Statement:
    return Statement(
        typing.cast(
            typing.LiteralString,
            f"""
            UNWIND $rows AS row
            MERGE (node:{":".join(TREE_LABELS)} {{id: row.id}})
            ON CREATE SET node = row.properties, {dialect().labels_from("node", "row.labels")}
            {WRITTEN}
            """,
        ),
        {"rows": rows},
        len(rows),
    )


# $rows: {labels, properties, creation}. The entities written in the document that were not there: head nodes of
# their own, made by the user who makes the write
def entities_statement(rows: list[dict], username: str) -> Statement:
    return Statement(
        typing.cast(
            typing.LiteralString,
            f"""
            MATCH (user:PGUser {{username: $username}})
            UNWIND $rows AS row
            CREATE (entity:{":".join(HEAD_LABELS)})
            SET entity = row.properties, {dialect().labels_from("entity", "row.labels")}
            CREATE (creation:PGCreation)
            SET creation = row.creation
            CREATE (creation)-[:is_creation_of]->(entity)
            CREATE (creation)-[:created_by]->(user)
            {WRITTEN}
            """,
        ),
        {"rows": rows, "username": username},
        len(rows),
    )


def edge_names(forward: str, backward: str) -> str:
    """What a row of the edges says its edges are called"""
    return f"{forward}/{backward}"


# $rows: {source, target, names, position, properties, allowed}. The forward and reverse edges between two nodes, with any
# edge properties on both (`+=`: `=` would take the `reverse` and the position off them), and the place of the value in
# its list on the forward one. `target` is the id of a node, or (`by_url`) a URL of an entity; `allowed` is the labels
# one of which an existing node must have, or null for a node that this write makes. `names` is the pair of names of
# the row's edges (`edge_names`): the type of an edge cannot come from a row, so there is a part for each pair the write
# has, which makes the edges of the rows that are of it
def edges_statement(
    pairs: list[tuple[str, str]], by_url: bool, rows: list[dict]
) -> Statement:
    target = (
        "(:PGUrl {url: row.target})<-[:has_url]-(target:PGIndexableNode)"
        if by_url
        else "(target:PGIndexableNode {id: row.target})"
    )
    each = "\n".join(
        f"""
            FOREACH (_ IN CASE WHEN row.names = '{edge_names(forward, backward)}' THEN [1] ELSE [] END |
                CREATE (source)-[forward:{forward} {{{POSITION}: row.position}}]->(target)
                CREATE (source)<-[backward:{backward} {{reverse: true}}]-(target)
                SET forward += row.properties
                SET backward += row.properties
            )"""
        for forward, backward in pairs
    )
    return Statement(
        typing.cast(
            typing.LiteralString,
            f"""
            UNWIND $rows AS row
            MATCH (source:PGIndexableNode {{id: row.source}})
            MATCH {target}
            WHERE row.allowed IS NULL OR any(label IN labels(target) WHERE label IN row.allowed)
            {each}
            {WRITTEN}
            """,
        ),
        {"rows": rows},
        len(rows),
    )


class _Renderer:
    """Walks a plan, gathering the rows of each statement"""

    def __init__(self, existing: Mapping[InlineEntityKey, ExistingEntity] | None):
        self.existing = existing or {}
        # The rows of the nodes of the document, of the new entities, and of their URLs
        self.tree_nodes: list[dict] = []
        self.entities: list[dict] = []
        self.url_rows: list[dict] = []
        # The rows of the edges, and the pairs of names among them: those to a node by its id, and those to one found
        # by a URL
        self.edge_rows: dict[bool, list[dict]] = {False: [], True: []}
        self.edge_pairs: dict[bool, set[tuple[str, str]]] = {False: set(), True: set()}
        # The ids of the entities written in the document, so that one that is written twice is one
        self.inline_entity_ids: dict[InlineEntityKey, str] = {}

    def relations(self, node: PlannedNode) -> None:
        # (the values of a field are in the plan in the order of its list: each has its place in it)
        positions: dict[str, int] = {}
        for relation in node.relations:
            field = relation.edges[0][0]
            position = positions.get(field, 0)
            positions[field] = position + 1
            target = relation.target
            if isinstance(target, InlineEntity):
                self.edges(relation, node.id, self.inline_entity(target), position)
            elif isinstance(target, ReferenceToExisting):
                # (an entity can be referred to by a URL, as well as by its id)
                self.edges(
                    relation,
                    node.id,
                    target.value,
                    position,
                    by_url=target.is_url,
                    allowed=list(target.allowed_types),
                )
            else:
                self.tree_nodes.append(
                    {
                        "id": target.id,
                        "labels": list(target.labels),
                        "properties": encoded(target.properties),
                    }
                )
                self.edges(relation, node.id, target.id, position)
                self.relations(target)

    def urls(self, node: PlannedNode) -> None:
        """The URLs of a new entity, as nodes (`PGUrl`) that it has, rather than as a
        property: a URL is unique, so that two entities cannot have it, even if they are
        made at the same time (a uniqueness constraint)."""
        self.url_rows.extend({"id": node.id, "url": url} for url in node.urls)

    def edges(
        self,
        relation: Relation,
        source: str,
        target: str,
        position: int,
        by_url: bool = False,
        allowed: list[str] | None = None,
    ) -> None:
        """A row for the pair of edges of the field, and for the same pair of each parent field that the field
        subclasses"""
        properties = (
            encoded(relation.edge_properties, node=False)
            if relation.edge_properties
            else {}
        )
        for forward, backward in relation.edges:
            self.edge_pairs[by_url].add((forward, backward))
            self.edge_rows[by_url].append(
                {
                    "source": source,
                    "target": target,
                    "names": edge_names(forward, backward),
                    "position": position,
                    "properties": properties,
                    "allowed": allowed,
                }
            )

    def inline_entity(self, entity: InlineEntity) -> str:
        """The id of an entity written in the document: the one there is, or a new head node of its own"""
        key = entity.key
        if key in self.inline_entity_ids:
            return self.inline_entity_ids[key]
        if key in self.existing:
            self.inline_entity_ids[key] = self.existing[key].id
            return self.existing[key].id
        node = entity.node
        assert node is not None
        self.inline_entity_ids[key] = node.id
        self.entities.append(
            {
                "labels": list(node.labels),
                "properties": encoded(node.properties),
                "creation": new_record("created_when"),
            }
        )
        self.urls(node)
        self.relations(node)
        return node.id

    def statements(self, username: str) -> list[Statement]:
        """Nodes before edges, as an edge is between nodes that are there"""
        found: list[Statement] = []
        if self.tree_nodes:
            found.append(tree_nodes_statement(self.tree_nodes))
        if self.entities:
            found.append(entities_statement(self.entities, username))
        if self.url_rows:
            found.append(
                Statement(
                    typing.cast(typing.LiteralString, URLS),
                    {"rows": self.url_rows},
                    len(self.url_rows),
                )
            )
        for by_url, rows in self.edge_rows.items():
            if rows:
                # (in a fixed order: the text is then the same for the same relations)
                pairs = sorted(self.edge_pairs[by_url])
                found.append(edges_statement(pairs, by_url, rows))
        return found


def render(
    plan: WritePlan,
    existing: Mapping[InlineEntityKey, ExistingEntity] | None = None,
) -> list[Statement]:
    """The statements that make the write of `plan`, in the order to run them, given which of the entities written in
    it exist (`existing`, found by `validate_write.find_existing_entities`)"""
    head = plan.head
    username = current_request_username.get()
    renderer = _Renderer(existing)

    if plan.is_update:
        first = Statement(
            typing.cast(typing.LiteralString, HEAD_UPDATE),
            {
                "username": username,
                "id": head.id,
                "update": new_record("updated_when"),
            },
        )
    else:
        first = head_create_statement(head, username)
        renderer.urls(head)

    renderer.relations(head)
    return [first, *renderer.statements(username)]


def build_head_create_query(
    instance: typing.Any,
    existing_entities: Mapping[InlineEntityKey, ExistingEntity] | None = None,
) -> list[Statement]:
    """The statements that create a document or an entity (`plan_create`, rendered)"""
    return render(plan_create(instance), existing_entities)
