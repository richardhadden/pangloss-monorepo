# Part 4: Statements

So far a factoid records that a passage *mentions* Charlemagne and Leo. It does not say what the passage says happened:
that Leo travelled to Paderborn, that Charles received him there as his guest. In this part a factoid gets a list of
**statements**, each a small structured claim. Along the way you meet most of the ideas that make Pangloss suited to
this kind of material:

- documents **inside** documents;
- an **abstract** model, with kinds of statement as subclasses;
- a relation that has a field of its own: someone **in a role**;
- a **trait**: "a person or a group";
- saying that something did **not** happen;
- **dates**, as historians have them: known to the year, approximate, in the Julian calendar.

## Dates first

Statements need dates, and historical dates are awkward: "799", "about Easter 800", "between 795 and 799". The optional
package `pangloss-dates` handles them. It is an app: add it to `INSTALLED_APPS`, and say which calendar your sources use,
in `chronicles_site/settings.py`:

```python
    INSTALLED_APPS: list[str] = [
        "pangloss_memgraph",
        "pangloss_dates",
        "chronicle",
        "pangloss_interface",
    ]

    # (the dates of the sources are in the Julian calendar)
    DATES_DEFAULT_CALENDAR: str = "julian"
```

## The new models

Here is the whole of `chronicle/models.py` as it will be at the end of this part. The new parts are explained below.

```python
from enum import Enum
from typing import Annotated

from pangloss_dates.models import Date
from pangloss_interface import InterfaceMeta
from pangloss_models.model_bases.configs import RelationConfig
from pangloss_models.model_bases.document import Document
from pangloss_models.model_bases.entity import Entity
from pangloss_models.model_bases.reified_relation import ReifiedRelation
from pangloss_models.model_bases.semantic_space import SemanticSpace
from pangloss_models.model_bases.trait import Trait


class Agent(Trait):
    """Anyone who can act: a person or a group"""


class Person(Entity, Agent):
    """Someone a source mentions"""

    _interface_meta = InterfaceMeta(colour="amber")

    aliases: list[str]


class Group(Entity, Agent):
    """A family, a religious community, an army"""


class Place(Entity):
    """A town, a monastery, a battlefield"""


class Source(Entity):
    """A text that makes claims: a chronicle, a letter, a charter"""

    _interface_meta = InterfaceMeta(colour="stone")

    author: str | None = None


class Role(Enum):
    HOST = "host"
    GUEST = "guest"
    ENVOY = "envoy"
    WITNESS = "witness"


class InRole[T](ReifiedRelation[T]):
    """Someone, in a role"""

    role: Role


class Statement(Document):
    """Something that happened (a kind of statement is one of the classes below)"""

    _meta = Document.Meta(abstract=True)

    when: Date


class Meeting(Statement):
    """Agents met, somewhere"""

    participants: list[InRole[Agent]]
    at: list[Place]


class Journey(Statement):
    """An agent travelled to a place"""

    traveller: Agent
    destination: Place


class Negative[T](SemanticSpace[T]):
    """The source says that this did *not* happen"""

    _interface_meta = InterfaceMeta(colour="rose")


class Factoid(Document):
    """What a source says, at one place in it"""

    source: Annotated[Source, RelationConfig(reverse_name="cited_by")]
    page: str
    text: str
    mentions: Annotated[list[Person], RelationConfig(reverse_name="mentioned_in")]
    statements: list[Statement | Negative[Statement]]
```

### Statements are documents, inside a factoid

`Statement` is a `Document`, and `Factoid.statements` is a list of them. A relation to a *document* works differently from
a relation to an entity: the statements are **part of** the factoid. You write them with it, in the same call, and they
are read, changed and deleted with it. Contrast `source`, which points at an entity that exists on its own.

> **Entities are referred to; documents are contained.** A rule of thumb for any model you write: if two records could
> be about the *same* one, it is an entity, and records refer to it. If it only makes sense as part of the record that
> says it, it is a document inside that record. Leo's journey to Paderborn *as the Annals tell it* belongs to the Annals'
> factoid; another source's account of the journey is another statement, in another factoid.

### An abstract model

There is no such thing as a statement that is not some *kind* of statement, so `Statement` is **abstract**
(`Document.Meta(abstract=True)`): nothing can be created as a plain `Statement`. `Meeting` and `Journey` are subclasses:
each has the fields of `Statement` (here, `when`) and its own. `list[Statement | ...]` accepts any of them, and you will
see that each statement says which kind it is.

`_meta` is Pangloss's own meta attribute, like the `_interface_meta` of part 3.

### Someone, in a role

Leo was at the meeting **as a guest**. The role belongs neither to Leo (he was not always a guest) nor to the meeting as
a whole (Charles was the host): it belongs to the link *between* them. A relation that has fields of its own is a
**reified relation**:

```python
class InRole[T](ReifiedRelation[T]):
    role: Role
```

`InRole[Agent]` is "an agent, in a role". It is generic (the `[T]`) so that the same idea can be used for other targets:
`InRole[Place]` would be a place in some role. `Role` is an enum, so a role that is not one of the four is refused.

### A person or a group

A meeting's participants can be people, but also groups ("the Frankish nobles"). That is what a **trait** is for:

```python
class Agent(Trait): ...
class Person(Entity, Agent): ...
class Group(Entity, Agent): ...
```

`Agent` is not a model of its own; it is a label that `Person` and `Group` share, and a relation to `Agent` accepts
either. A trait can be given to models that have nothing else in common.

### Something that did not happen

Sources do not only say what happened. They say what did not, what might have, what someone wished. Pangloss keeps such
statements in a **semantic space**, a wrapper that puts what it contains in a context:

```python
class Negative[T](SemanticSpace[T]): ...
```

`Factoid.statements` accepts a `Statement`, or a `Negative[Statement]`: a statement that the source says is *not* the
case. The statement inside is an ordinary `Journey` or `Meeting`, with all its fields, so it can be searched like any
other; but it is marked as being in the negative space wherever it appears, so it cannot be mistaken for something that
happened.

### A date

`when: Date` is an **embedded** model, not a literal: a date is made of several values (a year, perhaps a month, how
certain it is) that Pangloss stores and indexes together, so that statements can be searched and ordered by date
whatever kind of date they have. The [dates guide](../dates/README.md) has every kind; here you only need the
simplest, a year.

## The migration

```console
$ pangloss makemigrations --name statements
chronicle.0003_statements
    - Create the enum Role (ENVOY, GUEST, HOST, WITNESS)
    - Create the index :Group
    - Create the index :Journey
    - Create the index :Meeting
    - Create the index :Statement
    - Create the Entity Group
    - Create the ReifiedRelation InRole
    - Create the Document Journey
    - Create the Document Meeting
    - Create the SemanticSpace Negative
    - Create the Document Statement
    - On Person: add the labels Agent
    - Add the relation field Factoid.statements
Wrote .../chronicles/chronicle/migrations/0003_statements.py
```

Notice two lines. *On Person: add the labels Agent*: the people already in the database are given the trait, so that a
relation to `Agent` finds them. *Add the relation field Factoid.statements*: the factoid you already have gets an empty
list of statements. Nothing needs to be asked, because an empty list is a sensible value for it.

> **Why the dates come in with the statements.** If you added a *required* field to statements that already existed,
> Pangloss would need a value for each of them, and for a date it cannot guess which kind of date to give. Adding the
> date with the model, before there are any statements, avoids the question. When you do need to change a model that has
> data, the [migrations guide](../migrations/README.md) shows how.

Apply it:

```console
$ pangloss migrate
...
  pangloss_dates.0001_initial: applying
  pangloss_dates.0001_initial: applied
  chronicle.0003_statements: applying
  chronicle.0003_statements: applied
Done
Models the migrations could have made unreadable: Person
Reading the data with the models ...
All 2 can be read
```

`pangloss_dates` came with a migration of its own, for its date models, and it runs first because yours needs it.

## Writing statements

Start a new interactive session (the models have changed), connect, and find what you made in part 2:

```python
>>> from shell import *
>>> await connect()
>>> charles = (await Person.list("charlemagne")).results[0]
>>> leo = (await Person.list("leo")).results[0]
>>> annals = (await Source.list("annals")).results[0]
>>> paderborn = await Place.Create(label="Paderborn").save()
>>> nobles = await Group.Create(label="The Frankish nobles").save()
```

Now a factoid with two statements: Leo travelled to Paderborn, and Charles received him there, with the nobles as
witnesses. A statement is written as a dictionary with a `"type"` saying which kind it is:

```python
>>> factoid = await Factoid.Create(
...     label="Leo is received at Paderborn",
...     source={"type": "Source", "id": annals.id},
...     page="s.a. 799",
...     text="The king received the pope at Paderborn with great honour.",
...     mentions=[{"type": "Person", "id": charles.id}, {"type": "Person", "id": leo.id}],
...     statements=[
...         {
...             "type": "Journey",
...             "label": "Leo travels to Paderborn",
...             "when": {"type": "ExactDate", "year": 799},
...             "traveller": {"type": "Person", "id": leo.id},
...             "destination": {"type": "Place", "id": paderborn.id},
...         },
...         {
...             "type": "Meeting",
...             "label": "Charles receives Leo",
...             "when": {"type": "ExactDate", "year": 799},
...             "at": [{"type": "Place", "id": paderborn.id}],
...             "participants": [
...                 {"type": "InRole", "role": "host", "target": [{"type": "Person", "id": charles.id}]},
...                 {"type": "InRole", "role": "guest", "target": [{"type": "Person", "id": leo.id}]},
...                 {"type": "InRole", "role": "witness", "target": [{"type": "Group", "id": nobles.id}]},
...             ],
...         },
...     ],
... ).save()
```

A few things to notice:

- Each statement has a **label** of its own, like any document.
- An `InRole` has a `role` and a `target`. The target is a **list**, of one agent here; several agents can share a role.
- `{"type": "Group", ...}` is accepted where an `Agent` is expected, and so is `{"type": "Person", ...}`.
- The date is `{"type": "ExactDate", "year": 799}`: the year 799, in the Julian calendar, because that is the setting.

Read it back:

```python
>>> found = await Factoid.get(factoid.id)
>>> [(s.type, s.label) for s in found.statements]
[('Meeting', 'Charles receives Leo'), ('Journey', 'Leo travels to Paderborn')]
>>> meeting = [s for s in found.statements if s.type == "Meeting"][0]
>>> [(p.role, p.target[0].label) for p in meeting.participants]
[(<Role.WITNESS: 'witness'>, 'The Frankish nobles'), (<Role.GUEST: 'guest'>, 'Pope Leo III'), (<Role.HOST: 'host'>, 'Charlemagne')]
```

A date is stored with more than you gave. Look at the meeting's:

```python
>>> when = meeting.when
>>> when.type, when.calendar, when.year, when.precision
('ExactDate', <Calendar.JULIAN: 'julian'>, 799, <Precision.YEAR: 'year'>)
>>> when.earliest_strict, when.latest_strict
(2012893, 2013257)
```

The year 799 is a range of days, and those two numbers are its first and last, counted as Julian Day Numbers, which do not
depend on any calendar's months. Whatever kind of date a statement has (a day, a year, "about 800", a range), it has these
numbers, so statements can be found and ordered by date together.

> **A list of relations has no order.** The statements, and the participants, did not come back in the order you wrote
> them. Pangloss keeps a list of relations as a *set*: what is in it, not where. (A list of literal values, like a
> person's `aliases`, does keep its order.) If the order matters to you, make it a field: a number, or a date.

And from Leo's side:

```python
>>> person = await Person.get(leo.id)
>>> [j.label for j in person.traveller_reverse]
['Leo travels to Paderborn']
```

Every field that points at an agent has its reverse on `Person`: `traveller_reverse`, `participants_reverse`. Leo's page
now gathers his journeys and his meetings, from every factoid, with the source of each.

## Saying what did not happen

In the autumn of 799 Leo went back to Rome, escorted by the king's envoys; Charles himself stayed in Francia and spent the
winter at Aachen. To record that the source has Charles *not* going to Rome with him, wrap the journey in a `Negative`:

```python
>>> rome = await Place.Create(label="Rome").save()
>>> envoys = await Group.Create(label="The king's envoys").save()
>>> factoid = await Factoid.Create(
...     label="Leo returns to Rome with the king's envoys",
...     source={"type": "Source", "id": annals.id},
...     page="s.a. 799",
...     text="The pope was escorted back to Rome by the king's envoys.",
...     mentions=[{"type": "Person", "id": charles.id}, {"type": "Person", "id": leo.id}],
...     statements=[
...         {
...             "type": "Journey",
...             "label": "The envoys take Leo to Rome",
...             "when": {"type": "ExactDate", "year": 799},
...             "traveller": {"type": "Group", "id": envoys.id},
...             "destination": {"type": "Place", "id": rome.id},
...         },
...         {
...             "type": "Negative",
...             "contents": [
...                 {
...                     "type": "Journey",
...                     "label": "Charles goes to Rome",
...                     "when": {"type": "ExactDate", "year": 799},
...                     "traveller": {"type": "Person", "id": charles.id},
...                     "destination": {"type": "Place", "id": rome.id},
...                 }
...             ],
...         },
...     ],
... ).save()
```

A semantic space has no label of its own; it has `contents`, the statements it holds. Now look at Charlemagne's
journeys:

```python
>>> person = await Person.get(charles.id)
>>> [(j.label, j.meta.semantic_spaces) for j in person.traveller_reverse]
[('Charles goes to Rome', ['Negative'])]
```

The journey is there, as it should be, because it is about him. But it carries `semantic_spaces=['Negative']`: anything
that shows or counts his journeys can tell that this is one the source says he did *not* make.

## In the interface

Restart `pangloss interface dev` (the models have changed) and open the factoids at <http://localhost:3000/Factoid>.
"Leo is received at Paderborn" shows its statements laid out inside it: the meeting, with each participant in a box with
their role, and the journey. (A date is shown for now as the values stored for it, the calendar, the precision and the day
numbers; a display made for dates is still to come.) "Leo returns to Rome with the king's envoys" shows the journey Charles did not make in a rose
band labelled *Negative*: the colour you gave `Negative` with `InterfaceMeta`.

## What you have done

Your factoids now say what their sources say happened, in a form that can be searched and counted, without losing what
each source said or which source said it. In [part 5](05-api.md) you reach the same data over HTTP.
