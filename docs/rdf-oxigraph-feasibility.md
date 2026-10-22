# Feasibility: an RDF (Oxigraph) backend

A short report (2026-10-22). Written from the code in this repository and general knowledge of Oxigraph, with one quick search; **the Oxigraph points marked (verify) should be checked before anything is built.** Nothing here is built.

## Verdict

**Feasible, and the models side needs no change; it is a rewrite of the database package, not an adaptation of it, and it has a few real design costs.** The model layer (`pangloss-models`) already produces a database-neutral description (`_meta.fields`, `RelationFieldDefinition`, the snapshot of `migrations/snapshot.py`), so the RDF backend would read that, as `pangloss-memgraph` does. The work is `pangloss-memgraph`'s 3,600 lines (of which about 1,500 are query building and the migration operations are about 2,000 more), redone in SPARQL, plus a design for the places where the property-graph model and RDF differ. A rough size: **4 to 8 weeks for a read/write backend that passes the same tests, plus 3 to 5 for migrations**, by one person who knows the models. Oxigraph itself is a good fit for a research project (embedded, single binary, standards-based, easy to ship); it is a poor fit if the project needs a cluster, fine-grained access control, or heavy write concurrency.

## What maps well

| Pangloss | RDF |
|---|---|
| Node labels (`Person`, its parents, traits, kind) | several `rdf:type` triples; the label chain `labels_for_model` makes is exactly a type set |
| Literal properties, lists of literals | triples with typed literals (`xsd:string`, `xsd:integer`, `xsd:dateTime`, ...); a list of literals is several triples (order is lost; see below) |
| Relations between nodes | triples `subject predicate object` |
| Entities and documents with UUID / URL ids | IRIs (`https://example/entity/<uuid>`); an entity with a URL id uses that IRI directly, which is natural in RDF |
| Reverse relations (`..._reverse`) | the same triple read the other way: no second edge needed |
| Soft delete, version, created/updated metadata | triples on the head node, or (for history) named graphs |
| Document as a unit that asserts things | **a named graph per document**: this is the strongest fit. Everything a document states lives in its graph; "only documents assert" (`notes/descriptions-and-assertions.md`) and "restore as a draft" (`docs/history.md`) become graph operations |
| Querying and the semantic web | SPARQL, content negotiation, export to Turtle / JSON-LD for free; the data is publishable as linked data |

## Where it gets harder

1. **Edge properties (`ViaEdge[X, Weight]`) and the reified relations.** A property graph attaches properties to an edge; plain RDF cannot. Options: (a) reify every edge that has properties as a node (`_:e a ex:Edge; ex:from; ex:to; ex:weight`), which is how reified relations are already modelled (a node in between), so the *models* are unaffected but the queries are not symmetrical for edges with and without properties; (b) RDF 1.2 triple terms (the successor of RDF-star), which Oxigraph supports behind a feature flag (verify that the Python package exposes it, and how stable it is). Recommendation: (a), because it works everywhere and matches the reified-relation design.
2. **Order of lists.** RDF has no ordered multi-valued property. Pangloss lists are unordered today in the graph (check `docs/models.md`); if order matters, use `rdf:List` or an explicit position on a node.
3. **Reading a document as a tree.** `build_read_query.py` returns a nested document in one Cypher query. SPARQL `SELECT` returns flat rows and `CONSTRUCT` returns a graph; the nesting would be rebuilt in Python from a `CONSTRUCT` (or a few queries), using the field definitions to know the shape. This is workable, and the shape is known from `_meta`, but it is new code and slower than a Cypher path expression.
4. **Constraints and indexes.** Memgraph has unique constraints and indexes (`initialise_database.py`, `migration_backend.py`). Oxigraph has no schema constraints (no SHACL validation, as far as I know: verify); uniqueness, required fields and `validate_write.py` would be enforced in Python before writing, which the models already largely do. Indexes are automatic (it indexes all triple orderings).
5. **Migrations.** The migration framework (`pangloss_models/migrations`) is database-neutral (changes, planner, graph of files); the Memgraph operations (`migrations/operations.py`, about 2,000 lines of Cypher: rename a field, split an embedded object, retype, `Fulfils`, ...) would each be rewritten as SPARQL Update. Mostly mechanical, but it is the largest single piece, and each operation needs its own tests (the Memgraph ones are a good template).
6. **Transactions and concurrency.** Oxigraph is embedded (in the process, with RocksDB) or run as an HTTP server; it has transactions with snapshot isolation, but is a single node, with a single writer at a time (verify the exact guarantees). Pangloss already writes whole documents in one transaction with retries (`write_with_retries`), which maps. The API server and the CLI would not both open the same store directory at once in embedded mode; use the server mode (or one process) in production.
7. **Async.** `pyoxigraph` is synchronous (verify); the Pangloss database functions are `async`. Wrap calls in `asyncio.to_thread`, or use the HTTP server with an async client. Not hard; not free.
8. **Query performance.** The Oxigraph documentation says SPARQL evaluation has not been optimised much ([docs.rs](https://docs.rs/crate/oxigraph/latest)). For the sizes of a humanities project (millions of triples) it is likely to be fine; for the incoming-relations queries (path lengths through reified relations and semantic spaces: `read_incoming.py`) it needs measuring early.
9. **Access control.** Oxigraph has none of its own: the API layer (`pangloss-users`) already does authentication; anything finer (per-document) is application code. Same as Memgraph in practice, but worth saying.

## What would be built

1. A `pangloss-oxigraph` package with the same `exposed_functions` surface as `pangloss-memgraph` (`get_document`, `get_entity`, `list_items`, `create_head_node`, `update_head_node`, `delete_*`, `undelete_*`, users). The interface is already the seam (`DATABASE_MODULE` setting); `pangloss-sdk` is the stub for it.
2. An **RDF mapping** derived from `_meta` and the snapshot: one function from a model and a field to a predicate IRI (`ex:Person/born_in`, in a namespace from settings), one for ids, one for types. This is the part to design carefully, and to document, because it is the data format: it should be settled with real use of the data (export, other tools) in mind. A JSON-LD context could be generated from the same mapping.
3. Write path: `CreateDB` / `UpdateDB` models to triples in the document's named graph, inside one transaction; the labels, context labels and semantic spaces as triples.
4. Read path: head view, edit view, list and incoming relations from SPARQL, rebuilding the nested shapes in Python.
5. Migrations: the neutral part stays; operations rewritten as SPARQL Update.
6. The test suite: much of `packages/pangloss-memgraph/tests` (about 33 modules) is written against the public functions and could run against both backends, with the container fixture swapped for a temporary directory. That is a strong reason to start with a *backend-neutral test layer*.

## Risks and open questions

- **Is a second backend wanted at all?** `TODO.md` ("Other databases") asks this; a second backend means keeping two query layers in step, and the `migration_backend` interface needs a design pass first.
- **Which wins, a property graph or RDF, for the real use?** RDF gives linked data, named graphs for documents and standard tooling; it costs more code for edge properties and nested reads. If publishing as linked data or exchanging with other projects matters, RDF is attractive; if the main need is the API, Memgraph is simpler.
- **Scale and cluster.** One node; fine for a research database, not for high availability.
- The Oxigraph / `pyoxigraph` version, the status of RDF 1.2 support, transactions, async and SHACL should be confirmed against the current release notes (the current crate on [docs.rs](https://docs.rs/crate/oxigraph/latest) is 0.5.x, with RDF 1.2 behind a feature flag).

## Suggested way in

A one-to-two day spike before any decision: store the kitchen-sink models' sample data (`tests/test_model_setup/sample_data.py`) as triples in `pyoxigraph`, one named graph per document; write the three hard queries (a nested document read, the incoming relations through a reified relation and a semantic space, an edge with properties); time them on a generated dataset of about a million triples. If those three are acceptable, the rest is known work.
