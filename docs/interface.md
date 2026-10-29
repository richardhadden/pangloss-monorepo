# The interface (`pangloss-interface`)

The web interface of Pangloss. **Status: scaffolding only.** The structure, the tooling, the build in the
project and the export of the models are in place; the pages and components are placeholders.

It is a Python package (so that it installs and is configured like the other parts) that holds a
JavaScript workspace:

```
packages/pangloss-interface/
  pyproject.toml
  src/pangloss_interface/
    cli.py            pangloss interface <command>: wraps the JavaScript tools
    api.py            endpoints the interface needs, under /api/interface
    runtime.py        finds and runs Node (or Bun)
    workspace.py      the project's working directory (.pangloss/interface)
    typescript.py     the models as a TypeScript module
    paths.py          where the JavaScript is
    js/               an npm workspace
      package.json    workspaces; scripts: typecheck, check:layers, build, dev
      .dependency-cruiser.cjs   the rules of the layers (see below)
      interface-core/ the LIBRARY (@pangloss/interface-core): components, API client, types
      interface-app/  the APPLICATION (@pangloss/interface-app): Solid 2.0, SSR, routing
```

Add `"pangloss_interface"` to `INSTALLED_APPS`. Its `cli.py` adds `pangloss interface …`, and its
`api.py` router is included by the API (see [REST API](api.md)).

## Solid 2.0, not 1.x

Everything here is **Solid 2.0** (release candidate: `solid-js@next`, currently `2.0.0-rc.15`). Take
care with documentation, examples and AI suggestions that are for 1.x. [SolidStart v2 is built on
Solid **1.x**](https://docs.solidjs.com/solid-start/v2) (and is in maintenance), so it is **not**
used. Solid 2.0 has its own turnkey SSR in its Vite plugin, which is what the application uses.

Packages (`next` / RC versions; they are released in lockstep and must match):

| Package | Is |
|---------|----|
| `solid-js` | the core (also the stores: `createStore` is here, not in `solid-js/store`) |
| `@solidjs/web` | `render`, `hydrate`, `renderToStream`, `HydrationScript`, `httpStatus`, and the `JSX` types (not `solid-js/web`) |
| `@solidjs/vite-plugin` | the Vite plugin (was `vite-plugin-solid`): `solid({ ssr: true, start: { node: true } })` generates the client and server entries around `src/App.tsx` in the shell `src/Document.tsx` |
| `@solidjs/router` | `createRouter({ routes })` (config-based), typed `paths`; `@solidjs/router/fs` for file routes |
| `@solidjs/meta` | `<Title>` and the like |

[Rules from the 2.0 migration](https://v2.solidjs.com/migration/from-solid-1) to keep to in this code:

- `tsconfig`: `"jsx": "preserve"`, `"jsxImportSource": "@solidjs/web"`.
- **Effects are split**: `createEffect(() => tracked, (value) => { effect })`; no `createComputed`, no
  `on`. `onMount` is `onSettled`. Cleanup is returned from the effect.
- Setters are **batched to the next microtask** (a read straight after a write is the old value; `flush()`
  is for tests). No `batch`.
- **No `createResource`**: an async read is `createMemo(() => fetch…)`, shown in a `<Loading>` (was
  `Suspense`); `<Errored>` (was `ErrorBoundary`); `Reveal` (was `SuspenseList`).
- Stores: draft setters (`setState(draft => { draft.a.b = 1 })`); no path arguments, `produce` or
  `createMutable`. `merge` / `omit` replace `mergeProps` / `splitProps`.
- A context is its own provider: `<MyContext value={x}>` (no `.Provider`).
- Never destructure props; read `props.x` where it is used. Event props are camel case (`onClick`);
  no `classList` or `use:`.
- Components and module state run on the server too: no `window` outside an effect/`onSettled`, and no
  per-request state at module level.

## Bun or Node?

**Node is the default; Bun is supported as a choice** (`--runtime bun` or
`PANGLOSS_INTERFACE_RUNTIME=bun`).

Why Node:

- It is what the toolchain is built and tested on: Vite 8, the Solid plugin and the server it builds
  (`dist/server/node.js`) target Node first, and Solid's own deployment docs treat Node as the main path.
  Bun runs them, but a bug in a dev tool is then yours to work out.
- It is already there. People installing a Python package are likelier to have Node than Bun, and every CI
  image, Docker base and host can run it. The interface is *part of a Python package*; the fewer extra
  things to install, the better.
- It is predictable in production, where a server-rendering process that fails in a Bun-only way costs
  more than a slower install.
- `npm` ships with it, and npm workspaces are enough for two packages (no pnpm, which Node 25+ no longer
  has `corepack` to provide).

Why still allow Bun: installs and start-up are much faster, it runs TypeScript directly, and
`package.json` and the workspaces are the same, so there is no cost to allowing it. The same
`dist/server/node.js` runs under Bun, so a deployment can choose. If its use grows, a CI job should run the
checks under both.

Requires Node ≥ 22.12 (Vite 8).

## Building in the project

The interface is not built in the installed package (which should not be written to), but in
**`.pangloss/interface/` in the project**. Every command that needs it first:

1. copies the package's JavaScript there (`interface-core`, `interface-app`, `package.json`, ...), writing
   only what changed and removing what a newer package no longer has (`.synced.json` lists what came from
   the package, so the project's own files are left alone);
2. **exports the definitions of the project's models** (see below) to
   `.pangloss/interface/interface-app/src/generated/models.ts`;
3. installs the packages if they are not (`node_modules`), and then runs the tool.

`.pangloss/interface/.gitignore` ignores `node_modules`, `dist` and `.env` and nothing else: the copied
sources and the generated models can be committed (to see what changed in the interface with a new
version of Pangloss), or `.pangloss` ignored as a whole. Nothing there should be edited, as the next command
writes over it; project overrides will be laid over it from a folder of the project's own (not yet).

## The models in the interface

`pangloss_models.export.export_models()` turns the `ModelFields` of every initialised model into plain
data (no database is needed): for each model its kind, whether it is abstract, its docstring, parent and
concrete subtypes, type parameters, and every field with its `kind` (`literal`, `list`, `relation`, `embedded`,
`annotatedValue`, `typeVar`), its Python name and the `key` it has in the JSON of the API (`born_in` is
`bornIn`), whether it is required or nullable, its type or the types it can relate to (including those
through reified relations, semantic spaces and conjunctions), its validators, and the relations *to* the
model (`incoming`). The enums are listed with their members. The shape is documented in the module's
docstring and typed in `interface-core/src/types/models.ts`.

`typescript.py` writes it as `generated/models.ts`:

```ts
export type ModelName = "Person" | "Place" | "Statement";
export const definitions: ModelDefinitions = { models: {...}, enums: {...} };
```

`interface-app/src/App.tsx` gives `definitions` to `<ModelsProvider>`, and what is shown is decided from it:
the home page lists `headModels(useModels())`, and `FieldList` shows the fields of `/:type`. The library
reads it only through `useModels()` / `useModel(name)` and the helpers of `schema/` (it never imports the
generated file, which belongs to the application). The package has an empty `generated/models.ts`, so that
it builds by itself.

Restart `pangloss interface dev` after changing the models: they are exported when it starts.

## Commands

`pangloss interface …` (each takes `--runtime`; each needs the project's settings, as other `pangloss` commands do):

| Command | Does |
|---------|------|
| `info` | the working directory, whether it is installed and built, and the runtime found |
| `export-models [--format ts\|json] [-o FILE]` | prints (or writes) the exported models, without building |
| `install` | prepares the working directory, and installs its packages |
| `dev [--api-url] [--port] [--link]` | prepares it, then the Vite dev server with HMR and SSR; passes `/api` on to the API (`pangloss dev`). `--link`: see below |
| `build` | prepares it, then `vite build` → `.pangloss/interface/interface-app/dist/{client,server}` |
| `serve [--host] [--port]` | runs the built `dist/server/node.js` |
| `check` | prepares it, type-checks both packages (with the project's models), and checks the layers of the library |

For development: `pangloss dev` (API, port 8000) and `pangloss interface dev` (interface, port 3000).

### Working on the interface: `dev --link`

The copy in `.pangloss/interface` is overwritten by every command, so edits to `interface-core` and
`interface-app` would not show in it. For working on the interface itself, `pangloss interface dev --link`
runs Vite **from the package's own source** (`packages/pangloss-interface/src/pangloss_interface/js`), with
HMR, while the models come from the project: they are exported to `.pangloss/interface/linked/models.ts` and
the app's `@generated/models` alias is pointed at it (`PANGLOSS_MODELS_MODULE`, in `vite.config.ts`). Edit
the package, and the page in the project changes at once; the package's own empty `generated/models.ts` is
not touched. It needs a checkout of the source (an editable install), and installs the packages in the
package's `js/` the first time. (Symlinking the copy was not used: Vite follows a link to its real path, so
`solid-js` and the rest would be looked for next to the package, not the project.)

## Architecture

**The browser only talks to the interface's server**, on one origin; `/api` is passed on to the Pangloss
API (the Vite dev server does it in development; in production a reverse proxy, or a middleware of the
interface's server, does). So: no CORS, cookies are first-party, and the server-side render can call the API
as the user. (The API's CORS settings are for other frontends.)

**Rendering**: streaming SSR (`ssr: true`), hydrated in the browser. The routes are written in code, in
`interface-app/src/routes.ts` (`defineRoutes` / `defineRoute`, so that `params` are typed from the path); the pages are in
`interface-app/src/pages`, each `lazy` (a chunk of its own). `/:type` is the list of a type and `/:type/:id` one item.

**Prefetching**: `router.ts` has `preloadLinks: intentPreload()`: a link that is hovered, focused or touched fetches the
page's code and runs the route's `preload`, which calls the page's queries (`void listQuery(...)`; the page reads the same
`query` in a memo, so there is one request). The `query` cache keeps the result for a few seconds, so the click that follows
is instant. A list's `preload` reads the search from the address (`searchOf` in `queries.ts`, shared with the page). A link
that must not do this has `preload="false"`.

### Sessions

The interface uses **the API's own cookie session** (`POST /api/users/session` puts the access and refresh tokens in HTTP-only
cookies; `DELETE` ends it; `GET /api/users/me` says who it is: see [api.md](api.md)). Because the browser only talks to the interface's
origin, which passes `/api` on, the cookies are first-party. A server render passes the request's `Cookie` header on to the API, so the
page is rendered for the user. See [interface-to-document.md](interface-to-document.md), "Sessions and logging in". (The opaque
session token that `api.py` was to give, and its stubs at `/api/interface/session`, are not needed.) Still to decide: CSRF protection
beyond `SameSite`, and what the interface does with a 401 in the middle of a session.

### Layers of `interface-core`

`interface-core` is a library that anything may import and that imports nothing of the application, so that
an application, or a user's project, can override components without a circular dependency. It is **source,
not a build**: its `exports` point at `src` (with the `solid` condition), and the application compiles it
(`ssr.noExternal` in `vite.config.ts`).

```
types  <  schema  <  api  <  context  <  primitives  <  components  <  registry  <  index
```

A layer may import only from the layers *below* it. `types` imports nothing (the props of every component,
the `ComponentMap` of overridable ones, and the types of the exported models are here); `schema` is pure
functions over the definitions of the models; `registry.ts` (the only module that names every
component) is above all of them, so nothing needs it. `npm run check:layers` (dependency-cruiser; also
`pangloss interface check`) fails on a cycle, a wrong direction, or an import of the application.

**Overrides**: a component never imports another that could be replaced; it gets it with
`useComponent("Button")`, from a `<ComponentsProvider>`. The application builds the map with
`createComponentMap({ Button: MyButton })` (`interface-app/src/components.ts`), so a replacement is used
everywhere, including inside the library's own components. The library depends on nothing that overrides it.

## Interface modules

An installed app can ship its own pages and cards: a Solid library in `<app>/interface/` (`pangloss interface new-module <app>`)
whose `src/index.ts` is `defineModule({ name, requires, components, routes })`. A model names a component in its
`InterfaceMeta` (`list_page`, `item_page`, `view_card`, `edit_card`, as `"app:Name"`), and an app's `interface_config.py`
(`InterfaceConfig`, `NavModel`, `NavLink`) places links in the navigation bar. `prepare` copies the modules to
`.pangloss/interface/modules/<app>/`, adds them to the npm workspaces, and writes `generated/modules.ts` (the manifests; the
components are lazy) and `generated/sources.css` (for Tailwind). `pangloss interface check` type-checks the modules, checks the
layers (a module may not import the application or another module's files; the library may not import a module) and checks that
every component a model names is in the module's `components`. Spec and what is built: [interface-modules-implementation.md](interface-modules-implementation.md).

## Packaging

The JavaScript is in the Python package (`js/`); `node_modules` and `dist` are left out of the wheel and
sdist (`[tool.uv.build-backend]`). `package-lock.json` is committed, and copied to the project. To work on
the interface itself, run `npm install` and `npm run dev` / `npm run check:layers` in the package's `js/`.

## Decisions to make next

1. **Project overrides**: a folder of the project's own files (components, routes, styling) laid over the
   copy in `.pangloss/interface` when it is prepared.
2. **`@pangloss/interface-core` stays in the wheel** for now (not published to npm).
3. **Styling** (Tailwind in the old interface), forms and the editing views, search/autocomplete.
4. **Sessions** (above), and the production proxy for `/api`.
5. **Using the models further**: forms from the field kinds and validators, a view for each model kind
   (reified relations, semantic spaces and conjunctions are only listed so far), and the `bindToChildField`
   and `Fulfils` information, which is not exported yet.
6. **Tests** of components (`@solidjs/testing-library`, Vitest) once there is something to test.

## Known issues

- `npm audit` reports `braces` (a transitive dependency of the development tool dependency-cruiser; not
  shipped).
- Solid 2.0 and its Vite plugin are pre-release: versions are pinned to `^…-rc` / `-next` ranges and will
  move.
