# Part 3: The web interface

Pangloss has an optional web interface made from your models: a list page and an item page for every document and
entity, with search, and a navigation bar. In this part you install it, look at the data from part 2, and make a few
changes to how it is shown. One of them needs a migration, which shows how a migration deals with data that is already
there.

> **What the interface can do today.** It shows your data: lists with search, item pages with every field, the things
> that refer to an item, and documents nested inside documents. Logged in, it also makes, edits and deletes items, with
> forms made from your models ([the interface guide](../interface/README.md#making-and-editing-items)). This part
> only looks; the tutorial goes on writing data from Python (as in part 2) and over the API (part 5), where each step
> can be seen.

## Installing it

The interface is an app, like `chronicle`. Add it to `INSTALLED_APPS` in `chronicles_site/settings.py`:

```python
    INSTALLED_APPS: list[str] = [
        "pangloss_memgraph",
        "chronicle",
        "pangloss_interface",
    ]
```

It is a JavaScript application, so it needs Node (22.12 or newer). Prepare it:

```console
$ pangloss interface install
  wrote .pangloss/interface/...
  ...
  wrote .pangloss/interface/interface-app/src/generated/models.ts
  ...
added 167 packages, and audited 170 packages in 1s
```

(npm may add a warning that a package's install scripts are "not yet covered by allowScripts"; it is harmless here.)
This copies the interface into `.pangloss/interface/` in your project, writes a description of *your* models into it
(`generated/models.ts`), and installs its JavaScript packages. Nothing in `.pangloss/interface/` is for you to edit: it is
written again each time.

Now run the API and the interface, in two terminals (activate the environment in both):

```console
$ pangloss dev
```

```console
$ pangloss interface dev
...
  VITE v8.3.4  ready in 937 ms

  ➜  Local:   http://localhost:3000/
```

The interface runs on port 3000 and passes requests for `/api` on to the API on port 8000.

## Looking around

Open <http://localhost:3000/Person>. (Use `localhost`, as printed: the development server may not answer on
`127.0.0.1`.)

You see the list of people: *Charlemagne* and *Pope Leo III*, each with a coloured tag saying what type it is, a search box
above them, and the number found. Click *Charlemagne*. His page shows his aliases and, under **Mentions reverse**, the
factoid that mentions him: the reverse relation from part 2. Click the factoid and you see its source, page, text, and
the people it mentions, each a link to their own page.

The page at <http://localhost:3000/Factoid> lists the factoids, and so on for each of your models. The home page,
<http://localhost:3000/>, has the name of the project and one box that searches everything: type `charl` and
*Charlemagne* is found, whatever his type. ([The interface guide](../interface/README.md#your-own-homepage-and-pages)
says how to make the homepage, and pages of your own.)

## Colours

Entities are blue and documents green unless you say otherwise. Give people and sources colours of their own, in
`chronicle/models.py`:

```python
from pangloss_interface import InterfaceMeta
...


class Person(Entity):
    """Someone a source mentions"""

    _interface_meta = InterfaceMeta(colour="amber")

    aliases: list[str]


class Source(Entity):
    """A text that makes claims: a chronicle, a letter, a charter"""

    _interface_meta = InterfaceMeta(colour="stone")

    author: str | None = None
```

The colours are [Tailwind](https://tailwindcss.com/docs/colors)'s names: `red`, `amber`, `emerald`, `sky`, `stone` and
so on.

An attribute whose name starts with an underscore and ends in `_meta` is not a field: it is information *about* the
model, for Pangloss or for one of its apps. You will meet `_meta` (for Pangloss itself), `_review_meta` and others later.

## Navigation

The bar on the left (open it with the button at the top) can list your models, in sections. An app says what to put
there in a file of its own. Make `chronicle/interface_config.py`:

```python
from pangloss_interface import InterfaceConfig, NavModel

config = InterfaceConfig(
    sections=["Sources", "People and places"],
    nav=[
        NavModel("Factoid", section="Sources"),
        NavModel("Source", section="Sources"),
        NavModel("Person", section="People and places"),
        NavModel("Place", section="People and places"),
    ],
)
```

## A better name for the other direction

"Mentions reverse" is what Pangloss calls the reverse of `mentions` when you do not say. Say: a relation can be given a
**configuration**, with `Annotated`:

```python
from typing import Annotated

from pangloss_models import RelationConfig
...


class Factoid(Document):
    """What a source says, at one place in it"""

    source: Annotated[Source, RelationConfig(reverse_name="cited_by")]
    page: str
    text: str
    mentions: Annotated[list[Person], RelationConfig(reverse_name="mentioned_in")]
```

The field is still `source`, a `Source`; `Annotated` adds information without changing the type. Now a source lists the
factoids that cite it under `cited_by`, and a person those that mention them under `mentioned_in`.

Colours and navigation are only about display. The reverse names are different: each relation is stored as a pair of
links, one in each direction, and the reverse one has a name. The factoid you made in part 2 has links called
`mentions_reverse` and `source_reverse` in the database, and they must be renamed. That is a migration:

```console
$ pangloss makemigrations --name reverse_names
chronicle.0002_reverse_names
    - Factoid.mentions: the reverse edges mentions_reverse -> mentioned_in
    - Factoid.source: the reverse edges source_reverse -> cited_by
Wrote .../chronicles/chronicle/migrations/0002_reverse_names.py
```

(`--name` gives the file a name you can read; otherwise Pangloss makes one up from the changes.) Notice that the colours
and the navigation did not produce any change: `makemigrations` only writes what concerns the data.

This migration changes data that exists. Before applying a migration like that, try it: a **dry run** makes the changes
for real, inside a transaction, says what they did, and then undoes them.

```console
$ pangloss migrate --dry-run
To apply:
  chronicle.0002_reverse_names
    - Factoid.mentions: the reverse edges mentions_reverse -> mentioned_in
    - Factoid.source: the reverse edges source_reverse -> cited_by

Tried, and rolled back:
  chronicle.0002_reverse_names
    - Factoid.mentions: the reverse edges mentions_reverse -> mentioned_in
        2 edges made, 2 edges deleted, 2 properties set
    - Factoid.source: the reverse edges source_reverse -> cited_by
        1 edges made, 1 edges deleted, 1 properties set
Nothing was changed
```

Two people are mentioned, so two links were replaced, and one source is cited. That is what you expect, so apply it:

```console
$ pangloss migrate
...
  chronicle.0002_reverse_names: applying
  chronicle.0002_reverse_names: applied
Done
Models the migrations could have made unreadable: Factoid, Person, Source
Reading the data with the models ...
All 4 can be read
```

The last three lines are a check `migrate` makes for you: after a migration that changed data, it reads every object of
the models it touched with the models as they are now, to be sure nothing has become unreadable.

## Seeing the changes

`pangloss dev` restarts by itself when a file changes. The interface reads your models when it starts, so stop
`pangloss interface dev` (Ctrl-C) and start it again. Then open Charlemagne's page again: his tag is amber, the factoid is
listed under **Mentioned in**, and the navigation bar has your two sections.

## What you have done

You have a web interface for your data, coloured and arranged as you want it, and you have made a migration that changed
data already in the database, after trying it first. In [part 4](04-statements.md) the factoids grow statements.
