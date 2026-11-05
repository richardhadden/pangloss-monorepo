# Interface module of `pangloss_zotero`

A Solid 2.0 library that the interface (`pangloss interface build`) includes when `pangloss_zotero` is in
`INSTALLED_APPS`. What it is for: [docs/zotero-sources.md](../../../../../docs/zotero-sources.md), "Turning an item into
a project class by hand".

- `src/index.ts`: the manifest. *From Zotero* is a `newItemActions` entry (`FromZotero`), *Link to Zotero* and
  *Unlink* a `consoleActions` entry (`ZoteroLinkAction`). Both show only for the classes an item can be made into
  (`GET /api/zotero/classes`).
- `src/components/ItemPicker.tsx`: the dialog that finds an item of the fallback class (or takes its address).
- `src/api.ts`: the routes of `pangloss_zotero/api.py`.

Its tests run in a built project (`npx vitest run --root modules/pangloss_zotero` in `.pangloss/interface`).
