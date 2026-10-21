# 8. When something goes wrong

Find the message you got; each entry says what it means and what to do.

## The server will not start

```
The database and the models do not agree with the migrations:
  2 migrations have not been applied (library.0003_…, library.0004_…): run `pangloss migrate`
```

The database is behind the code. Run `pangloss migrate`.

```
The models are not what the migrations come to: run `pangloss makemigrations`
```

Someone changed a model and no migration records it. Run `pangloss makemigrations`, review, `migrate`, and commit the file. (Or, if you did not mean to change the model, undo the change in `models.py`.)

```
library.0002_… was applied, and has been changed since (a fix is a new migration)
library.0002_… was applied, but there is no such migration
library.0004_… was applied, but library.0003_…, which it follows, was not
```

The files and the database's record disagree.

- *Changed since*: you (or a merge) edited a migration that had run. Restore the file from version control (`git checkout`). If the edit was a real fix, put the file back and write a new migration for the fix.
- *No such migration*: a file was deleted. Restore it. (If you [squashed](05-back-and-squash.md) and deleted the originals, keep the squashed migration: it covers them.)
- *Which it follows, was not*: migrations were applied out of order, usually by hand-editing the record. Use `migrate --fake` carefully to put the record right, or ask someone who knows.

You can silence the server's check with `MIGRATION_CHECK = "warn"` or `"off"` while you sort it out. Not in production.

## `makemigrations`

**"These need an answer (so no migration is written without asking)"** — you ran with `--noinput` and Pangloss needed to ask something (a rename, a value). Run it without `--noinput`.

**It asks a rename question I don't understand.** It is asking whether a field/model/enum that has disappeared is the same thing as one that has appeared. Answer `y` only if the *values should move across*. If unsure, answer `n`, read the migration it writes (`--dry-run` first), and re-run: the removal will be marked `[LOSES DATA]`, which tells you what `n` costs.

**It wrote a change marked `[NEEDS CODE]`.** Pangloss found a change it cannot apply automatically. See [chapter 6](06-by-hand.md).

**It says "No changes" but I changed the model.** You may have changed something that is not stored (a docstring, a validator, a default in Python, the order of fields). That is correct; nothing to migrate.

**I answered a question wrongly.** If you have not applied the migration, delete the new migration file and run `makemigrations` again. If you have, edit nothing: write a new migration, or [go back](05-back-and-squash.md) first on your own database.

## `migrate`

### It stops with "needs an answer"

A change was written without an answer it needs (a hand-written migration, or one where an answer could not be asked). The message is the change followed by what it wants, with the name of the setting in backticks:

```
Make Person.born required: a value where there is none (`default`)
```

Add that setting to the change in the migration file ([chapter 3](03-changes.md#editing-the-answers-in-the-file)). Nothing was changed.

### A value does not convert

```
3 values of Person.born cannot be converted (Person.born: type str -> int): say what to do with them (`on_failure`: 'null' or 'default')
```

You changed a field's type and some stored values do not fit. Nothing was changed. Either fix the data first (for example, with a hand-written migration before this one), or choose what happens to such values with `on_failure` (`'null'` or `'default'`) in the migration file. The message says how many; query the database to find them.

### Narrowing or list-to-single fails

A relation that may no longer point to some model, or a list that is now a single value, found data that does not fit. Either fix the data, or accept the loss with `on_narrowing: 'remove'` / `keep: 'first'` in the file.

### A uniqueness constraint fails

```
Cannot make Require :Thing(name) to be unique: ... (the data may break it already)
```

Duplicates exist. Remove or merge them, then run `migrate` again.

### "Another migrate is running, or was stopped without finishing"

Check that no `migrate` is really running, then `pangloss migrate --unlock`.

### A migration shows `[!]` failed or `[~]` running in `showmigrations`

`[!]` failed: the error is kept in the database's record. Fix the cause and run `migrate` again; it is tried from the start (or, if it was in batches, from where it got to). `[~]` running: a run was killed; `--unlock`, then `migrate`.

### It says "The migrations and the record of them in the database do not agree"

See "The server will not start", above: it is the same check.

### "Some of these lose data: give --backup or --no-backup"

Intentional. Choose one ([chapter 4](04-safety.md#backups)).

### It is very slow, or runs out of memory

A migration is one transaction. For a large database use `--batch-size` ([chapter 4](04-safety.md#large-databases-batches)).

## After a migration

### "N of M cannot be read"

```
2 of 214 cannot be read:
  Person 01a1… (Ann): born: Field required
```

The migration itself succeeded, but the data does not fit the new models. Typical causes: you added a required **relation** (Pangloss cannot invent a target; existing records have none); or data was already invalid before. Fix the records (through the API, or a hand-written migration), then `pangloss check-data` to confirm.

## Going back

**"cannot be undone: …"** — a change in that migration has no inverse ([chapter 5](05-back-and-squash.md#what-cannot-be-undone)). Nothing was changed. If it is a hand-written change, add `reverse_query` / `reverse_function`. Otherwise it is a one-way migration; restore a backup instead.

**"needs an answer" when going back** — undoing needs a value (a required field coming back). Run without `--plan` / `--dry-run` and you will be asked.

## Development databases

**I want a clean database.** Drop it and `pangloss migrate`. Memgraph enums cannot be dropped, so enum definitions can linger in a database you reuse; for a truly fresh start, make a new Memgraph database or container.

**I applied a migration I want to change.** Only on your own database: `pangloss migrate library 0003` goes back to before it, then edit the file, then `pangloss migrate`. Once it has run anywhere else, write a new migration instead.

**The tests leave odd enums behind.** That is the same Memgraph limit.

## Still stuck?

`pangloss showmigrations` and `pangloss migrate --plan` say what Pangloss thinks the state is. `pangloss check-data` says whether your data can be read. Include these, and the text of the error, when you ask for help.
