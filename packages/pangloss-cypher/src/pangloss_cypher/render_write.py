"""The Cypher of a `WritePlan` (`write_plan`), for the backend in use (its `dialect()` encodes the properties).

How the plan is stored is said here:

- a head node has the labels `HeadNode` and `PGIndexableNode`, and a record of its creation (`PGCreation`, with an edge
  to the user), or, for an update, of the update (`PGUpdate`);
- a node of a document has `PGIndexableNode`, and is `MERGE`d by its id;
- a relation is a pair of edges for each name it has: forward, and backward marked `{reverse: true}`, with the edge
  properties on both;
- a URL of an entity is a node of its own (`PGUrl`, unique), that the entity `has_url`;
- an existing node is matched by its id (or by a URL it has), and must have one of the allowed labels.

The variables and the parameters are named `x1`, `x2`... in the order the plan is walked, so a write of the same shape is
the same text (Memgraph keeps the plan of a query by its text)."""

import datetime
import typing
import uuid
from collections.abc import Mapping

from pangloss_users import current_request_username

from pangloss_cypher.params import Identifier, QueryParams
from pangloss_cypher.transactions import dialect
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


class QueryObject:
    """The query of a plan, as it is made: its parts, and its parameters"""

    match_query_strings: list[str]
    create_query_strings: list[str]
    params: QueryParams
    return_identifier: Identifier | None

    def __init__(self) -> None:
        self.match_query_strings = []
        self.create_query_strings = []
        self.params = QueryParams()
        self.return_identifier = None

    def to_query_string(self) -> typing.LiteralString:
        if not self.return_identifier:
            raise ValueError("CreateQuery.to_query_string called on non-top-level node")
        return typing.cast(
            typing.LiteralString,
            f"""
            {"\n".join(self.match_query_strings)}
            {"\n".join(self.create_query_strings)}
            RETURN {self.return_identifier}.id AS id
        """,
        )


class _Renderer:
    def __init__(
        self,
        query: QueryObject,
        existing: Mapping[InlineEntityKey, ExistingEntity] | None,
        user: Identifier,
    ):
        self.query = query
        # The user making the write (`PGUser`), matched by `render`: the maker of the new entities too
        self.user = user
        self.params = query.params
        self.existing = existing or {}
        # Identifiers of the existing nodes already matched, so that one referred to many times is matched once
        self.matched_references: dict[tuple, Identifier] = {}
        # Identifiers of the entities written in the document, so that one that is written twice is one
        self.inline_entity_identifiers: dict[InlineEntityKey, Identifier] = {}

    def relations(self, node: PlannedNode, identifier: Identifier) -> None:
        for relation in node.relations:
            target = relation.target
            if isinstance(target, InlineEntity):
                self.inline_entity(relation, target, identifier)
            elif isinstance(target, ReferenceToExisting):
                self.reference(relation, target, identifier)
            else:
                self.tree_node(relation, target, identifier)

    def urls(self, node: PlannedNode, identifier: Identifier) -> None:
        """The URLs of a new entity, as nodes (`PGUrl`) that it has, rather than as a
        property: a URL is unique, so that two entities cannot have it, even if they are
        made at the same time (a uniqueness constraint)."""
        for url in node.urls:
            url_identifier = self.params.new_identifier()
            url_parameter = self.params.add(url)
            self.query.create_query_strings.append(f"""
            CREATE ({url_identifier}:PGUrl {{url: ${url_parameter}}})
            CREATE ({identifier})-[:has_url]->({url_identifier})
        """)

    def edges(self, relation: Relation, source: Identifier, target: Identifier) -> None:
        """The forward and reverse edges between two nodes — and the same pair for each parent field that the field
        subclasses — with any edge properties on all of them"""
        edge_property_assignments: PropertyAssignments | None = None
        if relation.edge_properties:
            edge_property_assignments = PropertyAssignments(
                self.params, relation.edge_properties, node=False
            )
        for forward_name, backward_name in relation.edges:
            forward_query_identifier = self.params.new_identifier()
            reverse_query_identifier = self.params.new_identifier()
            self.query.create_query_strings.append(f"""
            CREATE ({source})-[{forward_query_identifier}:{forward_name}]->({target})
            CREATE ({source})<-[{reverse_query_identifier}:{backward_name} {{reverse: true}}]-({target})
        """)
            if edge_property_assignments:
                # `+=` adds to the edge's properties; `=` would replace them and
                # remove the {reverse: true} marker
                self.query.create_query_strings.append(f"""
                SET {edge_property_assignments.set_items(forward_query_identifier)}
                SET {edge_property_assignments.set_items(reverse_query_identifier)}
            """)

    def tree_node(
        self, relation: Relation, node: PlannedNode, source: Identifier
    ) -> None:
        identifier = self.params.new_identifier()
        node_id_identifier = self.params.add(node.id)
        node_data = PropertyAssignments(self.params, node.properties)
        self.query.create_query_strings.append(f"""
        MERGE ({identifier}:{labels_of(node, TREE_LABELS)} {{id: ${node_id_identifier}}})
        ON CREATE SET {node_data.set_items(identifier, replace=True)}
    """)
        self.edges(relation, source, identifier)
        self.relations(node, identifier)

    def inline_entity(
        self, relation: Relation, entity: InlineEntity, source: Identifier
    ) -> None:
        """An entity written in the document: the one there is, or a new head node of its own"""
        key = entity.key
        if key in self.inline_entity_identifiers:
            identifier = self.inline_entity_identifiers[key]
        elif key in self.existing:
            identifier = self.params.new_identifier()
            existing_id = self.params.add(self.existing[key].id)
            self.query.match_query_strings.append(
                f"MATCH ({identifier}:PGIndexableNode {{id: ${existing_id}}})"
            )
            self.inline_entity_identifiers[key] = identifier
        else:
            assert entity.node is not None
            identifier = self.params.new_identifier()
            self.inline_entity_identifiers[key] = identifier
            entity_data = PropertyAssignments(self.params, entity.node.properties)
            creation = self.params.new_identifier()
            creation_data = self.params.add(
                {
                    "id": str(uuid.uuid7()),
                    "created_when": datetime.datetime.now(datetime.UTC),
                }
            )
            self.query.create_query_strings.append(f"""
            CREATE ({identifier}:{labels_of(entity.node, HEAD_LABELS)})
            SET {entity_data.set_items(identifier, replace=True)}
            CREATE ({creation}:PGCreation)
            SET {creation} = ${creation_data}
            CREATE ({creation})-[:is_creation_of]->({identifier})
            CREATE ({creation})-[:created_by]->({self.user})
        """)
            self.urls(entity.node, identifier)
            self.relations(entity.node, identifier)
        self.edges(relation, source, identifier)

    def reference(
        self, relation: Relation, reference: ReferenceToExisting, source: Identifier
    ) -> None:
        allowed_types = list(reference.allowed_types)
        reference_key = (reference.value, reference.allowed_types)
        if reference_key in self.matched_references:
            identifier = self.matched_references[reference_key]
        else:
            identifier = self.params.new_identifier()
            self.matched_references[reference_key] = identifier
            id_identifier = self.params.add(reference.value)
            allowed_types_identifier = self.params.add(allowed_types)
            # An entity can be referred to by a URL, as well as by its id
            if reference.is_url:
                match_node = (
                    f"(:PGUrl {{url: ${id_identifier}}})"
                    f"<-[:has_url]-({identifier}:PGIndexableNode)"
                )
            else:
                match_node = f"({identifier}:PGIndexableNode {{id: ${id_identifier}}})"
            self.query.match_query_strings.append(
                f"""MATCH {match_node}
                WHERE ANY(label IN labels({identifier}) WHERE label IN ${allowed_types_identifier})
            """
            )
        self.edges(relation, source, identifier)


def render(
    plan: WritePlan,
    existing: Mapping[InlineEntityKey, ExistingEntity] | None = None,
) -> QueryObject:
    """The query that makes the write of `plan`, given which of the entities written in it exist (`existing`, found by
    `validate_write.find_existing_entities`)"""
    query = QueryObject()
    params = query.params
    head = plan.head
    identifier = params.new_identifier()
    query.return_identifier = identifier
    user = params.new_identifier()
    username_identifier = params.add(current_request_username.get())
    query.match_query_strings.append(
        f"MATCH ({user}:PGUser {{username: ${username_identifier}}})"
    )
    renderer = _Renderer(query, existing, user)

    if plan.is_update:
        head_id_identifier = params.add(head.id)
        update_data_identifier = params.add(
            {
                "id": str(uuid.uuid7()),
                "updated_when": datetime.datetime.now(datetime.UTC),
            }
        )
        query.match_query_strings.append(
            f"MATCH ({identifier}:HeadNode {{id: ${head_id_identifier}}})"
        )
        query.create_query_strings.append(f"""
        CREATE (update:PGUpdate)
        SET update = ${update_data_identifier}
        CREATE (update)-[:is_update_of]->({identifier})
        CREATE (update)-[:updated_by]->({user})
    """)
    else:
        node_data = PropertyAssignments(params, head.properties)
        creation_data_identifier = params.add(
            {
                "id": str(uuid.uuid7()),
                "created_when": datetime.datetime.now(datetime.UTC),
            }
        )
        query.create_query_strings.append(f"""
        CREATE ({identifier}:{labels_of(head, HEAD_LABELS)})
        SET {node_data.set_items(identifier, replace=True)}
        CREATE (creation:PGCreation)
        SET creation = ${creation_data_identifier}
        CREATE (creation)-[:is_creation_of]->({identifier})
        CREATE (creation)-[:created_by]->({user})
    """)
        renderer.urls(head, identifier)

    renderer.relations(head, identifier)
    return query


def build_head_create_query(
    instance: typing.Any,
    existing_entities: Mapping[InlineEntityKey, ExistingEntity] | None = None,
) -> QueryObject:
    """The query that creates a document or an entity (`plan_create`, rendered)"""
    return render(plan_create(instance), existing_entities)
