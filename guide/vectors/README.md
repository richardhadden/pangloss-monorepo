# Similar items: "items like this one"

With two optional apps, every document and entity gets a **vector**, a list of numbers made from what kind of thing
it is and from what it is connected to. Two items whose vectors point the same way are alike. Pangloss uses that to
show, on every item's page, the items most like it ("Similar"), and gives the same list over the API.

- `pangloss-vectors` stores the vectors, searches them, keeps them current, and draws the section. Its own **part**
  of each vector is the class: a painting's creation is like an artwork's creation, then like other creations.
- `pangloss-fastrp` adds the part that matters most, the **graph**: two people named in the same factoids, with the
  same people, at the same places, are alike.
- `pangloss-names` adds a third, the **name**, and a search by a name: [Finding people by name](names.md).
- `pangloss-dates-vectors` adds a fourth, **time**, from the dates: [Finding the other reports of an event](time.md).

The reference is [vectors](../../implementation_docs/vectors.md) and [FastRP](../../implementation_docs/fastrp.md).
Both work on Memgraph and on Neo4j.

## 1. Install them

```python
INSTALLED_APPS = [
    "pangloss_memgraph",
    ...
    "pangloss_vectors",
    "pangloss_fastrp",   # the graph part; without it, similar by class alone
    "my_app",
    "pangloss_interface",
    "pangloss_admin",    # (for the Rebuild button on /admin)
]
```

`pangloss-fastrp` needs numpy and scipy in the server's environment (they are its dependencies).

## 2. Declare what is searched, and how things count

Nothing has to be declared: with the two apps installed, every document and entity class has vectors (but review's
mentions not yet identified, below). Three things make the results better, and the settings can leave classes out.

**Groups.** A class that says `searchable=True` is a group: its page's "Similar" can be narrowed to it ("people like
this one"), and it gets a vector index of its own. Its subclasses are in its group.

```python
from pangloss_vectors import VectorsMeta


class Person(Entity):
    _vectors_meta = VectorsMeta(searchable=True)


class Statement(Document):            # every kind of statement, in one group
    _vectors_meta = VectorsMeta(searchable=True)


class Note(Document):
    _vectors_meta = VectorsMeta(include=False)    # no vectors at all: never found, never searched from
```

**No vectors for a package's class.** `include=False` is said in the class. For a class you did not write (another
package's), or to say it in one place, the settings do it, by name, for the class and the classes below it:

```python
# settings.py
VECTORS_EXCLUDE = ["Note", "Memo"]       # no vectors, whatever the class says
VECTORS_INCLUDE = ["Unreconciled"]       # review's mentions, which have none unless you say so
```

The documents that stand in for an entity (review's `Unreconciled`, someone a source names who has not been
identified) have no vectors unless `VECTORS_INCLUDE` names them. A class with no vectors is never found and never
searched from, but it still joins what it names in the graph. A name that is not a class of documents or entities,
or a name in both lists, is refused at `initialise()`. Changing either list makes a rebuild due
(`pangloss vectors status`); until it runs, the items left out are already missing from the results. The order when
the settings and a class disagree is in [Vectors](../../implementation_docs/vectors.md#which-classes-have-no-vectors).

**A trait that is a class.** A plain `Trait` is a mixin (`Dateable`). If yours means something ("an agent: a person or
a group"), make it a `SemanticTrait`: the class part then counts it as a class above the classes that have it, so a
person and a group are nearer each other than either is to a place. It is stored exactly as a `Trait`: changing one
to the other is no change to the data.

```python
from pangloss_models import SemanticTrait


class Agent(SemanticTrait):
    """Anyone who can act: a person or a group"""
```

**How a class counts in the graph.** `FastRPMeta` says it, for a class and the classes below it:

```python
from pangloss_fastrp import FastRPMeta


class Negative[T](SemanticSpace[T]):
    # (what is said not to be so does not join its statement to the people in it)
    _fastrp_meta = FastRPMeta(stop=True)


class Mention(Statement):
    _fastrp_meta = FastRPMeta(weight=0.2, weights={"bystanders": 0.5})   # counts for less; its bystanders less still


class Source(Entity):
    # (a source cited by thousands of documents would make them all alike, and every save near it slow)
    _fastrp_meta = FastRPMeta(include=False)
```

`weight` and `weights` (for each field) are numbers of 0 or more; `stop` and `own` are for wrapper classes (reified
relations, semantic spaces, conjunctions, embedded objects); `include` for documents and entities. What each does, and
how the graph is made from your documents, is in [FastRP](../../implementation_docs/fastrp.md#fastrpmeta).
`initialise()` (and `pangloss check`) refuses what one of them cannot mean, by the class's name.

The demo (`pangloss-demo/demo_app/models.py`) does all three: `Person` and `Statement` are groups, `Agent` is a
`SemanticTrait`, `Negative` says `stop=True`.

## 3. Migrate, then build the vectors

The vector indexes follow your models, so they are a migration of your app:

```sh
pangloss makemigrations
pangloss migrate
```

For the demo, `makemigrations` wrote:

```
demo_app.0024_addindex_addindex_addindex
    - Create the vector index pgv_default_165 on :PGV_default_165(vector) (dimension 165, metric cos)
    - Create the vector index pgv_default_165_person on :PGV_default_165_Person(vector) (dimension 165, metric cos)
    - Create the vector index pgv_default_165_statement on :PGV_default_165_Statement(vector) (dimension 165, metric cos)
```

One index for each profile (here only `default`), and one for each profile and group. The number in the names is the
length of the vectors: 128 of the graph part, and one for each class and semantic trait. So **a class added or taken
away later is a migration** of these indexes too.

Then make the vectors, once:

```sh
pangloss vectors rebuild
pangloss vectors status        # what is built, and whether a rebuild is due, and why
```

Until then every item's "Similar" says "Not worked out yet". A rebuild writes the new vectors beside those in use and
then switches to them, so searches go on meanwhile; only one runs at a time.

## 4. What it looks like

**"Similar"** is a section after the contents of every item's page, a nested document's too (a statement in a
factoid): up to ten items, nearest first, each a chip with a bar and the similarity (1 is the same). The menus under
it narrow it to a group ("All types", or `Person`, …) and, if there is more than one, choose a profile (below). A
reader who is not logged in never sees there what they could not open.

**On `/admin`** (with `pangloss_admin`), the part "Similarity": each part and profile, when it was built, how many
vectors, how many are stale, whether a rebuild is due and why, and **Rebuild**, which runs the rebuild as a job. The
figures follow the rebuild while it runs, whoever started it.

## 5. Profiles: weighing the parts

A profile says how much each part counts. Without the setting there is one, `default`: the graph at 1 and the class
at 0.1. A weight is the weight of that part's similarity in the result: with `graph: 1, class: 0.1` the similarity of
two items is the mean of their graph similarity and their class similarity, the graph counted ten times as much.

**Worked example.** Some readers want "things of the same kind", whatever they are connected to. Add a profile:

```python
# settings.py
VECTORS_PROFILES = {
    "default": {"graph": 1, "class": 0.1},
    "kind": {"class": 1},
}
```

A profile has vector indexes of its own, so:

```sh
pangloss makemigrations        # the indexes of "kind": one, and one for each group
pangloss migrate
pangloss vectors rebuild       # every part made again, and the vectors of each profile
```

`pangloss vectors weights` lists the profiles and their weights (it reads no database). The section now has a menu of
the profile, `default` first; over the API, `?profile=kind`. A profile's name is a word of letters, digits and
underscores; a profile that names a part that is not installed, a weight below 0, or only zeros, is refused when the
models are initialised.

Changing a profile's weights makes a rebuild due (`pangloss vectors status` says so); `pangloss vectors rebuild` makes
the profile again.

## 6. Keeping the vectors current

After that first rebuild you do nothing for ordinary editing. Every save, delete, undelete, publish, restore or merge
of a document or entity leaves a mark, and a **worker** in the server brings the vectors of what changed up to date
(exactly: as a rebuild would make them). An item just saved shows its old similar items, or "Not worked out yet",
until the worker's next turn.

To run the worker in a process of its own instead of in the server:

```python
VECTORS_WORKER_IN_SERVER = False
```

```sh
pangloss vectors worker            # until stopped; --batch N: how many items it takes at once (200)
```

**A rebuild is needed** when the worker cannot see what changed:

- after a **bulk load** (`pangloss memgraph bulk-load`, `pangloss neo4j bulk-load`): it leaves no marks;
- after a **migration**: it leaves no marks, and a changed class changes the class part;
- after a **changed setting** a part depends on (`FASTRP_STEPS`, `FASTRP_DIMENSION`, `VECTORS_CLASS_DECAY`,
  `VECTORS_GRAPH_SEES`, a `FastRPMeta`): `pangloss vectors status` then says "rebuild due" and why, and so does
  `/admin`. Until the rebuild the old vectors are used.

`pangloss check` does not say a rebuild is due (it reads no database): use `pangloss vectors status`.

**Hubs.** A save near something joined to tens of thousands of items (a much-cited source) would have the worker
read much of the database. Past `FASTRP_REFRESH_CAP` nodes (50,000) it writes approximate vectors for that save
instead, close to the exact ones, and counts them as **stale**. A rebuild makes them exact again. To have the worker start a rebuild
when there are too many:

```python
VECTORS_REBUILD_AFTER = 5_000      # stale vectors of a part
```

A burst of many writes at once (a pipeline) that passes the cap together is refreshed in smaller groups, exactly:
only a save past the cap by itself is approximate. Run `pangloss vectors rebuild` after a large import. Leaving a hub class out of the graph
(`FastRPMeta(include=False)`) or giving it a low weight keeps saves near it exact.

## 7. What the graph sees: `VECTORS_GRAPH_SEES`

What may shape the vectors that every reader's search uses:

| Value | The graph holds |
|---|---|
| `"everyone"` (the default) | Only what a reader who is not logged in may see: no unpublished documents (`pangloss-review`), no candidates seen only by logged-in readers |
| `"logged_in"` | Everything that is not deleted, as soon as it is written |

Results are always cut to what the reader may see. With `"logged_in"` what they cannot see has still shaped the
vectors; with `"everyone"` a document of a reviewed class adds nothing to the graph until it is published (it still
has its class vector). A project whose data is mostly unpublished, or that wants similarity over new data at once,
sets `"logged_in"`. Changing it makes a rebuild due.

## 8. From a script or another program

```sh
# (the person's UUID, or, as GET /api/Person/{id} takes it, one of its URLs)
curl "http://127.0.0.1:8000/api/Person/$PERSON_ID/similar?type=Person&limit=5"
curl "http://127.0.0.1:8000/api/Person/https://example.org/people/42/similar?limit=5"
# (people and groups, nearest first: two types, or the field whose candidates they are)
curl "http://127.0.0.1:8000/api/Person/$PERSON_ID/similar?type=Person&type=Group"
curl "http://127.0.0.1:8000/api/Person/$PERSON_ID/similar?field=Activity.carried_out_by"
```

```json
{
  "status": "ok",
  "results": [{"type": "Person", "id": "…", "label": "…", "meta": {…}, "similarity": 0.83}, …],
  "profiles": ["default"],
  "groups": ["Person", "Statement"]
}
```

`GET /api/NAME/{id}/similar` takes `profile` (`default`), `type`, `field` and `limit` (1 to 100; 10). `type` is any
class of documents or entities, with the classes below it, and may be given more than once; `field` is a relation
of a model, `Model.field`, and narrows to the entity classes it can hold (through `InRole[...]` and the like; not
review's mentions); with both, to either. A name that is no class, or a field that is not a relation to entities, is
a 422 that says so. A group is searched through its own index; a class in no group by reading all of its vectors,
which takes about half a second for 80,000 of them: **a large class that is searched for often should be a group**
(`searchable=True`). Each result is
the item's reference view, as a list gives it, with its `similarity`; nothing below 0.005 is given. `status` is `ok`;
`pending` (the item has no vector yet, or the profile was never built); `rebuild_due` (a rebuild is due: the results
are of the vectors in use, or none if their length is not today's); or `excluded` (its class says
`include=False`). What the reader may not see is a 404, and never among the results.

**A project with a typology that is `also` another class** (`TypologyMeta(name="RoleType", also=Role)`): its types
have vectors like any item, are found by `type=RoleType` and by a search that is not narrowed, and have their own
"Similar". Narrowed to the other class (`type=Role`, the group `Role`, or a field that holds roles), a type is given
only where something uses it as a role: a relation that takes a `Role` names it, directly or through a wrapper
(`InRole[Role]`), from something the reader may see. A type that is only *had as a type* (`has_type`), or only
switched on, is not; `type=Role&type=RoleType` gives every type. A use written or deleted counts at once (nothing is
stored for it): [vectors, "Classes by use"](../../implementation_docs/vectors.md#classes-by-use).

`{id}` is the item's UUID or, for an entity, one of its URLs, as at `GET /api/NAME/{id}`; the query string after
`/similar` belongs to the URL, except `profile`, `type`, `field` and `limit` (`…/Person/http://x.org/p/similar?id=7&limit=3`
asks for `http://x.org/p?id=7`). A document is asked for by its UUID only. One thing to know: an entity whose own URL
ends in `/similar` can no longer be read at `GET /api/NAME/{that URL}`, which this route takes; read it by its UUID
(its similar are at `…/similar/similar`).

`GET /api/vectors/status` (logged in) gives what `pangloss vectors status` says, as JSON, and `rebuilding` while a
rebuild runs.

In Python, on the server's side:

```python
from pangloss_vectors import nearest

found = await nearest(str(person.id), group="Person", k=10)
found = await nearest(str(person.id), types=["Person", "Saint", "Group"], k=10)   # concrete classes, by name
found.status        # "ok", "pending", "rebuild_due"
found.hits          # [Hit(id, type, score), ...], nearest first
```

## 9. A large database: `VECTORS_EXACT_UP_TO`

While a profile has at most 20,000 vectors, a search reads them all and is exact: nothing that should be found is
left out. Above that it asks the database's vector index, which is fast (a millisecond or two) and, on Memgraph,
does not find items whose vectors are the same as others' (people known only from one meeting; items connected to
nothing). The exact search takes about 7 microseconds a vector on Memgraph: 0.2 s at 20,000, some 2 s at 300,000.

```python
# settings.py
VECTORS_EXACT_UP_TO = 100_000      # exact up to here; 0: always the index
```

The measurements are in [Vectors](../../implementation_docs/vectors.md#exact-while-it-is-small).

## Not yet

- `Person.similar()` and the SDK: use the route.
- A rebuild at a time of day (`VECTORS_REBUILD_AT` is not built); `pangloss check` saying a rebuild is due.
- The graph part inside Memgraph, as a query module (deferred).
- Still to be decided: the default number of FastRP steps; whether vocabularies and typologies are in the graph;
  refreshing a burst of writes in smaller groups. See [FastRP](../../implementation_docs/fastrp.md#open-for-the-user-to-decide).
