from typing import no_type_check

import pytest
from pangloss_models import initialise
from pangloss_models.model_bases.base_models import _ListItems
from pangloss_models.model_bases.document import Document
from pangloss_models.model_bases.entity import Entity

pytestmark = pytest.mark.asyncio(loop_scope="session")


LABELS = [
    "John Smith ate an Alligator",
    "John Smith ate a Bear",
    "John Smith ate a Cat",
    "John Smith ate a Dog",
    "John Smith ate an Elephant",
    "John Smith ate a Fox",
    "John Smith ate a Giraffe",
    "John Smith ate a Horse",
    "John Smith ate an Iguana",
    "John Smith ate a Jaguar",
    "John Smith ate a Kangaroo",
    "John Smith ate a Lion",
    "John Smith ate a Moose",
    "John Smith ate a Newt",
    "John Smith ate an Octopus",
    "John Smith ate a Penguin",
    "John Smith ate a Quail",
    "John Smith ate a Rabbit",
    "John Smith ate a Snake",
    "John Smith ate a Tiger",
    "John Smith ate an Urchin",
    "John Smith ate a Vulture",
    "John Smith ate a Walrus",
    "John Smith ate a Xenops",
    "John Smith ate a Yak",
    "John Smith ate a Zebra",
]


@no_type_check
async def test_list_basic_and_search(clear_database):

    class Factoid(Document):
        pass

    class SubFactoid(Factoid):
        pass

    initialise()

    for label in LABELS:
        factoid = Factoid.Create(label=label)
        await factoid.save()

        subfactoid = SubFactoid.Create(label=label)
        await subfactoid.save()

    result: _ListItems = await Factoid.list()

    assert result.count == 52
    assert result.page == 1
    assert result.next_page == 2
    assert result.previous_page is None
    assert result.page_size == 50

    # check we have some proper types being return
    assert any(r.type == "SubFactoid" for r in result.results)
    assert any(r.type == "Factoid" for r in result.results)

    assert any(isinstance(r, SubFactoid.ReferenceView) for r in result.results)
    assert any(isinstance(r, Factoid.ReferenceView) for r in result.results)

    # Now try with a search
    result: _ListItems = await Factoid.list("John ebr")
    assert result.count == 2

    result: _ListItems = await SubFactoid.list("John ebr")
    assert result.count == 1

    result: _ListItems = await SubFactoid.list("wank off")
    assert result.count == 0


@no_type_check
async def test_list_deep_search(clear_database):

    class Factoid(Document):
        statements: list[Statement]

    class Statement(Document):
        pass

    class Order(Statement):
        thing_ordered: Action

    class Action(Statement):
        action_carried_out_by: Person

    class Person(Entity):
        pass

    initialise()

    p = Person.Create(label="John Smith")
    john_smith = await p.save()
    assert john_smith

    f = Factoid.Create(
        label="A Factoid",
        statements=[
            Order.Create(
                label="An Order",
                thing_ordered=Action.Create(
                    label="An Action",
                    action_carried_out_by=Person.ReferenceSet(id=john_smith.id),
                ),
            )
        ],
    )

    await f.save()

    res = await Person.list(search_terms="act john", deep_search=True)

    assert res.count == 1
    assert res.results[0].id == john_smith.id


"""
// DOCUMENT QUERY
// $tokens: list of tokenised search words
// $targetType: e.g. "Document"
// $page: page number (1-indexed)
// $page_size: results per page

UNWIND $tokens AS token
CALL text_search.search_all("label_index", token) YIELD node AS matchedNode
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

// --- qualifying trees: every token matched somewhere in the tree ---
UNWIND matches AS m
WITH matches, m.treeRootId AS treeRootId, m.token AS token
WITH matches, treeRootId, collect(DISTINCT token) AS treeTokens
WHERE size(treeTokens) = size($tokens)
WITH matches, collect(DISTINCT treeRootId) AS qualifyingRoots

// --- score: distinct tokens matched directly on the node's own label ---
UNWIND matches AS m
WITH qualifyingRoots, m.matchedNode AS scoredNode, m.token AS token
WITH qualifyingRoots, scoredNode, size(collect(DISTINCT token)) AS score
WITH qualifyingRoots, collect({node: scoredNode, score: score}) AS nodeScores

// --- candidates via indexed point-lookups on qualifying roots ---
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

// --- capture total before paging ---
WITH collect({n: n, matchScore: matchScore}) AS allResults
WITH allResults, size(allResults) AS total

UNWIND allResults AS r
WITH r.n AS n, r.matchScore AS matchScore, total
ORDER BY matchScore DESC, n.id
SKIP ($page - 1) * $page_size
LIMIT $page_size

// --- creation/user info via each node's headnode (or itself, if it is one) ---
OPTIONAL MATCH (hn:HeadNode {id: n.head_node_id})
WITH n, matchScore, total, coalesce(hn, n) AS headnode
MATCH (headnode)<-[:is_creation_of]-(creation:PGCreation)
MATCH (creation)-[:created_by]->(user:PGUser)

WITH total, collect(n{.*, meta: {
    created_by: user.username,
    created_when: creation.created_when,
    updated_by: null,
    updated_when: null,
    semantic_spaces: n.semantic_spaces,
    semantic_space_labels: n.semantic_space_labels
}}) AS results

RETURN {
  results: results,
  count: total,
  page: $page,
  page_size: $page_size,
  page_count: toInteger(ceil(toFloat(total) / $page_size)),
  previous_page: CASE WHEN $page > 1 THEN $page - 1 ELSE null END,
  next_page: CASE WHEN $page < toInteger(ceil(toFloat(total) / $page_size)) THEN $page + 1 ELSE null END
} AS response
"""


"""
// ENTITY QUERY
// $tokens: list of tokenised search words
// $targetType: label to filter results by, e.g. "Person"
// $page: page number (1-indexed)
// $page_size: results per page

UNWIND $tokens AS token
CALL text_search.search_all("label_index", token) YIELD node AS matchedNode
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

UNWIND allResults AS r
WITH r.n AS n, r.matchScore AS matchScore, total
ORDER BY matchScore DESC, n.id
SKIP ($page - 1) * $page_size
LIMIT $page_size

OPTIONAL MATCH (hn:HeadNode {id: n.head_node_id})
WITH n, matchScore, total, coalesce(hn, n) AS headnode
MATCH (headnode)<-[:is_creation_of]-(creation:PGCreation)
MATCH (creation)-[:created_by]->(user:PGUser)

WITH total, collect(n{.*, meta: {
    created_by: user.username,
    created_when: creation.created_when,
    updated_by: null,
    updated_when: null,
    semantic_spaces: n.semantic_spaces,
    semantic_space_labels: n.semantic_space_labels
}}) AS results

RETURN {
  results: results,
  count: total,
  page: $page,
  page_size: $page_size,
  page_count: toInteger(ceil(toFloat(total) / $page_size)),
  previous_page: CASE WHEN $page > 1 THEN $page - 1 ELSE null END,
  next_page: CASE WHEN $page < toInteger(ceil(toFloat(total) / $page_size)) THEN $page + 1 ELSE null END
} AS response
"""
