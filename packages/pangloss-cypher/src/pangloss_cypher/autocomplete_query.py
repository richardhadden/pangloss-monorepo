"""The query for finding entities by their label while it is being typed (see docs/autocomplete.md)"""

from typing import LiteralString, cast

from pangloss_cypher import fragments
from pangloss_cypher.dialect import Dialect


# The end of both queries: the page of the ordered nodes `n`. (What is collected is a map of the properties, not the
# node: nodes found by the text index, collected after the ordering, came back as the same node several times.)
PAGE = """\
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


# $patterns: a pattern for each word typed (`Dialect.search_patterns`)
# $limit: how many hits the text index is asked for, of each word (`SEARCH_HIT_LIMIT`). The index is of every label,
#   of documents and of what is in them too, and it gives 1000 if it is not asked: a word that is in more labels than
#   that (a surname, in the labels of the statements about the family) then found few of the entities, or none
# $labels: any of these labels finds the node (the types asked for, with none that a parent already finds)
# $start: what was typed (`Dialect.autocomplete_start`), to put the labels that begin with it first
# $page (1-indexed), $page_size
def autocomplete_query(d: Dialect) -> LiteralString:
    return cast(
        LiteralString,
        f"""
    UNWIND $patterns AS pattern
    CALL {d.text_search("label_text", "pattern", "{limit: $limit}")} YIELD node, score
    WITH node AS n, pattern, max(score) AS patternScore
    WITH n, count(*) AS matchedPatterns, sum(patternScore) AS totalScore
    WHERE matchedPatterns = size($patterns)
      AND n:Entity
      AND any(label IN $labels WHERE label IN labels(n))
      AND {fragments.not_deleted("n")}
    WITH n, totalScore,
         CASE WHEN {d.folded_label("n")} STARTS WITH $start THEN 0 ELSE 1 END AS rank
    ORDER BY rank, totalScore DESC, toLower(n.label), {d.tie_break("n")}
{PAGE}""",
    )


# $labels, $page, $page_size: as above
#
# What is offered before anything is typed: the entities of the types that have the most edges out of them (an entity's
# reverse edges go out of it, one for each place it is referred to), so the ones most used come first.
def most_used_query(d: Dialect) -> LiteralString:
    return cast(
        LiteralString,
        f"""
    MATCH (n:Entity)
    WHERE any(label IN $labels WHERE label IN labels(n))
      AND {fragments.not_deleted("n")}
    OPTIONAL MATCH (n)-[edge]->()
    WITH n, count(edge) AS uses
    ORDER BY uses DESC, toLower(n.label), {d.tie_break("n")}
{PAGE}""",
    )
