# FastRP: the graph part of similarity 🚧

`pangloss-fastrp`: the part `"graph"` of [`pangloss-vectors`](vectors.md), a vector for each document and entity
from what it is **joined** to, made by FastRP. Built as phase 3 of [the build plan](similarity-build-plan.md) and
kept current by phase 5's worker (2026-11-21), in Python on both backends. **Not built**: the engine in a Memgraph
query module (phase 4, deferred by the user on 2026-11-21: a trial found it no faster for a rebuild). The design, and
why each rule is as it is, are in [graph embeddings](graph-embeddings.md), "The joined graph, as now proposed".

```python
# settings.py
INSTALLED_APPS = [..., "pangloss_vectors", "pangloss_fastrp"]
```

Needs `pangloss_vectors`, and a backend with Cypher and a vector index (`requires = {"cypher", "vector_index"}`:
Memgraph and Neo4j). It is the first package of the workspace to depend on numpy and scipy, imported only when the
maths runs (not by a client of the SDK that imports the models).

## Contents

- What is built, and what is not
- What the graph part is
- The joined graph
- `FastRPMeta`
- The settings
- Rebuild, refresh and overlay
- The actual network: the second part, `"actual"`
- Past the cap: groups, then approximate vectors
- Open: for the user to decide
- Measured
- As built: where the code differs from the plan
- The code

## What is built, and what is not

| | What |
|---|---|
| ✅ | The rules worked out of the models as plain data (`maps.py`), with what a class says (`FastRPMeta`), checked at `initialise()` |
| ✅ | The maths with no database in it (`maths.py`): the joins, FastRP, the exact refresh after a change, the overlay of a write not made |
| ✅ | The reader of a Cypher database (`cypher_reader.py`), on both backends; every query found by an index |
| ✅ | The part `"graph"` (`part.py`): rebuild, refresh, overlay, what it says of an unknown (`unknown`, step 10.2b); at weight 1 in the default profile |
| ✅ | The second part, `"actual"` (`ActualPart`, `walk.py`; step 5.4 of [the spaces plan](spaces-and-comparison-plan.md), 2026-11-27): a document joins by what the walk says of its path; at weight 0, and idle unless a profile weighs it ([below](#the-actual-network-the-second-part-actual)) |
| ✅ | Kept current after writes by `pangloss-vectors`' worker; a batch past `FASTRP_REFRESH_CAP` refreshed in groups, exactly; approximate vectors counted stale only for what is past it alone (`approximate.py`) |
| ⏳ | The engine in a Memgraph query module (phase 4): deferred by the user, 2026-11-21 |
| ⏳ | Measured on Neo4j at size; quality with shares, citation joins and vocabularies on and off; a real project's data |

## What the graph part is

FastRP (fast random projection) gives every point of a graph a random vector made from its id, and then, step by
step, replaces each point's vector by the sum of its neighbours', each at the weight of its join, made of length
one. An item's vector is a weighted sum of its steps
(`FASTRP_STEPS`). Two items joined to the same things end with vectors that point the same way; the cosine of the two
is their similarity by the graph. With `k` steps a vector depends on what is within `k` joins of the item.

The seed of each point comes from a hash of its id (blake2b, then splitmix64 for each dimension), so it is the same
in any engine and any order of reading; the maths is deterministic.

## The joined graph

FastRP runs on a graph of its own, worked out from what Pangloss stores, in plain words:

- **The points** are documents and entities, nested documents too (a statement in a factoid). They are called
  *stops*.
- **The wrappers between them are passed through**, however many there are: reified relations, semantic spaces,
  conjunctions and embedded objects. So a factoid is joined to the statements in it, and a statement to the people
  it names through an `InRole` or an `Identification[WeightedAlternative[Person]]`, in one join each.
- **A nested document is joined to the document it is in.**
- **A wrapper's own relations** (`InRole.at`, beside the `target` it holds) are joined to the document the chain
  started from, unless the wrapper's class says `own=False`.
- **Shares**: the alternatives of a field with `SumsTo` count at their share (70% counts 0.7). The candidates a
  `MatchesCriteria` was given count at one over their number.
- **A citation** (`Cites[T]`) joins the citing document to what it cites. A cited basis (`PGCitedBasis`) is passed
  through, so a document is joined to what its basis cites.
- **One join for each pair**, at the largest weight of the ways between them; a join has no direction. The weight
  of a way is the product of the class weight of the document it starts from, the field's weight, each wrapper
  class's weight on the way, and the shares.
- **Out of the graph**: what is deleted, or merged into another; a derived document and what is nested in it;
  a class with `FastRPMeta(include=False)`; citations as points of their own; and, by `VECTORS_GRAPH_SEES`, what a
  reader who is not logged in may not see (unpublished documents, candidates with `seen_by: "logged_in"`). A nested
  document is out when its head is.
- Only forward edges are followed: not the reverse edge of a relation, and not the edges `pangloss-derived` writes.
- **A guess no person has confirmed is not walked** ✅ (step 10.5c): a chain that reaches a node of a class the core's
  `hooks.unconfirmed` names ends there with no join, as at a `FastRPMeta(stop=True)`, whatever the class's own
  `FastRPMeta` says (`maps.py`: the class is an `END`). With `pangloss-library` that is every class of suggestion
  (`IdentificationByToolchain` and below, an outside toolchain's too), so a suggestion that a mention is A, B or C
  joins none of them to its document until a person confirms it (it is then an `Identification`, which is passed
  through). The overlay, the refresh and an unknown's vector follow the maps (the suite of the parts has a document
  holding suggestions, then confirmed: refreshed as rebuilt). **The maps are in the part's signature**, so a project
  with such classes (every project with the library, whether or not it has stored a suggestion) has a rebuild due
  once after this change: `pangloss vectors status` says, for the part `graph` and each profile that weighs it,
  "rebuild due: its signature is now …, not the … it was built with: the models it reads, a setting it depends on,
  or which classes have no vectors changed".

An item that is joined to nothing has no graph vector (it still has its class vector).

## `FastRPMeta`

A class says how it counts with a meta slot. A subclass has its parent's setting unless it says its own, and a trait's
setting counts for the classes that have it. A class that says nothing is `FastRPMeta()`.

```python
from pangloss_fastrp import FastRPMeta
```

| Option | Default | On | |
|---|---|---|---|
| `weight` | 1 | any class | Of a class of documents or entities, the weight of every join that starts from one of its items; of a wrapper class, of every chain through one of its nodes |
| `weights` | `{}` | any class | A weight for each field of the class (a relation or an embedded object) that is not 1 |
| `stop` | `False` | a wrapper class | A chain that reaches one of its nodes ends there, with no join |
| `own` | `True` | a wrapper class | Whether the wrapper's own relations are joined to the document the chain started from |
| `include` | `True` | a class of documents or entities | `False` leaves its items out of the graph: they have no graph vector, and join nothing |

A weight is a number of 0 or more; the weights along a chain multiply.

**`weight`**: a kind of statement that says little about who is like whom counts for less.

```python
class Mention(Statement):
    _fastrp_meta = FastRPMeta(weight=0.2)
```

**`weights`**: the bystanders of an event join it to its people at half the weight of the rest.

```python
class Activity(Statement):
    _fastrp_meta = FastRPMeta(weights={"bystanders": 0.5})

    carried_out_by: Agent
    bystanders: list[Person]
```

**`stop`**: what is said not to be so does not join its statement to the people in it (the demo's `Negative`).

```python
class Negative[T](SemanticSpace[T]):
    _fastrp_meta = FastRPMeta(stop=True)
```

**`own`**: the place of a role (`InRole.at`) is not joined to the document the role is in.

```python
class InRole[T](ReifiedRelation[T]):
    _fastrp_meta = FastRPMeta(own=False)

    role: str
    at: list[Place]
```

**`include`**: a hub (a source cited by thousands of documents) is left out of the graph, so that it neither joins
them all to each other nor makes every update near it read half the database.

```python
class Source(Entity):
    _fastrp_meta = FastRPMeta(include=False)
```

`initialise()` refuses, by the name of the class that says it: a field in `weights` that is not a relation or
embedded field of the class, a weight below 0, `stop` or `own` on a class that is not a wrapper, `include=False` on
a wrapper (use `stop=True`, or `weight=0`), and the slot on an edge model (its edges have the weight of their field).

`FastRPMeta` is not `VectorsMeta(include=False)`: that one gives a class's items no vectors at all, in any part; this
one leaves them out of the graph only, and they keep their class vector.

## The settings

| Setting | Default | |
|---|---|---|
| `FASTRP_STEPS` | `[0, 1, 1]` | The weight of each step of FastRP in the vector, the first step first: 1 to 8 numbers of 0 or more, not all 0. With `k` steps a vector depends on what is within `k` joins, and a change is followed `2k − 1` joins out. **The default is open** (below) |
| `FASTRP_DIMENSION` | 128 | The length of the graph part's vectors, a whole number from 8 to 2048 |
| `FASTRP_REFRESH_CAP` | 50,000 | The most nodes a refresh reads around what changed; past it, the batch in groups, and approximate vectors for what is past it alone (below) |
| `FASTRP_DEGREE_WEIGHTS` | `{"expected": 0.8, "likely": 0.6, "possible": 0.4, "unlikely": 0.2, "impossible": 0.0, "none": 0.5}` | Of the second part only: the weight at which a document joins that leans for, by its degree (`DEGREE_STEPS`; `"none"`: no degree entered and no default of its class). Every one named, each from 0 to 1; 0 is out of the graph. Checked at `initialise()` when the app is installed (the three above are checked where they are read) |

The part follows `VECTORS_GRAPH_SEES` too (`pangloss-vectors`' setting: `"everyone"` or `"logged_in"`).

The part's `signature()` is a hash of its maps: the kinds and weights worked out of the models, `FASTRP_STEPS`,
`FASTRP_DIMENSION` and `VECTORS_GRAPH_SEES`. A change to any of them makes a rebuild due (`pangloss vectors status`
says why). `FASTRP_REFRESH_CAP` is not in it.

## Rebuild, refresh and overlay

- **A rebuild** (`pangloss vectors rebuild`, or `--part graph`) reads every node and forward edge into memory, in
  pages of 10,000 by id, each page one row of lists, an edge with only the properties the maths reads (`load_all`).
  The maths runs in a thread, and the vectors are written in pages through `pangloss-vectors`' writer, into a new
  generation.
- **A refresh** after a write of some heads computes, exactly as a rebuild would, every vector the write can have
  changed: those within `k − 1` joins of what changed, from the graph `2k − 1` joins out (with three steps, within
  two joins, from five). What changed is the trees of the heads written and removed, every stop they are joined to
  as they are now *or would be were they in* (so the neighbours of what was deleted, unpublished or merged are found
  by the edges it still has), and what the heads named before the write (`Changed.before`, which the worker takes
  from the mark: a reference an update dropped leaves no edge to find it by, and the nested documents an update
  replaced have new ids). The vectors of what is now joined to nothing go. The reader of a refresh
  (`CypherReader`) works over one read transaction; the maths runs in a thread and each read goes back to the loop.
  On Memgraph a refresh reads one snapshot; **on Neo4j each query reads what is committed when it runs**, so a write
  made during a refresh can be seen in part (its own mark brings the next turn).
- **An overlay** of a write plan gives the vectors its stops (the head, its nested documents, the entities it
  writes) would have were it written, laid over the database; nothing is written. It is what reconciliation will
  use (phase 10, not built). A `MatchesCriteria` in a plan has no candidates yet, so it adds nothing.
- ✅ **An unknown** (step 10.2b; `unknown(plan, unknowns)`, `part.unknown_plan`): the vector an entity of a stand-in's
  class would have in its place. The same reading as an overlay (`_overlaid`: `_resolved`, `laid_out`, the maths
  over the database), with each unknown's node laid out as a node of its class (`stop_class`: the class itself, or
  for an abstract one, which the maps have no kind for, the first concrete class of entities below it that is a
  stop, in the order of names; nothing for a class out of the graph), reached by the edges that reach the stand-in
  in the plan and with nothing of what the stand-in itself points at. **Every node of the plan is taken as
  published**, whatever the head's `published` and `VECTORS_GRAPH_SEES`, an update's head too: a new document of a
  reviewed class is unpublished, and with the default setting its overlay would be empty. The rest of the database
  is read as the setting sees it, so nothing of another unpublished document reaches the vector. Only the unknowns'
  vectors are given. Tested by the suite of the parts (the unknown's vector is the stored one of a person made with
  its id once the same instance is written naming them) and in `test_fastrp_part_live.py` (an unpublished payload;
  an update of an unpublished document).

The worker that calls the refresh, the marks, and how it and a rebuild keep out of each other's way are in
[vectors](vectors.md), "Keeping vectors current".

## The actual network: the second part, `"actual"`

✅ Built 2026-11-27 (step 5.4 of [the spaces plan](spaces-and-comparison-plan.md), measured before it was built:
its "5.4 measured"). The graph part is the **structural** network: every statement is joined, denied, reported or
ordered alike, which is what finding statements and reconciling ("who is this?") want. The second part answers "who
met whom?": it is the graph part, with one difference, **a document joins by what the walk says of it** (the rule
"by-walk" of 5.3; `walk.py`).

For every stop that is a document, nested or a head, the walk (`pangloss_models.spaces.signature`) of its stored
path (`meta.path`; for a head, whose path is empty, of its class, so that the ground of its class counts) gives:

| The walk says | The document |
|---|---|
| asserted (`veridical == 1`) | joins as in the structural network |
| denied (`-1`) | is out of the graph, as a deleted node is: no joins, no vector |
| neither, leaning for | joins at the weight of its degree (`FASTRP_DEGREE_WEIGHTS`; a weight of 0 is out) |
| neither, leaning against or neither way | is out of the graph |

Entities, wrappers and citations are untouched. The weight is a field of the node (`maths.Node.weight`, 1 in the
graph part), multiplied in wherever the node's class weight is: the chains it starts, and a chain that ends at it as a
nested document. A path with no space in it, under a head whose ground asserts, is not walked; the walk is asked once
for each *shape* of path (the path without its ids). The reader reads the path in the same queries as the node, one
column more (`cypher_reader.page_query`, `nodes_query`, `walk=`); the graph part's queries are as they were. An
overlay takes each node's path from the plan's `meta`, which the write plan computes for every node below the head.

**What follows from the rule** (as decided, and as the figures of 5.4 show):

- someone said *not* to have been somewhere is no longer tied to it; a member said not to have been at an assembly
  is tied to the group by the membership alone; a prohibition kept ties no one through its contents;
- **an order not carried out still ties the giver and the receiver**: what is prescribed joins at its degree, whatever
  came of it (on 5.1's world, 0.268 against 0.161 by assertions alone, 0.395 in the structural network). And an order
  forbidden still joins the two by the order itself, which is asserted;
- `FastRPMeta(stop=True)` is **unchanged** and means the same in both parts: it ends the chains through a wrapper
  class. In the structural network it keeps a denied statement from being near its factoid, and does not keep a
  denied meeting from joining its people (5.3's figures).

**Idle unless weighed.** The part is at weight 0 (in the default profile only if a project's profile weighs it, as
the name part), and while no profile of `VECTORS_PROFILES` weighs it a rebuild of it writes nothing and returns 0 (its
state is kept, with no vectors), a refresh gives nothing, and an overlay and an unknown are empty: a registered part is
rebuilt and refreshed whether weighed or not, and this one costs what the graph part costs. Whether it is weighed is
in its `signature()`, beside the maps' signature, the degree weights and what the walk reads of the models (every
space class, every ground of a head class): so when a profile first weighs it a rebuild is due.

**What it costs** (measured 2026-11-26 on the planted world for comparison at 32,000 people asked for: 1,119,967
nodes, 2,495,018 edges; the plan's "5.4 measured"): **it doubles a rebuild and a turn of the worker**, on both
backends. A rebuild of it alone took 105 s on Memgraph and 58 s on Neo4j (of which reading the graph with the paths
16 s and 11 s, the walk 0.5 s, the maths 5 s and 4 s, writing the vectors 80 s and 38 s), and combining a profile
that weighs it 206 s and 90 s more: 311 s and 149 s added to a rebuild of 310 s and 161 s. A turn of the worker for
one plain factoid went from 6.1 s to 12.0 s at the median on Memgraph, and 5.4 s to 11.0 s on Neo4j (at this size a
factoid changes some 170 vectors of each part). The two parts read the database each for itself: no reading is
shared.

Turned on by a profile (`guide/vectors/README.md`, "Profiles"), as `VECTORS_PROFILES = {"default": {"graph": 1,
"class": 0.1}, "who_met": {"actual": 1, "class": 0.1}}`, then a migration (its vector indexes) and a rebuild.

## Past the cap: groups, then approximate vectors

A change near a hub (a source cited by thousands of documents, a person in thousands of factoids) would have the
refresh read much of the database. `FASTRP_REFRESH_CAP` bounds how many stops one refresh reads around what changed.

**A batch past the cap is refreshed in groups** (step 7a.1 of the build plan, 2026-11-21; `part.in_groups`). The
worker gives the part a batch of heads at once, and many small writes can pass the cap together though none would
alone. So the batch is divided into *units* (each head written, each head removed, each stop a head written named
before), and on `TooLarge` the units, in sorted order, are halved, each half refreshed by itself, down to one unit.
The answer of a refresh for a stop does not depend on what else is in the centre, so the union of the groups' answers
is the answer of the whole batch, and **exact** (the pure test divides random batches into 2, 3 and 7 groups and
compares the union with a rebuild). The groups overlap and the halves are tried again, so all of them run inside
one read transaction on a reader that asks the database for an id at most once (`cypher_reader.RememberingReader`);
it forgets everything once it holds more than forty times the cap of ids and answers, edges counted with nodes (`REMEMBERED_CAPS`), and reads again.

**Only what is past the cap alone is not exact.** A head written that is past it alone gets, for the stops of its
tree, a vector from their own joins and the **stored** vectors of what they are joined to (`approximate.py`): the
first step exact, the later ones taken from the stored vectors in place of the steps only the graph beyond could
give. They are written after the exact vectors of the same refresh, and never in place of one: a stop a group
answered exactly is left out of the approximation, and is a neighbour by its stored (fresh) vector. A head removed,
or a stop named before, that is past the cap alone is left as it was. The part's state counts as **stale** the
approximate vectors written and one for each unit left as it was; `Refreshed.written` is the exact vectors only. A
rebuild sets the count to zero; with `VECTORS_REBUILD_AFTER` the worker starts one when the count passes it.

How close the approximate vectors are: on simulated hubs (a person in every transfer of sixty, thirty seeds,
2026-11-21), with the default steps the cosine with the exact vector was at least 0.89 at full weight and 0.93 at
the half weight now used, of a document's head and its statement; with four steps a statement's was poorer (0.74 at
the least), with two 0.92 (`tests/test_fastrp_approximate.py`).

## Open: for the user to decide

Not settled, and not to be read as settled anywhere in these pages:

- **The default number of steps.** `[0, 1, 1]` for now. More steps find more on planted data and widen every
  update's reach (the figures are below).
- **Whether vocabularies and typologies are in the graph**, and at what weight. In, at weight 1, for now.
- **Whether classes of packages should have vectors**: review's unreconciled mentions and the entries of a typology
  have them, and are listed among an item's similar. A project can say `FastRPMeta(include=False)` or
  `VectorsMeta(include=False)` of its own classes, not of a package's.
- ~~**A burst of writes leaves approximate vectors**~~: decided by the user (2026-11-21, halves down to one unit
  before approximating) and built ("Past the cap", above); in `TODO.md` until it is measured.
- **A hook for `pangloss check` to say a rebuild is due**: it reads no database today; `pangloss vectors status` says
  it.

They are in `TODO.md` too.

## Measured

All on Memgraph 3.14 in Docker on a laptop, the scratch database `pangloss-memgraph-identity` (`:7690`, the demo's
models); the scripts and their output are in `notes/similarity-evaluation/`. **Nothing at size on Neo4j.**

**Step 3.5, 2026-11-21** (`measure.py`, `VECTORS_GRAPH_SEES = "logged_in"`: the data is nearly all unpublished, and
with `"everyone"` only 3,050 stops are joined to anything): 655,971 nodes and 1,030,449 forward edges read; 260,479
stops; 408,871 joins among 257,255 of them. A stop has 3 joins at the median, 7 at the 99th percentile; one source
has 19,766, and some people about 3,000.

| | Seconds |
|---|---|
| Reading the graph into memory | 37.0 at first; 12.2 after the reader was mended (a page now one row of lists) |
| The joins; FastRP | 2.0; 1.0 |
| The graph part's share of a whole rebuild, written and indexed | 93 (257,255 vectors); 80 after the mending |
| A whole rebuild of both parts (`pangloss vectors rebuild`) | 240; 263 after the mending, when nested documents got class vectors too (most of it combining the profile: [vectors](vectors.md), "Measured") |

What a refresh of one document reads (500 documents; the stops within `2k − 1` joins):

| Steps | Median | 90% | Most | Past the cap of 50,000 |
|---|---|---|---|---|
| 2 | 56 | 39,542 | 39,547 | 0% |
| 3 (the default) | 1,027 | 51,628 | 52,782 | 12% |
| 4 | 8,014 | 67,125 | 96,025 | 32% |
| 3, the most joined 0.1% of stops (257) left out | 151 | 341 | 546 | 0% |

So hubs, not steps, are what push updates past the cap on this data, and `FastRPMeta(include=False)` or a low weight
on a hub class is the lever. A refresh in memory, capped: 298 ms on average.

Planted quality by steps (`steps_planted.py`: of a person's ten nearest, the share of their own family; chance 1%):
`[0, 1]` 15.0%, `[0, 1, 1]` 19.2%, four steps 31.0%, six 42.2%, eight 47.4%; `[0, 0, 1]` 24.1%.

**Phase 5, 2026-11-21** (`measure_worker.py`, `:7690` at 1.9 million nodes; factoids of one statement naming two
people at random):

- the mark costs a small write nothing that shows: 12.6 ms with it, 12.2 ms without, at the median of 200;
- one turn of the worker for one factoid: 1.2 s at the median (1.8 s at 90%, 5.3 s the slowest), exact, 52 vectors
  written; writing them in place 0.22 s of it, 4.4 ms for each vector;
- a batch of 200 factoids is past the cap together, though each alone is not: the reader spends 14 s finding that
  out, then every vector is made approximately and counted stale, 18 s in all. With four writers (41 writes a
  second) a write waited 18.5 s at the median for its vectors, 20.6 s at most, and none of them is exact until a
  rebuild.

**Phase 4's trial, 2026-11-21** (`module_scan_trial.py`, `:7690`): reading every node and forward edge (655,971 and
about a million) took 14.1 s in a query module and 11.6 s in Python through Cypher. A refresh of one document in
Python: 272 ms at the median, 7.3 s the slowest of 28. Hence the deferral: for a rebuild the module buys nothing.

**On planted data, in the tests** (both backends): 40 people in 4 families written as factoids through `InRole` and
`Identification`: a person's five nearest people are of the family in 200 places of 200, and a factoid's nearest
factoid in 31 or 32 of 32 (`test_fastrp_similar_live.py`). `wrapper_walks.py`'s figures through the maths: the same
family among a person's ten nearest 19% to 20% at every depth of wrappers; shares 34.0 against flat 27.4 on its
world B (`test_fastrp_planted.py`).

## As built: where the code differs from the plan

- **No `through` option** on `FastRPMeta`: the investigation gave it no meaning the other options have not.
  `include` is the fifth option instead.
- **`PGCitedBasis`**, a third citation class (a node of the citing document that holds citations in `basis`), is
  passed through as a wrapper, so a document is joined to what its basis cites.
- **The join of a nested document to the one it is in takes the nested document's class weight**, so that a
  quieted nested class is quiet all the way up.
- **A computed field's share counts every candidate edge the reader may see**, whatever its end is (the
  investigation says "the candidates that are in"; a delete or a merge drops computed edges, so the two rarely
  differ).
- The reader is `nodes`, `out_edges`, `in_edges` and `citing` (the citations that cite these): a citation is a node
  joined as a chain's end, so there is no `citations()` giving pairs.

## The code

| File | |
|---|---|
| `meta.py` | `FastRPMeta`, and its checks at `initialise()` |
| `settings.py` | `FASTRP_STEPS`, `FASTRP_DIMENSION`, `FASTRP_REFRESH_CAP`, `FASTRP_DEGREE_WEIGHTS` (checked at `initialise()`) |
| `maps.py` | `graph_maps()`: the rules as plain data (`GraphMaps`: kinds, class and field weights, held fields, shares, citations, steps, dimension, what the graph sees), and `signature()` |
| `maths.py` | The joins, the seeds, FastRP, `refresh`, `overlay`: no database |
| `memory.py` | `MemoryReader`, a graph held in dicts |
| `cypher_reader.py` | `load_all` (a rebuild), `CypherReader` (a refresh or an overlay), `RememberingReader` (the groups of a refresh) |
| `part.py` | The part `"graph"`: `rebuild`, `refresh`, `overlay`, `unknown`, `refresh_ids(..., before=)`, `in_groups` (a batch past the cap in halves), `unknown_plan`, `stop_class`; the second part `"actual"` (`ActualPart`, the same with `walked`, its vectors by `part=`; idle unless weighed) |
| `walk.py` | `Walk`: a document's weight in the second part by what the walk says of its path, asked once for each shape |
| `approximate.py` | The vectors past the cap |
| `testing.py` | `oracle(graph, maps)` and `World` (random graphs of every shape, random edits; `weighted=True`, documents weighed as the second part's walk would, and an edit that changes a weight): what the tests compare against |

Tests: the pure ones in `tests/` (the exactness under 200 seeded rounds of random edits, each compared with a whole
rebuild to 10⁻⁵, and batches of them refreshed in 2, 3 and 7 groups; 51 overlays; one test for each rule; the maps; the planted figures; the approximation), the live ones
in `tests/live/` on both backends (the reader against a `MemoryReader` of the same payloads, the part against the
oracle, the worker after every kind of write).
