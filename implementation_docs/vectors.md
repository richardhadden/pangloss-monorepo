# Vectors: similarity 🚧

`pangloss-vectors`: a vector for each document and entity, from which "items like this one" are found through the
backend's vector index. Built as phases 2, 3, 5 and 6 of [the build plan](similarity-build-plan.md) (2026-11-21):
the package, the graph part ([`pangloss-fastrp`](fastrp.md)), the worker that keeps vectors current, and the
interface; the name part ([`pangloss-names`](names.md)) as phase 8 and the time part
([`pangloss-dates-vectors`](dates-vectors.md)) as phase 9 (2026-11-22). Its "As built" sections say
where the code differs from the steps. **Not built**: phase 4, the graph
part's engine in a Memgraph query module (deferred by the user, 2026-11-21), a model method and the SDK's side, a
rebuild at a time of day (`VECTORS_REBUILD_AT`), and `pangloss check` saying a rebuild is due. The design and the
measurements behind it are in [graph embeddings](graph-embeddings.md) and [the similarity plan](similarity-plan.md);
how to use it is [the guide](../guide/vectors/README.md).

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
- Which classes have no vectors
- The settings
- Generations and the switch
- Search
- Rebuild and status
- The API
- The commands and the admin job
- The interface
- The class part
- The graph part
- The name part
- The time part
- Keeping vectors current
- Measured

## What is built, and what is not

| | What |
|---|---|
| ✅ | The `Part` protocol, `register_part`, profiles (`VECTORS_PROFILES`, checked at `initialise()`) |
| ✅ | The suite every part passes, `pangloss_testing.parts.PartSuite` ([The suite of a part](#the-suite-of-a-part)); called for the graph, the class, the name and the time parts |
| ✅ | What a part keeps with a generation (`Part.kept`, `store.keep`, `store.kept`): the name part's table of rarity (step 8.3) |
| ✅ | What a part says of an unknown of a write plan (`unknown`, `unknowns_of`, `unknown_vectors`): the class, name and graph parts (step 10.2b) |
| ✅ | The store: parts and profile vectors on nodes of their own, generations, the switch, changes in place |
| ✅ | `VectorsMeta(searchable=, include=)`; groups; the vector indexes follow the models into the project's migrations |
| ✅ | No vectors for a class without its package knowing this one: `VECTORS_EXCLUDE`, the stand-ins (review's `Unreconciled`) unless `VECTORS_INCLUDE` ([Which classes have no vectors](#which-classes-have-no-vectors)) |
| ✅ | The class part: the hierarchy of the models as a vector |
| ✅ | `nearest`: by an exact scan while the profile is small (`VECTORS_EXACT_UP_TO`), above that through a profile's (or a group's) vector index, cut to what the reader may see; narrowed to several classes, through the groups' indexes and an exact scan of the rest (step 7a.4); a typology's type given as the other class only where the data uses it as one ([Classes by use](#classes-by-use), step 7a.5) |
| ✅ | `rebuild` under a lease, `status` with its reasons, `pangloss vectors rebuild \| status \| weights`, the admin job |
| ✅ | `GET /api/NAME/{id}/similar`, `GET /api/vectors/status` |
| ✅ | The graph part ([`pangloss-fastrp`](fastrp.md), phase 3 of the plan): the part `"graph"`, its rebuild, an exact `refresh`, `overlay`, in Python on both backends; measured on Memgraph at size |
| ✅ | The name part ([`pangloss-names`](names.md), phase 8 of the plan): the part `"name"` at weight 0, its table of rarity kept with the generation, a table of variants, a search by a name (`vector_of`, `search`, `pangloss names search`) |
| ✅ | The time part ([`pangloss-dates-vectors`](dates-vectors.md), phase 9 of the plan): the part `"time"` at weight 0, a date's bounds as a soft bump on a ring of years; measured on both backends at size |
| ⏳ | The graph part's engine in a Memgraph query module (phase 4): deferred by the user, 2026-11-21 (a trial found it no faster for a rebuild) |
| ✅ | The worker that keeps vectors current after writes ([Keeping vectors current](#keeping-vectors-current)). An item saved since the worker last ran is `pending`, or has its vector of before, until the next turn; `VECTORS_REBUILD_AFTER` |
| ⏳ | A rebuild at a time of day (`VECTORS_REBUILD_AT`): there is nothing to hang a schedule on |
| ✅ | The interface (phase 6): the section "Similar" on every item's page, the part of `/admin` ([The interface](#the-interface)) |
| ⏳ | A model method (`Model.similar()`) and the SDK's side |
| ⏳ | `pangloss check` saying a rebuild is due: it reads no database, and has no hook for an app's check of one; `pangloss vectors status` says it. Whether to add such a hook is open, for the user |

## Parts and profiles

A **part** is one kind of vector of an item. There are five:

- `"class"` (here, weight 0.1) from the hierarchy of the models;
- `"graph"` ([`pangloss-fastrp`](fastrp.md), weight 1) from what an item is connected to;
- `"actual"` ([`pangloss-fastrp`](fastrp.md#the-actual-network-the-second-part-actual) too, weight 0) the same, but a
  document joins by what the walk says of its path (denied or leaning against: not at all; reported, ordered: at its
  degree's weight); it computes nothing while no profile weighs it;
- `"name"` ([`pangloss-names`](names.md), weight 0, so in a profile only if the profile weighs it) from its names;
- `"time"` ([`pangloss-dates-vectors`](dates-vectors.md), weight 0 too) from its dates.

A part is an object with `name`, `local`, `requires`, `weight`,
`dimension()`, `signature()`, `rebuild(write)`, `refresh(changed, write)` and `overlay(plan)`
(`pangloss_vectors.Part`), given to `register_part` when its package is imported. This package stores what a part
computes, and searches it; it knows nothing of how a part is computed.

- `signature()` is a hash of everything a rebuild depends on (the models a part reads, its settings): it is stored
  with a generation, and another one today means a rebuild is due.
- `requires` names capabilities of the backend; a part the backend cannot build is skipped by a rebuild, and said.
- **What a part keeps with a generation** (optional, asked with `getattr`: the class and graph parts have none). A
  part may have `kept() -> str | None`: text that the rebuild just finished worked out over every item and that its
  refresh and overlay need (the name part's table of rarity, as JSON, `pangloss-names`). A part does not know its
  generation, and the switch comes after `rebuild` returns, so the rebuild asks for it once `rebuild(write)` has
  returned and stores it with the new generation **before the switch** (`store.keep(part, generation, text)`, a
  `PGVectorKept`); `store.kept(part)` gives that of the generation in use, None if there is none
  (`store.kept_in(tx, part, states)` in a transaction of the caller's). It is dropped with its generation. A
  rebuild that stops before its switch leaves the text in use as it was; what it kept is below the next rebuild's
  number (`next_generation` counts it), whose drop of the older generations removes it.
- **What a part says of an unknown** (optional too, asked with `getattr`: the time part has none; step 10.2b). A
  write plan may hold, where an entity would go, a stand-in that names the class it stands for
  (`hooks.StandIn.named_type`: review's `Unreconciled`). `unknowns_of(plan)` gives those nodes as `Unknown(id, type,
  label)`, in the order of the plan (a stand-in without `named_type`, criteria's `MatchesCriteria`, is none). A part
  may have `async unknown(plan, unknowns) -> {id: vector}`: the vector an entity of that class, with that label, put
  in the place of that node, would have once the plan was written and the part brought up to date; nothing is
  written. The class part gives the vector of the class (an abstract class its own); the name part that of the
  label, by the kept table, where `label` is a name of the class ([`names.md`](names.md)); the graph part lays the
  plan over the database with the node as an entity of the class, every node of the plan taken as published
  ([`fastrp.md`](fastrp.md)). `unknown_vectors(plan, unknowns)` asks every part that has it (by unknown, then by
  part; only unknowns of a class that has vectors; what a part raises is raised). Nothing in this package knows a
  stand-in's package: they are found through `pangloss_models.hooks`.

A **profile** is data: a weight for each part, by name.

```python
VECTORS_PROFILES = {"default": {"graph": 1, "class": 0.1}}
```

Without the setting, `"default"` is every registered part at its own `weight`. **A weight is the weight of a part's
cosine**: a profile's vector is its parts end to end, each at length one and scaled by the square root of its
weight, so that the cosine of two such vectors is the weighted mean of the cosines of their parts. A profile that
names a part that is not registered, a negative weight, or only zeros, is refused at `initialise()`.

### The suite of a part

Every part passes one suite, `pangloss_testing.parts.PartSuite` (step 8.4 of the plan); a part that has not called
it is not finished. Its author gives the apps and settings in the conftest of the part's `tests/live/`
(`parts.installed_apps("pangloss_names")`, `parts.settings_extras(...)`: the suite runs on
`pangloss_testing.similar_models`, which needs `pangloss_derived`, `pangloss_library` and `pangloss_criteria`), and
subclasses the suite in a test module, naming the part and its **slow way**, `async def slow(db_driver)`: the vectors
a whole rebuild would give now, by id.

```python
from pangloss_testing.parts import PartSuite

class TestTheGraphPart(PartSuite):
    parts = {"graph": lambda db_driver: fresh_oracle()}   # several parts may be checked together
    # tolerance = 1e-5; tolerances = {"class": 1e-8}; async def also(self, step, m, ids, database): ...
```

`dated = True` declares the models with dates (`similar_models.declare(dated=True)`: `Statement.when`,
`Person.born`, `InRole.during`, with `pangloss_dates` installed) and makes the payloads of every claim say dates (a
day, a year, a range, a period whose end is unknown, people born, a participant's period; `writes.dated`): the time
part's suite. Undated, the payloads are what they were.

What it claims, each a test of its own, against the slow way of every part named, to the tolerance:

- after each kind of write (a create; updates that add, drop and replace references and statements; an update of an
  entity that changes its label; a delete; a new citation; a criteria evaluation that changes candidates), the other
  workers and **one turn** of the worker, the stored vectors are the slow way's, **of exactly the same ids**; nothing
  the write took away keeps a vector of any part;
- the same after a delete and its undelete, a merge and its undo (the absorbed keeps no vector), a publish and an
  unpublish under both values of `VECTORS_GRAPH_SEES`;
- **an overlay equals the same payload written**: `overlay(plan)` of a `Create` (a factoid, a person) writes nothing
  and gives, for the ids it answers for, the vectors stored once that payload is written and the worker has turned;
  it answers for the head exactly when the head then has a vector;
- **an unknown's vector is the stored vector of an entity made in its place**: a factoid's payload that names a
  stand-in (`Mention` of `similar_models.declare(stand_in=True)`, registered for the test) beside Ada; `unknowns_of`
  of its plan gives it; each part's `unknown` writes nothing (nodes and edges counted); then a person made **with the
  unknown's id** and that label, the very `CreateDB` planned written with a reference to them in the stand-in's
  place (so every nested id is the plan's), and one turn: each part stores of the person what it said of the
  unknown, and a part that said nothing (the time part) stores none;
- **a rebuild under writes loses none**: the last part a rebuild builds held after it has computed, writes of every
  kind meanwhile, which the worker leaves; after it and one turn, the slow way's vectors.

`also` takes the claims a part has that are not every part's (the graph part's: Eve has a graph vector again after
the undo; an unpublished factoid is in the graph only under `"logged_in"`). Called by `pangloss-fastrp`'s
`test_fastrp_worker_live.py` (the graph part, with the class part beside it), `pangloss-vectors`'
`tests/live/suite/` (the class part alone) and `pangloss-names`' `test_names_part_live.py` (the name part, whose
slow way weighs by the table kept with the generation in use).

## What is stored

| Node | Is |
|---|---|
| `PGVector {of, part, type, generation, vector}` | One part of one item (`of` is its id); no vector index |
| `PGProfileVector:PGV_<profile>_<dimension>[:PGV_<profile>_<dimension>_<Group>…] {of, profile, type, generation, vector}` | The combined vector of an item for a profile, under the profile's label and one more for each group of its class; indexed by `pgv_<profile>_<dimension>` and `pgv_<profile>_<dimension>_<group>`, and by `of`, `generation` and `type` (the last for the exact scan of a class, migration `0002`) |
| `PGVectorState {part, generation, built_at, count, stale, signature, graph_sees}` | A part's state: the generation in use and what it was built with |
| `PGVectorProfile {profile, generation, signature, dimension, weights, built_at, count, removed}` | A profile's state. `weights` as JSON; `removed`, the vectors deleted in place since it was built (below) |
| `PGVectorKept {part, generation, text}` | What a part kept with a generation (`Part.kept`); indexed by `part` (migration `0003`) |
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

## Which classes have no vectors

✅ Built (step 7a.3 of [the build plan](similarity-build-plan.md), 2026-11-21). Three things say that the items of a
class have no vectors, two of which need the class's package to know nothing of `pangloss-vectors` (the user's
decision, 2026-11-21):

```python
# settings.py
VECTORS_EXCLUDE = ["Note"]               # these classes, and the classes below them
VECTORS_INCLUDE = ["Unreconciled"]       # a stand-in that has vectors all the same
```

- `VECTORS_EXCLUDE`: classes of documents or entities by name, of any package, with their subclasses.
- **The stand-ins**: the documents that stand in for an entity (`pangloss_models.hooks.stand_ins`; review's
  `Unreconciled`, a mention not yet identified, is the one today) have none, nor do the classes below them, unless
  `VECTORS_INCLUDE` names them (or a class above them). A stand-in that is a generic wrapper (criteria's
  `MatchesCriteria`) is no document and never an item: the rule is not for it.
- A class's own `VectorsMeta(include=…)`.

**The order** when they disagree (`meta.model_included`, which everything asks through `meta.included`): the first
that says it.

1. The class, or a class above it, is named in `VECTORS_EXCLUDE`: no vectors. The project's last word, over a
   class's own `VectorsMeta(include=True)` and over `VECTORS_INCLUDE` of a class below.
2. The class or a class above it sets `_vectors_meta` (the nearest): its `include`. A class's own
   `VectorsMeta(include=True)` wins over the stand-in rule.
3. The class is a stand-in's document, or below one: no vectors, unless it or a class above it is named in
   `VECTORS_INCLUDE`.
4. Otherwise it has vectors.

The two settings are checked at `initialise()` when the app is installed, with `VECTORS_PROFILES`: each is a list of
names (anything else is refused), and a name that is no model's, a class that is not one of documents or entities,
and a name in both are refused by name (`PanglossInitialisationError`).

**No vector, still joined.** Excluded means only that no vector is stored: the store leaves out the rows the parts
give of such an item, and deletes what it had. It does not take the class out of the joined graph (that is
`FastRPMeta(include=False)`, [FastRP](fastrp.md)): the graph part still walks through it, so a mention still joins
its testimony to what else the testimony names. And so **a head of an excluded class is still marked** for the
worker (a write of it can change the joins, and so the vectors, of what it names); the worker refreshes it as any
other, and the store drops its own row.

**What is excluded is part of what a rebuild depends on.** A part's vectors are stored and compared with
`store.part_signature(part)`: its own `signature()` while every class of documents and entities has vectors, and
otherwise `signature_of` it and the names of those that have none (`meta.excluded()`, whatever says so). A project
that leaves nothing out keeps its stored signatures; a class newly left out or let in (a change to either setting,
to a class's `VectorsMeta`, or review installed) makes a rebuild of every part due, and the rebuild removes the old
vectors or makes the new ones. Until it runs, nothing shows an excluded item: `nearest` leaves out a hit whose
class is among `meta.excluded()`, in its query (`search_query(…, excluding=True)`, and without that clause when
nothing is excluded). The similar route of an excluded item is `excluded`, as before.

## The settings

| Setting | Default | |
|---|---|---|
| `VECTORS_PROFILES` | every part at its own weight, as `"default"` | A weight for each part, by profile |
| `VECTORS_CLASS_DECAY` | 0.5 | What the class part gives each class above an item's (0 to 1) |
| `VECTORS_GRAPH_SEES` | `"everyone"` | What the graph a vector is computed from holds: what a reader who is not logged in sees, or (`"logged_in"`) everything not deleted. Stored with a part's generation; another value today is a rebuild due |
| `VECTORS_OVERFETCH` | 4 | A search asks the index for this many times the hits it wants |
| `VECTORS_EXACT_UP_TO` | 20,000 | A search of a profile with at most this many vectors in use reads them all and scores each, and does not ask the vector index ([Exact while it is small](#exact-while-it-is-small)); 0: always the index |
| `VECTORS_MIGRATIONS_APP` | the app with the most models | Whose migrations make the vector indexes of the profiles |
| `VECTORS_WORKER_IN_SERVER` | true | Whether the worker that keeps vectors current runs in the server (or apart: `pangloss vectors worker`) |
| `VECTORS_REBUILD_AFTER` | none | A number of stale vectors of a part past which the worker starts its rebuild |
| `VECTORS_EXCLUDE` | none | Classes of documents or entities, by name, whose items (and those of the classes below) have no vectors ([Which classes have no vectors](#which-classes-have-no-vectors)) |
| `VECTORS_INCLUDE` | none | Stand-ins (review's `Unreconciled`) that have vectors all the same |

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

### Exact while it is small

✅ (2026-11-22) A profile with at most `VECTORS_EXACT_UP_TO` vectors in use (20,000 by default) is **not asked
through its vector index**: the search reads its vectors and scores each by the dialect's cosine
(`search.scan_all_query` for the whole profile; a group or the classes asked for by `scan_query`, the scan of
"narrowed to classes" below), and gives the same hits at the same scores, cut to what the reader may see in the same
way. Above that size the index is asked, as the rest of this section says, unless the search says
`nearest(..., exact=True)` (step 10.2b): then the same exact scans whatever the size, so that items whose vectors
repeat are all found (people who share a name share a name vector: reconciliation finds its candidates so). The
route has no such parameter.

Why: **Memgraph's vector index does not find items whose vectors repeat**, and they repeat as a matter of course.
Three people named by one meeting and by nothing else have one graph vector; every item joined to nothing has the
vector of its class alone. Measured on Memgraph 3.14 alone, with no Pangloss in it
(`notes/similarity-evaluation/lost_in_index_sized.py`, 2026-11-22): of 2,000 nodes, half with one shared vector and
the rest in families of three with a vector each, the index gave a node among the 21 nearest *its own vector* 16
times in 300 written once, 43 written twice in place; with no shared vector at all, 31 and 66 in 300; an exact scan
300 in 300 every time. A small difference added to each stored vector did not mend it (between 22 and 247 in 300,
with no order in it), nor did deleting and making the node again in place of writing it in place. With vectors that
are all different (`lost_in_index.py`), about 3 in 100 were not found among 960. It was found from
`e2e/test_similar.py`, which failed now and then: a person's family, at similarity 1, was not among the hits of the
group's index for a whole minute, though the vectors were stored and labelled.

What it costs: the scan is linear, about 7 µs a vector on Memgraph and some tens of milliseconds whatever the size
(190 ms at 20,000 in the trial, against 1.4 ms through the index). **What is still open** (`TODO.md`): above the
size the index is asked and leaves out what it leaves out, and a project of several hundred thousand vectors chooses
between a search of seconds (a larger `VECTORS_EXACT_UP_TO`) and one that misses items whose vectors repeat; Neo4j's
index was not put to the same trial; the fault is not reported to Memgraph.

### Through the index

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

### Narrowed to several classes

✅ Built (step 7a.4 of [the build plan](similarity-build-plan.md), 2026-11-21).

```python
found = await nearest(str(person.id), types=["Group", "Person", "Saint"], k=10)
```

`types` are concrete classes of documents or entities, by name (the route works them out from `type` and `field`);
`group` and `types` together are refused. Filtering the whole index by class does not work: an item's nearest in
it are items of its own kind, so for a class that is a quarter of the database half of the true ten were found, and
asking for 65,536 mended neither (notes/similarity-evaluation/field_types_recall.txt, `:7690`, 328,929 vectors). So
there are two ways, chosen by `search.narrowed`, and their hits are merged by score (both are the cosine), each item
once, then by id, the first `k`:

- a **group** every class of which that has vectors is among those asked for is asked through its own index, as
  above (the fewest indexes: a group inside a chosen one is not asked as well);
- every other class asked for is found by an **exact scan** (`search.scan_query`): its profile vectors of the
  generation in use, found by the index on `PGProfileVector(type)` (this package's migration `0002`), each scored by
  `Dialect.vector_cosine` against the query vector, the best `fetch`, then matched to their items and cut to what the
  reader may see as the index's search is. Memgraph plans it by that index only if the other conditions come after a
  `WITH` (with them in the `MATCH`'s `WHERE` it reads the whole generation once for each class); Neo4j seeks the
  index for each class too, but only once the database has vectors enough for its planner to choose by (on a nearly
  empty one it scans the whole index): `test_the_scan_finds_the_vectors_of_each_class_by_the_index_on_their_type`
  plants 8,000. Being exact, it is asked again while short only for what the reader may not see, and not once it has
  had every vector of its classes (a count, asked when it is first short).

The scan is **linear in the vectors of its classes**: on Memgraph about 6.5 µs a vector (1,792 in 13 ms, 14,686 in
95 ms, 82,355 in 0.53 s; three classes, 157,035 vectors, 1.06 s; `:7690`, 2026-11-21). **A large class that is
searched often should be a group.** A class without vectors among those asked for is never found, and is not needed
for its group to be chosen.

### Classes by use

✅ Built (step 7a.5 of [the build plan](similarity-build-plan.md), 2026-11-21; `by_use.py`). A class can leave some of
its labels to the data (`__labels_unmanaged__`: a typology's type that is `also` another class, `TypologyMeta(name=
"RoleType", also=Role)`, is a `RoleType` below `Role`, and has the label `Role` only while its switch `is_concrete`
is on). Such a class is its own class, and every class above it, **by class**, except those whose names are among its
unmanaged labels (`Role`, and what is above `Role`): those it is only **by use**. The user's rule (2026-11-21): a
type has its vectors like any item, is found as a `RoleType`, is listed by a search that is not narrowed, and can be
searched from; but it is **given as a `Role` only where the data uses it as one**: something names it where a `Role`
goes. Its class, and the label `Role`, are not enough.

- **When.** A search narrowed by names (one `type`, several, a `field`'s classes, a `group`). A concrete class among
  those searched is *asked as itself* if a name asked is the class or one above it that it is by class
  (`type=RoleType`, or `type=Role&type=RoleType`: every type), or a field that can hold it and no class it is by use
  (one that takes a `RoleType`); otherwise (`type=Role`, `group="Role"`, a field that holds roles) a hit of it is a
  result only if a counting relation points at it. `nearest(asked=…)` is given the names as the route had them
  (`types` alone cannot tell `type=Role` from `type=Role&type=RoleType`); without it, the group or the `types`.
- **Which relations count.** A relation field of any model (a document, an entity, a wrapper, an embedded object)
  that reaches, directly or through wrappers, a class the item is by use. Having it as a type (`has_type`) and the
  hierarchy (`is_subtype_of`) are relations to a `RoleType`, and do not count. Worked out once from the models
  (`by_use.rules()`, after `initialise()`, forgotten at a reset) as pairs `(the stored type of the node the edge comes
  from, the edge's name)`: the edge of a wrapper onto its entity is the wrapper's (`target`), from its node, which is
  stored as the wrapper's class (`InRole`, not `InRole[Role]`). Two uses of one generic wrapper, one for the class by
  use and one for the class itself, give the same pair, which then counts, with a warning at the first search that
  needs the rules (a typology's type cannot be in a wrapper: a relation to it must be called `has_type`).
- **What the referrer must be.** By its forward edge (not the reverse edge, not a derived shortcut, not a relation
  the server computes), from a node the reader may look through by its head as the item is (`fragments.listed`: a
  deleted document no longer counts, an unpublished one only with `see_unpublished`), not the item itself, and not
  of a class whose references do not count (a derived document).
- **The query.** In the end of the search (`search._hits`, so the index's search and the scan alike), for an item
  whose class is among `$by_use_types` only, a `CALL (item) { … RETURN count(user) AS uses }` with the pairs as a
  parameter (`$by_use`), as `fragments.uses_of` counts, which both backends run. The clause is in the query only
  when the request has such a class; otherwise the text is what it was.
- **Nothing is stored.** The vectors, the groups and their labels (a `RoleType` still has the group label `Role`
  when `Role` is a group), the worker, the rebuild, the status and the answer's `groups` are as they were; a use
  written or deleted counts at the next search, with no turn of the worker. Unused types hold places among the
  nearest of a group's index; the search asks again while short.

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
| A part | It was never built; its signature (`store.part_signature`: its `signature()` and the classes that have no vectors) is not the one it was built with (the models it reads, a setting it depends on, or which classes have no vectors changed: `VECTORS_CLASS_DECAY` for the class part, `VECTORS_EXCLUDE` for every part); `VECTORS_GRAPH_SEES` is not what it was built with (said of every part, the class part too, though it reads nothing the setting changes) |
| A profile | It was never built; its weights are not those it was built with; its parts now make another dimension (its vector indexes are new ones: a migration is pending, which `pangloss showmigrations` reports, and the rebuild follows it); a part it weighs is due |

A part the backend cannot build is said to be unavailable, and is never due.

## The API

| Route | Gives |
|---|---|
| `GET /api/NAME/{id}/similar?profile=&type=&field=&limit=` | `{"status": "ok" \| "pending" \| "rebuild_due" \| "excluded", "results": [...], "profiles": [...], "groups": [...]}`: each result the reference view of an item, as a list gives it (camelCase, `meta` and all, read for all the hits in one query), with `similarity`, nearest first, and none of a similarity of 0 or less (below 0.005, which would be written 0.00: such an item has nothing in common with the one asked about; the user, 2026-11-21); `profiles` the names of the profiles (`default` first, then the others in order) and `groups` those a search can be narrowed to, so that the interface needs no second request for its menus |
| `GET /api/vectors/status` | (logged in) The status, as above: `{rebuildDue, rebuilding, parts: [...], profiles: [...]}`; `rebuilding` is `null`, or `{by, since}` of the lease of a rebuild running now (one that has not run out), whoever started it: read with the states, in the same transaction. `pangloss vectors status` says it too |

`NAME` is any document or entity class, the item's own or one above it; another is a 404. The item may be a document
nested in another (a statement in a factoid), and so may the results. What the reader may see is as for
`GET /api/NAME/{id}`, a nested document's by its head: an item that is not there, is deleted, or is unpublished to a
reader who is not logged in is a 404, and such items are never among the results. A nested document's reference view
is the one the core's search gives a nested node (`pangloss_cypher.list_query`): `meta.isHeadNode` false,
`meta.headNodeId` and `meta.headNodeType` of its head, and the head's creators, `published` and `reviewStatus`; a
head's has `isHeadNode` true and no `headNodeId`. `profile` defaults to `default` (an unknown one is a 422);
`type` is any class of documents or entities, meaning its concrete classes (it and those below it that are not
abstract; a trait, the classes that have it), and may be given more than once (`?type=Person&type=Group`); `field`
is `Model.field` (`Activity.carried_out_by`, or `carriedOutBy`), meaning the concrete entity classes that relation
can hold: through wrappers (`InRole[Agent]`, a wrapper in a wrapper), not the stand-ins (review's `Unreconciled`),
as the reverse fields of an entity are worked out (`entities_reached`; `pangloss_vectors.fields`); with both, the
classes of either. One `type` that is a group, and no `field`, is searched through the group's index as it always
was; anything else as [Narrowed to several classes](#narrowed-to-several-classes) says. A name that is no class of
documents or entities (or one with no concrete class), and a field that is no model's, no field of it, not a
relation, or a relation that reaches no entity, is a 422 that names it. `groups` in the answer is unchanged: what the
interface offers, which is still one group. `limit` is 1 to 100 (10). `rebuild_due` is also said with results when
the profile's status is due for any other reason: they are the results of the vectors in use. `excluded`: the item's
own class (its `type`, not the `NAME` asked at) has no vectors ([Which classes have no vectors](#which-classes-have-no-vectors)),
and never will; it is decided before any search, and `results` is empty. An item of such a class is never among the
results, though its vectors are stored until the rebuild that the change makes due.

`{id}` is what `GET /api/NAME/{id}` takes (step 7a.2 of the build plan): the item's UUID, or, of an entity, one of
its URLs (`create_with_id`), as the rest of the path, `http:/` read as `http://`, the query string being the URL's
but for the route's own `profile`, `type`, `field` and `limit` (`GET /api/Person/http://x.org/p/similar?id=7&limit=3` asks
for `http://x.org/p?id=7`; `pangloss_api.routes.models.reference_from`). It is resolved in the read transaction
that checks what the reader may see (`pangloss_cypher.lookup.resolve_id`); the URL of an entity merged into another
is the survivor's (a merge moves the URLs), so it answers for the survivor. A document is found by its UUID only: a
URL at a document class is a 422. A URL no entity has is a 404. The path is matched to its last `/similar`, so an
entity whose own URL ends in `/similar` can no longer be read at `GET /api/NAME/{that URL}` (the similar route takes
the request, for the URL without the `/similar`, and its 404 says so): it is read by its UUID, and its similar are at
`…/similar/similar`. The route matches only where `NAME` is a model's, so that a route of another app ending in
`/similar` (`/api/review/unreconciled/{id}/similar`) is still reached whatever the order of `INSTALLED_APPS`; another
`NAME` is the router's plain 404.

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

**Labels and filters of another module** ✅ (step 7.6 of [the spaces plan](spaces-and-comparison-plan.md#phase-7-the-interface)):
the list is named `"similar"`, and a module that labels it through core's `listLabels` (`pangloss-compare`, each
statement's relation to the page's: [compare.md](compare.md#similar-labelled-by-relation-)) is drawn only in the
browser, after the list, each in a boundary of its own made anew for each item (one that fails is said in the
browser's console, "A list labeller of an interface module (app:key) failed", leaves the list as it is, and is tried
again on the next item's page), and given the items listed; what it tells (`ListedLabels`) puts a label at the end of
each row it names (a last column that takes what room is left: a label is cut where the room ends, one line, and
squeezes no chip) and its filters at the left of the head's row (checkboxes on one line, scrolling sideways on a
narrow page; keyed `app:key:filter`, so that two modules' filters of one name are both offered), which filter what
is listed, nothing asked again, and are put off on another item's page. Where such a module applies to the item's
class (asked as the page is drawn), that column and the head's row (26px, as a small menu) are there from the start,
so that what arrives moves no row, chip, bar or figure; **the price**: where it applies but says nothing (the list
holds no statement it labels; its route has no comparison of the item), the row is there empty and the column
empty. Where none applies, the section is as without it, its classes the same. A read is shown only while it is of
the section's own item (`ListedLabels.of`): a link to another item's page gives the section new props, not a new
instance. The package imports no other module; with none installed nothing changes.

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

## The graph part

```python
INSTALLED_APPS = [..., "pangloss_vectors", "pangloss_fastrp"]
```

`pangloss-fastrp` registers the part `"graph"`, at weight 1, so with it installed the default profile is the graph
at 1 and the class at 0.1. Its vector of an item is made by FastRP from what the item is **joined** to: documents and
entities, nested documents too, with the wrappers between them passed through, shares counted at their share,
citations joining the citing document to what it cites, and what is deleted, merged, derived or (by
`VECTORS_GRAPH_SEES`) unpublished left out. A class says how it counts with `_fastrp_meta = FastRPMeta(weight=,
weights=, stop=, own=, include=)`; the settings are `FASTRP_STEPS`, `FASTRP_DIMENSION` and `FASTRP_REFRESH_CAP`.

It registers a second part too, `"actual"`, at weight 0: the actual network, in which a document joins by what the
walk says of it (`FASTRP_DEGREE_WEIGHTS`). It writes nothing, and its refresh does nothing, until a profile weighs it
(`VECTORS_PROFILES = {"who_met": {"actual": 1, "class": 0.1}}`); then it costs what the graph part costs.

The joined graph in full, the options, the settings, rebuild, refresh and overlay, the approximate vectors past the
cap, and what was measured are on [its own page](fastrp.md).

## The name part

```python
INSTALLED_APPS = [..., "pangloss_vectors", "pangloss_names"]
VECTORS_PROFILES = {"who": {"name": 1, "graph": 0.25}}
```

`pangloss-names` registers the part `"name"`, at weight 0: installing it changes no profile, and it counts only in a
profile that weighs it (with only `"who"` given, `"default"` stays the other parts at their weights). Its vector of an
item is made from the item's names (an entity's label, unless a class says other fields with `_names_meta =
NamesMeta(fields=, include=)`): the trigrams of their words, a table of variants applied first (`NAMES_VARIANTS`),
weighted by how rare each word is and hashed to `NAMES_DIMENSION` (256). The table of rarity is made at a rebuild and
kept with the generation (`kept()`, above), and a refresh weighs by it. A search by a name is
`nearest(vector={"name": ...})` (`pangloss_names.search`, `pangloss names search`); a hit's score is then not the
cosine of the names but that times `sqrt(w_name / Σ w of the parts the hit has)`.

The maths, the settings, the table of variants, rarity, the search and what was measured are on
[its own page](names.md).

## The time part

```python
INSTALLED_APPS = [..., "pangloss_dates", "pangloss_vectors", "pangloss_dates_vectors"]
VECTORS_PROFILES = {"when": {"graph": 1, "class": 0.1, "time": 0.5}}
```

`pangloss-dates-vectors` registers the part `"time"`, at weight 0, as the name part. Its vector of an item is made
from the item's dates (`pangloss-dates`): each date's four bounds a soft bump along the years, read at
`DATES_VECTOR_DIMENSION` (128) places `DATES_VECTOR_WIDTH` (2) years apart that the years go round. A date counts for
the document or entity that holds it and for the head it is under. Nothing is kept with a generation, and a refresh is
exact. A profile with time finds the other reports of an event, and tells apart the years of one that recurs. The
maths, whose vector a date is, the settings and what was measured are on [its own page](dates-vectors.md).

## Keeping vectors current

✅ Built (phase 5 of [the build plan](similarity-build-plan.md)). After a write, a worker in the background brings
the vectors of what changed up to date; no rebuild is needed for ordinary editing.

**What marks work.** A write of a document or entity leaves a mark in its own transaction (of a class that has no
vectors too, since 7a.3: it can change the vectors of what it names, and the store leaves out its own row) (`pangloss_cypher.pending`, kind `vectors`), when `pangloss_vectors` is an installed app: a create, an
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
   joins, with three steps), from the graph five joins out ([FastRP](fastrp.md#rebuild-refresh-and-overlay));
4. deletes every vector of what is gone: the heads removed, the documents nested in them, and what the mark kept of
   before that no longer exists;
5. completes the claims. On a failure they are given back and tried again.

A part that has never been built is skipped: the first vectors come from a rebuild.

**The worker and a rebuild never overlap.** A batch is claimed only if no rebuild holds its lease, and a rebuild
waits for the batch in hand. Marks made while a rebuild runs wait, and are worked after it against the new vectors.

**Past the cap.** A change near a hub (a source cited by thousands of documents) would have the graph part read
much of the database. A batch past `FASTRP_REFRESH_CAP` nodes (50,000) is refreshed in halves, down to one head,
exactly; only for a head past the cap alone does it write a vector taken from the stored vectors of what its
documents are joined to (`approximate.py`: the first step is exact, the later ones approximate; a cosine of about 0.9
with the exact vector on planted hubs: [FastRP](fastrp.md#past-the-cap-groups-then-approximate-vectors)), and count
those as stale in the part's state. A rebuild sets the count to zero; with `VECTORS_REBUILD_AFTER` the worker starts one when the count passes
it. There is no rebuild at a set hour (`VECTORS_REBUILD_AT` is not built: nothing to hang a schedule on).

**On Neo4j** each query of a refresh reads what is committed when it runs, so a write made during a refresh can be
seen in part; its own mark brings the next turn. On Memgraph a refresh reads one snapshot.

**Measured** (2026-11-21, Memgraph, the scratch database of 1.9 million nodes; [FastRP](fastrp.md#measured) has the
figures): the mark adds nothing that shows to a small write (12.6 ms against 12.2 ms at the median); one turn of
the worker for one factoid is 1.2 s at the median. **A burst of writes is past the cap together**: with four writers
a write waited 18.5 s at the median for its vectors, all of them approximate until a rebuild. Such a batch is now
refreshed in groups (step 7a.1; not yet measured).

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
