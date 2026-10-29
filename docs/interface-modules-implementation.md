# Interface modules: implementation spec

**Status: built (phases 0 to 4, 2026-10-29), except what "As built" at the end lists.** It is for packages and apps whose models, or whose features, need an interface that the
generic one (a list and a page for each type, made from the definitions of the models) cannot give: the calendar's month grid,
a map for places, a transcription view for a manuscript, a card for a bibliographic reference.

The idea in one paragraph: **an installed Python app may ship an *interface module***, a small Solid library in a folder of the
app (`<app>/interface/`). The module says what it provides in a *manifest* (components and routes); the links for the navigation bar are in Python, in the app's `InterfaceConfig`.
A model points at a module's component by name in its `InterfaceMeta`. `pangloss interface new-module <app>` makes the folder.
When the interface is built in the project, the modules of the installed apps are copied beside `interface-core` and
`interface-app`, and a generated file tells the application what is there. The generic pages ask, for the model they are showing,
whether a module has taken over.

It builds on [the interface](interface.md) (the layers, the component map, `.pangloss/interface`) and on the meta slots
([meta-slots.md](meta-slots.md)); it replaces the "use page / use section / use card" direction in
[calendar-implementation.md](calendar-implementation.md) (decision 4): there is no separate `InterfaceConfig`; what belongs to a
model goes in `InterfaceMeta`, and what does not (a page for the calendar, a link) goes in the module's manifest.

## 1. What is wanted

| Wanted | Where it is said |
|---|---|
| A whole page for the list of a type, instead of the generic one | `InterfaceMeta(list_page=...)` |
| A whole page for one item of a type | `InterfaceMeta(item_page=...)` |
| A card to *view* an item (where it is shown in a list, or referred to, or inside another item) | `InterfaceMeta(view_card=...)` |
| A card to *edit* an item | `InterfaceMeta(edit_card=...)` |
| Links in the navigation bar (to a type, or to anything else) | the app's `InterfaceConfig` (`nav`), §4.4 |
| A page that is not about one type (a month, a map, a dashboard) | the module's manifest (`routes`) |
| A command that makes the library for an app | `pangloss interface new-module <app>` |
| How it is all brought into the build | §5 |

Not wanted: the module replacing the frame, the login, or the generic components for everything (that is the existing
component map, `createComponentMap`, and stays the project's own choice; see §9).

## 2. Vocabulary

- **Module**: the folder `<app>/interface/` of an installed app, an npm package (`@pangloss-module/<app>`) with a manifest.
  An app is "the Python package that is in `INSTALLED_APPS`", whether a library (`pangloss_calendar`) or the project's own
  (`demo_app`).
- **Manifest**: what the module's `src/index.ts` exports as `default`, made by `defineModule({...})`.
- **Component reference** (`ComponentRef`): how Python names a component: `"pangloss_calendar:MonthPage"` (the app, a colon, the
  name under `components` in the manifest). It is a string, so that a model can name a component without importing JavaScript.
- **Slot**: the four things a model can name: `list_page`, `item_page`, `view_card`, `edit_card`.
- **`InterfaceConfig`**: what an *app* (not a model) tells the interface: where its links go in the navigation bar (§4.4).

## 3. The module (JavaScript)

### 3.1 Layout

```
pangloss_calendar/
  interface/                      <- the module; shipped in the wheel (without node_modules, dist)
    package.json                  name "@pangloss-module/pangloss_calendar"; peerDependencies on solid-js, @solidjs/web,
                                  @solidjs/router, @pangloss/interface-core
    tsconfig.json                 extends the workspace's tsconfig.base.json
    src/
      index.ts                    the manifest: defineModule({...})
      components/MonthPage.tsx    a component, one default export (or a named one) for each
      components/MonthPage.test.tsx
      strings.ts?                 see §8 (interface strings)
    README.md
```

### 3.2 The manifest

```ts
// pangloss_calendar/interface/src/index.ts
import { defineModule } from "@pangloss/interface-core/modules";

export default defineModule({
  name: "pangloss_calendar",          // must equal the Python app's name (checked)
  requires: [],                       // other modules it uses, by app name (installed, no cycles: checked)
  components: {
    // lazy: each is a chunk of its own, fetched when a page that uses it is (or when a link to it is hovered)
    MonthPage: () => import("./components/MonthPage"),
    CharacterisationCard: () => import("./components/CharacterisationCard"),
  },
  routes: [
    { path: "/calendar/:calendar/:year/:month", component: "MonthPage",
      preload: ({ params }) => void monthQuery(params.calendar, params.year, params.month) },
  ],
});
```

`defineModule` is identity with types (it is in `interface-core`, in a new top layer `modules`, which may import `types` and
`schema` only). It is the one thing a module imports to describe itself, so a manifest that does not fit is a type error.

`components` is the only place a component is named. `routes` refer to a component by its key; Python refers to it by
`"<app>:<key>"`. A component that no manifest key names cannot be used by a model, which is the point: a typo in
`InterfaceMeta` is found by `pangloss interface check` (§6), not by a blank page.

### 3.3 The contracts (props), in `interface-core/src/types/modules.ts`

One props type for each slot. They are the stable surface of the module system and are versioned with `interface-core`
(§10).

```ts
export interface ListPageProps {
  type: string;                     // the type in the address (/:type); may be a parent of what the model is
  model: ModelDefinition;           // its definition
  search: Search;                   // ?q= and ?deep= as the generic page reads them (searchOf)
  onSearch: (s: Search) => void;    // writes them back to the address
}
export interface ItemPageProps {
  type: string;                     // the item's own type
  id: string;
  item: Resolved<Item>;             // already read (the page's `preload` has fetched it)
  model: ModelDefinition;
}
export interface ViewCardProps {
  item: ItemSummary | Item;         // a summary where it is a result of a list; the whole item on its own page
  context: "result" | "reference" | "embedded" | "page";   // where it is shown
  href?: string;                    // where the card links to, if it links
  spaces?: ContextLabel[];
}
export interface EditCardProps {
  item: Item | undefined;           // undefined: a new one
  model: ModelDefinition;
  value: unknown;                   // the form's value for it (the shape of the API's Create / Edit model)
  onChange: (value: unknown) => void;
  errors?: FieldError[];            // from the API's 422
  disabled?: boolean;
}
```

`EditCardProps` is **provisional**: there is no editing in the interface yet ([interface.md](interface.md), "Decisions to
make next", 3). The slot, the reference to it and its validation are specified and built in phase 1; its props are fixed when the
forms are, and until then `edit_card` is accepted and exported but nothing renders it (§7).

A component follows the rules of Solid 2.0 in [interface.md](interface.md) (never destructure props; no `window` outside an
effect; no per-request state at module level), because it is rendered on the server too. It gets everything else the way the
library's components do: `useModels()`, `useComponent("Button")`, `useApi()`, `useSession()`.

### 3.4 What a module may import

- `@pangloss/interface-core` (its index and its sub-paths), `solid-js`, `@solidjs/web`, `@solidjs/router`.
- Its own files, and its own npm dependencies (a map library, say): they are installed with the others (§5.4).
- **Not** `interface-app`, nor another module's files. A module may *use* another module's components through the registry
  (`useModule("other")`, or a manifest key from a slot it is given); a dependency is declared in the manifest,
  `requires: ["other"]`, and is checked: the module must be installed, and a cycle is refused. A module that is `requires`d is
  built before it in the generated `modules.ts`, so the order of the bar and of route precedence follow the dependencies first,
  `INSTALLED_APPS` second.

**The components of `interface-core` are for modules to use.** Buttons, the primitives (`Button`, `Modal`, `NavRowButton`...), the
cards (`ResultButton`, `ReferenceChip`, `EntityCard`), `FieldList`, `ItemContents`, and the **console** (`Console`, `ConsoleBar`,
`ConsoleSearch`, `ConsoleButton`) are all exported from `@pangloss/interface-core`, and a module gets them with
`useComponent("Name")` so that a project's override of one reaches the module too (§5.3). A custom page therefore keeps the console
of the generic page: `<Console type={...} list ... />` with the same props. Two things to do in phase 2 for this to be true:
(1) audit `interface-core`'s exports and `ComponentMap` for what a module would need and does not get (the console's pieces
are exported by name but the console is not yet composed of parts a page can rearrange, so a *custom* console is by
`createComponentMap({ Console: MyConsole })`, or by a page passing `Console` extra buttons: `Console` gains an `actions` slot
for that); (2) document them in the module's README, which `new-module` writes.

`check:layers` gets two more rules (§5.6): a module may not import the application, and `interface-core` may not import a
module.

## 4. The Python side

### 4.1 `InterfaceMeta` (in `pangloss_interface/meta.py`)

```python
ComponentRef = NewType("ComponentRef", str)       # "app:Name"

@dataclass(frozen=True)
class InterfaceMeta:
    colour: Colour | None = None
    list_page: ComponentRef | None = None
    item_page: ComponentRef | None = None
    view_card: ComponentRef | None = None
    edit_card: ComponentRef | None = None
```

```python
class Manuscript(Document):
    _interface_meta = InterfaceMeta(
        colour="amber",
        item_page="pangloss_manuscripts:ManuscriptPage",
        view_card="pangloss_manuscripts:ManuscriptCard",
    )
```

Validated in `__post_init__`, like `colour` is: a `ComponentRef` is `<identifier>:<identifier>` (`PanglossMetaError` otherwise). That
it *exists* cannot be known there (the JavaScript is not read when a model is defined), so §6 does it.

**Inheritance (decided):** a subclass inherits each field from its parent unless it sets that field itself, so
`InterfaceMeta(colour="red")` on a subclass changes the colour and keeps its parent's `item_page`. This is field by field,
not the whole-slot replacement that other meta slots use (docs/meta-slots.md says so for `_interface_meta`; the rule is added
there). A field is "not set" when it is `None`. To *turn off* an inherited component (the child wants the generic page), the field
is given `False`:

```python
class Letter(Manuscript):
    _interface_meta = InterfaceMeta(item_page=False)    # the generic page again; the card and colour are Manuscript's
```

`list_page`, `item_page`, `view_card` and `edit_card` are `ComponentRef | Literal[False] | None`; The merge is done when the definitions are exported (walking the class's MRO, nearest first),
so the JavaScript only ever sees the resolved values and never walks the hierarchy. (`colour` follows the same rule; today
it is the same in effect, since a class that sets `InterfaceMeta()` has `colour=None`, which then means "the parent's" and not
"the default": a small change that the tests pin.)

Which model's page is used for an item is the item's **own** type (a `Letter` found under `/Document` gets `Letter`'s card), with
the nearest ancestor that names one if its own does not (resolved when the definitions are exported, so the JavaScript does not
walk the hierarchy: `interfaceMeta` of each exported model already holds the inherited value).

### 4.2 The export

`export_definitions()` already adds `interfaceMeta` to each model. It becomes
`{colour, listPage, itemPage, viewCard, editCard}`, with a reference exported as `{module, name}` (split at the colon).
`interface-core/src/types/models.ts` gets the same shape, and `test_models_match_typescript.py` holds the two together as it does for
`colour`.

### 4.3 Discovering the modules of the installed apps

`pangloss_interface/modules.py` (new, pure, tested without Node):

```python
@dataclass(frozen=True)
class InterfaceModule:
    app: str                 # "pangloss_calendar"
    root: Path               # <app dir>/interface
    package_name: str        # from its package.json

def discover(installed_apps: list[str]) -> list[InterfaceModule]: ...
def read_manifest(module, runtime) -> Manifest: ...   # §6: runs Node once to read the manifest as JSON
```

`discover` imports no app code beyond finding its directory (`importlib.util.find_spec(app).submodule_search_locations`); an app
has a module if `interface/package.json` is there. The order is that of `INSTALLED_APPS`, which is also the order of the
navigation bar's sections and of precedence for a route that two modules claim (the later wins, and it is logged).

### 4.4 `InterfaceConfig`: the navigation bar

An app says where its links go in a file of its own, **`<app>/interface_config.py`** (the same kind of hook as `api.py`, `cli.py`
and `structure.py`; it is not `interface.py`, which would sit beside the module's `interface/` folder and be confusing):

```python
# pangloss_manuscripts/interface_config.py
from pangloss_interface.config import InterfaceConfig, NavLink, NavModel

config = InterfaceConfig(
    nav=[
        NavModel("Manuscript", label="Manuscripts", section="Sources", order=10),
        NavModel("Folio", hidden=True),                  # a type that is not to be in the bar
        NavLink("Collation chart", href="/manuscripts/collation", section="Sources", order=20),
        NavLink("The library", href="https://example.org", external=True, section="Sources"),
    ],
    sections=["Sources"],                                 # the order of sections this app introduces
)
```

- `NavModel(model, label=, section=, order=, hidden=)` places a *type*. `model` is checked against the models when the definitions
  are exported (an unknown name is a `PanglossMetaError`-style error naming the file). It is the link to `/<model>`.
- `NavLink(label, href, section=, order=, external=, requires_login=)` is any other link: a page of a module's `routes`, or
  elsewhere. `href` starts with `/` (inside the interface; checked against the module's routes in §6 when it matches one) or is
  `external=True`.
- Without a `NavModel` for a type, it stays where the bar puts it now, under *Entities* or *Documents* by kind, in the order of the
  hierarchy. So nothing needs configuring, and an app only says what differs.
- **Merging** (`config.merge(configs)`, pure): the configs of the installed apps are read in the order of `INSTALLED_APPS`. Sections
  are in the order they first appear (the generic *Entities* and *Documents* first, unless a config lists them in `sections`).
  Two entries for the same type: **the later app wins**, so the project's own app, which comes last, has the final word over a
  library's; `hidden=True` there hides a library's link. Within a section, entries are by `order`, then by label.
- Labels are text for the user: the label is a UI slot (`nav.<app>.<label>` in `translations/ui.jsonc`), with the label given here
  as the default-language text (§8), so a link is translated like the rest.
- **Export:** `export_definitions()` gains a top-level `nav`: `[{ title, entries: [{ kind: "model" | "link", model?, label, href, order,
  external, requiresLogin }] }]`, already merged and resolved, so the JavaScript only draws it. `models.ts` gets the type, and the
  guard test holds the two together.

## 5. Building it into the interface

### 5.1 In `.pangloss/interface`

`prepare` (`workspace.py`) gains three steps, after copying the package's JavaScript and writing the models:

1. **Copy each module** to `.pangloss/interface/modules/<app>/` (the same `write_if_changed`; the same `.synced.json`
   mechanism with the module's files listed, so one that is gone is removed). `node_modules` and `dist` are not copied.
2. **Write the workspace**: `package.json` of the working directory gets `"workspaces": ["interface-core", "interface-app",
   "modules/*"]`. The package's own `package.json` lists only the first two (it is also what runs from the source), so `prepare`
   writes the working directory's from it, with the third added, only when there are modules. (A test holds the rest equal.)
3. **Write `interface-app/src/generated/modules.ts`**:

```ts
// generated: do not edit
import pangloss_calendar from "../../../modules/pangloss_calendar/src/index";
import demo_app from "../../../modules/demo_app/src/index";
export const modules = [pangloss_calendar, demo_app] as const;
```

It imports the **manifests** eagerly (they are small: names, paths, lazy loaders) and nothing else; the components are in the
chunks that `() => import(...)` makes. The package has an empty `modules.ts` (`export const modules = []`), as it has an empty
`models.ts`, so that it builds by itself.

### 5.2 In the application

- `interface-app/src/modules.ts`: `const registry = createModuleRegistry(modules)`; provided with a `<ModulesProvider>` beside
  `ModelsProvider`. `useModules()` gives the registry; `useCustom(model, slot)` returns the component for a model's slot (a lazy
  component) or `undefined`.
- `routes.ts`: the routes of the modules are added **before** `/:type`, so `/calendar/...` is not read as a type. A route's
  `component` key is turned into `lazy(() => module.components[key]())`, and its `preload` is the manifest's. A route that
  would shadow a model's name (`/Person`) is refused when the registry is made (§6).
- The generic pages become dispatchers. `List.tsx`:

```tsx
const Custom = useCustom(model(), "listPage");
return <Show when={Custom()} fallback={<DefaultList {...props} />}>{(C) => <C() ... />}</Show>;
```

  (the same for `Item.tsx` with `itemPage`). The page's `preload` is unchanged, so the data is already being read; a module's own
  `preload` is added by route only for routes the module declares.
- `ResultButton`, `ReferenceChip` and `EntityCard` ask `useCustom(type, "viewCard")` and render it if there is one, so a card is
  used in every list and reference without each page knowing. `ItemContents` does the same for an embedded item. This is the
  one place the library asks the registry; it does it through a context (`useModules()`), so `interface-core` imports nothing
  of a module.
- `NavBar`: with no `InterfaceConfig` anywhere, `NavModelList` is as it is now. With one, the bar is built from the exported `nav`
  (§4.4): `NavModelList` takes the resolved sections and entries as a prop (`sections`) instead of walking the model hierarchy
  itself, and the application passes `definitions.nav`. The library does not import the registry or the config.

### 5.3 Overrides stay separate

The component map (`createComponentMap`) replaces a *library component* everywhere. A module's slots replace the *page or card of
one model*. A project may use both; a module must not rely on the map (it may use whatever the map gives it). If a project's own
map overrides `ResultButton` it takes over the cards too, since the cards are looked up inside the default `ResultButton` (§9).

### 5.4 Installing and building

`npm install` at the working directory now installs the modules' dependencies with the rest (they are workspaces).
`vite.config.ts` changes in two ways: `ssr.noExternal` gets the module package names (the application writes
`PANGLOSS_MODULE_PACKAGES` into a generated `modules.json` that the config reads, since the config runs before the app does), and
`resolve.dedupe: ["solid-js", "@solidjs/web", "@solidjs/router", "@pangloss/interface-core"]` so a module that installed its own copy
of Solid does not make two (two copies of Solid is a bug that looks like reactivity not working).

Tailwind: styles are in the application's `styles.css`. A module's classes must be seen by the scanner, so `prepare` writes
`@source "../../modules";` into a generated `generated/sources.css` that `styles.css` imports. A module uses Tailwind and only
Tailwind for its CSS.

### 5.5 Development

`pangloss interface dev --link` runs the application from the package's source. Modules in the installed apps that are editable
installs (a checkout) are used **in place**: the generated `modules.ts` for a linked run imports from the app's own folder, `fs.allow`
gets the folders, and Vite's HMR then works on a module's files. A module in `site-packages` is copied as in a normal build.

### 5.6 Checks

`pangloss interface check` already prepares, typechecks and checks the layers. It gains:

- the typecheck covers the modules (`typecheck` is run in each workspace);
- `.dependency-cruiser.cjs` rules: `interface-core` (and `interface-app` except `generated/` and `modules.ts`) may not import `modules/`;
  a module may not import `interface-app` or another module's files;
- **the references** (§6).

## 6. Checking the references

A reference is checked in the Python process, because the model is there, and the manifest is read in a Node one-liner (it is
JavaScript): `pangloss interface check` and `build` both run `read_manifest` for each module (`node -e` through the runtime,
loading the built-in `tsx`-less path: the manifest is **plain data apart from `() => import()` functions**, which are not called;
it is read by Vite's SSR loader, `vite-node`, once; see the risk, §10). It returns JSON: the module name, the keys of `components`, the
routes.

Then (`pangloss_interface/modules.py: problems()`), with the exported models:

| Problem | Message |
|---|---|
| a model names `app:Name`, and `app` has no module | `Manuscript.item_page 'pangloss_manuscripts:ManuscriptPage': no installed app 'pangloss_manuscripts' has an interface module (pangloss interface new-module)` |
| the module has no such key | `... 'ManuscriptPage' is not in components (it has: ManuscriptCard)` |
| a manifest `name` is not its app's name | |
| a route component key is not in `components` | |
| a route that would be read as a type (`/Person`), or two modules' routes equal | |
| `requires` names a module that is not installed, or the requirements make a cycle | |
| a module's `peerDependencies` have a range that does not fit `interface-core`'s | |

`check` fails on any. `build` warns and, with `--strict`, fails: a reference that does not resolve falls back to the generic
page at run time (a warning in the console in development), never to an error page.

## 7. The command: `pangloss interface new-module <app>`

```
pangloss interface new-module APP [--force] [--with-example] [--link-name NAME]
pangloss interface modules              # lists the modules found, what each provides, and the problems
```

`new-module` makes `<app dir>/interface/` for an installed app (a name in `INSTALLED_APPS`; refused otherwise, and refused if
`interface/` exists unless `--force`, which writes only the files that are missing). It writes:

- `package.json` (name `@pangloss-module/<app>`, `type: module`, `peerDependencies` ranges taken from `interface-core`'s own,
  `files: ["src"]`, scripts `typecheck` and `test`);
- `tsconfig.json` (extends the workspace's base; `jsx: preserve`, `jsxImportSource: @solidjs/web`);
- `src/index.ts` with an empty `defineModule({ name: "<app>", components: {}, routes: [] })`;
- with `--with-example` (the default for the first module of a project): `src/components/ExampleCard.tsx` and a test, the
  card wired into `components`, so that it works the moment a model names `"<app>:ExampleCard"`;
- `README.md` (what the manifest is, the contracts, how to name a component from a model);
- and adds `[tool.uv.build-backend]` includes if the app's `pyproject.toml` excludes by default (it prints the lines; it
  does not rewrite someone's `pyproject.toml`).

It does **not** touch `INSTALLED_APPS` (the app is already there), run `npm install`, or add anything to `models.py`. It prints the
three next steps: name a component in `InterfaceMeta`, `pangloss interface check`, `pangloss interface dev`.

The command is in `pangloss_interface/cli.py` (the `interface` group), the scaffolding is in `pangloss_interface/scaffold.py`
(pure: a function from the app name and the versions to a dictionary of path to text), and the text of the templates is in
`pangloss_interface/templates/module/` as files, not strings in code.

## 8. Strings and translations

Uses the system that exists ([translations.md](translations.md)), with no new file format.

- A module **may** ship default translations, and need not. They are the app's own `translations/ui.jsonc` (the file every installed
  app can already have for its UI slots), so the module's strings are keyed like any other UI slot; the key is prefixed with the
  app's name (`pangloss_calendar.month.title`), so two modules cannot clash. `gather` reads it for every installed app, as it does.
- A module that ships none still works: its components ask for a slot, and the slot's text is whatever the project gives (below), or,
  if nothing gives one, the **default language's text**, or, if there is none either, the key shown as it is (so a missing string is
  visible and `check` reports it).
- **The project has the final word:** `<project>/translations/ui.jsonc` wins over the module's. Precedence, highest first:
  the project's file; the app's file; (for a language other than the default) the default language's text at run time. This is
  exactly the order [translations.md](translations.md) gives for models and for the interface's own slots.
- `pangloss interface translations check` lists the slots a module's components use that have no text in a language, per module.
  The slots are found from the module's source by `gather` (the same extraction that reads `interface-app/src`), now also reading
  `modules/*/src` in the working directory.
- Hard-coded strings in a *library's* module are added to `docs/interface-strings.md` when it is written, as the application's are.

## 9. What is deliberately not here

- **A module is not a plugin system for behaviour.** It adds pages, cards and links. It cannot change the router, the session or the
  API client; those are the application's.
- **No runtime loading.** Modules are known when the interface is built. A project that adds an app rebuilds; there is no fetching
  of a module's script from the API.
- **No hot-swapping of a card per user**; a card is a function of the model.
- **A project's own override of the generic pages** (decision 1 in [interface.md](interface.md): "a folder of the project's own
  files laid over the copy") is not part of this. A project that wants a page of its own for its own model has the same
  mechanism as a library: it makes a module of its own app (`pangloss interface new-module demo_app`). That is the answer to
  the earlier question, and it is why a project's own app counts as an app with a module.

## 10. Risks and things to decide while building

1. **Reading the manifest from Python.** The manifest is TypeScript with dynamic imports. Reading it needs a TypeScript-aware loader.
   The least new machinery: a small script in `interface-app/scripts/read-manifest.ts` run by Vite's SSR loader
   (`vite-node`), already a dependency of the toolchain; its cost is a second or two for `check`/`build`. Alternative: the manifest
   is also written as `interface/manifest.json` by the module's own `npm run manifest`, and committed. That is brittle (it can
   drift) so it is the fallback only.
2. **Versions of the contract.** `interface-core` is `0.x` and its types will move. A module declares
   `peerDependencies["@pangloss/interface-core"]`; `modules()` fails `check` if the range does not admit the version in the copy.
   Until `1.0`, a module is expected to be updated with the package.
3. **Two copies of Solid** (above: `dedupe`, and a check in `check` that `node_modules/solid-js` is single).
4. **SSR and lazy components.** A lazy component renders on the server inside a `<Loading>`; the pages already do. The dispatchers
   place the lazy component *inside* the page's `Loading`, so a card in a list does not hold back the list.
5. **Cost.** Every row of a list asks `useCustom(type, "viewCard")`. It is a lookup in a `Map` made once from the definitions
   (not a walk of the hierarchy), so it is free; the card's chunk is fetched once per type shown.
6. **A card in a list of mixed types** (the `/Document` list shows letters and manuscripts): each row uses its own type's card.

## 11. Decisions

Made:

1. **Slots on a subclass:** inherited field by field; a child's own value wins; `False` turns an inherited one off (§4.1).
2. **"View card" and "edit card":** the *view card* is how an item is shown wherever it is part of something else (a result in a
   list, a reference from another item, an embedded item); the item's own page is the `item_page`. The *edit card* is the form for
   one item, and also inside another's form for an embedded one.
3. **Where a link is declared:** all of them, for models and for anything else, in the app's **`InterfaceConfig`** (Python, §4.4),
   not in `InterfaceMeta` and not in the manifest. (The manifest is the module's `src/index.ts`, the `defineModule({...})` of §3.2:
   components and routes only.) One place for the layout of the bar, and it is Python, where the models are.
4. **Translations:** a module may ship defaults, in the app's `translations/ui.jsonc`; the project's file wins; the fallback is
   always the default language's text (§8).
5. **The npm name:** `@pangloss-module/<app>`, only ever a workspace name (not published).
6. **`requires` between modules:** kept (§3.4); and a module can use all of `interface-core`'s components, the console included.

Still open: none that block phase 0.

## 12. Phases

Each ends with the tests passing, the docs updated (`docs/interface.md`, `docs/interface-to-document.md`, `docs/cli.md`) and the
strings in `docs/interface-strings.md`. Nothing is added to a page the user has not asked for; phases 2 and 3 change the generic
pages only to dispatch.

**Phase 0: the contract (Python and types only).**
`meta.py` (the new fields, `ComponentRef`, validation), `config.py` (`InterfaceConfig`, `NavModel`, `NavLink`, merging); `export_definitions` and `models.ts` with the new shape; the
guard test. *Tests:* `test_interface_meta.py` (accepts and refuses references; inheritance is field by field and `False` turns one off; the export), `test_interface_config.py` (merging: later app wins, hidden, sections, unknown model refused), and
`test_models_match_typescript.py`.

**Phase 1: discovery, scaffolding, and the check.**
`modules.py` (`discover`, `problems`; reading each app's `interface_config.py`), `scaffold.py` and templates, `new-module` and `modules` commands, `read_manifest`.
*Tests:* a fixture app in a temporary directory: `new-module` writes the files and refuses to overwrite; `discover` finds it;
`problems` for each row of §6 (with a manifest given as data, so no Node is needed); one test that does read a real manifest
through the runtime, skipped without Node, like the existing `test_javascript.py`.

**Phase 2: building it in.**
`workspace.prepare` (copy, workspaces, `modules.ts`, `sources.css`), `vite.config.ts` (`noExternal`, `dedupe`), the `modules`
layer of `interface-core` (`defineModule`, the registry, `ModulesProvider`, `useCustom`), the layer rules.
*Tests:* `test_interface_workspace.py` (files copied, stale removed, workspaces and `modules.ts` written, nothing written
when there are no modules); `check:layers` fails on a module importing the application (a fixture); the registry in Vitest
(slots, routes, the shadowing of a type).

**Phase 3: the slots.**
The dispatchers in `List.tsx` and `Item.tsx`; the cards in `ResultButton`, `ReferenceChip`, `EntityCard` and `ItemContents`; `NavBar`
`NavModelList` taking `sections`; the module routes in `routes.ts`. *Tests:* component tests (Vitest, happy-dom) with a
registry holding a fixture module: a custom list page replaces the generic one for its type only; a subtype falls back to its parent's
card; with none the generic page is unchanged (the existing tests are the guard); nav entries appear in order.

**Phase 4: one real module, as the proof.**
Not the calendar's pages (that waits for the calendar interface, which has not been asked for): a small module in the test fixtures,
built for real with `pangloss interface build` in a throwaway project, and served; the custom card and page are in the server-rendered
HTML. Then `--link` (HMR on a module). The first library module is written when a package needs one.

**Phase 5: edit cards.** With the forms: `EditCardProps` fixed, the slot rendered, and the `new-module` example extended.

## 13. Files

| File | Change |
|---|---|
| `pangloss_interface/meta.py` | new fields, `ComponentRef`, export |
| `pangloss_interface/config.py` | new: `InterfaceConfig`, the nav entries, reading each app's, merging, export |
| `pangloss_interface/modules.py` | new: `discover`, `read_manifest`, `problems` |
| `pangloss_interface/scaffold.py`, `templates/module/` | new |
| `pangloss_interface/cli.py` | `new-module`, `modules`; `check` and `build` call `problems` |
| `pangloss_interface/workspace.py` | copy modules, workspaces, generated files |
| `js/interface-core/src/modules/` | new layer: `defineModule`, registry, provider, `useCustom` |
| `js/interface-core/src/types/{models,modules}.ts` | the shapes above |
| `js/interface-core/src/components/{NavBar,NavModelList,ResultButton,ReferenceChip,EntityCard,ItemContents}.tsx` | ask the registry |
| `js/interface-app/src/{App.tsx,routes.ts,modules.ts,pages/List.tsx,pages/Item.tsx}` | provider, routes, dispatch |
| `js/interface-app/vite.config.ts`, `js/.dependency-cruiser.cjs` | `noExternal`, `dedupe`, the layer rules |
| `js/interface-app/src/generated/modules.ts` | empty in the package; generated in the project |
| `docs/interface.md`, `interface-to-document.md`, `interface-strings.md`, `cli.md`, `meta-slots.md`, `README.md` | updated |

## 14. As built (2026-10-29), and where it differs from the above

Phases 0 to 4 are done. Tested: Python (`test_interface_meta.py`, `test_interface_config.py`, `test_interface_modules.py`, the guard in
`test_models_match_typescript.py`), Vitest (`schema/modules.test.ts`, `components/CustomCards.test.tsx`), the layers, and a real
throwaway project on the test database: `new-module`, `check` (types of the module, layers, references; a wrong reference is reported),
`build` (a chunk for each component), `serve`: the module's route (`/modapp/chart`), the custom item page and the custom card in a list are
in the server-rendered HTML.

Differences from the text above:

- **`nav` is exported unresolved by hierarchy.** `definitions.nav` is `{ sections, models: {Name: {label, section, order, hidden}}, links }`;
  the hierarchy of the types is still drawn by the interface (`schema/nav.ts: navSections`), which applies it. `NavModelList` reads
  `useModels().nav` itself (no `sections` prop). A type moved to another section is at depth 0 there.
- **No separate `modules` layer.** `defineModule`, the ordering and the lookups are in `schema/modules.ts`; the provider and
  `useCustom()` are in `context/modules.tsx`, and a library component calls `useCustom()(type, "viewCard")`. Without a provider there are
  no modules (the context has a default), so nothing changes for a project without any. `ModulesProvider` is in `App.tsx`.
- **`Console` already has an actions slot** (its `children`), so none was added; a custom page draws `useComponent("Console")` itself.
- **An item page keeps the Console bar** (type, label, spaces) and replaces what is under it; a list page replaces the whole page,
  including its Console, since the search is part of it (`ListPageProps` has `search` and `onSearch`).
- **`ViewCardProps`** has `type`, `id?`, `label`, `href?`, `spaces?`, `item?` (the data of an embedded item) and `context`. A card **replaces**
  `ResultButton` / `ReferenceChip` for its type, so it must draw the item itself; the scaffolded example does. (An example that renders
  `ResultButton` for its own type asks for itself again.)
- **Reading the manifests** is `interface-app/scripts/read-manifests.mjs`: Vite's SSR loader with the Solid plugin (risk 1 of §10, as proposed;
  about half a second).
- **`prepare` replaces `package.json`** of the working directory (workspaces `modules/*` only when there are modules); the modules'
  files are tracked in `.synced-modules.json`.
- **`dedupe`** is set in `vite.config.ts`; `noExternal` is not needed (a module is source reached by path, not a package from `node_modules`).
- **`check:layers`** also cruises `modules/*/src` when they are there (the script lists them), with three more rules.

Done afterwards (2026-10-29):

- **One component asks the modules: `Customised`** (`components/Customised.tsx`: `slot`, `type`, `props`, `fallback`, `skip`). `ResultButton`,
  `ReferenceChip`, `ItemContents` (embedded items and blocks), and the `List` and `Item` pages use it instead of each repeating the lookup.

- **`dev --link` uses the modules where they are.** `prepare_linked` writes `linked/modules.ts` (imports of each module's `src/index` by
  absolute path), `linked/sources.css` (`@source` of each module folder) and the app is given `PANGLOSS_MODULES_MODULE`,
  `PANGLOSS_SOURCES_CSS` and `PANGLOSS_MODULE_ROOTS` (`@generated/modules` and `@generated/sources.css` are aliases beside
  `@generated/models`; `dedupe` makes a module's `solid-js` and `interface-core` the application's). Tried for real: a module's route is
  server-rendered, Tailwind sees its classes, and editing its file shows at once. A module's *own* npm dependencies are found only if it has
  its own `node_modules`. A module's `tsconfig.json` is now self-contained (it used to extend the workspace's, which is not there when run in place).
- **`requires_login` links** are shown only to someone logged in (`NavModelList loggedIn`, from the bar's `user`).
- **Labels are translation slots.** Each exported entry has `labelSlot` (`nav_<app>_<label>` in `snake_case`); the label as written is the
  default-language text (the lowest `ui` layer, `i18n/resolve.py`), so the app's or the project's `ui.jsonc` can translate it, and
  `translations check` reports a language without one. A module's own strings are slots in its app's `translations/ui.jsonc`, which is
  already read for every installed app. (The interface does not yet *read* the gathered translations at all, so nothing is translated on screen yet; that is the general
  translation work, not the modules'.)
- **`check` also reports** a module whose `peerDependencies` range for `@pangloss/interface-core` does not admit the version (or has none), and a
  `NavLink` inside the interface that is neither a type nor a route of a module.

Not done:

- A module's strings are not *extracted from its source* to be listed as slots to translate (the interface itself has no extraction either; its slots are
  in `docs/interface-strings.md`).
- Edit cards: the slot and reference are exported and checked, but nothing renders `edit_card` (with the forms, as decided).
