# History: every version, and restoring one

`pangloss-history` keeps every version of every Document and Entity, so that you can see what a record looked like on a
given date, what changed between two versions, and **put an earlier version back**, even when the models have changed
since.

Add `"pangloss_history"` to `INSTALLED_APPS`. Nothing else: every write from then on is recorded. It has no models of
its own and no database to run: the history is a SQLite file.

## It is best effort

A version is recorded **after** the write has committed, by a background thread, and a write is never failed or slowed by
it. If recording fails, or the server stops at the wrong moment, the write stands and the history has a gap. Nobody is
promised a complete history, and history begins when the package is installed: a version written before that is not
there. For a copy of the whole database before a risky change use `pangloss migrate --backup`.

## Settings

All optional.

| Setting | Default | |
|---|---|---|
| `HISTORY_DB_PATH` | `.pangloss/history.sqlite3` | The file |
| `HISTORY_QUEUE_SIZE` | 1000 | Versions waiting to be written; a full queue drops and counts |
| `HISTORY_BATCH_SIZE`, `HISTORY_BATCH_MS` | 100, 50 | How the worker groups its writes |
| `HISTORY_EXCLUDE` | `[]` | Models with no history |

## Looking

```bash
pangloss history list <id>                    # versions: number, operation, who, when; and the ones not recorded
pangloss history show <id> <version>
pangloss history diff <id> <version> --to 5   # to the latest if --to is left out
```

(These read only the SQLite file and need no database.) Over HTTP, for a logged-in user:

| | |
|---|---|
| `GET /api/{Model}/{id}/history` | The versions |
| `GET /api/{Model}/{id}/history/{v}` | A version, **upgraded to today's models** (`?upgrade=false`: as written), with `problems` for anything that could not be |
| `GET /api/{Model}/{id}/history/{v}/diff?to=` | What changed between two versions; nested objects with an `id` are compared by id |
| `GET /api/{Model}/{id}/history/{v}/draft` | The version as a draft to reconcile: upgraded as far as it can be, and the problems someone must decide |
| `POST /api/{Model}/{id}/history/{v}/restore` | Write it again as a **new** version |

## Restoring

```bash
pangloss history restore <id> <version> --user ada --expected-version 7
```

A restore is a new version (the history is never rewritten), made by the user you name; `--expected-version` refuses it
if the record has moved on. A version written under older models is **upgraded through the migrations since**: renamed
fields, new defaults, enum values mapped. A restore is refused (409, with the reasons) only when there is a *blocking*
problem; a field that no longer exists is dropped from the restored copy and stays in the earlier version.

## Things to know

- Migrations and history work together: `pangloss cleanmigrations` warns when recorded versions were written part-way
  through what a squashed migration replaces, because they could no longer be upgraded once the originals are gone.
- Not upgraded: enum values inside annotated values and edge properties, and changes that wrap or unwrap fields or turn
  literals into embedded objects (these are reported as `unsupported-change`, never guessed).
- Not built: the interface's form for a draft; a `purge` command and an erasure policy.
- It has not yet been run against a long-lived project; try it on a copy first.

[History](../../docs/history.md) has the design and what each phase built.
