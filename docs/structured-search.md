# Structured search: finding documents and entities by pattern 🚧

A planning document. **Steps 1 to 5 of the plan are done** (see [step 1](#step-1-built), [2](#step-2-built), [3](#step-3-built), [4](#step-4-built) and [step 5](#step-5-measured)); the interface (6) is not. It is a design for one endpoint that finds **documents and entities** by a pattern written as JSON: "a `Letter` whose `sender` is this person and whose `date` is after 1500, and which mentions a `Place` somewhere". The decisions made so far are at the end; the rest is a recommendation.

What exists today: `list` (by class, label text, and `deep_search`, which regex-searches the text index and resolves hits to head documents) and [autocomplete](autocomplete.md) (entities by label). Neither can say "where *this field* has *that value*".

## What it has to express

From the requirements, for a **document**:

1. a field contains an entity (`sender` is Smith);
2. *any* field contains an entity;
3. a literal field compares to a value (`==`, and `>`/`<` for numbers and dates);
4. a field holds a sub-document that itself matches a pattern (the explicit relation);
5. a sub-document of some type occurs *somewhere* inside the document (not under a named field), and itself matches a pattern.

For an **entity** the same, plus **reverse relations**: the documents (or other entities) that point at it, and relations to other entities, in either direction.

The common shape is a pattern of nodes and edges, each node with a type and conditions: graph pattern matching, written as a JSON tree. Your reading ("like creating a document, with the pinned fields filled in, then queried") is right, and I think it is the best basis. The query for a sub-document *is* the shape of its `Create` model, with each value replaced by a condition.

## Recommendation in short

- **One endpoint**, `POST /api/search` (a body, since a pattern can be large; `GET /api/autocomplete` stays as it is for typing). `search` becomes a reserved model name.
- **The pattern mirrors the document**: a node is `{"type": ..., "where": {field: condition, ...}}`, and a relation field's condition is itself a node pattern, nested as deep as needed. This is what lets the interface reuse the create form (each field gets an operator beside it), and what keeps the JSON readable.
- **One generic, recursive `Match` model**, validated against the models' metadata when the query is compiled (does the field exist on that type; does the operator fit the field's type; is the type an entity or document). Not a generated `Query` model per class: it would double the generated models (five already), and the checks that matter (field and operator against type) need the metadata anyway. The interface gets the fields and operators from `export_models()`, as it does for forms. Revisit if OpenAPI-level typing of queries is wanted.
- **The result is a list of head documents or entities** (best match first, paged, with a total, like `list`), not the matched sub-node. The unit someone opens is the head document. Which sub-node matched can be returned later ("why did this match", for highlighting).
- **Compiled to one parameterised Cypher query** in `pangloss-memgraph`, as `list` and autocomplete are. Field names and types are taken from the models' metadata (never from the request string), and every value is a parameter.

## The JSON

```json
{
  "type": "Letter",
  "where": {
    "sender":   {"is": "0194…"},
    "date":     {"gt": "1500-01-01"},
    "title":    {"contains": "plague"},
    "addressee": {"type": "Person", "where": {"label": {"contains": "smith"}}},
    "$any":     {"is": "0195…"},
    "$somewhere": [
      {"type": "Place", "where": {"label": {"contains": "venice"}}}
    ],
    "$not": {"status": {"eq": "draft"}}
  },
  "page": 1, "page_size": 25
}
```

### Conditions on a field

| Field is | Condition | Meaning |
|----------|-----------|---------|
| literal (`str`) | `eq`, `ne`, `contains`, `starts_with`, `in: [...]`, `exists: bool` | text is compared case-insensitively for `contains` and `starts_with` |
| literal (`int`, `float`, `date`, `datetime`) | `eq`, `ne`, `gt`, `gte`, `lt`, `lte`, `between: [a, b]`, `in`, `exists` | |
| `bool`, `Enum` | `eq`, `ne`, `in`, `exists` | an enum is stored as its value, so it is compared as that |
| `Decimal` | as for numbers | stored as a string, which Cypher cannot compare numerically ([relations](relations.md#literal-fields)), so both sides are converted in the query (decided, see the end) |
| literal list | `contains: value`, `contains_any`, `contains_all`, `exists` | |
| annotated value | the conditions of its value type, applied to `.value`; `certainty` can be named | |
| relation to an entity | `{"is": id}`, `{"is_any": [ids]}`, or a node pattern (`{"type": "Person", "where": {...}}`) | an `id` that is a URL is resolved as elsewhere |
| relation to a document | a node pattern, or `{"exists": true}` | |
| relation, to match the empty list | `{"exists": false}` | |

Several keys in one `where` are all required (AND). `$all` and `$any_of` (a list of `where` maps) combine; `$not` negates one. Several values for one field are `in`/`is_any`, or `$any_of`.

### Whole-node conditions

| Key | Meaning |
|-----|---------|
| `$any` | The condition applies to **any field of this node**: for a relation condition (`is`), any relation field of the node points at it; for text (`contains`), any text field contains it. Not a recursive search of the document |
| `$somewhere` | A list of node patterns, each of which must occur **anywhere in this document's tree** (below the node it is written on). Uses `head_node_id`, which every non-head node carries, so no variable-length path is needed |
| `$incoming` | Reverse relations (below) |
| `$spaces` | The node sits inside all of these semantic spaces (`["Negative"]`): `meta.semantic_spaces` is already on every node inside a space |
| `$id`, `label`, `$created_by`, … | The properties every node has, as ordinary fields (`label` is a field already) |

The difference between `$any` ("a field of this node") and `$somewhere` ("a node of this type below this one") matters and should stay explicit. A third thing people mean by "any field contains Smith" is "Smith appears anywhere in the document", which is `$somewhere` with a pattern of `{"is": id}`; this is worth a short form (`$mentions: id`).

### Reverse relations

An entity (or a document) is matched by what points at it:

```json
{
  "type": "Person",
  "where": {"label": {"contains": "smith"}},
  "$incoming": [
    {"field": "sender", "from": {"type": "Letter", "where": {"date": {"lt": "1600-01-01"}}}}
  ]
}
```

`field` is the relation's name on the source (the model knows its reverse name, `ModelFields.incoming_fields`); it may be left out to mean "any field". The edge pair stored for each relation (`reverse: true` on the second) means a reverse match is an ordinary match on the reverse edge. An entity can be reached from documents through a path (a `Letter` mentions a `Statement` that is about the person); the first version matches **direct** relations only, and "any depth" is `$somewhere` from the document's side.

Edges with properties (`ViaEdge`) can be given conditions the same way, under `"via": {...}` on the relation condition.

### Wrappers

Semantic spaces, conjunctions and reified relations sit between a field and its target as nodes of their own. A relation condition should see **through** them by default (`has_statement` matches a statement inside `Negative[...]`), with `$spaces` to ask about the wrapper and an option to match them exactly. The queries need to know the wrapper types from the field's annotation; this is the part of the compiler I expect to be fiddliest, and it has not been looked into in the code yet.

## Where the work is done

| Layer | Module | Role |
|-------|--------|------|
| Models | `pangloss_models/search/` | The `Match` model (`type`, `where`, `$` keys); `check_match(model, match)`, which walks the pattern against `_meta.fields` and `incoming_fields` and raises a `PanglossSearchError` naming the field and what is wrong; reuses `resolve_entity_types` and `smallest_types` from autocomplete |
| Memgraph | `build_search_query.py`, `exposed_functions.search` | Compile a checked `Match` to Cypher and run it (`read_transaction`), returning the same page shape as `list` |
| API | `routes/search.py` | `POST /api/search`, validation errors as 422, the limits below |
| SDK | `protocol.search`, both flavours | One request; bound as `Document.search(match)` / `Entity.search(match)` (the class gives the root `type`) |
| Interface | later | The create form in "pinned" mode: each field with an operator; serialises to this JSON |

### How a pattern becomes Cypher

Each node pattern becomes a `MATCH` on labels (the class, so subclasses come with it; reduced as autocomplete does), then conditions in `WHERE`. A relation to a pattern becomes a `MATCH (a)-[:field]->(b)` with `b`'s conditions; `exists`/`not` use pattern predicates or `EXISTS { ... }` subqueries (check what Memgraph supports before relying on it). `$somewhere` is `MATCH (n {head_node_id: a.id})` with the sub-pattern; `$any` is `(a)-[r]->(b) WHERE NOT r.reverse` over the relation names the model has. Results are `DISTINCT` head ids, then ordered, counted and paged as in the existing list query (and, as in autocomplete, **collected as maps**, not as nodes).

Order: a search has no text rank to speak of, so default to the same order as `list` (by `label`), with an optional `order_by` on a literal field of the root type. If the pattern has a `label` text condition, the text index score could be used.

## Limits and safety

- It is a read, open to everyone like `list` (to be reconsidered with permissions: documents may later be hidden).
- Nothing from the request reaches Cypher as text: types, fields, reverse names and operators are checked against the models and come from the metadata; values are parameters. That includes the text of `contains` (no regular expression is built from it: use `CONTAINS`/`STARTS WITH` on lower-cased values, or the text index's word search).
- The cost of a pattern is bounded: a maximum depth of nesting, a maximum number of node patterns, a maximum page size, a query timeout. `$somewhere` and `$any` are the expensive ones, and each is only allowed with a type on the root so that the search starts from a label. Exact numbers should come from measuring.
- Speed: `label` text is on the text index; **no other literal is indexed**. A search on `Letter.date` scans the `Letter` nodes, which is fine for thousands and has to be measured on the 600,000-node data ([large data](large-data.md)). The likely help is label+property indexes on chosen fields (set in the model, created by `initialise_database`), and, for "any text field contains", the text index over all text fields that [autocomplete](autocomplete.md#to-do-later) also wants. Each index costs a commit, so these are chosen, not blanket.

## What this does not do (on purpose, for now)

- **Variables across branches** ("a person who is both the sender and a witness"). A tree cannot say the same node appears twice; this needs named nodes (`"as": "p"`, and `{"same_as": "p"}`). It can be added without changing the tree form.
- **Paths of unknown length** between entities (family trees, "within three steps"). Not a document-search problem; separate.
- **Aggregates and group-by** (counts per year).
- **Full text over every field**: waits for the text index.
- **Saved searches**, and a text syntax for the pattern.
- **Oxygen XML**: as for autocomplete, a different answer for the same function, later.
- **Derived data and "descriptions"** ([notes](../notes/descriptions-and-assertions.md)): a stored description is a structured pattern, so this format may well be what is stored. Keep the `Match` model free of anything tied to one request (paging, ordering are around it, not in it) so it can be.

## Plan, in steps that each work alone

1. **One class, literals and entity references.** `Match` model and `check_match`; compile `type` + `where` of literal conditions and `is`/`is_any` on entity relations; the route, `Document.search`/`Entity.search` over Memgraph and the SDK. Tests per operator and per literal type; one live HTTP test.
2. **Nested patterns and combinators.** A relation to a node pattern (entity or document), `$all`, `$any_of`, `$not`, `exists`.
3. **`$any`, `$somewhere`, `$mentions`, `$spaces`, and seeing through wrappers.**
4. **Reverse relations**, so entities can be searched by what refers to them; `via` conditions on edges.
5. **Measure on 600,000 nodes**; add the chosen indexes and the limits.
6. **The interface**: the form in search mode, and the translation of its operators.

## Decisions

Made by the user, 2026-10-27:

1. **Result unit: head documents only.** The matched sub-node is not returned (a "why it matched" could be added later).
2. **A generic `Match` model**, validated against the metadata. A generated `Query` model per class is not made; revisit only if typing of queries in OpenAPI is wanted.
3. **`Decimal` comparisons are converted in the query**: `gt`, `gte`, `lt`, `lte`, `between` are allowed on a `Decimal`, and the stored string and the given value are both converted (`toFloat`) for the comparison only. Nothing stored changes. A float has about 15 significant digits, so two values that differ beyond that compare as equal; that is acceptable for a search and is to be stated in the user docs. `eq`, `ne` and `in` are compared the same way (not on the string, which would make `1.1` differ from a stored `1.10`).
4. **`$any` over relations and `label` first.** Text in every other field waits for the all-text-fields index. A condition such as `Person.label contains "smith"` stays available as a nested pattern, but the **normal path is that the form's entity field has an autocomplete** ([autocomplete](autocomplete.md)), so the user picks the actual entity and the query is `{"is": id}`. That is the case to make cheap and fast; the label pattern is the fallback for when no particular entity is meant ("any Smith").
5. **Variables across branches: later** (`"as"`/`same_as` can be added without changing the tree).
6. **The `$` prefix** for the special keys is kept.

Next: step 1 of the plan.

## Step 1: built

`POST /api/search` with `{"type", "where", "page", "page_size"}`; `Document.search(Match)` and `Entity.search(Match)` (database and SDK); the answer is a page of reference views, as for `list`. Code: `pangloss_models/search.py` (`Match`, `Condition`, `SearchRequest`, `check_match`), `build_search_query.py` and `search` in the Memgraph `exposed_functions`, `routes/search.py`, `protocol.search`.

- **Fields:** `str`, `int`, `float`, `bool`, `Decimal`, `date`, `datetime`, enums, lists of these, and `label` (which every node has), with the operators in the table above. `TypedDict` and annotated-value fields are refused ("cannot be searched yet"), as are `$` keys and relations through a semantic space, a conjunction or a reified relation.
- **Relations:** `is` and `is_any` take entity (or document) **ids**, on the direct edge. A URL in place of an id is not resolved yet.
- **Root:** documents are matched on their head node; entities by their class and subclasses. What is deleted is not found. Order: by label, then id.
- **`ne` also finds the nodes that have no value** ("not draft" includes those without a status).
- **`exists`** is for a literal or a list being present or absent (not yet for a relation); text operators are case-insensitive for `contains` and `starts_with`, not for `eq` and `in`.
- **A field of a subclass** cannot be named when the search is of the parent class (the field is checked against the class searched).
- **Limits so far:** at most 20 fields in a pattern, 100 values in a list, a page of at most 100 (25 by default). No timeout yet.
- **Not measured** on the 600,000-node data. Nothing but `label` is indexed.

## Step 2: built

Nested patterns, the combinators, and `exists` on relations.

- **A relation's condition may be a pattern** for what it points at: `{"type": "Person", "where": {...}}`, **nested as deep as the data goes** (a document can be nested without limit, and an entity is reached through many relations); what is limited is the size of the search: at most 50 such patterns and 500 conditions in all, and the JSON read to 50 levels (so that a hostile body cannot make the reading recurse without end). A pattern nine sections down is one pattern for each. `type` may be a subclass of what the relation allows (`Poet` for a `Person` field); left out, it is the class the relation allows if that is only one (the options are reduced to the classes none of the others is a parent of), otherwise it is needed. A pattern can be given together with `is`/`is_any`/`exists`; all have to hold. The target can be an entity or a document; a deleted entity is not matched by a pattern.
- **One pattern is about one thing.** `{"attachments": {"where": {"size": {"gt": 10}, "name": {"eq": "map"}}}}` needs an attachment that is both. To need two different things, use `$all` with two conditions on the field.
- **`$all`** (a list of `where`s, all of which hold), **`$any_of`** (a list of `where`s, at least one of which holds) and **`$not`** (a `where`, which does not hold as a whole) can be used anywhere a `where` can, and inside one another. `$all` is what allows two conditions on the *same* field (a JSON object cannot have a key twice).
- **`$not` includes what has no value**, as `ne` does: `{"$not": {"pages": {"gt": 4}}}` finds nodes with fewer than 5 pages and nodes without pages.
- **`exists`** now works on a relation (has any / has none).
- **Compiled** with an `EXISTS { MATCH ... }` subquery per relation (checked to work in Memgraph, nested, under `NOT` and `OR`), replacing the `MATCH` + `DISTINCT` of step 1.
- Any other `$` key is refused when the pattern is read (a validation error / 422). Using the model in Python, that is a `ValidationError`; everything else is a `PanglossSearchError`.
- Error messages for a nested pattern name the whole path (`sender.born.gt: ...`).
- **Not measured** for speed; a pattern that begins at a relation's end (`EXISTS` per candidate node) may be slow on the big data. See the plan, step 5.

## Step 3: built

`$any`, `$somewhere`, `$mentions`, `$spaces`, and relations that see through semantic spaces, conjunctions and reified relations.

**How wrappers are stored** (looked at in the graph): a field typed `list[Person | Negative[Person]]` has an edge to a `Negative` node (labels: its name and `SemanticSpace`; no `label`), which has a `contents` edge to the person. A conjunction has its slots (`cause`, `result`) as edges, a reified relation its `target`, and wrappers can be inside one another. The labels `SemanticSpace`, `Conjunction`, `ReifiedRelation` and `ReifiedRelationDocument` are on all such nodes.

- **A relation sees through wrappers, to any depth.** `about: {"is": id}` finds the id whether the field points at it directly or through any number of wrappers; `type` for a pattern is one of the classes at the end (`Person` for the field above), and `exists` is just the edge. A field with no wrapper in its type is compiled as before (one `EXISTS`), so it costs nothing extra.
- **`through: ["Negative", ...]`** on a relation condition: the path to what it points at must pass through *all* of these wrappers (any semantic space, conjunction or reified relation, by its class name). Alone, it means "has a relation, and through these". It is refused for a relation that has no wrapper in its type.
- **`$spaces: ["Negative", "Hypothetical"]`** is of the node: it is inside all of these spaces. Only for a pattern for a *document* that a relation points at (a head document is never inside a space; an entity is not part of a document). It uses `meta.semantic_spaces`. For the *entity* in a space, use `through` on the relation that reaches it.
- **`$somewhere: [pattern, ...]`** (a list of `{"type": ..., "where": ...}`, each of which must occur): a document of that type anywhere in the document searched, at any depth (the nodes of a document all carry the id of their head). Only on the root of a search of documents; the type must be a document type.
- **`$mentions: condition`**: the condition (`is`, `is_any`, a pattern, `through`) holds for a relation of the document's head or of any node in it. This is "Smith appears anywhere in the document". Only on the root of a search of documents.
- **`$any: condition`**: the same, for a relation of this node only (not the rest of the document); usable at any level (`type` is needed for a pattern, as there is no field to say it). `contains` and `starts_with` are of this node's `label` (the text of the other fields is not indexed).
- **The edges followed** for `$any` and `$mentions` are all the outgoing relation edges to nodes of the model (not the reverse edges, nor the URL nodes). Only the field the condition names is followed for a named field.

**A Memgraph fault found on the way:** inside an `EXISTS`, a node found only by `WHERE m.head_node_id = n.id` (a test of one node against another's property) stops the query with "Expected to generate all filters". Putting the id in the pattern, `(m:Label {head_node_id: n.id})`, worked, but is not what the compiler does now (see step 5: it scanned every node).

**Speed:** this compilation of `$somewhere` and `$mentions` (and of `$incoming`) was too slow, and was changed in step 5: see [step 5](#step-5-measured).

**Not done:** wrappers by their own fields (`certainty` of a reified relation: a pattern whose `type` is the wrapper); a condition on the *kind* of wrapper that a pattern's own node is (only `through` and `$spaces`); `$somewhere` inside a nested pattern.

## Step 4: built

**`$incoming`** finds an *entity* by what refers to it: a list of patterns (or one), each of which has to be met by a node, and different patterns can be met by different nodes.

```json
{"type": "Person", "where": {"$incoming": [
  {"type": "Letter", "field": "sender", "where": {"date": {"lt": "1600-01-01"}}}
]}}
```

- **`type`** (needed): the class of the node that refers to it, a document (including one that is inside another document: the statements of a factoid) or an entity. It may be a parent class; its subclasses are found.
- **`field`** (optional): the relation of that class, by its own name (`sender`), not the reverse name. Left out, any relation of the class that can point at the entity (the entity's class or a parent or subclass of it); if the class has none, that is an error. A `field` that cannot point at the entity is refused, saying which fields can.
- **`where`**: a pattern for the referring node, checked against its class like any other (so `$incoming` can nest, and a relation of the referring node can have a pattern).
- **`through`**: as for a relation. If a relation of the class passes through wrappers (`Negative[Person]`), a node is found whether it refers directly or through them; with `through`, only through all of those named.
- Used as `$not: {"$incoming": [...]}`: entities nothing of that kind refers to. In a pattern for what a relation points at, it is a condition of that entity (letters whose sender is in an organisation).
- **Deleted** documents (and documents inside a deleted head document) and deleted entities refer to nothing.
- **Only an entity is referred to** (a document is not looked up by what contains it); the search must be of an entity or a pattern for one.
- **Not covered:** a relation in an *embedded* object of the referring document (the edge starts from the embedded node, not the document; the relation is not seen as one of the document's); a chain through several referring nodes ("referred to by a document that is referred to by...") is written by nesting `where` with a relation or `$incoming`.
- The reverse edge (`reverse: true`) is not used: the edge from the referring node is followed backwards, so the reverse names need not be known.

## Step 5: measured

Measured on 2026-10-27 on the data of [large data](large-data.md) (642,549 nodes, 1,649,526 edges: 100,000 entities, 30,000 factoids with 2 or 3 statements, some wrapped in `Negative`, `Hypothetical` or `Causes`), Memgraph 3.13.1 in Docker on a laptop, one search at a time. The script is `pangloss-demo/search_benchmark.py` (see the end of this section). Times are the shortest of two runs, through the models, for a page of 25 and the count of everything found.

### What was wrong, and what it was

The first measurement, of the compiler of steps 3 and 4, **timed out on every search that used `$mentions`, `$somewhere` or `$incoming`** (at 20 seconds; 90 for the first tries). The plans (`EXPLAIN`) showed why, and it was not a lack of an index:

- Inside an `EXISTS { ... }`, **a node found by `(m {head_node_id: n.id})`, or `WHERE m.head_node_id = n.id`, is found by looking at every node** (`ScanAll`) for each candidate, with or without an index on `head_node_id`. The same pattern outside an `EXISTS` (a `MATCH`, or a `CALL { WITH n ... }`) uses the index (`ScanAllByLabelProperties`): 100 documents took 11 ms there and 8,175 ms inside `EXISTS`. An index on `head_node_id` made no difference to the searches, which is why it is not recommended below.
- `$incoming` was written from the referring node (`(s:Activity)-[...]->(entity)`), so Memgraph scanned every node, kept the activities, and looked for an edge to the entity, for each entity. The deleted-head check (`(h:HeadNode {id: s.head_node_id})`) was the same fault.

The compiler then never looked a node up by property inside an `EXISTS`: it **walked from the node it already had**. **Memgraph 3.14.0 uses the index there** (measured 2026-10-28: 100 rows, 200,000 nodes, 2,001 ms on 3.13.1 and 20 ms on 3.14.0, if the pattern names the label), so `$somewhere` and `$mentions` now find the nodes of a document by `head_node_id` (index `PGIndexableNode(head_node_id)`, migration `pangloss_memgraph.0003_addindex`): see [the 3.14 result](#after-memgraph-314) below.

| Condition | Is compiled as |
|-----------|----------------|
| `$somewhere`, `$mentions` | (Memgraph 3.13; now by `head_node_id`, see below.) From the document's head node down the edges of the document: `(n)-[* (r, v \| v.head_node_id = n.id AND NOT r.reverse)]->(m:Type)` (not along reverse edges, which would make every path up and down the tree) |
| `$incoming` | From the entity back along its edges: `(n)<-[:field]-(s:Type)`; a deleted head document is found by going up the reverse edges from the source to its head |
| Relations (named or `$any`) | As before: from the node, along the edge |

### The result, with no indexes beyond those Pangloss makes

| Search | Time | Found |
|--------|------|-------|
| a person by `label`, `contains` or `eq`; a group by `name`; the 100 sources by `author` | 33 to 46 ms | 1 to 100 |
| every person (60,000), every factoid (30,000), all factoids not of a year | 46 to 70 ms | up to 60,000 |
| a factoid by `year` (134 found), a range of years (899), an `$any_of` of two years | 38 to 43 ms | |
| a factoid by its `source` (through a reified relation), by a pattern for it | 90 to 96 ms | 6; 574 |
| a factoid with an activity by a person (a hub of 20,006 as well as an ordinary one) | 107 to 109 ms | |
| a factoid with a statement inside a `Negative` (4,112); with any statement through one (5,702) | 81 to 158 ms | |
| `$mentions` a person, a place, or a person found by a pattern | 440 to 560 ms | 4 to 10,345 |
| `$somewhere` a transfer (17,912 found), with a condition on it | 190 to 275 ms | |
| a person by what refers to them: one person, or all who are in an activity | 60 ms; 125 ms | 1; 30,929 |
| the same, for activities of one year; places that any statement refers to | 85 ms; 90 ms | 278; 19,623 |

The searches that are not tied to an index look at every node of the class: **a search costs about the number of nodes in the database for a root of a class, and about the number of documents for `$mentions` and `$somewhere`**. A hub (one person referred to by 20,006 activities) costs nothing extra to any of them, because a search stops at the first edge that makes it true, and `$mentions` walks the document, not the entity's edges. Not measured: more than one search at once; a hub in a search that has to look at all of its edges (`$incoming` for a class that has none, which took 50 ms for the 20,006).

### Which indexes help

Done by hand on the same data, with the query as the compiler writes it (`MATCH (n:Factoid:HeadNode) WHERE NOT coalesce(n.deleted, false) AND n.year = 800`):

| Index | A search of a class | One property equal to a value | Others |
|-------|---------------------|-------------------------------|--------|
| None | `ScanAll`: **33 ms** (every node: 642,549) | 35 ms | |
| A label index (`CREATE INDEX ON :Factoid`) | `ScanAllByLabel`: **10 to 13 ms**, and the time is that of the class, not of the database | 10 to 12 ms | |
| A label-and-property index (`CREATE INDEX ON :Factoid(year)`) | not used for a search of the whole class (needs the label index) | **0.3 ms** | the planner uses it by itself |
| An index of `head_node_id` | | | no difference (see above) |
| An index for each edge type (`CREATE EDGE INDEX ON :carried_out_by`, twelve of them) | | | **no difference to any search**, including the hub: every search starts from a node it has, or scans a class, and goes along the edges of that node; an edge index would only be used by a search that started from the edges of a type |

Through the whole search (page of 25, the count, and the creation record of each):

| Search | No indexes | Label indexes | Label and property |
|--------|-----------|---------------|--------------------|
| factoid by `year` (134 found) | 41 ms | 12 ms | 4 ms |
| 100 sources by `author` | 35 ms | 3 ms | 4 ms |
| person by `label` | 37 ms | 10 ms | 32 ms |
| every factoid | 47 ms | 27 ms | 26 ms |

(The person `label` row: that run had an index on `Person(label)` which the whole-query planner did not use; by hand it did, at 0.3 ms. Not understood, probably the plan cache after the index was made.)

What an index costs to write, bare nodes in one transaction each: 3,975 a second without, 3,230 with a label index and a property index (about 0.06 ms a node). The text index costs 4.5 ms a commit, so these are small beside it.

**Recommendation (done: see "Indexes of the models" below):** (1) **a label index for each class of document and entity** (the class name of every `Document` and `Entity` model, including abstract parents, which a search of a parent class starts from): cheap, and the cost of a search of a class stops growing with the rest of the database. (2) **A label-and-property index on a field when a project searches by it a lot** (`year`, `author`, an identifier): 100 times faster, and a choice for the project, so a setting of the model rather than of Pangloss. (3) No edge indexes, and (on Memgraph 3.13) no `head_node_id` index; on 3.14 there is one, see [After Memgraph 3.14](#after-memgraph-314). These need a change to the structure that [migrations](migrations.md) keep (`initialise_database.structure()`), which is not made; see the questions below.

### Limits

- **A timeout.** `SEARCH_TIMEOUT_SECONDS` (30 by default; 0 for none) is sent with the transaction and Memgraph stops the query. Found on the way: Memgraph reports it as a *transient* error, and the driver **tries a transient error again** with waits of seconds, so a search that was too big took 15 seconds for a 2-second limit, and twice the limit in the first measurements. The search turns it into `PanglossSearchTimeoutError` itself, which the driver does not try again; the API answers it with a **`504`** (`error: PanglossSearchTimeoutError`) and the SDK raises the same class. Other reads are not limited by this.
- **Page size** is at most 100; the count is of the whole result, so a search is as costly for page 1 as for the last: the whole result is found, ordered and counted (30,000 documents: 46 ms). A result of millions would be more.

### Repeating it

On a scratch Memgraph (not one to keep: it makes and drops indexes), with the data of `bulk_load.py` ([large data](large-data.md#repeating-it)):

```bash
cp pangloss-demo/search_benchmark.py /tmp/smoke/ && cd /tmp/smoke
PYTHONPATH=. python search_benchmark.py --repeat 2 --timeout 40            # all the searches
PYTHONPATH=. python search_benchmark.py --indexes label property --profile  # with indexes, and the plan of each
PYTHONPATH=. python search_benchmark.py --explain --only mentions           # a plan, without running it
PYTHONPATH=. python search_benchmark.py --drop-indexes
```

### Indexes of the models (decided and built)

Decided 2026-10-27, after the measurements above:

- **A label index for each class of document and entity**, abstract ones too (a search of a parent class starts at its label). Made by `initialise_database()` and by migrations: the entries are in the structure of the snapshot (`kind: "label"`, no properties), the app of the model makes them (a new class is an `AddIndex` in the migration of its app; a class removed, a `RemoveIndex`). `pangloss_models.indexes.model_indexes()` lists them.
- **`Meta(indexes=["year"])`** on a document or entity: a label-and-property index of each field named (any literal field or list of literals, or `"label"`). Not inherited. Checked when the models are initialised (`PanglossMetaError` for a field that does not exist, a relation or other field with no property of its own, or a name twice). The demo asks for `Factoid.year`.
- **Measured on the same data after the demo's migration** (`demo_app.0002_addindex_addindex_addindex`: nine label indexes and `:Factoid(year)`): a factoid by year 41 to 3 ms, 100 sources 35 to 3 ms, every factoid 47 to 25 ms, a person by what refers to them 60 to 16 ms; `$mentions` and `$somewhere`, which walk the documents, did not change.
- **An existing database needs the migration**: `pangloss makemigrations` and `pangloss migrate` after updating (the server refuses to start while the models and the migrations differ, unless `MIGRATION_CHECK` is `warn` or `off`).

### Timeout

One timeout, `SEARCH_TIMEOUT_SECONDS`, for every search and every user, is what is wanted for now. A different one for some users or routes (lower for anonymous users, longer for an export) is not built.

## Embedded objects and ordering (built with `pangloss-dates`)

- **Embedded fields are searched like a relation**: `{"when": {"type": "JulianExactDate", "where": {"sort_day": {"between": [a, b]}}}}`. The `type` may be left out when the field is typed with one class (the class itself, even if abstract, is allowed: `JulianDate` matches every kind in the family, since the nodes carry their parents' labels). Embedded objects inside embedded objects work the same way. There is no deleted check and no wrappers (an embedded object is part of its document).
- **`order_by`** (in `Match`, so in the request body and in `Document.search(...)`): up to 3 of `{"field": "label" | "year" | "when.sort_day", "direction": "asc" | "desc"}`. A field is a text, number, decimal or date of the class, or of an embedded object in it (the class the field is typed with must have it; a kind of embedded object that lacks the value comes last). Results with no value come last either way; ties are ordered by label, as before. Compiled with an `OPTIONAL MATCH` per embedded object on the way, so a document without one is not left out.

## Published and reviewed (built with `pangloss-review`)

A search of a **head document** class can use two more fields, as ordinary conditions:

```json
{"type": "Letter", "where": {"published": {"eq": false}, "review_status": {"in": ["unchecked", "errors_found"]}}}
```

- `published` (a bool; a document with no property is published) takes `eq`, `ne`, `in`, `exists`.
- `review_status` (`unchecked`, `errors_found` or `checked`; none for a document of a class that is not reviewed) is
  text: `eq`, `ne`, `in`, `exists`, `contains`, `starts_with`.
- They are the head's own properties, so they are allowed only at the top of the pattern (also inside `$all`,
  `$any_of` and `$not`), not for what a relation points at, and not in a search of entities. A model that has a
  field of the same name keeps its own meaning for it (but do not call a field `published`: the property is the
  one that hides a document).
- The search still hides what a request may not see: for one that is not logged in, `published: {eq: false}`
  finds nothing. See [Review](review.md).

### After Memgraph 3.14

On the same 642,550 nodes (the `search_benchmark.py` run, no other change), with the index `PGIndexableNode(head_node_id)` and the nodes of a document found by it (`(m:PGIndexableNode:Transfer {head_node_id: n.id})`) instead of walked to:

| Search | 3.13, walking | 3.14, by `head_node_id` |
|--------|---------------|-------------------------|
| `$somewhere` a transfer (17,912 found) | 175 ms | 93 ms |
| the same with a condition on it | 177 ms | 94 ms |
| `$somewhere` a transfer given by a busy person | 251 ms | 106 ms |
| `$mentions` a busy person, an ordinary one, a place | 496 to 499 ms | 400 to 405 ms |
| `$mentions` a person found by a pattern | 518 ms | 433 ms |

The same documents are found in every case. `$mentions` gains less because most of its time is the test of each of the 287,505 nodes of the 30,000 documents (the plan, `--profile`, shows it in the filters of the relation, not in the scan). A search that **started from the entity** (the nodes that refer to it, then their heads) was 3 to 8 ms on a synthetic dataset, but cannot be had for every condition (a pattern, `$not`, wrappers); it is not built. `search_benchmark.py --profile` printed the times of 3.14's `PROFILE` as text and failed; it now prints them as they are.
