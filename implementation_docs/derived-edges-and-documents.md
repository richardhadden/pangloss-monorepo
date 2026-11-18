# Derived edges, edges declared on documents, derived documents ⏳

A plan (2026-11-17) for three changes to `pangloss-derived` ([derived.md](derived.md)). The questions are under
[Decisions](#decisions-for-the-user); the plan follows the recommended answer to each.

**Built so far (2026-11-18, uncommitted): steps 1 to 7 of [the eleven](#steps), and most of step 8.** Parts 1 and 2 (`DerivedEdge`, the
exports, `DerivesEdge`) are whole, and are described as built in [derived.md](derived.md); step 4 (citations in the
core) in [entity-identity.md](entity-identity.md#as-built-citations-that-do-not-protect-and-cited-bases-2026-11-17-);
step 5 (`Through`) in [derived.md](derived.md#asking-something-of-the-way-through-and-edge-2026-11-17) and
[structured-search.md](structured-search.md#the-way-of-a-relation-edge-models-and-what-is-asked-of-a-wrapper-built-2026-11-17);
steps 6 and 7 (templates, the trait, the checks; the worker writing the documents) in
[derived.md](derived.md#derived-documents--2026-11-17-the-interface-and-conversion-are-not-built).
Steps 8 to 11 (the interface and conversion, the demo, measurements, shortcut edges)
are not built. Where what was built differs from the plan below:

- `_derives` is a meta slot whose name does not end in `_meta`: `register_meta_slot(..., plain_name=True)` is new in
  the core for it.
- The class of a declared edge is an attribute of its document class's module once the models are initialised, and
  is in that module's stub (not in `derived.pyi`).
- `_derived` of an entity has a section for each way it is in the edges of a class (`GaveTo`, `received_from`,
  `SameGroup:group`), and the page route takes `at=`.
- RDF of derived edges comes through a general "part of a dump" (`pangloss_rdf.sections`), which `pangloss-rdf`
  did not have.
- A `PGCitedBasis` class exists only where an app asks for it (`citations.enable_cited_basis()`), so a project
  without `pangloss-derived` has no migration to make for it.
- Step 6: who may write a derived class is refused through `hooks.in_write` (in the write's transaction), not
  before it; `hooks.not_written_by_people` is the new hook, for the `POST` route and the export.
- Step 6: the check of `DerivedFrom` counts a class as a possible head only if it is concrete and
  `create_directly`. So the plan's own example is refused while a `ChildOf` can be a document of its own; the
  refusal says how to settle it.
- Step 6: a `Var[Agent]` in a template field of `Person` is refused even where a pattern has it at a field of
  `Person`: a variable's class is narrowed only by a pattern of its own (`Person.Where(is_=a)`), as before.
- Step 6: the loop check reads the class of each top-level pattern, not "a place the pattern reaches" inside it.
- Step 6: the similarity weight and `RDFMeta(dump=False)` are not set (the first has nothing to set it on; the
  second is left for step 7 or 9). The trait's fields are in `ReferenceView` and `Where`, not in `HeadView`.
- Step 7: the queue is of **documents** (by id), not of justifications: a pending document is made what its
  justification says, or deleted if it has none. A justification that is gone is deleted at once, and its document
  waits in `derive-retractions`.
- Step 7: "written only when it differs" is by a hash of what was written, kept on the head, not by reading the
  stored document. A merge of entities rewrites the relation itself, so the worker writes such a document once more.
- Step 7: `hooks.set_visibility` is the backend operation `set_published_in_db`, with `published` on a create or an
  update given through the existing `hooks.new_head_properties` / `updated_head_properties`. It does not depend on
  `pangloss-review` being installed (without it everything is published, so nothing is ever set).
- Step 7: the id of a new document is a UUID5 of the key **and the class**; a rule changed to derive another class
  gets new documents.
- Step 7: `via` of a citation through a derived document is the document, also when a statement inside it was
  chosen (`ResolvedCitation.via`, new in the core).
- Step 7: the cited basis is asked for when a class with the trait is declared, so a project with
  `pangloss-derived` and no derived document class has no new class and no migration.
- Step 7, not done: the review task for a citation through a lost derivation (D15: the mark is made and
  `hooks.citation_marked` is told, nothing listens); the take-over at the end of a rebuild (only in a batch);
  `derive status` counts the documents of a changed or removed rule but does not say "will replace"; `RDFMeta`
  default; the admin page.
- Step 8 (2026-11-18): built: a document's class changed in place in the core (conformance
  `test_change_class_document.py`; a citing field that cannot hold the new class refuses it), conversion with an
  adopted justification (`convert.py`, [derived.md](derived.md#made-a-document-of-someones-own-2026-11-18)), the
  "why" section, no Edit/Delete/New for a class people do not write (`writtenByPeople` in the export, instead of
  `createDirectly: false`, which also kept a derived class out of the search form). Not built: sources into a `Cites`
  field of the target, the review tasks (D15 and "converted"), the author clearing `derived_context`, "Derived from
  this", the search filter, a cited basis and an unprotected citation shown as chips in the interface, browser tests.
- A justification's stored context is now compared and written again when it changes while its nodes stay (a bug of
  the package as it was, found by the tests of this work).
- `Through` (step 5) is as the plan's example has it. Beside it: `Rel(edge=...)`, for the edge that reaches the
  entity whether or not a wrapper is on the way; an edge model and a wrapper each have a `Where` of their own values
  (`Likelihood.Where`, `Identification.Where`); a variable can also be a value of the wrapper itself; and
  `allow=[WeightedAlternative]` is not needed for an edge. A wrapper's own relations cannot be tested in a `Through`.
- The paths through wrappers followed reverse edges, on both backends: from a wrapper inside another, a search or a
  rule reached what was beside it in the outer one. Found by the tests of step 5, and fixed in the core.

**Reviewed against the code the same day**, and corrected: what `create_directly` means, the cycle check, the id of a
derived document, a symmetric rule writing each document twice, review status not reaching the worker, the cost of
`DerivedFrom` as an ordinary citation, citations of a basis, rebuilds, migrations. The review left six questions
(D16 to D21), answered the same day.

1. [`DerivedEdge`](#1-derivededge) replaces `Derived`: exactly two ends, and any other fields are what define the edge.
2. [An edge declared on a document class](#2-an-edge-declared-on-a-document-class): "the entities in field X relate
   to the entities in field Y", with no class or rule written out.
3. [Derived documents](#3-derived-documents): a rule whose head is a new document (a `DerivedFactoid`), its sources the
   documents the rule matched, and its contents made from a template.

Then: [interactions with other packages](#interactions-with-other-packages), especially
[matches criteria](matches-criteria.md) and [graph embeddings](graph-embeddings.md); [steps](#steps); [decisions](#decisions-for-the-user).

## What is there now

`Derived` is an n-ary fact. `SameGroup` has three relation fields (`first`, `second`, `group`), and `Meta(ends=...)`
(by default the symmetric pair or the first two relations) chooses which two are the edge when the facts are made a
graph (`pangloss derive graph`). It is stored as a node:

```
(:PGDerived:SameGroup {key, ...literals})-[:first]->(a) -[:second]->(b) -[:group]->(g)
(:PGJustification)-[:justifies]->(fact), -[:evidence]->(head of each document used)
```

The key of a fact is a hash of its class and **all** its fields. So the group is already part of what the fact is:
two people in two groups have two `SameGroup` facts. What is missing is that the model and the API do not say that
two of the fields are the ends and the others qualify the edge. A class with three ends can be declared, and `ends`
picks two of them only for the graph export.

## 1. `DerivedEdge`

### Declaring

```python
from pangloss_derived import DerivedEdge, Object, Subject, SymmetricLabel, Var, rule


class SameGroup(DerivedEdge):
    """Members of the same group (a family, an order, an army)"""

    _meta = DerivedEdge.Meta(symmetric=True)

    first: Annotated[Person, SymmetricLabel("member")]     # the two ends, in either order
    second: Annotated[Person, SymmetricLabel("member")]
    group: Group                                          # a qualifier: part of what the edge is


class GaveTo(DerivedEdge):
    """Gave something to"""

    giver: Annotated[Agent, Subject()]
    receiver: Annotated[Agent, Object(reverse_name="received_from")]


@rule(types=[family, social])
def same_group(a: Var[Person], b: Var[Person], group: Var[Group]):
    return SameGroup.Derive(first=a, second=b, group=group).when(
        MemberOf.Where(member=a, group=group),
        MemberOf.Where(member=b, group=group),
    )
```

- **The ends are named fields** (the user's decision, D1), so that they read well in the interface. Two kinds:
  - an asymmetric edge: one field marked `Subject()` and one `Object()`. `Object(reverse_name=...)` names the edge as
    read from its object ("received from").
  - a symmetric edge (`Meta(symmetric=True)`): the two fields carrying `SymmetricLabel` are the ends, which means the
    same name for either ("member"), as now.
  `initialise()` refuses a class without exactly two ends, or with a third relation marked as an end. Each end is an
  entity class (or a trait of entities, as now). `Meta(ends=...)` goes.
- **Every other field is a qualifier**: a relation to an entity (`group: Group`), or a literal (`year: int`). As
  now: no documents, embedded objects or lists.
- **Qualifiers define the edge.** The key is the class, the two ends and every qualifier (as today). `SameGroup(A, B,
  group=Medici)` and `SameGroup(A, B, group=Sforza)` are two edges between the same people.
- **Values that do not define the edge**: values taken from the path of each justification (a probability on the
  identification it went through: [D8](#reading-through-wrappers-d8)) are fields marked `PerJustification()`. They
  are kept on the justification, not in the key, and shown with each justification. There are no aggregates.
- **Symmetric**: stored once with the ends in order of id, and never from a thing to itself (as now).
  `reverse_names` (a key for each field) goes, since there are now only two directions.
- `Meta` keeps `max_per_seed` and `abstract`. A `DerivedEdge` subclass of another is a narrower edge, as now.
- **`Derived` is removed**, with no alias (D3).

### Storage: unchanged in shape

```
(:PGDerived:SameGroup {key, type, pg_subject, pg_object, ...literal qualifiers})-[:first]->(a) -[:second]->(b) -[:group]->(g)
```

The edges keep the field names. The node records which two fields are the ends (`pg_subject`, `pg_object`: the names
of the fields, prefixed so that a qualifier may be called `subject`), so that a reading needs no class to know them. The node stays. It is needed because:

- **justifications point at the fact** (`-[:justifies]->`), and the reader's visibility is worked out from them
  (`fragments.derived_visible`). An edge cannot be the end of another edge.
- **entity qualifiers stay links.** A group's page can list the edges it qualifies, a merge of the group moves them,
  and a deleted group hides them. On a plain edge the group would be an id in a property, and a merge, a deletion or
  `$derived` would have to treat it as a special case.

"As if it were a single edge" is a matter of reading, not storage:

| Where | What it gives |
|---|---|
| A view (`GaveTo.get`, `/api/derived/GaveTo/{id}`) | `{"type": "GaveTo", "id", "giver": ref, "receiver": ref, "ends": ["giver", "receiver"], "qualifiers": {...}, "symmetric", "plain", "contextLabels", "justifications": [...]}` |
| `_derived` of an entity | Unchanged in shape: the other end, which end it is (`giver`, or `member` for a symmetric one), and the qualifiers. **Read from a qualifier entity** (the group), which is at neither end: a count for each class, and a first page whose rows give both ends |
| `pangloss derive graph` / `/api/derived/graph/{type}` | One edge per fact, `source`/`target` as now, `attributes` the qualifiers. CSV as now. GraphML added (`--graphml`), since Gephi and Cytoscape read it |
| RDF (`pangloss-rdf`) | What `rdf.md` already does with a relation: a direct triple `a :sameGroup b` and an edge node (`pgo:Edge`, an `rdf:Statement`) with `rdf:subject`/`predicate`/`object`, the qualifiers, and `pgo:justifiedBy` the evidence documents. **Not exported today** at all: this is new |
| Search | `Person.Where(derived_=GaveTo.Where(receiver=b))`, as now. Added: on a symmetric edge, `SameGroup.Where(first=b)` matches either end |

### A shortcut edge (D2)

Beside the node, the worker can write `(a)-[:SameGroup {key}]->(b)` (with the ends in order of id when symmetric).
The user's answer was "if it makes lookups more efficient, yes". What it makes faster, and what it costs:

- **Not the API's reads.** "What is derived about A" goes from A to the node (one hop) and so to the other end. The
  node has to be read anyway, because who may see a fact is worked out from its justifications. That has to apply at
  once, when a source is deleted or unpublished, so it cannot be a property the worker copies onto the edge.
- **Paths and graph algorithms.** "Connected to A by up to three `SameGroup` edges", PageRank or communities in MAGE /
  GDS, and Cypher written by hand. Each step saves a hop through a node, and paths of unknown length become
  `-[:SameGroup*1..3]-`. These reads do not take account of the reader: they are for admins, exports and analysis.
- **The cost: every core query that takes "any edge between two items" would see it.** The incoming lists
  (`read_incoming.py`: `(:PGIndexableNode {id})<-[edge]-(source:PGIndexableNode)`), the check of what refers to an
  entity before a delete (`delete_node.py`), usage, the RDF dump, and the embeddings' walk. Today none of them sees
  derived facts, because `PGDerived` is not `PGIndexableNode`. A shortcut edge between two people would show up as
  "Smith: incoming: SameGroup from Jones", and make Jones "referred to". Each such query needs a condition that
  leaves them out (a general `fragments.model_edge(e)`, on a property `derived: true`), and its cost has to be
  measured on the hot reads. Also an edge more per fact, and a merge has to remove the absorbed entity's.

So: **an option of the class, `Meta(shortcut=True)`, off by default**, built after the rest. Its first step is the
exclusion in the core queries, with a conformance test that a shortcut edge appears in none of them. It is built when
something needs the paths. Recorded as the plan's reading of D2, to confirm.

### What else changes

- `pangloss derive rebuild` after upgrading. The hash of every rule changes (its head does), so the worker rebuilds
  them when it starts, and deletes the facts of the old classes. No data migration of the facts: they can always be
  rebuilt. (Derived documents cannot be treated so: [Rebuilds](#rebuilds).) Migrations are needed for part 3 only
  ([Steps](#steps)). The demo's `derived.py` is rewritten.
- **The new default of D8** (reified relations and conjunctions transparent) comes in with this step, not later, so
  that `plain` and the context labels of the existing facts, and the tests of them, change once.
- `DerivedSection` (interface): reads the ends from `ends`, and the label of the other end from its field (or the
  `SymmetricLabel`, or the `reverse_name` when read from the object). Translations: the class, its fields, the
  `reverse_name`.
- The stubs: `GaveTo.Derive(giver: Var[Agent], receiver: Var[Agent])`, as now.

## 2. An edge declared on a document class

```python
from pangloss_derived import DerivesEdge


class Transfer(Statement):
    _derives = [
        DerivesEdge("GaveTo", subject="given_by", object="given_to", reverse_name="received_from",
                    types=[exchange, social]),
    ]

    given_by: ...
    given_to: ...


class Activity(Statement):
    _derives = [DerivesEdge("CoParticipants", subject="participants", object="participants", symmetric=True)]
```

At `initialise()` each `DerivesEdge` becomes **an ordinary `DerivedEdge` class and an ordinary rule**, so everything in
part 1 holds: the worker, justifications, contexts, the graph, the API, the interface. For `Transfer` it is the same as
writing out:

```python
class GaveTo(DerivedEdge):
    given_by: Annotated[Agent, Subject()]
    given_to: Annotated[Agent, Object(reverse_name="received_from")]

@rule(types=[exchange, social])
def Transfer__GaveTo(doc: Var[Transfer], a: Var[Agent], b: Var[Agent]):
    return GaveTo.Derive(given_by=a, given_to=b).when(Transfer.Where(is_=doc, given_by=a, given_to=b))
```

**The names of the ends** ([D18](#decided-after-the-review), decided): by default
those of the document's fields, or given, `ends=("giver", "receiver")`. They have to be given when **two document
classes feed one edge**, which is the usual case for a network: `Transfer` (`given_by`, `given_to`) and `Sale`
(`seller`, `buyer`) both declare `DerivesEdge("GaveTo", ..., ends=("giver", "receiver"))`. That makes one class and a
rule for each document class. `initialise()` refuses two declarations of one name that differ in their ends, in
`symmetric`, in `reverse_name` or in their qualifiers; the class of each end is the nearest class or trait that the
fields of all the declarations share. A symmetric edge from one field (`participants`×`participants`) has
`SymmetricLabel` from `DerivesEdge(..., label="participant")`, by default the field's name.

- **A meta slot** (`_derives`, a list, since one class can give several edges), registered by `pangloss-derived`.
  It is inherited, as meta slots are. A subclass gets no second rule, because the parent's `Where` already matches it.
  A subclass may declare its own, more particular edge.
- **The end classes** are read from the fields. A field through a reified relation, a conjunction or a space is seen
  through as rules see through it (`DerivedMeta`), and a list field gives every item. Two list fields give every pair:
  `participants`×`participants` is the co-participant rule. The same field as subject and object needs
  `symmetric=True`, and never pairs a thing with itself.
- **`qualifiers={"role": "role"}`**: fields of the document (literals, or a relation to an entity) that define the
  edge, as in part 1. They are optional.
- **One edge per pair** (D4, decided) and set of qualifiers, whatever the number of documents. Each document is a
  justification. Their count (`justification_count`, which a reading of a fact has already) is the weight in
  `derive graph`; it is added to the export if it is not there.
- **The `RuleType`s** named in `types=` are declared in the models' module or one it imports, not in `derived.py`,
  which imports the models.
- **The edge class**: `DerivedEdge.named("GaveTo")`, and in the stubs (`derived.pyi`) as a name, so `GaveTo.list(...)`
  type-checks. `pangloss check` and the language server find a field name that does not exist, or one that is not
  an entity relation.
- `derived.py` stays for rules that join several documents. `DerivesEdge` is for the one-document case, which is most
  of what a network is built from.

## 3. Derived documents

### What it is for

A rule finds a pattern across documents ("A was a child of P", "B was a child of P", in two sources) and writes a
**document** saying what follows ("A and B were siblings"). The document's sources are the documents it rests on. It
is a document because it should be read, searched, cited, labelled and exported as one, and its statements are
ordinary statements.

### Declaring

A derived document class is **any document class with one `DerivedFrom` field** (D11, decided) and the trait
`DerivedDocument` ([D21](#decided-after-the-review), decided). `Factoid` is the user's project, not a requirement: a
`DerivedLetter` or `DerivedOrder` works the same way. `DerivedDocumentMeta` is optional, for the options below. In the
project's models:

```python
from pangloss_derived import DerivedDocument, DerivedDocumentMeta, DerivedFrom


class DerivedFactoid(Document, DerivedDocument):
    """What follows from what other factoids say"""

    _meta = Document.Meta(label_template="Derived: {statements|join('; ')}")
    sources: list[DerivedFrom[Factoid]]       # written by the worker: the documents its justification rests on
    statements: list[Statement]
```

- **Not `create_directly=False`.** That option means "only ever part of another document": creating one raises
  `PanglossNotCreatableError`, and a search for the class is refused. A derived document is a head, made and searched
  as one. What stops a person making it is the check that stops them changing it: a create, update, delete, undelete
  or restore by anyone but the worker is refused ([below](#which-document-and-when-it-changes)). The API gives the
  class no `POST`, and the export says `createDirectly: false` so that the interface offers no `+`; both through a
  general "who may write this class" hook, not through `create_directly`.
- **The trait `DerivedDocument`** carries what the worker records on the head, as `Dateable` carries the sort days of
  a date: the `DBField`s `derived_by` (the rule) and `derived_context` (labels). A `DBField` has to be declared on a
  class, and the hook for head properties is given the class, not the document, so without the trait there is
  nowhere to put them.

In `derived.py`:

```python
@rule(types=[family])
def siblings(a: Var[Person], b: Var[Person], p: Var[Person]):
    """Two children of one parent are siblings"""
    return DerivedFactoid.Derive(
        statements=[Sibling.Template(people=[a, b])],
    ).when(
        ChildOf.Where(child=a, parent=p),
        ChildOf.Where(child=b, parent=p),
        distinct(a, b),
    )
```

- **`Model.Template(...)`** is a generated model shaped like `Create`, in which any relation to an entity, and any
  literal, may be a variable. Literal values and nested documents are written as in `Create`. It is made for every
  class a derived document can contain, as `Where` is, and only with `pangloss-derived` installed. Because it is
  declarative, `initialise()` checks it (a variable of the wrong class, a missing required field), it has a hash
  (so a changed template rebuilds), and `explain` can show it (D7, decided).
- **The head fields**: the `DerivedFrom` field is filled by the worker, so the rule gives everything else.
- **Which nodes of the pattern are "the document aspects"**: the head document of every node a pattern matched, as
  `-[:evidence]->` is today. For `ChildOf` statements inside factoids, that is the factoids. `DerivedFrom[Factoid]`
  refuses a rule whose patterns can reach a head that is not a `Factoid`.

### Which document, and when it changes

- **One document per justification** (D5, decided). Its sources are that justification's evidence. The same siblings
  found through another parent, or in a third source, are another document. So there is no merging of sources, and a
  document never changes because another justification came or went.
- **Its id is made once and then stored.** When a justification is first found, the id is a UUID5 of its key (the
  rule, the nodes of its patterns, the values of its variables), and it is written on the `PGJustification`
  (`document_id`). It is not worked out again from the key, because the key can change while the document stays:
- **When the values change but the pattern nodes do not** (an entity merged, an identification changed), the key
  changes. In one batch the worker sees one justification gone and one new, of the same rule and the same pattern
  nodes, and the new one **takes over** the `document_id`: the document is updated, and its id, history and citations
  are kept. Only when it is one for one. Several justifications can share their pattern nodes (one activity gives
  every pair of its participants), and then nothing says which became which: those gone are deleted and those new
  are made.
- **Each document once: `unordered(a, b)`.** The `siblings` rule matches (A, B) and (B, A), with the same two
  statements in the other order: two justifications, so two documents saying one thing. Edges avoid this with
  `symmetric`; a document has no such option, and a template is not the same with its variables swapped
  (`people=[a, b]`). So a rule says it: the constraint `unordered(a, b)` matches each pair once (the first by id).
  `initialise()` checks that the body is the same with the two swapped (if it is not, half the pairs would be lost,
  which is the mistake the symmetric classes made at first), and warns of a document rule whose body is symmetric in
  two variables and does not say `unordered`.
- **The ids of its nested nodes are worked out**, a UUID5 of the document's id and the node's path
  (`statements/0`). A template gives no ids, and a rule further down a chain has the ids of the statements it matched
  in its own key. With new ids at every update, each document after it would be deleted and made again.
- **The worker writes it through the ordinary write path** (`create`, `update`, `delete`, `undelete` of a head), as the
  Zotero sync does (`acting_as` a user `derived`). So labels, history, review, pending marks, the text index and
  everything else that follows a save apply, and nothing in the core has to know about it.
- **It changes only when its content does.** The worker compares what the template gives, and the sources, with the
  stored document, and writes only if they differ. Otherwise each worker run would add a version to history.
- **No justification left** → the document is deleted (flagged, as every delete is). If one returns it is undeleted, so
  its history and anything citing it are kept.
- **Nobody writes it but the worker** (D6, decided). A create, update, delete, undelete or restore (history) by
  anyone else is refused with a `PanglossWriteError` that says so, and names the way out: converting it. What the
  core itself does to every document still happens: a merge of entities moves its relations, and a migration
  rewrites it.
- **A source deleted between finding and writing** makes the write of its `DerivedFrom` fail
  (`PanglossReferenceError`: what is cited must be there). The worker leaves that document out; the delete marked
  the source's head, so the next batch settles it.

### Rebuilds

"Derived facts can always be rebuilt" is true of edges. A derived document has a history, an id that citations
record (`via`), and perhaps an adopted justification. So:

- **A rebuild keeps the justifications it finds again** (as now: their generation is set), and with them their
  `document_id`. Nothing is deleted and made again that still holds.
- **Rules are built in order**: a rule that reads derived documents after the rules that write them (the order of
  the [cycle check's](#what-a-derived-document-may-not-do) graph), and the queue of documents is emptied between
  them. Built in the registry's order, a chained rule would find nothing, delete its documents, and undelete them in
  a later batch: two versions in the history of each, and `derivation_lost` set and cleared on what cites them.
- **A renamed rule is another rule**: every document of it is deleted and made with a new id. `@rule(name=...)`
  keeps the name when the function's changes. The same for a variable added to a rule (it is in every key).
  `pangloss derive status` says how many documents a changed rule will replace before the worker is started.
- **Adopted justifications** ([conversion](#converting-it-into-an-ordinary-document-d6)) are a record that is kept
  through a rebuild, and through the removal of their rule.
- **Time.** A document is a save (about 12 ms, with history and the text index). A first build of 100,000 documents
  is about 20 minutes, during which the queue is busy. To be measured (step 10).

### Converting it into an ordinary document (D6)

"Make this a document of my own": the user's project will have an `AbstractFactoid` with two subclasses, `Factoid`
(written by people) and `DerivedFactoid` (derived). Converting a `DerivedFactoid` makes a `Factoid`.

- **The derived document itself becomes the ordinary one** (D14, decided): the same id, its class changed in place
  (`DerivedFactoid` → `Factoid`). Its history goes on: the versions written by `derived`, then the user's.
- **What carries over**: the fields the two classes share (those of their nearest common class: `statements`). The
  fields only the target has (`Factoid.source`) are left for the user. So conversion **opens the target's form,
  filled in**, and nothing is written until it is saved. The derived document's sources are shown beside the form,
  and go into a `Cites` field of the target if it has one of the right type (and are then protected, as any
  citation). The `DerivedFrom` field has no counterpart and goes.
- **Which classes it may become**: `DerivedDocumentMeta(converts_to=Factoid)`; by default the non-derived classes that
  share a parent with it.
- **A new capability of the core: a document changes class in place.** Today `changing_class_from` is for entities
  only and refuses a document (`test_only_an_entity_changes_class`). An update already writes everything below the
  head again, so for a document it is the head's labels, the check that the payload fits the new class, and the
  history of a version of another class. It becomes general (any document, not only derived ones), with conformance
  tests. What it must refuse: a change that would remove a part another document cites (as an update does already).
  For a derived document there is none, since nothing ever cites one (citations go to the basis).
- **History**: compare works across the change on the shared fields. A restore of a version from before the
  conversion is refused ("this would make it derived again").
- **Review**: once converted it is reviewable, as its class says. It keeps the status it had (published if its
  derivation rested on published documents), and gets a review task "converted from a derived document", as D15 does
  for citations. (My call, consistent with D15 and with "editing does not change the review state"; easy to change.)
- **The worker** records its justification as **adopted**, and never writes that id again.
- **`derived_context` stays** ([D19](#decided-after-the-review), decided). A converted document is a `Factoid`, so a rule
  that blocks `DerivedFactoid` reads it as what a person wrote, and criteria read it. If it rested on a `Negative`
  statement or a description (`MatchesCriteria`), dropping the record would launder that by a click. So the labels
  stay on the head and are shown ("converted from a derivation through: …"), the exclusion of the matches-criteria
  plan still applies to it, and a rule that reads it inherits them. The author can clear them, as a statement that
  the document no longer rests on the derivation.
- **If the derivation later stops holding** (a source deleted), the converted document is not touched, since it now
  belongs to its author. Its page says "the derivation it was made from no longer holds", and `derive status` lists
  it. Citations through it (`via`) are marked `derivation_lost` as before; the chip in their group leads to the
  converted document.

**Issues with `AbstractFactoid` → `Factoid | DerivedFactoid`**. None prevent it. They are what to look out for:

| | |
|---|---|
| A rule pattern on `AbstractFactoid`, or on `Statement`, matches derived ones as well | The cycle check catches the loops. Where the rule should only read what people wrote, write it on `Factoid` |
| A field `Cites[AbstractFactoid]` lets a user cite a derived one | Allowed: what is saved is its basis ([Citing a derived document](#citing-a-derived-document)) |
| Lists and searches of `AbstractFactoid` mix the two | The interface marks derived ones (a chip style, and the search filter "derived / not derived") |
| Who writes it, review, label templates | By class: only the worker writes a `DerivedFactoid`, and it is not reviewed. Each subclass can have its own label template |
| Putting `AbstractFactoid` above an existing `Factoid` | A migration in the project (new labels), as for any new parent class |
| Fields on `AbstractFactoid` | Only those both have (`statements`). The derived one's `DerivedFrom` and the real one's `source` stay on the subclasses |

### `DerivedFrom[T]`: a citation that does not protect

`Cites[T]` protects what it cites: a cited statement cannot be changed without `acknowledge_citations`, nor removed.
If derived documents cited their sources with `Cites`, **every factoid that something is derived from would be
locked**. An editor would need to acknowledge each derived document their edit touches, and could not delete a factoid
at all. That reverses the dependency, since a derived document should follow its evidence and never constrain it.

`DerivedFrom[T]` is read, shown, labelled and exported as `Cites` is. But it **protects nothing and is never marked
changed**: a change to a source is handled by the worker deriving again. In the core it is a general option of a
citation, `protect=False` (not a name of this package), plus a check that only the worker writes it.

**It is stored as a class of its own** (`PGUnprotectedCitation`, with its own indexes on `target_id` and
`target_head_id`), not as a `PGCitation` with a flag. Two costs of an ordinary citation would otherwise fall on the
sources:

- **Every save of a cited head first finds who cites it** (`MATCH (citation:PGCitation {target_head_id: $id})`) and
  reads each cited part: 70 ms for a head cited 1,000 times (`entity-identity.md`). A factoid about a large family is
  the source of thousands of derived documents. Under another label they are not in that index, and a save of a
  source costs what it does now.
- **Writing a citation writes to the cited head** (`pg_cited`), so that a citation and a change of what it cites
  cannot both go through. The worker writing a thousand documents from one factoid would conflict with whoever is
  saving that factoid (the Memgraph conflict on that property is already recorded). An unprotected citation has no
  such race to guard, and writes nothing there.

"Derived from this" on a source's page reads the new class by its own index. A conformance test: a head with 5,000
unprotected citations is saved in the time of one with none.

### What a derived document may not do

These are the rules that keep it from feeding itself and from turning a doubt into an assertion.

1. **Rules read derived documents, but never in a loop** (the user's decision, 2026-11-17). A rule's patterns match
   inside derived documents as inside any other, so rule A can write `Sibling` documents that rule B reads to write
   `Cousin` documents. The worker needs nothing new for this: A's document is a save, which marks `derive` work, and
   B is run on a later batch. It stays exact for the same reason as before (one worker, each head after its last
   write). Each step adds one worker delay (about 300 ms median) and the saves.
   - **`initialise()` refuses a cycle, worked out from the templates.** A template is declarative, so the classes of
     the nodes a rule writes are known exactly: `siblings` writes a `DerivedFactoid` holding a `Sibling`, nothing
     else. The graph has an edge from rule A to rule B when a pattern of B can match a node that A's template writes
     (its class, or one above it, at a place B's pattern reaches). A cycle is an error that names the rules and the
     classes. **Not by document class**: `DerivedFactoid.statements` is `list[Statement]`, so by class any pattern
     "could match inside it", `siblings` (which reads `ChildOf`) would be a cycle of one, and a project with one
     derived class could have no chains at all. Recursion (a fixpoint, delete and derive again) stays out
     ([derived.md](derived.md#what-it-does-not-do)).
   - **Broad patterns are what trip it.** A rule that matches any `Statement` and writes a `Sibling` reads what it
     writes. The error's `fix=` is `block=[DerivedFactoid]` on the rule that should not read derived documents.
   - **`block=` by the class of the head is new.** Today it names the wrappers a pattern passes through. For a
     document class it is a condition on the head of each pattern's node (`NOT hd:DerivedFactoid`), which the
     compiled query has already matched for the evidence. It is added only to rules that block, and measured.
   - **The `DerivedFrom` check is as fine.** "A rule whose evidence could be a head the field does not take is
     refused" is worked out the same way: the heads a pattern can be in are the people's classes that can hold its
     class, and the derived classes that a rule before it in the graph writes with a node it matches. So `siblings`
     can say `DerivedFrom[Factoid]`, and only a rule that does read derived documents has to take them.
   - **Sources of a document in a chain are the derived documents it read** (the user's decision), not the factoids
     behind them. So the chain stays visible ("from the derived 'A and B were siblings', which rests on X and Y"),
     and retraction goes step by step: X deleted, A's document goes, and that removes B's. So the `DerivedFrom` field
     of a class a chain writes must accept the derived class (`DerivedFrom[Factoid | DerivedFactoid]`); a rule whose
     evidence could be a class the field does not take is refused.
   - **Context is inherited.** A justification that reads inside a derived document adds that document's
     `derived_context` to its own, so a document "assuming the identifications" does not become plain one step on.
   - A write of a derived document marks `derive` work only if some rule comes after its rule in that graph.
2. **What a document may be derived through.** Reified relations (identifications) are transparent ([D8](#reading-through-wrappers-d8)).
   A semantic space is not: a fact from a `Negative` statement has a context label, which the reader sees, but a
   document made from it would plainly say what the source denied. So a document rule takes only justifications that
   passed through no space (and no `MatchesCriteria`), unless the rule says which it may (`.when(..., allow=[...])`).
   What it passed through is recorded on the document in a `DBField` `derived_context` (labels), which searches and
   the interface can read.
   **Alternatives and machine identifications** ([D17](#decided-after-the-review), decided). D8 and D13 make every reified
   relation and conjunction transparent. For a document that goes too far in two cases: "Smith is A (60 per cent) or
   B (40)" would give two plain documents, one saying A and one saying B; and an `IdentificationByToolchain` (a
   machine's guess, not yet looked at) would be read as a person's. So `pangloss-library` says `qualify` on
   `WeightedAlternative` and on `IdentificationByToolchain`: edges through them are derived as now and are not plain,
   and a document rule takes them only when it says so (`allow=[WeightedAlternative]`), as the rule that puts the
   probability into the document ([D8](#reading-through-wrappers-d8)) will.
3. **Visibility.** A derived document is a document, and documents are hidden by review status, not by a read rule on
   their evidence. The worker sets its status from its justification (it has one, D5): **published** if every
   document that rests on is published, **unpublished** otherwise.
   - **A general hook** (`hooks.set_visibility`), which does nothing without `pangloss-review`. It writes the head's
     `published` itself: review's own calls refuse a class that is not reviewable. Conformance tests: an unpublished
     document of a class that is not reviewed is hidden from a reader who is not logged in, is not in the review
     queue, and is found by the `published` filter of a list.
   - **A change of review status has to reach the worker, and today does not.** Only writes, merges and relinks mark
     pending work; `pangloss_cypher/review.py` marks nothing. Facts do not need it (they are hidden when read).
     Documents do. So the core marks the head on a change of status (`hooks.pending_work`, as for a write). The
     matches-criteria plan needs the same mark, so it is built here, once.
   - **The delay is the worker's, not a constant.** Facts are hidden at read time; a derived document follows only
     when the worker has run. With an idle worker that is a few hundred ms. During a build, behind a large fan-out,
     or with `DERIVED_WORKER_IN_SERVER = False` and no worker running, a document whose source was deleted or
     unpublished stays public until its turn. So the queue of documents does **retractions first** (deletes, and
     changes to unpublished, before anything is made), and `derive status` and the admin page show how far behind
     it is.
4. **Fan-out (D9).** The worker already runs in the background, so a large fan-out never slows a save. What it does
   is hold the queue: one worker works at a time, and a pair rule over a family of 50 is 1,225 documents at about
   12 ms a save, 15 s during which no other derivation is made. So:
   - **Documents have their own kind of pending work** (`derive-documents`). The facts' worker finds the
     justifications and queues the documents to write. A second loop writes them in small transactions, so facts
     (and other documents) do not wait behind a big one. The one-worker lease covers both, so the result stays exact.
   - **The cap stays, as a safety net** against a rule or data that would fill the database: `max_per_seed=2,000`
     for document rules, with `pangloss derive dry-run` to see the count before a rule is switched on.

### Reading through wrappers (D8)

The user's decision: **a reified relation is transparent by default** (an `Identification` included). A rule matches
through it as if it were not there, and it is not in the context, so the facts and documents it gives are plain. A
pattern can still put conditions on what it passes through, and a rule can use the values it finds there.

- **The default changes for every rule**, of edges and documents alike: `derivation_of` gives `transparent` for a
  `ReifiedRelation` or a `Conjunction` with no `DerivedMeta` of its own (today `qualify`; conjunctions by D13). An
  exclusive conjunction (`WeightedAlternative`) is still exclusive: a justification takes one alternative at a time,
  but is plain. Semantic spaces stay `qualify`, so "plain" now means: through no space and no `MatchesCriteria`.
  `MatchesCriteria` says `qualify` on its own class, so the matches-criteria plan is not affected. A class can still
  say otherwise (`_derived_meta = DerivedMeta(derivation="qualify")`), and the library does for
  `WeightedAlternative` and `IdentificationByToolchain` ([D17](#decided-after-the-review), decided). This default comes in
  with step 1.
- **Conditions on the path.** "Through an identification only when its probability is at least 60 per cent." In the
  library the probability is the `percent` of the `Likelihood` edge model of a `WeightedAlternative`, on the edge to
  each alternative. `Rel(through=...)` takes wrapper classes today. It would also take a condition on a wrapper's
  fields and on its edge model:

  ```python
  @rule(types=[exchange])
  def gave_to(a: Var[Agent], b: Var[Agent], p: Var[int]):   # GaveTo has: likelihood: Annotated[int, PerJustification()]
      return GaveTo.Derive(giver=a, receiver=b, likelihood=p).when(
          Transfer.Where(
              given_by=Rel(is_=a, through=[Through(WeightedAlternative, edge=Likelihood.Where(percent=p))]),
              given_to=b,
          ),
          p >= 60,
          allow=[WeightedAlternative],
      )
  ```

  `Through` is a general addition to structured search, not only to rules. **Search cannot filter on an edge
  model's fields today**, so this is new in `pangloss-models` (the `Where`, `check_match`, stubs) and
  `pangloss-cypher` (the compiler), with conformance tests. The search form could use it later. The exact syntax is
  settled when it is built.
- **Using what the path gives.** A variable bound on the path (`p` above) can go into the head. For an edge it is a
  `PerJustification()` field (`likelihood: Annotated[int, PerJustification()]`): kept on each justification, not in
  the edge's key, so one edge between A and B still has, say, a justification at 80 per cent and one at 60. For a
  document it is a value of the template, like any other (`Sibling.Template(people=[a, b], certainty=p)`).

### Citing a derived document

(The user's design, 2026-11-17.) A user cites a derived document, or a statement inside one, as if it were any other.
The picker offers it like the others. **What is saved is its basis**: citations of the documents its justification
rests on, each recording that it was cited *through* the derivation. A derived document is never itself cited, so it is
never protected, and the worker can always change or delete it.

- **The basis** is that of its one justification (D5), whatever its class: the nodes its patterns matched (the two
  `ChildOf` statements). A derived document in the basis (a chain, D12) is replaced by its own basis in turn, until
  only documents people wrote are left. A statement inside a derived document is still derived, so it gives the
  basis of its document.
- **Any basis, in any `Cites` field.** The basis need not be of the field's class: `Cites[Sibling]` can hold the two
  `ChildOf` statements a derived `Sibling` rests on.
- **One chosen item is one item of the field: a `CitedBasis`** ([D16](#decided-after-the-review), decided). It is a
  nested document of the citing one, a variant of every `Cites` field beside the citation of its own class. It holds
  `via`, and a list of ordinary citations (`basis`), one for each document of the basis. So a field that takes one
  (`Cites[X] | None`) still holds one node, a `MaxLen` counts what the person chose, and the views, the TypeScript
  types, the form's checks and `check-data` need no rule that "these three count as one". The citations inside it
  are `PGCitation`s like any other, so protection and "who cites this" find them with no change.
- **`via` is checked when written.** A read gives `via` and the basis, and an update sends them back, so a payload
  could name any documents as a "basis" and put them in a field that does not take their class. The write accepts a
  `CitedBasis` only if it is what the hook made of a derived document in this write, or is the same (its `via` and
  its targets) as one the stored document has already. Anything else is a 422.
- **`via`, on the `CitedBasis`**: the derived document's id, the rule, its label at the time of citing, and the key of
  its justification. On the page the citations are grouped under it: *"Derived: A and B were siblings (rule
  `siblings`), from: …"*, with a chip of the derived document while it exists.
- **Protection** applies to the basis, as for any citation: editing one of the `ChildOf` statements needs
  `acknowledge_citations`, and deleting its factoid is refused (but for an admin's override), as for any cited
  document. The user's document rests on it, so this is right. It also means that **a derivation someone has cited
  is seldom lost by a delete**: what loses it is an acknowledged change to the basis, a changed or removed rule, a
  condition no longer met, or a source no longer published.
- **When the derivation changes or stops holding.** The worker updates a derived document in place (its values
  changed: an entity merged), or deletes it (no justification left). In the transaction of that write (a general
  hook that runs in it, as `hooks.pending_work` does) every `CitedBasis` whose `via` names it is marked, found by an
  index on its `via` id, as a change to what is cited
  marks `changed_since_cited` today: `derivation_changed`, or `derivation_lost`.
  - The citing document's page says so on the group ("this derivation no longer holds"), with the label and rule
    kept in `via` and a link to the derived document (still there, flagged deleted, so it can be shown struck
    through).
  - If the derivation comes back (the same justification, so the same id: the document is undeleted), the mark is
    cleared.
  - The user clears it as they clear "changed since cited": by saving the document with the citations acknowledged,
    or by removing them.
  - **Through a general hook** (`hooks.citation_marked`), `pangloss-review` gives the citing document a task: "a
    derivation it cites no longer holds". **It stays published** (D15, decided). `derive status` and a search filter
    list these documents too.
- **Saving and reading back differ.** The payload names the derived document, and a read gives the basis
  citations with `via`. An update replaces the whole document, so sending back what was read works.
- **In the core: a general hook** (`hooks.resolve_citation`): before a citation is written, an installed app may
  replace it with a `CitedBasis`: the targets, and a `via` it supplies. `pangloss-derived` uses it. The core knows nothing of
  derived documents.

### Where it is shown

- Its own page is a document page. Its `sources` are chips (citations), and a "Derived" band (from the module) says
  which rule made it and why, from its justifications. It has no edit, delete or `+` buttons.
- A source factoid's page lists "Derived from this" (the incoming `DerivedFrom`), as "Cited by" lists citations.
- **In the search of everything, as any document** ([D20](#decided-after-the-review), decided). A class can say
  `global_search=False`. The cost to keep in mind: one family can give 1,225 documents, each about 4.5 ms in the
  text index, and as many results for a name. It is in what step 10 measures.
- Structured searches find it as any document, with a filter "derived / not derived" in the search form (the `DBField` `derived_by` of the
  trait: the rule).

## Interactions with other packages

### Matches criteria ([matches-criteria.md](matches-criteria.md))

| Issue | What to do |
|---|---|
| **Edges: `$derived` in criteria (step 12).** Rule 1 there filters facts by their justifications' `context_labels`, and rule 2 marks entities when the worker changes facts | Unchanged by `DerivedEdge`: the node, the justifications and their `context_labels` stay. Edges declared on documents are ordinary facts, so they are covered too. When step 12 is built, the mark of rule 2 must also cover qualifier entities (a group whose `SameGroup` edges change), not only the ends |
| **Documents: criteria read them** (D10, decided). "Someone said by a derived factoid to be a sibling of X" is a criterion like any other | Nothing to add for most: a derived document is a document, its writes are saves that mark criteria work, and its review status (set by the worker) gives the two results, everyone's and the logged-in reader's |
| **Documents: a loop through criteria.** A description's candidates are read by a rule (`qualify`). With rule 2 above, that rule writes no document unless it allows `MatchesCriteria`. If it does, the document names the candidate plainly. Criteria evaluated elsewhere would then find that statement, outside any `MatchesCriteria`, and rule 1 of "What is searched" would not stop them | Criteria do not read inside a derived document whose `derived_context` contains `MatchesCriteria` (inherited along a chain, D12). A general condition in the search compiler, next to `exclude_wrappers`: `exclude_derived_context=["MatchesCriteria"]`, which `pangloss-derived` supplies through the extension hook. An ordinary search is unchanged |
| **Documents: laundering a guess.** A template variable bound through a description would write the candidate as a plain relation | The same as rule 2 above: refused unless the rule allows `MatchesCriteria`. If it does, the document carries `derived_context` |
| **Two queues become three.** A save → derive → (derived document saved) → criteria → derive... | Each stage marks the next through `hooks.pending_work`, as planned there. "When the queue is empty" in the churn test means every queue. The cycle check of rule 1 keeps it finite |
| **`Computed()`** (planned there) | A possible base for `DerivedFrom`: both are "written by the server, not the user". But a `Computed()` change makes no version, and a derived document's changes should be in history. `DerivedFrom` stays a citation option, and the two do not depend on each other |
| **`MatchesCriteria` inside a template** | Not allowed in a `Template`: a derived document says what follows, not a new description |

### Graph embeddings ([graph-embeddings.md](graph-embeddings.md))

| Issue | What to do |
|---|---|
| **Derived edges in the walk.** `PGDerived` is left out today. Shortcut edges or a pass-through node would put them in | Out by default. They add nothing the walk does not already see: the evidence documents join the same people. They would also count the same evidence twice. A per-class weight in `SimilarMeta` can bring a class in later. **The embeddings plan names `SameGroup` facts as held-out pairs to test the vectors.** Any derived edge in the walk makes that test circular. Keep them out at least until the vectors have been tested |
| **Derived documents are `Document`s**, so they are in the walk by default. A `DerivedFactoid` joins the people it names and, through `DerivedFrom`, its sources. That counts each piece of evidence twice and pulls the sources together | `DerivedDocumentMeta` sets the class's similarity weight to 0 by default (decided 8 there: per-class weights). The citation edge is not walked either |
| **Comparing statements / reconciliation.** "Two sources say X" must not count a derived statement as a third source | The comparison takes only documents without `derived_by`. This is a note for that plan, which is not built |
| **On-save refresh.** Each derived document the worker writes is a save, which marks `similar` work | With weight 0, the class is not embedded and marks nothing (`hooks.pending_work` returns nothing for it). Otherwise a large rule would flood the similarity worker |

### The rest

| Part | What happens |
|---|---|
| History | Derived documents have versions, written by the user `derived`. Facts and edges have none (unchanged). The history list can filter out the `derived` user |
| Review | Derived documents are never reviewed, and their status is set by the worker (rule 3), which needs the core to mark a head when its status changes. `reviewable=False` is forced by `DerivedDocumentMeta` |
| Entity merge | Facts: unchanged (a merge marks the heads). Documents: the worker derives again, and a justification whose values changed but whose pattern nodes did not updates its document in place (part 3) |
| `Cites` of a derived document by a user's document | Saved as citations of its basis ([Citing a derived document](#citing-a-derived-document)). A derived document is never itself cited, so the worker can always delete it |
| Label templates | Work as on any document. `{sources}` gives the labels of the cited documents |
| RDF | Derived documents are documents. `RDFMeta(dump=False)` by default on the class, since they are not what a source says. Derived edges: as above, with `--include-derived` |
| Usage (`include_only_when_referenced`), and deleting an entity | An entity named only by derived documents is not "referred to", in usage and in the check before a delete (else an entity could not be deleted until the worker had run). Through a general hook (classes whose references do not count), since the core may not know the class |
| Migrations | The citation model gains `CitedBasis` and the unprotected class: a migration **in every project that has citations**. In the package: indexes on the `via` id of a `CitedBasis` and on `derived_by`. `pangloss-derived` 0002 is not empty |
| Bulk load | Writes nothing derived (unchanged); `rebuild` afterwards |
| SDK | `DerivedEdge.list/get` as now. Derived documents are documents |
| Language server, stubs | `Subject()`/`Object()`, `PerJustification()`, `Template`, `Through`, `DerivesEdge` field names |

## Steps

Each works alone, with its tests on both backends.

1. **`DerivedEdge`** replaces `Derived`: declaration, `Subject()`/`Object()`/`SymmetricLabel` ends, qualifiers,
   `PerJustification()`, `reverse_name`, views, `_derived` (and of a qualifier entity), graph (with the weight),
   search, stubs, translations, `DerivedSection`; **the transparent default of D8/D13, and `qualify` in the library
   (D17)**; the demo's `derived.py`; docs and guide.
2. **Exports of edges**: GraphML from `derive graph`; RDF of derived edges in `pangloss-rdf` (behind `--include-derived`).
3. **`DerivesEdge`** on document classes: the meta slot, making the class and rule, several documents to one edge
   (D18), checks, stubs, `pangloss check`. The demo's `GaveTo` and `CoParticipants` move onto `Transfer` and `Activity`.
4. **In the core, citations**: `Cites(protect=False)` as a class of its own → `DerivedFrom[T]`, with conformance
   tests (no refusal, no "changed" mark, no `pg_cited`, a save of a much-cited source no slower, incoming "Derived
   from"); `hooks.resolve_citation`, `CitedBasis` (D16) and the check of `via`, the `derivation_changed`/`lost`
   marks and `hooks.citation_marked`; the migration of the citation model.
5. **`Through`** (D8): conditions on wrappers and edge models in structured search (conformance tests),
   `PerJustification()` values. Facts first, so it is useful before documents.
6. **`Template`** models (generated, checked, hashed), the trait `DerivedDocument` (D21) and `DerivedDocumentMeta`:
   the cycle check from the templates, `block=` by head class, the fine `DerivedFrom` check, `unordered`, who may
   write the class, `reviewable=False`, similarity weight.
7. **In the core, for the worker**: the mark on a change of review status, `hooks.set_visibility`, the hook for
   classes whose references do not count (usage, delete). Then **the worker writes documents**: stored ids and the
   take-over, worked-out nested ids, create/update/delete/undelete, status, `acting_as("derived")`, marking
   citations through a lost derivation, the `derive-documents` queue with retractions first, `max_per_seed`, rules
   built in order. A churn test checks that a rebuild finds nothing to change and adds no version to any history.
8. **Interface**: the derived document's page (no editing, the "why" band), "Derived from this", the search filter,
   and conversion (the filled-in form, adopted justifications, `derived_context` kept: D19). Before it, in the core:
   a document's class changed in place (`changing_class_from` for documents), with conformance tests and history's
   refusal across it.
9. **Demo**: `AbstractFactoid` / `Factoid` / `DerivedFactoid`, `Sibling` (or a rule the demo's data can feed), a migration, stubs.
10. **Measured** on the 642k scratch DB: the document worker's throughput, a first build, the cost of a fan-out, a
    save of a source with thousands of derived documents, `block=` by head class.
11. **Shortcut edges** (`Meta(shortcut=True)`): the exclusion in the core queries first.

The matches-criteria and embeddings conditions above are recorded in those two plans when they are built. Neither is
built now, so nothing has to change in them yet beyond notes.

## Decisions for the user

Decided 2026-11-17:

| # | Question | Decided |
|---|---|---|
| D1 | End names | **Named fields** marked `Subject()` / `Object()`, or the two symmetric fields with `SymmetricLabel` |
| D2 | A shortcut edge beside the node | Opt-in, `Meta(shortcut=True)`, built last (it speeds paths and graph algorithms, not the API's reads; every core query that takes any edge has to leave it out) |
| D3 | `Derived` | Removed |
| D4 | An edge declared on a document | One per pair |
| D5 | A derived document | One per justification |
| D6 | Editing a derived document | No; converting it into an ordinary document instead (`AbstractFactoid` → `Factoid` / `DerivedFactoid`) |
| D7 | Templates | Declarative (`Model.Template`) |
| D8 | Identifications | Every reified relation transparent unless the class says otherwise; conditions on the path, and its values usable in the head |
| D9 | Fan-out cap | Kept as a safety net (2,000); documents get their own queue so they do not hold facts back |
| D11 | Which classes | Any document class with a `DerivedFrom` field (and, by D21, the trait `DerivedDocument`) |
| D12 | Rules reading derived documents | Yes, by default; cycles refused; a chained document's sources are the derived documents it read |
| D10 | Matches criteria and derived documents | Criteria read them, except those resting on a description |
| D13 | Conjunctions | Transparent too (an exclusive one still takes one alternative at a time) |
| D14 | Conversion | The derived document itself changes class in place (a new core capability for documents) |
| D15 | A citation through a lost derivation | A review task; the citing document stays published |

### Decided after the review

Decided 2026-11-17, on the questions the review left:

| # | Question | Decided |
|---|---|---|
| D16 | One chosen derived document gives several citations | **One `CitedBasis` node** in the field, holding `via` and a list of ordinary citations |
| D17 | `WeightedAlternative` and `IdentificationByToolchain` under D8/D13 | **`qualify` for both, in the library**: edges through them are not plain, and a document rule needs `allow=` |
| D18 | Two document classes that feed one edge | **`ends=(...)` on `DerivesEdge`**, by default the field names; declarations of one name must agree |
| D19 | A converted document's `derived_context` | **Kept and shown**; the criteria exclusion still applies; the author can clear it |
| D20 | Derived documents in the search of everything | **In, as any document**; a class can say `global_search=False` |
| D21 | Where `derived_by` and `derived_context` are declared | **The trait `DerivedDocument`**. D11 is now: a document class with a `DerivedFrom` field and the trait |

Nothing is open. Calls of mine, confirmed by the user (2026-11-17): the converted document keeps its review status and gets a task
(part 3, conversion); a restore across a conversion is refused; `unordered(a, b)` as the way a rule says its two
variables are interchangeable; a document's id stored on its justification, and taken over only one for one;
retractions first in the queue of documents; `PGUnprotectedCitation` as the name of the class of a citation that does
not protect.
