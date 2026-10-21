# 9. Memgraph: what is specific to it

The rest of this guide is about migrations in general. This chapter collects what depends on the database underneath, which today is **Memgraph** (the `pangloss_memgraph` package). Another database would have its own version of this chapter.

## Backups: Memgraph snapshots

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
- Memgraph keeps only the newest few snapshots (3 by default, `--storage-snapshot-retention-count`), and may make its own on a timer (every 300 s by default in the container), each of which pushes the oldest out. So a backup can be gone **within minutes**. Pangloss says how long yours lasts, from the server's own settings:

  ```
  Memgraph makes a snapshot every 300 s and keeps 3: this one is removed in about 15 minutes. Raise `--storage-snapshot-retention-count`, or copy it from the server
  ```

  Raise the retention (or switch the timer off) on the Memgraph server if a migration will run longer than that, and copy the file off the server if it must be kept for good: it can only be copied from the server itself.
- If taking the snapshot fails, nothing is applied.

### Looking at backups, and going back to one

```bash
pangloss backups                       # the snapshots the server has, newest first
pangloss restore /var/lib/memgraph/snapshots/2026…   # put the database back to one
```

**`restore` replaces everything in the database with what the snapshot has.** Data written since is lost, and so is the record of migrations since (so the database is where the snapshot was: run `pangloss showmigrations`, and `pangloss migrate` with the code that goes with it). It asks first (`--yes` does not). Only a snapshot the server lists can be restored. Afterwards Pangloss makes the database's text indexes again: a recovered snapshot has them but not their files, and without that nothing could be written.

A migration with a `[LOSES DATA]` change *requires* you to choose one of the two flags. There is no default, so that "I didn't think about it" is not an option. `--no-backup` is for when you have your own arrangements (a database copy, a cloud snapshot) and want to be explicit about it.

## Indexes and constraints

Pangloss itself needs some indexes and uniqueness constraints (on ids, on user names, the text index used for searching labels). They are migrations like any other, shipped by the `pangloss_memgraph` package in its own `migrations/` folder, so a project does not write them. If a newer Pangloss needs another, you get it as a normal pending migration: `pangloss migrate` makes it.

Memgraph does not allow an index or a constraint to be created or changed inside a transaction. So these steps:

- happen **on their own, one at a time**, outside the migration's transaction;
- are not tried by `migrate --dry-run` (it says so);
- are written so that doing them twice is harmless, and a stop part way leaves the next run to finish them.

You cannot write them in a hand-written migration either: `RunCypher` runs inside the transaction.

## Writing Cypher against Pangloss data

For `RunCypher` and `RunPython` ([chapter 6](06-by-hand.md)), this is how the data is stored (the full account is in `docs/migrations.md`):

- A node of a model has the model's **name as a label** (`:Person`), as well as its parents', its kind (`:Entity`, `:Document`...) and `:PGIndexableNode`. Match on the model's label and you also get its subclasses.
- Literal fields are **properties** of the node. Dates are dates; decimals are strings; an enum is the **value** of its member (a string or a number).
- A relation `home: Place` is two edges: `(person)-[:home]->(place)` and `(place)-[:home_reverse {reverse: true}]->(person)`. Always write both (the reverse edge is called `<field>_reverse` unless the field sets another `reverse_name`).
- Every node has an `id` (a UUID string) and a `label`. Nodes inside a document have a `head_node_id` pointing to the document at the top.

Always use **parameters** (`$year`), not string building.
