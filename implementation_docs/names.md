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
| ⏳ | The table of variants as a setting (`NAMES_VARIANTS`, step 8.5): `settings.variants()` gives `{}` |
| ⏳ | Search by a name, `pangloss names search` (step 8.6), and what it was measured at |
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
