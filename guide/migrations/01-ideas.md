# 1. The ideas

## Models, data, migrations

There are three things, and a migration connects two of them.

- **Models** are the Python classes you write (`class Person(Entity): ...`). They are the *current* truth about the shape of your data.
- **Data** is what is in the database. It was written with whatever models you had at the time.
- **Migrations** are files in your app's `migrations/` folder, numbered in order: `0001_initial.py`, `0002_addfield_person_born.py`, and so on. Together they are the *history* of how the models got to where they are.

`makemigrations` compares your models with the history and writes the difference as a new migration. `migrate` applies the migrations the database has not had yet, and keeps a record of which it has had.

```
 models.py ──makemigrations──▶ migrations/0003_….py ──migrate──▶ database
   (what you want)              (how to get there)               (what you have)
```

## What a migration file looks like

A migration is an ordinary Python file, written for you to read and, where needed, to edit:

```python
"""0002_addfield_person_born"""

from pangloss_models.meta_kit.migrations.files import changes_from_data

dependencies = []
schema_hash = '3f9a…'

changes = changes_from_data([
    {'change': 'AddField',
     'model': 'Person',
     'name': 'born',
     'field_kind': 'literal',
     'needs_value': True,
     'default': 1900,          # <- the answer you gave when asked
     ...},
])
```

Each entry in `changes` is one **change**: "add this field", "rename that model", "convert this value". A migration is a list of changes, applied in order.

You rarely need to read these, but it is worth knowing that:

- the file is **data**, not code that imports your models. A migration written two years ago still runs after the models have changed beyond recognition;
- your **answers** are written into it (the `default: 1900` above), so the migration does the same thing every time and on every machine;
- it is **checksummed**: once a migration has been applied, editing it is refused (a fix is a new migration).

## What Pangloss stores, and so what can need migrating

Not every change to a class changes the data. Pangloss only migrates what is **stored**:

- adding, removing or renaming a **model**, or changing what it inherits (its labels in the database);
- adding, removing, renaming or retyping a **field**;
- the **kind** of a field (a plain value, a list, a relation, an embedded object...);
- what a **relation** may point to, whether it is a list or one value, its reverse name, properties on its edges, and whether it is wrapped in a reified relation or a semantic space;
- the **members and values of an enum** (the values are what is stored);
- the database's own **indexes and constraints**.

Things that are *not* stored are ignored, so changing them never makes a migration: docstrings, validators, whether a field has a default in Python, and the order you declare things in. (Validators are checked when data is written and by `check-data`, not stored.)

## How safe is a change?

Every change has a safety level, which `makemigrations` and `migrate` show you:

| Level | Meaning | Example |
|-------|---------|---------|
| safe / additive | nothing existing is touched, or only new things are made | a new model; a new optional field |
| transforming | existing data is rewritten, but nothing is lost | a rename; `int` becomes `str`; wrapping a relation |
| **lossy** | information is removed and cannot be brought back | removing a field; removing a model; unwrapping a relation |
| **by hand** | Pangloss cannot do it: `migrate` stops (and `--dry-run` says so) and you write it ([chapter 6](06-by-hand.md)) | wrapping in a conjunction; a type conversion it does not know |

One thing is **not allowed at all**: changing the **kind** of a model (an `Entity` that becomes a `Document`, or the reverse) or of a field (a plain value that becomes a relation). They are stored differently and nothing can be made of one from the other. `makemigrations` refuses, and says so: keep the kind, or make a new model or field and move the data to it.

Lossy changes are marked **`[LOSES DATA]`** everywhere you see them, and `migrate` will not apply one until you have said how you are protecting yourself (a backup, or `--no-backup`) and confirmed.

## Things Pangloss will never guess

Pangloss asks you, rather than assuming, whenever the answer changes your data:

- **Renames.** A field that disappears while another of the same kind appears *might* be a rename, or a removal plus an addition. Pangloss always asks; a wrong guess would silently throw data away.
- **Values for existing records.** If you add a required field, what do the records that are already there get?
- **What to do with values that don't convert**, and a few similar cases (see [chapter 3](03-changes.md)).

Your answers are kept in the migration file. You are only asked once.

## Where migrations live, and how many databases they apply to

Each **app** in `INSTALLED_APPS` has its own `migrations/` folder next to its `models.py`. The migrations of all apps together form one history, ordered by their declared dependencies (see [chapter 7](07-projects.md)).

The database keeps a record of what it has had: a `PGMigration` node for each applied migration (when, by whom, how long it took, and its checksum). That is how `migrate` knows what is pending, and how it notices if a file was edited after it was applied.

Your development database, your colleagues', staging and production each have their own record. The same migration files bring each of them up to date.

## The server checks, too

When the API starts it compares the database and the models with the migrations. It refuses to start if:

- there are migrations not yet applied,
- an applied migration was edited or is missing,
- or the models have changed since the migrations were written (you forgot `makemigrations`).

This stops you running new code against old data, or the reverse. The setting `MIGRATION_CHECK` controls it: `"error"` (the default) refuses to start, `"warn"` starts and warns, `"off"` does not look. A project with no migrations is not checked.
