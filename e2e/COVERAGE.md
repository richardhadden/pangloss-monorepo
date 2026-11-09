# What the end-to-end tests cover

Keep this current: when a page or feature is added to the interface (or a test is added here), change its row.
✅ tested · 🚧 partly · ⬜ not yet · — not built, so nothing to test

170 tests. The e2e project (`conftest.py`) has `Person` (`has_role: list[Role]`), `Role` (`has_type`), `RoleType` (a
typology, also a `Role`) with Clerk > Secretary and Advisor, and `Statement` (a document: `text`, `about: Person`). The `data`
fixture adds Maximilian (his secretary: a `Role` of the type Secretary), Marie of Burgundy (her advisor, and a statement
about her "held court at Ghent") and Charles the Bold (no role); `types` has only the types; `stack` has one admin user.

## Interface core (`interface-app`)

| Area | State | Where / notes |
| --- | --- | --- |
| Development build (`dev_url`: `pangloss interface dev` on the same API): lists, search, the search form, an item, back, a deleted item and a page that is not there, edit and new, a typology, with no error in the page (Solid's dev build stops on what the built one lets through, such as a write while rendering) | ✅ | `test_dev_mode.py` |
| Home: the models of the project are listed, each a link | ✅ | `test_navigation.py` (the page is a placeholder: unstyled, "Pangloss Yo!") |
| Navigation bar: opens when the mouse is over it, closes when it leaves | ✅ | `test_the_navigation_bar_opens_and_closes` |
| Navigation bar: while open its button is a pin; a click pins it open (stays when the mouse leaves or a link is followed), another unpins | ✅ | `test_clicking_the_button_of_the_bar_…`, `test_a_pinned_bar_…`, `test_unpinning_…` |
| Navigation bar: pinned, the page and the console move across (console still centred) | ✅ | `test_the_page_and_the_console_move_across_for_a_pinned_bar` |
| Language: another language is fetched (server function) only when chosen, once; the words change; `<html lang>` follows | ✅ | `test_another_language_is_fetched_only_when_it_is_chosen` |
| Language: the choice is kept in `localStorage` over a reload | ✅ | `test_the_language_chosen_is_kept_over_a_reload` |
| Language: the interface modules' words come from their own apps' `translations/ui.jsonc` (derived, timeline, calendar link, typologies section, history), and a label an app gives a link in the bar is translated by its slot | ✅ | `test_derived.py::test_the_words_of_the_modules_are_their_own_and_follow_the_language`, `test_history.py::test_the_history_follows_the_language`; Vitest `NavModelList.test.tsx` |
| Language: the fade while it loads | ⬜ | (CSS on `html[data-translating]`; checked by hand) |
| Navigation bar: the pin is kept in `localStorage` over a reload | ✅ | `test_the_pin_is_remembered` |
| A list of annotated values (`list[WithCertainty[str]]`): shown one by one, each with what is said of it; added to and removed from in the form, checked at its place in the list, sent as a list | ⬜ | Vitest only (`ItemContents.test.tsx`, `ItemForm.test.tsx`, `validation.test.ts`): no demo model has one yet, so no browser test |
| Navigation bar: sections and links to the lists of the models | ✅ | `test_the_navigation_bar_links_to_the_lists` |
| Navigation bar: the filter above the types (part of any name, any case; nothing left: a message; ✕ and Escape clear it) | ✅ | `test_the_types_in_the_navigation_bar_are_filtered`, dev build in `test_making_and_editing`; names in other languages and accents: Vitest (`NavModelList.test.tsx`) |
| Navigation bar: Cmd+K (Ctrl+K off a Mac) opens it with the cursor in the filter; again, Escape in the empty filter, or the focus leaving closes it, the focus going back; a pinned bar stays; not while a dialog is open | ✅ | `test_the_shortcut_opens_the_navigation_bar_with_the_cursor_in_the_filter`, dev build in `test_making_and_editing`; the rest: Vitest (`NavBar.test.tsx`) |
| Navigation bar: in the filter, the arrows choose a type (the first after each change), Enter opens its list, Cmd/Ctrl+Enter makes a new item (logged in, a type that can be made) | ✅ | `test_the_filter_of_the_types_chooses_with_the_arrows_and_enter_opens_the_list`, `test_the_filter_of_the_types_makes_a_new_item_for_someone_logged_in`; what cannot be made: Vitest (`NavModelList.test.tsx`, `NavBar.test.tsx`) |
| Navigation bar: going to a type (Enter, Cmd/Ctrl+Enter, or a click) empties the filter | ✅ | `test_going_to_a_type_empties_the_filter`; Vitest `NavBar.test.tsx` |
| Navigation bar on a touch device (no hover) | ⬜ | |
| Console bar names the type (plural on a list) and the item | ✅ | `test_the_console_names_the_type_of_the_page` |
| Console bar on an item page: created / modified, by whom and when, two light rows on the right | 🚧 | unit tests in `Console.test.tsx`; not in e2e |
| Login dialog: logging in; the session survives a reload | ✅ | `test_login.py` |
| Login dialog: a wrong password is explained, the right one then works | ✅ | |
| Login dialog: Escape and the close button give up | ✅ | |
| Log out | ✅ | |
| `RequireLogin`: `/Person/new` opens the dialog; giving up goes home; logging in shows the page | ✅ | |
| "New Person" button only for someone logged in | ✅ | |
| An item that was "Page not found" before logging in (an unpublished document) is shown once logged in, without a reload | ✅ | `test_an_item_not_found_before_logging_in_is_shown_once_logged_in` (the 404 simulated in the browser) |
| No "New" button, and `/TYPE/new` says why, for a document that cannot be made on its own (`create_directly=False`; `ReportSection` in the e2e project) | ✅ | `test_a_document_that_cannot_be_made_on_its_own_has_no_new_button_or_page`; Vitest (`Console.test.tsx`) |
| List page: items, count, links | ✅ | `test_lists_and_items.py` |
| List page: search (`?q=`), kept in the address, no result is a red 0, an address with a search shows it; typing is not held up or undone by the searches it makes | ✅ | `test_typing_is_not_held_up_or_undone_by_the_searches_it_makes`; Vitest (`ConsoleSearch.test.tsx`) |
| List page: a character typed with no field focused goes into the search, after what is there (not with a modifier, a space, in another field, or under a dialog) | ✅ | `test_typing_on_a_list_page_goes_into_the_search`; the rest: Vitest (`ConsoleSearch.test.tsx`) |
| List page: with the search box focused, the arrows choose an item (drawn as when hovered, the top one after each search) and Enter opens it, or searches if what is typed is not what is listed; a space between the console and the list | ✅ | `test_the_arrows_in_the_search_choose_an_item_and_enter_opens_it`, `test_a_new_search_selects_the_top_item`, `test_the_arrows_in_the_search_keep_the_selected_item_on_show_in_a_long_list`, `test_there_is_a_space_between_the_console_and_the_list`; Enter's choice: Vitest (`ConsoleSearch.test.tsx`) |
| List page: deep search toggle, typing makes none, Enter / run button make it, turning it off | ✅ | finds a person through a statement |
| List page: search form (button beside Deep search, panel under the console pushing the list down, closed again); a condition narrows the list and is kept in the address (`?form=`), reopened from it; not; Clear; entities picked; a nested form for what a relation points at; what refers to an entity; what a document mentions; the text box narrows it and Deep search is greyed out; the form is not offered for a document class that is only ever part of another (`canBeSearched`: the API refuses such a search, naming what holds it) | ✅ | `test_search_form.py`; `canBeSearched`: Vitest (`schema.test.ts`); dev build: `test_the_search_form`; operators, between, enum pills, Enter: Vitest (`SearchPanel.test.tsx`, `searchForm.test.ts`, `ConsoleSearch.test.tsx`) |
| List page: search form: order by, two conditions on one field, groups of alternatives, saved searches (browser), the panel in from the ends of the console | ✅ | `test_search_form.py`; contains somewhere, through, inside spaces: Vitest (`SearchPanel.test.tsx`, `searchForm.test.ts`): the e2e project has no nested documents or semantic spaces |
| List page: search form on dates, numbers, decimals, enums of the demo's models | 🚧 | checked by hand with screenshots; the e2e project has no such fields |
| List page: "truncated" (`count+`, "narrow the search") | ⬜ | needs more results than `SEARCH_HIT_LIMIT`: set it low in the e2e settings |
| List page: scrolling loads more (virtualised, a page at a time); `?at=` kept as it is scrolled, and reloading or going back starts there | ✅ | `test_a_long_list_is_loaded_as_it_is_scrolled_and_starts_where_it_was_left` (130 people) |
| Item page: fields, references as chips, reverse relations, no empty rows | ✅ | |
| Item page and form: every row of fields under a faint rule; rows of reverse relations with more room, their items centred on each other in a line; head bars and chips framed by a hairline, square buttons; the spaces of a chip or a list row as muted tabs before it, not round it | 🚧 | seen in screenshots of the demo data; no test of the look |
| Item page: reified relations without a "target" key; the full trail (spaces and documents) round a chip; reverse through a reified relation shows the field in its document | 🚧 | unit tests in `ItemContents.test.tsx`; the e2e project has no reified relation or semantic space |
| Dates (`pangloss_dates` module): a date is said as a person would, not listed by field | 🚧 | unit tests in the module (`format.test.ts`, `DateCard.test.tsx`); the e2e project has no dates |
| Item page of an entity that much refers to: the item is read alone (`?incoming_limit=0&extras=false`) and what refers to it apart (`GET .../incoming?limit=25`, `IncomingRelations`, in a boundary of its own with a spinner, streamed after the item; the modules' sections follow it, `Reveal`); the first 25 of each reverse relation, "and N more" after a row that has more (reads the next hundred, by label; gone when the row has them all); with a module's view chosen (by date), a notice of how many are not read and **Read them all**; from 200 references on only the rows on show are rendered (`VirtualRows`) | ✅ | `test_lists_and_items.py::test_an_entity_that_much_refers_to_has_the_first_of_each_and_reads_more_when_asked`; the routes: `test_model_routes.py::test_an_entity_is_read_apart_from_what_refers_to_it`, the conformance suite; Vitest `ItemContents.test.tsx` (read apart; pages of a hundred; an item read whole; the notice; thirty fields of ten, a window's worth rendered); the dev build by hand on the smoke test project (3,927 references, no error; measured in docs/large-data.md) |
| Item page: a type in a field leads to the page of the type (module page) | ✅ | |
| Item page: "Derived" section (`_derived` of `pangloss-derived`, the `itemSections.Derived` of its interface module; read by the section itself from `/api/derived/about/{Type}/{id}` when the item came without it, in the section's own `Loading`, shown after what refers to the item (`Reveal`)): after the item's facts, well apart, under a bar; each class with its count; each fact with the other end and its fields (the two symmetric ends as one "member"), never the item itself; "Why (n)" opens the rule and the evidence documents as chips, and closes; "and N more" reads the next page; after the Timeline when sorted by date; no section for an item with nothing derived; a deleted document hides at once only the facts it alone justifies | ✅ | `test_derived.py` (5 tests; the e2e project derives `SameGroup` from two `Membership`s); unit tests in `pangloss_derived/interface` (`DerivedSection.test.tsx`, with the section reading for itself); the read rule: `pangloss-derived/tests/live` (`test_a_deleted_factoid_hides_only_what_it_justifies`) |
| Interface-module hooks on the item page: `itemSections` (after the contents), `incomingViews` (another view of what refers to the item, offered while it takes some; the rest stays by field), and `InterfaceConfig(disabled=...)` leaving either (or a console action) out | ✅ | e2e through the dates module (the timeline tests above); `disabled` and the sections: Vitest `ItemContents.test.tsx`; the check: `test_interface_modules.py`, `test_interface_config.py` |
| Item page of a subtype (308 to its own route) | ✅ | through `/Role/<concrete type id>` in `test_typology_item.py` |
| Not-found page, with a 404 status | ✅ | `test_navigation.py` |
| An item that is not there is explained (`role="alert"`): "Page not found" in the page as the server renders it too, not the built server's "Internal Server Error" | ✅ | `test_an_item_that_is_not_there_is_explained` |
| An unknown type in the address | 🚧 | explained either way; what it should say is not decided |
| Server rendering: the first response has the data | ✅ | raw response text; **not** complete without JavaScript (Solid streams it) |
| Language switch | — | the bar shows the languages but `App.tsx` passes no `onLanguage`: it does nothing yet |
| Interface translations shown in another language | — | not connected |
| Edit button in the console of an item: only for someone logged in | ✅ | `test_editing.py`; unit tests in `Console.test.tsx` |
| Edit item: the form has the item, saves a change and shows the item | ✅ | |
| Edit item: someone else saved meanwhile (412): nothing is overwritten, the form says so, and "Load the new version" makes it again from the item as it is now | ✅ | `test_an_item_saved_meanwhile_is_not_overwritten_and_the_new_version_can_be_loaded` |
| Form: an enum or literal field of 8 values or fewer is pills (a radio group; the chosen one again: none), more is a dropdown | 🚧 | unit test in `ItemForm.test.tsx`; the e2e models have no enum |
| Form: what is added to a list (Add, a type from the menu, a paste, an entity found) lights up for a moment, and the cursor goes into it (not for an entity found: the search keeps it) | 🚧 | checked with the demo data; no test |
| Item page: a type of a typology in a field is the same chip as in the form (`TypeCard` uses `DefaultReferenceChip` as a reference) | 🚧 | checked with the demo data |
| Item page of a document inside another: "Contained in" and a chip to its head with its label, whose page scrolls to the document (`?show=`); the whole item in bands for its context, the bands of documents linking to them | 🚧 | checked with the demo data, built and dev (a Transfer three Orders deep); `contextPath` unit test; the e2e models have no nested documents |
| Edit button of a document inside another: to the form of its head document (`?show=<id>`), scrolled to its block | 🚧 | checked with the demo data (a Transfer in a Factoid); the e2e models have no nested documents |
| New item form: fields, an entity found by search, saved and shown | ✅ | |
| A new entity made from the form (+ beside the search, dialog) is chosen | ✅ | |
| With several entity types, + opens the dialog on the types (Back to them), then the form of the one chosen | ✅ | test_dev_mode (unit: ItemForm.test) |
| An optional single relation or embedded object (`Person \| None`, `Date \| None`): starts empty, may be saved empty, and what is added can be removed and saved as none | ✅ | `test_an_optional_relation_and_embedded_object_start_empty_may_be_left_out_and_removed` (a `Letter` of the e2e models) |
| A required list with one possible type (not an entity) starts with the items `MinLen` asks for (the Alternative of an Identification); a list at `MaxLen` has no Add | 🚧 | Vitest (`ItemForm.test.tsx`); checked with the demo data |
| Entity search before anything is typed: the most used of the types (most edges out: referred to most), asked for as the field is drawn; those picked lately (local storage) first, with a clock, and only while they match what is typed; only those the API still has (a database made again leaves the browser's list behind: one that is gone is not offered, and is forgotten; so is one a save is refused for, and what holds it on the clipboard) | ✅ | `test_an_entity_field_offers_the_most_used_then_puts_those_picked_lately_first`, `test_an_entity_picked_lately_that_is_no_longer_in_the_database_is_not_offered`; the refused save: Vitest (`ItemForm.test.tsx`); types and subclasses, accents: Vitest (`ItemForm.test.tsx`) |
| A rejected form says what is wrong and keeps what was typed; Cancel leaves without saving | ✅ | |
| Delete on an item's page (logged in; not a document inside another) and on its edit page (not on a new item): a dialog asks the API first (`GET …/deletable`, which marks nothing); "Are you sure", Cancel, Delete goes to the list with a toast; what cannot be deleted (an entity referred to, a part of another document, `delete_only_if`) says why, with up to ten links to what refers to it, and only Close | ✅ | `test_delete_asks_first_then_deletes_and_goes_to_the_list`, `test_an_item_is_deleted_from_its_own_page`, none logged out (`test_an_item_page_has_an_edit_button_only_when_logged_in`), `test_what_is_referred_to_cannot_be_deleted_and_says_by_what`; Vitest (`ItemForm.test.tsx`); the check: conformance (`test_check_deletable_says_why_and_writes_nothing`), API (`test_deletable_says_whether_and_why_not`) |
| Shares (`SumsTo`, `pangloss_library`'s `WeightedAlternative`): a number with `Slider()` is a slider with its box beside it; one chosen gets an even share, dragging one makes the others give way in proportion, one removed leaves the others to share the whole; not adding up is red at the list (and refused by the API) | ✅ | `test_weighted_alternatives.py` (a `Suspicion` of the e2e models); the arithmetic: Vitest (`share.test.ts`), the form (`form.test.ts`), the sliders (`ItemForm.test.tsx`), the check (`validation.test.ts`); the API: `pangloss-models/tests/test_shares.py`, conformance |
| Item page: the properties of an edge are the end of the entity's chip, inside its frame (`19%` for a field with `Slider(unit=…)`, else its name and value); a `WeightedAlternative` has its own card (`pangloss_library:WeightedAlternativeCard`): no head, and the name "Alternatives" only when there are several | 🚧 | Vitest (`ReferenceChip.test.tsx`; the card's own tests in `pangloss_library/interface`, run in a synced project: `npx vitest run --root modules/pangloss_library`); no e2e test of the item page yet |
| Form checked in the browser on Save (valibot schemas from the exported models): nothing sent; the names of the fields with problems red, with why under them; a red toast; a field changed is unmarked; a 422 shown at its fields in the same way | ✅ | `test_an_incomplete_form_is_not_sent_and_says_what_is_wrong_at_its_fields`; the schemas: Vitest (`validation.test.ts`), placing at rows (`form.test.ts`), nested, embedded, 422, other errors as a toast, the entity dialog (`ItemForm.test.tsx`); scrolling to the first problem checked by hand with the demo data |
| A toast at the bottom right after an item is saved or made (also an entity made from the form); it goes after 4 s or on a click | ✅ | `test_editing_an_item_saves_a_change`, `test_an_entity_is_made_from_the_form_and_chosen`; timing and click: Vitest (`Toasts.test.tsx`) |
| Clipboard: cut in one form, kept across pages (local storage), shown at the bottom of a form page only, pasted into another form | ✅ | `test_an_entity_cut_in_one_form_is_pasted_into_another`; ids kept or dropped, what fits where, folding: Vitest (`ItemForm.test.tsx`, `clipboard.test.ts`); the e2e project has no sub-documents to cut |
| Unsaved changes and the stash: Save off until there is a change; leaving a form with changes asks (stay, leave without saving, or stash and leave, with a label asked for if there is none); the Stash button; stashed items of the type beside the clipboard on its list and new pages, each opening the form (`?stash=`), which can be saved at once and leaves the stash when saved; entities checked when a stashed item is taken up (gone ones taken out and listed, labels brought up to date) | ✅ | `test_stash.py` (all four), `test_cancel_goes_back_without_saving`, dev build: `test_leaving_and_stashing`; the dialog, the browser's warning, re-stashing in place, the bar's sections: Vitest (`Stash.test.tsx`, `stash.test.ts`, `fetch.test.ts`) |
| Form: a nested block folds by clicking the grey of its head bar (no fold button; folded, a ▸ before the label) | ✅ | Vitest (`ItemForm.test.tsx`); checked with the demo data |
| Item page and form: a block nested five deep starts folded (view: its head bar is the toggle), and what is in it is made when it is unfolded; five more levels, then folded again; `?show=` opens the way to its part | ✅ | Vitest (`ItemContents.test.tsx`, `ItemForm.test.tsx`); the smoke test project's 61-deep factoid on both builds (`pangloss-smoketest/smoke_scripts/ui_unfold.py`); the e2e project has no deep nesting |
| Item page and form: in a narrow place (nested deep) the name of a field goes above it, the indents shrink, and the fields keep a floor width (container queries) | 🚧 | the classes: Vitest (`ItemContents.test.tsx`); the look: screenshots of the smoke test project at 61 deep |
| Form: a document inside another narrowed (↧) or widened (↥) to a type below or above it, what it holds moved to the fields of the new type (also those that stand for others, `subclasses`); a narrowing only where nothing would be lost (the others greyed in the menu, "Would lose: …", not chosen); a widening that would lose something asks first (also the properties of a relation); saved as the same node with its new type | ✅ | `test_retype.py` (the e2e project's `Provenance` of `CreationOfPhysicalObject` > `CreationOfArtwork` > `CreationOfPainting`; its `subject` bound into `object_created` reaches a creation of a painting's `painting_created`, in the form and on the server); dev build: `test_narrowing_and_widening_a_document_in_a_form`; Vitest (`retype.test.ts`, `Retype.test.tsx`, `TypeMenu.test.tsx`); the save on both backends: conformance `test_update_changes_the_type_of_a_nested_document_that_keeps_its_id` |
| Form: a relation to entities and reified relations or conjunctions has the search at once and a button for each of the rest under it; with `default_reified_type`, an entity found is put in that reified relation (through a conjunction too), which is not a button | 🚧 | Vitest (`ItemForm.test.tsx`, `relationLayout.test.ts`); seen in screenshots of the demo (`MemberOf.member`, `Activity.participants`); the e2e project has no reified relation |
| Form: the entity search chosen with the arrow keys and Enter (Enter does not save), Escape closes it; the add button opens, in its place, a box of the types to add, in zones (types on their own, each semantic space, conjunctions; what can be pasted under the button; hierarchy indented inside the buttons, abstract classes not selectable; one Tab stop, arrow keys; Escape, close button, click elsewhere or Tab out close it), what was added or pasted flashing, nested documents, reified relations, conjunctions, edge properties, dates | 🚧 | unit tests (`TypeMenu.test.tsx`, `ItemForm.test.tsx`, `typeChoices.test.ts`; the flash is not tested); the e2e project has no semantic space, conjunction, reified relation or date |
| Form: a field binding (`bind_to_child_field`): the parent's field copied to the bound fields of what the relation holds as it changes, and to what is added under it; a child changed by hand keeps its own; under a child that binds the same field, its own; a reified relation copied without its id; the types below those allowed or excluded; a narrower child's field that stands for the bound one (not given a value it cannot hold, and saying so at the field until it is filled in) | ✅ | e2e `test_retype.py::test_the_subject_of_a_provenance_is_given_to_a_step_of_a_narrower_type_in_its_own_field`, `test_a_step_that_cannot_hold_the_subject_says_so_at_its_field` (dev build: `test_narrowing_and_widening_a_document_in_a_form`); Vitest `formNotices.test.ts` (and the API: `test_the_server_gives_the_subject_to_a_step_of_a_narrower_type`); Vitest (`form.test.ts`); seen in the demo with a browser (`Order.ordered_to` into a transfer's `given_by`) |
| `InterfaceMeta(headless=True)`: a reified relation that is the only type of a single, required field has no head bar, on the item page and in the form (what it holds, then its own fields); anywhere else its head | 🚧 | Vitest (`headless.test.ts`); seen in screenshots of the demo (`Factoid.source`, `AtPage`: view, edit, new); the e2e project has no reified relation |
| Code fetched: forms and what is only for someone logged in (review, history, Zotero console actions) are not fetched by a reader logged out; the search form when it is opened; a logged-in user's console actions | ✅ | `test_code_splitting.py` |
| Search from the home page / global search | — | not built |

## `pangloss_typology` module

| Area | State | Where / notes |
| --- | --- | --- |
| Tree page lists the types, nested and indented | ✅ | `test_typology.py` |
| Not logged in: not draggable, no pencil | ✅ | |
| Drag onto the middle of a row moves the type below it (API and reload) | ✅ | |
| Drag onto the top or bottom edge of a row puts the type beside it (the top level beside a top-level type) | ✅ | |
| Drop marks (`data-drop` into / above / below), none where a drop is not allowed; rows do not move when a drag starts | ✅ | |
| A type cannot be dropped below its own subtype | ✅ | |
| Live feed: a move made by someone else shows without a reload | ✅ | `PANGLOSS_TYPOLOGY_POLL_MS=300` in the stack |
| Server refusal is shown (`role="alert"`) and the move undone | ✅ | the move request answered 409 by `page.route` |
| Pencil edits the label in place (Enter saves, Escape leaves it) | ✅ | blur and an empty label in Vitest |
| A subtype is added in a dialog from its chip (no new page) | ✅ | |
| A top-level type is added from the console's New and from the buttons above and below the tree | ✅ | |
| Dev build: drag and label edit with the dev server's own server functions | ✅ | `test_dev_mode.py` |
| Collapse / expand | ✅ | |
| A type links to its page | ✅ | |
| Item page: path (breadcrumb) | ✅ | `test_typology_item.py` |
| Item page: subtypes with counts | ✅ | |
| Item page: entities, "including subtypes" checkbox | ✅ | |
| Item page: "Show more" (50 at a time) | ✅ | creates 52 roles |
| Item page: edit labels (default, `de`, description), saved; cancel | ✅ | |
| Item page: not logged in, nothing can be changed | ✅ | |
| `is_concrete` switch: on makes the type a usable `Role`; the page of the type answers at `/Role/…` | ✅ | |
| `is_concrete` switch: refused while used, the reason shown | ✅ | |
| Drag and drop with the keyboard | — | the "Move to…" select is the keyboard way; arrow-key dragging is not built |
| Card (`TypeCard`) | ⬜ | where a type is shown as part of something else: no model uses it yet (a chip is used for references) |
| Other languages than `de` | ⬜ | |

## `pangloss_review` module

The e2e project's `Report` is reviewed (`ReviewMeta(reviewable=True)`), with nested `ReportSection`s; `ann` makes the reports, `bob` writes what someone else does, and self-review is not allowed.

| Area | State | Where / notes |
| --- | --- | --- |
| Console of a reviewed document: a flag button coloured by status, labelled with it; opens and closes the panel (pressed; Escape) | ✅ | `test_review.py::test_a_reviewed_document_has_a_review_button_with_its_status`; Vitest (`ReviewAction.test.tsx`) |
| No button for a document that is not reviewed, an entity, or a reader who is not logged in | ✅ | `test_a_document_that_is_not_reviewed_has_none`; the rest: Vitest |
| Status buttons at the top of the panel; a change goes to the API at once (publishes with Checked), "Reviewed by" | ✅ | `test_changing_the_status_publishes_it_and_goes_to_the_api` |
| A status the API refuses (self-review not allowed) is undone, with a red toast | ✅ | `test_checking_what_one_made_is_refused_and_said` (the e2e project has `REVIEW_ALLOW_SELF_REVIEW = False`; reports are made by `ann`) |
| A comment: shown at once on the right ("You", "Sending…"), confirmed by the feed, counted on the button | ✅ | `test_a_comment_is_mine_on_the_right_and_counted` |
| What another user does (a comment, a status) reaches the open page and panel without a reload (`live()` feed) | ✅ | `test_what_someone_else_does_reaches_the_open_page_without_a_reload`; also in the dev build (`test_dev_mode.py::test_the_review_panel`) |
| Resolve a comment; "Show resolved" shows it again, faded | ✅ | `test_a_comment_is_resolved_and_shown_again_on_asking` |
| The edit page has the button and panel too, apart from saving | ✅ | `test_the_edit_page_has_it_too_apart_from_saving` |
| References to parts: `#` in the box opens the list of the documents inside (filtered by what follows), Enter puts `#<id>` in the text (several per comment); read, each is an inline chip (type, label) that shows the part on the page; the first is the API's `targetId` | ✅ | `test_parts_are_referred_to_with_a_hash_and_shown_inline`, `test_a_reified_relation_document_can_be_referred_to` (the e2e `Report` has `findings: list[Finding[ReportSection]]`); also in the dev build; details (arrows, multi-word, put back on failure, a `targetId` without a reference): Vitest (`Composer.test.tsx`, `parts.test.ts`, `ReviewPanel.test.tsx`, `ReviewAction.test.tsx`) |
| The button "Refer to a part…" opens the list; Escape closes the list, not the panel | ✅ | `test_the_button_opens_the_list_and_escape_closes_only_it` |
| A comment about a part since removed says "(no longer there)" | ✅ | `test_a_comment_about_a_part_since_removed_says_so` |
| List: a flag at the right of each row of a reviewed document, or of what is inside one (its head's status), named by the status; none for what is not reviewed, or a reader logged out; the button to the head further right | ✅ | `test_the_list_flags_the_status_of_what_is_reviewed`, `test_what_is_inside_a_reviewed_document_has_the_flag_then_the_link_to_it`, `test_the_list_flags_nothing_not_reviewed_or_for_a_reader_logged_out`; Vitest (`ListStatusFlag.test.tsx`, `ResultButton.test.tsx`) |
| Queue page `/review` (nav link, logged in): status tabs, type filter, rows lead to the document, back and forward keep the filters | ✅ | `test_the_queue_lists_what_is_to_be_checked_by_status`; also in the dev build |
| Queue: 25 to a page, Previous / Next | ✅ | `test_the_queue_goes_a_page_at_a_time` |
| Queue: needs a login | ✅ | `test_the_queue_needs_a_login` |
| The feed closes when the page is left; reconnects (with a cookie refresh) after the access cookie ran out | 🚧 | Vitest (`ReviewAction.test.tsx`, `poll.test.ts`); the reconnect is not tested in a browser |
| The module's own tests and type-check, in the built project | ✅ | `test_the_module_tests_pass_in_the_built_project` |

## `pangloss_history` module

The e2e project installs `pangloss_history`. The `statement` fixture makes a `Statement` with three versions (made about
Marie at Ghent; moved to Bruges; about Mary and renamed); a `Report` has parts inside it (`ReportSection`s) and review.

| Area | State | Where / notes |
| --- | --- | --- |
| Console of an item: a History button (logged in, item page only); the panel of versions, newest first: version, what happened, who, when, a new label, the fields changed as tags, Current | ✅ | `test_history.py::test_the_panel_lists_the_versions_and_one_slides_out_beside_it`; not logged in, the edit page, gaps: Vitest (`HistoryAction.test.tsx`, `timeline.test.ts`) |
| A version clicked slides out from under the panel, as the item's page shows it; Escape puts it back, then closes the panel | ✅ | `test_the_panel_lists_the_versions_and_one_slides_out_beside_it`; clicked again: Vitest |
| Restore to this point: a dialog with the versions undone and the changes (trail, words), Cancel; Restore makes a new version, the page and the panel are read again, a toast | ✅ | `test_restoring_asks_first_listing_what_is_undone_and_then_changes_the_item`; also in the dev build (`test_dev_mode.py::test_the_history_panel_and_page`, with parts inside) |
| A restore after someone else saved is refused (412), in a red toast | ✅ | `test_a_restore_after_someone_else_changed_it_is_refused` |
| The current version has no Restore; a version with a blocking problem cannot be restored | 🚧 | the first: Vitest; the second is not tested in the interface (the API's restore is: `test_history_restore.py`) |
| Compare page `/:type/:id/history` (from "Compare all"): a column per version, the rows lined up, each cell marked against the one before it, words of a text, parts matched by id; scrolled to the newest | ✅ | `test_the_compare_page_shows_every_version_side_by_side`; the alignment: Vitest (`align.test.ts`, `words.test.ts`, `HistoryPage.test.tsx`) |
| A column "Not recorded" when the graph is ahead of the history | 🚧 | Vitest (`HistoryPage.test.tsx::columnsOf`) |
| One panel on the right at a time: opening history closes review's, and the other way round (`useSidePanel` in core) | ✅ | `test_one_panel_on_the_right_at_a_time`; Vitest (`sidePanel.test.tsx` in core, `HistoryAction.test.tsx`) |
| An item from before history was installed: the panel says so and names `pangloss history baseline`; after it, a "Recorded as it was" version | ✅ | `test_an_item_from_before_history_has_none_until_a_baseline_is_recorded` |
| An upgraded version (models changed since) is shown with the notice and its problems, in plain words (by `kind`, the field named as the form names it; the API's message is the tooltip) | 🚧 | the sentences: Vitest (`problems.test.ts`); the API's upgrade (`test_history_upgrade*.py`); the drawer's notice checked by hand (a screenshot with the version's answer changed by `page.route`) |
| The module's own tests and type-check, in the built project | ✅ | `test_history.py::test_the_module_tests_pass_in_the_built_project` |

## `pangloss_calendar` module

The e2e project installs `pangloss_dates` and `pangloss_calendar` (Julian, span 1499 to 1501, `CALENDAR_FIELDS = ["Event.when"]`); `Event` has a date, `Feast` is a `DateCharacterisation`. The `dated` fixture makes three events in March 1500 (a day, a range of eight days, a range of two), a reign from 1490 to 1510 (a long period over the whole span), a feast by rule (Benedict, 21 March) and one with no rule (Market day).

| Area | State | Where / notes |
| --- | --- | --- |
| Nav link "Calendar" (Links section) to `/calendar`: the years of the span, each with its months as links and "<n> events" at the end | ✅ | `test_calendar.py::test_the_navigation_bar_links_to_the_years_of_the_calendar`; Vitest (`YearsPage.test.tsx`) |
| Years page without a span says to set one | 🚧 | the e2e project has a span; not tested |
| Month page: 31 day links, six rows, the 1st on the right weekday; a date as a chip on its day, named by its field ("When · Coronation"); a single day known only within two days as a hollow dashed bar between them (not on them); a period of eight days as filled bars across two weeks (cut to the week, open where it goes on); a birth known only to the year listed under the grid ("between 1 January and 31 December"), not drawn; a feast by rule on its day; a chip leads to the document; Next month; the same month in the Gregorian calendar (30 days of April) | ✅ | `test_a_month_is_a_calendar_page_with_what_is_dated_on_its_days`; lanes, open ends, overlapping bars, "+N more", the hollow bar, the list: Vitest (`MonthGrid.test.tsx`, `MonthPage.test.tsx`, `lanes.test.ts`) |
| Day page: weekday and date, the same day under its Gregorian name (a link), what is dated on it: a period `stated` on each of its days, a single date `possible` with the days it could be on unless it names the day; Next day; a feast by rule says so and "repeats" | ✅ | `test_a_day_names_itself_in_both_calendars_and_lists_what_is_dated_on_it`; Vitest (`DayView.test.tsx`) |
| Logged in, day page: the search of the characterisations attaches one picked (toast, listed as attached to the day, in the month too, in the API as `manual`), the remove button of its chip takes it away, the + of the search offers Feast and Event (a document that can have a date) and makes either in a dialog, starting on the day: the feast is on the day, the event under "On this day" (not attached); no "New" buttons in the console | ✅ | `test_someone_logged_in_attaches_a_feast_to_a_day_and_takes_it_away` |
| Not logged in: no attach box or buttons | ✅ | in the day test; Vitest |
| An address that is not a day or a month is explained | ✅ | `test_an_address_that_is_not_a_day_is_explained` |
| Month: the + of a day (logged in) offers the characterisations and the documents that can be made on their own and can have a one-day date somewhere in them (Event, not Report); the form of a Feast with `when` that day; saved, it is on the day; none without a login | ✅ | `test_a_feast_is_made_from_the_plus_of_a_day_in_the_month`; Vitest (`MonthGrid.test.tsx`, `Chrome.test.tsx`) |
| Month: an Event made from a day's + in a dialog, its date that day in the page's calendar (Gregorian); saved, the month is still shown with it on the day, and it is on the same day in the Julian calendar. Every date of every item added in the dialog (a statement of a factoid) starts as the day; not an entity's, nor a period's start and end | ✅ | `test_a_document_with_a_date_is_made_from_the_plus_of_a_day_in_the_month`; Vitest (`fillEmbedded.test.ts`, `Chrome.test.tsx`) |
| The month is asked for again on logging in and on logging out (module pages read outside the router's queries: they read `useSessionKey()`; the day, the years and a type's page alike) | ✅ | `test_the_month_is_asked_for_again_after_logging_in_and_out`; Vitest (`session.test.tsx`) |
| A day and a month link to their year: its row in the list of years, marked (`aria-current`) | ✅ | `test_the_day_and_the_month_lead_to_their_year` |
| One calendar button in the console (the calendar read in, to the other) | ✅ | the month test and `test_dev_mode.py::test_the_calendar` |
| The form of a Feast: a Recurrence is said as a person would (Repeats: every year / month / week; On: a day of a month, a weekday of a month, a day from Easter, or the weekdays; How often; From / Until), none of the rule's raw fields, reads "every year on 12 March, 1450 – 1530", saved, and found on its day | ✅ | `test_a_feast_by_rule_is_made_in_the_form_as_a_person_says_it`; the ways, what each clears, the leap-day shift, the weekdays: Vitest (`DateEditor.test.tsx`, `format.test.ts`) |
| Under the month grid, what is dated roughly and what is attached to the month are reference chips | ✅ | in the month test; Vitest (`MonthPage.test.tsx`) |
| The pages in the dev build (years, month, day, next day, Gregorian, Years) with no Solid error | ✅ | `test_dev_mode.py::test_the_calendar` |
| Day and month: "Long periods that include this day" / "over the whole month" with the count; nothing is read until **Show them**, which lists a page (field, chip, range) and then "and N more"; no section when there are none | ✅ | `test_long_periods_over_a_day_or_a_month_are_counted_and_shown_when_asked_for` (the fixture's reign, 1490 to 1510); the dev build: `test_dev_mode.py::test_the_calendar`; paging ("and N more"): Vitest (`DayView.test.tsx`) |
| The module's own tests and type-check, in the built project | ✅ | `test_the_calendar_module_tests_pass_in_the_built_project` |
| A truncated month or day (more than `MONTH_LIMIT` dates) | ⬜ | |

## `pangloss_dates`: dateable documents and ranges

The e2e project's `Appointment` (`appointed: Person`) is `Dateable`; its `Statement` is not. The `appointed` fixture gives Ada a
bishop's appointment in 1510, a notary's not before 1490 (`notAfter` not known), an abbot's at a date not known, and a statement.

| Area | State | Where / notes |
| --- | --- | --- |
| Entity page, what refers to it: a "Sort by date" toggle in the console (only when something that refers to it is dateable; kept in `localStorage`); sorted, the item's values and what cannot have a date (no heading), then a "Timeline" section under a bar: under each year, the date in words (from `dateText`) and the field on the left, the chip on the right, "Date unknown" last; a sticky vertical timeline with a bar per year that scrolls to a year (keys, drag on a track that moves as the page scrolls) and follows the page; from 200 lines on only those on show are rendered (`VirtualRows`), the timeline scrolling to a year's line whether or not it is rendered | ✅ | `test_dateable.py::test_what_refers_to_a_person_is_shown_by_date`, `::test_the_timeline_is_dragged_to_a_year_and_follows_the_page`; dev build: `test_dev_mode.py::test_what_refers_to_a_person_by_date`; order, words, keys, the button, three hundred lines rendered as a window's worth: Vitest in `pangloss_dates/interface` (`ByDate.test.tsx`, `dating.test.ts`; the view `incomingViews.ByDate` and the button `consoleActions.SortByDate` of that module); the hook: `ItemContents.test.tsx` |
| Entity page: the slider of years (From / To) narrows the dated rows ("1 of 2"); a period is in the years if any of it is | ✅ | the same tests |
| A reference with fields only in the database (a dateable document's copy of its date) is still a chip; the form does not offer them | ✅ | `test_dateable.py` (both tests); Vitest (`ItemContents.test.tsx`, `ItemForm.test.tsx`) |
| Date editor: a range's ends are "Not before" and "Not after", each with a "Not known" button (pressed: an `UnknownDate`, the parts gone; again: a date); the other end's button is disabled while one is pressed; it reads "not before 1490" | ✅ | `test_dateable.py::test_an_end_of_a_range_that_is_not_known_is_a_button`; Vitest in the module (`DateEditor.test.tsx`, `format.test.ts`) |

## `pangloss_zotero` module

| Area | State | Where / notes |
| --- | --- | --- |
| The page of an item: title, creators by role, the URL as a link opening a new tab, language, a readable sync time, no raw Zotero fields; what refers to it stays | ✅ | `test_an_items_page_shows_its_zotero_fields_cleaned_up` |
| The list of Zotero items: only what is used at first, *Show all* / *Show used* beside the search (`?all=1`), a bubble with how many things refer to each; not on a class only made by hand | ✅ | `test_the_list_of_items_is_of_what_is_used_until_asked_for_all`, `test_a_class_only_made_by_hand_lists_everything` |
| The bar has one link for Zotero (`ZoteroBacked`, shown as *Zotero Items*); `ZoteroObject` and `ZoteroLibrary` are off it, their pages still there | ✅ | `test_the_bar_has_one_link_for_zotero_called_zotero_items` |
| The *Zotero item* row on the form of a new `Book` (no inputs for the Zotero fields): the picker of the library, the label filled in, the item as a chip, Save turns the item into the Book (same id; what cited it now cites a Book) | ✅ | `test_zotero.py::test_a_new_book_is_based_on_an_item_and_unlinked_again`; dev build in `test_dev_mode.py::test_a_book_from_zotero_and_unlinked` |
| The same row in the dialog that makes a Book from a relation's field | ✅ | `test_a_book_made_in_a_relations_dialog_is_based_on_an_item` |
| `item_type_override` not on the form of a class that names no Zotero types | ✅ | `test_a_new_book_is_based_on_an_item_and_unlinked_again`; pytest `test_zotero_mapping.py` |
| A long label set by the pick grows the label box (several lines), and the chip of the item is cut short with its ✕ in view | ✅ | `test_a_long_label_from_the_item_is_shown_whole` |
| *Unlink from Zotero*: asks first; the Book keeps its fields, the item is an entry of its own again | ✅ | the same |
| *Link to Zotero* on a Book made by hand, to an item nothing refers to (the Book is kept, the item's node goes) | ✅ | `test_a_book_made_by_hand_is_linked_to_an_item` |
| *Link to Zotero*: the item's node kept (another id, the page follows); refused when both are referred to; by an address | 🚧 | live tests in `pangloss-zotero` (`test_zotero_live_adopt.py`); not in a browser |
| The *Zotero item* row only on the classes an item can be made into | ✅ | `test_the_zotero_row_is_only_on_the_classes_an_item_can_be_made_into` |
| The hooks (`newItemActions`, `newItemFields`, page and dialog): filling the form in and sending it another way; `readOnly` fields not on forms, sent back as loaded | ✅ | Vitest `NewItemActions.test.tsx` |

## Findings of this suite (for the interface, not yet changed)

- The home page is unstyled.
- A page is not complete without JavaScript (the streamed parts need a script to be put in place).
- The language flags in the bar do nothing.

## Not for this suite

Logic that Vitest or the API tests cover: the shape of a response, validation, the hierarchy rules, the protection of
fields. Here only what needs a real browser: events, hydration, the built chunks, the proxy to the API, cookies.

The proxy to the API is the built interface's own (`pangloss interface serve --api-url`, `serve.mjs`): every test
goes through it, the streams of events too, and nothing else is in front of the interface. What it answers when the
API is not there (a 502, and "The interface cannot reach the API" on the page) is not tested here: the message is in
`ErrorMessage.test.tsx`, and the answer was checked by hand.

## Writing tests: what was learned

- Wait for `window._$HY.done` before something needs a handler (`helpers.hydrated`).
- An entity chosen from a search moves the cursor into what was added, on the next frame (`revealAdded`): wait for that (`to_be_focused`) before focusing something else, or it takes the focus back. Type into an entity search with `press_sequentially`; a `fill` right after another choice can be lost.
- The other tests use the built interface, which does not check what the development build does: a page that
  writes state while it renders works there and stops the app in `pangloss dev`. Add new pages to `test_dev_mode.py`.
- The development server (`dev_url`) is `localhost`, not `127.0.0.1`: a login is a cookie of the host, so log in there.
- `drag_to` does not start a drag in Chromium: use `page.mouse` in steps (`helpers.drag`).
- Open the navigation bar by hovering (`helpers.expand_nav`); it closes when the mouse leaves, e.g. for a dialog.
- A chip's accessible name has its type in front (`RoleType type Secretary`): match with a regex, not `exact`.
- A checkbox the page sets from the server's answer does not stay checked at once: use `click()` and then `expect`.
- The typology tree shows a move or a label before the API has it: wait for the API (`server_has` in `test_typology.py`).
