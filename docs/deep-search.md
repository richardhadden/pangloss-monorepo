# Deep search: why it is slow, and what to do

Measured 2026-10-28 on the 642,550-node scratch database (Memgraph 3.14.0, `pangloss-memgraph-smoke` on :7689; see [large-data.md](large-data.md)). `GET /api/NAME?q=…&deep=true` ran for 43 to 48 seconds on `Person` with two words. This document says why, what was tried, and what to do. **Status (2026-10-28): steps 1 to 4 below are done.** The deep queries in `build_list_query.py` are rewritten (results ordered by the label of the head node, then id); the text index is asked for up to `SEARCH_HIT_LIMIT` (100,000) hits a word, in deep and plain search, and a list with `q` has `truncated` in its page; the list route has the search timeout and a 504. Measured after, on the scratch database (642,550 nodes, Person and Activity, with `12`, `Person 12`, `e`, `person`, `12 smith`): plain 0.05 to 0.4 s; deep 0.1 to 2.4 s, the slowest being words that match every node. `e` (163,640 hits) is `truncated`, as it should be. Autocomplete was left at the index's default of 1000 (it shows the top of a page, per keystroke). Not done: Memgraph's per-query memory limit, and step 5.

One thing found on the way, not changed: a deep search finds an **entity** only through a document that refers to it, so an entity that no document refers to is never found by `deep=true` (the plain search finds it).

## Summary

1. **The cause we had written down is wrong.** The text index is not slow. `text_search.regex_search("label_text", ".*12.*")` takes 2 to 200 ms, leading wildcard and all: the regex runs over the index's dictionary of distinct words, not over the nodes.
2. **The time goes in the rest of the query** (`build_list_query.py`, the `deep_search` branches). It keeps every hit in a list (`nodeScores`) and carries that list on every row through several `DISTINCT`s and `WITH`s. The work grows with *rows × hits*, and memory with it: a two-word search on `Person` ran for 18 s and was then **killed by Memgraph's memory limit** (the 43 s runs were the ones that happened to finish).
3. **The same query is also wrong, not only slow:** the text index returns at most **1000 hits** a call unless told otherwise, so a search for `12` sees 1000 of the 14,241 labels that contain it. The count and the results are silently short. The plain (non-deep) search and autocomplete have the same cap.
4. **A query that carries no per-row list gives the same answer 30 to 140 times faster** (0.04 s against 5.5 s on `12`; 0.08 s against failure on `Person 12`), and, with the cap lifted, the *complete* answer in 0.9 to 2.3 s even for words that match every node.

So deep search can be made fast with a rewrite of the query and one parameter, with no change to the index, the models or the data. Deeper changes (below) are only needed if deep search is to mean more than "the labels of the nodes in a document".

## What deep search does today

Only `label` is in the text index (`label_text` on `PGIndexableNode(label)`). For each word, `.*word.*` is searched; each hit is resolved to a *root* (a document's head node, or, for a hit on an entity, the documents that point at it); a root qualifies if **every** word has a hit somewhere in its tree. A `Document` list then returns the nodes of the class in those trees; an `Entity` list returns the entities of the class that those trees refer to. The plain search matches the words against the labels of the listed class only.

So "deep" means "the labels of any node in the document, or of an entity it refers to". It does **not** search field values (a `description`, a note): they are not in any index.

## Measurements

| What | Time | Notes |
|---|---|---|
| `regex_search(".*12.*")`, `12.*`, `.*smith.*` | 1 to 3 ms (first call 200 ms) | the leading wildcard costs nothing visible |
| same, `limit` 100,000, 14,241 hits | 24 ms | |
| same, `.*e.*`, `limit` 1,000,000, 163,640 hits | 102 ms | |
| **current deep query**, `Person`, `12` | **5.5 s** | 3,107 results |
| **current deep query**, `Person`, `Person 12` | **18 s, then out of memory** (43 s when it did finish) | tries to allocate 5 GiB in one chunk |
| current deep query, `Activity` (a document), `12` | 1.7 s; `Activity 12` 0.9 s | the document branch is milder |
| prototype, `Person`, `12` (limit 1000) | 0.04 s | same 3,107 results as the current query |
| prototype, `Person`, `Person 12` (limit 1000) | 0.08 s | |
| prototype, `Person`, `12` (limit 100,000) | 0.86 s | **39,300** results: the current query reports 3,107 |
| prototype, `Person`, `e` or `person` (limit 100,000) | 2.1 s, 2.3 s | matches nearly every node: the worst case |
| prototype, `Person`, `12 smith` (no hit for `smith`) | 0.26 s | |

`PROFILE` of the current query on `12` (5.6 s): about 70% of the time is in `Produce`/`Distinct` operators that copy or hash the `nodeScores` list (1000 maps) for each of 3,000 to 9,000 rows; the text search itself is 1.3 ms, and the root lookups by index about 80 ms. The final `[x IN nodeScores WHERE x.node = n | x.score]` is a scan of that list for every row.

Caveats: one machine, one synthetic dataset (labels like `Person 20760`; real labels are more varied, which should help, since fewer words will match everything); only the entity branch was prototyped; the document branch is the same shape.

## Why it behaves like this

- `nodeScores` exists to rank results by how many words their *matched node* matched. Almost every result is a node *inside* a qualifying tree, not a matched node, so its score is 0 and the order is in practice by `n.id`. The list is carried for a ranking that mostly does nothing.
- `WITH DISTINCT n, nodeScores` makes Memgraph hash the whole list for each row.
- Every word multiplies the hits (`Person` alone is 1000 hits, each fanning out to its neighbours).
- The list route has **no timeout** (structured search has `SEARCH_TIMEOUT_SECONDS` and a 504). The container's `query_execution_timeout_sec` is 600, and a browser that gives up does not stop the query.

## The prototype (entity branch)

```cypher
UNWIND $tokens AS token
CALL text_search.regex_search("label_text", token, {limit: $limit}) YIELD node AS m
CALL {
  WITH m WITH m WHERE NOT "Entity" IN labels(m)
  RETURN coalesce(m.head_node_id, m.id) AS root
  UNION
  WITH m WHERE "Entity" IN labels(m)
  MATCH (m)--(nb:PGIndexableNode) WHERE NOT "Entity" IN labels(nb)
  RETURN coalesce(nb.head_node_id, nb.id) AS root
}
WITH root, count(DISTINCT token) AS hit WHERE hit = size($tokens)   // every word, in the one tree
WITH collect(root) AS roots
UNWIND roots AS rootId
CALL {
  WITH rootId MATCH (t:PGIndexableNode {id: rootId}) RETURN t
  UNION
  WITH rootId MATCH (t:PGIndexableNode {head_node_id: rootId}) RETURN t
}
WITH DISTINCT t
OPTIONAL MATCH (t_head:HeadNode {id: t.head_node_id})
WITH t, t_head
WHERE NOT coalesce(CASE WHEN t:Entity THEN t.deleted ELSE coalesce(t_head, t).deleted END, false)
  AND (t:Entity OR $see_unpublished OR coalesce(coalesce(t_head, t).published, true))
MATCH (t)--(n:Entity) WHERE $targetType IN labels(n)
WITH DISTINCT n
WHERE NOT coalesce(n.deleted, false)
WITH collect(n) AS all
RETURN {count: size(all), page: [x IN all[0..50] | x.label]} AS response
```

The difference from the current query: no `matches`/`nodeScores` lists, no ranking, and the roots are reduced to a list of ids before anything is expanded. It leaves out the `published`/`review_status` parameters of the list route, the paging fields and the enrichment (`meta`, creation); those come after the page is cut and are the same in either version. It has not been run through the tests.

## What to do, in order

1. **Rewrite the deep queries as above** (entities and documents), and drop `nodeScores`. *Trade-off:* the order of results changes (today: by an almost always zero score, then `id`). A useful order has to be chosen: by the label of the head node as the plain list does, or "the head node's own label matches" first. *Decision needed.* This is the whole speed-up; the rest is correctness and safety.
2. **Pass `{limit: …}` to `regex_search` explicitly** in deep search, the plain search and autocomplete (autocomplete is only the top of a page, so its cap matters least). Use a ceiling (100,000 is 24 to 70 ms of fetching) and, if it is reached, say so in the response (`truncated: true`) instead of a count that looks exact. *Trade-off:* words that match nearly everything cost 1 to 2.5 s instead of 0.05 s, and the number is real instead of 1000. The alternative, keeping 1000, is fast and wrong.
3. **Give the list route a timeout** like `search` has (`@timeout_from_setting("SEARCH_TIMEOUT_SECONDS", 30)` and the 504), at least for `deep`, and consider Memgraph's per-query memory limit (`QUERY MEMORY LIMIT` at the end of the query; check the syntax on 3.14) so that one search cannot take the database to its limit, as the current one does (the scratch database went from 4 to 24 GiB). *Trade-off:* a slow search ends with an error instead of an answer; with step 1 it should not happen.
4. **Re-measure** on the scratch database after 1 and 2, with the words that match the most (`e`, `person`), and put the table here.
5. **Only if deep search must also search field values, or must be faster still: a `search_text` property on head nodes** (the labels of the document's nodes, optionally more), written in the same transaction, with its own text index, so that deep search is one indexed lookup with no graph walk. *Trade-offs:* more to store; a second text index to pay for at every commit (about 4.5 ms; see [large-data.md](large-data.md)); `search_text` must be rebuilt by a migration and by `bulk-load`; and anything that includes the labels of *entities* would go stale when an entity is renamed, and updating every document that refers to it has no upper bound. Including only the document's own nodes avoids that. Not worth doing before 1 and 2 are measured.

Not recommended: a prefix-only search (no leading wildcard) to "use the index": it already does, it is not where the time goes, and it would lose matches inside words; and a debounce in the interface (the interface already runs deep search only on Enter or the button, which is right until step 1 is done and can then be reconsidered).

## Open questions

- **What should deep search mean?** Labels of nodes in a document (today), or the text of fields too? The second needs step 5.
- **How should results be ranked?** Step 1.
- **Is a result limit acceptable** (step 2), and what ceiling?
- **Real data.** The scratch labels are synthetic; the project's real labels should be tried before the ceiling is fixed.
