# Interface module of `pangloss_zotero`

A Solid 2.0 library that the interface (`pangloss interface build`) includes when `pangloss_zotero` is in
`INSTALLED_APPS`. What it is for: [docs/zotero-sources.md](../../../../../docs/zotero-sources.md), "Turning an item into
a project class by hand".

- `src/index.ts`: the manifest. *Zotero item* is a `newItemFields` entry (`FromZotero`: a row of the form of a new item, on its page and in a relation's dialog), *Link to Zotero* and
  *Unlink* a `consoleActions` entry (`ZoteroLinkAction`). Both show only for the classes an item can be made into
  (`GET /api/zotero/classes`).
- `src/components/ZoteroItemPage.tsx`: the page of an item (`item_page` of `ZoteroBacked`): title, creators by role, address, language and when synced, in place of the fields the sync writes; `src/zoteroItem.ts` reads them.
- `src/components/ItemPicker.tsx`: the dialog that finds an item of the fallback class (or takes its address).
- `src/api.ts`: the routes of `pangloss_zotero/api.py`.

Its tests run in a built project (`npx vitest run --root modules/pangloss_zotero` in `.pangloss/interface`).
