# Names: the name part of similarity ✅

`pangloss-names`: the part `"name"` of [`pangloss-vectors`](vectors.md), a vector of each item from its **names**,
so that two spellings of a name, and a name and its variants, are near each other. Built as phase 8 of [the build
plan](similarity-build-plan.md) (2026-11-21 and 22), on both backends; the plan's "As built" sections of 8.1 to 8.6
say where the code differs from the steps. How to use it is [the guide](../guide/vectors/names.md).

```python
# settings.py
INSTALLED_APPS = [..., "pangloss_vectors", "pangloss_names"]
VECTORS_PROFILES = {"who": {"name": 1, "graph": 0.25}}     # the part counts only in a profile that weighs it
```

Needs `pangloss_vectors`, and a backend with Cypher and a vector index (`requires = {"cypher", "vector_index"}`:
Memgraph and Neo4j). Depends on numpy, imported only when a vector is made (not by a client of the SDK that imports
the models).

## Contents

- What is built, and what is not
- What the name part is for
- The maths
- `NamesMeta`
- The settings
- The table of variants
- Rarity, and what a refresh weighs by
- Rebuild, refresh and overlay
- Search by a name
- In the demo
- Measured
- As built: where the code differs from the plan
- The code

## What is built, and what is not

| | What |
|---|---|
| ✅ | The maths with no database in it (`maths.py`, step 8.2): words folded and cut, the table of variants, trigrams, rarity by the word, hashed to a fixed dimension |
| ✅ | Which classes have names and which fields are names (`NamesMeta`, `meta.py`, step 8.3), checked at `initialise()` |
| ✅ | The part `"name"` (`part.py`, step 8.3): rebuild, refresh and overlay; at weight 0; the table of rarity kept with the generation (`Part.kept`) |
| ✅ | The suite every part passes (`pangloss_testing.parts.PartSuite`, step 8.4), on both backends (`tests/live/test_names_part_live.py`) |
| ✅ | The table of variants as a setting (`NAMES_VARIANTS`, step 8.5): a CSV file, checked at `initialise()` by the line, in the signature by its content |
| ✅ | Search by a name (step 8.6): `pangloss_names.vector_of`, `pangloss_names.search`, `pangloss names search` |
| ✅ | The demo: the profile `who` (name 1, graph 0.25) and a table of given-name variants (step 8.7) |
| ✅ | Measured on the planted world at 32,137 people: by name alone, with and without the table, and with the graph (steps 8.1 and 8.2, through the maths) |
| ✅ | Measured through the part at size, on both backends (step 8.6): below, "8.6 measured" |
| ⏳ | A typology as a table of variants: what it would mean (a type's subtypes as its variants?) is the user's to say when it is wanted (the plan, 8.5) |
| ⏳ | A route for a search by a name: phase 10's (`pangloss-reconcile`) is the one a client will ask |
| ⏳ | Anything in the interface ("did you mean…?" as a person is made: phase 10 and after) |

## What the name part is for

**Finding candidates, not comparing.** Given a name ("Guido of Spoleto"), the name part finds the items whose names
are near it: other spellings, the same name with the given name in another form, namesakes. It does not say whether
two names are the same person's; review's `likeness` compares two labels exactly, and stays what it is. A part's
vector goes into a profile with other parts (the graph's, which says whose company an item keeps), and a search by a
profile weighs them together (below, "Measured": a little graph helps much).

## The maths

`maths.py` is the whole of the computing, with no database in it: a name to a vector.

```
name ──fold──▶ words ──canonical──▶ words ──weighted (rarity, trigrams)──▶ weights ──hashed──▶ vector
```

- **Folded**: lower case, accents folded (`pangloss_models.fold`, as labels are searched), and cut into words at
  whatever is neither a letter nor a digit. The words are a bag: "Smith, John" and "John Smith" are the same name.
- **Canonical**: a word the table of variants knows (`Hans`) is replaced by its canonical form (`johannes`).
- **Trigrams**: each word between a start and an end mark, cut into threes (`^jo`, `joh`, `ohn`, `hn$`), so that two
  spellings of a name share most of theirs.
- **Weighted by rarity, by the word**: every trigram of a word weighs `1 + ln((names + 1) / (having + 1))`, where
  `names` is how many items had names when the table was made and `having` how many of them had the word. A surname
  few have counts for more than a given name many have; a word the table never saw (or one item had) weighs the most.
- **Hashed** to `NAMES_DIMENSION` places, each trigram to one place with a sign (the hashing trick), by blake2b, so
  the same in every process (never `hash()`); then made of length one.

The cosine of two such vectors is high for a name and its other spellings and variants, and near nothing for two
different names. An item's names (its label, and any other name fields) are one bag of words: several names make one
vector. A text with no letter or digit has no vector.

What the part finds is **one change of spelling, or a variant the table knows**. Short names with two letters changed
share few trigrams: in a world of five people "Jon Smyth" is nearer "Joan Smithers" than "John Smith" (0.27 against
0.50; the plan, 8.5 and 8.6 "As built").

## `NamesMeta`

```python
from pangloss_names import NamesMeta


class Person(Entity):
    aliases: list[str] = []
    _names_meta = NamesMeta(fields=["label", "aliases"])     # each alias one more name

class Letter(Document):
    _names_meta = NamesMeta(include=True)                    # its label is a name

class Place(Entity):
    _names_meta = NamesMeta(include=False)                   # no name vector
```

| Option | Default | |
|---|---|---|
| `fields` | `("label",)` | The fields whose values are the item's names: `label` (every document's and entity's), or a field the class declares as `str`, `str \| None` or `list[str]` (each item one name) |
| `include` | `True` | Whether the items of the class have names, and so a name vector |

With no slot anywhere, **an entity has names** (its `label`) and **a document has none**. A subclass has its parent's
setting (or a trait's) unless it says its own. A class `pangloss-vectors` gives no vectors (`VECTORS_EXCLUDE`,
`VectorsMeta(include=False)`, review's stand-ins unless `VECTORS_INCLUDE`) has no name vector either. Refused at
`initialise()` (`PanglossMetaError`), by the name of the class that says it: a field the class has not (with "Did you
mean"), a field that is not text (an annotated value, a relation, a number), `fields=[]` with `include=True`, and the
slot on a wrapper, an embedded object or an edge model (a trait may say it, for the classes that have it).

## The settings

| Setting | Default | |
|---|---|---|
| `NAMES_DIMENSION` | 256 | The length of the name part's vectors, a whole number from 8 to 2048. 256 is half of what there is to gain from 128 to 2,048, for twice the length (measured, below) |
| `NAMES_VARIANTS` | None | A table of name variants: the path of a CSV file, absolute or relative to the directory of the settings module (next section) |

The part's `signature()` is the classes with names and their fields, the dimension, and the table of variants (a hash
of its content). A change to any of them makes a rebuild due for the name part alone, and for the profiles that weigh
it (`pangloss vectors status` says why). The table of rarity is what a rebuild makes, not what it depends on, so it is
not in the signature.

## The table of variants

```python
NAMES_VARIANTS = "name_variants.csv"       # beside settings.py
```

```
# given names
Johannes,Johann,Hans,Jan
Margaret,Margareta,Greta
```

One line for each canonical form, the form first and then its variants. UTF-8 (a byte-order mark allowed, as a
spreadsheet writes it); blank lines and lines that start with `#` are skipped; each cell is **one word** once folded.
A word of a name that is a variant is replaced by its canonical form before its trigrams are made, so `Hans Mayer`
and `Johannes Mayer` have the same name vector. A variant that folds to its own form is left out.

**Refused at `initialise()`** (`PanglossInitialisationError`, by the file and the line), when the app is installed: a
file that is not there, is a directory or is not UTF-8; a line with no variant; a cell that is not one word (two
words, or none: an empty cell); a canonical form on two lines; a variant of two canonical forms; a variant that is
itself a canonical form. A setting that is not a path is refused too.

The file is read once for a settings object (`settings.variants()`) and forgotten when the models are reset, so **a
running server sees a changed table only when it starts again**; `pangloss vectors status` from the command line
sees it at once. The signature holds a hash of the table it makes (`settings.variants_hash()`), so a comment, a blank
line, the order of the lines or the case of a word changes nothing, and no table is the hash of the empty one.

## Rarity, and what a refresh weighs by

Rarity is a count over every name, so a refresh of a few items cannot make it again. So:

- **It is made at a rebuild**, over the items with names that a reader could be shown (`maths.Rarity.of`): the
  number of items with names and, for each word two or more of them have, how many. A word one item has weighs as one
  never seen, so the table holds only shared words (on the planted world, 38,564 names have 4,887 words, and the
  table fewer: the plan, 8.2).
- **It is kept with the generation** (the part's `kept()`, as JSON `{"having": {...}, "names": n}`, stored by
  `pangloss-vectors` as a `PGVectorKept` before the switch: [vectors](vectors.md), "Parts and profiles"). The text of
  the generation in use is parsed once in a process and remembered, by the generation and when it was built.
- **A refresh and an overlay weigh by the kept table** of the generation in use, never a new one, so a refresh is
  exact against the last rebuild's table: the vector it writes is the one a rebuild with that table would write.
- **Every vector a refresh writes is counted stale**: it is weighed by a table that does not count it, which is what
  `VECTORS_REBUILD_AFTER` means by "left out of date". So a project that sets it gets a new table after that many
  names written. (It over-counts a little: a write made before a rebuild and refreshed after it is counted though the
  rebuild's table counted it; `TODO.md`.)
- A part built whose kept table is not there makes a refresh raise `RebuildDue`, which the worker reports as it goes
  on; never built, a refresh does nothing (the first vectors come from a rebuild).

## Rebuild, refresh and overlay

- **A rebuild** (`pangloss vectors rebuild`, or `--part name`) reads every item of a class with names in pages of
  10,000 by `PGIndexableNode(id)`, with the values of the name fields, and keeps those a reader could be shown (not
  merged into another, its head there and not deleted; whether it is published is the search's); makes the table of
  rarity over them; and writes a vector for each item whose names give one, a thousand at a time.
- **A refresh** reads again the heads written, and the documents nested in them if a class of documents has names,
  and weighs them by the kept table. A written item whose names now give no vector (emptied, or no longer one a
  reader could be shown) loses its vector, and so does a head whose class was changed to one without names.
- **An overlay** of a write plan gives the vector its head would have, by the kept table, if its class has names;
  nothing is written. Nothing before the first rebuild.

The part is `local` (a write changes only the vectors of what it wrote) and at **weight 0**: installing the package
changes no profile and no result until `VECTORS_PROFILES` weighs it.

## Search by a name

```python
import pangloss_names

vector = await pangloss_names.vector_of("Guido of Spoleto")     # or several names of one item
found = await pangloss_names.search("Guido of Spoleto", types=["Person"], k=10)
found.status, found.hits                                          # as pangloss_vectors.nearest gives them
```

- `vector_of(text)` weighs a text as a stored item with those names would be weighed: by the table of rarity of the
  generation in use and the table of variants. None for a text with no letter or digit; `NotBuilt` (a `RebuildDue`)
  if the part was never built.
- `search(text, *, types=, profile=, k=10, see_unpublished=False)` is `pangloss_vectors.nearest(vector={"name": ...})`
  through the profile named, or else the first by name that weighs the name part; `ValueError` if none does (the
  message says what to set), if the profile named does not weigh it or does not exist, or if the text has no letter
  or digit. `types` are classes of documents or entities, with the classes below them. Unpublished documents only
  with `see_unpublished`; what a reader may not see is never a hit.
- On the command line, `pangloss names search TEXT [--type NAME ...] [--profile NAME] [-k 10]`: a line for each hit,
  nearest first, with its score, class, label and id. It shows unpublished documents (the command line is the
  project's owner). Exit 2 for a profile, a class or a text that is wrong; 1 if the part or the profile needs a
  rebuild. [The command line](../guide/cli.md#pangloss-names).
- **No route** yet: phase 10's is the one a client will ask.

**What a hit's score is.** The query has only the name part; the stored vectors of a profile have every part it
weighs, each at length one times the square root of its weight, end to end (`store.Layout.combine`). So a hit's score
is

```
cos(names) × sqrt(w_name / Σ w of the parts the hit has a vector of)
```

With `{"name": 1, "graph": 0.25}`: 0.894 × the cosine of the names for a hit that has a graph vector, and the cosine
of the names itself for one that has none. Among hits with the same parts the order is that of the names; **an item
that nothing names (no graph vector) is lifted above one that is named.** The score is not the cosine of the names,
and scores of different profiles cannot be compared. Whether a search by a name should weigh only the name (a profile
of the name alone has no such lift) is for phase 10.

## In the demo

`pangloss-demo` installs the app, and its settings say

```python
VECTORS_PROFILES = {"who": {"name": 1, "graph": 0.25}}
NAMES_VARIANTS = "name_variants.csv"       # pangloss_demo/name_variants.csv
```

`"default"` is not given, so it stays the parts at their own weights (class 0.1, graph 1). The weights of `who` are
those measured on the planted world (below). The table holds the given names of the demo's people (Charles with
Karolus and Karl, Guy with Wido and Guido, Eric with Erich, Augustus with Gussie, and so on). Every entity class has
names by its label, the default; none says `NamesMeta`. The migration `demo_app` 0025 is the three vector indexes of
`who` (dimension 384: 256 of the name, 128 of the graph) and nothing else. [Demo setup](demo-setup.md).

On a scratch copy with `populate.py` and 2,000 made-up people (2026-11-22, `pangloss names search ... --type Person`):
"Guido of Spoleto" gave `Wido of Spoleto` first at 1.0; "Eric Brunow" gave itself at 1.0 and `Colonel Erich Brunow`
at 0.90; "Gussie Fink-Nottle" gave itself and `Augustus Fink-Nottle` at 1.0; "Bertie Woostre" gave `Bertie Wooster`
first at 0.73.

## Measured

All on the planted world of `pangloss_testing.planted` (`notes/similarity-evaluation/planted.py`, step 8.1): at
`people=32_000`, 38,564 `Person`s of which **6,427 are mentions** (the same person under another spelling or a variant
of the given name, named beside the person's family and fellows), 32,137 people, 302,239 nodes of the models (629,927
in all). "Right first" is the person a mention is, ranked first among the 32,137 people, the other mentions left out;
it counts every namesake of the right person before them (half the people share their name with another). The
scripts and their output are in `notes/similarity-evaluation/`.

**The base, by graph and class alone** (8.1, 2026-11-21 and 22, `planted_base_memgraph.txt`, `planted_base_neo4j.txt`;
the stored vectors of a rebuild of the class and graph parts):

| | Right first | Among the five nearest | Among the ten |
|---|---|---|---|
| Memgraph | 0.0% | 33.1% | 47.5% |
| Neo4j | 0.0% | 33.3% | 47.2% |

The graph never puts the right person first: the people a mention is named beside share a document with it and are
nearer it than the person, who shares none. So the graph says whose company a mention keeps, and something else has
to choose within it: the name.

**By name alone, through the maths** (8.2, 2026-11-21, `names_planted.py`, `.txt`):

| | Right first | Among the five nearest |
|---|---|---|
| No rarity, 256 | 31.5% | 69.7% |
| Rarity by the trigram, 256 | 31.0% | 69.4% |
| **Rarity by the word, 256** (what is built) | **36.6%** | **80.5%** |
| The same, with the table of variants | 42.0% | 90.5% |
| No rarity, with the table | 41.8% | 91.4% |
| Rarity by the word at 32, 64, 128, 512, 2,048 (no table) | 28.5, 33.0, 35.5, 37.4, 38.1% | 64.8, 74.2, 78.3, 81.8, 82.6% |

Rarity by the trigram costs quality (the trigrams two spellings of a name do not share are the rare ones, so the
difference gets the weight); by the word it is worth 11 points among the five nearest without a table, and nothing
with one (the table already makes the given names agree). The planted surnames are evenly common, so what rarity among
surnames is worth on real names is not measured.

**Name and graph together** (8.1, 2026-11-22, `names_with_graph.py`, `.txt`: the stored graph vectors of the Memgraph
and name vectors made by the maths, combined as a profile is, `Σ w·cos / Σ w`):

| | Right first | Among the five | Among the ten |
|---|---|---|---|
| Name alone | 36.6% | 80.5% | 89.1% |
| Name 1, graph 0.25 | 45.0% | 89.7% | 95.6% |
| Name 1, graph 1 | 4.2% | 88.3% | 97.5% |
| Name alone, with the table of variants | 42.0% | 90.5% | 95.3% |
| **Name 1, graph 0.25, with the table** | **63.0%** | **97.2%** | **98.4%** |
| Name 1, graph 1, with the table | 4.8% | 93.3% | 98.9% |

A little graph helps much, and much graph puts the family (who share the surname) before the person: hence the
demo's `who`, name 1 and graph 0.25.

**Sizes and times of the planted world** (8.1): the file 47 MB, made in 0.7 s; loaded with 8 writers in 206 s on
Memgraph and 284 s on Neo4j; a rebuild of the class and graph parts (224,247 vectors of each) 187 s on Memgraph and
104 s on Neo4j. A search narrowed to `Person` by an exact scan of 38,564 vectors took 307 ms at the median on Memgraph
and 183 ms on Neo4j: **a class searched by name this often wants `VectorsMeta(searchable=True)`**, a group with an
index of its own.

**In the tests** (`tests/test_names_planted.py`, pure, 1,500 people, three seeds): floors a little under what is
measured, so that a change that costs quality fails: among the five nearest above 80% without the table and 93% with
it, among the ten above 98% with it, and the table worth 5 points to the mentions under a variant.

### 8.6 measured

Through the part, on 8.1's large world (32,137 people, 6,427 mentions, 302,239 nodes of the models), on both
backends, 2026-11-22 (`notes/similarity-evaluation/planted.py`; `planted_names_*.txt`). "Right first" counts everyone
as near as the right person before them. Tests of other steps were running on the same machine for part of it.

| Weights | Right first | Among the five nearest | Among the ten |
|---|---|---|---|
| Graph alone (8.1's base) | 0.0% | 33.1% | 47.5% |
| Name alone, no table of variants | 36.6% | 80.5% | 89.1% |
| Name 1, graph 0.25, no table | 45.2% | 89.7% | 95.6% |
| Name alone, with the table | 42.1% | 90.6% | 95.4% |
| Name 1, graph 0.1, with the table | 72.5% | 95.8% | 97.6% |
| **Name 1, graph 0.25, with the table** | **63.6%** | **97.2%** | **98.5%** |
| Name 1, graph 0.5, with the table | 28.2% | 96.9% | 99.1% |

(Memgraph's figures; Neo4j's are within 0.3 of each. The trial of 2026-11-11, on data that is lost: label alone 54%
right first, label and context 78%, 99.6% among the five.) The more the graph weighs, the more often the people named
beside a mention, who share its surname, come before the person: a little graph is worth 20 to 30 points right
first, and much graph costs all of it. Among the five nearest it hardly matters between 0.1 and 0.5.

| | Memgraph | Neo4j |
|---|---|---|
| The name part rebuilt (40,644 vectors: read, the table, the vectors written) | 13.3 s | 10.0 s |
| The profile `who` combined and indexed (224,247 vectors of 384) | 234 s | 98 s |
| A search by a name through the profile's index, 20 asked (300 mentions' labels): the person among them | 96.0% | 96.0% |
| The same narrowed to `Person`, an exact scan of 38,564: the person among them | 97.0% | 96.7% |
| A search through the index, at the median | 150 ms | 12 ms |
| A search by the exact scan, at the median | 756 ms | 572 ms |
| A new person written (with the marks for the workers) | 14 ms | 12 ms |
| The worker's turn after it (every part and both profiles) | 760 ms | 201 ms |

- **The profile is the cost, not the part.** A profile holds a vector for every item that has any of its parts, so
  `who` has one for each of 224,247 documents and entities though only 40,644 have names: combining and indexing
  them is 18 times the name part's own rebuild on Memgraph.
- **The index holds for a query of one part** (96.0% against 97.0% by the exact scan), though the query has zeros
  where the stored vectors have a graph part. That was not known before (2.4 measured queries made as the stored
  vectors are).
- **Not measured apart**: what the name part alone adds to a worker's turn (the turn is all the parts'), and why
  Memgraph's search through the index is 150 ms here.

## As built: where the code differs from the plan

- **Rarity is by the word, not by the trigram** (the plan said trigrams "weighted by rarity"): measured, above.
- **`fold` did not move to `pangloss-models`**: `pangloss_models.fold` (lower case, accents) was already general, and
  review's `label_key` is its own. The name part's `fold` is that and a cut into words.
- **Where the table of rarity is kept**: a general hook of `pangloss-vectors`, `Part.kept()`, stored as
  `(:PGVectorKept {part, generation, text})` with an index of its own (migration `0003_vector_kept` of
  `pangloss_vectors`), not a node of the name part's.
- **A refresh looks at every head written**, not only those of classes with names, to take the name vector from a
  head whose class was changed to one without; and a part built without its kept table raises `RebuildDue`.
- **Search** raises `ValueError` for a text with no name in it, rather than giving nothing; `NotBuilt` is a
  `RebuildDue`.
- **The plan's example, "Jon Smyth"**, ranks badly (above, "The maths").

## The code

| File | |
|---|---|
| `maths.py` | `fold`, `canonical`, `variants_table`, `trigrams`, `words`, `Rarity`, `weighted`, `place`, `hashed`, `vector`: no database |
| `meta.py` | `NamesMeta`, `named()` (each class with names and its fields), and its checks at `initialise()` |
| `settings.py` | `NAMES_DIMENSION`, `NAMES_VARIANTS` (`variants()`, `read_variants`, `variants_hash()`, `check_variants`) |
| `part.py` | The part `"name"`: `rebuild`, `refresh`, `overlay`, `kept()`, `rarity()` (the kept table, parsed once a generation) |
| `by_name.py` | `vector_of`, `search`, `profile_for`, `NotBuilt` |
| `cli.py` | `pangloss names search` |

Tests: the pure ones in `tests/` (the maths, `NamesMeta`, the part's signature and names, the table of variants and
its refusals, the planted floors); the live ones in `tests/live/` on both backends (the part through
`PartSuite`, with the kept table and its refusals; the table of variants in a rebuild and the status; a search by a
name: variants and namesakes ranked, narrowed, unpublished and merged items, the command).
