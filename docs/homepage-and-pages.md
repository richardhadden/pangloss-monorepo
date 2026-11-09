# The homepage, search everything, and a project's own pages

✅ Built, 2026-11-09. The "As built" section says where the code differs from the plan.

## What is wanted

- A default homepage: the project's name in large type, and a box that searches everything, with the results under it.
- A project can replace the homepage, and add pages of its own, from files in `<project>/pages/`, made by the CLI.
- The console of the homepage and of those pages links to the pages.

## Decisions

| Question | Decision |
|---|---|
| What the box searches | Labels of head documents and entities, by the text index, as the search of a list does. Not deep search |
| Results | 25, most connections first |
| An empty box | Shows nothing, and asks the database nothing. A type chip by itself lists the most connected of the type |
| A type in the box | A finished word that names a type, in any language, becomes a chip on space; Backspace against the chip makes it a word again. One chip at a time |
| Custom homepage | `pages/index.tsx`: its layout is the project's, the search is the shared `GlobalSearch` |
| Links to the pages | In the console of the homepage and of each page, the current one marked |

## Search everything

**Opting out.** `Document.Meta(global_search=False)` / `Entity.Meta(global_search=False)`: not inherited, so a project's
class on `ZoteroBacked` is found although `ZoteroObject` is not. It is on the model layer, not `InterfaceMeta`, because
the API applies it. Users and calendar days, months and years are not models and have no label, so they need nothing.

**Query.** `operations.search_everything`: every word in the label (the `label_text` index), head nodes only, what the
reader may see, not the classes opted out, and only the classes of the chip if there is one; ordered by the edges out
of the node (a relation is two edges, so these count both directions, as autocomplete does), then label. Backend
neutral, in `pangloss-cypher`; behaviour fixed by a conformance test.

**API.** `GET /api/search-everything?q=&type=&page_size=`. The answer has autocomplete's shape: `id`, `type`, `label`.

**Type names.** The database holds one name for a type; the browser already has every language's (`modelNames`, used by
the nav filter). The browser recognises the word and sends the model's name.

## A project's pages

The application's routes are declared in code: there is no filesystem router. `interface-app` makes one for
`<project>/pages/` with Vite's `import.meta.glob`:

- `index.tsx` is `/` (instead of the default); `About.tsx` is `/about`, `Our-Team.tsx` is `/our-team`. Flat folder.
- The name of the file says the rest: `10-About.tsx` is ordered by the number, `_Draft.tsx` has an address but no link, and the link's text is the translation slot `page_about`, or else the file name.
- Pages are compiled where they are, so an edit hot-reloads. Tailwind and `pangloss interface check` look there too.
- A page whose address is a route of the interface or a model's name is an error in `pangloss interface check`.

`PagesConsole` draws the links. CLI: `pangloss interface new-homepage`, `pangloss interface new-page NAME`; neither
writes over a file without `--force`.

## Steps

1. Model option, export, TypeScript type; opt-outs in `pangloss-zotero`.
2. Query, operation, SDK, API route; conformance and API tests; measure on 642k nodes.
3. `schema/` logic for recognising a type word; `GlobalSearch`; default homepage. Vitest.
4. Pages: route discovery, Tailwind, type-checking, clash check, `PagesConsole`. Vitest, pytest.
5. CLI and templates. Pytest.
6. E2E and dev-mode tests, `e2e/COVERAGE.md`, translations, docs, the skill.

## As built

- **No `meta` export.** To list the pages' titles, every page would have to be loaded with the first page of the site, so
  no page could be split off. The file's name holds the order and whether it is linked instead.
- **The default homepage is the template.** `new-homepage` copies `interface-app/src/pages/Home.tsx`, so the two cannot differ.
- **Page logic** (`pagesOf`) is in `interface-core/src/schema/pageFiles.ts`, where it can be tested without a DOM; a page's
  address is worked out the same way in `pangloss_interface/pages.py`.
- **A type chip with no words lists the most connected of the type** (decided after the first build). An empty box still asks nothing.

### Measured

Memgraph, 300,000 entities whose labels all match (the hardest case for the ranking: every hit has its edges counted),
100,000 hits per word (`SEARCH_HIT_LIMIT`): 475-504 ms for `smith` (100,000 hits), 289-405 ms for `1`, 115-164 ms
for `smith 1234` (96 hits).

A word with more hits than `SEARCH_HIT_LIMIT` is ranked among the hits the index gave, as a list search is: the most
connected of all could then be missed. The count stops at that limit too.
