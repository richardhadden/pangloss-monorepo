# Names: the name part of similarity 🚧

`pangloss-names` (an app: `INSTALLED_APPS += ["pangloss_vectors", "pangloss_names"]`) registers the part `"name"` of
[similarity](vectors.md): a vector of each item from its names, so that two spellings of a name, and a name and its
variants, are near each other. Being built as phase 8 of [the build plan](similarity-build-plan.md); this page is a
stub until step 8.7 writes it fully.

## What is built, and what is not

| | |
|---|---|
| ✅ | The maths (`maths.py`, step 8.2): words folded and cut, trigrams, rarity by the word (`Rarity`), hashed to a fixed dimension; no database in it |
| ✅ | Which classes have names (`meta.py`, step 8.3): `_names_meta = NamesMeta(fields=["label"], include=True)` |
| ✅ | The part `"name"` (`part.py`, step 8.3): rebuild, refresh and overlay; weight 0; the table of rarity kept with a generation |
| ✅ | The suite every part passes (`tests/live/test_names_part_live.py`) |
| ✅ | The table of variants as a setting (`NAMES_VARIANTS`, step 8.5): a CSV file, checked at `initialise()` by the line |
| ✅ | Search by a name (step 8.6): `pangloss_names.vector_of`, `pangloss_names.search`, `pangloss names search` |
| ⏳ | What a search by a name was measured at, on the planted world at size (step 8.6, main) |
| ⏳ | The demo's profile `who` and a guide page (step 8.7) |

## Which classes have names

```python
class Person(Entity):
    aliases: list[str] = []
    _names_meta = NamesMeta(fields=["label", "aliases"])

class Letter(Document):
    _names_meta = NamesMeta(include=True)          # its label is a name
```

With no slot anywhere, an entity has names (its `label`) and a document has none. A subclass has its parent's
setting (or a trait's) unless it says its own. A name field is `label` or a field the class declares as `str`,
`str | None` or `list[str]` (each item one name); anything else, a field the class has not, and no field at all, are
refused at `initialise()`. A class that has no vectors (`VECTORS_EXCLUDE`, `VectorsMeta(include=False)`) has no name
vector either.

## The part

- **Weight 0**: installing the package changes no profile and no result. A project names it in a profile:
  `VECTORS_PROFILES = {"who": {"name": 1, "graph": 0.25}}`.
- `NAMES_DIMENSION` (256), a whole number from 8 to 2048.
- **The signature** is the classes with names and their fields, the dimension and the table of variants: the table of
  rarity is what a rebuild makes, not what it depends on.
- **Rebuild**: every item of a class with names that a reader could be shown (not merged into another, its head there
  and not deleted), read in pages of 10,000 by `PGIndexableNode(id)` with the values of the name fields; the table of
  rarity over them; a vector for each item whose names give one. The table (JSON, `{"having": {...}, "names": n}`)
  is kept with the generation (`Part.kept`, `pangloss_vectors.store.keep`: [vectors](vectors.md), "Parts and
  profiles").
- **Refresh**: the heads written (and the documents nested in them, if a class of documents has names), weighed by
  the **kept** table of the generation in use, so exact against the last rebuild's table; every vector it writes is
  counted stale (weighed by a table that does not count it), towards `VECTORS_REBUILD_AFTER`. A written item whose
  names now give no vector loses it. Nothing before the first rebuild.
- **Overlay**: the vector of a plan's head by the kept table, if its class has names.

## The table of variants

`NAMES_VARIANTS = "variants.csv"`: a path, absolute or relative to the directory of the settings module. One line for
each canonical form, the form first and then its variants; UTF-8; blank lines and lines that start with `#` skipped:

```
# given names
Johannes,Johann,Hans,Jan
Margaret,Margareta,Greta
```

A word of a name that is a variant is replaced by its canonical form before its trigrams are made, so `Hans Mayer`
and `Johannes Mayer` have the same name vector. Read once (`settings.variants()`), forgotten when the models are
reset, and checked at `initialise()` when the app is installed: a file that is not there or not UTF-8, a line with no
variant, a cell that is not one word once folded, a canonical form on two lines, a variant of two canonical forms and
a variant that is itself a canonical form are each refused (`PanglossInitialisationError`) by the file and the line.
The signature holds a hash of the table's content (`settings.variants_hash()`: a comment, the order of the lines or
the case of a word changes nothing), so a changed table makes a rebuild due for the name part alone (and the profiles
that weigh it). A typology as a table is not built (the build plan, 8.5, says why).

## Search by a name

```python
vector = await pangloss_names.vector_of("Jon Smyth")             # or several names of one item
found = await pangloss_names.search("Jon Smyth", types=["Person"], k=10)
```

`vector_of` weighs a text as a stored item would be weighed: by the table of rarity of the generation in use and the
table of variants; None for a text with no letter or digit; `NotBuilt` (a `RebuildDue`) if the part was never built.
`search` is `pangloss_vectors.nearest(vector={"name": ...})` by the profile named or the first, by name, that weighs
the name part (`ValueError` if none does), narrowed to `types` and the classes below them; unpublished documents only
with `see_unpublished`. On the command line, `pangloss names search TEXT [--type NAME ...] [--profile NAME] [-k 10]`
([the command line](../guide/cli.md)), which shows unpublished documents. No route yet (phase 10's).

**A hit's score is not the cosine of the names.** The query has only the name part, the stored vectors every part the
profile weighs, so a hit's score is `cos(names) × sqrt(w_name / Σ w of the parts the hit has a vector of)`: with
`{"name": 1, "graph": 0.25}`, 0.894 × the cosine of the names for an item with a graph vector, the cosine itself for
one without. Among hits with the same parts the order is that of the names.
