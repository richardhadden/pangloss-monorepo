"""The query for finding entities by their label while it is being typed (see docs/autocomplete.md)"""

from typing import LiteralString

# $patterns: one `.*word.*` for each word typed (lower case: the index cuts labels into lower-case words)
# $labels: any of these labels finds the node (the types asked for, with none that a parent already finds)
# $start: what was typed, to put the labels that begin with it first
# $page (1-indexed), $page_size
#
# (What is collected is a map of the properties, not the node: nodes found by the text index, collected
# after the ordering, came back as the same node several times.)
AUTOCOMPLETE_QUERY: LiteralString = """
    UNWIND $patterns AS pattern
    CALL db.index.fulltext.queryNodes("label_text", pattern) YIELD node, score
    WITH node AS n, pattern, max(score) AS patternScore
    WITH n, count(*) AS matchedPatterns, sum(patternScore) AS totalScore
    WHERE matchedPatterns = size($patterns)
      AND n:Entity
      AND any(label IN $labels WHERE label IN labels(n))
      AND NOT coalesce(n.deleted, false)
    WITH n, totalScore,
         CASE WHEN toLower(n.label) STARTS WITH $start THEN 0 ELSE 1 END AS rank
    ORDER BY rank, totalScore DESC, toLower(n.label), elementId(n)
    WITH collect({id: n.id, type: n.type, label: n.label}) AS allNodes
    WITH allNodes, size(allNodes) AS total,
         toInteger(ceil(toFloat(size(allNodes)) / $page_size)) AS totalPages
    WITH allNodes[($page - 1) * $page_size .. $page * $page_size] AS pageNodes,
         total, totalPages
    RETURN {
        results: pageNodes,
        count: total,
        page: $page,
        page_size: $page_size,
        page_count: totalPages,
        previous_page: CASE WHEN $page > 1 THEN $page - 1 ELSE null END,
        next_page: CASE WHEN $page < totalPages THEN $page + 1 ELSE null END
    } AS response
"""
