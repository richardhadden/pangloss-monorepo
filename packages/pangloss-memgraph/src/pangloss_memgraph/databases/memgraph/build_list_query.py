from typing import LiteralString

from pangloss_models.model_bases.document import Document
from pangloss_models.model_bases.entity import Entity


def build_generic_list_query(
    object_class: type[Document | Entity],
    search_terms: str | None = None,
    page_number: int | None = None,
    page_size: int | None = None,
    deep_search: bool = False,
) -> tuple[LiteralString, dict]:

    print("BuildListQuery", object_class.__metatype__, search_terms, deep_search)

    if search_terms and deep_search:
        search_term_list = [f".*{t}.*" for t in search_terms.split(" ")]
        params = {
            "targetType": object_class.__name__,
            "page": page_number or 1,
            "page_size": page_size or 50,
            "tokens": search_term_list,
        }
        if object_class.__metatype__ == "Document":
            return (
                """
                // $tokens: list of tokenised search words
                // $targetType: e.g. "Document"
                // $page: page number (1-indexed)
                // $page_size: results per page

                UNWIND $tokens AS token
                CALL text_search.regex_search("label_index", token) YIELD node AS matchedNode
                CALL {
                  WITH matchedNode
                  WITH matchedNode
                  WHERE NOT "Entity" IN labels(matchedNode)
                  RETURN coalesce(matchedNode.head_node_id, matchedNode.id) AS treeRootId
                  UNION
                  WITH matchedNode
                  WHERE "Entity" IN labels(matchedNode)
                  MATCH (matchedNode)--(neighbor:PGIndexableNode)
                  WHERE NOT "Entity" IN labels(neighbor)
                  RETURN coalesce(neighbor.head_node_id, neighbor.id) AS treeRootId
                }
                WITH collect({token: token, matchedNode: matchedNode, treeRootId: treeRootId}) AS matches

                UNWIND matches AS m
                WITH matches, m.treeRootId AS treeRootId, m.token AS token
                WITH matches, treeRootId, collect(DISTINCT token) AS treeTokens
                WHERE size(treeTokens) = size($tokens)
                WITH matches, collect(DISTINCT treeRootId) AS qualifyingRoots

                UNWIND matches AS m
                WITH qualifyingRoots, m.matchedNode AS scoredNode, m.token AS token
                WITH qualifyingRoots, scoredNode, size(collect(DISTINCT token)) AS score
                WITH qualifyingRoots, collect({node: scoredNode, score: score}) AS nodeScores

                UNWIND qualifyingRoots AS rootId
                CALL {
                  WITH rootId, $targetType AS targetType
                  MATCH (n:PGIndexableNode {id: rootId})
                  WHERE targetType IN labels(n)
                  RETURN n
                  UNION
                  WITH rootId, $targetType AS targetType
                  MATCH (n:PGIndexableNode {head_node_id: rootId})
                  WHERE targetType IN labels(n)
                  RETURN n
                }
                WITH DISTINCT n, nodeScores

                WITH n, [x IN nodeScores WHERE x.node = n | x.score] AS scoreList
                WITH n, CASE WHEN size(scoreList) > 0 THEN scoreList[0] ELSE 0 END AS matchScore

                WITH collect({n: n, matchScore: matchScore}) AS allResults
                WITH allResults, size(allResults) AS total

                // --- paging + enrichment, isolated so it always returns exactly one row ---
                CALL {
                  WITH allResults
                  UNWIND allResults AS r
                  WITH r.n AS n, r.matchScore AS matchScore
                  ORDER BY matchScore DESC, n.id
                  SKIP ($page - 1) * $page_size
                  LIMIT $page_size

                  OPTIONAL MATCH (hn:HeadNode {id: n.head_node_id})
                  WITH n, coalesce(hn, n) AS headnode
                  MATCH (headnode)<-[:is_creation_of]-(creation:PGCreation)
                  MATCH (creation)-[:created_by]->(user:PGUser)

                  WITH collect(n{.*, meta: {
                      created_by: user.username,
                      created_when: creation.created_when,
                      updated_by: null,
                      updated_when: null,
                      semantic_spaces: n.semantic_spaces,
                      semantic_space_labels: n.semantic_space_labels
                  }}) AS pagedResults
                  RETURN pagedResults
                }

                RETURN {
                  results: pagedResults,
                  count: total,
                  page: $page,
                  page_size: $page_size,
                  page_count: toInteger(ceil(toFloat(total) / $page_size)),
                  previous_page: CASE WHEN $page > 1 THEN $page - 1 ELSE null END,
                  next_page: CASE WHEN $page < toInteger(ceil(toFloat(total) / $page_size)) THEN $page + 1 ELSE null END
                } AS response
            """,
                params,
            )
        if object_class.__metatype__ == "Entity":
            return (
                """

            // $tokens: list of tokenised search words
            // $targetType: label to filter Entities by
            // $page: page number (1-indexed)
            // $page_size: results per page

            UNWIND $tokens AS token
            CALL text_search.regex_search("label_index", token) YIELD node AS matchedNode
            CALL {
              WITH matchedNode
              WITH matchedNode
              WHERE NOT "Entity" IN labels(matchedNode)
              RETURN coalesce(matchedNode.head_node_id, matchedNode.id) AS treeRootId
              UNION
              WITH matchedNode
              WHERE "Entity" IN labels(matchedNode)
              MATCH (matchedNode)--(neighbor:PGIndexableNode)
              WHERE NOT "Entity" IN labels(neighbor)
              RETURN coalesce(neighbor.head_node_id, neighbor.id) AS treeRootId
            }
            WITH collect({token: token, matchedNode: matchedNode, treeRootId: treeRootId}) AS matches

            UNWIND matches AS m
            WITH matches, m.treeRootId AS treeRootId, m.token AS token
            WITH matches, treeRootId, collect(DISTINCT token) AS treeTokens
            WHERE size(treeTokens) = size($tokens)
            WITH matches, collect(DISTINCT treeRootId) AS qualifyingRoots

            UNWIND matches AS m
            WITH qualifyingRoots, m.matchedNode AS scoredNode, m.token AS token
            WITH qualifyingRoots, scoredNode, size(collect(DISTINCT token)) AS score
            WITH qualifyingRoots, collect({node: scoredNode, score: score}) AS nodeScores

            UNWIND qualifyingRoots AS rootId
            CALL {
              WITH rootId
              MATCH (t:PGIndexableNode {id: rootId})
              RETURN t
              UNION
              WITH rootId
              MATCH (t:PGIndexableNode {head_node_id: rootId})
              RETURN t
            }
            WITH DISTINCT t, nodeScores
            MATCH (t)--(n:Entity)
            WHERE $targetType IN labels(n)
            WITH DISTINCT n, nodeScores

            WITH n, [x IN nodeScores WHERE x.node = n | x.score] AS scoreList
            WITH n, CASE WHEN size(scoreList) > 0 THEN scoreList[0] ELSE 0 END AS matchScore

            WITH collect({n: n, matchScore: matchScore}) AS allResults
            WITH allResults, size(allResults) AS total

            CALL {
              WITH allResults
              UNWIND allResults AS r
              WITH r.n AS n, r.matchScore AS matchScore
              ORDER BY matchScore DESC, n.id
              SKIP ($page - 1) * $page_size
              LIMIT $page_size

              OPTIONAL MATCH (hn:HeadNode {id: n.head_node_id})
              WITH n, coalesce(hn, n) AS headnode
              MATCH (headnode)<-[:is_creation_of]-(creation:PGCreation)
              MATCH (creation)-[:created_by]->(user:PGUser)

              WITH collect(n{.*, meta: {
                  created_by: user.username,
                  created_when: creation.created_when,
                  updated_by: null,
                  updated_when: null,
                  semantic_spaces: n.semantic_spaces,
                  semantic_space_labels: n.semantic_space_labels
              }}) AS pagedResults
              RETURN pagedResults
            }

            RETURN {
              results: pagedResults,
              count: total,
              page: $page,
              page_size: $page_size,
              page_count: toInteger(ceil(toFloat(total) / $page_size)),
              previous_page: CASE WHEN $page > 1 THEN $page - 1 ELSE null END,
              next_page: CASE WHEN $page < toInteger(ceil(toFloat(total) / $page_size)) THEN $page + 1 ELSE null END
            } AS response
            """,
                params,
            )
    if search_terms:
        search_string = [f".*{t}.*" for t in search_terms.split(" ")]
        params = {
            "node_type": object_class.__name__,
            "page_number": page_number or 1,
            "page_size": page_size or 50,
            "patterns": search_string,
        }
        return (
            """
            UNWIND $patterns AS pattern
            CALL text_search.regex_search("label_index", pattern) YIELD node, score
            WITH node AS n, pattern, max(score) AS patternScore
            WITH n, count(*) AS matchedPatterns, sum(patternScore) AS totalScore
            WHERE matchedPatterns = size($patterns)
              AND $node_type IN labels(n)
            WITH n, totalScore
            ORDER BY totalScore DESC, id(n)
            WITH collect(n) AS allNodes
            WITH allNodes,
                 size(allNodes) AS total,
                 toInteger(ceil(toFloat(size(allNodes)) / $page_size)) AS totalPages
            WITH allNodes[($page_number - 1) * $page_size .. $page_number * $page_size] AS pageNodes,
                 total, totalPages
            CALL {
                WITH pageNodes
                UNWIND pageNodes AS n
                OPTIONAL MATCH (hn:HeadNode {id: n.head_node_id})
                WITH n, coalesce(hn, n) AS headnode
                OPTIONAL MATCH (headnode)<-[:is_creation_of]-(creation:PGCreation)
                OPTIONAL MATCH (creation)-[:created_by]->(user:PGUser)
                RETURN collect(n{.*, meta: {
                    created_by: user.username,
                    created_when: creation.created_when,
                    updated_by: null,
                    updated_when: null,
                    semantic_spaces: n.semantic_spaces,
                    semantic_space_labels: n.semantic_space_labels
                }}) AS items
            }
            RETURN {
                results: items,
                count: total,
                page: $page_number,
                page_size: $page_size,
                page_count: totalPages,
                previous_page: CASE WHEN $page_number > 1 THEN $page_number - 1 ELSE null END,
                next_page: CASE WHEN $page_number < totalPages THEN $page_number + 1 ELSE null END
            } AS result;
        """,
            params,
        )

    else:
        params = {
            "node_type": object_class.__name__,
            "page_number": page_number or 1,
            "page_size": page_size or 50,
        }
        return (
            """
            MATCH (n)
            WHERE $node_type in labels(n)
            WITH count(n) AS total

            MATCH (n)
            WHERE $node_type in labels(n)
            WITH n, total
            ORDER BY n.id
            SKIP ($page_number - 1) * $page_size
            LIMIT $page_size

            OPTIONAL MATCH (hn:HeadNode {id: n.head_node_id})
            WITH n, total, coalesce(hn, n) AS headnode
            MATCH (headnode)<-[:is_creation_of]-(creation:PGCreation)
            MATCH (creation)-[:created_by]->(user:PGUser)

            WITH collect(n{.*, meta: {
                created_by: user.username,
                created_when: creation.created_when,
                updated_by: null,
                updated_when: null,
                semantic_spaces: n.semantic_spaces,
                semantic_space_labels: n.semantic_space_labels
            }}) AS items, total, toInteger(ceil(toFloat(total) / $page_size)) AS totalPages

            RETURN {
              results: items,
              count: total,
              page: $page_number,
              page_size: $page_size,
              page_count: toInteger(ceil(toFloat(total) / $page_size)),
              previous_page: CASE WHEN $page_number > 1 THEN $page_number - 1 ELSE null END,
              next_page: CASE WHEN $page_number < totalPages THEN $page_number + 1 ELSE null END
            } AS result
        """,
            params,
        )
