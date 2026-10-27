# Structured search: finding documents and entities by pattern 🚧

A planning document. **Steps 1, 2 and 3 of the plan are built** (see [step 1](#step-1-built), [step 2](#step-2-built) and [step 3](#step-3-built)); the rest is not. It is a design for one endpoint that finds **documents and entities** by a pattern written as JSON: "a `Letter` whose `sender` is this person and whose `date` is after 1500, and which mentions a `Place` somewhere". The decisions made so far are at the end; the rest is a recommendation.

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

**A Memgraph fault found on the way:** inside an `EXISTS`, a node found only by `WHERE m.head_node_id = n.id` (a test of one node against another's property) stops the query with "Expected to generate all filters". Putting the id in the pattern, `(m:Label {head_node_id: n.id})`, works, and is what the compiler does (and can use the index on `head_node_id`).

**Speed:** `$somewhere` and `$mentions` look at the nodes of each candidate document. There is an index on `(id, head_node_id)` together; whether the pattern above uses it, or a separate one on `head_node_id` is needed, is to be measured in step 5. `$mentions` on a database of many documents with many nodes each is the first suspect.

**Not done:** wrappers by their own fields (`certainty` of a reified relation: a pattern whose `type` is the wrapper); a condition on the *kind* of wrapper that a pattern's own node is (only `through` and `$spaces`); `$somewhere` inside a nested pattern.
