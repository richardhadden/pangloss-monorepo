# Similar items by graph embeddings: an investigation ⏳

Written 2026-11-11, revised the same day after the user's comments (every document, not only heads; walks through
the nodes that are there for modelling; FastRP inside Memgraph; an on-save updater as a query module). **Nothing here
is built.** This page says how documents and entities could be given vectors from the shape of the graph around them,
kept in a vector index, and searched for "items like this one". It covers what the two databases offer, what was tried
and measured on throwaway containers, what would have to be built, and what is left to decide.

## Contents

- In short
- What gets a vector, and the graph between them
- Shaping the walk to the model
- Weighting by the type of document
- Similar by class: the hierarchy as part of the vector
- Use cases: reconciliation and comparing statements (ideas)
- What the databases offer
- What was tried and measured
- Which algorithm
- Where the computing is done
- Does it read the whole database?
- Where the vectors are kept
- The batch: building every vector
- On save: keeping vectors current
- Who may see what
- Declaring it in a project
- API, SDK and interface
- Neo4j
- What would be built
- Decisions for the user
- What is not known yet
- Sources

## In short

- **Every document and every entity gets a vector**: heads and nested documents alike. The nodes that exist for
  modelling (reified relations, conjunctions, semantic spaces, embedded objects) get none. The walk passes through
  them, and which kinds or classes it passes through, or stops at, is set per project.
- **FastRP, run inside Memgraph by a Python query module.** The module installs itself over Bolt
  (`mg.create_module_file`), with no change to the image: numpy 2.2 and scipy 1.13 are already in
  `memgraph-mage:3.14.0`. On a synthetic graph of 920,000 nodes (520,000 documents and entities), a full rebuild took
  **28 s** of scanning and computing and **38 s** with every vector written. Memgraph's own `node2vec` took 204 s on a
  smaller graph.
- **On save, an exact update, not an approximation.** A FastRP vector depends only on the graph a few steps out, so
  the module recomputes just the vectors a save changes: **278 ms** median for one new factoid, giving 47 vectors from a
  neighbourhood of 4,240 nodes. They matched a full rebuild to **1.2 × 10⁻⁷**. It is called by a background worker from
  the existing `hooks.pending_work` queue, not inside the save's transaction. Hubs (a place in 10,000 documents) need a
  cap, past which the update is left to the next rebuild.
- **The batch does not read the database out.** Inside Memgraph nothing leaves the server but the vectors. The same
  algorithm, run outside the database for Neo4j, reads only the edge list (ids, no properties).
- **Vectors on their own nodes, linked by id, not by an edge**: `(:PGEmbedding {of: <id>, vector})`. A head's
  properties are replaced on update, reads return every property of what they touch, and an edge to a model node
  would make the worker's writes conflict with users' saves.
- **Two Memgraph faults found**: a Python procedure returning more than about 100,000 records **loses its last record
  and duplicates another**, so large results have to be paged; and a just-deleted vector can be returned by a search
  until garbage collection.
- **Neo4j**: the same maths in Python outside the database (vectors identical, since the seeds come from ids), and the
  vector index of Community Edition. A new package, provisionally **`pangloss-similar`**; nothing in the core needs to
  know of it.

## What gets a vector, and the graph between them

The nodes Pangloss writes are of six kinds, and the kind is always among a node's labels (the last label, on Memgraph:
`labels_for_model`):

| Kind | Gets a vector | In the walk |
|---|---|---|
| `Document` (a head, or nested in another document) | Yes | A stop: a node of the graph |
| `Entity` | Yes | A stop |
| `ReifiedRelation`, `Conjunction`, `SemanticSpace`, `Embedded` | No | Passed through (by default) |

So the graph that is embedded is a **graph of documents and entities**. Its nodes are every `Document` and `Entity`
(`PGIndexableNode`, not deleted). Two of them are joined when one has a forward edge to the other, directly or through
nodes it passes through. Reverse edges (`reverse: true`) are never followed; a walk that went out and back along the
same relation would count it twice. Records (`PGCreation`, `PGUser`, …), add-on nodes (`PGDerived`, calendar days,
`PGPending`) and anything not `PGIndexableNode` are not in it.

What that gives, for a factoid whose nested statement names a person through an `Identification` (a reified relation)
and two more through a conjunction:

```
Factoid ── Statement ── Person A        (through the Identification)
              ├──────── Person B        (through the conjunction)
              └──────── Place C         (through the conjunction)
```

The factoid and its statement are both in the graph, joined by the containment edge. Factoids that name the same people
come out close, and so do people named in the same kind of statement. Statements and their factoids are similar,
though not identical: the factoid's other statements pull it elsewhere.

Searching near a nested statement in the trial gave the person it names, its own factoid, another statement with the
same people and its factoid, then the place.

## Shaping the walk to the model

FastRP has no walks as such: each iteration averages a node's neighbours' vectors. "The walk" is therefore the graph it
averages over, and that graph is Pangloss's to make. These are the controls, all in the module (and in its Python twin),
none needing the database's co-operation:

| Control | Example | How |
|---|---|---|
| Kinds passed through | Reified relations, conjunctions, semantic spaces, embedded objects (default) | `through=[...]` |
| A class not passed through | A `Negated` or `Hypothetical` semantic space, so that "X was *not* in Y" does not make X like Y | `stop=["Negated"]`: the labels of a node the walk stops at without joining |
| A class left out entirely | A typology (`Occupation`, `Gender`) whose values would be hubs | No vector, and not a node of the graph |
| A field that counts more or less | `born_in` 2.0, `mentioned` 0.5 | A weight on the joined edge (the edge's type is the field) |
| A class kept as a node | A reified relation important enough to be found by itself | Make it a stop that gets a vector |
| Containment | Whether a nested document is joined to the one it is in | On by default |
| How far | FastRP's iteration weights (`[0, 1, 1]` is three steps) | A setting |

**node2vec cannot be shaped like this.** MAGE's `node2vec` and GDS's walk the projection they are given, choosing the
next step by `p`, `q` and an edge-weight property only. A projection of stored paths (`project(path)`) holds the
modelling nodes too, so walks spend their steps in them and they get vectors to throw away. The only way round is to
write joined edges into the database as real edges and keep them up to date: a second copy of the graph. That is one
more reason for FastRP in a module.

## Weighting by the type of document

Asked 2026-11-11: can the type (class) of a document count, and what would it do? There are three ways, and they do
different things. They were tried on a graph with **planted answers**, which the earlier synthetic graphs lacked
(`/tmp/embed-trial/type_weights.py`, numpy only):

- 2,000 people in 100 families of 20; each person also has one of 10 careers, unrelated to family; 50 offices (5 per
  career); 200 places.
- 6,000 `Kinship` documents: two people of one family and a place.
- 6,000 `Office` documents: a person, an office of their career, and a place.
- 12,000 `Mention` documents: three people at random and a place. This is noise, and the most common type, as passing
  mentions are in real sources.

The score is how many of each person's 10 nearest people share their family, or their career, and how many of each
document's 10 nearest documents are of its type.

| Variant | Same family | Same career | Documents of the same type |
|---|---|---|---|
| Chance | 1.0% | 10.0% | 37.5% |
| 1. No weights | 4.0% | 10.6% | 47.5% |
| 2. **A weight per type**: `Mention` 0.2 | 19.9% | 13.0% | 45.3% |
| 2. `Mention` 0 (left out) | 29.1% | 16.1% | 79.6% |
| 2. `Mention` 0.2, `Office` 3 | 7.0% | 27.6% | 41.8% |
| 3. **The type as a feature** (a quarter of the vector starts from the type) | 1.4% | 11.0% | 65.4% |
| 3. … half of the vector | 1.9% | 11.4% | 64.1% |
| 4. **A view per type**, `Kinship` only | 33.0% | 10.5% | — |
| 4. A view per type, `Office` only | 1.0% | 65.4% | — |
| 4. One vector of all three views, weights chosen **in the query**: kinship only | 32.7% | 10.3% | — |
| … office only | 1.1% | 65.2% | — |
| … kinship 1, office 0.5, mention 0.2 | 22.8% | 22.3% | — |

(A view's documents of other types have no vector there, so the documents column is left empty for views.)

**2. A weight per type of document.** This is an edge weight on every join that starts at a document of that class.
- **Its effect is on entities, not on documents.** A document's joins all carry its own type's weight, and FastRP
  divides each node's sum by its total weight, so a document's own first step is unchanged. What changes is how an
  entity averages over the documents it is in.
- It was the largest single gain: turning down the noise type took family from 4% to 20% (to 29% when left out).
- **It also chooses which similarity you get.** Raising `Office` to 3 took career from 13% to 28% and family down to
  7%. A weight is therefore a statement about what "similar" should mean in the project, not a neutral tuning knob.
- It keeps `refresh` exact (weights are local), and costs nothing.
- In `SimilarMeta`: `SimilarMeta(weight=0.2)` on the class, inherited, alongside the per-field weights.

**3. The type as a feature** (GDS's `propertyRatio`: part of each start vector comes from the class rather than at
random). **Not recommended.** It made documents of one type cluster (65%), but a type filter or an index per class does
that exactly. It **destroyed the people's similarity** (family from 4% to 1.4%): every person appears in much the same
mix of types, so the shared part swamps what distinguishes them. A related use was not tried: making people similar by
the *mix* of what is said of them ("people of whom office-holding is recorded"), a likeness of role rather than of
circle. That would want its own measure and a separate vector.

**4. A view per type, mixed at search.** One FastRP vector per group of document classes (say family: `Kinship`,
`Marriage`, `Baptism`; career: `Office`, `Membership`), stored side by side as **one vector**, with one index. The
search scales each part of the *query* vector. Because the index compares by cosine, that is the same as a weighted
sum of the views' similarities, so **the kind of similarity is chosen per search, without another index**. The results
matched separate views (32.7% against 33.0%, 65.2% against 65.4%).
- **It gives the best results for a single question**: career 65%, against 28% at best by weights.
- **It answers a question users will ask**: "people like this one *by family*" against "*by career*", as a control in
  the "Similar" section.
- The views are declared by the project (`SIMILAR_VIEWS = {"family": [...], "career": [...]}`, or a `view=` in
  `SimilarMeta`). Documents of no view are left out or go to an "other" view.
- The vector is longer (3 × 64 = 192 here), so the index build costs more.
- `refresh` after a save recomputes only the views of the saved document's classes.
- **Not measured**: the index's recall when the query zeroes or rescales parts of the vector. HNSW was built for the
  whole vector, so a query far from that may lose recall. This needs checking on the index, not in numpy.

**Decided (2026-11-11): per-class weights (2).** They are cheap and exact, mostly used to quiet noisy classes. Views
(4) stay a possible later addition for projects with distinct questions, and type as a feature (3) is not used. Note
that (3) is the type *mixed into the start vector and carried by the graph*. A class part kept beside the graph's,
never carried, does work, and is the next section. Which
classes are noisy can only be found on a project's data, so the evaluation in "What is not known yet" should try the
weights.

**How a node's class is found: its `type` property, not its labels.** In the trial each document simply carried a
type string, so neither was used. In Pangloss every node written has `type`, the name of its concrete class
(`pangloss_cypher/write_plan.py`). Its labels are that class, every parent class, its heritable traits, the classes it
`Fulfils` by what it holds, and its kind. Labels would therefore be ambiguous: a `Birth` that is also a `Factoid`, has
the `Dateable` trait and fulfils some class has four labels that could each carry a different weight. Resolving that in
the database would need a rule, and Neo4j keeps no order of labels to apply one by.

- **At `initialise()`**, `pangloss-similar` works out one number for each concrete class, with Python's rules:
  `SimilarMeta` is a meta slot, so a class inherits it from its nearest parent or trait that sets it, and the most
  specific class wins. The result is a plain map, `{"Birth": 1.0, "Mention": 0.2, …}`, which can be checked and shown
  (`pangloss similar weights`).
- **The module and the Python path get that map** as a parameter, and look up each document's `type`. That is one
  property read per node, with no label logic in the database. A `type` missing from the map (a class added since)
  gets the default and is warned of.
- **What `type` does not cover** is the classes a document `Fulfils` by what it holds, which are decided per instance
  and only appear as labels. Weighting by them would need labels after all, with a rule for several (the product, or
  the smallest). Not proposed until a project needs it.
- **Which document's weight a join takes:** the document it starts from. A statement nested in a factoid joins its
  entities at the statement's weight, not the factoid's. The containment edge between them takes the nested
  document's weight, so a quieted nested class is quieted all the way up. Reified relations, conjunctions and the like
  have no weight of their own, since the walk passes through them. A per-field weight, where given, multiplies the
  class's weight.
- **Changing a weight is a rebuild.** `PGEmbeddingState` keeps a hash of the map it was built with. A server that
  starts with a different map says so on the admin page, and `pangloss check` warns of it.

## Similar by class: the hierarchy as part of the vector

Asked 2026-11-11: a `CreationOfArtwork` should be like a `CreationOfPainting`, because one is a subclass of the other
(in the demo: `Statement` → `CreationOfPhysicalObject` → `CreationOfArtwork` → `CreationOfPainting`). This is not a
weight, which can only make a class count more or less. It is **a second part of each vector, describing the item's
class**, set beside the part the graph gives:

- **One dimension for each class of the hierarchy.** The demo's `models.py` declares 24, and the packages add some,
  so tens of dimensions.
- **An item's class part** is its own class at 1, its parent at `decay`, the parent's parent at `decay²`, and so on,
  normalised. So `CreationOfPainting` and `CreationOfArtwork` share `CreationOfArtwork`'s dimension and above;
  `CreationOfPainting` and a `Birth` share only `Statement`'s, at `decay³`.
- **Not carried by the graph.** It is the item's own, and FastRP does not average it over neighbours.
- **Its weight is set in the query** (scaling that part of the query vector, as for views), so one index serves "like
  this, whatever its class" (weight 0) and "like this, and of a like class".

**Tried** on planted data (`/tmp/embed-trial/hierarchy.py`):
- 2,000 people in families, each with a craft (painter, sculptor, architect).
- `Creation` → `CreationOfArtwork` → {`CreationOfPainting`, `CreationOfSculpture`}, and `Creation` →
  `CreationOfBuilding`, each naming a person of the matching craft.
- `CreationOfArtwork` itself is used when the kind of work is unknown (by a painter or sculptor).
- `Kinship` and `Mention` documents besides.
- Measured from creation documents: their 10 nearest documents, and their 10 nearest documents *of another class*.

| | 10 nearest: same class | 10 nearest: a person in common | Nearest of another class: parent, child or sibling | … same tree, further off | … unrelated |
|---|---|---|---|---|---|
| Chance | ~13% | ~0.1% | ~22% | — | — |
| Graph only | 27.9% | 14.9% | 63.7% | 28.2% | 8.1% |
| Class part, no hierarchy (decay 0), weight 0.1 | 88.8% | 19.7% | 63.7% | 28.2% | 8.1% |
| **Hierarchy, decay 0.5, weight 0.1** | 75.3% | 19.8% | **76.1%** | 20.5% | 3.4% |
| Hierarchy, decay 0.5, weight 0.3 | 98.9% | 19.2% | **87.8%** | 10.8% | 1.4% |
| Hierarchy, decay 0.8, weight 0.1 | 62.0% | 18.6% | 78.8% | 19.1% | 2.1% |
| Hierarchy, decay 0.8, weight 0.3 | 91.8% | 19.5% | 89.1% | 10.3% | 0.6% |
| The class part carried by the graph instead (decay 0.5) | 45.3% | 23.2% | 68.1% | 18.9% | 13.0% |

What it shows:

- **It does what was asked.** With the hierarchy, a document's nearest neighbours of other classes are mostly its
  parent, child and sibling classes (76-89%, against 64% from the graph alone). Unrelated classes all but disappear.
- **What the graph says survives.** Within the classes it favours, ranking is still by the graph, so "a person in
  common" went up (15% to 19-20%).
- **Two settings, each with a plain meaning.** The *weight* says how much class counts against connections; at 0.3
  nearly every result is of the same class. The *decay* says how close a parent class is to a child: at 0.8 a
  `CreationOfArtwork` counts nearly as a `CreationOfPainting`. The demo would start at decay 0.5, weight 0.1, chosen on
  its data.
- **Without the hierarchy (decay 0) it is only a soft filter by class**, which an index per class does exactly.
- **People are not changed by it.** Every `Person` has the same class part, which therefore adds nothing to how people
  rank against each other. Entity hierarchies (a `Painter` subclass of `Person`) would work the same way as documents'.
- **Carrying the class part through the graph is something else**: people become alike by the kinds of document they
  appear in (craft 34% to 42% in this test: painters near painters), a likeness of role. It may be worth a later view
  of its own; it is not this feature.
- **The dimensions must be exact.** A first try gave each class a random 32-dimension vector instead. Unrelated classes
  then overlapped by chance (cosine about ±0.18) as much as parent and child did by design, and the results were noise.
  With tens of classes, one dimension each costs little. With hundreds, a random projection would need at least 256
  dimensions.

**Which classes count: taken from the models, not filtered from the labels.** A node's labels mix several things:

- its class and its parents (the hierarchy wanted);
- heritable traits (`Dateable`, `Agent`);
- ontology mixins (`E5_Event`, from `pangloss-rdf`);
- classes it `Fulfils` by what it holds;
- typologies' unmanaged labels;
- its kind.

So `pangloss-similar` builds the class part at `initialise()` from the model registry, where these can be told apart
(`labels_for_model`, `model_is_trait`, `__labels_unmanaged__`). It makes one map from each concrete `type` to its
class vector:

- **Parents** that are declared Document or Entity classes: the hierarchy, at `decay^depth`.
- **Traits: only those that mean something.** Traits do two jobs today. `Dateable` and `Marked` are mixins: they add
  fields, and having one says nothing about what a thing is. `Agent` is a meaning: "a person or a group", a class that
  relations point at. Only the second kind should count. Proposed (user, 2026-11-11): **`SemanticTrait`**, a subclass
  of `Trait`, for traits that say what their classes are. A semantic trait has a dimension of its own in the class
  part, as if it were a parent of the class that has it (`decay^depth` of that class), and its own parent traits go
  further up. A plain `Trait` is a mixin and is never in the class part. `NonHeritableTrait` follows the label's rule:
  only the class that names it, not its subclasses. In the demo, `Agent` would become a `SemanticTrait` and `Dateable`
  stay a `Trait`. **Decided (2026-11-11): classes, not a `Meta` flag**: `SemanticTrait` (a subclass of `Trait`) and
  `SemanticNonHeritableTrait` (of `NonHeritableTrait`). A class shows on the declaration line, is seen by type
  checkers and the stubs, and a trait that extends a semantic trait is semantic as a subclass, with no rule about
  inheriting a `Meta` option. It is a change to `pangloss-models` (two new bases, exported, in the stubs and the
  export), and general: "this trait is a kind of thing" may be wanted elsewhere too (the RDF export, the interface's
  type grid, search across a trait).
- **Ontology mixins** (`E5_Event`, `E39_Actor`): not in the class part. The CIDOC-CRM classes are themselves a
  hierarchy, so they could be a group of their own later, with its own weight.
- **Kinds, `PGIndexableNode`, `HeadNode`, and generic bases**: never.
- **`Fulfils`: what is actually fulfilled counts** (user, 2026-11-11). A node has a fulfilled class's labels only while
  it fulfils it, because they are put on and taken off by what it holds (`get_labels_for_db_classes`,
  `fulfillable_labels`). So the module reads them from the node's labels, through a second map built at
  `initialise()`: for each class that can be fulfilled, its label and its own class part (itself, its parents, its
  semantic traits), added at `decay`, as a parent would be. Any label not in the map is ignored, so nothing in the
  database interprets labels beyond a lookup. A save that changes what a document fulfils changes its labels, and so
  is a change `refresh` already sees.

**Cost and upkeep.**
- The class part is computed from `type` alone, with no graph. Changing the hierarchy, a decay or a group weight only
  rewrites the class parts, with no FastRP rebuild.
- A new class adds a dimension, so the index is rebuilt. That is a migration of the package, made when the models
  change, as other indexes are.
- `refresh` is unaffected: a save does not change an item's class, except an implied-type narrowing or a class changed
  in place, which is then one more node to rewrite.

## Use cases: reconciliation and comparing statements (ideas) ⏳

The user's, 2026-11-11, for a factoid prosopography. They want a general "graph and semantic similarity" feature in
a package of its own, used here for two things. These are ideas, none tried yet except where said.

### One idea under both: a vector in parts, and two stages

Both uses need more than the graph, so the package's vector would be made of **parts**, each computed apart and each
weighted in the query (as the class part is):

| Part | What it says | How | Status |
|---|---|---|---|
| Graph | Who and what it is connected to | FastRP over documents and entities (above) | Measured |
| Class | What kind of thing it is | The hierarchy, semantic traits, what it fulfils (above) | Measured on planted data |
| Label | What it is called | Character trigrams of the folded label (`label_key`, as review folds it), hashed into a few hundred dimensions and weighted by rarity. Their cosine is close to trigram similarity. That handles spelling variants (Johann, Johannes; Wien, Vienna less so), deterministically, with no model. A multilingual name model could be another kind later | Idea |
| Time | When | A date's day numbers (`pangloss-dates`' bounds) encoded as soft bumps along the time axis, averaged over the date's fuzzy bounds, so that the cosine of two dates falls off with the gap between them and overlapping uncertain dates come out alike. Needed because dates are embedded nodes the walk passes through: the graph part never sees time | Idea |

A **profile** is a set of weights for the parts, chosen per task: "reconcile a person" weights label and graph;
"statements like this one" weights class, graph and time.

**Two stages**:
1. **Find candidates** by one vector search with the profile's weights: fast, approximate, and recall matters more
   than order.
2. **Decide among them** in Python on exact features: label likeness, the shared neighbours by name, date overlap from
   the real bounds, field-by-field comparison. These give a score that can be explained.

Vectors are for finding; the decision is made on what a reviewer can read. Each use below is that pattern.

### 1. Reconciling entities

The setting is already built (`pangloss-review`, `implementation_docs/review.md`). A factoid comes in, often from a
toolchain, naming people it cannot identify. Each becomes an `Unreconciled` (a document in the entity's place), or a
toolchain proposes an `IdentificationByToolchain`. Review finds *mentions* like one another (folded labels, URIs in
common) and lets a person choose the entity. What is missing is **ranking existing entities as candidates**, by name
*and* by the company the mention keeps.

- **(a) Label**: the label part finds people of a like name among all entities, which `difflib` over every label
  could not do at scale. Review's `likeness` stays as the exact re-ranking.
- **(b) Context**: a mention's company is the factoid it is in: the other people, the place, the source (a Zotero
  `Book` is an entity, so the source is in the graph). A person whose own factoids have that company (the same spouse,
  the same town, the same source) is a strong candidate. The graph part measures exactly that.
- **The vector of something not yet written.** FastRP is local, so the vector a mention *would* have can be computed
  without writing it. Give the module the new factoid's tree as virtual nodes and edges to existing ids; it computes
  the neighbourhood (`k` joins out, smaller than `refresh` needs for one node), and returns the virtual nodes' vectors.
  Nothing is written. This is `refresh` with an overlay, and exact: the vector it would have once saved. It serves
  the form while the factoid is being made, and a toolchain before it uploads. A mention already saved as
  `Unreconciled` is a document of the graph, with a vector of its own, and needs no overlay.
- **The overlay also answers the question about unpublished documents.** They can be left out of the graph, so they
  do not shape what readers see, and still get vectors by overlay when someone needs them.
- **Deciding.** Each candidate is scored on:
  - label likeness;
  - context similarity, plus the shared neighbours by name ("also in a factoid with Y; also in source S");
  - whether its class can be the one the relation takes;
  - whether its dates fit (no factoids long after the person's death);
  - a URI in common, which decides at once, as now.

  Start with set weights. Every reconciliation a person makes, and every toolchain suggestion they confirm or
  reject, is a labelled pair (review records them), so the weights can later be learnt from the project's own
  decisions (a logistic regression over the features).
- **Where it shows.** Candidates as `ReferenceChip`s in the reconcile dialog, with score and reasons. An automatic run
  writes `IdentificationByToolchain` (with `WeightedAlternative`s, its likelihoods) for a person to confirm, which is
  already built. Never a silent merge.

### 2. Comparing statements: one event, two events, or sources that disagree

In the factoid model a factoid records what a source says, and two factoids are never merged. The question is about
pairs:
- source A: X married Y on 1 January 1492 in Vienna;
- source B: X married Z on that day in Vienna.

The two either describe one event and disagree about the spouse, or describe two events. Ten years apart, they are
two marriages. The aim is to find such pairs, set them side by side, and say how likely each reading is.

- **Finding pairs.** Statements of the same or related classes (the class part), with people in common (the graph
  part), at nearby times (the time part). Where the people are already reconciled, `pangloss-derived` can also find
  them exactly ("two `Marriage` statements naming one person"). The vectors add what a rule cannot: related classes,
  and people not yet reconciled (X in source A and X′ in source B may still be two entities).
- **Setting them side by side.** Compare the two field by field, on the fields of their nearest common class (a
  `CreationOfArtwork` and a `CreationOfPainting` compare as `CreationOfArtwork`). For each field: same, different, one
  silent, or (for dates and places) overlapping, disjoint or nested. The history compare page (`pangloss-history`)
  already sets two versions side by side; this is the same view between two documents.
- **What the class says about itself.** Whether a difference is a contradiction depends on the kind of event, which
  only the model knows. A `CompareMeta` per class:
  - **Which fields identify the event**: for a `Marriage`, its participants as a set.
  - **Whether it can happen more than once**: a `Birth` and a `Death` happen once per person, so two `Birth`s of X
    are one event, and any difference contradicts. A `Marriage` can recur, but not twice on one day.
  - **How close in time** two reports of one event usually are.
- **How likely each reading is.** Three outcomes:
  - **One event, sources agree** (corroboration);
  - **One event, sources disagree**, with the fields they disagree on (contradiction);
  - **Two events.**

  The probability of "one event" comes from:
  - the date gap measured against both dates' uncertainty;
  - place (same, nested, different);
  - participants in common and different;
  - whether the class recurs;
  - whether the sources differ (one source naming the same event twice is unusual).

  Given one event, the field comparison says agree or disagree. Start with priors set per class; learn from
  judgements once there are some.
- **A judgement is worked out when someone looks; only a person's is written** (tried: below). The machine's verdict
  is a function of the two statements and the class's `CompareMeta`. It is cheap, the same every time, and should
  change when the data does. Writing it would make a copy that goes stale. What cannot be worked out again is a
  person's decision ("these are two events, whatever the dates suggest"), and that is research data: a document
  (`EventJudgement` or the like, naming the statements, the verdict and the fields, with `meta.created_by`). A lookup
  reads those first, and they override the computed verdict. They are also the training data. Only a *list* across the
  database ("every disagreement in source S") wants the verdicts kept, and then as a rebuildable cache, not as data.
- **The two uses feed each other.** "X married Y" against "X married Z" on the same day in Vienna is a contradiction,
  unless Y and Z are one person under two names. That is a reconciliation candidate, with the context that suggests
  it. The comparison view should offer it.

### Where it would live

- **`pangloss-similar`**: the general feature. It holds:
  - the parts, the profiles and the module;
  - `refresh` with overlays;
  - the vector index, a "similar" API, and `candidates(item or overlay, type, profile)`.

  It knows nothing of review or factoids.
- **Reconciliation candidates**: review's dialog asks for candidates through a hook of its own, which
  `pangloss-similar` fills when both are installed. Either review defines `candidate_providers`, or a small glue app
  does it; the core and `pangloss-similar` name neither. Which, is for the user.
- **Comparing statements**: a package of its own (`pangloss-compare`, say). It holds `CompareMeta`, the field
  comparison, the likelihoods, the people's judgement documents (or those go to `pangloss-library`, beside
  `Identification`), and the side-by-side page. It uses `pangloss-similar` and `pangloss-dates`.

### Tried: reconciliation as a service, and judgements at lookup (2026-11-11)

Both on one planted prosopography (`/tmp/embed-trial/proso.py`; numpy only, the module's maths, no database):

- **People**: 3,000, in families sharing a surname, with given names drawn by frequency. Some common surnames are
  shared by unrelated families, so names collide often, as they do in the sources.
- **Places and sources**: 80 towns, 40 offices, 60 sources (each covering a few towns and a period).
- **Factoids**: about 17,000.
  - Births: once each, reported by 1-2 sources.
  - Marriages: reported by 1-3 sources; 20% of the married marry again 3-15 years later.
  - Offices.
  - Witnesses: a person with two others of the same town and time.
- **Planted errors**: a second report of a birth may give another year. 12% of later marriage reports name another
  spouse, and 10% shift the date by a year or two.
- **Date precision**: each report gives the event's one true day as that day, its year or its decade.
- **Spelling in the sources**: Johannes, Hans, Iohannes for Johann; ü/ue, ck/k, tz/z; a Latin *-ius*.

**Reconciliation as a service.** A factoid comes in, a `Create` payload like any other, and one person in it is only a
label from the source. The answer is a ranked list of candidates; nothing is written. Built:
- the label part (trigrams of the folded label, hashed into 512 dimensions, weighted by rarity);
- the context: the vector the unknown mention would have, by overlay;
- the time fit: the factoid's date against the dates the database has for each candidate.

Stage 1 is the top 50 by label together with the top 50 by context. Stage 2 is a weighted sum, its weights chosen on
450 queries and measured on another 450. A fifth of the queries (200) were about people the database does not have.

| Ranked by | Right first | In the top 5 | Right first, name shared by several people (253 of 450) | Right first, name unique |
|---|---|---|---|---|
| Label only | 54.1% | 87.4% | 29.9% | 85.3% |
| Context only | 2.4% | 30.7% | 3.2% | 1.5% |
| Label + time | 62.3% | 92.7% | 43.6% | 86.3% |
| **Label + context** | **78.4%** | **99.6%** | **70.4%** | 88.8% |
| Label + context + time | 78.4% | 99.8% | 70.4% | 88.8% |

By kind of factoid, right first with label + context: marriages 82% (label alone 52%), offices 85% (53%), witnesses
76% (55%).

- **Context is what tells namesakes apart.** Alone it is useless: it finds the right town and family, not the person.
  With the label it lifts shared names from 30% to 70%, and puts the right person in the top five 99.6% of the time.
  That is a list a person can confirm from. A worked case: "Niklas Eckgrurich" ranked Nikolaus Eckgrurich of the same
  town first (context 0.56), above namesakes in another town (0.14, 0.09).
- **Time adds little once context is there** here, because every candidate's dates in this data roughly fit. It
  helped when label was all there was (54% to 62%). On real data with long spans it may matter more.
- **A weighted sum beat "label, then context only to break ties"** (78.4% against 75-78%).
- **Someone new**: the best score is lower when the person is not in the database (median 0.94 against 1.18; AUC
  0.83). That is enough to say "perhaps someone new", not to decide it. "A new person" should always be one of the
  answers.
- **The overlay is exact and cheap**: within 6 × 10⁻⁸ of a full rebuild with the factoid saved (15 cases), 0.5 ms in
  numpy per query. On the server it would be the module, plus two vector searches (label and context) of about a
  millisecond each, plus stage 2 in Python.

**How the service would look** (the workflow is for later):
- `POST /api/similar/candidates` with a `Create` payload in which the unknown is given as an `Unreconciled` (review's
  stand-in, which already validates as a label and a class).
- It answers, for each `Unreconciled`, the ranked candidates as `ReferenceView`s, each with its label, context and time
  scores, the shared neighbours by name (the reasons), and how likely "someone new" is.
- The overlay comes from `pangloss_cypher.write_plan.plan_create`, which turns a `Create` into nodes, relations and
  references without writing.
- Two unknowns in one factoid are two virtual nodes in one overlay.
- An external toolchain needs nothing but the payload it would upload anyway.

**Judgements at lookup.** For every birth and marriage report, every other report of its class about one of its
people (4,656 pairs) was classified as *agree*, *disagree* (with the fields) or *two events*. The class's
`CompareMeta` said a `Birth` happens once per person and a `Marriage` can recur. For marriages, "one event" was a
logistic of the date gap beyond both dates' uncertainty, the place, whether the participants are the same, and
whether the sources differ. The weights were set by hand, not learnt.

| Truly ↓ / said → | agree | disagree | two events |
|---|---|---|---|
| agree (2,405) | 2,405 | 0 | 0 |
| disagree (708) | 59 | 612 | 37 |
| two events (1,543) | 0 | 8 | 1,535 |

**97.8% right.** The mistakes are the cases the sources cannot settle:
- **59 births a source dated wrongly** but only to the decade, which still overlaps the true date.
- **37 marriages dated a year or two off.** The same couple, but read as two events. A `CompareMeta` rule that a couple
  does not marry twice would take most of these.
- **8 two-event pairs judged as disagreements.**

One planted bug cost time first: each report had drawn its own random day, which made correct reports of one event
"disagree". With one true day per event given at each report's precision, that went.

**Cost.** The comparison itself took 1 µs a statement in Python (all 6,923 reports in 0.01 s). A reader sees a median
of 1 other report and at most 11. On the server the cost is the query that finds the other reports (statements of the
class naming one of these people: index lookups, a few milliseconds, not measured). So the verdict for the statement
on the screen is computed when it is shown, and **nothing is written**. A list across the whole database is one query
over every report and seconds of Python; if pages need it often, it can be a cache the worker keeps, rebuildable like
derived facts.

### Tried on a model of the user's size, in Pangloss itself (2026-11-11)

The experiments above ran on plain numpy graphs. This one used real Pangloss: a generated model, data written by
`pangloss memgraph bulk-load`, the module in Memgraph reading what Pangloss stores, and incoming factoids validated
and planned by the models. Everything is in `/tmp/embed-proj/`, a scratch project with its own Memgraph on port 7704
(container `pangloss-embed-proj`):
- `gen_models.py`, `gen_data.py`, `make_overlays.py`;
- `pg_similar.py`, the module;
- `build.py`, `exp_reconcile.py`, `exp_compare.py`.

**The model** (`simapp/models.py`, generated; `pangloss check`: "The models are sound"):
- **162 statement classes** (143 concrete) in 19 branches:
  - life events, kinship, parentage, membership, office;
  - transactions (sales, loans, payments, donations, bequests, leases), objects changing hands;
  - creation (`CreationOfArtwork` → `CreationOfPainting` → `CreationOfAltarpiece`, …), commissions, possession;
  - legal, witnessing, movement, residence, religious, education, correspondence, military, employment.
- **52 entity classes**:
  - people; groups (families, guilds, monasteries, councils);
  - places (settlements, buildings, regions);
  - **32 kinds of object** (`PhysicalObject` → `Artwork` → `Painting` → `Altarpiece`, …), offices, sources.
- **Factoids** of statements, some in `Negative` or `Hypothetical`. Several roles are `list[InRole[Person]]`
  (reified relations). Dates are `pangloss-dates` dates (embedded nodes). People and objects allow `Unreconciled`.

**The data** (`gen_data.py`):
- **The world**: 60 towns with buildings, guilds, councils and monasteries; 5,000 people in families, each with a
  craft; 3,661 objects, each made by a person of the matching craft, and commissioned, owned and passed on.
- **Events**: 49,960 of them, in 111 of the classes.
- **Reports**: each event in 1-3 sources. 10% of later reports name someone else, and 8% give another year. A fifth of
  creation reports give the general class (`CreationOfArtwork` for a painting). Some events genuinely recur with the
  same people (yearly rent, repeated elections). 5% of reports are wrapped in `Negative` or `Hypothetical`.
- **The load**: 11,006 entities and 52,716 factoids holding 78,884 statements, **330,092 nodes and 1,088,562 edges**,
  in 159 s (401 records a second, 8 writers). A driver traceback (`'NoneType' object has no attribute 'complete'`,
  on a rollback) was printed during the load, but every record was there afterwards, the lock was gone and the 14
  constraints were back. Not looked into.

**Building and keeping the vectors** (the module, second version):
- **Installed over Bolt** with `mg.create_module_file` in 1.7 s.
- **`rebuild`** is a write procedure that writes the `PGEmbedding` nodes itself. That avoids the fault of more than
  100,000 records. It labels each by its item's group (`PGEPerson`, `PGEPhysicalObject`, `PGEStatement`, …) so that
  each group can have an index.
  - It took **12.5 s** for 142,606 documents and entities (703,562 joins) on the 330,092 nodes.
  - The indexes took 10.5 s (all 141,134 vectors), 5.4 s (statements), 0.3 s (people), 0.2 s (objects).
- **`overlay`** gives the exact vectors of a write plan that has not been written.
  - **Exactness**, three checks: with nothing laid over, it matches `rebuild` to **3 × 10⁻⁷**. For three factoids
    written for real (then deleted), it gave **exactly** the vectors computed from the written nodes. It looks at
    5-7 nodes' joins per query.
  - **The input:** the held-out factoids, as `Factoid.Create` payloads with `Unreconciled` in place of the unknown,
    were validated and planned (`plan_create`) in **0.3 ms** each.

**Reconciliation as a service** (1,250 held-out reports: 648 about people, 452 about objects, 150 about people the
database does not have; weights chosen on half, measured on the other half):

| Ranked by | People: right first | Top 5 | Name shared (170 of 326): right first | Objects: right first | Top 5 |
|---|---|---|---|---|---|
| Label only | 54.9% | 85.0% | 24.7% | 32.8% | 64.8% |
| Context only | 2.8% | 18.7% | 2.9% | 78.4% | 98.2% |
| Label + time | 64.9% | 91.9% | 42.2% | 66.6% | 99.2% |
| Label + context | 82.2% | 97.2% | 74.1% | 96.9% | 100% |
| **Label + context + time** | **86.2%** | **98.2%** | **81.2%** | **99.6%** | **100%** |

- **Speed**: **37 ms** median per query (p95 50 ms), Bolt round trip and module included.
- **People** behave as in the numpy trial, and better: time now helps (82% to 86%), because lives are spread over
  150 years.
- **Objects are the reverse of people.** Their labels collide constantly ("Altarpiece of St Mary", "Ring made by …"),
  so label alone is right a third of the time. But an object appears with its maker and its patron, so context alone
  is right 78% of the time, and the two together **99.6%**.
- **Someone new**: AUC 0.74. As before, a hint, not a decision.
- **Where it fails**:
  - **A report with almost no context.** A baptism names only the child and the church; "Anne Hofkurz" ranked a
    Margarethe Hofkurz first.
  - **Given-name equivalents** (Anne/Anna, Hans/Johann) that groups of letters cannot know. A table of variants of
    given names, or a name model, belongs in the label part.

**Comparing statements at lookup** (every pair of statements of related classes, the same class or one an ancestor of
the other, naming the same person or object):

- **What each class must say** (a `CompareMeta`, here written by branch in `exp_compare.py`):
  - which fields identify the event (the member of a membership, the subject of a life event, the object of a
    creation);
  - whether it happens once per that (a birth; the making of an object);
  - whether it recurs with the same people (rent, elections).
- **Without the identifying fields** (every field counted): 442,413 pairs and 13,459 wrong judgements. Two *different*
  members of one guild were read as one membership that disagreed about the member.
- **With them**: **186,861 pairs, 8,746 wrong (95.3% right)**:

| Truly ↓ / said → | agree | disagree | two events |
|---|---|---|---|
| agree (26,647) | 26,647 | 0 | 0 |
| disagree (6,446) | 670 | 4,852 | 924 |
| two events (153,768) | 2,188 | 4,964 | 146,616 |

- **A general and a specific class** (`CreationOfArtwork` against `CreationOfPainting` of one object): 579 of 589
  judged right.
- **Not one event**: a birth and a death of one person are never one event, whatever "once per person" says. The
  first version made that mistake: life events 17% right, 97% after.
- **What is left is mostly undecidable from the sources**:
  - two payments or sales between the same people in the same year or decade, where the dates are years or decades;
  - repeated elections two years apart, dated by decade;
  - a report that names the wrong person, which then collides with that person's own birth or death.

  These want per-class base rates (how often a merchant sells in a year), learnt from people's judgements.
- **Cost**: the verdicts take 9 µs a statement. The query a lookup needs (the other statements naming the same people
  or objects, with their dates) took **0.9 ms** median, p95 1.7 ms. A reader sees a median of 3 others, at most 42. So
  nothing needs to be written: this confirms the earlier finding on stored data.

**Finding the other reports of an event by vector** (for people not yet reconciled, where no rule can find them):
- **Graph part only**: 89.8% of an event's other reports are among its 10 nearest statements (88.2% through the
  vector index, which is approximate).
- **With the class part** (decay 0.5, weight 0.5): **95.4%**.

The class part earns its place here as well.

### Further tests on the same project (2026-11-11)

All on the scratch project above (`/tmp/embed-proj/`: `recon_lib.py`, `exp_variants.py`, `gen_two.py`, `exp_two.py`,
`exp_time.py`, `exp_learn.py`, `similar_py.py`, `check_py_path.py`, `exp_neo4j.py`).

**1. Given-name variants in the label part.** Before the trigrams, each given name is replaced by its standard form
from a table (Hans, Iohannes and Jan → Johann; Anne → Anna), as a project would keep it (a list, or a typology).

| | People: right first | Name shared: right first | Objects | Someone new (AUC) |
|---|---|---|---|---|
| Without | 86.2% | 81.2% | 99.6% | 0.74 |
| **With the table** | **93.9%** | **88.2%** | 100% | **0.86** |

The largest single gain of these tests. A name table belongs in the label part; whether a model of names would add
more is still untried.

**2. Per-class weights on this model.** Three settings, each rebuilt (about 41 s, the four indexes included) and
measured, with the name table:
- *Routine classes quieted* (`MemberOf`, `LivesIn`, `CitizenOf`, `PaymentOfRent` 0.3; elections, offices and
  witnessing 0.5): people 92.3%.
- *Kinship raised* (marriage, betrothal, parentage 2; apprenticeship 1.5): 93.3%.
- *Both*: 92.3%.
- Against **93.9% with no weights.**

They did not help. Records that look routine (who belonged to which guild, who lived where) are part of what places
a person, and quieting them took information away. The gain measured earlier came from a class that was pure noise.
So: **per-class weights are for real noise, found by measuring on the project's data, not something to set
beforehand.** The decision stands (weights are the control), but the default is 1 everywhere.

**3. f16 vectors.** The statements' index (78,884 vectors) as f32 and as f16, against exact cosine (300 queries):
recall@10 99.6% both. Queries took 0.7 ms and 1.6 ms. The memory of all four indexes went from 251 MiB to 232 MiB:
f16 halves the vectors (about 40 MB to 20 MB here), but the index's own structure is most of the memory. **Not worth
it at this size**; f32 stays the default.

**4. Two unknowns in one factoid.** 600 existing reports naming two people (382 transactions, 112 marriages and
betrothals, 80 apprenticeships and studies, letters, parentage, military service), reported again by another source
with both people given only as variant labels. Validated and planned as before; one overlay gives both unknowns'
vectors (each is the other's virtual neighbour). Measured on 300, the pair's weights chosen on the other 300:

- **Each ranked alone**: right first 89.0%, but **both right only 79.3%**.
- **The two ranked together**: the top 10 of each, a pair scored as the sum of its two scores, plus 0.25 if the two
  candidates are already named together in some statement, plus 0.25 × the cosine of their vectors. **Both right
  94.3%.** By the cosine alone (no lookup of statements), 90.7%.
- **The reasons a reviewer would see**, for the top candidate of each unknown:

  | What the candidate shares with the factoid | Right candidates (534) | Wrong candidates (66) |
  |---|---|---|
  | The same place | 100% | 62% |
  | The same source | 7% | 2% |
  | **Already named with the other unknown's candidate** | **94%** | **26%** |

  "Same place" is true of nearly everyone in a town, so it explains little. "Already named together" is the reason
  worth showing. In the example, a `BequestOfLand` naming "Elisabeth Ergrurich" and "Jörg Burgstein": Elisabeth
  Ergrurich and Georg Burgstein, already named together in 2 statements.

**5. The time part as a vector**, for finding the other reports of an event among all 78,884 statements. Dates as
soft bumps along the time axis, each averaged over its bounds (a day, a year, a decade): 139 dimensions for bumps of 2
years over 265 years. Share of an event's other reports among a statement's 10 nearest (2,568 statements, 414 of them
of a recurring event):

| Parts (weights) | All | Recurring |
|---|---|---|
| Graph | 89.2% | 88.8% |
| Graph + class (0.5) | 95.0% | 95.7% |
| **Graph + class (0.5) + time, bumps of 2 years (0.5)** | **99.5%** | **100%** |
| … time, 2 years (1.0) | 99.1% | 98.9% |
| … time, 1 year (1.0) | 95.6% | 95.5% |
| … time, 5 years (1.0) | 99.7% | 99.8% |

- With time, nearly every other report of an event is found.
- Recurring events no longer crowd each other out: this year's rent and last year's are told apart.
- **The bumps must be as wide as the dates are vague.** One year was too narrow for dates known to the decade.

**6. Learning the comparison from people's judgements.** A logistic regression for "one event" over 50 features: the
identifying fields, the date gap and how vague the dates are, place, source, class relation, "once per", recurring,
other fields differing, negation, and a base rate and a time rate for each branch. Trained on N pairs drawn at random
(as if a person had judged them), measured on all the others:

| Trained on | Right | Wrong, at the scale of all 186,861 pairs |
|---|---|---|
| Hand-set weights (above) | 95.3% | 8,746 |
| 50 judged pairs | 88.3% | 21,910 |
| 200 | 94.7% | 9,851 |
| **1,000** | **96.8%** | **6,045** |
| 5,000 | 96.9% | 5,857 |

- **A few hundred judgements equal the hand-set rules, and a thousand beat them by a third.**
- **It levels off there**: what is left is what the sources cannot settle.
- **The declarations remain:** the identifying fields, "once per" and "recurs" are among the features learnt from.
  Learning sets the weights; the model says what to weigh.

**7. Neo4j, by the Python path** (`similar_py.py`, `check_py_path.py`, `exp_neo4j.py`).
- **Exactness**: the Python path reads the nodes and the forward edges by Cypher that both databases run, joins
  through the modelling kinds, and runs FastRP outside the database. Run against Memgraph's data, it gave **exactly**
  the module's vectors (difference 0.0, all 141,134). Memgraph took 4.2 s to read 266,356 nodes and 7.9 s to read
  480,559 forward edges, then 1.1 s to join and 1.8 s for FastRP.
- **The load**: the same file into Neo4j 2026.10.1 by `pangloss neo4j bulk-load` (ordinary transactions, 8 writers):
  63,722 records in 234 s (273 a second, against Memgraph's 401 in analytical mode), with no errors: 330,090 nodes
  and 1,088,562 edges.
- **The batch on Neo4j**: about **33 s** in all.
  - Read the nodes in 4.3 s and the edges in 8.6 s; join 1.0 s; FastRP 1.7 s.
  - Write 141,134 vectors in batches of 10,000: 14.2 s.
  - Three vector indexes (people, objects, statements) online: 3.3 s.
  - A search for 10 (the `SEARCH` clause): 2.0 ms median.
- **The overlay on Neo4j**, as it would be done there: the neighbourhood of the entities a factoid names, read by
  Cypher a ring of raw edges at a time (two rings: an entity, its roles, their statements), then the maths in Python.
  - **Exact**: difference 0.0 against the graph held in memory (100 factoids).
  - **But 267 ms** median (2 queries), against 37 ms in Memgraph's module: a town or a source a factoid names brings
    thousands of rows over Bolt.
  - Lighter on Neo4j would be to read only the joined neighbours' ids with an aggregation in Cypher, or to keep each
    node's degree with its vector.
- **Reconciliation on Neo4j's vectors**, with the name table: people right first **94.8%**, objects **99.1%**
  (Memgraph: 93.9%, 100%). The vectors are not the same as Memgraph's, because the documents were given new ids in
  the second load and the seeds come from the ids. They are as good.

So **both backends work**, with one algorithm. Memgraph is quicker for the on-save update and the overlay, because the
module reads the graph in place; Neo4j needs nothing installed.

### What to try next

1. On the demo's data: reconciliation against its real `Unreconciled` mentions and the choices made for them, and
   comparisons of its real statements.
2. The label part on real names (Latin and vernacular forms, abbreviations), and whether a name model adds to the
   table of given-name variants.
3. Choosing which judgements to ask for (the pairs the model is least sure of) rather than at random: fewer than 1,000
   may then be enough.
4. `CompareMeta` as a declaration on the models (identifying fields, once per, recurs), checked at `initialise()`.

## What the databases offer

Checked against the docs and, where marked ✔, against the images this repository runs (`memgraph/memgraph-mage:3.14.0`,
`neo4j:2026.10.1`).

| | Memgraph 3.14 (community) | Neo4j 2026.10 (Community) |
|---|---|---|
| Vector index | ✔ `CREATE VECTOR INDEX n ON :Label(prop) WITH CONFIG {dimension, capacity, metric}`; `:A\|B(prop)` multi-label ✔ | ✔ `CREATE VECTOR INDEX … FOR (n:L) ON n.p OPTIONS {indexConfig: {…}}`; multi-label and filter properties (`WITH [n.kind]`) since 2026.01 |
| Search | ✔ `CALL vector_search.search(index, k, vector) YIELD node, similarity` | ✔ `SEARCH x IN (VECTOR INDEX i FOR v LIMIT k) SCORE AS s` (`db.index.vector.queryNodes` still works, deprecated) |
| Filtering in the search | None: only by which index | `SEARCH … WHERE` on the filter properties |
| Where the vector lives | In the index only (USearch); persisted in snapshots and WAL | A `LIST<FLOAT>` property (the native `VECTOR` type is Enterprise only) |
| Custom code in the database | ✔ Python query modules (`mgp`), also C, C++, Rust. **Installed over Bolt** ✔: `mg.create_module_file(name, text)`, `mg.update_module_file`, `mg.get_module_file` (written to `/var/lib/memgraph/internal_modules/`) | Java plugins, put in the plugins directory |
| Python libraries in the image | ✔ Python 3.12, numpy 2.2.6, scipy 1.13.1, torch 2.9 (CPU), networkx, scikit-learn, sentence-transformers | — |
| node2vec | ✔ `node2vec.get_embeddings` / `set_embeddings` (C++), on a `project(path)` subgraph | GDS `gds.node2vec` |
| FastRP | Not in MAGE | GDS `gds.fastRP` ✔ |
| Online / incremental | `node2vec_online`: Enterprise only, ✔ absent without a licence; edge additions only | None |
| GDS | — | ✔ In the image (`NEO4J_PLUGINS='["graph-data-science"]'`, no download). Community: all algorithms, at most 4 cores, 3 models in the catalogue |
| Triggers | `BEFORE`/`AFTER COMMIT`, may `CALL` procedures | APOC triggers (not in the image) |

Things found while trying it that the docs do not say:

- **A Python procedure that returns more than about 100,000 records loses the last one** and gives another twice.
  100,000 came back whole; 131,072 and more (up to 520,002 tried) always lost exactly the last and duplicated one.
  This happens whether the result is collected in Cypher or streamed to the client. Seen first as a missing statement
  in a full rebuild. Workarounds: return in pages (a `limit`/`offset`, or `mgp.add_batch_read_proc`), or write inside
  the procedure. Worth reporting to Memgraph, with the trial's `many(n, dim)` procedure as the reproduction.
- **Keep plain values, not `Vertex` objects, across a whole-graph scan.** The first version of the module held 520,000
  vertices in a list. It also gave a wrong id, though that may have been the fault above. Keeping ids and looking
  vertices up again (`ctx.graph.get_vertex_by_id`) is the safe pattern.
- **`project()` takes paths**, not nodes and edges: `MATCH path = (a)-[e]->(b) … WITH project(path) AS g`. Nodes with
  no edge in the projection get no vector.
- **`knn.get` cannot read a property once a vector index holds it** ("must be a list of doubles").
- **A just-deleted `PGEmbedding` can still be returned by `vector_search.search`** until garbage collection, and the
  index's `size` is not reduced by deletes. Update vectors in place, and make the read tolerant.
- **Building a vector index is not cheap**: 14 s over 207k vectors of 64 dimensions, but 146 s over 520k of 128.
  Writing with the index live ran at about 2,400 vectors a second. Either way a full rebuild at this size spends 2-3
  minutes on the index.

## What was tried and measured

All on throwaway containers (`:7702`, `:7703`, removed afterwards). The demo's and the tests' databases were not
touched. Laptop, Docker Desktop, 8 cores for Memgraph, 4 for GDS (its Community limit).

**Two synthetic graphs.** Their structure is made up, so **they say something about speed and nothing about how good
the vectors are.**

- *Round 1*: 100k people, 20k places, 200k factoids each with a statement naming two people and a place. 520,000
  nodes, 1.6 million edges counting reverse ones, no modelling nodes.
- *Round 2*: the same entities. Each of 200k factoids has a nested statement, an `Identification` (reified relation) to
  one person, and a conjunction of a person and a place. 920,000 nodes, 2.4 million edges, of which 520,000 are
  documents and entities.

| What | Result |
|---|---|
| **Round 2, FastRP in a Memgraph Python module** | |
| Full rebuild: scan, join through modelling nodes, compute (128 dims, 3 steps) | **28-35 s** |
| … and write 520,000 vectors (no index yet) | **38 s** |
| Vector index over them afterwards | 146 s |
| On save: exact update after one new factoid (5 changed nodes) | **278 ms** median (460 ms the first time), 47 vectors, neighbourhood 4,240 |
| Exactness: those 47 against a full rebuild | largest difference **1.2 × 10⁻⁷** |
| Installing a module over Bolt, then calling it | ✔ at once, no restart |
| **Round 1, the alternatives** | |
| Memgraph `node2vec` (10 walks of 20, 64 dims) + writing 207k vectors | 204 s, +2 GB |
| GDS `node2vec`, same settings | 122 s (4 cores) |
| GDS `fastRP` on the same projection | 0.26 s compute + 1.1 s write |
| FastRP in Python *outside* the database, heads only (320k, 600k edges) | read 14.4 s, compute 0.21 s, write 88 s with the index live |
| Search, k = 20 | 0.6 ms median, 1.0 p95; recall@20 against brute force 1.0 |
| Search near a factoid, fetch 200, keep only people | found 2 of 20 wanted (filtering after the search does not work) |

The trial code is in `/tmp/embed-trial/`, with a scratch venv for numpy in `/tmp/embed-venv`. The query modules are
`modules/pg_fastrp.py` (`rebuild`, `refresh`, and the `many` reproduction) and `modules/pg_embed.py` (an earlier
average-of-neighbours fold-in, superseded). The scripts are `big2.py` and `inside.py` (round 2), and `big.py`,
`time_n2v.py`, `time_idx.py`, `neo.py`, `fastrp_out.py` (round 1). It is scratch: anything kept should be rewritten in
the package.

What the numbers mean:

- In the database, the Python scan of 920,000 nodes, not the arithmetic, is most of the 28 s. Written in C++ (MAGE's
  own modules are) it would be faster, but 30 s for a rebuild needs no optimising.
- Outside the database, moving data costs; inside, it is the index build. Either way a rebuild at this size is a few
  minutes, which suits an admin job.
- The on-save update is exact, and costs a few hundred milliseconds on this graph. It grows with the neighbourhood,
  which a hub makes large (see "On save").

## Which algorithm

| | FastRP | node2vec | node2vec_online | Text embeddings |
|---|---|---|---|---|
| What makes two items close | Shared neighbours, a few steps out | Walk co-occurrence (towards communities or roles by `p`, `q`) | Recently added edges | What their labels and text say |
| Cost (520k nodes) | Under a second of arithmetic | 2-3 min | — | Not measured; long on CPU |
| Deterministic | Yes, seeded by id | With a seed and one worker | No | Yes |
| Update after a save | Exact and local | Retrain | Added edges only | That item alone |
| Can be shaped to the model | Fully (the graph is Pangloss's) | Only by projection and edge weights | No | — |

**FastRP**, with each node's start vector seeded by a hash of its UUID. A vector then depends only on the graph,
not on load order or internal ids. That is what makes the on-save update exact, and makes the Memgraph module and the
Python path for Neo4j give the same vectors. node2vec can be a second `kind` later.

**Text embeddings** measure a different kind of similarity, of what is said, and suit documents with long text.
`kind` keeps room for them. Memgraph's image already has a working `embeddings` module (sentence-transformers).

## Where the computing is done

**On Memgraph: a Python query module, `pangloss_similar.module` (the trial's `pg_fastrp`)**, with:

- `rebuild(settings…, offset, limit)`: scans, joins, computes, and returns `(id, vector)` a page at a time (the
  100,000-record fault). Or it writes the `PGEmbedding` nodes itself as a `write_proc`; which of the two is faster is
  not measured.
- `refresh(nodes, settings…)`: the exact local update (below).

**Installing it.** `pangloss-similar` ships the module as a file of the package, and installs it over Bolt
(`mg.create_module_file`, or `mg.update_module_file` when `mg.get_module_file` differs) when the server starts and
when the package's migration runs. So a project needs no image or volume of its own, the module's version is always
the package's, and `run_tests.sh`, the demo and the smoke tests need nothing new. The module needs numpy and scipy,
which `memgraph-mage` has (Pangloss already requires the mage image for `text_search`). The install checks that they
import, and fails loudly if not.

**On Neo4j, and as the reference: the same maths in Python outside the database.** The maths (seeding, the joined
graph, FastRP, the local update) lives in one pure module that knows neither `mgp` nor a driver. The Memgraph module
calls it on what it reads from `ctx.graph`; the Neo4j path calls it on what one query returns. Two backends, one
algorithm, the same vectors. The conformance-style test of the package can then compare the two.

This departs from "add-ons run on any backend" only in where the code runs, not in what it does. The choice is made by
a capability (`in_database_embeddings`, true on Memgraph) and a `Dialect` method, not by naming a backend.

**Why not a trigger** (`CREATE TRIGGER … AFTER COMMIT EXECUTE CALL pangloss_similar.refresh(…)`): the update costs
hundreds of milliseconds, so not `BEFORE COMMIT` (a save is about 12 ms). An `AFTER COMMIT` trigger runs once per
commit with no retry, no batching, and no knowledge of what a save was. It sees nodes deleted and created, and an
update deletes and re-creates a document's whole tree. It would also fire for every write the worker itself makes, and
on bulk loads. The `pending_work` queue already gives retries, batching and claims. The worker calls the module.

## Does it read the whole database?

- **The batch, on Memgraph: no data leaves the server** except the vectors written back. The module reads the graph in
  place. It does look at every node once, so its cost is that of a scan: 28 s for 920,000 nodes.
- **The batch, outside the database (Neo4j): only the edge list**, ids and no properties: one row per forward edge
  between `PGIndexableNode`s, with the two ids, the two kinds and the field name. For round 1 that was 600,000 rows in
  14 s. Labels, text and dates are never read.
- **On save, on either: never.** Only the neighbourhood the save can affect is read, a few thousand nodes for a
  typical factoid.

## Where the vectors are kept

`(:PGEmbedding {of: <id of the document or entity>, kind, generation, vector, at})`, with an index on `of`, and **no
edge** to the item. The reasons, found in the code and the trial:

- **An update replaces a head's properties.** `build_replace_head_query` does `SET head = …` and keeps only
  `KEPT_PROPERTIES` (review's fields). Nested documents are deleted and written again. A vector stored on them would be
  wiped by every save.
- **Reads return every property of everything they touch.** `read_query.py` returns `properties(root)` and
  `properties(endNode(edge))` for every node of a document and every entity it refers to. A factoid naming five people
  would carry five 128-float lists to the API.
- **An edge to a model node is a write to that node.** The worker updating thousands of vectors would then conflict
  with users saving those documents: a serialisation error on Memgraph, a lock on Neo4j. Linking by `of` touches only
  embedding nodes.
- `mgp` cannot look a node up by property, so the module returns `(id, vector)` and Cypher writes
  (`MERGE (e:PGEmbedding {of: row.id}) SET e.vector = row.vector`), which uses the index on `of`.

**Nested documents keep their ids across an update** when the client sends them back (the update writes the tree again
with the same ids). Their vectors therefore carry over. A nested document removed by an update leaves a `PGEmbedding`
whose `of` no longer exists, which the worker deletes. The search ignores such leftovers anyway, because it joins on
`of` to a visible node.

**Indexes.** On Memgraph a search cannot be filtered, and filtering afterwards fails (2 of 20 found). So embedding nodes
also carry the class labels of their item (`PGEmbedding:Person`), and there is one index over all of them, plus one per
class asked to be searchable on its own (`:PGEmbedding&Person(vector)`; the `&` form is allowed for nodes, not tried).
On Neo4j one index with filter properties (`WITH [e.kind, e.item_type]`) does it.

**Generations.** A full rebuild writes a new `generation`, switches a pointer (`(:PGEmbeddingState {kind,
generation})`) and deletes the old. Searches read the current one, so there is never a half-built space. Memory for the
duration is doubled: about 270 MB of vectors at 520k × 128 × f32, plus the index's graph; `scalar_kind: 'f16'` halves
it.

## The batch: building every vector

An admin job, `similar rebuild [--kind fastrp]`, also a CLI command:

1. Make sure the module is installed and current.
2. Call `rebuild` page by page (or as a `write_proc`) and write a new generation with no index on it.
3. Create the new generation's index (2-3 minutes at 520k × 128), switch, drop the old generation and its index.
4. Record when and how many in `PGEmbeddingState`; clear the stale count.

On Neo4j step 2 is the Python path: read the edge list in pages, compute, write in batches of 10,000.

## On save: keeping vectors current

1. **`hooks.pending_work`**: a save, delete, undelete or publish of a document or entity that is embedded leaves a
   `(:PGPending {kind: "similar", head_id})` in the save's own transaction (`pangloss_cypher.pending`). This cost
   `pangloss-derived` 0.1-0.9 ms a save.
2. **A worker** (a `BackgroundTask` from `pangloss-similar`) claims pending items in batches, as
   `pangloss_derived.worker` does. For each batch it works out the **changed nodes**: the documents of the saved tree,
   plus every entity they refer to now *and* referred to before. The "before" comes from the `neighbours` list kept on
   each `PGEmbedding` (the ids it was joined to at its last computation), so an entity a save stopped referring to is
   updated too.
3. It calls **`refresh(changed nodes)`**. With `k` FastRP steps, the vectors a change can alter are those within
   `k − 1` joins of a changed node. Computing them exactly needs the graph `2k − 1` joins out, with each node's true
   number of neighbours. The module walks that far, computes on what it found, and returns only the vectors within
   `k − 1`. In the trial that was 47 vectors from 4,240 nodes, 278 ms, matching a full rebuild to 1.2 × 10⁻⁷.
4. It writes them in place (`SET e.vector = …`, which also avoids the deleted-node fault), with their new `neighbours`.

**Hubs.** The neighbourhood `2k − 1` joins out of a factoid that names a place cited by 10,000 documents takes in those
10,000 and everything they name: on real data, perhaps most of the database. So the module counts as it walks, and
past a cap (a setting, say 50,000 nodes) it stops. It then updates the saved documents themselves from their
neighbours' current vectors (an approximation) and adds to the stale count. A hub can also be made not to propagate:
excluded, or a lower weight. Fewer steps (`k = 2`) shrink the neighbourhood a great deal, at some cost to quality.

**Drift.** Only the capped updates are approximate. When the stale count passes a setting, or at a set hour, the
rebuild job runs.

**A new item with no neighbours yet** gets no vector until it is linked to something. Its first link is a change like
any other, so it is updated then: FastRP has no cold-start problem of its own.

## Who may see what

- **Deleted** documents and entities are not in the graph; their vectors are removed. Entities `marked_for_deletion`
  stay, since they are still referred to.
- **Search results** go through `fragments.visible(item)` and `not_deleted` after the vector search, which overfetches
  (k × 2, say) and cuts. The interface never sees an item it could not read.
- **Unpublished documents** (`pangloss-review`): if they are in the graph, they shape published items' vectors. A reader
  could learn that two people are close because of a factoid they cannot see. Little is revealed, but something is.
  Leaving them out until published is the cautious choice; publishing is then a change like any other. **A decision
  for the user.**
- **History**: vectors are derived and rebuildable, so `pangloss-history` does not record them, and no write event is
  raised for them.

## Declaring it in a project

A meta slot (`register_meta_slot("_similar_meta", SimilarMeta)`), inherited as meta slots are:

```python
from pangloss_similar import SimilarMeta

class Person(Entity):
    _similar_meta = SimilarMeta(searchable=True)               # its own index: "people like this"

class Negated(SemanticSpace[T]):
    _similar_meta = SimilarMeta(through=False)                 # the walk stops here

class Occupation(Entity):                                      # a typology
    _similar_meta = SimilarMeta(include=False)                 # no vector, not in the graph

class Birth(Document):
    _similar_meta = SimilarMeta(weights={"place": 2.0})        # a field counts more
```

The defaults (every document and entity in, the four modelling kinds passed through, weight 1) are settings, along
with `SIMILAR_DIMENSION`, `SIMILAR_STEPS` (FastRP's iteration weights), `SIMILAR_REFRESH_CAP`, `SIMILAR_REBUILD_AFTER`
and `SIMILAR_REBUILD_AT`. Changing the dimension or which classes are searchable is a migration of the package (indexes
made or dropped). Changing what is passed through, weights or exclusions means a rebuild, which `pangloss check` can
warn of. Weights are given in `SimilarMeta` rather than as an `Annotated` marker on the field, because a marker that is
neither pydantic's nor Pangloss's is refused.

## API, SDK and interface

- **`GET /api/{NAME}/{id}/similar?type=Person&limit=20`**: `[{item: ReferenceView, similarity}]`. It works for a nested
  document too, by its own id; the `ReferenceView` names its head, as a search result does. `type` picks the index.
  An item the reader cannot see is a 404; one not yet embedded gives an empty list with `"pending": true`.
- **`GET /api/similar/status`**: generation, when built, how many stale, whether a rebuild is running.
- **The SDK**: either an operation `Model.similar(id, …)` with its SDK side and a contract test, or only the route.
- **The interface**: an interface module with an `itemSections` entry, "Similar", on the item page and on a nested
  document's page. It shows **`ReferenceChip`s** with a similarity bar and a type filter (`MenuSelect`), fetched on its
  own as `IncomingRelations` is. Its strings are `t()` slots with translations, and it gets a row in `e2e/COVERAGE.md`.
  An admin `slots` entry shows the status and a Rebuild button. Later: "why are these close" (their shared neighbours,
  which the joined graph gives directly), and "similar to" as a search filter.

## Neo4j

- **Computing**: the Python path. It reads the edge list (one query, paged), uses the same pure maths, writes in batches,
  and on save reads the neighbourhood by a variable-length query and calls the same `refresh` maths. That is slower than
  in-database, and it has not been measured on Neo4j.
- **Storage and search**: Community's vector index on `PGEmbedding.vector` (a `LIST<FLOAT>`), with filter properties
  for the type. Two `Dialect` methods: `vector_index_ddl(…)` (`WITH CONFIG` against `OPTIONS {indexConfig}`, plus
  `db.awaitIndexes()` on Neo4j) and `vector_search(…)` (`CALL vector_search.search` against `SEARCH … IN (VECTOR
  INDEX …)`).
- **GDS is not needed.** It ships in the image, and `gds.fastRP` is very fast (0.26 s), but it walks stored
  projections (no passing through modelling nodes) and seeds by internal node ids. Its vectors would differ from
  Memgraph's and could not be updated by the same `refresh`.

## What would be built

| Where | What |
|---|---|
| `packages/pangloss-similar` (new) | The pure maths (seeding, the joined graph, FastRP, the local update), with no `mgp` and no driver; the Memgraph query module over it and its installer; the Python path for other backends; `SimilarMeta`; the rebuild job (`admin.py`) and command (`cli.py`); the worker; routes; migrations (index DDL through the dialect); translations; an interface module. `requires = {"cypher"}` |
| `pangloss-cypher` `Dialect` | `vector_index_ddl`, `vector_search`; Memgraph's and Neo4j's |
| `pangloss-core` `Capabilities` | `vector_index` (both true, the SDK false), `in_database_embeddings` (Memgraph true) |
| `pangloss_models` | `SemanticTrait` and `SemanticNonHeritableTrait`: traits that say what a thing is, as against mixins; exported, in the stubs and in `export_models()`. Otherwise nothing: `pending_work` is enough, and a node's kind and fulfilled classes are already labels |
| `pangloss-testing` | Tests of the package on both backends: rebuild, search, refresh equal to rebuild after a save, a removed reference updates the entity, delete, unpublished not visible, the module reinstalled when it changes |
| `pangloss-sdk` | The operation's HTTP side, if a model method is chosen |
| Deployment | numpy and scipy for the server only when the backend has no in-database module (Neo4j). Nothing for Memgraph |
| Docs | This page as the plan with "As built" sections; `status.md`; a guide page; the skill's package table |

Rough order: (1) the pure maths and the module, `similar rebuild` against a scratch copy of the demo, and an evaluation
(next sections) before anything else; (2) storage, indexes, the route; (3) the worker and `refresh`, with the hub cap;
(4) the interface section; (5) `SimilarMeta` controls; (6) the Python path, Neo4j, and the tests on both.

## Decisions for the user

1. **Nested documents' containment**: joined to the document they are in (as tried), or only through what they name.
2. **The default walk**: pass through all four modelling kinds (as tried), or only reified relations and conjunctions,
   leaving semantic spaces to be opted in, since a `Negated` space passed through says the opposite of what it means.
3. **Unpublished documents** in the graph or not (recommended: not, until published).
4. **Which classes get an index of their own** by default: none, entities only, or every class.
5. **Typology and other vocabulary entities**: in at weight 1, lower, or out by default.
6. **The hub cap** and what happens past it: approximate now and rebuild later (as proposed), or leave those vectors
   alone until the rebuild.
7. **A model method** (`Person.similar(id)`) with an SDK side, or only the route.
8. ~~Weighting by type~~: **decided 2026-11-11, per-class weights**, by the node's `type`. Views are possible later;
   type as a feature is not used
8a. **The class part** (similar by class hierarchy): its starting decay and weight. Decided: only semantic traits count,
   mixins never; fulfilled classes count from the node's labels; the bases are classes, `SemanticTrait` and
   `SemanticNonHeritableTrait`. Open: which demo traits become semantic (`Agent` yes, `Dateable` no)
9. **Text embeddings** as a second kind: now, later, or not.
10. **Report the 100,000-record fault to Memgraph?** It would mean sending them the reproduction; nothing of the
   project need be in it.

## What is not known yet

- **Whether the vectors are any good.** The synthetic graphs cannot say. The test is to hold back pairs that are known
  to belong together and see whether the vectors rank them high. Candidates for the pairs are identifications
  (`pangloss-review`, `pangloss-library`'s `Identification`), derived `SameGroup` facts, and members of one family.
  This is the first thing to do on real data, and it decides which of the walk's controls matter.
- The cost on **real data of about 640,000 nodes** with real hubs: the neighbourhood sizes `refresh` meets, and so
  the cap.
- `rebuild` as a `write_proc` against returning pages, and its memory at a million nodes.
- The Python path's speed on Neo4j.
- `scalar_kind: f16` recall, and the index build at f16.
- What the vector index costs the worker's small writes while users are saving.

## Sources

- Memgraph: [node2vec](https://memgraph.com/docs/advanced-algorithms/available-algorithms/node2vec),
  [node2vec_online](https://memgraph.com/docs/advanced-algorithms/available-algorithms/node2vec_online),
  [vector search](https://memgraph.com/docs/querying/vector-search),
  [custom query modules](https://memgraph.com/docs/custom-query-modules),
  [Python API](https://memgraph.com/docs/custom-query-modules/python/python-api),
  [managing query modules](https://memgraph.com/docs/custom-query-modules/manage-query-modules),
  [triggers](https://memgraph.com/docs/fundamentals/triggers),
  [knn](https://memgraph.com/docs/advanced-algorithms/available-algorithms/knn).
- Neo4j: [vector indexes (Cypher 25)](https://www.neo4j.com/docs/cypher-manual/25/indexes/semantic-indexes/vector-indexes/),
  [GDS FastRP](https://neo4j.com/docs/graph-data-science/current/algorithms/fastrp/),
  [GDS editions](https://neo4j.com/docs/graph-data-science/current/introduction/),
  [GDS and Neo4j versions](https://neo4j.com/docs/graph-data-science/current/installation/supported-neo4j-versions/).
- In this repository: `pangloss_models/model_bases/labels.py` (a node's kind among its labels),
  `pangloss_cypher/build_update_query.py` (`KEPT_PROPERTIES`, the replace), `pangloss_cypher/read_query.py` (what a
  read returns), `pangloss_cypher/pending.py` and `implementation_docs/derived.md` (the queue and the worker),
  `implementation_docs/admin.md` (jobs).
