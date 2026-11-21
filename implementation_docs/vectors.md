# Vectors: similarity 🚧

`pangloss-vectors`: a vector for each document and entity, from which "items like this one" are found through the
backend's vector index. Built as phase 2 of [the build plan](similarity-build-plan.md) (2026-11-21), whose "As built"
sections say where the code differs from the steps; the design and the measurements behind it are in
[graph embeddings](graph-embeddings.md) and [the similarity plan](similarity-plan.md).

```python
# settings.py
INSTALLED_APPS = [..., "pangloss_vectors"]
```

Needs a backend with Cypher and a vector index (`requires = {"cypher", "vector_index"}`: Memgraph and Neo4j).

## Contents

- What is built, and what is not
- Parts and profiles
- What is stored
- `VectorsMeta` and groups
- The settings
- Generations and the switch
- Search
- Rebuild and status
- The API
- The commands and the admin job
- The interface
- The class part
- The graph part 🚧
- Keeping vectors current
- Measured

## What is built, and what is not

| | What |
|---|---|
| ✅ | The `Part` protocol, `register_part`, profiles (`VECTORS_PROFILES`, checked at `initialise()`) |
| ✅ | The store: parts and profile vectors on nodes of their own, generations, the switch, changes in place |
| ✅ | `VectorsMeta(searchable=, include=)`; groups; the vector indexes follow the models into the project's migrations |
| ✅ | The class part: the hierarchy of the models as a vector |
| ✅ | `nearest`: through a profile's (or a group's) vector index, cut to what the reader may see |
| ✅ | `rebuild` under a lease, `status` with its reasons, `pangloss vectors rebuild \| status \| weights`, the admin job |
| ✅ | `GET /api/NAME/{id}/similar`, `GET /api/vectors/status` |
| 🚧 | The graph part (`pangloss-fastrp`, phases 3 and 4 of the plan): the part `"graph"`, its rebuild, a `refresh` that misses a reference an update dropped, `overlay`; in Python on both backends. Not yet the Memgraph module, nor the measurements of 3.5 (below) |
| ✅ | The worker that keeps vectors current after writes ([Keeping vectors current](#keeping-vectors-current)). An item saved since the worker last ran is `pending`, or has its vector of before, until the next turn |
| ✅ | The interface (phase 6): the section "Similar" on every item's page, the part of `/admin` ([The interface](#the-interface)) |
| ⏳ | A model method (`Model.similar()`) and the SDK's side |
| ⏳ | `pangloss check` saying a rebuild is due: it reads no database, and has no hook for an app's check of one; `pangloss vectors status` says it |

## Parts and profiles

A **part** is one kind of vector of an item: `"class"` (here) from the hierarchy of the models, `"graph"`
(`pangloss-fastrp`) from what an item is connected to. It is an object with `name`, `local`, `requires`, `weight`,
`dimension()`, `signature()`, `rebuild(write)`, `refresh(changed, write)` and `overlay(plan)`
(`pangloss_vectors.Part`), given to `register_part` when its package is imported. This package stores what a part
computes, and searches it; it knows nothing of how a part is computed.

- `signature()` is a hash of everything a rebuild depends on (the models a part reads, its settings): it is stored
  with a generation, and another one today means a rebuild is due.
- `requires` names capabilities of the backend; a part the backend cannot build is skipped by a rebuild, and said.

A **profile** is data: a weight for each part, by name.

```python
VECTORS_PROFILES = {"default": {"graph": 1, "class": 0.1}}
```

Without the setting, `"default"` is every registered part at its own `weight`. **A weight is the weight of a part's
cosine**: a profile's vector is its parts end to end, each at length one and scaled by the square root of its
weight, so that the cosine of two such vectors is the weighted mean of the cosines of their parts. A profile that
names a part that is not registered, a negative weight, or only zeros, is refused at `initialise()`.

## What is stored

| Node | Is |
|---|---|
| `PGVector {of, part, type, generation, vector}` | One part of one item (`of` is its id); no vector index |
| `PGProfileVector:PGV_<profile>_<dimension>[:PGV_<profile>_<dimension>_<Group>…] {of, profile, type, generation, vector}` | The combined vector of an item for a profile, under the profile's label and one more for each group of its class; indexed by `pgv_<profile>_<dimension>` and `pgv_<profile>_<dimension>_<group>` |
| `PGVectorState {part, generation, built_at, count, stale, signature, graph_sees}` | A part's state: the generation in use and what it was built with |
| `PGVectorProfile {profile, generation, signature, dimension, weights, built_at, count, removed}` | A profile's state. `weights` as JSON; `removed`, the vectors deleted in place since it was built (below) |
| `PGVectorsRebuild {key, holder, by, since, until}` | The lease of a rebuild |

None of them has an edge. The dimension is in the label and the name of an index because Memgraph refuses to make a
vector index while any node of the label has the property at another length: a class added to a project changes the
class part's dimension, and so the names of the vector indexes, which is a migration.

## `VectorsMeta` and groups

```python
from pangloss_vectors import VectorsMeta


class Person(Entity):
    _vectors_meta = VectorsMeta(searchable=True)       # a group: "people like this one"


class Note(Document):
    _vectors_meta = VectorsMeta(include=False)         # no vectors at all
```

A **group** is a class that says `searchable=True` itself (a document or entity class: anything else is refused at
`initialise()`). Its subclasses are in its group and are not groups of their own. Each profile has a vector index of
each group. `include=False` gives the class's items no vectors: they are never found, and never searched from. The
vector indexes (`structure.indexes()`) follow the models into the **project's** migrations: a group's to the app of its
class, a profile's to the app with the most models, or `VECTORS_MIGRATIONS_APP`.

## The settings

| Setting | Default | |
|---|---|---|
| `VECTORS_PROFILES` | every part at its own weight, as `"default"` | A weight for each part, by profile |
| `VECTORS_CLASS_DECAY` | 0.5 | What the class part gives each class above an item's (0 to 1) |
| `VECTORS_GRAPH_SEES` | `"everyone"` | What the graph a vector is computed from holds: what a reader who is not logged in sees, or (`"logged_in"`) everything not deleted. Stored with a part's generation; another value today is a rebuild due |
| `VECTORS_OVERFETCH` | 4 | A search asks the index for this many times the hits it wants |
| `VECTORS_MIGRATIONS_APP` | the app with the most models | Whose migrations make the vector indexes of the profiles |
| `VECTORS_WORKER_IN_SERVER` | true | Whether the worker that keeps vectors current runs in the server (or apart: `pangloss vectors worker`) |
| `VECTORS_REBUILD_AFTER` | none | A number of stale vectors of a part past which the worker starts its rebuild |

## Generations and the switch

A rebuild writes a new **generation** of each part's vectors beside the one in use, combines a new generation of each
profile that weighs one of them, once, from all the new ones, and then **switches**: one transaction that sets the
generations (and what they were built with) on the state nodes of every part and profile rebuilt, and nothing else. Readers read whatever generation the states name, so a search
during a rebuild sees the old generation, whole. After the switch the older generations are dropped in batches.
Numbers are one sequence for all parts and profiles.

`store.set_vectors` changes the generation in use in place (and the profile vectors that follow it), `delete_for`
deletes every vector of some items; both keep the states' `count` that of the generation in use, and a profile's
`removed` counts what they deleted since its build.

## Search

```python
from pangloss_vectors import nearest

found = await nearest(str(person.id), profile="default", group="Person", k=10, see_unpublished=False)
found.status        # "ok", "pending", "rebuild_due"
found.hits          # [Hit(id, type, score), ...], nearest first; score the cosine
```

One query: the profile's state, the vector index of the profile or group, the hits of the generation in use, each
matched to its item (`PGIndexableNode(id)`: a head, or a document nested in one) and kept if the reader may look
through it, by its head (`fragments.listed`: not deleted, published unless `see_unpublished`, not merged into
another). An index seek on both backends (`test_the_class_part_s_queries_and_the_search_read_from_indexes`). Never
the item itself; an entity merged into another answers for its survivor; the item searched from may be a nested
document too, and a group (`Statement`) finds the nested documents of the classes below it. `"pending"`: the item has no vector, or the profile was never built; `"rebuild_due"`: the profile's
vectors are of another dimension than its parts make today (no hits then).

While it has fewer than `k` hits it asks again for four times as many, up to twice the profile's `count` and
`removed`, plus one, or 4096. (On Memgraph a deleted node keeps its place among the nearest until the database
collects it, about 30 s: notes/similarity-evaluation/deleted_in_index.py; during a rebuild both generations are in
the index. `removed` is there because after many deletes in place the count alone was too low a limit to reach past
them: found in step 2.5, when `count` was first kept right.)

## Rebuild and status

`await pangloss_vectors.rebuild.rebuild(part=None)` rebuilds one part, or every registered part in the order of
their names: for each, a new generation, `part.rebuild(write)` writing into it a page at a time; then `combine` once
for each profile that weighs any of them, from all their new generations; then one switch to all of them; then the
older generations dropped. (Combined after each part, a profile of two parts was combined twice: 46 s and 83 s of a
rebuild of 257,000 items, step 3.5.) Then each profile it did not combine whose weights
or dimension are not those its state says (or that was never built) is combined again alone from the parts in use,
unless one of its parts is itself due (then it is skipped, and said). A part whose `requires` the backend lacks is
skipped, and said. It gives a `Rebuilt`: for each part and profile its generation, count, seconds and how many older
vectors were dropped, what was skipped and why, and the seconds of the whole.

Only one rebuild runs on a database. It holds a lease (`PGVectorsRebuild`), taken in a transaction that takes the
backend's lock (`ensure_lock`, `lock`) so that two cannot take it at once, renewed in the background every 15 s, and
given up at the end. A second is refused with `VectorsRebuildBusy`, which says who holds it (a user, the process and
the host) and since when; a lease that is not given up (the process stopped) runs out after 60 s.

`await pangloss_vectors.status.status()` gives, for each part and profile, the generation in use, when it was built,
the count (and of a part, how many are stale) and the reasons a rebuild is due, in words:

| Of | A rebuild is due when |
|---|---|
| A part | It was never built; its `signature()` is not the one it was built with (the models it reads or a setting it depends on changed, `VECTORS_CLASS_DECAY` for the class part); `VECTORS_GRAPH_SEES` is not what it was built with (said of every part, the class part too, though it reads nothing the setting changes) |
| A profile | It was never built; its weights are not those it was built with; its parts now make another dimension (its vector indexes are new ones: a migration is pending, which `pangloss showmigrations` reports, and the rebuild follows it); a part it weighs is due |

A part the backend cannot build is said to be unavailable, and is never due.

## The API

| Route | Gives |
|---|---|
| `GET /api/NAME/{id}/similar?profile=&type=&limit=` | `{"status": "ok" \| "pending" \| "rebuild_due" \| "excluded", "results": [...], "profiles": [...], "groups": [...]}`: each result the reference view of an item, as a list gives it (camelCase, `meta` and all, read for all the hits in one query), with `similarity`, nearest first, and none of a similarity of 0 or less (below 0.005, which would be written 0.00: such an item has nothing in common with the one asked about; the user, 2026-11-21); `profiles` the names of the profiles (`default` first, then the others in order) and `groups` those a search can be narrowed to, so that the interface needs no second request for its menus |
| `GET /api/vectors/status` | (logged in) The status, as above: `{rebuildDue, rebuilding, parts: [...], profiles: [...]}`; `rebuilding` is `null`, or `{by, since}` of the lease of a rebuild running now (one that has not run out), whoever started it: read with the states, in the same transaction. `pangloss vectors status` says it too |

`NAME` is any document or entity class, the item's own or one above it; another is a 404. The item may be a document
nested in another (a statement in a factoid), and so may the results. What the reader may see is as for
`GET /api/NAME/{id}`, a nested document's by its head: an item that is not there, is deleted, or is unpublished to a
reader who is not logged in is a 404, and such items are never among the results. A nested document's reference view
is the one the core's search gives a nested node (`pangloss_cypher.list_query`): `meta.isHeadNode` false,
`meta.headNodeId` and `meta.headNodeType` of its head, and the head's creators, `published` and `reviewStatus`; a
head's has `isHeadNode` true and no `headNodeId`. `profile` defaults to `default` (an unknown one is a 422);
`type` is a group (a 422 if it is not one); `limit` is 1 to 100 (10). `rebuild_due` is also said with results when
the profile's status is due for any other reason: they are the results of the vectors in use. `excluded`: the item's
own class (its `type`, not the `NAME` asked at) has `VectorsMeta(include=False)`, so it has no vectors and never
will; it is decided before any search, and `results` is empty.

## The commands and the admin job

`pangloss vectors rebuild [--part NAME]`, `pangloss vectors status`, `pangloss vectors weights` (every option in
[the command line guide](../guide/cli.md#pangloss-vectors)). With `pangloss-admin`, the job `vectors_rebuild` on
`/admin` does a rebuild in a process of its own; its option `part` is `all` or one of the parts registered when the
job is declared; its counts are those of each part and profile, and what was skipped is in a file `skipped.txt`.

## The interface

✅ Built (phase 6 of [the build plan](similarity-build-plan.md), 2026-11-21): an interface module of the package
(`pangloss_vectors/interface/`, its words `vectors_*` in `translations/ui.jsonc`).

**The section "Similar"** (`itemSections.Similar`), after the contents of the page of every document and entity, a
head's and a nested document's. It reads `GET /api/{type}/{id}/similar?limit=10` (with `profile` and `type` once
chosen) itself, in a memo under the boundary `ItemSections` gives each section, and again on login and logout
(`useSessionKey`).

| The answer | Shown |
|---|---|
| `excluded` | Nothing |
| `pending` | The bar and "Not worked out yet" |
| `ok` or `rebuild_due`, no results | The bar and "Nothing similar found" |
| Results | One row each, nearest first: a `ReferenceChip` (to the item's own page, as the lists link a nested document), a slate bar as long as the similarity (the route gives none at 0 or below; a `meter` named "Similarity 0.97") and the figure to two decimals. A grid: the chips are one column and the bars another |
| `rebuild_due` | Also, to someone logged in, "The similarity data is due for a rebuild" |

Under the bar, on the right, a `MenuSelect` of the profile (only with more than one) and one of the type, "All types"
and then each group by its model's name (only if there is a group). A choice changes the request, not the address. A
person is not narrowed to people by default, though `Person` is a group: the default is all types.

**The part of `/admin`** (`slots.admin`, "Similarity"): a table of the parts (generation, when built, vectors, stale,
and the state: up to date, rebuild due with the reasons as the API words them, or unavailable and why) and one of the
profiles (weights, generation, when built, vectors, state). **Rebuild** posts `POST /api/admin/jobs {kind:
"vectors_rebuild", options: {part: "all"}}` with no dialog (a rebuild writes a new generation beside the one in use and
destroys nothing); it is off while its own request is out and while `rebuilding` is set, when the section says
"Rebuilding since … (by …)". A refusal is shown above the tables. What is shown comes from a `live()` feed of
`GET /api/vectors/status` (on the interface's server, every `PANGLOSS_VECTORS_POLL_MS`, 1000 ms by default; opened only
in the browser and while the tab is seen), so the figures change when a rebuild ends, whoever started it.

Browser tests: `e2e/test_similar.py` (the e2e project installs both packages and rebuilds once at the start of the
session); the development build, `e2e/test_dev_mode.py`; the states and the requests, the module's Vitest tests.

## The class part

The part `"class"`, registered when the package is imported, at weight 0.1, so every project that installs the
package has it in its default profile. One dimension for each declared class of documents or entities (abstract ones
too) and each semantic trait, in the order of their names. An item's vector is its class at 1, each class above it at
`VECTORS_CLASS_DECAY ** depth`, a semantic trait as a parent of the class that has it (a `SemanticNonHeritableTrait`
only for the class that names it), a class it fulfils (`Fulfils`, by the label on its node) at the decay; the
nearest way up counts; normalised. Plain traits, mixins, the kinds and generic bases are never dimensions. Every
node with the label `Document` or `Entity` has a vector, a nested document as well as a head (as the graph part
gives them), unless it is merged into another, deleted (a nested one: its head is, or is not there), a citation
(`PGCitation`, `PGUnprotectedCitation`) or a cited basis (`PGCitedBasis`, which the graph part takes as a wrapper).
A rebuild reads them by `PGIndexableNode(id)` in pages of 10,000; a refresh of a head reads its nested documents
too. The class part reads nothing of an item's contents, so a document the graph part leaves out (a derived one, and
what is in it) still has a class vector.

So, with the class part alone, a `CreationOfPainting`'s similar are the other paintings, then the artworks, and a
`Birth` after them (`test_a_project_with_only_pangloss_vectors_answers_documents_of_a_like_class`, both backends).

## The graph part 🚧

```python
INSTALLED_APPS = [..., "pangloss_vectors", "pangloss_fastrp"]
```

`pangloss-fastrp` (phase 3 of [the plan](similarity-build-plan.md), 3.1 to 3.4 built 2026-11-21) registers the part
`"graph"`, at weight 1, so with it installed the default profile is the graph at 1 and the class at 0.1. Its vector
of an item is made by FastRP from what the item is **joined** to, in plain words:

- documents and entities are the points of the graph (nested documents too); the wrappers between them (reified
  relations, semantic spaces, conjunctions, embedded objects) are passed through, however many there are, so a
  factoid is joined to the statements in it, and a statement to the people it names through an `InRole` or an
  `Identification[WeightedAlternative[Person]]`;
- a wrapper's own relations (`InRole.at`) are joined to the document the chain started from; the alternatives of a
  field with `SumsTo` count at their shares (70% counts 0.7), and the candidates a `MatchesCriteria` was given at one
  over their number;
- a citation joins the citing document to what it cites;
- what is deleted, merged into another, of a derived document, or (by `VECTORS_GRAPH_SEES`) not published, is out;
  a nested document is out when its head is.

The rules, and why, are in [graph embeddings](graph-embeddings.md), "The joined graph, as now proposed". The
computing is `maths.py`, with no database in it; the rules worked out of the models are `maps.py`; the reader of the
database is `cypher_reader.py`, in Cypher both backends run (every query found by an index: `PGIndexableNode(id)`,
`HeadNode(id)`, `PGIndexableNode(head_node_id)`, `PGCitation(target_id)` and `PGUnprotectedCitation(target_id)`,
checked on both, `test_no_query_of_the_reader_scans_a_label_or_every_node`).

- **A rebuild** reads every node and forward edge into memory (in pages of 10,000 by id, each query one row of
  lists, an edge with only the properties the maths reads), and computes in a thread.
- **A refresh** after a write of some heads computes, exactly as a rebuild would, the vectors the write can have
  changed, from the neighbourhood of the heads' trees and of what those are joined to (as if they were in, so the
  neighbours of what was deleted, unpublished or merged are found by the edges they still have). The vectors of what
  is now joined to nothing go. **What it does not yet catch**: a reference an update *dropped* (no edge is left to
  find the item by), and the nested documents an update replaced with new ids (they are gone from the graph, their
  vectors with nothing to say they should go). Both are caught when the caller gives what was named before
  (`pangloss_fastrp.part.refresh_ids(ids, write, before=...)`), which the part's own `refresh` cannot: phase 5 keeps
  each vector's neighbours for that. Past `FASTRP_REFRESH_CAP` nodes a refresh writes nothing and reports the heads
  as stale.
- **An overlay** of a write plan gives the vectors its stops (the head, its nested documents, the entities it
  writes) would have were it written; nothing is written. A description (`MatchesCriteria`) in a plan has no
  candidates yet.

A class says how it counts with a meta slot, inherited by the classes below it (and from a trait by the classes that
have it):

```python
from pangloss_fastrp import FastRPMeta


class Mention(Statement):
    _fastrp_meta = FastRPMeta(weight=0.2, weights={"bystanders": 0.5})


class Hypothetical[T](SemanticSpace[T]):
    _fastrp_meta = FastRPMeta(stop=True)
```

| Option | Default | |
|---|---|---|
| `weight` | 1 | Of a class of documents or entities: the weight of every join that starts from one of its items. Of a wrapper class: of every chain through it |
| `weights` | `{}` | A weight for each field of the class (a relation or an embedded object) |
| `stop` | `False` | (A wrapper class) a chain that reaches it ends there, with no join |
| `own` | `True` | (A wrapper class) whether its own relations (`InRole.at`, beside the `target` it holds) are joined to the document the chain started from |
| `include` | `True` | (A class of documents or entities) `False` leaves its items out of the graph |

The weights along a chain multiply. `initialise()` refuses a field the class has not, a weight below 0, `stop` or
`own` on a class that is not a wrapper, `include=False` on a wrapper, and the slot on an edge model. Derived documents
are always out.

| Setting | Default | |
|---|---|---|
| `FASTRP_STEPS` | `[0, 1, 1]` | The weight of each step of FastRP in the vector: 1 to 8 numbers of 0 or more, not all 0. With more steps a vector reaches further, and so does the work of keeping it current after a save |
| `FASTRP_DIMENSION` | 128 | The length of the graph part's vectors, from 8 to 2048 |
| `FASTRP_REFRESH_CAP` | 50,000 | The most nodes a refresh reads around a write; past it nothing is written and the heads are stale until a rebuild |

The part follows `VECTORS_GRAPH_SEES` too. A change to a weight, to `FASTRP_STEPS`, `FASTRP_DIMENSION` or
`VECTORS_GRAPH_SEES` changes the part's signature, so a rebuild is due.

On planted data (40 people in 4 families, written as factoids through `InRole` and `Identification`, a few mentions
across), the five people most like each person are all of the person's family, 200 places of 200, on both backends,
and a factoid's similar factoids are led by those of its family (`test_fastrp_similar_live.py`). Measured at scale
in step 3.5 (notes/similarity-evaluation/README.md) and below.

## Keeping vectors current

✅ Built (phase 5 of [the build plan](similarity-build-plan.md)). After a write, a worker in the background brings
the vectors of what changed up to date; no rebuild is needed for ordinary editing.

**What marks work.** A write of a document or entity of a class that has vectors leaves a mark in its own
transaction (`pangloss_cypher.pending`, kind `vectors`), when `pangloss_vectors` is an installed app: a create, an
update, a delete, an undelete, a change of review status (publishing), a restore from history, a merge (the survivor,
the entity absorbed and every document whose references moved) and its undo, and the criteria worker writing the
candidates of a description. An update's mark keeps what the document named before: the entities it referred to, and
the documents nested in it, which an update replaces by new ones.

**Not marked**: a bulk load and a migration. Run `pangloss vectors rebuild` after either.

**The worker** (`worker.py`; in the server unless `VECTORS_WORKER_IN_SERVER` is false, or `pangloss vectors worker`),
one at a time on a database:

1. claims a batch of marked heads;
2. reads what each is now (there, deleted, merged into another) and what its mark kept of before;
3. asks each part that can update in place (`local`) and has been built to refresh: the class part looks the items
   up again; the graph part computes, exactly, every vector the change can have altered (the items within two
   joins, with three steps), from the graph five joins out;
4. deletes every vector of what is gone: the heads removed, the documents nested in them, and what the mark kept of
   before that no longer exists;
5. completes the claims. On a failure they are given back and tried again.

A part that has never been built is skipped: the first vectors come from a rebuild.

**The worker and a rebuild never overlap.** A batch is claimed only if no rebuild holds its lease, and a rebuild
waits for the batch in hand. Marks made while a rebuild runs wait, and are worked after it against the new vectors.

**Past the cap.** A change near a hub (a source cited by thousands of documents) would have the graph part read
much of the database. Past `FASTRP_REFRESH_CAP` nodes (50,000) it writes, for the documents written alone, a vector
taken from the stored vectors of what they are joined to (`approximate.py`: the first step is exact, the later ones
approximate; a cosine of about 0.9 with the exact vector on planted hubs), and counts them as stale in the part's
state. A rebuild sets the count to zero; with `VECTORS_REBUILD_AFTER` the worker starts one when the count passes
it. There is no rebuild at a set hour (`VECTORS_REBUILD_AT` is not built: nothing to hang a schedule on).

**On Neo4j** each query of a refresh reads what is committed when it runs, so a write made during a refresh can be
seen in part; its own mark brings the next turn. On Memgraph a refresh reads one snapshot.

**Not measured yet**: the worker's lag under several writers, and what the mark adds to a save in milliseconds.

## Measured

2026-11-21, Memgraph 3.14 in Docker on a laptop (the scratch `pangloss-memgraph-similar`), 100,000 heads of five
classes made by plain Cypher (40,000 `Person`, 10,000 `Saint`, 20,000 `Birth`, 20,000 `CreationOfPainting`, 10,000
`CreationOfArtwork`), the class part of dimension 7, the package's indexes and the vector indexes made as migrations
would make them:

| | Seconds |
|---|---|
| A whole rebuild (the class part, the default profile) | 22.0 (writing the part's vectors 4.0, combining the profile 15.7, reading the heads 2.1) |
| The same again, dropping the 100,000 older vectors of each | 25.3 (dropping 0.4) |
| `nearest`, `k` 10, ten calls | 56 to 71 ms; with `group="Person"` 55 to 59 ms |

`combine` reads every id of a generation first (1.8 s of its 15.7 s here) and then reads and writes pages of 1,000.

2026-11-21, after the mending of step 3.5, Memgraph on `:7690` (the scratch `pangloss-memgraph-identity`: a million
nodes of the demo's models, 655,971 of them `PGIndexableNode`, 1,030,449 forward edges), `VECTORS_GRAPH_SEES =
"logged_in"`, the class and graph parts:

| | Seconds |
|---|---|
| Reading the graph into memory (`load_all`) | 12.2 (37.1 before: a record for each node and edge, `properties(e)`; a page of 10,000 nodes was 0.17 s of nodes and 0.32 s of edges, now 0.07 s and 0.11 s; pages of 25,000: 13.7) |
| A whole rebuild (`pangloss vectors rebuild`) | 263 (240 before, when the class part had 173,564 heads): the class part 20 (327,109 vectors, nested documents now among them), the graph part 80 (257,255), the profile combined once 163 (twice before: 46 and 83) |
| `nearest`, `k` 10, from people, factoids and nested statements, no group | 81 to 140 ms, 83 at the median (20 calls) |

The profile is now combined once, but of 327,109 items, not 173,564 and then 257,255: of its 163 s, reading every id
is 11 s, reading the parts' vectors and combining them about 24 s (a page of 1,000 in 0.073 s), and the rest, about
128 s, is writing the profile vectors into the vector index's label (not taken apart further).
**Without the package's plain indexes** (`PGVector(of)` and the rest, made by its migration `0001`) the write of a
part's vectors is a scan of every node for each row: about 11 s a page of 1,000 and growing. Not measured on Neo4j.
