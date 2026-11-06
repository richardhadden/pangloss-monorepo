# Interface refactoring: Solid 2.0 idioms

A review of the interface code (`pangloss-interface/js/interface-core`, `interface-app`, and the interface modules of
`pangloss-dates` and `pangloss-typology`) against Solid 2.0 as it is meant to be written: the `solidjs-v2` skill
(`.claude/skills/`, written for rc.8) and the v2 docs (<https://v2.solidjs.com/>, especially "Avoid unnecessary
effects", "Mutations", "Async reactivity" and "Integrate non-Solid code"). The interface was on `solid-js@2.0.0-rc.19` then; it is on rc.21 since 2026-11-06 (see the end).
Reviewed 2026-11-02.

Most of the code is already idiomatic v2: split effects everywhere, async memos under `Loading`/`Errored`, `onSettled`
for setup that returns its teardown, `class` arrays and objects, keyed `For`, context providers for per-request state,
`untrack` for deliberate one-time reads of props. What is listed below is what is not, and what was done about it.

## The rules this is checked against

1. **Derive, do not relay.** A signal written from an effect whose compute reads other reactive state is a copy one
   flush late (`EFFECT_RELAY_TEAR` in the dev build). Use a memo, a plain function, or a *writable derivation*
   (`createSignal(() => props.value)`, which resets itself when its source changes).
2. **Re-ask with `refresh(source)`**, not a counter signal that a memo reads only to depend on it.
3. **Mutations are `action`s**: `yield` the request, then `yield refresh(source)`; catch a failure in the generator and
   put it in state. The action's writes are held to the end of its transaction.
4. **DOM after a write: `flush()`, then read.** Not `setTimeout`/`queueMicrotask` to wait for the render.
5. **Effects are for systems Solid does not own** (the document, storage, a library). A measuring/sizing effect is a
   render effect (`createRenderEffect`). Reactive state read in the apply function is read once, and the dev build
   says so (`STRICT_READ_UNTRACKED`) unless it is in an `untrack`.
6. **`Show` narrows with a function child** (`{(value) => ...value()}`), rather than `when={x()}` and then `x()!`.
7. **Reads in a component body are one-time captures**: say so with `untrack`.

## Findings and decisions

| # | Where | What is not idiomatic | Decision |
|---|-------|-----------------------|----------|
| 1 | `ConsoleSearch.tsx` | `deepOn` is a signal that an effect copies `props.deep` into | ✅ writable derivation `createSignal(() => props.deep ?? false)` |
| 2 | `context/clipboard.tsx` | `key` is a signal that an effect sets from `props.owner` | ✅ a memo (`storageKey`); the effect only reads the storage (an outside system) |
| 3 | `pages/List.tsx` | `generation` is a signal an effect bumps when the address's form is not the panel's | ✅ a memo of the panel's instance, which is a new object when the address has a form the panel did not ask for |
| 4 | `pages/Item.tsx` | `Track` relays the item into a signal of the page by an effect (and `Forget` clears it from an `onSettled` in the error fallback), so that the console outside the boundaries shows it | ❌ tried and put back: with a console inside the boundaries (the item's in the content, the type's in each fallback), an item that is not there after logging out left its console in the bar beside the fallback's: the content's portal stays when `Errored` (rc.19) goes to its fallback. `test_an_item_that_disappears_on_logging_out_is_a_404_and_leaves_no_label` caught it |
| 5 | `pages/Edit.tsx` | `reload` counter read by the item memo | ✅ `refresh(item)` |
| 6 | typology `TypeTree.tsx`, `TypeItem.tsx` | `version` counters; mutations as async functions that bump them | ✅ `action`s that `yield` the request and `yield refresh(...)`, catching the refusal into `refused` |
| 7 | `TypeMenu.tsx` (3), `Problems.tsx`, `SearchPanel.tsx` (saved search name) | `setTimeout`/`queueMicrotask` to focus or scroll once the write has rendered | ✅ `flush()`, then the DOM; but not where `TypeChooser` opens its box (see below) |
| 8 | `ModelFields.tsx` `TitleBox` | an effect that sizes the box | ✅ `createRenderEffect` |
| 9 | `Problems.tsx` `useSaveChecks` | `untrack` around the effect's apply (it looked redundant) | ❌ it was not (the dev build warns `STRICT_READ_UNTRACKED` without it); the effect itself went with 16 |
| 10 | `pages/List.tsx` `Results` | `untrack` around a call in a `setTimeout` callback (not tracked) | ✅ removed |
| 11 | `Retype.tsx`, `ModelFields.tsx` (`PickOrCreate`), `Console.tsx` (history) | `when={x()}` then `x()!` | ✅ function children / plain values |
| 12 | `LiteralEditor.tsx` `JsonEditor` | the store read in the body to seed the box, untracked but not said to be | ✅ `untrack` |
| 13 | `EntityPicker.tsx` | the autocomplete is fetched in a handler with a ticket, `busy`, `failed`, `searched` and `results` signals kept in step by hand | ✅ a debounced `asked` signal (`equals: false`, so the same words again are a new search) and an async memo of what was found, failure included as a value; `busy` is `isPending(found)`. Tests of its own: `EntityPicker.test.tsx` |
| 14 | `ItemForm.tsx`, `EntityCreateDialog`, `LoginDialog.tsx`, `App.tsx` (log out) | saves as async functions with a `saving`/`busy` signal | ✅ the request is an `action` that sets a `createOptimistic(false)` flag (false again when it is over, whatever the answer); what comes of it (toast, `onSaved` and its navigation, problems at the fields, which need `flush()`, refused inside an action) is the caller's, once the action's promise settles. Log out has no flag, and stays a plain function. Test: `ItemForm.test.tsx` "Save is off while the item is being sent" |
| 15 | `context/translations.tsx` | `setLanguage` loads with a ticket and a `loading` signal | ✅ the chosen language is a signal, the bundle an async memo of it (each fetched once; one that cannot be fetched resolves to what was shown), `language()` is the shown bundle's, `loading()` is `isPending(bundle)`, the choice is kept by an effect on the language shown. `setLanguage` keeps its contract: its promise is `resolve(bundle)`. The tests are unchanged, with one more: the rest of the page goes on changing while a language loads |
| 16 | `Problems.tsx` `useSaveChecks` | an effect writes the problems again in the new language | ✅ the problems had their codes and parameters already: `useProblemText` words them by `useSayProblem` where they are shown, so they follow the language with no effect (nor the `checked` flag it needed) |

### Kept as they are, on purpose

- **`TypeMenu.tsx` `TypeChooser`, opening the box**: still a `setTimeout`. With `flush()` the box is drawn during the
  click that opens it, in the place of the button that was clicked, and the same click, going on to the document's
  click-away listener, is then outside the box and closes it (in happy-dom, whose `composedPath()` follows the
  element; the Vitest tests caught it). Focusing after the click is over is what is wanted there.

- **`List.tsx` `Results`**: the pages of a virtualised list are fetched from an effect on what is on show. The rows on
  show are a fact of the window (an outside system), and each page is fetched once into a `Map`; an async memo per
  page would put a `Loading` round every row. The row `ref` measures in a `queueMicrotask`: a ref runs before the
  element is in the document, and nothing may be written while rendering.
- **`Edit.tsx` `ScrollToNested`**: `requestAnimationFrame` after `onSettled`, as the scroll needs the layout.
- **`RequireLogin.tsx`**: an effect opens the login dialog when no one is logged in. The dialog is the app's (a
  provider above the page), and opening it is a command to it, not a copy of state.
- **`ConsoleSearch.tsx`**: the effect that writes a query from the address into the box. It writes the DOM (the box is
  not bound, so what is being typed is not overwritten) and the draft with it, only when the query is not the one asked
  for.
- **Storage read in `onSettled`** (`navbar`, `translations`, `clipboard`, saved searches, recent entities): so that the
  first client render is the server's.
- **`createSignal(untrack(() => props.x))` and `untrack(() => ({ ...props }))`**: deliberate one-time captures, as the
  docs say to write them.

## Status (2026-11-02)

Done in one commit with this file. Tests run: the interface's Vitest suites (core and app: 214 passed) and its
typecheck; the interface module suites (typology 18, dates 12) and their typechecks, in a scratch copy, as they have no
`node_modules` of their own; and the browser tests (`e2e/`, including `test_dev_mode.py`, which runs the dev build,
where Solid's dev-only errors show). A browser test was added for the Edit page's "Load the new version" (5), which no
test covered: `test_editing.py::test_an_item_saved_meanwhile_is_not_overwritten_and_the_new_version_can_be_loaded`.

Then, each in a commit of its own, the four that were left for later: the entity picker (13), the saves (14), the
translations (15) and the problems (16). Nothing of the review is left to do.

## 2026-11-06: rc.21, and what the development server said

Raised to `solid-js` and `@solidjs/web` 2.0.0-rc.21, `@solidjs/router` 2.0.0-next.44 and `@solidjs/vite-plugin`
3.0.0-next.56 (in `interface-core`, `interface-app` and the eight interface modules; the plugin's option for the
Node server is now `start: { nodeServer: true }`, and its build writes `.br` and `.gz` files beside the client's).
Nothing behaved differently: what follows was there on rc.19 too. Found by clicking through the smoke test's
project on the development server and reading its log, which also has the browser's warnings (Vite passes them on).

| What the development build said | Where | Cause, and what was done |
|---|---|---|
| `SSR_BOUNDARY_WATERFALL`: the item page's `Loading` took 4 passes on the server, 3 waits one after another | `pages/Item.tsx` | The item was read, and only when it had come was the code the modules add to the page asked for (the sections, the views of what refers to it, a model's own page, the cards of models that have one), each a `lazy` component. 🚧 `useModules().preloadItemPage(type)`, called in the memo that reads the item, starts those imports with the request, so the code is there when the item is. **What is left is the development server's own**: when a `lazy` component is rendered, Solid looks up its assets, which the development server answers later, a pass of the boundary for each such component, and it does not count that as work already started (the lookup is not stamped). A page with one such component is now silent; with two or more it still says "3 sequential async waits" in development, the first time. The built server looks assets up at once: no pass. (Seen by logging what each pass waited for.) |
| `SERVER_WRITE`: a signal written on the server | `pages/Item.tsx`, `Track` | Its `onCleanup` clears the console's item; the server discards each pass of a boundary, so the cleanup ran there. ✅ registered in the browser only (`isServer`) |
| `STRICT_READ_UNTRACKED` | `pages/Edit.tsx`, `ScrollToNested` | `const id = props.id`, read once on purpose. ✅ `untrack(() => props.id)` |
| "Hydration key miss ... (template: `<option>`)" and "Hydration completed with N unclaimed server-rendered node(s)", on every list page | `SearchPanel.tsx`, `AddSelect` (the menu that adds an order) | **A trap of the release candidate.** An `<option>` whose text is a child expression (`<option value="">{label}</option>`), followed by a `<For>` of options: the browser counts the expression among the children and the server does not, so the keys of the options after it differ, the server's are left unclaimed and the browser's are made detached. ✅ the text as a property: `<option value="" textContent={label} />`, here and in the five other places with the same shape (two more in the panel, the review queue's types, the months and weekdays of the date forms) |
| "Hydration key miss" for a `<div>` and a menu button, on the form of a document with documents inside | `form/ModelFields.tsx`, `Block` | **A prop that is elements, read twice**: `props.buttons ? openClass : closedClass` and then `{props.buttons}`. Each read of such a prop makes the elements again, so the browser made a second set of retype buttons that was never shown. ✅ `const buttons = children(() => props.buttons)`, read from there |
| `STRICT_READ_UNTRACKED` in a `<Show>` | `ItemContents.tsx`, the view of what refers to an item | The function child read `chosen().component` in its body. ✅ `<Dynamic component={chosen().component} .../>` |
| `IMMUTABLE_UPDATE_IN_STORE`, when a document in a form is made another type | `form` (retype) | Advice, not a fault: the document is put in the form's store as a new object on purpose, and all of it is shown anew. Left; the tests expect it |
| `UNSTABLE_LIST_IDENTITY`: every row of a `<For>` made again | `SearchPanel.tsx`, `AddSelect` | Its options are new objects each time one is chosen. ✅ `keyed={(option) => option.value}` |

The browser tests now fail on any of these: the fixture of the development server (`e2e/conftest.py`, `dev_url`)
reads its log when the tests are done (`development_warnings`), and fails with each kind and where it was, except
`SSR_RENDER_ERROR_CONTAINED` (a page for what is not there, which the tests ask for), the advice about the store, and
the development server's own waterfall on the item page (`KNOWN_IN_DEVELOPMENT`). The first run of it found the rows
above that the smoke test's project had not shown.

Also found: the built server puts "Internal Server Error" in place of an error that is not marked safe to show,
before the page's own `Errored` sees it, so a page for an item that is not there said that. `ApiError` is now
marked (`markSafeError`), and recognises itself after it has crossed to the browser as a plain `Error`
(`Symbol.hasInstance`).
