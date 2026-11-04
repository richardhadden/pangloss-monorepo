# pangloss-history

Optional. Keeps every version of every Document and Entity, so that one can be looked at and
compared with another (and, later, restored). Add `"pangloss_history"` to `INSTALLED_APPS`.

The design (built) is in [docs/history.md](../../docs/history.md). History is **best effort**: a record
is made after the write has committed, and a write is never failed or slowed by it.

Settings (all optional, on the project's settings class): `HISTORY_DB_PATH`
(default `.pangloss/history.sqlite3`), `HISTORY_QUEUE_SIZE` (1000), `HISTORY_BATCH_SIZE` (100),
`HISTORY_BATCH_MS` (50), `HISTORY_EXCLUDE` (names of models that have no history).

`pangloss history baseline` records what data written before it was installed is now. With `pangloss_interface`
installed, its interface module (`src/pangloss_history/interface/`) adds a History button and panel to the item page,
restoring from it, and a page comparing every version: [docs/history-interface.md](../../docs/history-interface.md).

Guide: [guide/history](../../guide/history/README.md).
