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

## Rows added one by one, and the types there are (2026-11-10)

- **No row until a filter is added.** A node of the form (the root, a nested form, an alternative) shows only what
  has been added to it, in the order it was added, and ends with a menu, **+ Add a filter**: its fields (those not
  there yet), then under "More" what is not a field (Mentions, Referred to by, Contains, Inside, Any of, Order by, as
  the node can have them). A field is added with its first operator (and, for a relation to one type, that type's
  form); a row with nothing in it is no condition. ✕ takes a row out, and it is offered again. The schema side is
  `extraRowsOf`, `newRow`, `newCondition` in `searchForm.ts`.
- **The types offered for a relation are those there are.** When a relation is "is one matching" and can point at
  more than one type, the form asks `POST /api/search/types` which types the nodes that fit **the rest of that node's
  form** point at (`whereWithout`: the field's own conditions left out; a nested node asks with `parts: true`), a
  moment after the form changes, in the browser only. The menu (and the menu that changes the type of a nested form)
  then lists only those, each with its count (`foundTargets`; a type found below one the relation names counts); with
  one there is no menu, and with none it says "There are none". Until the answer comes, or if it cannot, every type
  is offered.
- **Fixed**: a nested form of a type that is only ever part of a document (the demo's `Transfer` in
  `Factoid.statements`) was refused by the API with the message for a search of such a class; and an abstract type
  chosen in a nested form (`Statement`) was refused as not one of the relation's types. See
  [structured-search.md](structured-search.md#decisions) (step 1, "Result unit").

**Tests:** `searchForm.test.ts` (the functions above), `SearchPanel.test.tsx` (the menu, the request for the types, the
narrowed menu with counts, "There are none"), `test_search_form.py::test_there_is_no_row_until_a_filter_is_added`, the
narrowed menu of one type in `test_a_nested_form_describes_what_a_relation_points_at`; the API: conformance
`test_a_document_only_ever_inside_another_is_found_in_a_pattern`, `test_the_types_a_relation_points_at_are_counted_through_wrappers`.

## The look, to the style guide (2026-11-10)

No native `<select>` in the panel: every menu is `MenuSelect` (`components/search/MenuSelect.tsx`), a box drawn as a
text box is (32px, a thin chevron) whose list opens joined on to it, as the search for an entity does; the menus that
add something (+ Add a filter, + then by, + Add a document it contains, + Add what refers to it) are the dashed `add`
button opening the same list, with group heads (Fields, More). The keys are a select's. A type is shown as it is everywhere: Contains chooses its document in the menu of types (`TypeMenu`, by the hierarchy), and the options of Referred to by are the type as a tinted chip, then the field. A long list scrolls only up and down (the room of its scroll bar is kept). The choices of Through and Inside are chips in the colour of their type (a space's own colour; a reified relation or a conjunction the plain tint), joined; a chosen one is its colour solid (`kindSolid`): white text on the 700 shade, or dark text on the bright 400 of a light hue (yellow, amber, lime), which so dark would be brown. Every line of a condition is
32px (the `md` of `buttonClass`): NOT is small and faint, red when on, as the NOT in the head bar of a nested form; ✕ is a square icon button at
the end of the line. A row of entries (Order by, Contains, Referred to by, Any of) goes when its last entry is taken
out, so it has its own ✕ only while it is empty. Tests: `MenuSelect.test.tsx`.

## Only choices that can change what is found (2026-11-10)

A choice the form offers has to be able to change the result. **Through** offers a wrapper only if some way to what
the relation points at does not pass through it (`throughChoicesOf`): a wrapper on every way (the demo's
`Factoid.source`, only ever `AtPage[...]`; a single `Negative[Person]`) is passed through by every value, so it is not
offered. **Inside**, on the nested form of what a relation points at, offers the semantic spaces that relation can
pass through, less any it always does (`spaceChoicesOf`), not every space of the project; a nested form not reached
by a relation (Contains, Referred to by) offers them all. Tests: `searchForm.test.ts`.

## Not done (yet)

- Saved searches shared between people or browsers (in the database).
- `$incoming` of a document (the API has it for entities only).
- Groups of alternatives inside an alternative (the API takes them; the form does not offer them).
