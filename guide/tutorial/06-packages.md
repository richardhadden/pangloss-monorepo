# Part 6: More packages

Pangloss's core is small on purpose. Much of what a research project needs comes as optional packages, each an app you
add to `INSTALLED_APPS`, as you did with the interface and with dates. In this part you add two:

- **`pangloss-typology`**: a controlled vocabulary in a hierarchy, here of occupations. A pope is a bishop is a cleric,
  so asking for the clerics finds the popes too.
- **`pangloss-review`**: a factoid is checked by someone before the public can see it.

## Installing them

In `chronicles_site/settings.py`:

```python
    INSTALLED_APPS: list[str] = [
        "pangloss_memgraph",
        "pangloss_dates",
        "pangloss_typology",
        "pangloss_review",
        "chronicle",
        "pangloss_interface",
    ]
```

Each brings commands of its own: `pangloss --help` now lists `typology` and `review`.

## A vocabulary of occupations

In `chronicle/models.py`, declare the typology, and give people a field for it:

```python
from pangloss_typology import Typed, Typology, TypologyMeta
...


class OccupationTypology(Typology):
    """What people did: a hierarchy (a pope is a bishop is a cleric)"""

    _typology_meta = TypologyMeta(name="OccupationType")


class Person(Entity, Agent):
    """Someone a source mentions"""

    _interface_meta = InterfaceMeta(colour="amber")

    aliases: list[str]
    has_type: list[Typed[OccupationTypology]]
```

`OccupationTypology` makes a new entity model, **`OccupationType`**: each occupation ("Pope", "King") is an entity of
that model, with a label, a description and a supertype. Because it is an ordinary entity, it has lists, search, and an
item page in the interface like any other. `has_type: list[Typed[OccupationTypology]]` lets a person have any number of
occupations. (The field must be called `has_type`; the [typology guide](../typology/README.md) explains the rules.)

In Python the new model is `OccupationTypology.Type`: it is made by the typology, so there is no `OccupationType` to
import.

## Reviewing factoids

Mark the model whose documents are to be checked:

```python
from pangloss_review import ReviewMeta
...


class Factoid(Document):
    """What a source says, at one place in it"""

    _review_meta = ReviewMeta(reviewable=True)

    source: Annotated[Source, RelationConfig(reverse_name="cited_by")]
    ...
```

From now on a new factoid starts **unpublished**: people who are logged in see it, the public does not. When someone
marks it as checked, it is published.

## The migration

```console
$ pangloss makemigrations --name types_and_review
chronicle.0004_types_and_review
    - Create the index :OccupationType
    - Create the Entity OccupationType
    - Add the relation field Person.has_type
Wrote .../chronicles/chronicle/migrations/0004_types_and_review.py
$ pangloss migrate
...
  chronicle.0004_types_and_review: applying
  chronicle.0004_types_and_review: applied
Done
```

Review needed no change to the data, so it is not in the migration: it is a rule about what is shown, kept in `meta`.

## Loading the vocabulary

You could create occupations one at a time, but a vocabulary is usually written out as a whole. Make a file
`occupations.jsonc` in the project directory, nested as the hierarchy is:

```jsonc
// The occupations of the people in the sources, as a hierarchy
[
  {"label": "Cleric", "children": [
    {"label": "Bishop", "children": [{"label": "Pope"}]},
    {"label": "Abbot"}
  ]},
  {"label": "Ruler", "children": [
    {"label": "King"},
    {"label": "Emperor"}
  ]}
]
```

and load it:

```console
$ pangloss typology load OccupationType occupations.jsonc --user alice
7 made, 0 already there
$ pangloss typology tree OccupationType
Cleric
  Abbot
  Bishop
    Pope
Ruler
  Emperor
  King
```

Loading again changes nothing (`0 made, 7 already there`): an occupation already there, with the same label under the
same parent, is left alone. So you can add to the file and load it again.

## Giving people occupations

In a new interactive session:

```python
>>> from shell import *
>>> await connect()
>>> pope = (await OccupationTypology.Type.list("pope")).results[0]
>>> leo = (await Person.list("leo")).results[0]
>>> edit = await Person.get_for_edit(leo.id)
>>> await Person.Update(**{**edit.model_dump(), "has_type": [{"type": "OccupationType", "id": pope.id}]}).save()
>>> (await Person.get(leo.id)).has_type
[OccupationTypeReferenceView(id=UUID('01a197db-18fa-...'), label='Pope', type='OccupationType')]
```

The hierarchy is what makes a typology more than a list. Where does "Pope" sit, and who are the clerics?

```python
>>> [t.label for t in await OccupationTypology.path(pope.id)]
['Cleric', 'Bishop', 'Pope']
>>> cleric = (await OccupationTypology.Type.list("cleric")).results[0]
>>> view = await OccupationTypology.view(cleric.id, include_subtypes=True)
>>> [e.label for e in view.entities.items]
['Pope Leo III']
```

Leo was given "Pope", not "Cleric", and is found among the clerics because a pope is a bishop is a cleric.

Open <http://localhost:3000/OccupationType> after restarting the interface: the typology has a page of its own, the
hierarchy as a tree, in which you can drag an occupation to move it under another.

## Checking a factoid

Make a new factoid in the same session:

```python
>>> annals = (await Source.list("annals")).results[0]
>>> crowned = await Factoid.Create(
...     label="Leo crowns Charles emperor",
...     source={"type": "Source", "id": annals.id},
...     page="s.a. 801",
...     text="On the most holy day of Christmas the pope placed a crown on his head.",
...     mentions=[{"type": "Person", "id": leo.id}],
...     statements=[],
... ).save()
```

(The Annals begin each year at Christmas, so the coronation of Christmas 800 is under 801.) Read it back as alice and it
is there, but not published:

```python
>>> new = await Factoid.get(crowned.id)
>>> new.meta.published, new.meta.review_status
(False, 'unchecked')
```

Someone who is not logged in cannot see it at all. Try it (with the id of the new factoid):

```console
$ curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:8000/api/Factoid/01a197db-42c6-...
404
```

The factoids made before review was switched on are unaffected: they stay published. The review queue lists what is
waiting:

```console
$ pangloss review queue
01a197db-42c6-...  unchecked    Factoid              Leo crowns Charles emperor  (0 open comments)
1 in all
```

Check it:

```console
$ pangloss review set 01a197db-42c6-... checked --user alice
Factoid Leo crowns Charles emperor: checked (published: True)
```

and now everyone can read it (`curl` gives `200`). In a real project the checking would be done by someone other than the
author; `REVIEW_ALLOW_SELF_REVIEW = False` in the settings enforces that. Reviewers can also leave comments on a factoid,
or on one statement in it. The [review guide](../review/README.md) has the rest, including the HTTP endpoints.

## Other packages

The same pattern (add to `INSTALLED_APPS`, use in your models, migrate) applies to the rest:

| | |
|---|---|
| [`pangloss-history`](../history/README.md) | Every version of every document kept, with differences between them, and a way back |
| [`pangloss-calendar`](../calendar/README.md) | What is dated on a day, in a month, in a year; feasts and Easter |
| [`pangloss-zotero`](../zotero/README.md) | A Zotero library kept in the database as sources |
| [`pangloss-sdk-server`](../sdk/01-server.md) | Your models as a Python package that others can install and script against |

## What you have done

Your people have occupations from a vocabulary you control, and new factoids wait to be checked before they are
published. In [part 7](07-testing.md), the last, you write tests.
