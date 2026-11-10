"""The query of a list of a class: all of it, a page at a time, or what the text index finds of it (see
implementation_docs/deep-search.md), for the backend in use: its dialect gives the call of the text index, the patterns, the `meta`, and
may give its own text for a part (`Dialect.query`)"""

from typing import LiteralString, cast

from pangloss_models import Document, Entity

from pangloss_cypher import fragments
from pangloss_cypher.dialect import Dialect
from pangloss_cypher.transactions import dialect
from pangloss_cypher.visibility import unpublished_visible


# (the head nodes of what is listed: see `pangloss_cypher.fragments`)
N_HEAD = fragments.head_of("n", "n_head")
T_HEAD = fragments.head_of("t", "t_head")
COUNTED_HEAD = fragments.head_of("n", "counted_head")
LISTED_HEAD = fragments.head_of("n", "listed_head")

# The deep search (see implementation_docs/deep-search.md). Nothing large is carried from row to row: the hits are reduced to
# the ids of the documents (the roots) that have every word, and only those are expanded. (It once kept a list of
# every hit on each row, and took time and memory by the number of rows times the number of hits.)
#
# $tokens: a pattern for each word (`Dialect.search_patterns`)
# $limit: the most hits of the text index looked at for each
# $targetType: the class listed
# $page (1-indexed), $page_size


def _deep_roots(d: Dialect) -> str:
    return f"""
    UNWIND $tokens AS token
    CALL {d.text_search("label_text", "token", "{limit: $limit}")} YIELD node AS matchedNode
    CALL (matchedNode) {{
      WITH matchedNode
      WHERE NOT "Entity" IN labels(matchedNode)
      RETURN coalesce(matchedNode.head_node_id, matchedNode.id) AS treeRootId
      UNION
      WITH matchedNode
      WHERE "Entity" IN labels(matchedNode)
      MATCH (matchedNode)--(neighbor:PGIndexableNode)
      WHERE NOT "Entity" IN labels(neighbor)
      RETURN coalesce(neighbor.head_node_id, neighbor.id) AS treeRootId
    }}
    // (a root qualifies if every word is found somewhere in its tree)
    WITH treeRootId, count(DISTINCT token) AS wordsFound
    WHERE wordsFound = size($tokens)
    WITH collect(treeRootId) AS qualifyingRoots
    UNWIND qualifyingRoots AS rootId
"""


# (the documents of the class in the trees found; they are ordered by the label of their head node)
def _deep_documents(used: str) -> str:
    return f"""
    CALL (rootId) {{
      MATCH (n:PGIndexableNode {{id: rootId}})
      WHERE $targetType IN labels(n)
      RETURN n
      UNION
      MATCH (n:PGIndexableNode {{head_node_id: rootId}})
      WHERE $targetType IN labels(n)
      RETURN n
    }}
    WITH DISTINCT n
    // (what has been deleted is not listed: a deleted entity, or a node of a deleted document)
    {N_HEAD.match}
    WITH n, n_head
    WHERE {fragments.visible("n", N_HEAD, filters=True)}
    {used}
    WITH n, toLower(coalesce(coalesce(n_head, n).label, "")) AS headLabel
    ORDER BY headLabel, n.id
"""


# (the entities of the class that the nodes of the trees found refer to; ordered by their labels)
def _deep_entities(used: str) -> str:
    return f"""
    CALL (rootId) {{
      MATCH (t:PGIndexableNode {{id: rootId}})
      RETURN t
      UNION
      MATCH (t:PGIndexableNode {{head_node_id: rootId}})
      RETURN t
    }}
    WITH DISTINCT t
    // (what has been deleted is not listed: a deleted entity, or a node of a deleted document)
    {T_HEAD.match}
    WITH t, t_head
    WHERE {fragments.visible("t", T_HEAD, filters=True)}
    MATCH (t)--(n:Entity)
    WHERE $targetType IN labels(n)
    WITH DISTINCT n
    // (the same for the entity found)
    {N_HEAD.match}
    WITH n, n_head
    WHERE {fragments.visible("n", N_HEAD, filters=True)}
    {used}
    WITH n, toLower(coalesce(coalesce(n_head, n).label, "")) AS headLabel
    ORDER BY headLabel, n.id
"""


# (the page of what is ordered above, and its enrichment, isolated so that it always returns exactly one row)
def _deep_page(d: Dialect) -> str:
    return f"""
    WITH collect(n) AS allResults
    WITH allResults, size(allResults) AS total

    CALL {{
      WITH allResults
      UNWIND allResults AS n
      WITH n
      SKIP ($page - 1) * $page_size
      LIMIT $page_size

      OPTIONAL MATCH (hn:HeadNode {{id: n.head_node_id}})
      WITH n, coalesce(hn, n) AS headnode
      // (a head without a record of its creation is listed all the same, with no creator)
      OPTIONAL MATCH (headnode)<-[:is_creation_of]-(creation:PGCreation)
      OPTIONAL MATCH (creation)-[:created_by]->(user:PGUser)

      WITH collect(n{{.*, meta: {{
          created_by: user.username,
          created_when: creation.created_when,
          updated_by: null,
          updated_when: null,
          semantic_spaces: coalesce({d.meta_property("n", "semantic_spaces")}, []),
          context_labels: {d.meta_property("n", "context_labels")},
          head_node_id: n.head_node_id,
          head_node_type: n.head_node_type,
          is_head_node: n:HeadNode,
          published: coalesce(headnode.published, true),
          review_status: headnode.review_status
      }}}}) AS pagedResults
      RETURN pagedResults
    }}

    RETURN {{
      results: pagedResults,
      count: total,
      page: $page,
      page_size: $page_size,
      page_count: toInteger(ceil(toFloat(total) / $page_size)),
      previous_page: CASE WHEN $page > 1 THEN $page - 1 ELSE null END,
      next_page: CASE WHEN $page < toInteger(ceil(toFloat(total) / $page_size)) THEN $page + 1 ELSE null END
    }} AS response
"""


# What the text index is asked for, of each word, if the settings say nothing (`SEARCH_HIT_LIMIT`). The index
# gives 1000 if it is not asked: a word with more hits than that had most of its results left out, unseen.
DEFAULT_HIT_LIMIT = 100_000


# Whether some word of the search has more hits than `$limit` (asked for one more, to know): then the results
# of the list are not all there are. Apart from the list's own query so that it gives an answer when the list is empty.
def truncation_query(d: Dialect) -> LiteralString:
    return cast(
        LiteralString,
        f"""
    UNWIND $patterns AS pattern
    CALL {d.text_search("label_text", "pattern", "{limit: $limit + 1}")} YIELD node
    WITH pattern, count(node) AS hits
    RETURN coalesce(max(hits), 0) > $limit AS truncated
""",
    )


def search_patterns(search_terms: str | None) -> list[str]:
    """A pattern for each word of the search, for the text index of the backend in use (`Dialect.search_patterns`)"""
    return dialect().search_patterns(search_terms)


def build_truncation_query(
    search_terms: str | None, hit_limit: int = DEFAULT_HIT_LIMIT
) -> tuple[LiteralString, dict]:
    return truncation_query(dialect()), {
        "patterns": search_patterns(search_terms),
        "limit": hit_limit,
    }


def build_generic_list_query(
    object_class: type[Document | Entity],
    search_terms: str | None = None,
    page_number: int | None = None,
    page_size: int | None = None,
    deep_search: bool = False,
    published: bool | None = None,
    review_status: str | None = None,
    hit_limit: int = DEFAULT_HIT_LIMIT,
    used_only: bool = False,
) -> tuple[LiteralString, dict]:
    query, params = _build_list_query(
        object_class,
        search_terms,
        page_number,
        page_size,
        deep_search,
        hit_limit,
        used_only,
    )
    # (a document that is not published is listed only for those who may see it)
    params["see_unpublished"] = unpublished_visible()
    # (to list only the documents that are, or are not, published, or in a status of review)
    params["published"] = published
    params["review_status"] = review_status
    return query, params


def _build_list_query(
    object_class: type[Document | Entity],
    search_terms: str | None = None,
    page_number: int | None = None,
    page_size: int | None = None,
    deep_search: bool = False,
    hit_limit: int = DEFAULT_HIT_LIMIT,
    used_only: bool = False,
) -> tuple[LiteralString, dict]:
    d = dialect()
    patterns = d.search_patterns(search_terms)

    if patterns and deep_search:
        # (`n_head` is used after it, for the order)
        used = fragments.only_used("n", "n_head") if used_only else ""
        params = {
            "targetType": object_class.__name__,
            "page": page_number or 1,
            "page_size": page_size or 50,
            "tokens": patterns,
            "limit": hit_limit,
        }
        if object_class.__metatype__ == "Document":
            found = _deep_documents(used)
        else:
            found = _deep_entities(used)
        return cast(LiteralString, _deep_roots(d) + found + _deep_page(d)), params
    if patterns:
        params = {
            "node_type": object_class.__name__,
            "page_number": page_number or 1,
            "page_size": page_size or 50,
            "patterns": patterns,
            "limit": hit_limit,
        }
        return (
            cast(
                LiteralString,
                f"""
            UNWIND $patterns AS pattern
            CALL {d.text_search("label_text", "pattern", "{limit: $limit}")} YIELD node, score
            WITH node AS n, pattern, max(score) AS patternScore
            WITH n, count(*) AS matchedPatterns, sum(patternScore) AS totalScore
            WHERE matchedPatterns = size($patterns)
              AND $node_type IN labels(n)
            WITH n, totalScore
            // (what has been deleted is not listed: a deleted entity, or a node of a deleted document)
            {N_HEAD.match}
            WITH n, totalScore, n_head
            WHERE {fragments.visible("n", N_HEAD, filters=True)}
            {fragments.only_used("n", "totalScore") if used_only else ""}
            WITH n, totalScore
            ORDER BY totalScore DESC, {d.tie_break("n")}
            WITH collect(n) AS allNodes
            WITH allNodes,
                 size(allNodes) AS total,
                 toInteger(ceil(toFloat(size(allNodes)) / $page_size)) AS totalPages
            WITH allNodes[($page_number - 1) * $page_size .. $page_number * $page_size] AS pageNodes,
                 total, totalPages
            CALL {{
                WITH pageNodes
                UNWIND pageNodes AS n
                OPTIONAL MATCH (hn:HeadNode {{id: n.head_node_id}})
                WITH n, coalesce(hn, n) AS headnode
                OPTIONAL MATCH (headnode)<-[:is_creation_of]-(creation:PGCreation)
                OPTIONAL MATCH (creation)-[:created_by]->(user:PGUser)
                RETURN collect(n{{.*, meta: {{
                    created_by: user.username,
                    created_when: creation.created_when,
                    updated_by: null,
                    updated_when: null,
                    semantic_spaces: coalesce({d.meta_property("n", "semantic_spaces")}, []),
                    context_labels: {d.meta_property("n", "context_labels")},
                    head_node_id: n.head_node_id,
                    head_node_type: n.head_node_type,
                    is_head_node: n:HeadNode,
                    published: coalesce(headnode.published, true),
                    review_status: headnode.review_status
                }}}}) AS items
            }}
            RETURN {{
                results: items,
                count: total,
                page: $page_number,
                page_size: $page_size,
                page_count: totalPages,
                previous_page: CASE WHEN $page_number > 1 THEN $page_number - 1 ELSE null END,
                next_page: CASE WHEN $page_number < totalPages THEN $page_number + 1 ELSE null END
            }} AS result;
        """,
            ),
            params,
        )

    else:
        params = {
            "node_type": object_class.__name__,
            "page_number": page_number or 1,
            "page_size": page_size or 50,
        }
        page = (
            _used_page(object_class)
            if used_only
            else d.query("list.plain.page", _plain_page(), object_class=object_class)
        )
        return cast(LiteralString, page + _plain_items(d)), params


def _plain_page() -> str:
    """The nodes of the page of a plain list, ordered by id, as `n`, with the number of them all (`total`)"""
    return f"""
            MATCH (n:$node_type)
            // (what has been deleted is not listed: a deleted entity, or a node of a deleted document)
            {COUNTED_HEAD.match}
            WITH n, counted_head
            WHERE {fragments.visible("n", COUNTED_HEAD, filters=True)}

                        WITH count(n) AS total

                        MATCH (n:$node_type)
            {LISTED_HEAD.match}
            WITH n, total, listed_head
            WHERE {fragments.visible("n", LISTED_HEAD, filters=True)}

                        WITH n, total
                        ORDER BY n.id
                        SKIP ($page_number - 1) * $page_size
                        LIMIT $page_size
"""


def _used_page(object_class: type[Document | Entity]) -> str:
    """As `_plain_page`, of what something refers to. The class is read once, for the number and the page together
    (each node is tested for what refers to it: twice would be twice the cost), with the text the same on every backend"""
    return f"""
            MATCH (n:{fragments.label(object_class.__name__)})
            {LISTED_HEAD.match}
            WITH n, listed_head
            WHERE {fragments.visible("n", LISTED_HEAD, filters=True)}
            {fragments.only_used("n")}
            WITH n
            ORDER BY n.id
            WITH collect(n) AS listed
            WITH listed, size(listed) AS total
            UNWIND listed[($page_number - 1) * $page_size .. $page_number * $page_size] AS n
            WITH n, total
"""


def _plain_items(d: Dialect) -> str:
    """The page of a plain list as one row: its items, the facets of what they refer to, and the counts"""
    return f"""
                        OPTIONAL MATCH (hn:HeadNode:PGIndexableNode {{id: n.head_node_id}})
                        WITH n, total, coalesce(hn, n) AS headnode
                        // (a head without a record of its creation is listed all the same, with no creator)
                        OPTIONAL MATCH (headnode)<-[:is_creation_of]-(creation:PGCreation)
                        OPTIONAL MATCH (creation)-[:created_by]->(user:PGUser)

                        // The page, as one row: the facets are of the entities the whole page refers
                        // to (computed for each node they were one row each, and a page of
                        // documents that refer to entities came back as many rows)
                        WITH collect(n{{.*, meta: {{
                            created_by: user.username,
                            created_when: creation.created_when,
                            updated_by: null,
                            updated_when: null,
                            semantic_spaces: coalesce({d.meta_property("n", "semantic_spaces")}, []),
                            context_labels: {d.meta_property("n", "context_labels")},
                            head_node_id: n.head_node_id,
                            head_node_type: n.head_node_type,
                            is_head_node: n:HeadNode,
                            published: coalesce(headnode.published, true),
                            review_status: headnode.review_status
                        }}}}) AS items, collect(n) AS page_nodes, total,
                        toInteger(ceil(toFloat(total) / $page_size)) AS totalPages

                        CALL {{
                          WITH page_nodes
                          UNWIND page_nodes AS m
                          OPTIONAL MATCH (m)-->(entities:Entity)
                          WITH entities
                          WHERE entities IS NOT NULL
                          WITH entities.type AS type, collect(DISTINCT entities{{.id, .type, .label}}) AS nodes
                          RETURN {d.facets_from("type", "nodes")} AS facets
                        }}

                        RETURN {{
                          results: items,
                          count: total,
                          page: $page_number,
                          page_size: $page_size,
                          page_count: toInteger(ceil(toFloat(total) / $page_size)),
                          previous_page: CASE WHEN $page_number > 1 THEN $page_number - 1 ELSE null END,
                          next_page: CASE WHEN $page_number < totalPages THEN $page_number + 1 ELSE null END,
                          facets: facets
                        }} AS result
        """
