# Interface module of `pangloss_history`

A Solid 2.0 library that the interface (`pangloss interface build`) includes when `pangloss_history` is in
`INSTALLED_APPS`. The plan and what was built: [implementation_docs/history.md](../../../../../implementation_docs/history.md).

- `src/index.ts`: the manifest; the button is a `consoleActions` entry (`HistoryAction`), and the page of every version
  is the route `/:type/:id/history` (`HistoryPage`).
- `src/components/HistoryAction.tsx`: the button, the panel (`HistoryPanel`), the version sliding out beside it
  (`VersionDrawer`) and the restore's "are you sure" (`RestoreDialog`). The panel is one of core's `useSidePanel`, so
  opening it closes review's.
- `src/align.ts`: several versions lined up as rows (fields in the model's order, parts matched by id), each cell marked
  against the version before it; `changedRows`, what a restore changes. `src/words.ts`: a word diff of two texts.
- `src/timeline.ts`: the versions newest first, with the gaps; what a restore undoes.
- `src/api.ts`: the history API's types and calls.

Its tests run in a built project (`npx vitest run --root modules/pangloss_history` in `.pangloss/interface`); the e2e
suite does that.
