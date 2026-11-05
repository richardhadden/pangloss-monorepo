# Unsaved changes and stashed items

Status: ✅ built (2026-11-05).

Leaving a form with changes in it by accident loses them. The interface now (a) warns before a form with changes is
left, (b) offers to *stash* a new head document instead, keeping it in the browser to finish later, (c) shows what is
stashed beside the clipboard where another one of the same type could be made, (d) asks for a label before stashing
something that has none, (e) has a Stash button beside Save, and (f) turns Save off until there is a change to save.
When a stashed item is taken up again, the entities it refers to are checked against the database in one request
(`POST /api/references`): those that are gone are taken out (and listed), and labels are brought up to date.

## What counts as a change

`createItemFormState` keeps two plain copies beside the store being edited: the *baseline* (what the item is when
nothing is to be saved: the item as loaded, or a blank new one) and the *start* (what the form opened with: the same,
or the stashed item it was opened from). Two memos compare the store with them, each made comparable by
`cleanForSave` (what would be sent: so a field typed in and emptied again is no change, and an entity's label does
not count):

| | compared with | used for |
|---|---|---|
| `changed()` | the baseline | Save is on only when it is true (and nothing is being sent) |
| `edited()` | the start | leaving asks first; Stash is on |

A stashed item opened again has its baseline blank and its start the stash: it can be saved at once, but leaving it
untouched asks nothing (it is still stashed).

## Leaving

`ItemForm` takes `guardLeaving`, which it calls with a function the page calls before it is left:
`(leave) => boolean`, true if it may go now. The application's New and Edit pages give it to the router's
`useBeforeLeave` (core knows no router): when the form says no, the navigation is held, and the form's dialog decides
(`LeaveDialog`): *Stay*, *Leave without saving*, and, for a new head document that is not an entity, *Stash and
leave*, with a label field if the item has none. Cancel is a way of leaving too, so it asks the same. A save, a delete or a stash that worked lets the page go
without asking. Leaving the page altogether (reload, closing the tab, an address typed) gets the browser's own warning
(`beforeunload`), which can offer nothing more.

## The stash

`StashProvider` (core, `context/stash.tsx`) keeps the stashed items in local storage, per user
(`pangloss.stash.<username>`), shared by tabs, as the clipboard is. An entry is `{ key, type, label, value, when }`;
`value` is the form's whole item. Stashing an item that was opened from the stash replaces that entry; saving it
removes it.

The Stash button (beside Save, on the form of a new head document that is not an entity) stashes at once if the
item has a label, and otherwise asks for one (`StashDialog`); then the page goes to the list of the type
(`onStashed`).

Opening a stashed item is a link to `/<Type>/new?stash=<key>`. The New page reads the entry once settled (local
storage is the browser's: the server renders "Loading"), asks `/api/references` about every entity it refers to, and
opens the form on the result (`restoreStashed`). What is gone is shown above the form as chips.

## The bar at the bottom

`ClipboardBar` holds two sections side by side, of one height: the clipboard (where a form is on the page and there
is something on it, as before) and the stash (where the page has said what type it is about with
`stash.showFor(type)` — the list page and the New page — and there are stashed items of that type or its subtypes).
The arrow at the left folds the whole bar to its head line. Clicking a section's name shows all of it (it takes most
of the width, and grows taller); the other stays beside it.

## The API

`POST /api/references` `{"ids": [...]}` → `{"found": [{id, type, label}]}`: the entities with those ids that are not
deleted, in the order asked, with their labels as they are now. Up to 1000 ids; open to everyone, as autocomplete is.
It is `Entity.references(ids)` (`Person.references(ids)` keeps only people), bound by `initialise()` to the backend's
`references` (`pangloss_cypher.read_functions`), and to one request in the SDK. Tested in the conformance suite
(`test_references_live.py`).

## Not done

- An entity's form (page or dialog) cannot be stashed.
- An edit of an existing item is not stashed: leaving it only warns.
- The stash is in the browser: another browser does not see it.
- A card in the bar shows the item as it was stashed; only the form opened from it has the labels brought up to date
  (the entry itself is not rewritten until it is stashed again).
