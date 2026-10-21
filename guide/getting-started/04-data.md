# 4. Writing and reading data

Your models are ordinary Python classes, so you can use them from any Python code. Make a file `play.py` in the project directory (next to `pyproject.toml`):

```python
import asyncio

from letters.models import Letter, Person, Place
from pangloss_cli.project import load_project
from pangloss_models import initialise
from pangloss_users import current_request_username


async def main():
    # Load the project's settings, import its models, and generate everything from them
    project = load_project()
    backend = project.require_database()
    project.import_models()
    initialise()

    current_request_username.set("alice")  # what is written is recorded as written by this user
    await backend.connect()
    try:
        ada = await Person.Create(label="Ada Lovelace", name="Ada Lovelace").save()
        babbage = await Person.Create(label="Charles Babbage", name="Charles Babbage").save()
        london = await Place.Create(label="London", name="London").save()

        letter = await Letter.Create(
            label="Ada to Babbage, 1843",
            text="My dear Babbage ...",
            sent_by={"type": "Person", "id": ada.id},
            sent_to={"type": "Person", "id": babbage.id},
            sent_from=[{"type": "Place", "id": london.id}],
        ).save()

        found = await Letter.get(letter.id)
        print(found.label, "- from", found.sent_by.label, "to", found.sent_to.label)

        page = await Letter.list()
        print(page.count, "letter(s):", [item.label for item in page.results])

        person = await Person.get(ada.id)
        print(person.label, "wrote:", [item.label for item in person.sent_by_reverse])
    finally:
        await backend.disconnect()


asyncio.run(main())
```

Run it:

```console
$ python play.py
Ada to Babbage, 1843 - from Ada Lovelace to Charles Babbage
1 letter(s): ['Ada to Babbage, 1843']
Ada Lovelace wrote: ['Ada to Babbage, 1843']
```

## What it did

- **`initialise()`** generates `Create`, `View` and the rest from your classes. It must be called once, after all the models are imported. (Servers and commands do this for you; a script has to.)
- **`Person.Create(...).save()`** checks the values (it is a Pydantic model, so a missing `name` or a `name=3` is an error at this line), writes the node, and returns a short reference to it, with the new `id`.
- **Relations are given as references**: `{"type": "Person", "id": ada.id}`. The letter does not contain Ada; it points at her. If the id does not exist, the write raises `PanglossReferenceError` ("Invalid references to existing objects: sent_by: '...' not found") and nothing is written.
- **`Letter.get(id)`** reads one back as a `Letter.HeadView`. `found.sent_by` is a summary of the person (their `id`, `label` and `type`), not the whole person.
- **`Letter.list()`** returns a page: `results`, `count`, `page`, `page_size`. Search and paging are options of `list`.
- **`Person.get(...)` shows the other direction.** You never declared a field on `Person` for the letters, but `sent_by_reverse` is there: every relation is stored both ways, so an entity can list everything that refers to it. This is the reason to make Ada a `Person` once and refer to her, instead of writing her name in each letter.

## Updating and deleting

```python
await Letter.Update(id=letter.id, label="Ada to Babbage", text="...", sent_by=..., sent_to=..., sent_from=[...]).save()
await Letter.delete(letter.id)
```

An update replaces the record with what you give (it is the whole letter again, not a patch: a `sent_from=[]` empties the places), and the letter's `meta.version` goes up by one. Deleting does not erase anything for good: the letter is flagged as deleted and every read leaves it out. An entity that something still refers to cannot be deleted. See [Defining models](../../docs/models.md#deleting).

Next: do the same over HTTP, with [the REST API](05-api.md).
