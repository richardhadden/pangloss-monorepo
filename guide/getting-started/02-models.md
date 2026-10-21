# 2. Your first models

Open `letters/models.py` and replace its contents with:

```python
from pangloss_models.model_bases.document import Document
from pangloss_models.model_bases.entity import Entity


class Person(Entity):
    """Someone who wrote or received a letter"""

    name: str


class Place(Entity):
    name: str


class Letter(Document):
    """A letter, from one person to another"""

    text: str
    sent_by: Person
    sent_to: Person
    sent_from: list[Place]
```

That is all the code you write for the data model. Here is what it says.

## Two kinds of model

- An **`Entity`** is a real-world thing that other records refer to: a person, a place, a group. Many letters mention the same Ada Lovelace, and they should all point at the *one* `Person`. An entity exists on its own.
- A **`Document`** is a record: a letter, a statement, a claim. It can contain nested documents, and it refers to entities.

There are other kinds ([Defining models](../../docs/models.md) has them all); these two are enough to start.

## Fields

`name: str` and `text: str` are **literal** fields: a plain value stored on the node. Besides `str` you can use `int`, `float`, `bool`, `Decimal`, `date`, `datetime`, enums, and lists of these. `X | None` makes a literal optional.

`sent_by: Person` is a **relation**: a field whose type is another model. It is stored as an edge from the letter to the person, and the person is *referred to*, not copied. Every `Letter` must have exactly one `sent_by` and one `sent_to`.

`sent_from: list[Place]` is a relation that can be empty or have several places. (A relation is either required, or a list. There is no `Place | None` for a relation: use a list for "may be empty".)

Every Pangloss object also gets a `label` (a short human-readable name, required) and an `id` (generated), without you declaring them.

## What was generated

Each class gives you more than itself. After Pangloss reads your models, `Letter` has:

| | |
|---|---|
| `Letter.Create` | The model for making a letter: the fields you wrote, plus `label`. Relations are given as references (`{"type": "Person", "id": ...}`) |
| `Letter.Update` | The same, for replacing one |
| `Letter.HeadView` | What you get back when you read a letter: your fields, with each relation as a short summary of the thing it refers to, and a `meta` (who created it and when) |
| `Letter.get(id)`, `Letter.list()`, `Letter.delete(id)` | Reading and deleting |

The same goes for `Person` and `Place`. You will use these in [part 4](04-data.md), and the REST API is made from them in [part 5](05-api.md).

## A note on types

You can also ask for type stubs, so that your editor completes `Letter.Create(...)` and knows what `get` returns:

```console
$ pangloss make-stubs
```

It writes `letters/models.pyi` next to the models. Run it again when you change them.

Now the database has to learn about these models: [part 3](03-database.md).
