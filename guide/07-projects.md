# 7. Several apps, existing databases, teams

## Apps

A Pangloss project is made of **apps** (the entries of `INSTALLED_APPS`). Each app that has models has its own `migrations/` folder:

```
library/
  models.py
  migrations/
    __init__.py
    0001_initial.py
    0002_addfield_person_nickname.py
people/
  models.py
  migrations/
    0001_initial.py
```

`makemigrations` writes each change into the app **whose `models.py` the class is in**. You do not choose; if `Person` lives in `people`, changes to `Person` are `people` migrations, even if the field that changed refers to a model in `library`.

To write only one app's migrations, name it: `pangloss makemigrations people`. You get that app's, and those of other apps they depend on (a migration cannot be written without what it follows), and are asked only about the changes in those. The others are listed as "not written", for a later `makemigrations`.

The migrations of all apps together are one history. Each app's are numbered in order, and a migration can **depend on** another app's:

```python
dependencies = [('people', '0001_initial')]
```

Pangloss writes these for you whenever a change mentions a model of another app. `migrate` then applies everything in an order that respects them, regardless of which app you list first.

### Models that need each other

Suppose `library.Place` has a list of `people.Person`, and `people.Person` has a `library.Place`. Neither app can be fully made first. Pangloss handles this by making one of them **in two steps**:

```
library.0001_initial   creates Place, without the field that refers to Person
people.0001_initial    creates Person (depends on library.0001)
library.0002_…         adds Place.visitors, now that Person exists  (depends on people.0001)
```

You will see the extra migration appear; nothing is asked of you. This works for any number of apps going round in a circle, and only splits as many as it needs. (It handles *fields* that refer to each other. A circle that runs through model *inheritance* is refused: put those models in one app.)

### Moving a model to another app

Move the class to another app's `models.py` (and fix imports). Because *which app* a class is in is not stored in the data, **nothing needs migrating**: `makemigrations` finds no changes. Later changes to the model are written into its new app's migrations, which depend on the old app's.

### Apps that come with Pangloss

`pangloss_memgraph` ships migrations of its own: the indexes and constraints Pangloss needs (ids unique, the label text index, user names and so on). They appear in `showmigrations` and are applied by `migrate` like yours. You never write or change them. When you upgrade Pangloss and it needs something new, the upgrade brings a new migration, and `pangloss migrate` applies it.

## A database that already exists

If your database was made **before** the project had migrations (with `pangloss setup-database`, say), it already has the structure and the data. The first migration would try to create what is there.

Tell Pangloss the database is already as the migrations say. (If you forget, `migrate` notices a database with data and no record of any migration, and says so.)

```bash
pangloss makemigrations        # writes 0001_initial from the current models
pangloss migrate --fake        # records them as applied, without running them
pangloss showmigrations        #  [X] 0001_initial (faked)
```

From then on, everything works normally. Only use `--fake` when the database **really is** what the models were when you ran `makemigrations`; it is an assertion, and Pangloss takes your word.

You can fake just part of the history (`pangloss migrate library 0003 --fake` records up to 0003), for a database that is somewhere in the middle.

`pangloss setup-database` and `pangloss migrate` both set a database up. Use `setup-database` only for a project **without** migrations; it warns you if you run it on one that has them, because it makes the indexes as they are now, which can get ahead of the migrations.

## A new developer, a new database

```bash
pangloss migrate
```

That is all: the whole history is applied to the empty database, library migrations included. If the history is long and you have [squashed](05-back-and-squash.md#squashing) it, a new database uses the squashed migrations.

## Working in a team

Migrations are code: they go through version control and review with the models they belong to.

- **Commit the model and its migration together**, and review the migration's list of changes in the pull request. `[LOSES DATA]` should always get a second pair of eyes.
- **Don't edit an applied migration**; write a new one. Pangloss refuses an applied migration whose file has changed.
- **Keep a straight line.** Migrations are a single numbered sequence per app; there are no "merge" migrations. If two branches each add `0004_…`, they will clash when merged. The one who merges second should:
  1. before merging, if they have applied theirs locally, undo it: `pangloss migrate library 0003`;
  2. delete their migration file;
  3. merge, and run `pangloss migrate` (which applies the other's `0004`);
  4. run `pangloss makemigrations` again, which now writes theirs as `0005`, and `migrate`.
- **Run `pangloss makemigrations --check` in CI**, to catch a changed model with no migration.
- **Try a migration against realistic data** before it reaches production ([chapter 4](04-safety.md)).

## Deploying

Run the migration **before** starting the new code, and stop the old code while it runs (nothing stops the application writing during a migration; see [chapter 4](04-safety.md#keep-writers-out)):

```bash
pangloss migrate --backup
# start the new version
```

The server will refuse to start if you forget, which is the point: `MIGRATION_CHECK = "error"` (the default) is a safety net. Set it to `"warn"` in development if you find it intrusive, or `"off"` if your deployment applies migrations by some other route; leave it on in production.

## Each database has its own record

The record of which migrations have run lives *in the database*. Your laptop, a colleague's, staging and production each have their own, and each is brought up to date by running `migrate` against it. `pangloss showmigrations` shows the state of whichever database your settings point to.
