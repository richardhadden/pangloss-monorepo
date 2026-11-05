# Part 7: Testing

Your models are rules: a participant has one of four roles, a person has a list of aliases, a statement can be said not
to have happened. As the project grows and the models change, tests make sure the rules you rely on still hold. In this
part you write tests for them with [pytest](https://docs.pytest.org/), which comes with Pangloss's development
environment.

## Tests without a database

The models check data *before* it reaches the database: `Factoid.Create(...)` refuses a bad role on the spot. So the
rules of your models can be tested with no database at all, which keeps the tests fast and safe to run anywhere.

Make a directory `tests/` in the project, and in it a `conftest.py`, which pytest reads first:

```python
import pytest
from pangloss_cli import load_project
from pangloss_models import initialise


@pytest.fixture(scope="session", autouse=True)
def models():
    """The project's settings and models, as `pangloss` loads them (no database is used)"""
    project = load_project(argv=[])
    project.import_models()
    initialise(bind_database=False)
```

This is the setup from `shell.py`, without connecting: `bind_database=False` makes the classes without the functions that
read and write, so nothing here can touch your data.

Then `tests/test_models.py`:

```python
import uuid

import pytest
from pydantic import ValidationError

from chronicle.models import Factoid, Person


def ref(type_: str) -> dict:
    """A reference to something (the tests never save, so it need not exist)"""
    return {"type": type_, "id": uuid.uuid4()}


def journey(label: str) -> dict:
    return {
        "type": "Journey",
        "label": label,
        "when": {"type": "ExactDate", "year": 799},
        "traveller": ref("Person"),
        "destination": ref("Place"),
    }


def factoid(statements: list) -> Factoid.Create:
    return Factoid.Create(
        label="A factoid", source=ref("Source"), page="1", text="...", mentions=[], statements=statements
    )


def test_a_person_needs_a_list_of_aliases_even_if_it_is_empty():
    with pytest.raises(ValidationError, match="aliases"):
        Person.Create(label="Einhard", has_type=[])
    Person.Create(label="Einhard", aliases=[], has_type=[])


def test_a_participant_has_one_of_the_roles():
    meeting = {
        "type": "Meeting",
        "label": "A meeting",
        "when": {"type": "ExactDate", "year": 799},
        "at": [],
        "participants": [{"type": "InRole", "role": "bishop", "target": [ref("Person")]}],
    }
    with pytest.raises(ValidationError, match="'host', 'guest', 'envoy' or 'witness'"):
        factoid([meeting])


def test_a_statement_can_be_said_not_to_have_happened():
    made = factoid([{"type": "Negative", "contents": [journey("Charles goes to Rome")]}])
    assert made.statements[0].type == "Negative"
    assert made.statements[0].contents[0].label == "Charles goes to Rome"


def test_a_statement_is_always_some_kind_of_statement():
    plain = {"type": "Statement", "label": "Something", "when": {"type": "ExactDate", "year": 799}}
    with pytest.raises(ValidationError):
        factoid([plain])
```

Run them from the project directory:

```console
$ python -m pytest -q tests
....                                                                     [100%]
4 passed in 0.31s
```

Each test is about one rule, and its name says which. The last one checks that `Statement` really is abstract: a
statement must be a `Meeting` or a `Journey`. If someone later removes `abstract=True`, a test fails and says why.

## What a test of the models is for

Tests like these catch the changes you did not mean to make. Suppose you rename the role `GUEST` to `VISITOR`: a test
that writes `"guest"` fails, which reminds you that the data, the interface's labels and any scripts that send
`"guest"` all need changing too, and that the migration will have to say what becomes of the guests already recorded.

Tests that need the database (that saving and reading give back what was written, that a search finds what it should)
are not covered here. Pangloss's own packages have fixtures for them in `pangloss-testing`, but they are made for testing
Pangloss itself and use a database at a fixed address that they empty; a version for projects is not there yet.

## Where to go from here

You have built an application: models of entities and of documents with statements inside them, roles, a trait, a
semantic space, dates, a typology and review, seen in Python, in the browser and over HTTP, with tests for its rules.
From here:

- **Change your models with confidence.** The [migrations guide](../migrations/README.md) covers what this tutorial did
  not: renaming a field (Pangloss asks whether it was a rename or a removal and an addition), taking a field away, going
  back, backups, migrations written by hand. Read [chapter 2](../migrations/02-workflow.md) and
  [chapter 4](../migrations/04-safety.md) first.
- **Find things.** [Searching](../search/README.md): lists, autocomplete, and structured search by a pattern ("every
  meeting at which a pope was a guest").
- **Model more.** [Defining models](../../docs/models.md) and [Relations and fields](../../docs/relations.md) have the
  rest: properties on a relation itself (how certain a source is that Leo was the guest), conjunctions ("one of these
  people"), binding a value into the statements of a factoid, and more. The demo (`pangloss-demo/demo_app/models.py`)
  uses nearly all of it, with comments.
- **Work with others.** [Users, logins and the API](../accounts/README.md) for accounts and tokens; [the SDK](../sdk/README.md)
  for colleagues who want to script against your data.
- **Choose a database.** Everything in this tutorial works the same on Neo4j: [Choosing and running a database](../backends/README.md).

Good luck with your sources.
