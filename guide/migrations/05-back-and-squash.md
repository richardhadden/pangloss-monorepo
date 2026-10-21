# 5. Going back, and squashing

## Going to a particular migration

`migrate` takes an app and a target:

```bash
pangloss migrate library 0003            # bring the library app to 0003
pangloss migrate library 0003_add_born   # the same, by full name
pangloss migrate library zero            # undo every migration of the app
```

A target is a migration's name, its number, or the beginning of its name (it must pick exactly one). What happens depends on where the database is:

- if the target is **not applied yet**, `migrate` goes **forwards** to it, applying it and whatever it needs, and no further;
- if it **is applied**, `migrate` goes **backwards**, undoing everything after it.

## Going backwards

```console
$ pangloss migrate library 0003 --plan
To undo:
  library.0005_removefield_person_nickname
    - Add the literal field Person.nickname
  library.0004_renamefield_person_born_birth_year
    - Rename the field Person.birth_year to born
  [LOSES DATA: what the migrations wrote or changed is not brought back]
```

The migrations come off **last first**. Each is undone by the opposite of each of its changes, in the opposite order:

| It did | Undoing it |
|--------|-----------|
| Rename X to Y | Rename Y back to X |
| Add a field | Remove it (the values written since are lost) |
| Remove a field | Add it back, empty (the values it had are gone for good) |
| Create a model | Delete it, and the nodes made since |
| Delete a model | Make it again, empty |
| Change a type | Convert back (what no longer converts makes it fail) |
| Wrap a relation | Unwrap it (the wrapper's own fields are lost) |
| Unwrap a relation | Wrap it again (**asked** for the wrapper's fields) |
| Add or remove an index, a constraint, an enum member; rename an enum or a member; change a member's value | The opposite |
| Make a field required | Make it optional |
| Make a field optional | Make it required (**asked** for a value for the empty ones) |

A useful way to think of it: **the structure goes back exactly; the data goes back as far as the information still exists.** A removed field comes back, but its values do not. Undoing is marked `[LOSES DATA]` whenever that is so, and, as for going forwards, you must pick `--backup` or `--no-backup` and confirm.

Every reversal is checked before it is tried: applied to the models as they were after the migration, it must give the models as they were before. If it does not, that migration is refused as irreversible.

### What cannot be undone

- A **hand-written** `RunCypher` or `RunPython` that was given no way back (see [chapter 6](06-by-hand.md)).

Pangloss says which migration and which change, before touching anything:

```
library.0004_… cannot be undone: Run a query: it has no `reverse_query`
```

### Rules of the road

- **Undoing runs in one transaction per migration** (unless you give `--batch-size`, or the migration says `atomic = False` or `batch_size`: then in batches, like going forwards). If one fails in a transaction, it changes nothing and stays recorded; the ones already undone stay undone. One that fails in batches has undone part: run it again, which is safe, because what is undone is not there to undo again.
- **A migration that failed or was left `[~] running` is undone too**: going back to an earlier migration undoes whatever was begun after it, finished or not.
- **Going back makes a migration pending again.** Its record is removed, so the next plain `pangloss migrate` applies it again, and until you do, the server will refuse to start with the newer models (as it should). The usual use is a rollback of a deployment: go back, then run the older code.
- **Answers are asked when you run it.** If undoing needs a value (a required field coming back), `migrate` asks (`--dry-run` asks too, since it tries it). `--plan` does not ask: it lists what will be asked (`Going back will ask for: ...`).
- **`--fake`** with a target removes the records without touching the data (the mirror of `migrate --fake`).
- Undoing a migration also undoes anything **in any app** that depends on it and has been applied. It lists them first.

## Squashing

After a while, a project has dozens of migrations: a model made in `0001`, given a field in `0002`, renamed in `0005`... Applying them all to a new database is slow and noisy. **Squashing** replaces a run of migrations with one that does the same.

```console
$ pangloss squashmigrations library 0001 0007
library.0001_squashed_0007_addfield_person_born
  replaces 0001_initial, 0002_..., 0003_..., 0004_..., 0005_..., 0006_..., 0007_...
  24 changes in 7 migrations -> 9 changes
    - Create the Entity Person
    ...
Wrote library/migrations/0001_squashed_0007_addfield_person_born.py
The migrations it replaces are kept, for databases that are part way through them.
Delete them (the files) when every database has applied them all.
```

Use `--dry-run` to look first, `--name` to choose the name, and `--no-optimize` to keep every change as it was.

### What goes in it

- If the run **starts at the app's first migration** and contains nothing written by hand, the squashed migration is the changes *between the models before and after* — so a model that was made and then given three fields is simply made with them. This is the big saving. (A rename inside the run becomes a removal and an addition: with no data yet, that is the same.)
- Otherwise — a run in the middle of the history, or one with hand-written changes — it is the **original changes, one after another**. Data may exist at that point, and what was done to it must still be done. You save files, not work.

### Which does a database use?

The squashed migration and the originals both stay in your project. Each database picks by its own record:

| The database has had | It uses |
|----------------------|---------|
| none of the originals (a new database) | the squashed migration |
| **all** of the originals | the squashed migration — and counts it as applied; nothing to do |
| **some** of them | the originals, to finish the job |

So squashing is safe to commit while colleagues and servers are at different points: nobody is left in between.

### Deleting the originals

Once **every database** that matters (your own, your colleagues', staging, production) has applied all the originals, delete the original files. A database whose record names migrations that no longer exist is still fine: it counts the squashed migration as applied. But one that is only **part way** through the originals, and whose files you deleted, is told so and cannot go on; keep the originals until you are sure.

```console
$ pangloss cleanmigrations library
These are replaced by a squashed migration:
  0001_initial.py  (by 0001_squashed_0007_addfield_person_born)
  ...
No other database is looked at. One that is part way through them cannot go on without them.
Delete them? [y/N]:
```

`cleanmigrations` deletes the files of what a squashed migration replaces (`--yes` skips the question). It looks only at **the database your settings point to**: it keeps the originals if that one is part way through them. It cannot know about the others, which is why it asks.

### Rules

- You can squash any run of one app's consecutive migrations (`0003` to `0007`), not only from the start.
- A squashed migration can be squashed again with the migrations after it (`squashmigrations library 0001 0010`). The new one replaces the old one and everything the old one replaced, and each database uses it, or the first squashed migration, or the originals, according to how far it has got.
- Later migrations, and migrations of other apps that depended on an original, continue to work: they follow the squashed one.
- Going back past a squashed migration removes the originals' records too.
