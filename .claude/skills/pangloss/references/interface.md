# The interface

What is particular to Pangloss's web interface: where things are, the rules of its code and its look, how a package
adds to it, and how it is tested. For the Solid 2.0 API itself use the `solidjs-v2` skills; for Tailwind, `tailwind-ops`.
The reference is `docs/interface.md` (architecture), `docs/interface-modules-implementation.md` (modules),
`docs/interface-to-document.md` (what is built, feature by feature) and `docs/translations.md`.

## Contents

- Where things are
- The stack, and what it rules out
- How the interface knows the models
- The layers of `interface-core`
- Rules of the code
- Rules of the look
- Text: every fixed string is a slot
- Interface modules: how a package adds pages and parts
- Running it
- Tests

## Where things are

```
packages/pangloss-interface/src/pangloss_interface/
  cli.py, api.py, meta.py, config.py, modules.py, workspace.py, typescript.py   the Python side
  translations/ui.jsonc                                                          the words of core and app
  js/                                                                            an npm workspace
    interface-core/src/    the library (@pangloss/interface-core)
      types/ schema/ api/ context/ primitives/ components/ registry.ts
    interface-app/src/     the application: App.tsx, routes.ts, pages/, queries.ts, styles.css

<app>/interface/           an interface module of an installed app (pangloss_dates, pangloss_review, …)
<project>/.pangloss/interface/   the copy that is built and run. Written over by every command: never edit it
```

## The stack, and what it rules out

- **Solid 2.0** (release candidates; `solid-js`, `@solidjs/web`, `@solidjs/router`, `@solidjs/vite-plugin`, released in
  lockstep). Not Solid 1.x, not SolidStart, never React. Most examples on the web, and much of what a model
  remembers, are 1.x: check the API in the `solidjs-v2` skill or at v2.solidjs.com before using it.
- **Tailwind v4 for all CSS.** Utility classes only; `interface-app/src/styles.css` holds the theme.
- **Server-rendered** (streaming SSR, then hydration) by the Solid Vite plugin. Node is the default runtime; Bun is
  allowed.
- **The browser talks only to the interface's server**, which passes `/api` to the Pangloss API. One origin: no CORS,
  first-party cookies. Login is the API's cookie session, through a dialog (`useLoginDialog().openLogin()`); there is
  no `/login` page. A server render passes the request's cookies on, so the page is rendered for the user.

## How the interface knows the models

`pangloss_models.export.export_models()` turns the initialised models into plain data: every model's kind, fields
(with the JSON `key`, validators, markers, bindings), the types a relation can hold, incoming relations, traits,
subclasses, and what other packages add through `InterfaceMeta`. `typescript.py` writes it as `generated/models.ts`.
Pages, forms and the search form are all made from it, read through `useModels()` / `useModel(name)` and the pure
functions of `schema/`.

So a new thing the interface must know about a model is **exported from Python**, typed in
`interface-core/src/types/models.ts`, and guarded by `test_models_match_typescript.py`. The interface does not keep
its own description of a model. The models are exported when a command starts: restart `pangloss interface dev`
after changing them.

## The layers of `interface-core`

```
types  <  schema  <  api  <  context  <  primitives  <  components  <  registry  <  index
```

A layer imports only from layers below it; the library never imports the application or a module. `npm run
check:layers` (and `pangloss interface check`) fails otherwise. `schema/` is pure functions over the definitions, and
is where logic goes so that it can be tested without a DOM.

**A component that could be replaced is never imported by another**: it is taken from the map,
`useComponent("ReferenceChip")`. The application builds the map (`createComponentMap`), so a project's replacement is
used everywhere, inside the library's own components too.

## Rules of the code

Components run on the server as well as in the browser, and Solid 2.0's development build stops on mistakes its
production build lets through.

- Never destructure props; read `props.x` where it is used. A snapshot of a prop in a component body needs `untrack`.
- No `window`, `document` or `localStorage` outside an effect or `onSettled`. No per-request state at module level.
- Choose between elements with `<Show when fallback>`, never a ternary or `&&` in JSX. Conditional classes use the
  object form, one class per key; a ternary is only for a plain attribute value.
- Effects are split: `createEffect(() => tracked, (value) => { … })`. A signal read in the second function needs
  `untrack`.
- **Never write a signal while rendering** (in a component body, an `Errored` fallback, a `ref` that sets state). The
  dev build halts the whole application. Writes go in event handlers, the second function of an effect, `onSettled`
  or a microtask.
- **Make no reactive primitive inside `onSettled`**, and do not read the router's `useSearchParams()` there (it makes
  some lazily): read it in the component body.
- An async read is a `createMemo` shown inside `<Loading>`; errors in `<Errored>` (whose fallback gets an accessor,
  `err()`). Saves are actions. Setters are batched: a read straight after a write is the old value.
- `For` gives the item as a plain value and the index as an accessor. Key a list whose items are made anew on each
  update (`keyed={(item) => item.value}`), or every row is made again. **With `keyed={fn}` the item is an accessor, `item()`**: read as a plain value it is silently empty, and a module's types are checked only by `pangloss interface check`.
- **The text of an `<option>` that other options follow is `textContent={...}`, not a child expression**: the browser
  counts the expression and the server does not, and the options after it are not taken over on hydration.
- **A prop that is elements is read once**: each `props.buttons` makes them again. To ask whether there are any and
  then show them, `const buttons = children(() => props.buttons)` and read `buttons()`.
- **On the server nothing is written to a signal, not even from an `onCleanup`** (the server discards each pass of a
  boundary): register such a cleanup only `if (!isServer)`.
- A `lazy` must be given a file's module as it is (it carries `$$moduleUrl`): a `lazy` that returns a wrapper of its own hydrates as a key miss (`[LAZY_ASSET_UNMAPPED]`). Put what goes round it outside the `lazy`.
- Code a page needs only once its data has come (a module's `lazy` components) is started with the data, not after
  it: `useModules().preloadItemPage(type)` on an item's page. Otherwise the server renders the page in one pass for
  each thing it waits for.
- An error thrown while the server renders reaches the page as "Internal Server Error" in the built interface unless
  it is marked `markSafeError` (as `ApiError` is). Test such a page in the built interface, not only in development.
- What most pages do not show is `lazy`, so that it is not in every page's code: in the map, `ItemForm` and `ItemContents`; also `SearchPanel`, the virtualised branch of `VirtualRows`, the delete dialog and a chip's clip buttons. A page that shows one of the map's after reading data starts it with the data (`preload(ItemContents)`). A new import from a page-wide component can undo this: `e2e/test_code_splitting.py` guards it. A `lazy` first rendered while hydrating must also have been rendered on the server, or the page crashes: what depends only on the browser (the clipboard bar) uses a plain `import()` in an effect instead.
- A `live()` feed is opened only in the browser: draw what reads it inside `<Show when={inBrowser()}>`, a signal set in `onSettled`. Rendered on the server it gets a first answer, and the browser never opens the feed. Open it through `whileVisible(...)` (core): an open feed holds one of the browser's six connections to the host, and feeds in background tabs left new pages stalled.
- A module-level memo that depends on who is logged in reads `useSessionKey()`, so it is fetched again on login and
  logout.
- Decide what a logged-in user sees with `userIsLoggedIn()`.
- A page that shows an `ItemForm` gives it `guardLeaving={useLeaveGuard()}` (`interface-app/src/leaving.ts`), so a
  form with changes asks before it is left (docs/unsaved-changes-and-stash.md).

Known traps of the current release candidate are listed in `docs/interface-refactoring.md`. The development server
says when one is met (`[SSR_BOUNDARY_WATERFALL]`, `[SERVER_WRITE]`, `[STRICT_READ_UNTRACKED]`, "Hydration key miss"):
read its output after clicking through what you changed. The browser tests fail on them (`dev_url` in
`e2e/conftest.py`).

## Rules of the look

- **An item shown as a reference is a `ReferenceChip`** (`useComponent("ReferenceChip")`, with `type`, `label`,
  `href`): in lists of what refers to something, dialogs, panels, toasts, search results. Never a plain link, never
  "TYPE label" as text. The user asked for this to hold everywhere unless they say otherwise for a case.
- **A button that stands by itself takes `buttonClass(kind, size)`** (or is a `Button`): `ordinary`, `primary`
  (slate-700: never sky, which is the entities' colour), `danger`, `quiet` (actions in each row of a table), `add`; `sm`
  26px, `md` 32px in a dialog's footer. A button in a bar (a panel's or dialog's head: Close) is as tall as the bar,
  `barButtonClass` / `barIconButtonClass`. One of several chosen is `segmentedClass` + `segmentClass(chosen)`; a state
  is `badgeClass`, a number `numberBadgeClass`; a table uses `tableClass` and its fellows. All in core `primitives/`.
  The look is flat: no gradients or shadows of light (tried and taken out, `docs/look-and-feel/`).
- Text of the frame (not content) is `uppercase font-semibold`. Every icon has `select-none`. Icons are drawn thin and sharp: `stroke-linecap="square"`, mitred joins (the default), and on a 24-unit viewBox `stroke-[1.5]` at `size-5`, `stroke-[1.75]` at `size-4`, `stroke-2` at `size-3.5` and smaller, so that the line is the same weight on screen.
- **Anything that names a type carries `data-type-info={modelName}`** (the raw name of the model). The one `TypeInfoPopup` in the frame then describes it on hover + Alt; a new chip needs nothing else. Add `data-type-info-side="right"` to place it beside rather than under.
- A page says its window title with `PageTitle` (core), not `Title`: `Function | label | type | project`.
- Colours of types come from `InterfaceMeta(colour=...)`: blue for entities and green for documents by default.
- Extract a repeated piece into a component, but ask the user before adding a new shared one.
- **Nesting is bounded by folding, not by depth.** A block five deep starts folded, in the view and the form
  (`components/nesting.ts`), and what is folded is not made: a document can nest without limit, and making sixty
  levels at once overran the call stack. The rows of fields are a container query of what they are in
  (`fieldGridClass`, `nestedClass` in `form/styles.ts`): keep new layout inside those classes' tiers.
- The user works on a retina screen and sees half-pixel faults. `border-[0.5px]` draws a full CSS pixel in Chrome,
  so nested boxes must not rely on a half-pixel negative margin to overlap: draw the outer hairline as an
  `after:absolute after:inset-0` overlay. Check thickness in a screenshot's pixels, not by eye. Vertical rhythm was
  reviewed in `notes/vertical-rhythm-2026-11-03.md`.
- Look at what you built. Take a screenshot of the page with real data (the demo's models) before saying a visual
  change is done.

## Text: every fixed string is a slot

No English in a component. A string a person reads or hears (labels, placeholders, tooltips, `aria-label`s) is
`t("slot_name")` from `useTranslations()`, with its texts in a `ui.jsonc`:

- core and the application: `packages/pangloss-interface/src/pangloss_interface/translations/ui.jsonc`;
- an interface module: **its own app's** `translations/ui.jsonc` (`review_*` in `pangloss_review`, and so on);
- a project's own words and overrides: `<project>/translations/ui.jsonc`.

Give each new slot its text in every language the file has (English, German and French at present);
`pangloss interface translations check` reports a slot without one. Names of models, fields and enum members come
from `models.jsonc`, which `pangloss interface translations generate` keeps in step with the models while keeping
manual edits. See `docs/translations.md`.

## Interface modules: how a package adds pages and parts

An installed app ships a small Solid library in `<app>/interface/` (`pangloss interface new-module <app>`). Its
`src/index.ts` is a manifest:

```ts
export default defineModule({
  name: "pangloss_calendar",              // the app's name
  requires: [],                           // other modules it uses
  components: { MonthPage: () => import("./components/MonthPage") },   // lazy
  routes: [{ path: "/calendar/:calendar/:year/:month", component: "MonthPage" }],
  // also: collapseRules, consoleActions, newItemActions, newItemFields, editItemFields, itemSections, incomingViews, resultMarks, userHref
});
```

| The package wants | It uses |
|---|---|
| Its own list page, item page, view card or edit card for a model | `InterfaceMeta(list_page="app:Name", item_page=…, view_card=…, edit_card=…)` on the model |
| A page not about one type (a month, a tree, a queue) | `routes` in the manifest |
| Links and sections in the navigation bar | `<app>/interface_config.py`: `config = InterfaceConfig(nav=[NavModel(...), NavLink(...)], sections=[...])` |
| A button or panel in the console of a page | `consoleActions` (`{ loggedIn: true, load }` if only for someone logged in: no one else fetches its code) |
| A button on the form of a new item that fills it in, or sends it another way | `newItemActions` (`NewItemForm`: `get`, `set`, `sendBy`) |
| A row among the fields of a new item's form (page and relation dialog), with the same powers | `newItemFields` (draw a `FieldRow`) |
| Fields a form must not edit (kept up to date by the package) | `Protection(read_only=...)` on the model: exported as `readOnly`, left off every form |
| Fields a person may set but forms need not show (per class) | `InterfaceMeta(hide_on_forms=(...) or a function of the class)` |
| A row first among the fields of the form that edits an item, to show what it holds | `editItemFields` (`EditItemFieldProps`; draw a `FieldRow`) |
| A section after an item's own contents | `itemSections` |
| Another way to show what refers to an item (a timeline) | `incomingViews` (`takes` chooses the items; the rest stay by field) |
| Something small at the right end of each row of a list (a status flag) | `resultMarks` (a component, not a loader: `ResultMarkProps`, `type` and `item`) |
| A person's name in the console to link to a page (`pangloss_users`) | `userHref` (a function of the username; for someone logged in) |
| A part of a page that another module draws (`/admin`) | `slots: { place: { Name: loader } }`, read with `useModules().slot("place")`; no change to core for a new place |
| A rule for folding a wrapper into the one thing it holds | `collapseRules`, named from `InterfaceMeta(collapse="app:rule")` |

Other `InterfaceMeta` options: `list_used_only` (an Entity's list shows what something refers to until *Show all*, each with a count; `True`, `False`, or a function of the class; unset, the class's `Usage`), `colour`, `nav_section`, `collapse=True | Collapse(...)`, `headless=True` (a reified
relation shown without its head bar where it is a field's only, single, required type). `InterfaceMeta` is resolved
field by field through the parents: a subclass that sets only `colour` keeps its parent's `item_page`.

A project turns off what a module adds with `InterfaceConfig(disabled=["app:key"])`.

A **project's own pages** are not modules: `<project>/pages/*.tsx` (`pangloss interface new-homepage`, `new-page NAME`), found by `import.meta.glob` (there is no filesystem router), compiled where they are. `index.tsx` replaces `/`; `About.tsx` is `/about`, linked in the console (`10-About.tsx` orders it, `_About.tsx` has no link). A page imports only `@pangloss/interface-core` and Solid. See `docs/homepage-and-pages.md`.

The rule that matters: **`interface-core` has only generic hooks.** What belongs to a package (the timeline to dates,
the Derived section to derived, the review panel to review) lives in that package's module, with its strings and its
tests. If core would have to know a package's trait, field names or API to do something, add or use a hook instead.

A module may import `@pangloss/interface-core`, Solid, the router and its own dependencies; not the application, not
another module's files. `pangloss interface check` type-checks the modules, checks the layers, and reports a model
that names a component no manifest has. `pangloss interface modules` lists what is installed.

## Running it

```sh
pangloss dev                       # the API, port 8000
pangloss interface dev             # the interface with hot reload, port 3000; passes /api on
pangloss interface dev --link      # the same, run from the package's source: for working on the interface itself
pangloss interface build && pangloss interface serve   # the built one; it passes /api on too (--api-url)
pangloss interface check           # types with the project's models, layers, modules
```

Run them in a project (the demo: from `pangloss-demo/`, as `../.venv/bin/pangloss …`). The user may have their own
dev servers on 3000 and 8000: use them if they are up, and do not stop them. The demo's password is not known to
you: to see pages that need a login, use the e2e stack with its own user, not a guess.

## Tests

| What | Where | Run |
|---|---|---|
| Logic and components of core and the application | `*.test.ts(x)` beside the source (Vitest; components start `// @vitest-environment happy-dom` and use `render` from `@solidjs/web`) | `npm test` in `packages/pangloss-interface/src/pangloss_interface/js`; also run by pytest (`test_javascript.py`, with `typecheck` and `check:layers`) |
| A module's own tests | `<app>/interface/src/**.test.ts(x)` | They have no `node_modules` in the source: run them in a prepared workspace (a project's `.pangloss/interface`, `npx vitest run --root modules/<app>`) whose `interface-core` is a fresh copy |
| The Python side (export, meta, config, modules, translations) | `packages/pangloss-interface/tests/` | `uv run pytest packages/pangloss-interface` |
| The built interface in a browser | `e2e/` (Playwright; a real project, API and the test Memgraph) | `uv run pytest e2e` |

- **`e2e/COVERAGE.md` is kept current**: a new page or feature gets a row; a new test changes its row and names the
  test.
- **The e2e stack is a production build**, which does not show Solid's development-only errors. Any new page is also
  loaded in `e2e/test_dev_mode.py` (the `dev_url` fixture), which looks for errors in the page as well as thrown ones.
  All tests passing has, before now, coexisted with a dev server that would not render.
- Keep e2e tests few: what only a browser shows (drag and drop, hydration, built chunks). Logic belongs in Vitest and
  API tests. Notes on writing them are in `e2e/README.md`.
- In a module's Vitest, a lazy view needs `vi.waitFor`, not one tick.
- **The parts of the item page that read for themselves are boundaries in a `Reveal`.** The page reads the item
  alone; what refers to it (`IncomingRelations`) and each module section (`ItemSections` gives each a `Loading` with
  no fallback) read in a `Loading` of their own, streamed after the item, and the page's `Reveal` shows them in page
  order, so a section never appears before what is above it and then moves down. Rules learnt there: a `Loading` the
  `Reveal` is to order must be the outermost boundary of its part (an `Errored` between severs it: put it inside); a
  section reads its data directly, with no boundary of its own nested in the one it is given (the nested one hydrated
  wrongly, its server nodes unclaimed); a `lazy` component's code is started with the page (`preloadItemPage`) and
  awaited under the page's boundary as a serialisable value (`ItemSections.ready`), never resolved by hand into a
  component (a function is not written into the page for hydration), so that the section's own boundary waits only
  for its read (each wait after another is a pass on the server, and three are `[SSR_BOUNDARY_WATERFALL]`). A new
  part of the item page that reads something should follow the same shape; a list that can be thousands of rows is
  `VirtualRows` (docs/large-data.md).
- **Save is off until the item has changed** (`ItemFormState.changed`): a test that saves must change something
  first, and in Vitest wait a tick after typing before clicking Save (the memo and the button follow after a flush).
