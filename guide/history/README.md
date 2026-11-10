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
there (but see "Data from before history" below). For a copy of the whole database before a risky change use
`pangloss migrate --backup`.

## Data from before history

Installed on a project that has data already, history has no record of that data until it is next saved, and what it
was before that save could never be restored. Record what it is now:

```bash
pangloss history baseline              # every model with history; --model Person for one (as many as are given)
pangloss history baseline --dry-run    # only count
```

Each document and entity whose latest record is missing, or older than its version in the database (a write that was
not recorded), gets one record of its content now: the operation `baseline`, its version, and who last changed it and
when. One that has a record of its version is left alone, so it is safe to run again. One that no longer fits its model
is named, and the rest go on.

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
| `GET /api/{Model}/{id}/history` | The versions (`?summary=true`: each with its label then and the fields that differ from the version before) |
| `GET /api/{Model}/{id}/history/{v}` | A version, **upgraded to today's models** (`?upgrade=false`: as written), with `problems` for anything that could not be; `?view=true` in the read form of the API (camelCase, the entities it refers to with their labels now) |
| `GET /api/{Model}/{id}/history/contents` | Every version with content, in the read form, for comparing them |
| `GET /api/{Model}/{id}/history/{v}/diff?to=` | What changed between two versions; nested objects with an `id` are compared by id |
| `GET /api/{Model}/{id}/history/{v}/draft` | The version as a draft to reconcile: upgraded as far as it can be, and the problems someone must decide |
| `POST /api/{Model}/{id}/history/{v}/restore` | Write it again as a **new** version |

## Restoring

```bash
pangloss history restore <Model> <id> <version> --user ada --expected-version 7
```

A restore is a new version (the history is never rewritten), made by the user you name; `--expected-version` refuses it
if the record has moved on. A version written under older models is **upgraded through the migrations since**: renamed
fields, new defaults, enum values mapped. A restore is refused (409, with the reasons) only when there is a *blocking*
problem; a field that no longer exists is dropped from the restored copy and stays in the earlier version.

## In the interface

With `pangloss_interface` installed, the item page of a logged-in user has a **History** button in its console. It opens
a panel on the right (closing review's, if that is open: one panel at a time) with the versions, newest first, each
condensed: its number, what happened, who and when, its label if it changed, and the fields that changed as tags.
Clicking one slides it out beside the panel, shown as the item's page shows the item, with **Restore to this point** at
its foot. That asks first, listing the later versions whose work is undone and what will change, field by field; nothing
is erased, so a restore can itself be undone the same way.

**Compare all** opens `/<Model>/<id>/history`: every version side by side, oldest on the left, the rows lined up (the
parts inside matched by id), and each cell marked against the version before it: green put in, red taken out, amber
changed, and the words of a text that changed. The plan and what was built: [implementation_docs/history.md#the-interface-the-history-panel-restore-compare-plan-of-2026-11-04-built](../../implementation_docs/history.md#the-interface-the-history-panel-restore-compare-plan-of-2026-11-04-built).

## Things to know

- Migrations and history work together: `pangloss cleanmigrations` warns when recorded versions were written part-way
  through what a squashed migration replaces, because they could no longer be upgraded once the originals are gone.
- Not upgraded: enum values inside annotated values and edge properties, and changes that wrap or unwrap fields or turn
  literals into embedded objects (these are reported as `unsupported-change`, never guessed).
- Not built: the interface's form for a draft; a `purge` command and an erasure policy.
- It has not yet been run against a long-lived project; try it on a copy first.

[History](../../implementation_docs/history.md) has the design and what each phase built.
