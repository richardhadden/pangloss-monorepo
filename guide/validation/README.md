# Checking data, working things out, and methods

Your models are pydantic classes, and what you would write in a pydantic class works in them: validators, constraints,
methods, properties. This guide shows each, says when it runs, and adds the two things Pangloss has that pydantic does
not: values worked out for the database alone, and checks that need the database (or the version that is there now).

The examples use the models of [Getting started](../getting-started/02-models.md): `Person`, `Place` and `Letter`.

## Which one for which job

| I want to… | Use | Runs |
|---|---|---|
| Refuse a value, or tidy it (strip spaces, a pattern, a range) | a constraint (`Annotated[int, Ge(1)]`, `Field(pattern=...)`) or a `@field_validator` | when a `Create` or `Update` is made |
| Check fields against each other | a `@model_validator` | the same |
| Keep something worked out from the data, for searching or sorting | a `DBField`, filled in by a `@create_validator` / `@update_validator` | on the server, as it is written |
| Refuse a write by what is in the database, or by what the item was before | `@before_create` / `@before_update` | on the server, before it is written |
| Ask an item something (`letter.word_count()`, `person.initials`) | a method or a property | whenever you call it, on what you made or read |

## Checking and tidying values

Constraints and validators are pydantic's own, and they mean what they mean in pydantic:

```python
from typing import Annotated

from annotated_types import Ge
from pangloss_models import Document, Entity
from pydantic import field_validator, model_validator


class Person(Entity):
    name: str
    born: Annotated[int, Ge(0)] | None

    @field_validator("name")
    @classmethod
    def tidy(cls, value: str) -> str:
        return " ".join(value.split())


class Letter(Document):
    text: str
    sent_by: Person
    sent_to: Person
    sent_from: list[Place]
    year: int | None
    sent: bool = False

    @model_validator(mode="after")
    def not_unsent_and_dated(self):
        if self.year is not None and not self.sent:
            raise ValueError("a letter that was not sent has no year of sending")
        return self
```

They run when the `Create` or `Update` is made, which is where the data comes in: `Person(label=..., name=...)` in a
script, a request to the API, a form in the interface (which shows the API's answer at the field), or the SDK in a
colleague's notebook (where they run before anything is sent, and again on the server). Each runs **once** for each
of these: not again when Pangloss turns the `Create` into what it writes.

```python
>>> Person(label="Ann", name="  Ann   Smith ").name
'Ann Smith'
>>> Person(label="Ann", name="Ann", born=-5)
Traceback (most recent call last):
  ...
pydantic_core._pydantic_core.ValidationError: 1 validation error for PersonCreate
born
  Input should be greater than or equal to 0 [type=greater_than_equal, ...]
```

Two things differ from a plain pydantic class:

- In a `@model_validator`, a relation is a **reference** (`self.sent_by.id`, and perhaps a `label`), not the person:
  the person is in the database. To check something about the person, use `@before_create` (below).
- A `mode="before"` validator is given the keys in snake_case (`sent_by`), whether the payload used them or the
  camelCase the API speaks (`sentBy`).

A `@field_validator` is for a literal field (a value of the class's own). One of a relation is an error at
`initialise()`: use a `@model_validator`, or `@before_create`.

## Working out what is stored

Some values are worth keeping in the database without anyone typing them: a count to sort by, a normalised form to
search for, the first and last day an uncertain date may be (which is what [`pangloss-dates`](../dates/README.md)
does). Declare the field as a `DBField`, so that it is not in what a client sends or is given, and fill it in with a
`@create_validator` and an `@update_validator`:

```python
from pangloss_models import DBField, create_validator, update_validator


class Letter(Document):
    text: str
    ...
    # (only in the database: for sorting and searching)
    words: Annotated[int | None, DBField] = None

    @create_validator
    @update_validator
    def count_the_words(self):
        self.words = len(self.text.split())
```

A `@create_validator` runs on what is written when something is new, an `@update_validator` when it is written again;
one function may have both. They run on the server, after the fields are validated, so a field they fill in needs a
default (`= None`), and they return nothing (they change `self`). Raising `ValueError` refuses the write, as a
validator does.

You can search and sort by such a field (`Letter.search(Letter.Where(words={"gt": 100}))`), and index it
(`Meta(indexes=["words"])`). It is not in what is read back (`Letter.HeadView`): it is the database's.

## Checks that need the database

Some rules cannot be checked from the data alone: that no other person has the same name, that a letter that has been
sent is not changed. `@before_create` and `@before_update` are `async`, run on the server before anything is written,
can read the database through your models, and refuse the write with `PanglossWriteRefused`:

```python
from pangloss_models import Match, PanglossWriteRefused, before_create, before_update


class Person(Entity):
    name: str

    @before_create
    async def no_namesake(self):
        found = await Person.search(Match(where={"name": {"eq": self.name}}))
        if found.results:
            raise PanglossWriteRefused(f"There is already a person called {self.name}", field="name")


class Letter(Document):
    ...

    @before_update
    async def not_once_sent(self, previous):
        if previous.sent and self.text != previous.text:
            raise PanglossWriteRefused("A letter that was sent cannot be changed", field="text")
```

`self` is what is about to be written; in `@before_update`, `previous` is the item as it is in the database now (a
`HeadView`). When one refuses, nothing is written:

```python
>>> await Person(label="Ann", name="Ann Smith").save()
>>> await Person(label="Ann again", name="Ann Smith").save()
Traceback (most recent call last):
  ...
pangloss_models.exceptions.PanglossWriteRefused: There is already a person called Ann Smith
```

Over the API the answer is a 422, in the shape of pydantic's own errors, so the interface shows the reason at the field
you named (`field="name"`; leave it out for a reason that is about the whole item, which the interface shows as a
message). The SDK raises the same `PanglossWriteRefused`, with its `field`.

What is nested is checked too. When a letter is written, every part of it that has these checks is checked: a nested
document, an embedded object, a reified relation, an entity made with `create_new`. In an update, a part that was
already there has its `@before_update`, with `previous` being that part as it is now; a part that is new has its
`@before_create`. A refusal says where it is: `refused.path` is `("clauses", 1, "text")` for the text of a letter's
second clause, and the interface marks that field, in that clause.

These checks run for every write the models make: a request to the API, a script, `bulk-load` (where a record that is
refused stops the load at its line, and what came before it stays written). The SDK's client does not run them
itself: it sends the write, and the server runs them. They run just before the write, not inside its transaction, so
two writes made at the same moment can both pass a check like `no_namesake`. For a rule that must hold whatever the
timing, use a database constraint.

## Methods and properties

A method or property you declare is on every model made from the class: what you make (`Person(...)` is a
`Person.Create`), what you read back (`await Person.get(id)` is a `Person.HeadView`), and what the SDK gives:

```python
class Person(Entity):
    first: str
    last: str

    def full_name(self) -> str:
        return f"{self.first} {self.last}"

    @property
    def initials(self) -> str:
        return self.first[0] + self.last[0]
```

```python
>>> ada = await Person.get(ada_id)
>>> ada.full_name(), ada.initials
('Ada Lovelace', 'AL')
```

`pangloss make-stubs` writes them into the stubs too, so your editor knows them.

On these models a relation is a reference, so a method can use `self.sent_by.label` but not `self.sent_by.born`. A
reference itself (`Person.ReferenceView`, which is what a relation holds) has only the id and the label, and not the
methods. A method may not have the name of a field (`id`, `label`, `meta`) or of what Pangloss gives the class
(`save`, `get`, `search`, `list`, `delete`, ...): that is an error at `initialise()`.

A `@computed_field` is not supported (it would change what the API gives, for everyone); Pangloss warns of one at
`initialise()`. Use a property, or a `DBField` that a `@create_validator` fills in.

## Where to read more

- [Validators, write checks and methods](../../implementation_docs/generated-models.md#validators-write-checks-and-methods-), the
  reference, with what is on which generated model.
- [Defining models](../../implementation_docs/models.md) and [Fields](../../implementation_docs/relations.md).
