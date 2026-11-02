# The search form of a list ✅

Step 6 of [structured search](structured-search.md): a form on the list page of a type that builds a search pattern
(`POST /api/search`) from the fields of the type, as the entry form edits an item from them. Built 2026-11-02.

**Tests:** `schema/searchForm.test.ts` (the pattern made of each operator), `components/search/SearchPanel.test.tsx`
(the rows, operators, entities, nested forms, what refers to an entity), `ConsoleSearch.test.tsx` (the button),
`e2e/test_search_form.py` and `test_dev_mode.py::test_the_search_form` (in the browser).

## Status and where to resume (2026-11-02)

**Built and tested**, in two commits (`4cd1282`, `042b025`): the panel (button beside Deep search, slides out under the
console, pushes the list down, `mx-3` in from its ends), every field with not + operator + value, entity picking,
nested forms, Mentions, Contains (`$somewhere`), Referred to by (`$incoming`), Any of (`$any_of`), "+ and" on a row,
through / Inside (`$spaces`), Order by, saved searches in the browser, `?form=` in the address, text box narrowing.
Full `./run_tests.sh` passed (the e2e suite again after a test fix: 86).

**Where the code is**

| What | File |
|------|------|
| Form state, fields/operators, compile to the API (`compileSearch`, `compileRequest`), address encoding | `interface-core/src/schema/searchForm.ts` (+ `.test.ts`) |
| The panel and all its rows | `interface-core/src/components/search/SearchPanel.tsx` (+ `.test.tsx`) |
| Saved searches (local storage) | `interface-core/src/components/search/saved.ts` |
| Button in the console | `interface-core/src/components/ConsoleSearch.tsx` |
| List page wiring, query, preload | `interface-app/src/pages/List.tsx`, `queries.ts` (`listQuery`, `requestOf`), `routes.ts` |
| Browser tests | `e2e/test_search_form.py`, `e2e/test_dev_mode.py::test_the_search_form` |
| Strings | `translations/ui.jsonc` (`search_*`, en/de/fr), `docs/interface-strings.md` |

**To pick up next** (see "Not done" at the end): saved searches in the database (shared), `$incoming` of documents
(needs the API first), any-of groups inside alternatives. Not checked yet: the form with the demo's richer models while
logged in (unpublished factoids), and on a large database (a nested form's search cost is as in
[structured search, step 5](structured-search.md#step-5-measured)). The e2e project has no nested documents or semantic
spaces, so Contains, through and Inside are tested only in Vitest.

## What was decided (2026-11-02)

- **A button beside Deep search**, in the console (an icon of a form). It opens a panel that slides out from under the
  console bar. The panel **pushes the list down**: it is part of the page, and scrolls away with it.
- **The text box narrows the form's search**: while the form has a condition, each word typed is a condition
  `label contains <word>` added to the pattern. Deep search cannot be used with the form (its button is greyed out).
- **The search runs as the form is changed** (a moment after the last change, as the text box does). A condition that is
  not complete (no value yet) is left out; a `between` with one end is `≥` or `≤` that end.
- **Covered**: each field of the type with an operator; entity fields by picking entities (any of them, or all);
  documents and embedded objects (a factoid's statements, a date) as nested forms of their own type; **Mentions**
  (documents: entities anywhere in the document, `$mentions`); **Referred to by** (entities: what points at them,
  `$incoming`); and **not** on every condition (`$not`).

## How it works

| Part | Where | What |
|------|-------|------|
| The form's state | `interface-core/src/schema/searchForm.ts` | A `NodeSearch` (`type`, `fields` by name, `mentions`, `incoming`); each field a `FieldSearch` (`op`, `not`, `value`, `entities`, `node`). It is what the form edits, and what the address keeps (`?form=` JSON), with the labels of the entities picked, so that the form can be shown again from the address |
| Pattern | the same | `compileSearch(form, q)` makes the `where` of the API from it; `undefined` when the form has no condition (the list is then the ordinary one, by the text index) |
| Fields and operators | the same | From `searchPatterns` in the exported definitions (`export_search_patterns`), plus `label` for documents and entities. Text: contains, starts with, is, has a value, has none. Numbers, dates, decimals: =, >, ≥, <, ≤, between, has a value, has none. Enums and yes/no: is one of (pills), has a value, has none. Lists of literals: contains, has any, has none. Relations to entities: is any of, is all of, matching (a nested form of the entity's type), has any, has none. Relations to documents and embedded objects: matching, has any, has none |
| Panel | `interface-core/src/components/search/SearchPanel.tsx` | The rows as the entry form has them (the name on the left, under a rule), each with a **not** toggle and an operator; a nested form in a box headed by its type, as a nested document is |
| Console | `ConsoleSearch` | The form button (`aria-pressed` when open; a dot when a structured search is applied), and Deep search greyed out while it is |
| List | `interface-app/src/pages/List.tsx`, `queries.ts` | `?form=` in the address; `listQuery(type, q, deep, where, page)` posts to `/api/search` when there is a `where` |
| Scroll | `createWindowVirtualizer` | Where the list starts is measured again when the page round it changes size (the panel opening) |

## Built after (2026-11-02, the same day)

- The panel is a little in from the ends of the console (`mx-3`), so the two read as two things.
- **Order by**: up to 3 fields of the type's `orderBy` (`date.sort_day` is named "date › sort day"), each ascending or
  descending. An order alone is a search (with an empty `where`): `compileRequest` gives `{where, orderBy}`, and the
  address-to-query string is that (`requestOf`).
- **More conditions on one field** ("+ and" under a row): `FieldSearch.and`, each with its own not and operator; all
  must hold (they go into `$all`).
- **Any of** (`$any_of`): groups of alternatives, each a form of the same type in its own box, "or" between them; an
  alternative with nothing in it is left out, and a group with one left is that one. An alternative has no groups of
  its own, nor an order.
- **Contains** (`$somewhere`, documents at the root): documents of any type somewhere inside, each with a form, and not.
- **Through** (a relation that can pass through semantic spaces, conjunctions or reified relations, from the model's
  field options): pills under the condition; with nothing else chosen it is "has one through these". **Inside**
  (`$spaces`): pills of the semantic spaces, on a nested form for a document that a relation points at.
- **Saved searches**, in this browser (local storage, `pangloss.savedSearches.<type>`, the user's choice): Save… asks
  for a name (the same name replaces the one before); a menu at the foot loads one into the form; ✕ deletes it.

## Not done (yet)

- Saved searches shared between people or browsers (in the database).
- `$incoming` of a document (the API has it for entities only).
- Groups of alternatives inside an alternative (the API takes them; the form does not offer them).
