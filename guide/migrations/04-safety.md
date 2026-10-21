# 4. Staying safe

Most migrations are harmless, and a few change a great deal of data at once. This chapter is about the tools Pangloss gives you to know in advance what will happen, to recover if it goes wrong, and to cope with databases too large to migrate in one go.

## What `migrate` does, in order

1. **Reads the record** of what the database has had, and checks it against the files. It refuses to go on if an applied migration was edited or is missing.
2. **Shows what it will apply**, change by change, with `[LOSES DATA]` marks.
3. **Asks before losing data** (if any change is lossy): you must have chosen `--backup` or `--no-backup`, and you confirm (or give `--yes`).
4. **Takes the lock**, so two people cannot migrate at once.
5. **Takes the backup**, if you asked for one.
6. **Applies each migration**, recording it as `running`, then `applied` (or `failed`, with the error).
7. **Releases the lock.**
8. **Reads back the data** the migrations could have made unreadable, and says if any cannot be read.

You can stop before step 4 at any point, and `--plan` and `--dry-run` stop there on purpose.

## Look first

### `--plan`

```console
$ pangloss migrate --plan
To apply:
  library.0005_removefield_person_nickname
    - Remove the literal field Person.nickname and its data  [LOSES DATA]
```

Lists the pending migrations and their changes. None of your data is touched.

### `--dry-run`

`--plan` tells you what the migration *says*. `--dry-run` tells you what it would *do* to your actual data:

```console
$ pangloss migrate --dry-run

Tried, and rolled back:
  library.0003_addfield_person_born
    - Add the literal field Person.born (a value is needed for the nodes that exist)
        214 properties set
  library.0005_removefield_person_nickname
    - Remove the literal field Person.nickname and its data
        198 properties set
Nothing was changed
```

It runs every change for real, in **one transaction that is then rolled back**, and reports the counts Memgraph gives: properties set, nodes and edges made or deleted, labels added or removed. If something would fail you find out now:

```
    - Person.born: type str -> int
        WOULD FAIL: 3 values cannot be converted ...
Some changes would fail: nothing was changed
```

Things to know:

- After the first failure the remaining changes say `not tried` (a failed transaction cannot go on).
- Changes to the database's indexes and constraints are **not tried** (`changes the database itself (an index or constraint: not tried)`), because the database does not allow them inside a transaction ([chapter 9](09-memgraph.md)). Everything else, enum changes included, is.
- It does not take the lock, and changes nothing.
- It makes a transaction as large as the whole migration, so on a very large database it is slow or heavy. Try it on a copy.

**Best practice:** restore a recent copy of production somewhere safe, and run `migrate --dry-run`, then `migrate`, there first.

## Backups

```bash
pangloss migrate --backup        # take a backup first
pangloss migrate --no-backup     # you have taken your own
pangloss backups                 # the backups the database has
pangloss restore PATH            # put the database back to one (replaces everything)
```

`--backup` takes a backup of the whole database just before applying (after taking the lock, so nothing else is migrating). If taking it fails, nothing is applied. A migration with a `[LOSES DATA]` change *requires* you to choose one of the two flags: there is no default, so that "I didn't think about it" is not an option. `--no-backup` is for when you have your own arrangements (a database copy, a cloud snapshot) and want to be explicit about it.

**`restore` replaces everything in the database with what the backup has.** Data written since is lost, and so is the record of migrations since (so the database is where the backup was: run `pangloss showmigrations`, and `pangloss migrate` with the code that goes with it). It asks first.

What a backup *is*, where it is kept and how long it lasts depend on the database. For Memgraph (the one Pangloss uses), read [chapter 9](09-memgraph.md): **a backup can be gone within minutes.**

## When a migration fails

By default a migration is **one transaction**: it either all happens or none of it does. If a change fails (a value will not convert, a constraint is broken), the data is as it was, the migration is recorded as `failed` with the error, and the rest are not tried.

```console
$ pangloss migrate
  library.0006_alterliteraltype_person_born: applying
  library.0006_alterliteraltype_person_born: failed
3 values of Person.born cannot be converted (Person.born: type str -> int): say what to do with them (`on_failure`: 'null' or 'default')
```

Fix the cause (see [chapter 8](08-troubleshooting.md)) and run `migrate` again: a failed migration is tried again from the start.

The exception is a database limit (see [chapter 9](09-memgraph.md)): **indexes and constraints cannot be changed inside a transaction**, so those steps happen on their own, one at a time. They are written so that doing them twice is harmless, and a stop part way leaves the next run to finish them.

If you needed to stop a migration and the lock remains (see below), the record shows `[~] running`.

### The lock

While `migrate` runs it holds a lock in the database, so two cannot run at once. If a run is killed, the lock stays, and the next one says:

```
Another migrate is running, or was stopped without finishing: `pangloss migrate --unlock` removes the lock
```

Make sure no migration really is running, then:

```bash
pangloss migrate --unlock
```

### Read-only while it runs

While `migrate` runs it holds a lock in the database, and **while the lock is held nothing can be written**: every write (through the API, a script, or the models in a shell) is refused, and everything can still be read. The check is made inside the transaction of each write, so it holds for anything that writes through Pangloss.

- Through the API a refused write is answered with **`503 Service Unavailable`**, `Retry-After: 30`, and `The database is being migrated: it can be read, and not written to, until that is done`. Reads go on as usual.
- A write that was already running when the lock was taken is not waited for. For a migration that matters, stop the writers (or wait for quiet) before you start.
- The same goes for the changes in your own migrations: a `RunPython` must write through `tx`, not through the models (those are refused while the lock is held).
- If a run was killed and left the lock, writes stay refused until `pangloss migrate --unlock`. The message says so.
- `--plan`, `--dry-run` and `--check` take no lock, so they do not stop anyone writing.

## Large databases: batches

A migration is one transaction by default, which on a very large database can be long, and means a failure throws all the work away. You can ask for it to be done in **batches**:

```bash
pangloss migrate --batch-size 5000
```

or mark one migration in its file:

```python
atomic = False        # batches of 5000
batch_size = 1000     # or: batches of this many (this implies atomic = False)
```

(The command line's `--batch-size` wins over the file's.)

In batches:

- changes to plain fields (add, remove, rename, make required, change type, wrap or unwrap an annotated value) and changes of labels are made **N nodes at a time, in the order of their ids**, each batch its own transaction;
- everything else that touches data is made **N of whatever is left at a time**: relations wrapped or unwrapped (in a reified relation or a semantic space), one wrapper changed for another, fields turned into an embedded object and back, relations renamed or removed (and the nodes they own), a reverse name or the properties on edges changed, a list made a single value, a relation made to point to less, parent fields, the values of an enum, models renamed or deleted. What is done is no longer there to find, so each batch finds the next, and a run that stops is simply run again;
- what must hold **before anything is changed** (that every value converts, that every answer is given) is checked **once, before the first batch**, so a bad value does not leave you with half a migration;
- how far it has got is saved **in the same transaction as each batch**.

Still made in one go: anything you wrote by hand (`RunCypher`, `RunPython`). (The recomputing of the context of documents after a model rename is in batches too: the documents that still have the old name in them, `N` at a time.)

If a batched run stops (the network, a killed process), run `migrate` again — after `--unlock` if it left the lock:

```
  library.0006_alterliteraltype_person_born: going on from change 1
```

It continues from where it was. The result is the same as the all-at-once migration. (Batches and `--dry-run` do not combine: a dry run is always one transaction.)

## After a migration

The data check at the end is your safety net. It reads back the models the migrations could have affected, which is fewer than all: adding a model or an optional field affects nothing that exists, so nothing is read. If something cannot be read you get the list, and the exit code is non-zero.

```bash
pangloss migrate --check-all     # read everything afterwards
pangloss migrate --no-check      # read nothing
pangloss check-data              # read everything, at any time
pangloss check-data --parallel 4 # several at a time (not faster against a local database; may help with a remote one)
```

## A checklist for production

1. The migration was generated and reviewed in development, and committed.
2. You ran `migrate --dry-run` and then `migrate` on a copy of the production data, and `check-data` is clean.
3. You read the `[LOSES DATA]` lines and are happy to lose them.
4. A backup exists that you can restore (`--backup`; mind how long it lasts: [chapter 9](09-memgraph.md)).
5. The API is stopped.
6. `pangloss migrate` (with `--batch-size` if the data is large).
7. `pangloss check-data` if you used `--no-check`, then start the API.
