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
- Changes to the database's enums and indexes are **not tried** (`changes the database itself (enums, indexes: not tried)`), because Memgraph does not allow them inside a transaction. A change that needs an enum that the same migration would create fails here for want of it; that is expected.
- It does not take the lock, and changes nothing.
- It makes a transaction as large as the whole migration, so on a very large database it is slow or heavy. Try it on a copy.

**Best practice:** restore a recent copy of production somewhere safe, and run `migrate --dry-run`, then `migrate`, there first.

## Backups

```bash
pangloss migrate --backup        # take a snapshot first
pangloss migrate --no-backup     # you have taken your own
```

`--backup` asks Memgraph for a **snapshot** of the whole database just before applying (after taking the lock, so nothing else is migrating). Pangloss prints where it is:

```
Backup: /var/lib/memgraph/snapshots/20261021040143118268_timestamp_405218
```

Know what this is:

- The snapshot is **Memgraph's own**, written on the **server** (not on the machine you ran `pangloss` from).
- Memgraph keeps only the newest few snapshots (3 by default, `--storage-snapshot-retention-count`). A later snapshot, including its own automatic ones, can remove yours. **If it must be kept, copy it away.**
- Pangloss does **not** restore. To go back to a snapshot, use Memgraph's own tools (see Memgraph's documentation on snapshots and recovery).
- If taking the snapshot fails, nothing is applied.

A migration with a `[LOSES DATA]` change *requires* you to choose one of the two flags. There is no default, so that "I didn't think about it" is not an option. `--no-backup` is for when you have your own arrangements (a database copy, a cloud snapshot) and want to be explicit about it.

## When a migration fails

By default a migration is **one transaction**: it either all happens or none of it does. If a change fails (a value will not convert, a constraint is broken), the data is as it was, the migration is recorded as `failed` with the error, and the rest are not tried.

```console
$ pangloss migrate
  library.0006_alterliteraltype_person_born: applying
  library.0006_alterliteraltype_person_born: failed
3 values of Person.born cannot be converted (Person.born: type str -> int): say what to do with them (`on_failure`: 'null' or 'default')
```

Fix the cause (see [chapter 8](08-troubleshooting.md)) and run `migrate` again: a failed migration is tried again from the start.

The exceptions are Memgraph's own limits: **enums, indexes and constraints cannot be changed inside a transaction**, so those steps happen on their own, one at a time. They are written so that doing them twice is harmless, and a stop part way leaves the next run to finish them.

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

### Keep writers out

The lock only stops another `migrate`. **Nothing stops your application writing while a migration runs**, and a write during a structural change would store data in the old shape. For a migration that matters:

- stop the API (`MIGRATION_CHECK = "error"` already stops it *starting* with migrations pending), or put it behind a maintenance page;
- run the migration;
- start the API again.

A read-only mode while migrating is not available yet.

## Large databases: batches

A migration is one transaction by default, which on a very large database can be long, and means a failure throws all the work away. You can ask for it to be done in **batches**:

```bash
pangloss migrate --batch-size 5000
```

or mark one migration in its file:

```python
atomic = False        # batches of 5000
```

In batches:

- changes to plain fields (add, remove, rename, make required, change type, wrap or unwrap an annotated value) and changes of labels are made **N nodes at a time, in the order of their ids**, each batch its own transaction;
- wrapping a relation in a reified relation is made N relations at a time (the ones done are no longer there to wrap, so the next batch finds the next);
- everything else (removing or renaming a relation, wrapping in a semantic space, enum changes) is still made at once, in a transaction of its own;
- what must hold **before anything is changed** (that every value converts, that every answer is given) is checked **once, before the first batch**, so a bad value does not leave you with half a migration;
- how far it has got is saved **in the same transaction as each batch**.

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
```

## A checklist for production

1. The migration was generated and reviewed in development, and committed.
2. You ran `migrate --dry-run` and then `migrate` on a copy of the production data, and `check-data` is clean.
3. You read the `[LOSES DATA]` lines and are happy to lose them.
4. A backup exists that you can restore (`--backup`, and copied off the server if it must outlive Memgraph's retention).
5. The API is stopped.
6. `pangloss migrate` (with `--batch-size` if the data is large).
7. `pangloss check-data` if you used `--no-check`, then start the API.
