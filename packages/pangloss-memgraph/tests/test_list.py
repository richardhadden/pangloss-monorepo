from typing import no_type_check

import pytest
from pangloss_models import initialise
from pangloss_models.model_bases.base_models import _ListItems
from pangloss_models.model_bases.document import Document
from pangloss_models.model_bases.entity import Entity
from pangloss_models.model_bases.semantic_space import SemanticSpace

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
async def test_a_list_says_which_semantic_spaces_an_item_is_in(clear_database):

    class Negative[T](SemanticSpace[T]):
        pass

    class Factoid(Document):
        statements: list[Statement | Negative[Statement]]

    class Statement(Document):
        pass

    initialise()

    await Factoid.Create(
        label="A Factoid",
        statements=[
            {"type": "Statement", "label": "Plain"},
            {
                "type": "Negative",
                "contents": [{"type": "Statement", "label": "Denied"}],
            },
        ],
    ).save()

    result: _ListItems = await Statement.list()
    by_label = {r.label: r for r in result.results}

    assert by_label["Plain"].meta.semantic_spaces == []
    assert by_label["Denied"].meta.semantic_spaces == ["Negative"]
    assert by_label["Denied"].meta.context_labels[0]["type"] == "Negative"

    # the document it is in
    factoid = (await Factoid.list()).results[0]
    assert by_label["Plain"].meta.is_head_node is False
    assert by_label["Plain"].meta.head_node_id == factoid.id
    assert by_label["Plain"].meta.head_node_type == "Factoid"
    assert factoid.meta.is_head_node is True


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


@no_type_check
async def test_a_deep_search_past_the_end_still_counts_what_was_found(clear_database):
    class Action(Document):
        carried_out_by: Person

    class Person(Entity):
        pass

    initialise()

    john = await Person.Create(label="John Smith").save()
    await Action.Create(
        label="An Action", carried_out_by=Person.ReferenceSet(id=john.id)
    ).save()

    first = await Person.list(search_terms="act john", deep_search=True)
    assert first.count == 1
    assert [r.id for r in first.results] == [john.id]

    past = await Person.list(
        search_terms="act john", deep_search=True, page_number=4, page_size=1
    )
    assert past.results == []
    assert past.count == 1
    assert past.page == 4
    assert past.previous_page == 3

    # (and Documents are listed the same way)
    past = await Action.list(search_terms="act", deep_search=True, page_number=4)
    assert past.results == []
    assert past.count == 1


@no_type_check
async def test_a_deep_search_is_ordered_by_the_label_of_what_is_found(clear_database):
    class Action(Document):
        carried_out_by: Person

    class Person(Entity):
        pass

    initialise()

    # (written in an order that is neither the order of the labels nor one that ids would give)
    people = {
        label: await Person.Create(label=label).save()
        for label in ("Zed Smith", "adam Smith", "Mary Smith")
    }
    for label in ("Beta Action", "alpha Action", "Gamma Action"):
        await Action.Create(
            label=label, carried_out_by=Person.ReferenceSet(id=people["Zed Smith"].id)
        ).save()
    for person in people.values():
        await Action.Create(
            label="Delta Action", carried_out_by=Person.ReferenceSet(id=person.id)
        ).save()

    found = await Person.list(search_terms="action smith", deep_search=True)
    assert [r.label for r in found.results] == ["adam Smith", "Mary Smith", "Zed Smith"]

    found = await Action.list(search_terms="action", deep_search=True)
    assert [r.label for r in found.results] == [
        "alpha Action",
        "Beta Action",
        "Delta Action",
        "Delta Action",
        "Delta Action",
        "Gamma Action",
    ]


"""
// DOCUMENT QUERY
// $tokens: list of tokenised search words
// $targetType: e.g. "Document"
// $page: page number (1-indexed)
// $page_size: results per page

UNWIND $tokens AS token
CALL text_search.search_all("label_text", token) YIELD node AS matchedNode
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
    semantic_spaces: coalesce(n.meta.semantic_spaces, []),
    context_labels: n.meta.context_labels,
    head_node_id: n.head_node_id,
    head_node_type: n.head_node_type,
    is_head_node: n:HeadNode
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
CALL text_search.search_all("label_text", token) YIELD node AS matchedNode
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
    semantic_spaces: coalesce(n.meta.semantic_spaces, []),
    context_labels: n.meta.context_labels,
    head_node_id: n.head_node_id,
    head_node_type: n.head_node_type,
    is_head_node: n:HeadNode
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


@no_type_check
async def test_list_with_nothing_in_it_or_a_page_past_the_end(clear_database):
    class Person(Entity):
        pass

    initialise()

    empty = await Person.list()
    assert empty.results == []
    assert empty.count == 0
    assert empty.page == 1
    assert empty.next_page is None
    assert empty.previous_page is None

    for label in ("One", "Two", "Three"):
        await Person.Create(label=label).save()

    past_the_end = await Person.list(page_number=5, page_size=2)
    assert past_the_end.results == []
    assert past_the_end.count == 3
    assert past_the_end.page == 5
    assert past_the_end.previous_page == 4
    assert past_the_end.next_page is None

    # (a deleted one is not counted)
    first = (await Person.list(page_size=1)).results[0]
    await Person.delete(first.id)
    assert (await Person.list(page_number=9)).count == 2

    # With search terms, nothing found is nothing ...
    assert (await Person.list("nothing like this")).count == 0

    # ... and a page past the end of what was found still says how much there was
    found = await Person.list("T", page_size=1)  # (Two, Three: One was deleted)
    assert found.count == 2
    past = await Person.list("T", page_number=7, page_size=1)
    assert past.results == []
    assert past.count == 2
    assert past.previous_page == 6
    assert past.next_page is None


@no_type_check
async def test_a_page_of_documents_that_refer_to_entities_is_one_page(
    db_driver, clear_database
):
    """(the facets were worked out for each document, and a page of them came back as many)"""

    class Person(Entity):
        pass

    class Statement(Document):
        about: Person

    initialise()

    people = [await Person.Create(label=f"P{i}").save() for i in range(3)]
    for i in range(5):
        await Statement.Create(
            label=f"S{i}", about={"type": "Person", "id": people[i % 3].id}
        ).save()

    page = await Statement.list(page_number=1, page_size=100)
    assert page.count == 5
    assert sorted(r.label for r in page.results) == [f"S{i}" for i in range(5)]
    assert page.next_page is None


@no_type_check
async def test_a_search_with_more_hits_than_the_limit_says_it_was_truncated(
    clear_database, monkeypatch
):
    from pangloss_memgraph.databases.memgraph.database import Database

    class Action(Document):
        carried_out_by: Person

    class Person(Entity):
        pass

    initialise()
    # (a deep search finds an entity by the documents that refer to it)
    for label in [f"Smith {number}" for number in range(5)] + ["Jones"]:
        person = await Person.Create(label=label).save()
        await Action.Create(
            label="An Action", carried_out_by=Person.ReferenceSet(id=person.id)
        ).save()

    # (the limit is for each word; with room for all, nothing is left out)
    for deep in (False, True):
        found = await Person.list(search_terms="smith", deep_search=deep)
        assert (found.count, found.truncated) == (5, False)

    monkeypatch.setattr(Database.default.settings, "SEARCH_HIT_LIMIT", 3, raising=False)
    for deep in (False, True):
        found = await Person.list(search_terms="smith", deep_search=deep)
        assert found.truncated is True
        assert found.count < 5

    # (a word with few hits does not truncate; neither does a list with no search)
    assert not (await Person.list(search_terms="jones")).truncated
    assert not (await Person.list()).truncated
    # (and a search that finds nothing, because of a word with no hits, is not truncated by the other word)
    assert not (await Person.list(search_terms="nobody", deep_search=True)).truncated


@no_type_check
async def test_a_space_at_the_end_of_a_search_is_not_a_word(clear_database):
    class Action(Document):
        carried_out_by: Person

    class Person(Entity):
        pass

    initialise()
    for label in ("Smith", "Jones"):
        person = await Person.Create(label=label).save()
        await Action.Create(
            label="An Action", carried_out_by=Person.ReferenceSet(id=person.id)
        ).save()

    for deep in (False, True):
        found = await Person.list(search_terms="smith ", deep_search=deep)
        assert [r.label for r in found.results] == ["Smith"]
        # (and nothing but spaces is no search)
        assert (await Person.list(search_terms="  ", deep_search=deep)).count == 2


@no_type_check
async def test_a_list_search_that_takes_too_long_is_stopped(
    clear_database, db_driver, monkeypatch
):
    import time

    import pytest
    from pangloss_memgraph.databases.memgraph import exposed_functions
    from pangloss_memgraph.databases.memgraph.database import Database
    from pangloss_models.exceptions import PanglossSearchTimeoutError

    class Person(Entity):
        pass

    initialise()
    with db_driver.session() as session:
        session.run("UNWIND range(1, 400) AS x CREATE (:Filler {id: x})").consume()
    # (a query that cannot end in the time: 64 million combinations)
    slow = (
        "MATCH (a:Filler), (b:Filler), (c:Filler) WITH count(*) AS c "
        "RETURN {results: [], count: c, page: 1, page_size: 25} AS response"
    )
    monkeypatch.setattr(
        exposed_functions, "build_generic_list_query", lambda *a, **k: (slow, {})
    )
    monkeypatch.setattr(
        Database.default.settings, "SEARCH_TIMEOUT_SECONDS", 0.5, raising=False
    )

    started = time.monotonic()
    with pytest.raises(PanglossSearchTimeoutError, match="more specific"):
        await Person.list(search_terms="smith", deep_search=True)
    assert time.monotonic() - started < 3


@no_type_check
async def test_a_read_of_another_package_that_takes_too_long_raises_the_search_timeout(
    clear_database, db_driver, monkeypatch
):
    """The backend translates the timeout, so a package that writes its own query (typology, calendar) catches no driver error"""
    import time

    from pangloss_memgraph.databases.memgraph.database import (
        Database,
        Transaction,
        timeout_from_setting,
    )
    from pangloss_models.exceptions import PanglossSearchTimeoutError

    with db_driver.session() as session:
        session.run("UNWIND range(1, 400) AS x CREATE (:Filler {id: x})").consume()
    monkeypatch.setattr(
        Database.default.settings, "SEARCH_TIMEOUT_SECONDS", 0.5, raising=False
    )

    @Database.default.read_transaction
    @timeout_from_setting("SEARCH_TIMEOUT_SECONDS", 30)
    async def slow(tx: Transaction):
        result = await tx.run(
            "MATCH (a:Filler), (b:Filler), (c:Filler) RETURN count(*) AS c"
        )
        return await result.single()

    started = time.monotonic()
    with pytest.raises(PanglossSearchTimeoutError):
        await slow()
    assert time.monotonic() - started < 3
