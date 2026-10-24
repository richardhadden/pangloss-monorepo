# 2. Everyday workflow

This chapter follows one model through a few typical changes. The output shown is abridged; yours will list more detail.

## The first migration

You have a new project with a model:

```python
# library/models.py
class Person(Entity):
    name: str
```

Write the first migration and apply it:

```console
$ pangloss makemigrations
library.0001_initial
    - Create the Entity Person
Wrote library/migrations/0001_initial.py

$ pangloss migrate
To apply:
  library.0001_initial
    - Create the Entity Person
  library.0001_initial: applying
  library.0001_initial: applied
Done
Nothing that exists is affected by these migrations: no data to read
```

Commit the migration file with your code. It is part of the project, just like `models.py`.

> **A new project's database.** The first `migrate` also makes the indexes and constraints Pangloss needs, through the migrations that `pangloss_memgraph` itself ships. You do not need `pangloss setup-database` for a project that has migrations.

## A change that needs no answers

Add an **optional** field:

```python
class Person(Entity):
    name: str
    nickname: str | None
```

```console
$ pangloss makemigrations
library.0002_addfield_person_nickname
    - Add the literal field Person.nickname
Wrote library/migrations/0002_addfield_person_nickname.py

$ pangloss migrate
```

Nothing is asked: existing people simply have no nickname. Nothing is read afterwards either, because nothing that exists could have been made unreadable.

## A change that asks for a value

Add a **required** field:

```python
class Person(Entity):
    name: str
    nickname: str | None
    born: int
```

```console
$ pangloss makemigrations
A value for Person.born on the nodes that exist: 1900
library.0003_addfield_person_born
    - Add the literal field Person.born (a value is needed for the nodes that exist)
Wrote library/migrations/0003_addfield_person_born.py
```

Every person already in the database gets `born = 1900`. The answer is typed (an `int` here; dates are `2024-05-01`) and is written into the migration file as `'default': 1900`. Someone else running `migrate` later will not be asked anything.

When you apply it, Pangloss reads the data back with the new models, to be sure it is still all readable:

```console
$ pangloss migrate
...
Done
Models the migrations could have made unreadable: Person
Reading the data with the models ...
All 214 can be read
```

## A rename

Pangloss cannot tell a rename from "removed one field, added another". It **always asks**:

```python
class Person(Entity):
    name: str
    nickname: str | None
    birth_year: int  # was: born
```

```console
$ pangloss makemigrations
In 'Person', was the field 'born' renamed to 'birth_year'? [y/N]: y
library.0004_renamefield_person_born_birth_year
    - Rename the field Person.born to birth_year
```

Answer `y` and the existing values move across. Answer `n` and you get a *removal* of `born` (which loses its values, and is marked **`[LOSES DATA]`**) plus an *addition* of `birth_year` (which asks for a value). The same question is asked for renamed models, enums and enum members.

## A change that loses data

Remove a field:

```console
$ pangloss makemigrations
library.0005_removefield_person_nickname
    - Remove the literal field Person.nickname and its data  [LOSES DATA]
```

Writing the migration is harmless. Applying it is where the care goes:

```console
$ pangloss migrate
Some of these lose data: give --backup (take a snapshot first) or --no-backup (you have your own)

$ pangloss migrate --backup
Some of these lose data. Go on? [y/N]: y
Backup: /var/lib/memgraph/snapshots/20261021…
```

More on this in [chapter 4](04-safety.md). Use `--yes` to skip the confirmation in scripts (you still must choose `--backup` or `--no-backup`).

## Looking before you leap

```bash
pangloss makemigrations --dry-run     # what would be written; writes nothing
pangloss migrate --plan               # what would be applied; applies nothing
pangloss migrate --dry-run            # actually tries it, then rolls it back (chapter 4)
pangloss showmigrations               # [X] applied   [ ] pending   [!] failed   [~] running
```

`showmigrations` looks like this:

```
pangloss_memgraph
 [X] 0001_initial
library
 [X] 0001_initial
 [X] 0002_addfield_person_nickname
 [ ] 0003_addfield_person_born
```

## The day-to-day loop

1. Change `models.py`.
2. `pangloss makemigrations` — read what it says it will do. Answer its questions.
3. `pangloss migrate` on your development database. Check things work.
4. Commit `models.py` **and** the new migration together.
5. Teammates and deployments run `pangloss migrate` when they pull.

A few habits that pay off:

- **Read the list of changes** `makemigrations` prints, especially anything marked `[LOSES DATA]`. It is a summary of what you are about to do to real data.
- **Make one logical change at a time.** Small migrations are easier to check, to undo, and to review.
- **Never edit a migration that has been applied** anywhere other than your own machine. Pangloss will refuse (the checksum no longer matches). If you made a mistake, write a new migration that fixes it. A migration that has *not* been applied anywhere yet can be deleted and regenerated freely.
- **Run `pangloss makemigrations --check` in CI.** It exits with an error if someone changed a model and forgot the migration.

## Checking the data

`pangloss migrate` reads the data affected by the migrations it just applied. You can also read *everything* at any time:

```bash
pangloss check-data                     # every document and entity
pangloss check-data --type Person       # only one model (repeat --type for more)
pangloss check-data --limit 100         # at most 100 of each model
```

It reads each stored item with the current models and prints `All 214 can be read`, or `3 of 214 cannot be read:` followed by the first twenty errors (`Person 01a1… (Ann): born: Field required`); in the second case it exits with an error. This is the same read the API does, so "can be read" means "the application can show it".

On a large database a full check takes time (roughly 1.5 ms for a simple node, a few ms for a document with many nodes). `migrate --check-all` does a full check after applying; `migrate --no-check` skips the check.

## What the server does at start-up

If you forget a step, the API tells you rather than running against the wrong data:

```
The database and the models do not agree with the migrations:
  1 migrations have not been applied (library.0003_addfield_person_born): run `pangloss migrate`
```

or `The models are not what the migrations come to: run `pangloss makemigrations``. See [chapter 1](01-ideas.md#the-server-checks-too) for the setting that controls this.
