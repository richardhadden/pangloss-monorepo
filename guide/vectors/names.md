# Finding people by name

With `pangloss-names`, every person (and every other entity) gets a vector made from its **name**, so that you can
search by a name and find the people whose names are near it: other spellings ("Wooster", "Woostre"), the same name
with the given name in another form ("Wido", "Guido"), and namesakes. It is a third **part** of
[similar items](README.md), beside the class and the graph, and works on Memgraph and on Neo4j.

It finds **candidates**: the people a name might be. It does not decide that two names are the same person's.

The reference is [names](../../implementation_docs/names.md).

## 1. Install it

```python
INSTALLED_APPS = [
    "pangloss_memgraph",
    ...
    "pangloss_vectors",
    "pangloss_fastrp",
    "pangloss_names",    # the name part
    "my_app",
    "pangloss_interface",
]
```

It needs `pangloss_vectors`, and numpy in the server's environment (a dependency of the package).

## 2. Weigh the name in a profile

Installing the package changes nothing by itself: the name part has a weight of 0, so no profile uses it until you
say so. Add a profile that weighs it:

```python
# settings.py
VECTORS_PROFILES = {
    "who": {"name": 1, "graph": 0.25},
}
```

`"who"` is mostly the name, with a little of the graph (the company a person keeps). Do not give the graph much
more: a person's family shares the surname and is named beside them, and with the graph at 1 the family comes before
the person. (Measured on made-up data: with the name at 1 and the graph at 0.25 the right person was among the five
nearest 97% of the time, with a table of variants; with the graph at 1, the right person was first only 5% of the
time. The figures are in [the reference](../../implementation_docs/names.md#measured).)

If you do not give `"default"` it stays as it was (the graph at 1, the class at 0.1), so the "Similar" section of
each item's page does not change. `pangloss vectors weights` shows the profiles.

## 3. Migrate, then build the vectors

A new profile has vector indexes of its own:

```sh
pangloss makemigrations        # the indexes of "who": one, and one for each group
pangloss migrate
pangloss vectors rebuild       # (or only the name part and the profiles that weigh it: --part name)
pangloss vectors status
```

For the demo, `makemigrations` wrote:

```
demo_app.0025_addindex_addindex_addindex
    - Create the vector index pgv_who_384 on :PGV_who_384(vector) (dimension 384, metric cos)
    - Create the vector index pgv_who_384_person on :PGV_who_384_Person(vector) (dimension 384, metric cos)
    - Create the vector index pgv_who_384_statement on :PGV_who_384_Statement(vector) (dimension 384, metric cos)
```

384 is 256 for the name and 128 for the graph.

## 4. Search by a name

```sh
pangloss names search "Guido of Spoleto" --type Person
```

```
1.0000  Person  Wido of Spoleto  01a20103-1838-76b7-ab6c-5f3cb6619df9
0.3951  Person  Spiny Norman  01a20103-7b79-73f3-906c-afd37390c219
...
```

A line for each, nearest first: the score, the class, the label and the id. `--type` (more than once if you like)
keeps to a class and the classes below it; `-k` says how many (10); `--profile` chooses the profile, otherwise the
first, by name, that weighs the name part. The command shows unpublished documents too.

The order of the words does not matter ("Smith, John" is "John Smith"), nor case or accents. What it finds well is a
name **with one change of spelling**, or a variant the table of variants knows (next). Two short names with two
letters changed have little in common: "Jon Smyth" is not near "John Smith".

**The score is not only the name.** With other parts in the profile, a person who also has a graph vector (someone
named in a published document) scores a little lower than a person with the same name who has none: with the name at
1 and the graph at 0.25, 0.894 times as much. Compare the scores of one search, not of two profiles.

From Python, on the server's side:

```python
import pangloss_names

found = await pangloss_names.search("Guido of Spoleto", types=["Person"], k=10)
found.status        # "ok", "pending", "rebuild_due"
found.hits          # [Hit(id, type, score), ...], nearest first

vector = await pangloss_names.vector_of("Guido of Spoleto")   # the name vector of a text
```

There is no route over the API yet.

## 5. A table of variants

The name part knows nothing of what names are the same name: "Hans" and "Johannes" share no letters in order. A
table says so. Make a CSV file beside `settings.py`:

```
# given names
Johannes,Johann,Hans,Jan
Margaret,Margareta,Greta
Guy,Wido,Guido,Wito
```

```python
# settings.py
NAMES_VARIANTS = "name_variants.csv"     # relative to the directory of settings.py, or an absolute path
```

Each line is a canonical form and then its variants, one word in each cell. A word of a name that is a variant is read
as its canonical form, so `Hans Mayer` and `Johannes Mayer` have the same name vector. Blank lines and lines that start
with `#` are skipped; a spreadsheet's UTF-8 export is fine.

The table is checked when the models are initialised (`pangloss check`, or starting the server), and a mistake is
refused with the file and the line: a line with no variant, a cell of two words or of none, a canonical form on two
lines, a word that is a variant of two forms, or a variant that is itself a canonical form.

**A changed table makes a rebuild due** for the name part (`pangloss vectors status` says so): run
`pangloss vectors rebuild --part name`. A running server reads the table when it starts, so restart it too.

The demo's table is `pangloss-demo/pangloss_demo/name_variants.csv`: the given names of its people.

## 6. Which fields are names

By default every entity has a name, its `label`, and documents have none. A class says otherwise with `NamesMeta`:

```python
from pangloss_names import NamesMeta


class Person(Entity):
    aliases: list[str] = []
    # (the label, and each alias, is a name of the person: all of them make one vector)
    _names_meta = NamesMeta(fields=["label", "aliases"])


class Letter(Document):
    # (a document is found by its label too)
    _names_meta = NamesMeta(include=True)


class Place(Entity):
    _names_meta = NamesMeta(include=False)     # no name vector
```

A name field is `label`, or a field of the class that is `str`, `str | None` or `list[str]`. A subclass has its
parent's setting unless it says its own. `initialise()` (and `pangloss check`) refuses a field the class does not
have, a field that is not text, and `fields=[]`. A class with no vectors at all (`VECTORS_EXCLUDE`,
`VectorsMeta(include=False)`) has no name vector either. Changing `NamesMeta` makes a rebuild due.

## 7. Keeping it current

As with the other parts, the worker brings the name vectors of what you save up to date. Each name is weighed by how
rare its words are (a surname few people have counts for more than a common given name), and how rare a word is, is
counted at a rebuild: the worker weighs a new or renamed item by the counts of the last rebuild. That is exact for
what the last rebuild counted, and a little out of date for what has been written since, so every vector the worker
writes for the name part is counted as **stale**. With

```python
VECTORS_REBUILD_AFTER = 5_000
```

the worker starts a rebuild after that many. Otherwise run `pangloss vectors rebuild` now and then, and after a large
import.

## Not yet

- A route over the API for a search by a name, and anything in the web interface ("did you mean…?" as a person is
  made): later phases of [the build plan](../../implementation_docs/similarity-build-plan.md).
- A typology as a table of variants.
