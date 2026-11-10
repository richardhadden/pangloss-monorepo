# The admin page and jobs 🚧

`pangloss-admin`: the page `/admin`, and long-running jobs. First user: the RDF dump.

Written as the plan, 2026-11-09, with the user's decisions; the markers say what is built.

## Decisions

| Question | Decision |
|---|---|
| How a job runs | A new `pangloss admin run-job` process for each job, started by the API |
| Who gets what a job makes | Admins: a download on `/admin`, kept until an admin deletes it |
| Who sees `/admin` | Not logged in: the login dialog. Logged in, not an admin: the ordinary 404. No link to it anywhere |
| Options of the dump | Format (N-Quads, TriG or Turtle), gzip (on by default), include unpublished, include unused. Not `--types` |
| Hooks | `pangloss-admin` knows nothing of RDF. Apps add jobs (`admin.py`) and parts of the page (the manifest's `slots`) |

## Why a process of its own

`BackgroundTask` is an asyncio task on the server's own event loop. A dump measured 133 to 336 s on 691k nodes, reached
about 4 GB, and most of its time is Python turning reads into quads, which would hold up every request. A process has
its own event loop and connection, and its memory goes back when it ends. It needs nothing else deployed.

## How it works ✅

- **An app declares a job** in an `admin.py`: `jobs = [JobKind("rdf_dump", run, options=(Choice(...), Flag(...)))]`.
  `run(context)` writes to `context.directory` and calls `context.progress(step, steps, current, counts)`. The options
  are data, so the page draws the form and the app needs no interface code, only the words: `{kind}_title`,
  `{kind}_option_{name}`, `{kind}_{name}_{value}`, `{kind}_count_{key}` in its `ui.jsonc`.
- **State is files**, in `ADMIN_JOBS_DIRECTORY` (default `.pangloss/admin-jobs`, mode 0700): `<id>/job.json`, `heartbeat`,
  `log.txt`, `files/`. Polling them is no load on the database, and all server workers see them. A lock file makes "one
  job of a kind at a time" hold across workers.
- **The process is in its own session**, so a server restart does not stop it. It touches `heartbeat` from a thread. A
  job with no heartbeat for 30 s is shown as `interrupted`. If the process dies while the server is up, the server
  records it as `failed`, with the end of the log.
- **Cancel** marks the job and sends SIGTERM, and the job ends as `cancelled`. What a job made is kept only if it
  finishes, so a partial file is never offered.
- **Download** is admin-only, and only of a name the job lists. It is exempt from the API's gzip.

States: `queued`, `running`, `finished`, `failed`, `cancelled`, `interrupted`.

## API ✅

All for admins (403 otherwise; a route of the `pangloss_admin` router that is not is a failing test).

| Route | Does |
|---|---|
| `GET /api/admin/jobs` | The kinds with their options, and the latest 30 jobs |
| `POST /api/admin/jobs` | `{kind, options}`: 201; 409 if one of the kind is running; 422 for a wrong option |
| `POST /api/admin/jobs/{id}/cancel` | 409 if it is not running |
| `DELETE /api/admin/jobs/{id}` | 204; 409 while it is running |
| `GET /api/admin/jobs/{id}/files/{name}` | The file |

## The page ✅

- `live()` (`feed.ts`), as the typology tree does: the interface's server polls `GET /api/admin/jobs` with the
  admin's cookies every `PANGLOSS_ADMIN_POLL_MS` (1000) and sends what changed. `broadcast()` shares one answer among
  callers, and so one person's cookies; with a few admins and a cheap read, `live()` keeps each caller's own check.
- `slots`: a new, general manifest key, `slots: { admin: { Jobs: () => import("./JobsSection") } }`, read with
  `useModules().slot("admin")`. Anything an app wants on the page is one more entry. `InterfaceConfig(disabled=["app:key"])`
  applies. The jobs are themselves one such section.

## Limits

- A dump is not a snapshot: it reads a page at a time, so a document changed during it is either version.
- Progress is by class (`4 of 30`), with running counts. There is no percentage, as a true total would need more queries.
- One machine: the server and its jobs share a disk. `fcntl`, so not Windows.
- Finished files stay until deleted. Nothing limits their size.

## Tests

| What | Where |
|---|---|
| Options, discovery, state files, one at a time, cancel, stale jobs, a real process that crashes or is cancelled | `packages/pangloss-admin/tests/` |
| Every route refuses a non-admin, start, conflict, download, no path escape | `packages/pangloss-admin/tests/test_admin_api.py` |
| The dump's job, with a real database | `packages/pangloss-rdf/tests/live/test_rdf_admin_job.py` |
| Polling, helpers | `interface/src/*.test.ts` |
| `/admin` for each kind of visitor; a dump from button to download | `e2e/test_admin.py`, `e2e/test_dev_mode.py` |
