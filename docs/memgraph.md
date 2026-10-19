# Memgraph backend

Package: `pangloss-memgraph` (module `pangloss_memgraph.databases.memgraph`). Select it with `DATABASE_MODULE = "pangloss_memgraph.databases.memgraph"` and a `MemgraphDatabaseSettings`.

Requirements: a Memgraph server with the **MAGE** library (the read query uses `convert_c.to_tree`, `graph_util`, and the text-search module), started with `--storage-properties-on-edges=true`.

## Modules

| Module | Role |
|--------|------|
| `database.py` | `Database` class: holds settings and a `neo4j.AsyncDriver`; provides `read_transaction` and `write_transaction` decorators |
| `exposed_functions.py` | The functions bound to the models: `list_items`, `get_document`, `create_head_node` (plus the internal `write_head_node`) |
| `build_create_query.py` | Turns a `CreateDB` instance into one Cypher statement (`build_head_create_query`) |
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
| `(:PGUser {username})` | Must already exist. The writer matches on `current_request_username` and creates nothing if the user is missing, so make sure the user node exists first (the tests `MERGE` it) |

### Property values

Values are converted by `convert_type_for_writing`: UUIDs and URLs become strings, `Decimal` becomes a string, an `Enum` becomes its value, and sets, tuples, lists and dicts (including `TypedDict`s) are converted recursively. `None` is never written. Edge properties are converted in the same way.

A text index on `:PGIndexableNode(label)` named `label_index` is required for listing and search:

```cypher
CREATE TEXT INDEX label_index ON :PGIndexableNode(label);
```

## Operations

All are `async`.

### `create_head_node(instance, return_type="Reference")` ✅

Called by `.save()`. Converts the `Create` instance to `CreateDB`, builds one query (`CREATE` for the head and its creation record; `MERGE` for nested documents keyed on `id`; `MATCH` + `CREATE` for edges to existing entities, restricted to the field's allowed types), and runs it in a write transaction.

- **Existing nodes** are matched on `id`, or, if the reference gives a URL, on `$url IN node.urls`. If any referenced node does not exist or is not of an allowed type, nothing is written (a write is all-or-nothing).
- **Generic wrappers** (reified relations, semantic spaces, conjunctions): the allowed types of their contents (such as `target: list[T]`) come from the field that uses the wrapper, e.g. `Proxy[Person]`.
- **Inline entities** are `MERGE`d on `id`, so an entity that already exists is not duplicated or changed.

- `return_type="Reference"` returns the `ReferenceView` straight from the in-memory object, with `meta.created_by` set from `current_request_username`.
- `return_type="Full"` re-reads the node and returns the `HeadView`.
- The `"Detail"` literal is accepted by the registry's wrapper signature but not handled here.

### `get_document(cls, id)` ✅

Matches `PGIndexableNode` by `id` and type label, then collects paths to entities and nested documents with `BFS` expansions, converts them to a tree with `convert_c.to_tree`, and adds `meta`. Returns `cls.HeadView`, or `None` if not found. Only documents are supported; ⏳ `Entity.get`. Known read-side gaps (covered by expected-failure tests): a conjunction field is not returned, and a `date` field fails validation (`convert_neo4j_datetimes` converts `DateTime` but not `Date`).

### `list_items(cls, search_terms=None, page_number=None, page_size=None, deep_search=False)` ✅

Returns `_ListItems` of `ReferenceView`s of all concrete subtypes of `cls`. Default page size 50.

- Without `search_terms`: plain pagination.
- With `search_terms`: label search through the text index.
- With `deep_search=True`: each space-separated token is regex-searched (`.*token.*`); a hit on a nested node resolves to its head node, and a hit on an Entity resolves to the documents that reference it.

### Transactions

`Database.read_transaction` / `write_transaction` open a session per call. Write failures of type `TransactionError` are printed and the result is `None`. `max_transaction_retry_time` is 10 seconds.

## Known rough edges

- `exposed_functions.py` writes each generated query to `.query_dumps/*.cypher` (git-ignored) and prints timings and debug output. The `.query_dumps` directory must exist.
- `save(tx, ...)` in this module is a placeholder that prints.
- Updating existing objects is not implemented (see [Status](status.md)).
- `Database.default` is set by the last `Database(...)` constructed, and `exposed_functions` decorates with `Database.default` at import time, so the settings/`Database` must be created before the module is first imported (which `initialise()` does when binding).
