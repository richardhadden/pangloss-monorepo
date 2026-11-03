# What the end-to-end tests cover

Keep this current: when a page or feature is added to the interface (or a test is added here), change its row.
✅ tested · 🚧 partly · ⬜ not yet · — not built, so nothing to test

112 tests, about 210 s. The e2e project (`conftest.py`) has `Person` (`has_role: list[Role]`), `Role` (`has_type`), `RoleType` (a
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
| Language: the fade while it loads | ⬜ | (CSS on `html[data-translating]`; checked by hand) |
| Navigation bar: the pin is kept in `localStorage` over a reload | ✅ | `test_the_pin_is_remembered` |
| Navigation bar: sections and links to the lists of the models | ✅ | `test_the_navigation_bar_links_to_the_lists` |
| Navigation bar: the filter above the types (part of any name, any case; nothing left: a message; ✕ and Escape clear it) | ✅ | `test_the_types_in_the_navigation_bar_are_filtered`, dev build in `test_making_and_editing`; names in other languages and accents: Vitest (`NavModelList.test.tsx`) |
| Navigation bar on a touch device (no hover) | ⬜ | |
| Console bar names the type (plural on a list) and the item | ✅ | `test_the_console_names_the_type_of_the_page` |
| Console bar on an item page: created / modified, by whom and when, two light rows on the right | 🚧 | unit tests in `Console.test.tsx`; not in e2e |
| Login dialog: logging in; the session survives a reload | ✅ | `test_login.py` |
| Login dialog: a wrong password is explained, the right one then works | ✅ | |
| Login dialog: Escape and the close button give up | ✅ | |
| Log out | ✅ | |
| `RequireLogin`: `/Person/new` opens the dialog; giving up goes home; logging in shows the page | ✅ | |
| "New Person" button only for someone logged in | ✅ | |
| No "New" button, and `/TYPE/new` says why, for a document that cannot be made on its own (`create_directly=False`; `ReportSection` in the e2e project) | ✅ | `test_a_document_that_cannot_be_made_on_its_own_has_no_new_button_or_page`; Vitest (`Console.test.tsx`) |
| List page: items, count, links | ✅ | `test_lists_and_items.py` |
| List page: search (`?q=`), kept in the address, no result is a red 0, an address with a search shows it; typing is not held up or undone by the searches it makes | ✅ | `test_typing_is_not_held_up_or_undone_by_the_searches_it_makes`; Vitest (`ConsoleSearch.test.tsx`) |
| List page: deep search toggle, typing makes none, Enter / run button make it, turning it off | ✅ | finds a person through a statement |
| List page: search form (button beside Deep search, panel under the console pushing the list down, closed again); a condition narrows the list and is kept in the address (`?form=`), reopened from it; not; Clear; entities picked; a nested form for what a relation points at; what refers to an entity; what a document mentions; the text box narrows it and Deep search is greyed out | ✅ | `test_search_form.py`; dev build: `test_the_search_form`; operators, between, enum pills, Enter: Vitest (`SearchPanel.test.tsx`, `searchForm.test.ts`, `ConsoleSearch.test.tsx`) |
| List page: search form: order by, two conditions on one field, groups of alternatives, saved searches (browser), the panel in from the ends of the console | ✅ | `test_search_form.py`; contains somewhere, through, inside spaces: Vitest (`SearchPanel.test.tsx`, `searchForm.test.ts`): the e2e project has no nested documents or semantic spaces |
| List page: search form on dates, numbers, decimals, enums of the demo's models | 🚧 | checked by hand with screenshots; the e2e project has no such fields |
| List page: "truncated" (`count+`, "narrow the search") | ⬜ | needs more results than `SEARCH_HIT_LIMIT`: set it low in the e2e settings |
| List page: scrolling loads more (virtualised, a page at a time); `?at=` kept as it is scrolled, and reloading or going back starts there | ✅ | `test_a_long_list_is_loaded_as_it_is_scrolled_and_starts_where_it_was_left` (130 people) |
| Item page: fields, references as chips, reverse relations, no empty rows | ✅ | |
| Item page and form: every row of fields under a faint rule; rows of reverse relations with more room, their items centred on each other in a line; head bars and chips framed by a hairline, square buttons; the spaces of a chip or a list row as muted tabs before it, not round it | 🚧 | seen in screenshots of the demo data; no test of the look |
| Item page: reified relations without a "target" key; the full trail (spaces and documents) round a chip; reverse through a reified relation shows the field in its document | 🚧 | unit tests in `ItemContents.test.tsx`; the e2e project has no reified relation or semantic space |
| Dates (`pangloss_dates` module): a date is said as a person would, not listed by field | 🚧 | unit tests in the module (`format.test.ts`, `DateCard.test.tsx`); the e2e project has no dates |
| Item page: a type in a field leads to the page of the type (module page) | ✅ | |
| Item page: "Derived" section (`_derived` of `pangloss-derived`): each class with the other end and its fields (each by its field name in the derived class), the context of a qualified fact, "and N more" reading the next page, "Why" fetching the justifications | 🚧 | unit tests in `DerivedSection.test.tsx`; the e2e project does not install `pangloss_derived` |
| Item page of a subtype (308 to its own route) | ✅ | through `/Role/<concrete type id>` in `test_typology_item.py` |
| Not-found page, with a 404 status | ✅ | `test_navigation.py` |
| An item that is not there is explained (`role="alert"`) | ✅ | |
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
| Edit button of a document inside another: to the form of its head document (`?show=<id>`), scrolled to its block | 🚧 | checked with the demo data (a Transfer in a Factoid); the e2e models have no nested documents |
| New item form: fields, an entity found by search, saved and shown | ✅ | |
| A new entity made from the form (+ beside the search, dialog) is chosen | ✅ | |
| With several entity types, + opens the dialog on the types (Back to them), then the form of the one chosen | ✅ | test_dev_mode (unit: ItemForm.test) |
| A required list with one possible type (not an entity) starts with the items `MinLen` asks for (the Alternative of an Identification); a list at `MaxLen` has no Add | 🚧 | Vitest (`ItemForm.test.tsx`); checked with the demo data |
| Entity search before anything is typed: the most used of the types (most edges out: referred to most), asked for as the field is drawn; those picked lately (local storage) first, with a clock, and only while they match what is typed; only those the API still has (a database made again leaves the browser's list behind: one that is gone is not offered, and is forgotten; so is one a save is refused for, and what holds it on the clipboard) | ✅ | `test_an_entity_field_offers_the_most_used_then_puts_those_picked_lately_first`, `test_an_entity_picked_lately_that_is_no_longer_in_the_database_is_not_offered`; the refused save: Vitest (`ItemForm.test.tsx`); types and subclasses, accents: Vitest (`ItemForm.test.tsx`) |
| A rejected form says what is wrong and keeps what was typed; Cancel leaves without saving | ✅ | |
| Form checked in the browser on Save (valibot schemas from the exported models): nothing sent; the names of the fields with problems red, with why under them; a red toast; a field changed is unmarked; a 422 shown at its fields in the same way | ✅ | `test_an_incomplete_form_is_not_sent_and_says_what_is_wrong_at_its_fields`; the schemas: Vitest (`validation.test.ts`), placing at rows (`form.test.ts`), nested, embedded, 422, other errors as a toast, the entity dialog (`ItemForm.test.tsx`); scrolling to the first problem checked by hand with the demo data |
| A toast at the bottom right after an item is saved or made (also an entity made from the form); it goes after 4 s or on a click | ✅ | `test_editing_an_item_saves_a_change`, `test_an_entity_is_made_from_the_form_and_chosen`; timing and click: Vitest (`Toasts.test.tsx`) |
| Clipboard: cut in one form, kept across pages (local storage), shown at the bottom of a form page only, pasted into another form | ✅ | `test_an_entity_cut_in_one_form_is_pasted_into_another`; ids kept or dropped, what fits where, folding: Vitest (`ItemForm.test.tsx`, `clipboard.test.ts`); the e2e project has no sub-documents to cut |
| Form: a nested block folds by clicking the grey of its head bar (no fold button; folded, a ▸ before the label) | ✅ | Vitest (`ItemForm.test.tsx`); checked with the demo data |
| Form: a document inside another narrowed (↧) or widened (↥) to a type below or above it, what it holds moved to the fields of the new type (also those that stand for others, `subclasses`); a dialog first if something would be lost; saved as the same node with its new type | 🚧 | Vitest (`retype.test.ts`, `Retype.test.tsx`); the save on both backends: conformance `test_update_changes_the_type_of_a_nested_document_that_keeps_its_id`; the e2e project has no sub-documents |
| Form: a relation to entities and reified relations or conjunctions has the search at once and a button for each of the rest under it; with `default_reified_type`, an entity found is put in that reified relation (through a conjunction too), which is not a button | 🚧 | Vitest (`ItemForm.test.tsx`, `relationLayout.test.ts`); seen in screenshots of the demo (`MemberOf.member`, `Activity.participants`); the e2e project has no reified relation |
| Form: the entity search chosen with the arrow keys and Enter (Enter does not save), Escape closes it; the add button opens, in its place, a box of the types to add, in zones (types on their own, each semantic space, conjunctions; what can be pasted under the button; hierarchy indented inside the buttons, abstract classes not selectable; one Tab stop, arrow keys; Escape, close button, click elsewhere or Tab out close it), what was added or pasted flashing, nested documents, reified relations, conjunctions, edge properties, dates | 🚧 | unit tests (`TypeMenu.test.tsx`, `ItemForm.test.tsx`, `typeChoices.test.ts`; the flash is not tested); the e2e project has no semantic space, conjunction, reified relation or date |
| Search from the home page / global search | — | not built |

## `pangloss_typology` module

| Area | State | Where / notes |
| --- | --- | --- |
| Tree page lists the types, nested and indented | ✅ | `test_typology.py` |
| Not logged in: no dragging, no select | ✅ | |
| Drag a type onto another moves it (API and reload) | ✅ | |
| Drag to the top-level strip | ✅ | |
| Rows do not move when a drag starts | ✅ | a bug this suite found and fixed |
| A type cannot be dropped below its own subtype | ✅ | |
| Server refusal is shown (`role="alert"`) | ✅ | a move another user made first |
| "Move to…" select moves a type; it offers only allowed places | ✅ | |
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
| Queue page `/review` (nav link, logged in): status tabs, type filter, rows lead to the document, back and forward keep the filters | ✅ | `test_the_queue_lists_what_is_to_be_checked_by_status`; also in the dev build |
| Queue: 25 to a page, Previous / Next | ✅ | `test_the_queue_goes_a_page_at_a_time` |
| Queue: needs a login | ✅ | `test_the_queue_needs_a_login` |
| The feed closes when the page is left; reconnects (with a cookie refresh) after the access cookie ran out | 🚧 | Vitest (`ReviewAction.test.tsx`, `poll.test.ts`); the reconnect is not tested in a browser |
| The module's own tests and type-check, in the built project | ✅ | `test_the_module_tests_pass_in_the_built_project` |

## `pangloss_calendar` module

The e2e project installs `pangloss_dates` and `pangloss_calendar` (Julian, span 1499 to 1501, `CALENDAR_FIELDS = ["Event.when"]`); `Event` has a date, `Feast` is a `DateCharacterisation`. The `dated` fixture makes three events in March 1500 (a day, a range of eight days, a range of two), a feast by rule (Benedict, 21 March) and one with no rule (Market day).

| Area | State | Where / notes |
| --- | --- | --- |
| Nav link "Calendar" (Links section) to `/calendar`: the years of the span, each with its months as links and "<n> events" at the end | ✅ | `test_calendar.py::test_the_navigation_bar_links_to_the_years_of_the_calendar`; Vitest (`YearsPage.test.tsx`) |
| Years page without a span says to set one | 🚧 | the e2e project has a span; not tested |
| Month page: 31 day links, six rows, the 1st on the right weekday; a date as a chip on its day, named by its field ("When · Coronation"); a single day known only within two days as a hollow dashed bar between them (not on them); a period of eight days as filled bars across two weeks (cut to the week, open where it goes on); a birth known only to the year listed under the grid ("between 1 January and 31 December"), not drawn; a feast by rule on its day; a chip leads to the document; Next month; the same month in the Gregorian calendar (30 days of April) | ✅ | `test_a_month_is_a_calendar_page_with_what_is_dated_on_its_days`; lanes, open ends, overlapping bars, "+N more", the hollow bar, the list: Vitest (`MonthGrid.test.tsx`, `MonthPage.test.tsx`, `lanes.test.ts`) |
| Day page: weekday and date, the same day under its Gregorian name (a link), what is dated on it: a period `stated` on each of its days, a single date `possible` with the days it could be on unless it names the day; Next day; a feast by rule says so and "repeats" | ✅ | `test_a_day_names_itself_in_both_calendars_and_lists_what_is_dated_on_it`; Vitest (`DayView.test.tsx`) |
| Logged in, day page: the search of the characterisations attaches one picked (toast, listed as attached to the day, in the month too, in the API as `manual`), the remove button of its chip takes it away, the + of the search makes one that starts on the day; no "New" buttons in the console | ✅ | `test_someone_logged_in_attaches_a_feast_to_a_day_and_takes_it_away` |
| Not logged in: no attach box or buttons | ✅ | in the day test; Vitest |
| An address that is not a day or a month is explained | ✅ | `test_an_address_that_is_not_a_day_is_explained` |
| Month: the + of a day (logged in) offers the characterisations and the documents that can be made on their own and can have a one-day date somewhere in them (Event, not Report); the form of a Feast with `when` that day; saved, it is on the day; none without a login | ✅ | `test_a_feast_is_made_from_the_plus_of_a_day_in_the_month`; Vitest (`MonthGrid.test.tsx`, `Chrome.test.tsx`) |
| Month: an Event made from a day's + in a dialog, its date that day in the page's calendar (Gregorian); saved, the month is still shown with it on the day, and it is on the same day in the Julian calendar. Every date of every item added in the dialog (a statement of a factoid) starts as the day; not an entity's, nor a period's start and end | ✅ | `test_a_document_with_a_date_is_made_from_the_plus_of_a_day_in_the_month`; Vitest (`fillEmbedded.test.ts`, `Chrome.test.tsx`) |
| A day and a month link to their year: its row in the list of years, marked (`aria-current`) | ✅ | `test_the_day_and_the_month_lead_to_their_year` |
| One calendar button in the console (the calendar read in, to the other) | ✅ | the month test and `test_dev_mode.py::test_the_calendar` |
| The form of a Feast: a Recurrence is said as a person would (Repeats: every year / month / week; On: a day of a month, a weekday of a month, a day from Easter, or the weekdays; How often; From / Until), none of the rule's raw fields, reads "every year on 12 March, 1450 – 1530", saved, and found on its day | ✅ | `test_a_feast_by_rule_is_made_in_the_form_as_a_person_says_it`; the ways, what each clears, the leap-day shift, the weekdays: Vitest (`DateEditor.test.tsx`, `format.test.ts`) |
| Under the month grid, what is dated roughly and what is attached to the month are reference chips | ✅ | in the month test; Vitest (`MonthPage.test.tsx`) |
| The pages in the dev build (years, month, day, next day, Gregorian, Years) with no Solid error | ✅ | `test_dev_mode.py::test_the_calendar` |
| The module's own tests and type-check, in the built project | ✅ | `test_the_calendar_module_tests_pass_in_the_built_project` |
| A truncated month or day (more than `MONTH_LIMIT` dates) | ⬜ | |

## Findings of this suite (for the interface, not yet changed)

- The home page is unstyled.
- A page is not complete without JavaScript (the streamed parts need a script to be put in place).
- The language flags in the bar do nothing.

## Not for this suite

Logic that Vitest or the API tests cover: the shape of a response, validation, the hierarchy rules, the protection of
fields. Here only what needs a real browser: events, hydration, the built chunks, the proxy to the API, cookies.

## Writing tests: what was learned

- Wait for `window._$HY.done` before something needs a handler (`helpers.hydrated`).
- The other tests use the built interface, which does not check what the development build does: a page that
  writes state while it renders works there and stops the app in `pangloss dev`. Add new pages to `test_dev_mode.py`.
- The development server (`dev_url`) is `localhost`, not `127.0.0.1`: a login is a cookie of the host, so log in there.
- `drag_to` does not start a drag in Chromium: use `page.mouse` in steps (`helpers.drag`).
- Open the navigation bar by hovering (`helpers.expand_nav`); it closes when the mouse leaves, e.g. for a dialog.
- A chip's accessible name has its type in front (`RoleType type Secretary`): match with a regex, not `exact`.
- A checkbox the page sets from the server's answer does not stay checked at once: use `click()` and then `expect`.
- The select of every typology row names the other types: find a row by its link, not by its text.
