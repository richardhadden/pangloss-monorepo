# Interface: hard-coded strings

Every piece of fixed text in the interface (`packages/pangloss-interface/.../js/interface-core` and `interface-app`) that a
person reads, hears (screen reader labels) or sees as a tooltip, and so that has to be translated. Written 2026-10-28 from
a read of the source; **keep it up to date as strings are added** (and see [translations.md](translations.md), whose
`ui.jsonc` slots, `title`, `log_in` and `log_out`, are where these are meant to go: slots are `snake_case`, with a text
per language).

Connected to `ui.jsonc` (with `useTranslations().t`, see [translations.md](translations.md)): the nav bar, `NavModelList` (section titles, model names), `Console` and `ConsoleSearch` (`search`, `found`, `found_more`, `deep_search`, `deep_search_run`, `search_form`, `new_item`), the search form (`search_*`) and `LoginForm`. Still English in the code: `LoginDialog`, the pages (`Loading…`, not found), `Modal`, `Spinner`, `ItemContents` (yes/no, and the field names, which should use `fieldName`), `EntityCard`, `FieldList`, `ResultButton`. "Slot" is a suggested name.

**2026-11-02:** every `t()` slot of `interface-core`, `interface-app`, `pangloss_dates` and `pangloss_typology` is in
`ui.jsonc` in English, German and French (162 slots). The typology module, the "Loading…" fallbacks, `Spinner`,
`ConsoleBar` and `EntityCard` now go through `t()` too (`typology_*`, `loading`, `console`, `open`). Dates are said in the
language of the page (`formatDate(date, words)`: month and weekday names from `Intl`, the `date_*` slots for the order
and the words), and so are the times in the console. What is still not translatable: the labels of typology types in the
tree and in reference chips (the typology API sends the default label only), and the API's own messages (English).

**2026-11-05:** the slots of the interface modules moved to their apps' own `translations/ui.jsonc` (see
[translations.md](translations.md)); where the tables below say "in `ui.jsonc`" for a `date_*`, `calendar_*`, `review_*`,
`typology_*` or `derived_*` slot, it is that app's file.

## Visible text

| Slot | English | Where | Notes |
|------|---------|-------|-------|
| `title` | Pangloss | `Document.tsx` (`<title>`), `App.tsx` and `pages/Home.tsx` (`<Title>`) | exists in `ui.jsonc`; the name of the site, so a project may want it to be its own |
| `title_not_found` | Not found | `NotFound` (window title) | |
| `title_new` | New | `New` (window title) | |
| `title_edit` | Edit | `Edit` (window title) | |
| `page_not_found` | Page not found | `pages/NotFound.tsx` | |
| `pager_pages` / `_previous` / `_next` / `_page` | Pages / Previous / Next / Page {page} of {pages} | `Pager` (core: under the review queue and a user's page) | since 2026-11-10 one set in core; they were `review_queue_*` and `users_*`, the same words twice |
| `loading` | Loading… | `App.tsx`, `pages/List.tsx`, `pages/Item.tsx` | the "…" is part of the text |
| `home` | Home | `NavBar` (link in the top row) | |
| `log_in` | Log in | `NavBar` | exists in `ui.jsonc` |
| `log_out_user` | Log out {user} | `NavBar` | `log_out` exists, but this puts the user's name after it: a slot with a parameter, as the order of the words differs between languages |
| `section_entities` | Entities | `NavModelList` (heading and `aria-label`) | `ui` already has `kind_entity_plural` ("Entities"): use it |
| `section_documents` | Documents | `NavModelList` (heading and `aria-label`) | `kind_document_plural` |
| `section_links` | Links | `schema/nav.ts` (the heading of links that an `InterfaceConfig` gives no section) | |
| `nav_<app>_<label>` | (the labels of `NavModel` / `NavLink`) | `InterfaceConfig` of an app | the label given is the default-language text of the slot (exported as `labelSlot`); shown as written until the interface reads translations |
| `search` | Search | `ConsoleSearch` (placeholder) | placeholder is shown in capitals; do not put capitals in the text |
| `not_available` | – | `ConsoleSearch` (the count when it could not be read) | a dash; probably the same in every language |
| `open` | Open | `EntityCard` (button) | a placeholder component |
| `no_such_model` | No model called {model} | `FieldList` (`fallback`) | a placeholder component (not on a page now) |
| `dialog_log_in` | Log in | `LoginDialog` (the heading of the dialog) | the same slot as `log_in` |
| `username` | Username | `LoginForm` (label) | |
| `password` | Password | `LoginForm` (label) | |
| `log_in` | Log in | `LoginForm` (submit button) | the same slot as the nav bar's |
| `logging_in` | Logging in… | `LoginForm` (the button while a try is made) | |
| `yes` | Yes | `ItemContents` (a true value) | |
| `no` | No | `ItemContents` (a false value) | |
| `derived_heading` | Derived | `DerivedSection` (the heading of what the rules derive about an item, `pangloss-derived`) | in `ui.jsonc` (en, de, fr) |
| `derived_why` | Why ({count}) | `DerivedSection` (the button that shows the justifications of a fact; `count` is how many) | in `ui.jsonc` |
| `derived_more` | and {count} more | `DerivedSection` (a button under the facts shown of a derived class: reads the next page) | in `ui.jsonc` |
| `home_heading` | Pangloss Yo! | `pages/Home.tsx` (`<h1>`) | a placeholder from a commit of the owner's; will go |
| *(the plural)* | {Type}s, {Type}es, {Type}ies | `Console` (`pluralOf`) | **not a string to translate: code.** A stand-in that makes an English plural of the type; it goes when the plural names of models come from `models.jsonc` |
| *(field names)* | activity type, carried out by... | `ItemContents` (the keys) | **not strings of the interface**: the name of the field in Python with `_` as a space. They should come from the models' translations (`models.jsonc`); incoming relations likewise (`participants reverse`) |
| *(words)* | list of, relation to, relations to, embedded, value, required `*` | `FieldList` (`describe`) | a placeholder component; not on a page now |
| `stash_this` | Stash this | `ItemForm` (console button beside Save, `aria-label` and tooltip) | |
| `stash` | Stash | `StashDialog` (button) | |
| `stash_and_leave` | Stash and leave | `StashDialog` (button) | |
| `stash_title` | Stash this {type} | `StashDialog` (heading) | |
| `stash_explain` | A stashed {type} is kept in this browser, to be finished later: it is offered where a new one is made. | `StashDialog` | |
| `stash_label` | A label, to know it by | `StashDialog` (the label field, when the item has none) | |
| `leave_title` | Leave without saving? | `StashDialog` (heading, when leaving) | |
| `leave_lost` | The changes in this form are not saved: they will be lost. | `StashDialog` | |
| `leave_or_stash` | The changes in this form are not saved. Stash it to finish it later, or leave it and lose them. | `StashDialog` | |
| `leave_stay` | Stay | `StashDialog` (button) | |
| `leave_discard` | Leave without saving | `StashDialog` (button) | |
| `toast_stashed` | {type} “{label}” stashed | `ItemForm` (toast) | |
| `stash_gone` | These were referred to when this was stashed, and are no longer there: they have been taken out. | `ItemForm` (above a form opened from the stash) | |
| `bottom_bar` | Clipboard and stash | `ClipboardBar` (`aria-label` of the bar) | |
| `stashed` | Stashed | `ClipboardBar` (`aria-label` of the section, tooltip of the icon) | |
| `stashed_count` | Stashed ({count}) | `ClipboardBar` (section heading) | |
| `stash_open` | Go on with {label} | `ClipboardBar` (`aria-label` and tooltip of a stashed item's link) | |
| `stash_open_here` | Open in this form | `ClipboardBar` (tooltip of the item the form was opened from) | |
| `stash_remove` | Throw away {label} | `ClipboardBar` (`aria-label` and tooltip of ✕) | |

## Labels for a screen reader, and tooltips

These are not shown, but are read aloud, or appear when the pointer rests on the control.

| Slot | English | Where | Notes |
|------|---------|-------|-------|
| `derived_qualified` | Only from statements with a context | `DerivedSection` (the tooltip of the context labels of a fact that is `qualifiedOnly`) | in `ui.jsonc` |
| `nav_main` | Main | `NavBar` (`aria-label`) | the name of the navigation landmark |
| `nav_expand` | Expand the navigation bar | `NavBar` (the toggle) | |
| `nav_retract` | Retract the navigation bar | `NavBar` (the toggle) | |
| `status_logged_in_as` | Logged in as {user} | `NavBar` | |
| `status_not_logged_in` | Not logged in | `NavBar` | |
| `language_current` | Language: {language} | `NavBar` | the name of the language is its own (below) |
| `console` | Console | `ConsoleBar` (`aria-label`) | |
| `search` | Search | `ConsoleSearch` (`aria-label` of the input) | the same slot as the placeholder |
| `found` | Found | `ConsoleSearch` (tooltip of the count) | would better be "{count} found", with the plural forms of the language |
| `close` | Close | `Modal` (the close button) | `closeLabel` can be given |
| `found_more` | Found, and more: narrow the search | `ConsoleSearch` (tooltip of the count when the search was cut short: the count has a "+" after it) | the "+" is a sign, not a word |
| `deep_search` | Deep search | `ConsoleSearch` (toggle) | |
| `deep_search_run` | Run deep search (Enter) | `ConsoleSearch` (run button) | "Enter" names a key |
| `search_form` | Search by fields | `ConsoleSearch` (the button of the search form) | |
| `search_form_in_use` | Search by fields (in use) | `ConsoleSearch` (the same, while the form has a condition) | |
| `search_form_of` | Search {type} by fields | `SearchPanel` (`aria-label` of the panel) | |
| `search_clear`, `search_close` | Clear, Close | `SearchPanel` (buttons at its foot) | |
| `search_not`, `search_not_named`, `search_not_title` | not; Not: {name}; Find what does not match this | `SearchPanel` (the toggle on each condition: text, `aria-label`, tooltip) | |
| `search_operator` | Condition on {name} | `SearchPanel` (`aria-label` of the menu of operators) | |
| `search_op_*` | contains, starts with, is, between, is one of, is any of, is all of, is one matching, has a value, has no value, has any, has none | `SearchPanel` (the operators) | `=`, `>`, `≥`, `<`, `≤` are symbols, not translated |
| `search_from`, `search_to`, `search_and` | from, to, and | `SearchPanel` (between: the boxes' `aria-label`s, and the word between them) | |
| `search_remove_condition` | Remove the condition on {name} | `SearchPanel` (✕ of a condition) | |
| `search_choose_type`, `search_change_type`, `search_change_type_of` | Choose a type; Type; Change the type of {name} | `SearchPanel` (the type of a nested form) | |
| `search_mentions`, `search_find_any_entity` | Mentions; Find an entity… | `SearchPanel` (the row of a document's mentions, and its search) | |
| `search_referred_to_by`, `search_add_referring`, `search_source`, `search_any_field` | Referred to by; Add what refers to it; {type} · {field}; any field | `SearchPanel` (what refers to an entity) | |
| `search_and_condition` | And another condition on {name} | `SearchPanel` ("+ and" under a row: `aria-label`, tooltip) | |
| `search_through`, `search_through_named`, `search_in_spaces` | through; Through, for {name}; Inside | `SearchPanel` (wrappers a relation passes through; the spaces a document is in) | |
| `search_add_filter`, `search_fields`, `search_more` | Add a filter; Fields; More | `SearchPanel` (the menu at the foot of each node that adds a row) | |
| `search_none_found` | There are none | `SearchPanel` (a relation of whose types there are none, in what the rest of the form finds) | |
| `search_somewhere`, `search_add_somewhere` | Contains; Add a document it contains | `SearchPanel` (documents inside a document) | |
| `search_any_of`, `search_alternatives_n`, `search_alternative`, `search_or`, `search_add_alternatives` | Any of; Alternatives {n}; alternative {n}; or; Add alternatives | `SearchPanel` (groups of alternatives) | |
| `search_order_by`, `search_then_by`, `search_order_n`, `search_direction`, `search_ascending`, `search_descending` | Order by; then by; Order by, {n}; Direction of {name}; ascending; descending | `SearchPanel` (the order) | |
| `search_saved`, `search_saved_placeholder`, `search_save`, `search_save_name`, `search_delete_saved` | Saved searches; Saved searches…; Save; Name of this search; Delete the saved search {name} | `SearchPanel` (searches saved in the browser) | |
| `new_item` | New {type} | `Console` (the new button) | `{type}` is the name of the model, which has its own translation |
| `go_to_head` | Go to the {type} | `ResultButton` (the button to the document an item is in: `aria-label` and tooltip) | `{type}` is the name of the model, which has its own translation |
| `loading` | Loading | `Spinner` (`aria-label`), `pages/List.tsx` (a row whose page has not come yet: `aria-label`) | the same slot as above, but without the "…" |
| `edit` | Edit | `Console` (the edit button on an item) | |
| `new` | New | `ItemForm` (the label in the console of a new item) | |
| `save` | Save | `ItemForm` (console button) | |
| `cancel` | Cancel | `ItemForm` (console button) | |
| `edit_form` | {type} form | `ItemForm` (`aria-label` of the form) | |
| `stale_version` | Someone has saved this item since you opened it. Nothing was overwritten: load the new version, and make your changes again. | `ItemForm` (after a 412) | |
| `reload` | Load the new version | `ItemForm` (button in the message above) | |
| `label` | Label | `ModelFields` (`ItemFields`: the label of every Document and Entity) | |
| `uris` | URIs | `ItemFields`, `ItemContents` (the URIs of an entity) | |
| `opens_in_new_tab` | (opens in a new tab) | `ExternalLink` (for a screen reader, after the address) | |
| `plain` | Plain | `TypeMenu` (the section of the types that are in no semantic space) | the sections of the spaces are headed with the name of the space model |
| `add` | Add | `LiteralEditor` (add to a list of literals) | |
| `add_to` | Add to {name} | `LiteralEditor` (`aria-label` of that button) | |
| `add_named` | Add {name} | `ModelFields` (the button of the menu of a relation or embedded field) | `{name}` is the name of the field |
| `remove_item` | Remove {name} | `LiteralEditor`, `ModelFields` (`aria-label` of the ✕ buttons) | |
| `fold` | Fold or unfold {name} | `ModelFields` (`Block`: `aria-label` of the fold button) | |
| `collapse_show_whole` | Show the whole {name} | `ItemContents` (`aria-label` and tooltip of the marker of a collapsed relation) | |
| `fold_all` | Fold all | `ItemForm` (button in the console when the form has nested blocks) | |
| `unfold_all` | Unfold all | `ItemForm` (the same button, when all are folded) | |
| `collapse_fold` | Fold {name} | `ItemContents` (`aria-label` and tooltip of the fold button on the head of a relation that can collapse) | |
| `narrow_type` | Narrow {name} to a type below it | `RetypeButtons` (`aria-label` and tooltip of ↧) | |
| `widen_type` | Widen {name} to a type above it | `RetypeButtons` (`aria-label` and tooltip of ↥) | |
| `retype_title` | Change to {type}? | `RetypeButtons` (the dialog's heading) | |
| `retype_loses` | {type} has no room for what is in these fields of {from}, which will be lost: | `RetypeButtons` (the dialog, above the list of fields) | |
| `retype_confirm` | Change the type | `RetypeButtons` (the dialog's button) | |
| `invalid_json` | This is not valid JSON, so it is not changed | `LiteralEditor` (`JsonEditor`, for a field the form has no editor for) | |
| `find_entity` | Find {type}… | `EntityPicker` (placeholder and `aria-label`) | `{type}` is the names of the models it looks in |
| `new_entity` | Make a new one | `ModelFields` (`PickOrCreate`: the + button beside the search; `aria-label` and tooltip) | the dialog is headed `new_item` |
| `search_failed` | The search failed | `EntityPicker` | |
| `nothing_found` | Nothing found | `EntityPicker` | |
| `created` | Created | `Console` (the history of an item: tooltip and screen-reader text of the icon of a new page) | shown as an icon, no longer as a word |
| `modified` | Modified | `Console` (the same, for the icon of a pen) | |
| `step_up` | Increase {name} | `NumberInput` (`aria-label` of its up button) | `{name}` is the label of the box; the buttons are not Tab stops (the Up key does the same) |
| `step_down` | Decrease {name} | `NumberInput` (`aria-label` of its down button) | |
| `date_year` | Year | `pangloss_dates` `DateEditor` (placeholder and `aria-label` of the year of an exact date) | a module's string, in the same `ui` slots |
| `date_month` | Month | `DateEditor` (`aria-label` of the month) | the names of the months are English in the module (`MONTHS` in `format.ts`), as in `DateCard` |
| `date_no_month` | (no month) | `DateEditor` (the empty choice of the month) | |
| `date_day` | Day | `DateEditor` (placeholder and `aria-label` of the day) | |
| `date_earliest` | Earliest | `DateEditor` (a range: the label of its first end) | |
| `date_latest` | Latest | `DateEditor` (a range: the label of its last end) | |
| `date_edtf_help` | Extended Date/Time Format: 1500-03~ is about March 1500, 15XX some year of the 1500s, 1500/1510 from 1500 to 1510 | `DateEditor` (under the EDTF box) | the examples are EDTF, not words |
| `date_reads` | Reads | `DateEditor` (before the date as it reads) | |
| `nav_filter` | Filter types | `NavBar` (`NavFilter`: placeholder and `aria-label` of the box above the types) | |
| `type_info_fields` | Fields | `TypeInfoPopup`: heading of the fields | |
| `type_info_text` | Text | `TypeInfoPopup`: a text field accepts | |
| `type_info_whole_number` | Whole number | `TypeInfoPopup`: an `int` field accepts | |
| `type_info_number` | Number | `TypeInfoPopup`: a `float` or `Decimal` field accepts | |
| `type_info_yes_or_no` | Yes or no | `TypeInfoPopup`: a `bool` field accepts | |
| `type_info_date` | Date | `TypeInfoPopup`: a date field accepts | |
| `type_info_date_time` | Date and time | `TypeInfoPopup`: a datetime field accepts | |
| `type_info_time` | Time | `TypeInfoPopup`: a time field accepts | |
| `type_info_duration` | Duration | `TypeInfoPopup`: a duration field accepts | |
| `type_info_structured` | Several values | `TypeInfoPopup`: a `TypedDict` field accepts | |
| `key_ctrl` | Ctrl | `NavBar` (the Control key in the shortcut shown at the foot of the retracted bar, off a Mac) | |
| `nav_filter_clear` | Clear the filter | `NavBar` (`NavFilter`: `aria-label` and tooltip of its ✕ button) | |
| `nav_filter_none` | No types match | `NavModelList` (shown when the filter leaves nothing) | |
| `toasts` | Notifications | `Toasts` (`aria-label` of the region the toasts are in) | |
| `toast_dismiss` | Dismiss: {message} | `Toasts` (`aria-label` of a toast: clicking it closes it) | `{message}` is the toast's text |
| `toast_created` | {type} “{label}” created | `ItemForm`, `ModelFields` (`EntityCreateDialog`): the toast after a new item is saved | `{type}` is the name of the model; the quotation marks belong to the language |
| `toast_saved` | {type} “{label}” saved | `ItemForm` (the toast after a change is saved) | as above |
| *(the validation slots below, `not_saved*` and `invalid_*`, are in `ui.jsonc`, English and German, since 2026-11-02; valibot is given them per language)* | | | |
| `not_saved_problem` | Not saved: a field has a problem, marked in red | `useSaveChecks` (`form/Problems.tsx`): the red toast when one field has a problem | the form is not sent |
| `not_saved_problems` | Not saved: {count} problems, marked in red | `useSaveChecks`: the same, for more | `{count}` is a number |
| `not_saved` | Not saved | `useSaveChecks`: when no problem has a field to be shown at (they follow it, after ` · `) |  |
| `invalid_required` | Required | `useProblemText` (`form/Problems.tsx`): under the name of a field, red |  |
| `invalid_too_short` | At least {n} characters | `useProblemText` | `MinLen` of a text |
| `invalid_too_long` | At most {n} characters | `useProblemText` | `MaxLen` of a text |
| `invalid_too_few` | At least {n} needed | `useProblemText` | `MinLen` of a list or relation |
| `invalid_too_many` | At most {n} allowed | `useProblemText` | `MaxLen` of a list or relation |
| `invalid_too_small` | Must be {n} or more | `useProblemText` | `Ge` |
| `invalid_must_exceed` | Must be more than {n} | `useProblemText` | `Gt` |
| `invalid_too_large` | Must be {n} or less | `useProblemText` | `Le` |
| `invalid_must_be_under` | Must be less than {n} | `useProblemText` | `Lt` |
| `invalid_not_whole` | Must be a whole number | `useProblemText` |  |
| `invalid_not_multiple` | Must be a multiple of {n} | `useProblemText` | `MultipleOf` |
| `invalid_not_number` | Must be a number | `useProblemText` | a decimal |
| `invalid_not_date` | Must be a date | `useProblemText` |  |
| `invalid_not_datetime` | Must be a date and time | `useProblemText` |  |
| `invalid_not_uuid` | Must be a UUID | `useProblemText` |  |
| `invalid_not_choice` | Not one of the choices | `useProblemText` | an enum or literal |
| `invalid_type_not_allowed` | This type is not allowed here | `useProblemText` | a pasted or edited value of a type the field does not hold |
| `invalid_value` | Not a valid value | `useProblemText` | a value of the wrong type, or not matching a pattern |

**Review (2026-11-03).** The module of `pangloss_review` (`ReviewAction`, `ReviewPanel`: [review.md#the-interface-the-review-panel-and-the-queue-plan-of-2026-11-03-built](review.md#the-interface-the-review-panel-and-the-queue-plan-of-2026-11-03-built)), in `ui.jsonc` in English, German and French:

| Slot | English | Where | Notes |
|------|---------|-------|-------|
| `review_status_unchecked` / `_errors_found` / `_published` | Unchecked / Errors found / Published | `ReviewPanel` (the status buttons), the button's label | `review_status_<status>` |
| `review_button` | Review: {status} | `ReviewAction` (the console button's label and tooltip) | |
| `review_button_comments` | Review: {status}, open comments: {count} | `ReviewAction` | with open comments; worded to need no plural |
| `review_panel` | Review | `ReviewPanel` (heading, `aria-label`) | |
| `review_close` | Close the review | `ReviewPanel` (close button label and tooltip) | |
| `review_status` | Status | `ReviewPanel` (`aria-label` of the status buttons) | |
| `review_reviewed_by` | Reviewed by {user}, {when} | `ReviewPanel` | `{when}` in the language of the page |
| `review_comments` | Comments | `ReviewPanel` (heading, `aria-label` of the list) | |
| `review_show_resolved` | Show resolved ({count}) | `ReviewPanel` (checkbox) | |
| `review_no_comments` | No comments | `ReviewPanel` | |
| `review_you` | You | `ReviewPanel` (the reader's own comments) | |
| `review_sending` | Sending… | `ReviewPanel` (a comment not yet confirmed) | |
| `review_resolve` | Resolve | `ReviewPanel` (button) | |
| `review_resolved_by` | Resolved by {user} | `ReviewPanel` | |
| `review_comment_label` | Comment | `ReviewPanel` (`aria-label` of the box) | |
| `review_comment_placeholder` | Write a comment (# for a part) | `Composer` (placeholder) | |
| `review_send` | Send | `ReviewPanel` (button) | |
| `review_status_refused` | The status was not changed: {reason} | `ReviewAction` (red toast) | `{reason}` is the API's message (English) |
| `review_comment_refused` | The comment was not sent: {reason} | `ReviewAction` (red toast) | |
| `review_resolve_refused` | The comment was not resolved: {reason} | `ReviewAction` (red toast) | |
| `review_parts` | Parts of the document | `Composer` (`aria-label` of the list a `#` opens) | |
| `review_part_choose` | Refer to a part… | `Composer` (button that puts a `#` in the box) | |
| `review_part_none` | No parts match | `Composer` | |
| `review_part_gone` | (no longer there) | `ReviewPanel` (a comment about a part since removed) | |
| `review_part_show` | Show it on the page | `ReviewPanel` (tooltip of a comment's "About: …") | |
| `review_queue` | Review | `ReviewQueue` (the console's name for the page) | |
| `review_queue_title` | Documents to review | `ReviewQueue` (heading) | |
| `review_queue_count` | Documents: {count} | `ReviewQueue` | worded to need no plural |
| `review_queue_empty` | Nothing here | `ReviewQueue` | |
| `review_queue_document` / `_created_by` / `_changed` / `_reviewed_by` / `_comments` | Document / Made by / Changed / Reviewed by / Open comments | `ReviewQueue` (column headings) | |
| `review_queue_type` / `_all_types` | Type / All types | `ReviewQueue` (the filter) | |
| `review_tab_*`, `review_assigned_*`, `review_take`, `reconcile_*`, `reconciliations_*`, `unreconciled_*`, `identifications_*`, `confirm_*` | (tabs, "Tasks of", Take, the reconcile panel and dialog, the two task pages, the mention's chip and form row, the Confirm dialog) | `ReviewTabs`, `ReviewQueue`, `ReconcilePanel`, `Reconciliations`, `UnreconciledCard`, `UnreconciledEditor`, `Identifications`, `ConfirmDialog` | since 2026-11-10; the list is the module's `translations/ui.jsonc` |
| `nav_pangloss_review_review` | Review | the navigation bar (`interface_config.py` of `pangloss_review`) | |
| `date_every_on` / `date_unit_year(s)` / `_month(s)` / `_week(s)` / `date_day_month` / `date_day_of_the_month` / `date_nth_weekday(_of)` / `date_nth_first` … `_last` / `date_easter` / `date_from_easter` | {every} on {on} / year, years… / {day} {month} / the {day}. / the {nth} {weekday} of {month} / first … last / Easter / Easter {sign} {days} days | `format.ts` (a recurrence as it reads: "every year on 21 March") | |
| `date_repeats` / `date_every_year` / `_month` / `_week` / `date_on` / `date_way_*` / `date_of` / `date_of_the_month` / `date_weekday` / `date_no_weekday` / `date_weekdays` / `date_nth` / `date_leap_shift` / `date_easter_offset` / `date_days` / `date_easter_help` / `date_how_often` / `date_interval` / `date_from` / `date_until` | Repeats / Every year … / On / A day of a month … / of / of the month / Weekday / (weekday) / Weekdays / Which / A day later in a leap year … / Days from Easter / days / 0 is Easter Day … / How often / Every / From / Until | `RecurrenceEditor` (the form of a repeated event) | |
| `calendar` | Calendar | the calendar module (`Chrome`: the console's name for its pages) | |
| `calendar_years` | Years | `Chrome` (console button), `YearsPage` (heading) | |
| `calendar_year` / `calendar_months` / `calendar_events` | Year / Months / Events | `YearsPage` (column headings) | |
| `calendar_event_word` / `calendar_events_word` | event / events | `YearsPage` (after the number in a circle: one, or any other number) | a language with more plural forms needs more slots |
| `calendar_where` | Where in the calendar | `Breadcrumbs` (`aria-label` of the year and month links above a heading) | |
| `calendar_add_on` | Add to {date} | `MonthGrid` (`aria-label` and tooltip of the + of a day) | |
| `calendar_attach_placeholder` | Find one to attach to this day, or + to make one | `DayView` (the search of characterisations) | |
| `calendar_julian` / `calendar_gregorian` | Julian / Gregorian | `Chrome` (the one button that shows the calendar a page is read in, and goes to the other), the headings of the pages | |
| `calendar_month_year` | {month} {year} | `MonthPage`, `YearsPage` | the month name is from `Intl` in the language |
| `calendar_weekday_date` | {weekday} {date} | `DayView` (heading) | the date is `date_day_month_year`; German puts a comma |
| `calendar_other_name` | {date} ({calendar}) | `DayView` (the same day in the other calendar) | |
| `calendar_previous_month` / `_next_month` / `_previous_day` / `_next_day` | Previous month / Next month / Previous day / Next day | `Arrows` (`aria-label` and tooltip) | |
| `calendar_more` | +{count} more | `MonthGrid` (a day with more dates than it shows) | |
| `calendar_possible` | possible | `DayView` (a single date whose range of days holds the day without naming it) | |
| `calendar_between` | between {first} and {last} | `MonthGrid` (tooltip of a hollow bar), `MonthFoot`, `DayView` (the days a single date could be on) | |
| `calendar_roughly` | Sometime in or around this month | `MonthFoot` (single dates known only to a range beyond the month) | |
| `calendar_repeats` | repeats | `DayView` (a characterisation with a rule) | |
| `calendar_over_month` | Over the month | `MonthPage` (characterisations attached to the month, year or a span) | |
| `calendar_on_this_day` / `calendar_nothing_on_day` | On this day / Nothing is dated on this day | `DayView` | |
| `calendar_characterisations` / `calendar_no_characterisations` | Feasts and characterisations / None on this day | `DayView` | |
| `calendar_by_rule` / `_attached_day` / `_attached_month` / `_attached_year` / `_attached_span` | by rule / attached to this day / attached to the month / attached to the year / attached to {first} – {last} | `DayView` (how a characterisation comes to be on the day) | |
| `calendar_attached_done` / `_attach_refused` / `calendar_detach` / `_detached_done` / `_detach_refused` | {label} attached / Not attached: {reason} / Detach {label} / {label} detached / Not detached: {reason} | `DayPage` (toasts), `DayView` (button) | |
| `calendar_truncated` | More dates were found than are shown | `MonthPage`, `DayView`, `YearsPage` | |
| `calendar_no_span` | Set CALENDAR_FIRST_YEAR and CALENDAR_LAST_YEAR … | `YearsPage` | |
| `calendar_bad_address` | That is not a day of the calendar: … | `Chrome` (`BadAddress`) | |
| `nav_pangloss_calendar_calendar` | Calendar | the navigation bar (`interface_config.py` of `pangloss_calendar`) | |

## Not translated by the interface's own file

- **Names of languages.** `English` and `Deutsch` in `NavBar` (`LANGUAGES`) are each in its own language, and stay so (they are
  not translated into the language of the page). The list itself should come from `INTERFACE_LANGUAGES`, not be written here.
- **Flags.** The emoji (🇬🇧, 🇦🇹) stand for languages, not countries; a language can have no sensible flag (and a flag is
  not a language). To be decided with the real language selector.
- **Names of models and fields** (`Person`, `Place`, the labels of fields, and the singular and plural names the console and
  the results show): these are the *project's*, from `models.jsonc`, not `ui.jsonc`. At present the interface shows the Python class
  name as it is: `Console`, `ResultButton`, `NavModelList`, the home page and the item page.
- **The kinds** (`Entity`, `Document`): `kind_entity`, `kind_document` and their plurals are in `ui` already.
- **The API's messages.** `ErrorMessage` shows the text the API sent (`422 'nope' is neither an id nor an http(s) URL`,
  `404 There is no Place with id …`). The API is not multilingual, so these are English; a status → text mapping in `ui` could
  replace the common ones (404, 422, 401, 412, 428).
- **Developer errors** (`useComponent("X"): there is no <ComponentsProvider> above`, and the like) are for developers, and stay.

## Things that are not strings, but depend on the language

- **Plurals.** "N found", and the plural of a type name. Some languages have more than two forms; a slot needs the forms of the
  language, not `{n} found` + `s`.
- **Word order and parameters.** `Log out {user}`, `Logged in as {user}`, `New {type}`, `Language: {language}` (the parameter may
  not go last; some languages inflect the type name after "New").
- **Capitalisation.** Chrome text is shown with `uppercase` by CSS. Write the texts in ordinary case: uppercase in some languages
  changes the letters (German `ß`, Turkish `i`), and CSS handles that when the page's `lang` is set. The `<html lang>` in
  `Document.tsx` is `en` and must follow the language.
- **Dates and numbers** are not shown anywhere yet.
