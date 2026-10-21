# 6. Changing a model

Models change. You realise a letter should have a year. Edit `letters/models.py`: add a **required** field.

```python
class Letter(Document):
    """A letter, from one person to another"""

    text: str
    year: int
    sent_by: Person
    sent_to: Person
    sent_from: list[Place]
```

Your database already has a letter without a year, so the models and the data now disagree. A migration brings them together:

```console
$ pangloss makemigrations
A value for Letter.year on the nodes that exist: 1843
letters.0002_addfield_letter_year
    - Add the literal field Letter.year (a value is needed for the nodes that exist)
Wrote letters/migrations/0002_addfield_letter_year.py
```

Pangloss saw a new required field and cannot invent a value, so it asked. Every letter that exists gets `1843`. (If you added `year: int | None`, nothing would be asked: existing letters would simply have no year.) Your answer is written into the migration file, so anyone else who runs it later is not asked.

Before you apply it, try it. A **dry run** does the migration for real inside a transaction, says what it did, and rolls everything back:

```console
$ pangloss migrate --dry-run
To apply:
  letters.0002_addfield_letter_year
    - Add the literal field Letter.year (a value is needed for the nodes that exist)

Tried, and rolled back:
  letters.0002_addfield_letter_year
    - Add the literal field Letter.year (a value is needed for the nodes that exist)
        1 properties set
Nothing was changed
```

One property would be set: one letter. Now apply it:

```console
$ pangloss migrate
  letters.0002_addfield_letter_year: applying
  letters.0002_addfield_letter_year: applied
Done
Models the migrations could have made unreadable: Letter
Reading the data with the models ...
All 1 can be read
```

The last lines are a check Pangloss makes for you: it read every `Letter` back with the new model, to be sure that all the data can still be read.

Now `year` is part of everything. Add `year=1843,` to the `Letter.Create(...)` in `play.py` and run it again; `Letter.get` has `year`, and so does the JSON of the API. (A `Create` without it now fails: `year` is required.)

## Where to go from here

- **Migrations** have more to them than this: renaming a field (Pangloss asks whether it was a rename or a removal plus an addition), going back, backups before something that loses data, writing a migration by hand. Read the [migrations guide](../migrations/README.md); chapters [2](../migrations/02-workflow.md) and [4](../migrations/04-safety.md) first.
- **More kinds of model**: nested documents, embedded objects, relations that carry fields of their own (a letter *sent via* someone, with a date), a context in which statements hold, traits ("any of these entities"). [Defining models](../../docs/models.md) and [Relations and fields](../../docs/relations.md) describe them, and the demo project (`pangloss-demo/`, built step by step in [the demo setup](../../docs/demo-setup.md)) uses most of them.
- **The command line**: [Command line](../../docs/cli.md).
- **The web interface**: the optional `pangloss-interface` package gives a front-end made from your models: [The interface](../../docs/interface.md).
