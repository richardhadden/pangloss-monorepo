# The web interface

`pangloss-interface` is a server-rendered web application made from your models: a list page and an item page for every
Document and Entity, search, login, and a retractable navigation bar. It is a Solid 2.0 application (Solid 2.0 release
candidates only, Tailwind for all CSS) that lives in a Python package so that it installs and is configured like the other
parts.

> **What it does today.** Reading: the home page lists the models; each model has a list (search, deep search, counts),
> and each item a page with its fields, references, reverse relations and the contents of its nested documents laid out;
> models in semantic spaces are shown in coloured bands; login and logout through a dialog (the API's cookie session);
> pages that need a login ask for one. Writing: the typology tree (drag a type to move it; edit labels). **Not built yet:**
> forms to create or edit an ordinary item (the "New" page has only the console), a pager on lists (the first page only),
> an autocomplete in relation fields, translations shown on screen (the files and commands exist), the language switch.
> [`e2e/COVERAGE.md`](../../e2e/COVERAGE.md) is the checked list, row by row.

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

## Making it yours

**Colour.** `InterfaceMeta(colour="amber")` on a model sets the colour of its type wherever it is shown (a Tailwind base
colour; without it: blue for entities, green for documents):

```python
from pangloss_interface import InterfaceMeta

class Person(Entity):
    _interface_meta = InterfaceMeta(colour="amber")
```

**Navigation.** An app puts links in the bar from `<app>/interface_config.py`:

```python
from pangloss_interface.config import InterfaceConfig, NavLink, NavModel

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
modules are found and built into the application is in [Interface modules](../../docs/interface-modules-implementation.md).
`pangloss interface check` reports a module that names a component that does not exist.

**Languages.** The text of the interface (model and field names, help, enum members) is in JSONC files per app and per
project, kept in step with your models:

```bash
pangloss interface translations generate     # writes <app>/translations/models.jsonc; keeps manual edits through changes
pangloss interface translations check --lang de
pangloss interface translations gather       # one JSON file for the frontend
```

No page reads the gathered file yet, so nothing is translated on screen. [Translations](../../docs/translations.md).

## Deploying

`pangloss interface build`, then `pangloss interface serve` behind the same host as the API (the production proxy for
`/api` is a decision still open; see [the interface](../../docs/interface.md)). The login is the API's cookie session, so the
interface and the API must share a site.

## Tests

`e2e/` holds Playwright tests that drive the built interface against a real API and database (46 tests, about a minute).
Keep [`e2e/COVERAGE.md`](../../e2e/COVERAGE.md) current when a page or feature is added.
