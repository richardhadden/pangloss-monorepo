# RDF export

🚧 The package `pangloss-rdf`: every document and entity as RDF, and an ontology made from the models. The design and what is not built are in [the plan](rdf-export-plan.md). A how-to is in [the guide](../guide/rdf/README.md).

Add `"pangloss_rdf"` to `INSTALLED_APPS`. Nothing about a model has to change.

## Shape of the data ✅

- A head document or entity is a **named graph**, named by its URI. What is known of the graph (`dcterms:creator`, `created`, `modified`, `pgo:version`, `pgo:reviewStatus`) is in the default graph.
- A **relation** is a direct triple and an edge node (`pgo:Edge`, a kind of `rdf:Statement`), joined by `pgo:edge`, with `rdf:subject`, `rdf:predicate`, `rdf:object`, `pgo:position` and the fields of an edge model.
- Inside a **semantic space**, every node says `pgo:inSpace` for each space around it, and has its classes, literals and edge nodes; the direct triples, outside classes and outside properties are left out, so nothing negated is asserted. A reasoner given the ontology can still infer an outside *class* from the node's Pangloss class.
- A reference to an **entity** in a document gives it only `a` and `rdfs:label`.
- An entity's own export has its own data, and `pgo:referencedBy` for what refers to it. Reverse relations are not in the data: the ontology has `owl:inverseOf`.
- `DBField`s are not exported. Packages add what they mean: `pangloss_dates.rdf`, `pangloss_typology.rdf` (SKOS), `pangloss_zotero.rdf`.

## URIs ✅

| Thing | URI |
|---|---|
| Item, wrapper | `{ENTITY_BASE_URL}/{Class}/{uuid}` |
| Embedded, annotated value, `TypedDict` | `{parent}/{Class.property}` (`/{n}` in a list) |
| Edge node | `{subject}/edge/{Class.property}/{position}`: changes if a list is reordered |
| Class | `{RDF_ONTOLOGY_URL}{Class}` |
| Property | `{RDF_ONTOLOGY_URL}{Class.property}`, of the top-most class that has the field; camelCase |

A nested item is kept over an update only if the update names it by its id, so a head's URI is the one to cite.

## Settings

All optional but `ENTITY_BASE_URL`, which every project has.

| Setting | Default | |
|---|---|---|
| `RDF_ONTOLOGY_URL` | `{ENTITY_BASE_URL}/ontology/` | Where classes and properties are |
| `RDF_PREFIX` | made from `PROJECT_NAME` | What the project's classes and properties are called in Turtle, TriG and JSON-LD |
| `RDF_CORE_URL` | `{RDF_ONTOLOGY_URL}/core#` | The structural terms (`Edge`, `inSpace`, called `pgo:` in these docs). By default each project's own, and defined in its ontology; several projects that want to be queried alike can give one address, where those terms must then be published |
| `RDF_CORE_PREFIX` | `core` | What those terms are called in the output |
| `RDF_REFERENCED_BY_LIMIT` | 1000 (at most 500 are read of each field) | `pgo:referencedBy` of an entity, per incoming field |
| `RDF_HTML_URL` | none | Where the interface is, for sending a browser to an item's page |
| `RDF_EXPOSE_USERS` | `True` | Whether usernames are in the provenance |
| `RDF_LICENSE`, `RDF_DUMP_URL` | none | In the dataset description |

## Routes ✅

`GET /api/rdf/{Class}/{id}` (`?format=ttl|trig|jsonld|nt|nq` or `Accept`; `?view=true` as plain text), `GET /api/rdf/ontology` (`?part=shapes|context`), `GET /api/rdf` (VoID). Reading is what `GET /api/NAME/{id}` would show the same reader. An item asked for at a class it is not is a `301` to the right one, also a class that no longer exists.

## URIs lead somewhere ✅

`{ENTITY_BASE_URL}/{Class}/{id}` answers with a `303`: a browser (one whose `Accept` names HTML above any RDF) to the item's page at `RDF_HTML_URL`, or to the data as text if that is not set; anyone else to `/api/rdf/...`, keeping its `Accept`. An edge or an embedded object goes to the item it is in, and what is under the ontology's address to the ontology, when that is under `ENTITY_BASE_URL`.

**These requests must reach the API.** Where the interface's server is in front, `pangloss interface serve --api-path /entity` passes them on (the development server reads `PANGLOSS_API_PATHS=/entity`). `ENTITY_BASE_URL` therefore needs a path of its own: `pangloss rdf check` warns of one at the root of the site, which is the interface's.

## Commands ✅

`pangloss rdf check`, `ontology [--shapes] [--context]`, `dump -o FILE[.gz] [--format nq|trig] [--types A,B] [--include-unpublished]`, `generate-ontology FILE --prefix crm [--title NAME] --out MODULE.py`.

## A package's own RDF ✅

An app's `rdf.py`, found by name, calls `register_rdf_converter(Class, function, replace=False)`. The function is given the view, its URI and a `Context` (`quad(...)`, `asserted`), and gives quads; it must leave out what it should not assert when `context.asserted` is false.

## In the interface ✅

A menu in the console of an item: the RDF formats, and **API JSON**, the item as `GET /api/NAME/{id}` gives it. The console's own View as JSON button is not shown while this is installed (`jsonLinkIn` in the module's manifest, a general option: it comes back if the project disables `pangloss_rdf:ViewRdf`).
