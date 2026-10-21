# 3. The database

Your models say what the data looks like. The database needs to be told too (it has indexes and constraints for them), and it needs a record of what it was told, so that when the models change later, Pangloss knows what changed. That record is a **migration**.

## The first migration

```console
$ pangloss makemigrations
letters.0001_initial
    - Create the Document Letter
    - Create the Entity Person
    - Create the Entity Place
Wrote letters/migrations/0001_initial.py
```

`makemigrations` compared your models with what the migrations so far describe (nothing yet), and wrote a file saying what to do. Open `letters/migrations/0001_initial.py` if you are curious: it is ordinary Python. **Commit it with your code**, like `models.py`.

Nothing has touched the database yet. To see what would happen:

```console
$ pangloss migrate --plan
To apply:
  letters.0001_initial
  pangloss_memgraph.0001_initial
```

`pangloss_memgraph.0001_initial` is a migration that comes with the database package: the indexes and constraints Pangloss itself needs. You never write it. Now apply:

```console
$ pangloss migrate
...
  letters.0001_initial: applying
  letters.0001_initial: applied
  pangloss_memgraph.0001_initial: applying
  pangloss_memgraph.0001_initial: applied
Done
Nothing that exists is affected by these migrations: no data to read
```

and check:

```console
$ pangloss showmigrations
pangloss_memgraph
 [X] 0001_initial
letters
 [X] 0001_initial
```

`[X]` means the database has had it. From now on the rhythm is always the same: **change the models, `makemigrations`, `migrate`**. [Part 6](06-changing-a-model.md) does it with data in the database, and the [migrations guide](../migrations/README.md) has the rest.

## A user

Everything written to Pangloss is recorded as written by a **user** (who created a letter, who changed it). Make one:

```console
$ pangloss users create --username alice --email alice@example.org \
    --password alice-password --full-name "Alice" --no-admin
Created user 'alice'
```

(Give `--admin` or `--no-admin`, or it will stop and ask.)

You now have a database with a structure, and a user to write as. Next: [writing and reading data](04-data.md).
