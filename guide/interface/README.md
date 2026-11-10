# The web interface

`pangloss-interface` is a server-rendered web application made from your models: a list page and an item page for every
Document and Entity, search, login, and a retractable navigation bar. It is a Solid 2.0 application (Solid 2.0 release
candidates only, Tailwind for all CSS) that lives in a Python package so that it installs and is configured like the other
parts.

> **What it does today.** Reading: a homepage that searches everything; a list for each model (search, deep search, a
> search form made from the model's fields); a page for each item with its fields, what refers to it, and its nested
> documents laid out, those in semantic spaces in coloured bands. Writing, once logged in: forms to make, edit and delete
> any item (below). The optional packages add their own pages and panels: history, review, the calendar, typologies,
> users, `/admin`. The fixed text is translated, and the language is chosen in the navigation bar.
> [`e2e/COVERAGE.md`](../../e2e/COVERAGE.md) is the checked list, row by row, and says what is not built.

## Using it

You need **Node 22.12 or later** (or Bun, with `--runtime bun`). Add `"pangloss_interface"` to `INSTALLED_APPS`, then:

```bash
pangloss interface install      # copies the JavaScript to .pangloss/interface and installs its packages
pangloss dev                    # the API, port 8000
pangloss interface dev          # the interface with hot reload, port 3000; /api goes to the API
```

| Command | |
|---|---|
| `info` | Where it is, whether it is installed and built, and the runtime found |
| `install`, `build` | Prepare the working directory; `build` makes `dist/{client,server}` |
| `serve [--host] [--port]` | Run what `build` made |
| `check` | Type-check both packages with *your* models, and the rules of the layers |
| `export-models [--format ts\|json] [-o FILE]` | The models as plain data: what the interface is made from |
| `dev --link` | Work on the interface itself, from the source in a checkout of the repository |

Every command that needs the interface first copies the package's JavaScript to **`.pangloss/interface/`** in your
project, exports your models there (`generated/models.ts`), and installs. Nothing in `.pangloss/interface` should be edited;
it is overwritten. Restart `pangloss interface dev` after changing the models.

## Making and editing items

Log in (the button in the navigation bar; users are made with `pangloss users create`). Then:

- **New.** The console of a list page has a *New* button (Cmd/Ctrl+Enter); the address is `/Person/new`. The form is
  made from the model: a box for each literal, a search for each relation to an entity (the most used and those you
  picked lately are offered before you type; an entity that is not there yet can be made from inside the form), and
  nested documents added in place, with a menu of the types a field can hold.
- **Save** (Cmd/Ctrl+S) is on once something has changed. The form is checked in the browser first: nothing is sent
  if a field is wrong, and the field says why. What the server refuses is shown at its field in the same way.
- **Edit and delete.** An item's page has both. Delete asks the server first whether the item can be deleted (an
  entity that something refers to cannot), and says why not.
- **Leaving a form with changes** asks whether to stay, leave, or **stash** it: a stashed new item is kept in the
  browser and listed on the type's list page, to be taken up again.
- **Cut, copy and paste** of nested documents and references, between fields and between forms.
- **Narrowing and widening** (↧ ↥): a nested document can be made a more specific type, or a more general one, where
  nothing it holds would be lost.
- A document whose class says `Document.Meta(create_directly=False)` has no *New* button: it is only made inside
  another.

Two people editing one item: the second to save is told the item has changed, and can load the new version; nothing
is written over.

## Making it yours

**Colour.** `InterfaceMeta(colour="amber")` on a model sets the colour of its type wherever it is shown (a Tailwind base
colour; without it: blue for entities, green for documents):

```python
from pangloss_interface import InterfaceMeta

class Person(Entity):
    _interface_meta = InterfaceMeta(colour="amber")
```

**No head on a reified relation.** `InterfaceMeta(headless=True)` on a `ReifiedRelation` shows it without its head bar,
as only what it holds and its own fields, on the item page and in the form, wherever it is the only type a field can hold,
the field holds one of it (not a list) and it is required. There its type says nothing and it is never added or removed.
Anywhere else it has its head as usual:

```python
class AtPage[T](ReifiedRelation[T]):
    _interface_meta = InterfaceMeta(headless=True)

    page: str


class Factoid(Document):
    source: AtPage[Source]  # the source, then its page: no "At page" bar
```

**Navigation.** An app puts links in the bar from `<app>/interface_config.py`:

```python
from pangloss_interface import InterfaceConfig, NavLink, NavModel

config = InterfaceConfig(
    sections=["People"],
    nav=[NavModel("Person", section="People"), NavLink("About", "/about")],
)
```

**Your own components: interface modules.** An installed app can ship a small Solid library in `<app>/interface/` and
take over a page or a card for a model from `InterfaceMeta`:

```bash
pangloss interface new-module my_app
```

```python
_interface_meta = InterfaceMeta(item_page="my_app:LetterPage", view_card="my_app:LetterCard")
```

`list_page`, `item_page`, `view_card` and `edit_card` are the four slots (edit cards are exported and checked but nothing
renders them yet). The typology and calendar packages are built this way; the typology's tree page is the best example. How
modules are found and built into the application is in [Interface modules](../../implementation_docs/interface-modules-implementation.md).
`pangloss interface check` reports a module that names a component that does not exist.

**Languages.** The text of the interface (model and field names, help, enum members) is in JSONC files per app and per
project, kept in step with your models:

```bash
pangloss interface translations generate     # writes <app>/translations/models.jsonc; keeps manual edits through changes
pangloss interface translations check --lang de
pangloss interface translations gather       # one JSON file for the frontend
```

The languages are those of `INTERFACE_LANGUAGES` in the settings; a reader chooses one in the navigation bar, and the
choice is kept in the browser. Your own fixed text (the label of a page or a link) goes in `translations/ui.jsonc`.
[Translations](../../implementation_docs/translations.md).

## Deploying

```sh
pangloss interface build
pangloss run                                                  # the API, port 8000
pangloss interface serve --api-url http://127.0.0.1:8000      # the interface, port 3000
```

The interface's server passes `/api` on to the API, as the development server does, so the two commands are a whole
site: the browser only talks to the interface, and the login is the API's cookie session on that one address. Put a
reverse proxy in front for TLS. If that proxy sends `/api` to the API itself, start the interface with
`--no-api-proxy` (it still needs `--api-url`: the pages it renders ask the API too). If a page says "The interface
cannot reach the API", the API is not running or is not at `--api-url`.

## Tests

`e2e/` holds Playwright tests that drive the built interface, and the development build, against a real API and
database (about 230 tests; several minutes).
Keep [`e2e/COVERAGE.md`](../../e2e/COVERAGE.md) current when a page or feature is added.

## Your own homepage and pages

The homepage shows the name of the project and a box that searches everything. To change it, or to add pages:

```sh
pangloss interface new-homepage      # pages/index.tsx, a copy of the default to edit
pangloss interface new-page About    # pages/About.tsx, at /about
```

The files are in `pages/` in your project, and are Solid components styled with Tailwind. Each page is linked in the
console of the homepage and of the other pages. A file called `10-About.tsx` is put in order by its number; `_About.tsx`
has an address but no link. The text of the link is the translation `page_about` in your `translations/ui.jsonc`, or
else the name of the file. `pangloss interface check` reports a page whose address is already used.

In the box, a word that names a type offers that type in a list under it: Tab takes the first, the arrows choose another. A type narrows the search, and by itself lists the most connected of that type. With no types offered, the arrows go through the results, and Enter opens the one chosen, or the first.

A class is left out of the search with `Entity.Meta(global_search=False)` (or `Document.Meta`).
