# Memgraph backend

Package: `pangloss-memgraph` (module `pangloss_memgraph.databases.memgraph`). Select it with `DATABASE_MODULE = "pangloss_memgraph.databases.memgraph"` and a `MemgraphDatabaseSettings`.

Requirements: a Memgraph server with text search (the `text_search` module), supporting native enums, started with `--storage-properties-on-edges=true`. (Reading does not use MAGE's `convert_c.to_tree`, which cannot handle enum values.)

## Modules

| Module | Role |
|--------|------|
| `database.py` | `Database` class: holds settings and a `neo4j.AsyncDriver`; provides `read_transaction` and `write_transaction` decorators |
| `exposed_functions.py` | The functions bound to the models: `list_items`, `get_document`, `create_head_node`, `update_head_node` (plus the internal `write_head_node` and `replace_head_node`) |
| `build_create_query.py` | Turns a `CreateDB` (or `UpdateDB`) instance into one Cypher statement (`build_head_create_query`); also the code, shared with updates, that writes everything below a head node |
| `build_update_query.py` | The queries for an update: find the head node, collect `meta` of its tree, replace the head node and delete its tree, and write the new version (`build_head_update_query`) |
| `read_incoming.py` | Reads the relations *to* an entity, for `get_entity` |
| `delete_node.py` | Deleting (flagging) a head document or an entity, or marking an entity that is referred to |
| `lookup.py` | `resolve_id`: the id of a node, given its id or a URL |
| `build_tree.py` | Makes the nodes and edges returned by the read query into a nested dict |
| `read_enums.py` | Turns the enums returned by the database (dicts such as `{"__type": "mg_enum", "__value": "Colour::RED"}`) into members of the models' enums |
| `validate_write.py` | Checks made inside a write transaction before anything is written (user, references, ids, the document being updated) |
| `build_read_query.py` | `build_fetch_document_query` |
| `build_list_query.py` | `build_generic_list_query`: pagination, text search, and deep search |
| `settings.py` | `MemgraphDatabaseSettings` |
| `indexes.py` | Empty. ⏳ Index creation is currently done in the test fixtures |

## Graph schema

**Everything that is not a literal value is stored as a node**: documents, entities, embedded objects, reified relations, semantic spaces and conjunctions alike. Only literal fields (see [Literal fields](relations.md#literal-fields)) are stored as node properties; every other field becomes a relation to such a node. Embedded objects are nodes too, joined by an edge pair named like a relation's (`<field>` and `<field>_reverse`). An annotated value is the exception: it is a map property on the node it belongs to (`name: {value: "John", certainty: 2}`), because it holds only literals.

| Element | Meaning |
|---------|---------|
| Node labels | Class name, each parent class name, the kind (`Document`, `Entity`, ...), plus `PGIndexableNode` on everything and `HeadNode` on the top-level node |
| Node properties | `id`, `type`, `label`, the literal fields that are not `None`, `meta` (`created_by`, `created_when`, `updated_*`, `semantic_spaces`, `context_labels`; times are UTC), and on non-head nodes `head_node_id` / `head_node_type`. Annotated values are stored as map properties, named after their field |
| Relation edges | `(a)-[:field_name]->(b)` and `(a)<-[:reverse_name {reverse: true}]-(b)`; edge properties from a `ViaEdge` are added to both, and the `reverse: true` marker is kept |
| `(:PGCreation)` | One per head node, with `id` and `created_when`; linked `(creation)-[:is_creation_of]->(head)` and `(creation)-[:created_by]->(:PGUser)` |
| `(:PGUpdate)` | One for each update of a head node, with `id` and `updated_when`; linked `(update)-[:is_update_of]->(head)` and `(update)-[:updated_by]->(:PGUser)`. `get_document` reports the latest as `meta.updated_by` / `meta.updated_when` |
| `(:PGUrl {url})` | A URL of an entity (from a URL given as its `id`), linked `(entity)-[:has_url]->(url)`. It is a node, not a property, so that it can have a **uniqueness constraint**: a URL cannot belong to two entities, even if they are written at the same moment. It is not part of what an entity owns or contains: reading and updating an entity leave it alone, and a deleted entity keeps it (so the URL stays taken) |
| `(:PGDeletion)` | One for each deletion of a head document or an entity, with `id` and `deleted_when`; linked `(deletion)-[:is_deletion_of]->(node)` and `(deletion)-[:deleted_by]->(:PGUser)`. The node itself has `deleted: true` |
| `(:PGUndeletion)` | One for each undeletion, with `id` and `undeleted_when`; linked `(undeletion)-[:is_undeletion_of]->(node)` and `(undeletion)-[:undeleted_by]->(:PGUser)`. The node's `deleted` flag is removed; its `PGDeletion` records are kept |
| `(:PGUser {username})` | Must already exist: a write as a user with no node raises `PanglossUserNotFoundError`, and as a disabled user `PanglossUserDisabledError`. Users made with `create_user` also have `email`, `full_name`, `admin`, `disabled`, `created_when` and `hashed_password`; `username` and `email` are unique. See [Users](users.md). (The tests `MERGE` a bare one) |

### Property values

Values are converted by `convert_type_for_writing`: UUIDs and URLs become strings, `Decimal` becomes a string, and sets, tuples, lists and dicts (including `TypedDict`s) are converted recursively. `None` is never written. Edge properties are converted in the same way.

**Enums** are stored as Memgraph's native enums (`Colour::RED`, from the enum's name and the *name* of the member), which cannot be passed as query parameters. So the properties of a node or edge are set from one parameter holding everything but the enums, followed by `SET n += {colour: ToEnum($p), colours: [ToEnum($q), ToEnum($r)]}` for the properties that are, or have in them (in a list, a `TypedDict` or an annotated value), an enum (`PropertyAssignments` in `build_create_query.py`). The enum has to exist in the database: see `initialise_database`. A write that uses one that does not (or a member added since) raises a `PanglossWriteError` that says so.

### Setting up the database

`initialise_database()` (in `initialise_database.py`) sets up a database for Pangloss. Run it once, and again after changing the models (it is safe to repeat: what exists is left alone). Call `pangloss_models.initialise()` first, as the enums it creates come from the models.

```python
from pangloss_memgraph.databases.memgraph.initialise_database import initialise_database

setup = await initialise_database()   # uses the default Database, or give one
setup.created, setup.already_present  # lists of what it did and what was there
```

It creates:

| What | Why |
|------|-----|
| An index and a uniqueness constraint on `id` of `PGIndexableNode`, `PGCreation` and `PGUpdate` | Ids are UUIDs, and are how nodes are found. A second node with the same id fails when it is committed |
| An index on `PGIndexableNode(id, head_node_id)` | Finding a node of a particular document |
| An index on `HeadNode(id)` | Reads and updates look up the head node by id |
| The text index `label_text` on `PGIndexableNode(label)` | Listing and searching (`text_search.regex_search("label_text", ...)`) |
| An enum for each `Enum` used by a model | See below |

**Enums.** Every `Enum` used as the type of a field (also in a list, a `TypedDict`, an edge model, or an annotated value) is created as a Memgraph enum of the same name, with the names of its members. If one exists, members it lacks are added (Memgraph cannot remove them). Two different enums with the same name, or names that are not identifiers, are an error. Fields of an enum type are stored as these enums (see above), so run it after changing the models.

Indexes, constraints and enums cannot be changed inside a transaction, so each statement is run on its own.

## Operations

All are `async`.

### `create_head_node(instance, detail=False)` ✅

Called by `.save()`. Converts the `Create` instance to `CreateDB`, builds one query (`CREATE` for the head and its creation record; `MERGE` for nested documents keyed on `id`; `MATCH` + `CREATE` for edges to existing entities, restricted to the field's allowed types), checks it (see [Checks before writing](#checks-before-writing)), and runs it in a write transaction.

- **Existing nodes** are matched on `id`, or, if the reference gives a URL, through the `PGUrl` node of the URL. A write is all-or-nothing: if anything it refers to is missing, nothing is written, and the error says which reference.
- **Generic wrappers** (reified relations, semantic spaces, conjunctions): the allowed types of their contents (such as `target: list[T]`) come from the field that uses the wrapper, e.g. `Proxy[Person]`.
- **Entities written in the document** (with `create_new`) are entities of their own. Before the query is built, those that exist are looked up (by `id`, or by `PGUrl`, if given a URL) in the same transaction, and the query is built again: an existing one is `MATCH`ed like a reference, and a new one is `CREATE`d as `Entity.Create` creates it (head node, `PGCreation` record, its own relations). One that appears twice in a document is one entity. A conflict with what exists raises `PanglossConflictError`. A URL, like an id, has a uniqueness constraint. If another write creates the entity at the same moment, after this one checked that it was not there, this one fails when it commits and is run again (up to 3 times): it then finds the entity and uses it. For something that cannot be shared, such as a document id, the second attempt reports a `PanglossConflictError`.

- By default `.save()` returns the `ReferenceView` straight from the in-memory object, with `meta.created_by` set from `current_request_username`.
- `detail=True` re-reads the node and returns the full `HeadView` (`get_document` or `get_entity`).

### `update_head_node(instance, detail=False)` ✅

Called by `.save()` on a `Document.Update` or `Entity.Update`. **An update is a full replacement of the document, not a patch**: anything left out of the payload is removed. It does not work out what has changed; it deletes the tree and writes the new one, in one transaction:

1. **Check**, before anything is deleted: the user exists; the head node exists and has the given type (`PanglossNotFoundError`); everything referred to exists (`PanglossReferenceError`); no id in the payload belongs to a node outside this document (`PanglossConflictError`). If any check fails, nothing has changed.
2. **Collect `meta`** of every node already below the head node, so that nodes given again keep `created_by` and `created_when`. Their `updated_by` and `updated_when` are set.
3. **Replace the head node**: delete every node below it, except entities, and delete the edges it owns; then replace its properties. (Its URLs are kept: they are `PGUrl` nodes, which it does not own.) The head node itself is kept, with its `PGCreation`.
4. **Write the new tree**, with the same code as a creation, and add a `PGUpdate` node.

What is deleted, and what is not:
- Nodes are found by walking forward edges from the head node, without entering entities. These are the nested documents, embedded objects, semantic spaces, conjunctions and reified relations. (Annotated values are properties of those nodes, so go with them.)
- **Entities are never deleted**: they are not part of the document, including those it wrote with `create_new`. An update only removes and re-creates the *edges* to them. An entity written in an update is found or created as in a creation.
- A node owns its outgoing edges that are **not** marked `reverse: true`, and the incoming edges that are. So when an entity is updated, the edges from documents *to* it are kept, and only its own relations are replaced.
- Nodes given with an existing `id` keep that id (and so can be referred to), nodes given without one get a new id, and nodes left out are gone.

`detail` is as for creation; by default `.save()` returns the `ReferenceView` with `meta.created_by`, `created_when`, `updated_by` and `updated_when`.

### `delete_document(cls, id)` and `delete_entity(cls, id)` ✅

Both are in one write transaction (`soft_delete` in `delete_node.py`), after checking that the user exists. Nothing is removed: the node gets `deleted: true`, and a `PGDeletion` record is added.

- **Documents.** The node must exist (and not be deleted, nor be in a deleted document), and be a `HeadNode`; if it is nested in another document, `PanglossNotDeletableError` is raised.
- **Entities** (by id or URL). The query follows the reverse edges out of the entity to whatever holds each relation, then takes the head document of that (or the entity itself, if it is one). Those that are not deleted are the references. If there are none the entity is deleted, and any mark cleared. If there are, the entity gets `marked_for_deletion` (with `marked_for_deletion_by` and `marked_for_deletion_when`), the transaction **commits**, and `delete_entity` then raises `PanglossEntityInUseError`. (Raising inside the transaction would roll the mark back.)

**What deletion hides.** `get_document` and `get_entity` do not find a deleted node, or a node of a deleted document; all four `list` queries (also the count and the pages) leave them out, as do the searches, and the incoming relations of an entity; `update` raises `PanglossNotFoundError`; and a write that refers to a deleted entity raises `PanglossReferenceError` ("has been deleted"). A deleted node keeps its `id`, so it cannot be used again. For an entity the `deleted` flag is its own; for any other node it is that of its head document.

### `undelete_document(cls, id)` and `undelete_entity(cls, id)`

Restore a deleted head document or entity (`undelete` in `delete_node.py`), in one write transaction: the `deleted` flag is removed and a `PGUndeletion` record added. `PanglossNotFoundError` if there is no such node, `PanglossNotDeletableError` if the document is nested in another, and `PanglossNotDeletedError` if it has not been deleted. (A document nested in a deleted document comes back with its head document.)

### Checks before writing

`validate_write.py` runs these in the write transaction, so that a write that cannot succeed raises a `PanglossWriteError` subclass rather than silently doing nothing (or, for an update, deleting data and writing nothing):
- the user exists;
- each reference to an existing entity exists, and has one of the types allowed in that field;
- the URLs of new entities are not taken (`check_urls_available`);
- the ids of new nodes are free: for a creation, the head id and the ids of all nested documents; for an update, they may also belong to the document being updated, but not to any other node. (Entities written in the document are not checked here: they are found by id or URL, or created.)

### `get_entity(cls, id)` ✅

Reads an entity (by id, or by one of its URLs) with the same query as `get_document` for its own values, `meta` and relations, and a second query, in the same transaction, for the relations *to* it (`build_fetch_incoming_query`, assembled by `read_incoming.py`). Returns `cls.HeadView`, or `None` if not found.

Each relation is stored as a forward edge and a reverse edge marked `reverse: true`, so the relations to an entity are the reverse edges leading out of it. For each one, the query follows the chain of reified relations and embedded objects up (each has one reverse edge to what contains it) to the node that holds the relation, and returns the chain with it. Python then decides which incoming field the relation belongs to, drops sources the models do not allow for that field (the subclassed relations), and builds the view of each. See [Reading an entity](models.md#reading-an-entity) for what each contains.

It takes 100–130 ms to read an entity with 400 incoming relations, and the time hardly grows with the number. The incoming relations are not paginated.

### `get_document(cls, id)` ✅

Matches `PGIndexableNode` by `id` and type label, then builds the document as a tree and adds `meta`. Returns `cls.HeadView`, or `None` if not found. (See `get_entity` for entities.)

The query returns the root node and the edges of the tree below it, and `build_tree` makes them into nested dicts (a node's field names hold lists of what it is related to; the properties of a `ViaEdge` edge become `edge_properties`). The edges are made from three sets of paths:
- every path from the root through **forward** edges (reverse edges marked `reverse: true` are not followed), without entering entities, which reaches all nested documents, embedded objects, semantic spaces, conjunctions and reified relations at any depth;
- the edges from each of those nodes to **entities**; and
- the edges from the root to entities.

An entity appears as a reference (its `id`, `label` and so on): its own relations are not part of the document. A relation with no items has no edges, so reads back as an empty list; an optional literal that was `None` was never stored, so reads back as `None`. `neo4j` date, time and datetime values are converted to Python values.

### `list_items(cls, search_terms=None, page_number=None, page_size=None, deep_search=False)` ✅

Returns `_ListItems` of `ReferenceView`s of all concrete subtypes of `cls`. Default page size 50.

- Without `search_terms`: plain pagination.
- With `search_terms`: label search through the text index.
- With `deep_search=True`: each space-separated token is regex-searched (`.*token.*`); a hit on a nested node resolves to its head node, and a hit on an Entity resolves to the documents that reference it.

### Transactions

`Database.read_transaction` / `write_transaction` open a session per call. If a write function raises, its transaction is rolled back and the exception propagates (the checks above rely on this to leave data untouched). Transient conflicts, such as two updates of the same document at once, are retried by the driver for up to `max_transaction_retry_time` (10 seconds); the last write wins.

## Known rough edges

- `initialise_database` is run by `pangloss setup-database` (see [Command line](cli.md)), or can be called from code.
- Nothing yet removes deleted nodes for good.
- `Database.default` is set by the last `Database(...)` constructed, and `exposed_functions` decorates with `Database.default` at import time, so the settings/`Database` must be created before the module is first imported (which `initialise()` does when binding).
