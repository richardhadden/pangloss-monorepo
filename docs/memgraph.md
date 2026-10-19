# Memgraph backend

Package: `pangloss-memgraph` (module `pangloss_memgraph.databases.memgraph`). Select it with `DATABASE_MODULE = "pangloss_memgraph.databases.memgraph"` and a `MemgraphDatabaseSettings`.

Requirements: a Memgraph server with the **MAGE** library (the read query uses `convert_c.to_tree`, `graph_util`, and the text-search module), started with `--storage-properties-on-edges=true`.

## Modules

| Module | Role |
|--------|------|
| `database.py` | `Database` class: holds settings and a `neo4j.AsyncDriver`; provides `read_transaction` and `write_transaction` decorators |
| `exposed_functions.py` | The functions bound to the models: `list_items`, `get_document`, `create_head_node`, `update_head_node` (plus the internal `write_head_node` and `replace_head_node`) |
| `build_create_query.py` | Turns a `CreateDB` (or `UpdateDB`) instance into one Cypher statement (`build_head_create_query`); also the code, shared with updates, that writes everything below a head node |
| `build_update_query.py` | The queries for an update: find the head node, collect `meta` of its tree, replace the head node and delete its tree, and write the new version (`build_head_update_query`) |
| `validate_write.py` | Checks made inside a write transaction before anything is written (user, references, ids, the document being updated) |
| `build_read_query.py` | `build_fetch_document_query` |
| `build_list_query.py` | `build_generic_list_query`: pagination, text search, and deep search |
| `settings.py` | `MemgraphDatabaseSettings` |
| `indexes.py` | Empty. ⏳ Index creation is currently done in the test fixtures |

## Graph schema

**Everything that is not a literal value is stored as a node**: documents, entities, embedded objects, reified relations, semantic spaces and conjunctions alike. Only literal fields (see [Literal fields](relations.md#literal-fields)) are stored as node properties; every other field becomes a relation to such a node. Embedded objects and annotated values are nodes too, joined by an edge pair named like a relation's (`<field>` and `<field>_reverse`).

| Element | Meaning |
|---------|---------|
| Node labels | Class name, each parent class name, the kind (`Document`, `Entity`, ...), plus `PGIndexableNode` on everything and `HeadNode` on the top-level node |
| Node properties | `id`, `type`, `label`, the literal fields that are not `None`, `urls` (for entities created with URL ids), `meta` (`created_by`, `created_when`, `updated_*`, `semantic_spaces`, `context_labels`; times are UTC), and on non-head nodes `head_node_id` / `head_node_type`. Annotated-value nodes have `id`, `type`, `head_node_*` and their fields, but no `meta` |
| Relation edges | `(a)-[:field_name]->(b)` and `(a)<-[:reverse_name {reverse: true}]-(b)`; edge properties from a `ViaEdge` are added to both, and the `reverse: true` marker is kept |
| `(:PGCreation)` | One per head node, with `id` and `created_when`; linked `(creation)-[:is_creation_of]->(head)` and `(creation)-[:created_by]->(:PGUser)` |
| `(:PGUpdate)` | One for each update of a head node, with `id` and `updated_when`; linked `(update)-[:is_update_of]->(head)` and `(update)-[:updated_by]->(:PGUser)`. `get_document` reports the latest as `meta.updated_by` / `meta.updated_when` |
| `(:PGUser {username})` | Must already exist: a write as a user with no node raises `PanglossUserNotFoundError`. (The tests `MERGE` it) |

### Property values

Values are converted by `convert_type_for_writing`: UUIDs and URLs become strings, `Decimal` becomes a string, an `Enum` becomes its value, and sets, tuples, lists and dicts (including `TypedDict`s) are converted recursively. `None` is never written. Edge properties are converted in the same way.

A text index on `:PGIndexableNode(label)` named `label_index` is required for listing and search:

```cypher
CREATE TEXT INDEX label_index ON :PGIndexableNode(label);
```

## Operations

All are `async`.

### `create_head_node(instance, return_type="Reference")` ✅

Called by `.save()`. Converts the `Create` instance to `CreateDB`, builds one query (`CREATE` for the head and its creation record; `MERGE` for nested documents keyed on `id`; `MATCH` + `CREATE` for edges to existing entities, restricted to the field's allowed types), checks it (see [Checks before writing](#checks-before-writing)), and runs it in a write transaction.

- **Existing nodes** are matched on `id`, or, if the reference gives a URL, on `$url IN node.urls`. A write is all-or-nothing: if anything it refers to is missing, nothing is written, and the error says which reference.
- **Generic wrappers** (reified relations, semantic spaces, conjunctions): the allowed types of their contents (such as `target: list[T]`) come from the field that uses the wrapper, e.g. `Proxy[Person]`.
- **Inline entities** are `MERGE`d on `id`, so an entity that already exists is not duplicated or changed.

- `return_type="Reference"` returns the `ReferenceView` straight from the in-memory object, with `meta.created_by` set from `current_request_username`.
- `return_type="Full"` re-reads the node and returns the `HeadView`.
- The `"Detail"` literal is accepted by the registry's wrapper signature but not handled here.

### `update_head_node(instance, return_type="Reference")` ✅

Called by `.save()` on a `Document.Update` or `Entity.Update`. **An update is a full replacement of the document, not a patch**: anything left out of the payload is removed. It does not work out what has changed; it deletes the tree and writes the new one, in one transaction:

1. **Check**, before anything is deleted: the user exists; the head node exists and has the given type (`PanglossNotFoundError`); everything referred to exists (`PanglossReferenceError`); no id in the payload belongs to a node outside this document (`PanglossConflictError`). If any check fails, nothing has changed.
2. **Collect `meta`** of every node already below the head node, so that nodes given again keep `created_by` and `created_when`. Their `updated_by` and `updated_when` are set.
3. **Replace the head node**: delete every node below it, except entities, and delete the edges it owns; then replace its properties. (Its `urls` are kept.) The head node itself is kept, with its `PGCreation`.
4. **Write the new tree**, with the same code as a creation, and add a `PGUpdate` node.

What is deleted, and what is not:
- Nodes are found by walking forward edges from the head node, without entering entities. These are the nested documents, embedded objects, annotated values, semantic spaces, conjunctions and reified relations.
- **Entities are never deleted**, including entities created inline by this document, as other documents may refer to them. An update only removes and re-creates the *edges* to them. A new inline entity in an update (`create_new`) is created; one that exists is left as it is.
- A node owns its outgoing edges that are **not** marked `reverse: true`, and the incoming edges that are. So when an entity is updated, the edges from documents *to* it are kept, and only its own relations are replaced.
- Nodes given with an existing `id` keep that id (and so can be referred to), nodes given without one get a new id, and nodes left out are gone.

`return_type` is as for creation; `"Reference"` returns the `ReferenceView` with `meta.created_by`, `created_when`, `updated_by` and `updated_when`.

### Checks before writing

`validate_write.py` runs these in the write transaction, so that a write that cannot succeed raises a `PanglossWriteError` subclass rather than silently doing nothing (or, for an update, deleting data and writing nothing):
- the user exists;
- each reference to an existing entity exists, and has one of the types allowed in that field;
- the ids of new nodes are free: for a creation, the head id and the ids of all nested documents; for an update, they may also belong to the document being updated, but not to any other node. (Entities created inline are not checked, as one that already exists is simply used.)

### `get_document(cls, id)` ✅

Matches `PGIndexableNode` by `id` and type label, then collects paths to entities and nested documents with `BFS` expansions, converts them to a tree with `convert_c.to_tree`, and adds `meta`. Returns `cls.HeadView`, or `None` if not found. Only documents are supported; ⏳ `Entity.get`. Known read-side gaps (covered by expected-failure tests): a conjunction field is not returned; a `date` field fails validation (`convert_neo4j_datetimes` converts `DateTime` but not `Date`); and a nested document with no entity or further document below it is not returned.

### `list_items(cls, search_terms=None, page_number=None, page_size=None, deep_search=False)` ✅

Returns `_ListItems` of `ReferenceView`s of all concrete subtypes of `cls`. Default page size 50.

- Without `search_terms`: plain pagination.
- With `search_terms`: label search through the text index.
- With `deep_search=True`: each space-separated token is regex-searched (`.*token.*`); a hit on a nested node resolves to its head node, and a hit on an Entity resolves to the documents that reference it.

### Transactions

`Database.read_transaction` / `write_transaction` open a session per call. If a write function raises, its transaction is rolled back and the exception propagates (the checks above rely on this to leave data untouched). Transient conflicts, such as two updates of the same document at once, are retried by the driver for up to `max_transaction_retry_time` (10 seconds); the last write wins.

## Known rough edges

- `exposed_functions.py` writes each generated query to `.query_dumps/*.cypher` (git-ignored; the directory is created if missing) and prints timings and debug output.
- Updates need `id`s to be looked up without an index: `PGIndexableNode(id)` should be indexed by the (not yet written) database setup command, as should `head_node_id`.
- Deleting objects is not implemented (see [Status](status.md)).
- `Database.default` is set by the last `Database(...)` constructed, and `exposed_functions` decorates with `Database.default` at import time, so the settings/`Database` must be created before the module is first imported (which `initialise()` does when binding).
