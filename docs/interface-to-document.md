# Interface: still to document

A running list of what has been built in the interface (`packages/pangloss-interface`) but is not yet in
[interface.md](interface.md) or the guide. Add to it as things are built; move an item into the real docs, and
delete it here, when it is written up.

## Stack and set-up

- [ ] **Solid 2.0 only** (RC; `solid-js` and `@solidjs/web` 2.0.0-rc.19 at 2026-10-28): not 1.9, and no React idioms
      (`class` takes arrays/objects, there is no `classList`; `Loading`, not `Suspense`). Versions of the router,
      meta and Vite plugin, and why the plugin's `latest` tag is the newest.
- [ ] **Tailwind 4** (`tailwindcss`, `@tailwindcss/vite`): all styling is utility classes; `interface-app/src/styles.css`,
      imported by `Document.tsx`. The base theme is kept for now.
- [ ] **`@source`**: Tailwind scans only the app by itself, so `styles.css` points it at `interface-core/src`;
      a class used in the library is otherwise silently not generated. Anything else beside the app (a
      project's overrides) needs the same.

## Layout

- [ ] **`NavBar`** (`interface-core/src/components/NavBar.tsx`): fixed, full height, 3rem wide retracted, overlays the
      page when expanded; the content scrolls inside it; the page needs `pl-12`. Overridable (`ComponentMap`).
- [ ] **`NavBarProps`**: `user`, `onLogin`, `onLogout`, `language`, `onLanguage`; `children` are the expanded content.
- [ ] **Glass look**: the nav bar and the console share it (translucent slate with `backdrop-blur-md`, a faint border, no shadow, `slate-700` text); the nav bar is `slate-300/60`, one shade darker than the console's `slate-200/60`.
- [ ] **Icons** (SVGs, emoji, icon cells) always have `select-none`.
- [ ] **Chrome text** (everything that is not content: the bar, and later headers, buttons, labels) is `uppercase font-semibold`;
      on the bar it is set once on the `<nav>` and inherited (buttons too: `styles.css` undoes the reset that stops them). Content is not.
- [ ] **Top row of the bar**: the Home link (`homeHref`, expanded only) on the left and the hamburger on the right, which
      turns 90° (animated) while the bar is expanded. `NavRow` has `ruled={false}` for the first row. Every row and icon cell of the bar is a 3rem square (as high as the console).
- [ ] **Expanding**: on hover of any of the bar, or the toggle button (for touch).
- [ ] **`useNavExpanded` / `NavExpandedProvider`**: the shared signal, so anything can close the bar
      (`setNavExpanded(false)`); a context, not a module signal, so server renders do not share it.
- [ ] **Login status row**: the icon (✕ not logged in, ✓ logged in) and the log in / log out button.
- [ ] **Language row**: the flag of the selected language (emoji for now: `en` → 🇬🇧, `de` → 🇦🇹) and, expanded,
      the other languages.
- [ ] **`NavRow` and `NavIconCell`** (primitives, not in the component map): a 3rem-high row of the bar, and the 3rem-square
      icon cell in it (a button with `onClick`, otherwise a labelled icon); how a new row of the bar is made.
- [ ] **`NavRowButton`** (primitive): the bar's text button, a link with `href` or else a button; `inRow` inside a
      `NavRow`, `indent` steps the text in (0.75rem each) without narrowing the button. Used for log in/out, the
      languages and the Entity/Document types; a link closes the bar (`setNavExpanded(false)`), which stays closed until the pointer leaves and returns.
- [ ] **Entities and Documents in the bar** (`NavModelList`, `modelHierarchy` in `schema`): shown only when expanded;
      each type links to `/<Type>`; ordered by the type hierarchy (siblings alphabetical), indented 0.75rem per level;
      abstract types are included (their list page shows their subtypes). A type whose parent is of another kind is top level.
- [ ] **`For` in Solid 2.0**: the item is a plain value, the index the accessor (the reverse of 1.x).
- [ ] **The console** (`ConsoleBar`, `Console`, `ConsoleMountProvider`): the bar fixed along the top (beside the nav bar,
      the page needs `pt-12`; 3rem high, 5rem in from each side of the page (`left-32`, `right-20`: the nav bar is 3rem), translucent slate-200 with a blur); each page renders `<Console type list? label?>…actions…</Console>` anywhere in its markup,
      and a `Portal` puts it in the bar. Left: the type (plural for a list), the label of an item; right: the `children`.
      Portals are client-only: the console appears after hydration. The bar is hidden (transparent, not clickable, `aria-hidden`) unless a page has a `Console` (each registers with `onSettled`, counted in `ConsoleMountProvider`), and slides in from the top (300ms, with a fade) when one does; the server always renders it hidden. The plural is a stand-in until translations are connected.
- [ ] **Entities are blue, Documents green**: the theme (tint `bg-sky-400/25`, `text-sky-950`) starts with the type in the console, which fills the height of
      the bar; `tintOf` in `Console.tsx` picks it by the kind of the model. Documents are green (`bg-green-400/25`, `text-green-950`). To be used across the interface.
- [ ] **`ConsoleButton`** (primitive, configurable; separate from `NavIconCell` on purpose): the button for the right of the console,
      as high as the bar, with a rule on its left. Props: the icon (children), `label` (screen reader, tooltip, and the text
      with `text`), `tone` (`neutral`, `entity`, `document`, `danger`), `disabled`, `pressed` (a toggle), and `href` (a link) or `onClick`. A square
      unless `text`. A list's console has a *new* button (plus icon, to `/<Type>/new`) when the type is not abstract; the route
      for `/new` does not exist yet (it falls to `/:type/:id`).
- [ ] **Search in the console** (`ConsoleSearch`): a list's console has a text search in the middle (full height, at most `max-w-xl`,
      centred in what the type and the buttons leave, so not exactly the centre of the page), and at its right a *Deep search* toggle
      (`ConsoleButton` with `pressed`). Not connected: the text and the toggle are local state.
- [ ] **`Frame`** in `App.tsx`: how the bar and the page are put together.

## Development

- [ ] **Seeing changes**: `pangloss dev` and `pangloss interface dev --link` in `pangloss-demo`, then
      `http://localhost:3000` (`localhost`, not `127.0.0.1`).
- [ ] **The demo's copy** in `.pangloss/interface` is overwritten by every command, and stale until rebuilt.

## Data fetching

- [ ] **Reads** (`interface-core/src/api/fetch.ts`): `listItems`, `getItem`, `getEditView`, `autocomplete`, `searchItems`,
      `getCurrentUser` (undefined on a 401), each taking the client. `ApiClient` has `get` (with a query) and `post`; a failure
      is an `ApiError` (`status`, `detail`). Types in `api/types.ts`. **Writes (create, update, delete, undelete) are not built.**
- [ ] **Solid 2.0 way**: the app wraps them in the router's `query` (`interface-app/src/queries.ts`; cached by name and plain
      arguments) and a page reads them in an async `createMemo`, inside `<Loading>` (first load) and `<Errored>` (failures).
      There is no `createAsync`. In RC.19 the `Errored` fallback gets the error as an accessor: `(error) => … error()`.
      Read every reactive input before the first `await`.
- [ ] **On the server** the client asks the API directly (`PANGLOSS_API_URL`, as `pangloss interface dev` sets it), as the
      server cannot ask its own origin; the browser asks `/api`. Cookies are *not* forwarded yet, so a server render is
      anonymous (fine for the public lists and items; not for the edit view or `/users/me`).
- [ ] **Tests**: `api/fetch.test.ts` (a fake `fetch`: URLs, escaping, errors) and `api/fetch.live.test.ts`, which runs against
      a real API only when `PANGLOSS_LIVE_API` is set (`PANGLOSS_LIVE_API=http://127.0.0.1:8000 npm test`).
- [ ] **Abstract types have no list route** in the API (404), though the nav bar lists them.

## When they are connected up

- [ ] Sessions / the logged-in user (cookie, server-side render with the request's cookies).
- [ ] The log-in form and its place.
- [ ] Language selection, and how it reaches the translations of the models.
