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
- The class part
- The graph part 🚧
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
| 🚧 | The graph part (`pangloss-fastrp`, phases 3 and 4 of the plan): the maths, `FastRPMeta` and the settings are built; no reader of a database nor a part yet (below) |
| ⏳ | The worker that keeps vectors current after writes (`refresh`, `overlay`: phase 5). Until it is built, a vector is made only by a rebuild: an item saved since the last one is `pending` |
| ⏳ | The interface (phase 6); a model method (`Model.similar()`) and the SDK's side |
| ⏳ | `pangloss check` saying a rebuild is due: it reads no database, and has no hook for an app's check of one; `pangloss vectors status` says it |

## Parts and profiles

A **part** is one kind of vector of an item: `"class"` (here) from the hierarchy of the models, `"graph"` (to come,
`pangloss-fastrp`) from what an item is connected to. It is an object with `name`, `local`, `requires`, `weight`,
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

## Generations and the switch

A rebuild writes a new **generation** of a part's vectors beside the one in use, combines a new generation of each
profile that weighs the part from it, and then **switches**: one transaction that sets the generation (and what it
was built with) on the state nodes, and nothing else. Readers read whatever generation the states name, so a search
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
matched to its head and kept if the reader may look through it (`fragments.listed`: not deleted, published unless
`see_unpublished`, not merged into another). Never the item itself; an entity merged into another answers for its
survivor. `"pending"`: the item has no vector, or the profile was never built; `"rebuild_due"`: the profile's
vectors are of another dimension than its parts make today (no hits then).

While it has fewer than `k` hits it asks again for four times as many, up to twice the profile's `count` and
`removed`, plus one, or 4096. (On Memgraph a deleted node keeps its place among the nearest until the database
collects it, about 30 s: notes/similarity-evaluation/deleted_in_index.py; during a rebuild both generations are in
the index. `removed` is there because after many deletes in place the count alone was too low a limit to reach past
them: found in step 2.5, when `count` was first kept right.)

## Rebuild and status

`await pangloss_vectors.rebuild.rebuild(part=None)` rebuilds one part, or every registered part in the order of
their names: for each, a new generation, `part.rebuild(write)` writing into it a page at a time, `combine` for each
profile that weighs it, the switch, the older generations dropped. Then each profile it did not combine whose weights
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
| `GET /api/NAME/{id}/similar?profile=&type=&limit=` | `{"status": "ok" \| "pending" \| "rebuild_due", "results": [...]}`: each result the reference view of an item, as a list gives it (camelCase, `meta` and all, read for all the hits in one query), with `similarity`, nearest first |
| `GET /api/vectors/status` | (logged in) The status, as above: `{rebuildDue, parts: [...], profiles: [...]}` |

`NAME` is any document or entity class, the item's own or one above it; another is a 404. What the reader may see
is as for `GET /api/NAME/{id}`: an item that is not there, is deleted, or is unpublished to a reader who is not logged
in is a 404, and such items are never among the results. `profile` defaults to `default` (an unknown one is a 422);
`type` is a group (a 422 if it is not one); `limit` is 1 to 100 (10). `rebuild_due` is also said with results when
the profile's status is due for any other reason: they are the results of the vectors in use.

## The commands and the admin job

`pangloss vectors rebuild [--part NAME]`, `pangloss vectors status`, `pangloss vectors weights` (every option in
[the command line guide](../guide/cli.md#pangloss-vectors)). With `pangloss-admin`, the job `vectors_rebuild` on
`/admin` does a rebuild in a process of its own; its option `part` is `all` or one of the parts registered when the
job is declared; its counts are those of each part and profile, and what was skipped is in a file `skipped.txt`.

## The class part

The part `"class"`, registered when the package is imported, at weight 0.1, so every project that installs the
package has it in its default profile. One dimension for each declared class of documents or entities (abstract ones
too) and each semantic trait, in the order of their names. An item's vector is its class at 1, each class above it at
`VECTORS_CLASS_DECAY ** depth`, a semantic trait as a parent of the class that has it (a `SemanticNonHeritableTrait`
only for the class that names it), a class it fulfils (`Fulfils`, by the label on its node) at the decay; the
nearest way up counts; normalised. Plain traits, mixins, the kinds and generic bases are never dimensions. A head is
`HeadNode` with `Document` or `Entity`, not deleted, not merged into another; the class part reads nothing of an
item's contents.

So, with the class part alone, a `CreationOfPainting`'s similar are the other paintings, then the artworks, and a
`Birth` after them (`test_a_project_with_only_pangloss_vectors_answers_documents_of_a_like_class`, both backends).

## The graph part 🚧

`pangloss-fastrp` (being built: phase 3 of [the plan](similarity-build-plan.md)) will register the part `"graph"`: a
vector for each document and entity from what it is joined to. Two items are joined when a chain of relations leads
from one to the other through wrappers only (reified relations, semantic spaces, conjunctions, embedded objects),
however many there are; a citation joins the citing document to the cited one. The rules are in
[graph embeddings](graph-embeddings.md), "The joined graph, as now proposed". What is built: the computing
(`maths.py`, with no database in it) and the rules as plain data worked out of the models (`maps.py`). There is no
reader of a database and no registered part yet, so no project has graph vectors.

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

The weights along a chain multiply, with the share of each edge of a field with `SumsTo` (an alternative at 70% counts
0.7). `initialise()` refuses a field the class has not, a weight below 0, `stop` or `own` on a class that is not a
wrapper, `include=False` on a wrapper, and the slot on an edge model. Derived documents are always out.

| Setting | Default | |
|---|---|---|
| `FASTRP_STEPS` | `[0, 1, 1]` | The weight of each step of FastRP in the vector: 1 to 8 numbers of 0 or more, not all 0. With more steps a vector reaches further, and so does the work of keeping it current after a save |
| `FASTRP_DIMENSION` | 128 | The length of the graph part's vectors, from 8 to 2048 |

The part follows `VECTORS_GRAPH_SEES` too. A change to a weight, to one of these settings or to `VECTORS_GRAPH_SEES`
changes `pangloss_fastrp.maps.signature()`, which the part will give as its signature: once it is registered, such a
change means a rebuild is due.

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
**Without the package's plain indexes** (`PGVector(of)` and the rest, made by its migration `0001`) the write of a
part's vectors is a scan of every node for each row: about 11 s a page of 1,000 and growing. Not measured on Neo4j.
