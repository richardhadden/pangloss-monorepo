# What the end-to-end tests cover

Keep this current: when a page or feature is added to the interface (or a test is added here), change its row.
✅ tested · 🚧 partly · ⬜ not yet · — not built, so nothing to test

46 tests, about 65 s. The e2e project (`conftest.py`) has `Person` (`has_role: list[Role]`), `Role` (`has_type`), `RoleType` (a
typology, also a `Role`) with Clerk > Secretary and Advisor, and `Statement` (a document: `text`, `about: Person`). The `data`
fixture adds Maximilian (his secretary: a `Role` of the type Secretary), Marie of Burgundy (her advisor, and a statement
about her "held court at Ghent") and Charles the Bold (no role); `types` has only the types; `stack` has one admin user.

## Interface core (`interface-app`)

| Area | State | Where / notes |
| --- | --- | --- |
| Home: the models of the project are listed, each a link | ✅ | `test_navigation.py` (the page is a placeholder: unstyled, "Pangloss Yo!") |
| Navigation bar: opens when the mouse is over it, closes when it leaves | ✅ | `test_the_navigation_bar_opens_and_closes` |
| Navigation bar: the button toggles, so a click while hovering **closes** it | ✅ (as it is now) | `test_clicking_the_button_of_the_bar_…`: a finding, see below |
| Navigation bar: sections and links to the lists of the models | ✅ | `test_the_navigation_bar_links_to_the_lists` |
| Navigation bar on a touch device (no hover) | ⬜ | |
| Console bar names the type (plural on a list) and the item | ✅ | `test_the_console_names_the_type_of_the_page` |
| Login dialog: logging in; the session survives a reload | ✅ | `test_login.py` |
| Login dialog: a wrong password is explained, the right one then works | ✅ | |
| Login dialog: Escape and the close button give up | ✅ | |
| Log out | ✅ | |
| `RequireLogin`: `/Person/new` opens the dialog; giving up goes home; logging in shows the page | ✅ | |
| "New Person" button only for someone logged in | ✅ | |
| List page: items, count, links | ✅ | `test_lists_and_items.py` |
| List page: search (`?q=`), kept in the address, no result is a red 0, an address with a search shows it | ✅ | |
| List page: deep search toggle, typing makes none, Enter / run button make it, turning it off | ✅ | finds a person through a statement |
| List page: "truncated" (`count+`, "narrow the search") | ⬜ | needs more results than `SEARCH_HIT_LIMIT`: set it low in the e2e settings |
| List page: paging (`nextPage`) | ⬜ | the list shows the first page only (the interface has no pager yet) |
| Item page: fields, references as chips, reverse relations, no empty rows | ✅ | |
| Item page: a type in a field leads to the page of the type (module page) | ✅ | |
| Item page of a subtype (308 to its own route) | ✅ | through `/Role/<concrete type id>` in `test_typology_item.py` |
| Not-found page, with a 404 status | ✅ | `test_navigation.py` |
| An item that is not there is explained (`role="alert"`) | ✅ | |
| An unknown type in the address | 🚧 | explained either way; what it should say is not decided |
| Server rendering: the first response has the data | ✅ | raw response text; **not** complete without JavaScript (Solid streams it) |
| Language switch | — | the bar shows the languages but `App.tsx` passes no `onLanguage`: it does nothing yet |
| Interface translations shown in another language | — | not connected |
| New item form | — | not built (the page has the console only) |
| Edit item | — | not built |
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

## Findings of this suite (for the interface, not yet changed)

- The navigation bar opens on `mouseenter` and its button toggles: a mouse user who clicks the button to open it closes it again.
- The home page is unstyled.
- A page is not complete without JavaScript (the streamed parts need a script to be put in place).
- The language flags in the bar do nothing.

## Not for this suite

Logic that Vitest or the API tests cover: the shape of a response, validation, the hierarchy rules, the protection of
fields. Here only what needs a real browser: events, hydration, the built chunks, the proxy to the API, cookies.

## Writing tests: what was learned

- Wait for `window._$HY.done` before something needs a handler (`helpers.hydrated`).
- `drag_to` does not start a drag in Chromium: use `page.mouse` in steps (`helpers.drag`).
- Open the navigation bar by hovering (`helpers.expand_nav`); it closes when the mouse leaves, e.g. for a dialog.
- A chip's accessible name has its type in front (`RoleType type Secretary`): match with a regex, not `exact`.
- A checkbox the page sets from the server's answer does not stay checked at once: use `click()` and then `expect`.
- The select of every typology row names the other types: find a row by its link, not by its text.
