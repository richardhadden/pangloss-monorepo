"""The queries that read a document or an entity: what is below it, and what refers to it, for the backend in use (its
dialect walks the tree)"""

import uuid

from pangloss_models import Document, Entity

from pangloss_cypher import fragments
from pangloss_cypher.params import Identifier, QueryParams
from pangloss_cypher.transactions import dialect
from pangloss_cypher.values import convert_type_for_writing
from pangloss_cypher.visibility import unpublished_visible

# (the head node of what is read, and of what refers to an entity: see `pangloss_cypher.fragments`)
ROOT_HEAD = fragments.head_of("root", "hn")
HOLDER_HEAD = fragments.head_of("holder", "hn")


def build_fetch_document_query(
    document_class: type[Document | Entity], document_id: uuid.UUID
) -> tuple[str, QueryParams]:
    """Build the query for a Document or Entity and what it contains: its own
    values, `meta`, and everything below it. It returns the root node, the edges of
    the tree below it, and the `meta` (`build_tree` makes the tree). (For an Entity, its relations to
    documents come from `build_fetch_incoming_query`)"""
    # (the names of the parameters are fixed, so that the text of the query is the same each
    # time and the database finds its plan again: with a name made for each call it planned it
    # afresh each time, which took most of the time a read took)
    document_id_identifier = Identifier("document_id")
    document_type_identifier = Identifier("document_type")
    query_params = QueryParams()
    query_params[document_id_identifier] = convert_type_for_writing(document_id)
    query_params[document_type_identifier] = document_class.__name__
    query_params[Identifier("see_unpublished")] = unpublished_visible()
    d = dialect()
    query = f"""
    MATCH rp = (root:PGIndexableNode {{id: ${document_id_identifier}}})
    WHERE ${document_type_identifier} in labels(root)
    {ROOT_HEAD.match}
    WITH root, rp, {ROOT_HEAD} AS headnode
    // (a deleted document, or one nested in it, or a deleted entity, is not found)
    WHERE {fragments.visible("root", "headnode")}
    MATCH (headnode)<-[:is_creation_of]-(creation:PGCreation)
    CALL {{
        WITH headnode
        OPTIONAL MATCH (headnode)<-[:is_update_of]-(update:PGUpdate)-[:updated_by]->(update_user:PGUser)
        RETURN update.updated_when AS updated_when, update_user.username AS updated_by
        ORDER BY update.updated_when DESC
        LIMIT 1
    }}
    // The tree below the root: every node reachable by forward edges, without
    // entering entities. (Each relation is stored as a forward edge and a
    // reverse edge marked `reverse: true`, which is not followed.)
    OPTIONAL MATCH tree_path = (root){d.down_tree("tree")}(descendant)
    WITH headnode, root, creation, updated_by, updated_when, rp, collect(tree_path) AS tree_paths
    // The entities that the nodes of the tree refer to
    OPTIONAL MATCH entity_path = (root){d.down_tree("held")}(holder)-[holder_edge]->(:Entity)
    WHERE NOT coalesce(holder_edge.reverse, false)
    WITH headnode, root, creation, updated_by, updated_when, rp, tree_paths, collect(entity_path) AS entity_paths
    OPTIONAL MATCH root_entity_path = (root)-[root_edge]->(:Entity)
    WHERE NOT coalesce(root_edge.reverse, false)
    WITH headnode, root, creation, updated_by, updated_when, tree_paths, entity_paths,
         collect(rp) AS root_paths, collect(root_entity_path) AS root_entity_paths
    WITH headnode, root, creation, updated_by, updated_when,
         root_paths + tree_paths + entity_paths + root_entity_paths AS paths
    UNWIND paths AS path
    UNWIND (CASE WHEN size(relationships(path)) = 0 THEN [null] ELSE relationships(path) END) AS edge
    WITH headnode, root, creation, updated_by, updated_when,
         [found IN collect(DISTINCT edge) WHERE found IS NOT NULL] AS found_edges
    // A search reaches each node once, along one edge. A field that narrows another is stored
    // as an edge for each (to the same node), so the others between the same two nodes are
    // added: which one the search met first is not to decide what is read.
    UNWIND (CASE WHEN size(found_edges) = 0 THEN [null] ELSE found_edges END) AS found_edge
    WITH headnode, root, creation, updated_by, updated_when, found_edges, found_edge,
         CASE WHEN found_edge IS NULL THEN null ELSE startNode(found_edge) END AS from_node,
         CASE WHEN found_edge IS NULL THEN null ELSE endNode(found_edge) END AS to_node
    OPTIONAL MATCH (from_node)-[parallel]->(to_node)
    WHERE parallel <> found_edge AND NOT coalesce(parallel.reverse, false)
    WITH headnode, root, creation, updated_by, updated_when, found_edges,
         collect(DISTINCT parallel) AS parallels
    WITH headnode, root, creation, updated_by, updated_when,
         found_edges + [p IN parallels WHERE p IS NOT NULL] AS all_edges
    UNWIND (CASE WHEN size(all_edges) = 0 THEN [null] ELSE all_edges END) AS edge
    WITH headnode, root, creation, updated_by, updated_when, collect(DISTINCT edge) AS edges
    RETURN
        properties(root) AS root,
        labels(root) AS root_labels,
        [(root)-[:has_url]->(url:PGUrl) | url.url] AS urls,
        [edge IN edges WHERE edge IS NOT NULL | {{
            source: startNode(edge).id,
            type: type(edge),
            properties: properties(edge),
            target: properties(endNode(edge)),
            target_labels: labels(endNode(edge))
        }}] AS edges,
        {{
            created_by: {fragments.creators("creation")},
            uploaded_by: creation.uploaded_by,
            created_when: creation.created_when,
            updated_by: updated_by,
            updated_when: updated_when,
            semantic_spaces: {d.meta_property("root", "semantic_spaces")},
            context_labels: {d.meta_property("root", "context_labels")},
            head_node_type: headnode.type,
            head_node_id: headnode.id,
            head_node_label: headnode.label,
            marked_for_deletion: coalesce(root.marked_for_deletion, false),
            published: coalesce(headnode.published, true),
            review_status: headnode.review_status,
            version: size([(headnode)<-[:is_update_of]-(version_update:PGUpdate) | version_update]) + 1
        }} AS meta
    """
    return (query, query_params)


# The nodes that a relation to an entity can pass through on its way up to the document that holds it:
# the generic wrappers (a reified relation, a semantic space, a conjunction), and embedded objects
WRAPPER_LABELS = (
    "ReifiedRelation",
    "ReifiedRelationDocument",
    "SemanticSpace",
    "Conjunction",
)
CHAIN_LABELS = (*WRAPPER_LABELS, "Embedded")


def build_fetch_incoming_query(
    entity_class: type[Entity],
    entity_id: uuid.UUID,
    allowed: list[str],
    *,
    field: str | None = None,
    skip: int = 0,
    limit: int | None = None,
) -> tuple[str, dict]:
    """Build the query for the relations *to* an entity.

    Every relation is stored as a forward edge and a reverse edge marked
    `reverse: true`, so the relations to an entity are the reverse edges leading
    out of it. An entity can be related to through a chain of generic wrappers
    (reified relations, semantic spaces, conjunctions) and embedded objects
    (`Statement -> Date -> Identification -> Person`); for each reverse edge, this
    follows the chain up to the node that holds the relation (the document, or
    entity, that the chain starts from).

    Each row has the name of the relation as the entity has it (`name`: the field of its `HeadView`), how many there
    are of that name (`total`), the reverse edge's name, the nodes of the chain from the one next to the entity up
    to that node (and the names of the edges between them, and how many of the first are wrappers), and what is
    needed for the `meta` of that node. (What the nodes of the chain hold is read by `build_fetch_held_query`: with
    it in this query, the server returned a different path.)

    `allowed` is what the models show: `name|Holder|1` for each relation of that name from a class `Holder`, through
    a wrapper (`1`) or not (`0`). A relation that a subclass narrows is stored under both names and shown under one:
    the rest is left out here, before anything of it is read. With `field`, only the relations of that name. With
    `limit`, that many of each name from `skip`, by the label of what holds them: a name of which none is in the
    slice still has a row, with its `total` and no `chain`.

    (Finding the rows is quick, and reading the properties of every node of every chain is what takes the time:
    for an entity that 3,900 statements refer to, 14 ms and 480 ms, and another 160 ms for who made each. So the
    rows are found, sorted and cut first, and only what is kept is read.)
    """
    params = {
        "id": str(entity_id),
        "type": entity_class.__name__,
        "chain_labels": list(CHAIN_LABELS),
        "wrapper_labels": list(WRAPPER_LABELS),
        "allowed": allowed,
        "see_unpublished": unpublished_visible(),
    }
    only = ""
    if field is not None:
        only = "AND name = $field"
        params["field"] = field
    kept = "found"
    if limit is not None:
        kept = "found[$skip..$skip + $limit]"
        params["skip"] = skip
        params["limit"] = limit
    # (the labels are tested as a list: written as `a:X OR a:Y OR ...`, a longer list made the server
    # return the wrong path for a chain of several nodes)
    query = f"""
    MATCH (entity:PGIndexableNode {{id: $id}})
    WHERE $type IN labels(entity)
    MATCH (entity)-[first]->(next)
    WHERE coalesce(first.reverse, false)
    OPTIONAL MATCH ascent = (next){dialect().up_reverse("ascent", maximum=10)}(top)
    WHERE ANY(label IN labels(next) WHERE label IN $chain_labels)
      AND ALL(chain_node IN nodes(ascent)[0..-1]
              WHERE ANY(label IN labels(chain_node) WHERE label IN $chain_labels))
      AND NONE(label IN labels(top) WHERE label IN $chain_labels)
    WITH first, next, ascent, coalesce(top, next) AS holder
    {HOLDER_HEAD.match}
    WITH first, next, ascent, holder, {HOLDER_HEAD} AS headnode
    // (what has been deleted no longer refers to the entity)
    WHERE {fragments.visible("holder", "headnode")}
    // How many wrappers the relation passes through first (the node next to the entity, and those above it without
    // a break): counted up while they are wrappers, and held (as a negative number) from the first that is not
    WITH first, next, ascent, holder, headnode,
         CASE WHEN ascent IS NULL THEN 0 ELSE reduce(run = 0, chain_node IN nodes(ascent) |
             CASE WHEN run < 0 THEN run
                  WHEN ANY(label IN labels(chain_node) WHERE label IN $wrapper_labels) THEN run + 1
                  ELSE -run - 1 END) END AS run
    WITH first, next, ascent, holder, headnode, CASE WHEN run < 0 THEN -run - 1 ELSE run END AS wrappers
    // The name of the relation as the entity has it: the reverse edge that the wrappers end with, or else the first
    WITH first, next, ascent, holder, headnode, wrappers,
         CASE WHEN wrappers > 0 THEN type(relationships(ascent)[wrappers - 1]) ELSE type(first) END AS name
    WHERE (name + '|' + holder.type + '|' + CASE WHEN wrappers > 0 THEN '1' ELSE '0' END) IN $allowed {only}
    WITH name, first, next, ascent, holder, headnode, wrappers
    ORDER BY toLower(coalesce(holder.label, '')), holder.id
    WITH name, collect({{first: type(first), next: next, ascent: ascent, holder: holder, headnode: headnode,
                        wrappers: wrappers}}) AS found
    WITH name, size(found) AS total, {kept} AS kept
    UNWIND (CASE WHEN size(kept) = 0 THEN [null] ELSE kept END) AS row
    WITH name, total, row, row.next AS next, row.ascent AS ascent, row.holder AS holder, row.headnode AS headnode
    OPTIONAL MATCH (headnode)<-[:is_creation_of]-(creation:PGCreation)
    CALL {{
        WITH headnode
        OPTIONAL MATCH (headnode)<-[:is_update_of]-(update:PGUpdate)-[:updated_by]->(update_user:PGUser)
        RETURN update.updated_when AS updated_when, update_user.username AS updated_by
        ORDER BY update.updated_when DESC
        LIMIT 1
    }}
    RETURN
        name,
        total,
        row.first AS first_edge_type,
        row.wrappers AS wrappers,
        CASE WHEN row IS NULL THEN null
             WHEN ascent IS NULL THEN [next{{.*, _labels: labels(next)}}]
             ELSE [chain_node IN nodes(ascent) | chain_node{{.*, _labels: labels(chain_node)}}]
        END AS chain,
        CASE WHEN ascent IS NULL THEN [] ELSE [edge IN relationships(ascent) | type(edge)] END AS chain_edge_types,
        {{
            created_by: {fragments.creators("creation")},
            created_when: creation.created_when,
            updated_by: updated_by,
            updated_when: updated_when,
            head_node_type: headnode.type,
            head_node_id: headnode.id
        }} AS creation_meta
    """
    return query, params


def build_fetch_held_query(node_ids: list[str]) -> tuple[str, dict]:
    """Build the query for what generic wrappers hold: for each node, the forward edges from it (not
    the reverse ones that lead back up) with what they lead to.

    A reified relation holds its targets in `target`, a semantic space its contents in `contents`, a
    conjunction its parts in the fields it names (`cause`, `result`)."""
    query = """
    UNWIND $node_ids AS node_id
    MATCH (node:PGIndexableNode {id: node_id})
    OPTIONAL MATCH (node)-[held]->(target)
    WHERE NOT coalesce(held.reverse, false)
    RETURN node_id AS id,
           collect(CASE WHEN held IS NULL THEN null ELSE {edge: type(held), node: target{.*}, labels: labels(target), properties: properties(held)} END) AS held
    """
    return query, {"node_ids": node_ids}
