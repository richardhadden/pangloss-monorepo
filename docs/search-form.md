# The search form of a list ✅

Step 6 of [structured search](structured-search.md): a form on the list page of a type that builds a search pattern
(`POST /api/search`) from the fields of the type, as the entry form edits an item from them. Built 2026-11-02.

**Tests:** `schema/searchForm.test.ts` (the pattern made of each operator), `components/search/SearchPanel.test.tsx`
(the rows, operators, entities, nested forms, what refers to an entity), `ConsoleSearch.test.tsx` (the button),
`e2e/test_search_form.py` and `test_dev_mode.py::test_the_search_form` (in the browser).

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

## Not done (yet)

- Two conditions on one field (`$all` over the same field), and "any of" groups of rows (`$any_of`).
- Ordering by a field (`order_by`); the order is by label, as the list's.
- `$somewhere` (a document of some type anywhere in the document), `through` and `$spaces` (semantic spaces).
- `$incoming` of a document (the API has it for entities only).
- Saving searches.
