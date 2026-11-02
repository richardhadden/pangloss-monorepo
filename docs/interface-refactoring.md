# Interface refactoring: Solid 2.0 idioms

A review of the interface code (`pangloss-interface/js/interface-core`, `interface-app`, and the interface modules of
`pangloss-dates` and `pangloss-typology`) against Solid 2.0 as it is meant to be written: the `solidjs-v2` skill
(`.claude/skills/`, written for rc.8) and the v2 docs (<https://v2.solidjs.com/>, especially "Avoid unnecessary
effects", "Mutations", "Async reactivity" and "Integrate non-Solid code"). The interface is on `solid-js@2.0.0-rc.19`.
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
| 9 | `Problems.tsx` `useSaveChecks` | `untrack` around the effect's apply (it looked redundant) | ❌ kept: it is what keeps the dev build from warning `STRICT_READ_UNTRACKED` for the problems read there; a comment says so |
| 10 | `pages/List.tsx` `Results` | `untrack` around a call in a `setTimeout` callback (not tracked) | ✅ removed |
| 11 | `Retype.tsx`, `ModelFields.tsx` (`PickOrCreate`), `Console.tsx` (history) | `when={x()}` then `x()!` | ✅ function children / plain values |
| 12 | `LiteralEditor.tsx` `JsonEditor` | the store read in the body to seed the box, untracked but not said to be | ✅ `untrack` |
| 13 | `EntityPicker.tsx` | the autocomplete is fetched in a handler with a ticket, `busy`, `failed`, `searched` and `results` signals kept in step by hand | ⏸ not now: see below |
| 14 | `ItemForm.tsx`, `EntityCreateDialog`, `LoginDialog.tsx`, `App.tsx` (log out) | saves as async functions with a `saving`/`busy` signal | ⏸ not now: see below |
| 15 | `context/translations.tsx` | `setLanguage` loads with a ticket and a `loading` signal | ⏸ not now: see below |
| 16 | `Problems.tsx` `useSaveChecks` | an effect writes the problems again in the new language | ⏸ not now: the problems would have to keep their codes and be put into words where shown |

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

### Not now (⏸), and why

- **13, the entity picker.** The idiomatic form is a debounced text signal and an async memo of the matches
  (`isPending` for the spinner, `Errored` for "The search failed"). But the list is a popup that has to stay open with
  the last matches while the next are asked, has its own "Nothing found" state that depends on what was searched, and
  is in every entity field of every form: it wants its own change with its own tests, not a sweep.
- **14, saves as actions.** An `action` holds its writes until it settles, and the saves call `onSaved`, which
  navigates: what a navigation inside a held transaction does with the router (rc.19) needs trying first. The
  `saving` flag would become `createOptimistic(false)`. The typology mutations (6) have no navigation, so they were
  done.
- **15, translations.** `setLanguage` returns a promise the tests and the language menu wait for, and a language that
  fails to load must leave the page as it was (not reach an error boundary). An async memo of the bundle would hold the
  whole page in a transition while a language loads, which is what is wanted, but changes the provider's contract.
- **16.** Needs the problems to be stored as codes and parameters (`SayProblem`), and worded where shown.

## Status (2026-11-02)

Done in one commit with this file. Tests run: the interface's Vitest suites (core and app: 214 passed) and its
typecheck; the interface module suites (typology 18, dates 12) and their typechecks, in a scratch copy, as they have no
`node_modules` of their own; and the browser tests (`e2e/`, including `test_dev_mode.py`, which runs the dev build,
where Solid's dev-only errors show). A browser test was added for the Edit page's "Load the new version" (5), which no
test covered: `test_editing.py::test_an_item_saved_meanwhile_is_not_overwritten_and_the_new_version_can_be_loaded`.

To pick up next: the ⏸ rows, each a change of its own, the entity picker (13) first.
