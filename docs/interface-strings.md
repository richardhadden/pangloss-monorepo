# Interface: hard-coded strings

Every piece of fixed text in the interface (`packages/pangloss-interface/.../js/interface-core` and `interface-app`) that a
person reads, hears (screen reader labels) or sees as a tooltip, and so that has to be translated. Written 2026-10-28 from
a read of the source; **keep it up to date as strings are added** (and see [translations.md](translations.md), whose
`ui.jsonc` slots, `title`, `log_in` and `log_out`, are where these are meant to go: slots are `snake_case`, with a text
per language).

Nothing here is translated yet: the language row of the nav bar changes nothing. "Slot" is a suggested name.

## Visible text

| Slot | English | Where | Notes |
|------|---------|-------|-------|
| `title` | Pangloss | `Document.tsx` (`<title>`), `App.tsx` and `pages/Home.tsx` (`<Title>`) | exists in `ui.jsonc`; the name of the site, so a project may want it to be its own |
| `title_not_found` | Not found - Pangloss | `pages/NotFound.tsx` (`<Title>`) | contains the site title |
| `page_not_found` | Page not found | `pages/NotFound.tsx` | |
| `loading` | Loading… | `App.tsx`, `pages/List.tsx`, `pages/Item.tsx` | the "…" is part of the text |
| `home` | Home | `NavBar` (link in the top row) | |
| `log_in` | Log in | `NavBar` | exists in `ui.jsonc` |
| `log_out_user` | Log out {user} | `NavBar` | `log_out` exists, but this puts the user's name after it: a slot with a parameter, as the order of the words differs between languages |
| `section_entities` | Entities | `NavModelList` (heading and `aria-label`) | `ui` already has `kind_entity_plural` ("Entities"): use it |
| `section_documents` | Documents | `NavModelList` (heading and `aria-label`) | `kind_document_plural` |
| `search` | Search | `ConsoleSearch` (placeholder) | placeholder is shown in capitals; do not put capitals in the text |
| `not_available` | – | `ConsoleSearch` (the count when it could not be read) | a dash; probably the same in every language |
| `open` | Open | `EntityCard` (button) | a placeholder component |
| `no_such_model` | No model called {model} | `FieldList` (`fallback`) | a placeholder component (not on a page now) |
| `dialog_log_in` | Log in | `LoginDialog` (the heading of the dialog) | the same slot as `log_in` |
| `username` | Username | `LoginForm` (label) | |
| `password` | Password | `LoginForm` (label) | |
| `log_in` | Log in | `LoginForm` (submit button) | the same slot as the nav bar's |
| `logging_in` | Logging in… | `LoginForm` (the button while a try is made) | |
| `home_heading` | Pangloss Yo! | `pages/Home.tsx` (`<h1>`) | a placeholder from a commit of the owner's; will go |
| *(the plural)* | {Type}s, {Type}es, {Type}ies | `Console` (`pluralOf`) | **not a string to translate: code.** A stand-in that makes an English plural of the type; it goes when the plural names of models come from `models.jsonc` |
| *(words)* | list of, relation to, relations to, embedded, value, required `*` | `FieldList` (`describe`) | a placeholder component; not on a page now |

## Labels for a screen reader, and tooltips

These are not shown, but are read aloud, or appear when the pointer rests on the control.

| Slot | English | Where | Notes |
|------|---------|-------|-------|
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
| `deep_search` | Deep search | `ConsoleSearch` (toggle) | |
| `deep_search_run` | Run deep search (Enter) | `ConsoleSearch` (run button) | "Enter" names a key |
| `new_item` | New {type} | `Console` (the new button) | `{type}` is the name of the model, which has its own translation |
| `loading` | Loading | `Spinner` (`aria-label`) | the same slot as above, but without the "…" |

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
