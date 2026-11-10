# Plan: RDF export (`pangloss-rdf`)

🚧 **Built, with the exceptions in "As built" at the end.** Written 2026-11-09 from the code on `dev`; the reference is [RDF export](rdf.md). This is an *export*: Memgraph or
Neo4j stay the store. [The Oxigraph report](rdf-oxigraph-feasibility.md) is about a different thing, an RDF backend.

Points not yet confirmed by running anything are marked **(check)**; §13 lists them in the order they should be settled.

## 1. What it does

- A **"View as RDF" button** in the console of every document and entity, next to "View as JSON".
- `GET` of one item as Turtle, TriG, JSON-LD or N-Triples.
- A **full dump** (`pangloss rdf dump`) of everything a reader who is not logged in can see.
- The **ontology** of the project, generated from its models (RDFS/OWL, optional SHACL, JSON-LD context).
- `_rdf_meta = RDFMeta(...)` and `RDFField(...)` to override names, and generated **mixins** that align classes and
  fields to an outside ontology such as CIDOC-CRM.

Out of scope for the first version: importing RDF, a SPARQL endpoint, exporting past versions from `pangloss-history`.

## 2. Decisions taken

| Question | Decision |
|---|---|
| Shape of a relation | Every relation is an **edge node and also a direct triple** |
| Item URIs | `{ENTITY_BASE_URL}/{Type}/{uuid}`; any type segment resolves, and a stale one redirects |
| Mixins | **Generated from the ontology's RDFS file**; CRM ships ready-made |
| Semantic spaces | Node, classes and edge nodes are written, with `pgo:inSpace`; **direct and aligned triples are withheld** |
| Property URIs | **Per declaring class** |
| Aligning a field | `Annotated[..., RDFField(parent=crm.P14_carried_out_by)]`; in the ontology **and** in the data |
| An entity's export | Its own data, plus capped `pgo:referencedBy` links to the head documents |
| Packaging | A **named graph per head**; the button defaults to Turtle |

## 3. Example

The demo's `Activity` (`carried_out_by: ViaEdge[Agent, Certainty]`), nested in a `Factoid`, in TriG:

```turtle
@prefix ex:  <https://example.org/ontology/> .
@prefix crm: <http://www.cidoc-crm.org/cidoc-crm/> .
@prefix pgo: <https://pangloss.example/ns#> .      # the fixed vocabulary of §7; its final address is open (§14)
@prefix d:   <https://example.org/> .

d:Factoid\/0190a {                                 # the graph is the head document
  d:Factoid\/0190a a ex:Factoid , pgo:Document ;
      rdfs:label "Ambassador's report, f. 12" ;
      ex:Factoid.statements d:Activity\/0191b ;
      pgo:edge <https://example.org/Factoid/0190a/edge/Factoid.statements/0> .

  d:Activity\/0191b a ex:Activity , ex:Statement , pgo:Document , crm:E7_Activity ;
      rdfs:label "Meeting at Innsbruck" ;
      pgo:partOf d:Factoid\/0190a ;
      ex:Statement.text "They met at Innsbruck" ;
      ex:Activity.activityType "meeting" ;
      ex:Activity.carriedOutBy d:Person\/0188c ;     # the direct triple
      crm:P14_carried_out_by   d:Person\/0188c ;     # from RDFField(parent=...)
      pgo:edge <https://example.org/Activity/0191b/edge/Activity.carriedOutBy/0> .

  <https://example.org/Activity/0191b/edge/Activity.carriedOutBy/0> a pgo:Edge ;
      rdf:subject   d:Activity\/0191b ;
      rdf:predicate ex:Activity.carriedOutBy ;
      rdf:object    d:Person\/0188c ;
      pgo:position  0 ;
      ex:Certainty.level 3 .

  d:Person\/0188c a ex:Person ; rdfs:label "Maximilian" .    # what a chip shows, nothing more
}

d:Factoid\/0190a pgo:version 4 ;                     # provenance is about the graph, in the default graph
    dcterms:creator "rhadden" ; dcterms:created "..."^^xsd:dateTime ; dcterms:modified "..."^^xsd:dateTime .
```

## 4. Item 1: how to convert

### 4.1 The method

A pure function, tested without a database, walks a read result by the model's field definitions:

```python
def convert(item, context: Context) -> Iterator[Quad]: ...
```

- **Input.** `Document.get(id)`'s `HeadView`. For an entity, `get_for_edit(id)`'s `EditView`: exactly its own values
  and outgoing relations, without incoming ones **(check that it applies the same visibility rules)**. Going through
  the models keeps the add-on rules: any backend, and no copy of who-may-see-what.
- **Driver.** `model._meta.fields`, not the JSON. A `ModelFieldDict` says which of `LiteralFieldDefinition`,
  `ListFieldDefinition`, `AnnotatedValueFieldDefinition`, `EmbeddedFieldDefinition` or `RelationFieldDefinition` each
  field is. Fields the definitions do not list are not exported, which is how `_derived` and other view extras stay out.
- **Context carried down the tree:** the head (graph name), and the stack of enclosing semantic spaces. This comes from
  the walk and does not rely on `meta.semantic_spaces`.
- **Output.** A stream of plain `Quad` tuples, so the serialiser is separate (§10).

### 4.2 Each kind of thing

| In Pangloss | In RDF |
|---|---|
| Head `Document` / `Entity` | URI; `a` its classes; `rdfs:label`; named graph |
| Nested `Document` | Own URI by its own type and id; `pgo:partOf` the head |
| Reference to an `Entity` | Direct triple + edge node; the target gets only `a` and `rdfs:label`, from the `ReferenceView` |
| `Embedded` | A node `{parent}/{Property}`; `a` its class; joined by direct triple + edge node, like a relation |
| `ReifiedRelation[T]`, `SemanticSpace[T]`, `Conjunction` | A node of their own, URI from their id; their fields are relations like any others |
| `ViaEdge[X, E]` | E's fields are properties of the edge node, named `ex:E.field` |
| List position (`pg_position`) | `pgo:position` on the edge node |
| Literal | One triple, datatype by §4.3 |
| `list[str]` and the like | Repeated triples; order lost unless `RDFField(ordered=True)`, which makes an `rdf:List` |
| `AnnotatedValue` (`WithCertainty[str]`) | A node `{parent}/{Property}` (`/{n}` in a list) with `rdf:value` and its extra fields. It is stored as a map, so has no id |
| `TypedDict` | A node of the same form, with properties `ex:{Class}.{field}.{key}` |
| `Enum`, `Literal[...]` | The value as a literal (§14 has the alternative) |
| `meta` | Provenance on the graph, §3 |
| Reverse relations | **Never in the data.** `owl:inverseOf` in the ontology |
| `Fulfils[Other]` | Also `a` the fulfilled class, as for its node labels |
| `deleted`, `marked_for_deletion` | Not exported; a read leaves them out |

Classes written on a node mirror `labels_for_model`: the class, its parents and heritable traits, its kind (as
`pgo:Document` etc., not `HeadNode` or `PGIndexableNode`), then the outside classes from its mixins. Writing them all
means a consumer can query without a reasoner.

### 4.3 Literal datatypes

Derived from `pangloss_models.literals`, in one table that a package can add to, as it can add a codec.

| Python | Datatype |
|---|---|
| `str` | `xsd:string`; a language tag with `RDFField(language="la")` |
| `int`, `float`, `bool`, `Decimal` | `xsd:integer`, `xsd:double`, `xsd:boolean`, `xsd:decimal` |
| `date`, `datetime`, `time`, `timedelta` | `xsd:date`, `xsd:dateTime`, `xsd:time`, `xsd:duration` |
| URL | `xsd:anyURI` |
| `UUID`, IP, path, email, `Pattern`, `Fraction` | `xsd:string` |

### 4.4 Reification rules

- **Every value of every relation field gets an edge node**, including those to wrappers, nested documents and
  embedded objects. One rule: a query never has to know which kind of field it is on.
- Edges have no ids in the store, so the URI is derived:
  `{subject URI}/edge/{Class.property}/{position}`. It changes if a list is reordered. It is an address within the
  export, not a thing people should cite.
- `pgo:Edge rdfs:subClassOf rdf:Statement`. Standard tools can read it, and by RDF's semantics a reified statement
  does not assert its triple, which is what §4.5 relies on.
- Scale: about 6 triples per relation value, so plan on the total being several times the node count (measured at §12, step 9).

### 4.5 Semantic spaces

Inside a `Negative`, `Hypothetical` or subjunctive space:

- written: the node, its Pangloss classes, its literals, its edge nodes, and `pgo:inSpace` for **each** enclosing space;
- withheld: direct relation triples, outside classes (`crm:E7_Activity`), and aligned properties (`crm:P14...`).

So a CRM consumer reading the data does not learn that an event that did not happen happened.

**Limit, to be documented:** the ontology still says `ex:Activity rdfs:subClassOf crm:E7_Activity`. A reasoner run over
data and ontology together will type a negated activity as `E7_Activity`, because it has `a ex:Activity`. It still gets
no `P14`. If this turns out to matter, classes that occur in spaces can be given a separate `pgo:` type there; not in
the first version.

The same rule answers a wider point. In `notes/descriptions-and-assertions.md`, only documents assert: the named graph
is what makes every direct triple something *a document says*, not a fact about the world.

## 5. Item 2: default URIs

| Thing | URI |
|---|---|
| Head or nested item, wrappers | `{ENTITY_BASE_URL}/{Type}/{uuid}` |
| Embedded, annotated value, `TypedDict` | `{parent}/{Property}`, with `/{n}` in a list |
| Edge node | §4.4 |
| Class | `{ONTOLOGY}/Person` |
| Property | `{ONTOLOGY}/Activity.carriedOutBy` |
| Reverse property | `{ONTOLOGY}/Activity.carriedOut` |
| Edge property | `{ONTOLOGY}/Certainty.level` |

- **`ENTITY_BASE_URL`** is at last used (it is required in settings, and nothing reads it). A value left at
  `example.org` is a warning at `pangloss rdf check`.
- **`RDF_ONTOLOGY_URL`** is a new optional setting, by default `{ENTITY_BASE_URL}/ontology/`. A type called `ontology`
  is refused at startup.
- **A dot, not the slash discussed.** `ex:Activity.carriedOutBy` is a legal prefixed name in Turtle;
  `ex:Activity/carriedOutBy` needs an escape in every occurrence.
- **Declaring class.** The property belongs to the top-most class in the MRO that has the field, so `Activity` reuses
  `Statement.text` and a mixin or trait's fields keep one URI. Field names are in camelCase, as the API gives them.
- **Generic classes** have one URI by origin: `InRole[Agent]` and `InRole[Group]` are both `ex:InRole` **(check what
  `type` a view gives for them)**.
- **Entities with URL ids.** The URI is still minted from the UUID. Each `PGUrl` is written as `owl:sameAs` (§14).
- **A type that has changed.** Only entities can (`changing_class_from`). The route looks for `{Type}/{id}`, and if
  it is not there asks `Entity.references([id])` for the current type and answers `301`. It ignores the old segment
  altogether, so a class since removed from the models still resolves.
- **Nested ids may not be permanent.** An update keeps a nested item that is sent with its `id`; one sent as a new
  `Create` gets another **(check what the form sends: if it re-creates nested items, their URIs are not citable and the
  doc must say so)**. Head URIs are permanent.

## 6. Item 3: `RDFMeta`

```python
class Person(Entity, Agent, E21_Person):
    _rdf_meta = RDFMeta(class_name="HistoricalPerson")

    known_as: Annotated[WithCertainty[str], RDFField(name="appellation")]
```

```python
class RDFMeta(BaseMeta):
    class_name: str | None = None   # replaces the class's name in its class URI and its items' URIs
    class_uri: str | None = None    # a whole URI, for using an outside class as this class itself
    exclude: bool = False           # this class is not exported, nor any relation to it
```

```python
@dataclass(frozen=True)
class RDFField(FieldMarker):
    name: str | None = None
    uri: str | None = None
    parent: OntologyProperty | Iterable[OntologyProperty] = ()   # §7
    exclude: bool = False
    ordered: bool = False
    language: str | None = None
```

- Registered with `register_meta_slot("_rdf_meta", RDFMeta)`.
- **A slot is inherited, but a name must not be** (a subclass would get its parent's URI). `class_name` and `class_uri`
  are read only through `declared_slots`; `exclude` is inherited.
- A generic's slot is read from its origin class.
- Checked at server start and by `pangloss rdf check`, raising `PanglossMetaError`: two classes or properties with one
  URI, a name that is not a valid local name, and a `uri` and `name` together.
- Neither is data, so neither is seen by migrations. A rename does change published URIs, and the docs must say so.

**Core change needed.** A field marker today is on literal fields, and embedded ones through `apply_to_embedded`;
`RelationFieldDefinition` has no `markers`, and an unknown thing in `Annotated` is refused. Add `markers` to
relations and annotated values, as a general hook with a test in `pangloss-models`. It is also not part of the
snapshot, so it needs no migration. `FieldMarker.check` is passed the exported field, and is how `ordered=True` on a
single value gets refused.

## 7. Item 4: mixins for outside ontologies

```python
from pangloss_rdf.ontologies.crm import E7_Activity, E21_Person, P14_carried_out_by

class Person(Entity, Agent, E21_Person): ...

class Activity(Statement, E7_Activity):
    carried_out_by: Annotated[
        ViaEdge[Agent, Certainty],
        RelationConfig(reverse_name="carried_out"),
        RDFField(parent=P14_carried_out_by),
    ]
```

- **A mixin is a plain Python class, not a `Trait`.** `labels_for_model` skips a parent that is not a pydantic model,
  so it gives no node label, and adding or removing one needs no migration. This is what keeps CRM's hierarchy from
  becoming dozens of labels on every node. Its URI is an unannotated class attribute (`_rdf_uri = "..."`).
- **Spike, 2026-11-09 (§12 step 1), passed.** A plain mixin, itself in a small hierarchy, on an `Entity`, `Document`,
  abstract `Document` (reaching its subclasses), `Trait`, `Embedded`, generic `ReifiedRelation` and `SemanticSpace`:
  `initialise()` gave no warning; labels, migration snapshot hash and `export_models()` were identical to the same
  models with no mixin; a nested write built its `CreateDB`; the stubs keep the bases; `ty` had no error on the models
  or stubs. Not run: `pangloss check`, or the SDK build.
- **Why not `Trait`.** Traits work, and were tried in the same spike, but each one is model data: a `Trait` mixin put
  the whole chain on the node (`Person, Agent, E21, E39, E77, Entity`) and changed the snapshot hash, so it is a
  migration; it also adds to `export_models()` and to the registry. `NonHeritableTrait` adds only the direct label,
  but still changes the snapshot and the export, and a subclass gets no label (`Meeting` lost `E7`). A project that
  wants a relation to "any actor" declares its own trait with the mixin: `class Agent(Trait, E39_Actor)`.
- A trait or an abstract base can have a mixin. Everything inheriting from it gets it.
- **Order of the bases.** The trait first, then any narrower mixin: `class Person(Entity, Agent, E21_Person)`. Naming a
  broader class before a trait that has it (`class Person(Entity, E39_Actor, Agent)`) is a `TypeError` from Python
  ("cannot create a consistent method resolution order") as the class is declared. There is a test that it raises. No
  check of ours can word it better, as the class never comes to exist; the guide should say so.
- In the ontology: `ex:Person rdfs:subClassOf crm:E21_Person`. In the data: `a crm:E21_Person`, outside spaces (§4.5).
- The nearest mixins are written in the data, not all their CRM ancestors. The ontology file of CRM supplies those.
- **A property is an instance**, `OntologyProperty(uri, domain, range)`, for use in `parent=`. It is a marker's value
  and not a mixin, because a Python class cannot inherit from a field.
- **Generated.** `pangloss rdf generate-ontology <file.rdf> --prefix crm --out crm.py` reads an RDFS or OWL file and
  writes a module: a class per RDFS class with the ontology's own hierarchy, as Python bases; a constant per property,
  docstrings from `rdfs:comment`, deprecated terms left out. The module is checked in; generating needs `rdflib`, using
  it does not.
- **Shipped.** `pangloss_rdf.ontologies.crm`, generated from a named CRM version which is recorded in the module.
  FRBRoo, CRMdig and so on, or a project's own, by the same command.
- **Checked** at `pangloss rdf check`: a field's value classes against `parent`'s domain and range, as warnings.
  Pangloss fields are often not a perfect match, so this does not refuse.

Only a field-to-property alignment is in scope. A *path* mapping (a Pangloss field that needs several CRM nodes, as
`P4_has_time-span → E52 → P82`) is a separate feature; §11 has the one built-in case and the hook.

## 8. Item 5: the ontology

Generated from `ModelRegistry`, so with no database. `pangloss rdf ontology --format ttl`, and
`GET /api/rdf/ontology` at the address `RDF_ONTOLOGY_URL` should redirect to.

| Source | Output |
|---|---|
| Each class | `owl:Class`, `rdfs:label`; `rdfs:comment` from the docstring |
| Parents, traits | `rdfs:subClassOf`, mirroring labels |
| Mixins | `rdfs:subClassOf` the outside class |
| Literal fields | `owl:DatatypeProperty` |
| Relation, embedded fields | `owl:ObjectProperty` |
| Annotated value, `TypedDict` | A property to a generated class |
| `subclasses_parent_fields` | `rdfs:subPropertyOf` |
| `RDFField(parent=...)` | `rdfs:subPropertyOf` the outside property |
| `reverse_name` | A property with `owl:inverseOf` |
| Translations (`translations/models.jsonc`) | Further `rdfs:label`s with language tags |
| The fixed `pgo:` vocabulary | Shipped as a static file, imported with `owl:imports` |

- **Domain and range use `schema:domainIncludes` and `schema:rangeIncludes`, not `rdfs:domain`/`range`.** A relation
  to `Agent | Identification[...]` has several ranges, and several `rdfs:range` statements mean the *intersection*.
  They would also cause a reasoner to infer wrong types through the wrapper nodes.
- **Generics.** `ex:InRole.target` has the range of everything it is used with, so the ontology collects each use.
- `owl:versionInfo` is a hash of the exported model definition, so a consumer can tell it has changed. The project's
  name and version go in `owl:Ontology`.
- **SHACL** (`--shapes`): `sh:NodeShape` per class from the same definitions (required fields, cardinalities, the
  `Literal` lists). Its main job is in the tests (§12): generated data must conform to generated shapes.
- **JSON-LD context** (`--context`), and the context used by the JSON-LD output.

## 9. Routes and the button

```
GET /api/rdf/{Type}/{id}        ?format=ttl|trig|jsonld|nt, or by Accept (default Turtle)
GET /api/rdf/ontology           the same formats
```

- From `pangloss_rdf/api.py`. `GET /api/NAME/{id}` is the core's and stays JSON: content negotiation there would put
  RDF into the core.
- Reading needs no login, and access is what `get` gives: a deleted or unpublished item is a 404 for those who cannot see it.
- `ETag` from `meta.version`, for a head.
- The reserved names need `rdf` added (a model called `rdf`), checked with the others at `initialise()`.
- **Button.** A `consoleActions` entry in `pangloss_rdf/interface/`, shown with the JSON one, opening a new tab. An
  `<a>` to a `text/turtle` response may download instead of showing, so the route also answers `text/plain` with
  `?view=1`. Text as `t()` slots with translations; a row in `e2e/COVERAGE.md`.
- **Dereferencing.** For a URI to work, `{ENTITY_BASE_URL}/{Type}/{id}` must reach something that negotiates. Whether
  that matches the interface's own item URLs, and how the interface's server sends RDF clients a `303` to
  `/api/rdf/...`, is a later phase. Until then the URIs are identifiers that do not resolve to RDF (§14).

**Entity export.** Its own data, plus one triple for each head document referring to it:
`<entity> pgo:referencedBy <head>`, up to `RDF_REFERENCED_BY_LIMIT` (default 1000), and if there are more,
`pgo:nextPage` to `?page=`. Incoming data is read with what `GET /api/NAME/{id}/incoming/{field}` uses; those
functions are not bound to the models, so **an add-on needs a small general way to reach them (check)**, and it
has to give the head document when the referrer is nested. An incoming relation is never restated as a triple.

## 10. The dump, libraries and packaging

```sh
pangloss rdf check                       # all the checks of §6 and §7
pangloss rdf ontology [--shapes] [--context] [--format ttl] [-o FILE]
pangloss rdf dump -o data.nq.gz [--format nq|trig] [--types Factoid,Person]
pangloss rdf generate-ontology ...
```

- **The dump** goes through `Model.list` and `get`, with bounded concurrency, and streams. It holds nothing in memory.
  Every head has its own graph, so a write in the middle affects one graph only. There is no global snapshot; the
  dump says when it started, in a header graph.
- It runs **as a reader who is not logged in** (no unpublished documents). `--include-unpublished` is explicit.
- **N+1 is the risk** on 642k nodes: one read per head. Measure first (§12, step 9). If it is too slow, the fix is a
  general streaming read of many heads in a backend operation, in `pangloss-cypher` with conformance tests, and not
  Cypher in this package.
- **Libraries.** `rdflib` for Turtle, TriG and JSON-LD on one item, and to read ontology files. N-Quads for the dump
  written directly from `Quad`s, since it is a line format and `rdflib` per item would be the slow part. `pyshacl` in
  dev only. `rdflib` 7.6.0 and `pyshacl` import on Python 3.15, and `rdflib` round-trips TriG and JSON-LD (spike,
  2026-11-09); neither is in the workspace yet.
- **Package layout**, with `requires` empty (no Cypher):

```
packages/pangloss-rdf/src/pangloss_rdf/
  __init__.py      RDFMeta, RDFField, register the slot; no rdflib, no FastAPI at import
  meta.py  terms.py (Quad, URI building)  convert.py  literals.py  ontology.py  shacl.py  serialise.py
  ontologies/crm.py  ontologies/pgo.ttl
  generate.py      api.py      cli.py      interface/      translations/
```

- **The SDK.** A project's `models.py` imports `pangloss_rdf`, so it must import on a client: only `meta.py` and the
  mixins at module level, and `rdflib` imported where it is used. The SDK build's check covers it, with a test.
- `INSTALLED_APPS` needs `pangloss_rdf`.

## 11. Anything else

- **Packages extend the conversion by a hook**: `register_rdf_converter(DeclaredClass, function)` replaces how nodes
  of a class are written, as a general path-mapping seam:
  - **`pangloss-dates`**: all the `Date` subclasses. The default gives structure (`ExactDate.year`), and the computed
    bounds matter more. Written as `pgo:earliest`, `pgo:latest` and so on as `xsd:date` where a proleptic Gregorian
    date can be given, with the source text kept; and for a `Dateable` aligned to CRM, `P4 → E52_Time-Span → P82a/P82b`.
    (Julian dates and BCE years **need care**: `xsd:date` is proleptic Gregorian. **Check** which `DBField` values a view has.)
  - **`pangloss-typology`**: types as `skos:Concept` in a `skos:ConceptScheme`, with `skos:broader`. Written in the
    typology's own graph.
  - **`pangloss-zotero`**: `dcterms` and `bibo` for an item, and the Zotero URI with `owl:sameAs`.
  - **`pangloss-calendar`**: days and feasts are its own graph and are out of scope at first.
  - The hook lives in `pangloss-rdf`; a package gives its converter in an optional `rdf.py` module found by name (the
    pattern of `derived.py`), so **those packages do not depend on `pangloss-rdf`**.
- **`pangloss-derived`.** Not in an item's export (not in the field definitions), so nothing derived is asserted as if
  a document had said it. Later, a `--derived` graph per rule with `prov:wasDerivedFrom`.
- **`pangloss-review`.** A published head can say `pgo:reviewStatus`. Unpublished items are a 404 for anonymous readers.
- **Licence and dataset description.** `RDF_LICENSE`, and a VoID description at `GET /api/rdf` and at the head of a dump
  (title, licence, counts, the dump's address).
- **Users.** `meta` names usernames, as the JSON does, to everyone. A published export is more permanent: a setting
  `RDF_EXPOSE_USERS` (see §14).
- **Size limit.** A document can be big (the write path handles thousands of nodes). No limit on an item, but note
  the response is built fully and not streamed.
- **Round trip.** Not promised: list order of literals, `DBField`s and the original `Create` cannot all be rebuilt.
- **`pangloss-lsp`.** `RDFField` and `_rdf_meta` get checks through `pangloss check`, each with `fix=`, once the first
  version is stable.

## 12. Order of work

1. **Spike (half a day).** A plain mixin on a `Document`/`Entity`/trait: `initialise()`, stubs, `ty`, no label, no
   migration. `rdflib` on 3.15. Confirms §7; everything else waits for it.
2. ✅ Package skeleton, `RDFMeta`, slot, URIs, the literal table; pure unit tests. *As built (2026-11-09):*
   `terms.py` (`IRI`, `Lit`, `Quad`), `meta.py`, `uris.py` (with `check_models()`, not yet called at server start, which
   comes with the routes), `literals.py`. `rdflib` is not a dependency yet, and `RDF_ONTOLOGY_URL` is read if a project's settings
   declare it, not added to `BaseSettings`. The `pgo:` namespace waits for the conversion.
3. `convert()` for literals, entities, relations, edge nodes, against field definitions, then embedded, annotated,
   wrappers, spaces. Tests with the kitchen-sink models and `tests/support/sample_data.py`.
4. `markers` on relations in `pangloss-models`, `RDFField`.
5. Serialisers; routes; live tests on both backends (`pangloss_testing.live`).
6. Ontology, JSON-LD context, SHACL. **The key test: for every sample model, the generated data conforms to the
   generated shapes, and every predicate and class used is in the ontology.**
7. `generate-ontology`; CRM module; `pangloss rdf check`.
8. The button, translations, e2e, and aligning a piece of the demo (`Person`, `Activity`).
9. The dump. **Measure on the 642k database**: time, size, triples per node. Decide then on a bulk read.
10. Converter hook; dates, typology, Zotero.
11. Dereferencing, VoID, the rest of §11.

With each step: docs (`implementation_docs/rdf.md` with markers, `implementation_docs/status.md`, `implementation_docs/packages.md`, a guide page), and the Pangloss
skill (new package, new marker support, the `_rdf_meta` slot), then `check_skill.py`.

## 13. To check, in order

1. ✅ A plain mixin as a parent of a declared class (§7); the SDK build of the demo, which has them, passes.
2. ✅ `rdflib` on Python 3.15 (§10).
3. ✅ Not needed: an entity is read with `get_entity_without_incoming`, what `GET /api/NAME/{id}?incoming_limit=0` uses.
4. ⏳ What the form sends for nested items on an update: not checked. Until it is, only head URIs are promised to last (§5).
5. ✅ A view of a generic has the generic's own name (`InRole`), and its `_owner` is the generic.
6. ✅ `get_incoming_fields`, of the backend's operations, as the API does. What it gives may be nested, and says nothing of its head.
7. ✅ None: a view has no `DBField`. `pangloss_dates.rdf` asks the date class to work its bounds out again.

## 14. Still open (each has a default, so none blocks starting)

| Question | Default in this plan | Alternative |
|---|---|---|
| The address of the structural terms | The project's own (settled: see "As built") | `RDF_CORE_URL`, shared between projects |
| Enums | Literals | A `skos:Concept` per member: better for linking, heavier for a short list |
| An entity's external URL | `owl:sameAs` | `skos:exactMatch`: `sameAs` merges everything said about both, which may be too strong a claim for a research identification |
| Usernames in `meta` | As the JSON gives them | `RDF_EXPOSE_USERS=False`, giving a hashed or role-based agent |
| Dereferencing | Later phase | First-class from the start, if publishing soon is the aim |
| Should reasoners be told about spaces | Documented limit (§4.5) | A separate `pgo:` type within spaces |

## As built (2026-11-09)

Steps 1 to 10 are built; of step 11, URIs that resolve (`pangloss_rdf.resolve`), the dataset description and `RDF_LICENSE`, `RDF_DUMP_URL` and `RDF_EXPOSE_USERS`. Where the code differs from the plan above:

- **`pgo:referencedBy`** names the document that refers to the entity, which may be nested (a read of what refers to an entity does not say which head it is in; a nested document has a URI of its own). The limit is per incoming field, at most 500 (`RDF_REFERENCED_BY_LIMIT`), and `pgo:referenceCount` gives the total. There is no `pgo:nextPage`.
- **An outside property through a wrapper** (not considered in §7): `crm:P14` of a statement reaches through a reified relation to its target, as the property's range wants a person and not a role. Through a semantic space or a conjunction it writes nothing: the value is not simply so.
- **A date and CRM** needs no path mapping: the date node is an `E52_Time-Span` with `P82a`/`P82b`, so `RDFField(parent=P4_has_time_span)` on a date field is the whole path.
- **Nothing is generically Pangloss.** `pgo:` in this plan is a name only. The structural terms are each project's own, at `{RDF_ONTOLOGY_URL}/core#`, and defined in its ontology (not the static file of §8); `RDF_CORE_URL` gives them a shared address, and `RDF_PREFIX` / `RDF_CORE_PREFIX` the prefixes (by default from `PROJECT_NAME`, and `core`). The cost: a query for edge nodes is written for one project, unless projects choose to share the address.
- **`check_models` runs** as the server starts (`configure_app`), and `pangloss rdf check` runs it too.
- A class name in an address may also be the Python name when `RDFMeta(class_name=...)` is set, so the console's link (which knows only the type) works; it redirects to the right one.

Not built:

- `Fulfils`: a node is not given the fulfilled classes (a view does not say which).
- Translated `rdfs:label`s in the ontology.
- `pangloss check` and the language server do not know `RDFField` or `_rdf_meta` beyond what `initialise()` refuses.
- The `--derived` graph. Enums as concepts.

**Measured** only on a small database (Memgraph, 2,200 heads, 12 relation values in each `Fact`): `pangloss rdf dump`'s code took 8.6 s, 255 heads a second, 148 quads and 32 KB of N-Quads a head. **Step 9's measurement on the 642k database was not done**: no such database was running. Whether one read per head is good enough at that size is open.
