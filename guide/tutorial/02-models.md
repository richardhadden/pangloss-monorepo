# Part 2: Models

In this part you describe your data as Python classes, let Pangloss set the database up for them, and then create and
read some data from an interactive Python session.

## Thinking about the data

Before writing code, think about what kinds of thing there are. Our material is chronicles, and what they say about
people. Some of what we record are **things in the world** that many sources talk about: Charlemagne, Paderborn, the Royal
Frankish Annals themselves. Others are **records of what one source says**: "the Annals, under the year 799, say that Pope
Leo came to the king at Paderborn".

Pangloss has a kind of model for each:

- An **`Entity`** is a thing in the world that records refer to. There is *one* Charlemagne in the database, however many
  sources mention him, and every record that mentions him points at that one entity.
- A **`Document`** is a record: it says something, and it refers to entities. Two sources that disagree are two
  documents, and both stay in the database; neither overwrites the other.

> **Philosophy: documents assert, entities are asserted about.** Pangloss encourages you to keep claims in documents, not
> on entities. Charlemagne's entity says very little (a name, some aliases); what he did is in the factoids that cite the
> sources that say so. That way every claim keeps its source with it, and two sources can say different things about the
> same man without one of them being lost.

## Your first models

Replace the contents of `chronicle/models.py` with:

```python
from pangloss_models import Document, Entity


class Person(Entity):
    """Someone a source mentions"""

    aliases: list[str]


class Place(Entity):
    """A town, a monastery, a battlefield"""


class Source(Entity):
    """A text that makes claims: a chronicle, a letter, a charter"""

    author: str | None = None


class Factoid(Document):
    """What a source says, at one place in it"""

    source: Source
    page: str
    text: str
    mentions: list[Person]
```

That is all the code there is for the data model. Here is what it says.

**Every object has a `label` and an `id`** without your declaring them. The label is a short, human-readable name
("Charlemagne", "Leo comes to Charles at Paderborn"), and it is required: it is what lists, searches and the interface
show. The id is made for you when the object is created.

**Literal fields** hold a plain value, stored on the object:

- `page: str` and `text: str` are required strings.
- `author: str | None = None` is optional: a source may have no known author.
- `aliases: list[str]` is a list of strings. It is required in the sense that you must give a list, but the list may be
  empty.

Besides `str` you can use `int`, `float`, `bool`, `Decimal`, `date`, `datetime`, enums, `TypedDict`s and lists of these.

**Relation fields** have another model as their type:

- `source: Source` says that every factoid refers to exactly one source.
- `mentions: list[Person]` says that a factoid refers to any number of people (none is fine).

A relation is stored as a link from one object to the other: the factoid *points at* the source, it does not contain a
copy of it. A relation is required (`Source`), optional (`Source | None`: there may be none), or a list (`list[Person]`, which may
be empty).

`Place` has no fields of its own yet. It still has a label and an id, and that is enough to be referred to; you will use it
in [part 4](04-statements.md).

## What Pangloss makes of them

When Pangloss loads your models, it generates more classes from each one. For `Factoid`:

| | |
|---|---|
| `Factoid.Create` | What you give to make a factoid: your fields, plus `label`. A relation is given as a reference, `{"type": "Source", "id": ...}` |
| `Factoid.Update` | What you give to change one: the same again, with its `id` |
| `Factoid.HeadView` | What you get back when you read one: your fields, each relation as a short summary of what it points at, and `meta` (who created it, when, which version) |
| `Factoid.get(id)`, `Factoid.list()`, `Factoid.delete(id)` | Reading, listing and deleting |

They are [Pydantic](https://docs.pydantic.dev/) models, so whatever you give them is checked: a missing `page`, or a
`page=3`, is an error before anything reaches the database. The REST API in [part 5](05-api.md) is made from the same
classes.

Your editor cannot see classes made at run time, but Pangloss can write a description of them for it:

```console
$ pangloss make-stubs
  wrote chronicle/models.pyi
Wrote 1 stub file(s)
```

Now an editor completes `Factoid.Create(...)` and knows what `Factoid.get` returns. Run it again whenever you change
your models.

## A migration for your models

Your models say what the data looks like, and the database needs to be told. As in part 1, that is a migration, but this
time you make it yourself:

```console
$ pangloss makemigrations
chronicle.0001_initial
    - Create the index :Factoid
    - Create the index :Person
    - Create the index :Place
    - Create the index :Source
    - Create the Document Factoid
    - Create the Entity Person
    - Create the Entity Place
    - Create the Entity Source
Wrote .../chronicles/chronicle/migrations/0001_initial.py
```

`makemigrations` compared your models with what the migrations so far describe (for `chronicle`, nothing), and wrote a
file saying what has changed. Open `chronicle/migrations/0001_initial.py` if you are curious: it is ordinary Python, a list
of changes with each model written out in full. **Keep it with your code** (commit it to git, alongside `models.py`):
anyone who sets up the project from your code runs the same migrations and gets the same database.

Nothing has touched the database yet. To see what would:

```console
$ pangloss migrate --plan
To apply:
  chronicle.0001_initial
    - Create the index :Factoid
    ...
    - Create the Entity Source
```

and to do it:

```console
$ pangloss migrate
...
  chronicle.0001_initial: applying
  chronicle.0001_initial: applied
Done
Nothing that exists is affected by these migrations: no data to read
```

From now on, whenever you change your models, the three steps are the same: **change `models.py`, run
`makemigrations`, run `migrate`.**

## A user

Everything written to Pangloss is recorded as written by someone: each object's `meta` says who created it and who last
changed it. Make a user:

```console
$ pangloss users create --username alice --email alice@example.org --password alice-password --full-name "Alice" --no-admin
Created user 'alice'
```

(Leave out an option and the command asks for it. `--admin` makes a user who can manage other users.)

## Exploring from Python

Your models are ordinary Python classes, and the quickest way to get to know them is to try them in an interactive
session. Pangloss talks to the database asynchronously, so use Python's **asyncio REPL**, in which you can `await` at the
prompt.

First, a few lines of setup that you will want every time. Make a file `shell.py` in the project directory (next to
`pyproject.toml`):

```python
"""For an interactive session: `python -m asyncio`, then `from shell import *` and `await connect()`"""

from pangloss_cli import load_project
from pangloss_models import initialise
from pangloss_users import current_request_username

# Load the settings, import the models of every installed app, and generate the classes from them
project = load_project(argv=[])
backend = project.require_database()
project.import_models()
initialise()

# What is written in this session is recorded as written by alice
current_request_username.set("alice")


async def connect():
    await backend.connect()


from chronicle.models import *  # noqa: E402, F403
```

Then, in the project directory:

```console
$ python -m asyncio
asyncio REPL 3.15.1 ...
Use "await" directly instead of "asyncio.run()".
>>> from shell import *
>>> await connect()
```

(Leave the session with Ctrl-D. When you change `models.py`, start a new session: the models are loaded once.)

### Creating

Make a source and two people:

```python
>>> annals = await Source.Create(label="Royal Frankish Annals").save()
>>> annals
SourceReferenceView(id=UUID('01a197d5-429a-7437-8974-4247743b005b'), label='Royal Frankish Annals', type='Source')
>>> charles = await Person.Create(label="Charlemagne", aliases=["Charles the Great", "Karolus"]).save()
>>> leo = await Person.Create(label="Pope Leo III", aliases=[]).save()
```

`Create(...)` checks the values; `.save()` writes them and gives back a short reference to what was made, with its new
`id`. `author` was left out of the source, and that is fine: it is optional.

Now a factoid. The Annals, under the year 799, say that Pope Leo, driven out of Rome, came to Charles at Paderborn:

```python
>>> factoid = await Factoid.Create(
...     label="Leo comes to Charles at Paderborn",
...     source={"type": "Source", "id": annals.id},
...     page="s.a. 799",
...     text="Pope Leo came to the king at Paderborn, and was received with great honour.",
...     mentions=[{"type": "Person", "id": charles.id}, {"type": "Person", "id": leo.id}],
... ).save()
```

The relations are **references**: `{"type": "Source", "id": annals.id}` says *which* source, by its id. The factoid does
not contain the Annals; it points at them.

### Reading

```python
>>> found = await Factoid.get(factoid.id)
>>> found.label
'Leo comes to Charles at Paderborn'
>>> found.source
SourceReferenceView(id=UUID('01a197d5-429a-7437-8974-4247743b005b'), label='Royal Frankish Annals', type='Source')
>>> found.mentions
[PersonReferenceView(id=UUID('01a197d5-42b1-...'), label='Charlemagne', type='Person'), PersonReferenceView(id=UUID('01a197d5-42bc-...'), label='Pope Leo III', type='Person')]
>>> found.meta.created_by, found.meta.version
('alice', 1)
```

A relation is read back as a summary of what it points at (its id, label and type), which is usually all a page needs.
To see the whole source, `Source.get(found.source.id)`.

`list()` gives a page of results, and takes a search:

```python
>>> page = await Person.list()
>>> page.count
2
>>> [person.label for person in page.results]
['Charlemagne', 'Pope Leo III']
>>> [person.label for person in (await Person.list("leo")).results]
['Pope Leo III']
```

### The other direction

Now read Charlemagne:

```python
>>> person = await Person.get(charles.id)
>>> person.aliases
['Charles the Great', 'Karolus']
>>> person.mentions_reverse
[FactoidReferenceView(id=UUID('01a197d5-42c6-...'), label='Leo comes to Charles at Paderborn', ...)]
```

You never declared a field on `Person` for the factoids that mention him, but `mentions_reverse` is there. Every relation
is stored in both directions, so an entity can always list what refers to it. This is the reason to make Charlemagne once
and refer to him, rather than writing his name into each factoid: his page now gathers everything every source says about
him. (`mentions_reverse` is not a very good name; you will give it a better one in [part 3](03-interface.md).)

The source works the same way: `(await Source.get(annals.id)).source_reverse` lists the factoids that cite it.

### When something is wrong

```python
>>> Person.Create(label="Einhard")
Traceback (most recent call last):
  ...
pydantic_core._pydantic_core.ValidationError: 1 validation error for PersonCreate
aliases
  Field required [type=missing, input_value={'label': 'Einhard'}, input_type=dict]
```

The check happens as soon as you make the `Create`, before anything is sent to the database (your own checks can be
added as in pydantic, and some that read the database too: see [Checking data](../validation/README.md)). A reference to something that
does not exist is caught when you save:

```python
>>> import uuid
>>> await Factoid.Create(label="A mistake", source={"type": "Source", "id": uuid.uuid4()}, page="1", text="...", mentions=[]).save()
Traceback (most recent call last):
  ...
pangloss_models.exceptions.PanglossReferenceError: Invalid references to existing objects: source: '0b29da39-...' not found
```

and nothing is written.

### Changing and deleting

To change something, read it **for editing**, change what you want, and save the whole thing as an update:

```python
>>> edit = await Person.get_for_edit(leo.id)
>>> await Person.Update(**{**edit.model_dump(), "aliases": ["Leo"]}).save()
PersonReferenceView(id=UUID('01a197d5-42bc-...'), label='Pope Leo III', type='Person')
>>> (await Person.get(leo.id)).aliases
['Leo']
>>> (await Person.get(leo.id)).meta.version
2
```

An update replaces the object with what you give, which is why you start from what is there (`get_for_edit` gives it in
the shape `Update` takes). Each update makes a new version.

`await Place.delete(id)` deletes. A deleted object is flagged and left out of every read rather than erased. An entity
that something still refers to is not deleted: Pangloss will not leave a factoid pointing at nothing. Try it with
Charlemagne and you get `PanglossEntityInUseError: Person ... is referred to by 1 object, so cannot be deleted. It has
been marked for deletion` (marked, so that someone can see it was asked for; he is still there and still readable).

## What you have done

You have models, the migration that set the database up for them, a user, and some data, and you have seen how relations
work in both directions. In [part 3](03-interface.md) you look at the same data in a browser.
