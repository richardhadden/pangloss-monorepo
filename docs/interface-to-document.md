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
- [ ] **`STRICT_READ_UNTRACKED`** (Solid 2.0 dev warning): a reactive value read in a component body is read once. For a deliberate snapshot (the starting value of a signal that then follows its own course, as in `ConsoleSearch`) say so with `untrack(() => props.x)`; otherwise read it in JSX, a memo or an effect's compute function. **No ternaries (or `&&`) to choose what is shown in JSX**: use `<Show when={…} fallback={…}>` (a component that returns `props.x ? <a/> : <b/>` reads `props.x` once, and Solid cannot track a choice made that way). Conditional classes use the **object form** (`class={["static classes", { "w-72": open(), "w-12": !open() }]}`), not a ternary or a template string: Solid then toggles only the tokens that change. One class per key. Ternaries stay for plain attribute values (`aria-expanded`, a label prop). The same goes for reading a signal in the *apply* function of `createEffect` (`untrack` it, or read it in the compute function).
- [ ] **`For` in Solid 2.0**: the item is a plain value, the index the accessor (the reverse of 1.x).
- [ ] **The console** (`ConsoleBar`, `Console`, `ConsoleMountProvider`): the bar fixed along the top (beside the nav bar,
      the page needs `pt-12`; 3rem high, 5rem in from each side of the page (`left-32`, `right-20`: the nav bar is 3rem), translucent slate-200 with a blur); each page renders `<Console type list? label?>…actions…</Console>` anywhere in its markup,
      and a `Portal` puts it in the bar. Left: the type (plural for a list), the label of an item; right: the `children`.
      Portals are client-only: the console appears after hydration. The bar is hidden (transparent, not clickable, `aria-hidden`) unless a page has a `Console` (each registers with `onSettled`, counted in `ConsoleMountProvider`), and slides in from the top (300ms, with a fade) when one does; the server always renders it hidden. The plural is a stand-in until translations are connected.
- [ ] **Entities are blue, Documents green**: the theme (tint `bg-sky-400/25`, `text-sky-950`) starts with the type in the console, which fills the height of
      the bar; `kindTint` picks it by the kind of the model. Documents are green (`bg-green-400/25`, `text-green-950`). To be used across the interface.
- [ ] **`ConsoleButton`** (primitive, configurable; separate from `NavIconCell` on purpose): the button for the right of the console,
      as high as the bar, with a rule on its left. Props: the icon (children), `label` (screen reader, tooltip, and the text
      with `text`), `tone` (`neutral`, `entity`, `document`, `danger`), `disabled`, `pressed` (a toggle), and `href` (a link) or `onClick`. A square
      unless `text`. A list's console has a *new* button (plus icon, to `/<Type>/new`) when the type is not abstract; the route
      for `/new` does not exist yet (it falls to `/:type/:id`).
- [ ] **Search in the console** (`ConsoleSearch`): a list's console has a text search in the middle (full height, at most `max-w-xl`,
      centred in what the type and the buttons leave, so not exactly the centre of the page), and at its right a *Deep search* toggle
      (`ConsoleButton` with `pressed`). It does not search: it shows `query`/`deep` and says what changed (`onQuery`, 250ms after the last key; `onDeep`). The list page keeps them in the address with `useSearchParams` (`?q=rome&deep=1`; an empty `q` or a null `deep` removes the parameter), writing with `replace: true` so a search is not a history entry per key, and its `createMemo` of `listQuery` runs again when they change. The input follows the address if it changes otherwise (back, a link). `count` (how many were found) is shown beside the input, small, and dark red when 0; it is passed as a getter that waits for the result, so `ConsoleSearch` gives it a `Loading` and an `Errored` of its own, or the whole page would wait with it.
- [ ] **Results of a list** (`ResultButton`, overridable): a full-width light-slate button per item, its own type on the left (only as wide as the type,
- [ ] **Semantic spaces in a list**: an item whose `meta.contextLabels` has spaces (`Negative`, `Hypothetical`...) is wrapped in a band for each, outermost first, the names side by side on the left; the colour is the model's own (`_interface_meta = InterfaceMeta(colour="rose")`, see [meta-slots.md](meta-slots.md)), or by depth (amber, violet, rose, teal, then again) if it has none. The type block of a result and of the console takes the model's colour too (else blue for an Entity, green for a Document). Documents outside a space (`#rootcontext`: "did happen") are not wrapped. `#rootcontext` entries (documents outside a space) make no band (`wrappingSpaces`). The names are the project's model names (see `interface-strings.md`). The list route had been reading `semantic_spaces`/`context_labels` from the wrong place, so they were always empty. On the page of one item, the console wraps the type in the same bands (outermost first, each inset by a little padding; same colours, `spaceTint`). On the page of one item, the console shows the same spaces as full-height cells before the type (outermost first; same colours, `spaceTint`).
- [ ] **Head node button**: a result that is inside another document (`meta.isHeadNode` false, with `headNodeType` and `headNodeId`) has a square button with a layers icon (its context) at the far left of the row, joined to the bar but not wrapped by the bands, to that document. Head nodes and entities have none, so the left edges of a list are not all alike. (The list query had left the head node out of the meta of its items.)
- [ ] **Contents of an item** (`ItemContents`, overridable; `ReferenceChip`, overridable): the fields of the model in its order, in a grid of a key column (10rem, chrome text) on the left and the contents on the right; a field with nothing in it is left out. A **list** stacks its values. An **Entity** is a chip (type, tinted blue or by its model's colour, on the left; label on the right; a link; the edge properties after it as small pills (a stand-in: `level 5`; to be thought about)). An **embedded** object is only its rows, indented (it is in one place only: no box, no type). A **Document inside**, a **reified relation**, an **annotated value** and (for now) a **conjunction** are a bordered block: type (and label) at the head, then its own rows, to any depth. A **semantic space** is a band (the colour of its model, else by depth) with its name at the left and what is in it inside, nested spaces one depth further. What refers to an item from elsewhere (`incoming`) follows its fields, as chips. **Not done**: the layout of conjunctions (`Causes` is a plain block with `cause` and `result` for now), the dates and numbers formatted by language, the names of fields from the models' translations, empty fields hidden by choice, a link in the head of a nested document to its own page, pagination of long incoming lists.
      tinted by kind with `kindTint`) and its label. The list page is `max-w-[100rem]` (1600px), centred, with `px-6 py-6` margins.
      `kindTint` (primitives) is the one place the Entity blue / Document green theme is defined.
- [ ] **Deep search is run on request**: it is slow (43 to 48 s on 642k nodes; see `TODO.md`). Typing makes an ordinary search after 250ms, or at once on Enter. Turning *Deep search* on makes none: the run button (play icon, disabled when what is typed is what is shown) and Enter do. `ConsoleSearch` has the toggle's state itself (`deepOn`) and follows `deep` of the address when that changes; `onSearch({ query, deep })` is the one callback.
- [ ] **Pending**: while a new search is answered, Solid 2.0 keeps the old results on screen. The list page uses `isPending(items)` to dim
      the list (`opacity-50`) and passes `pending` to the console, which shows a `Spinner` (primitive) in place of the count; the count also
      has the spinner as its first-load fallback.
- [ ] **`Frame`** in `App.tsx`: how the bar and the page are put together.

## Development

- [ ] **Seeing changes**: `pangloss dev` and `pangloss interface dev --link` in `pangloss-demo`, then
      `http://localhost:3000` (`localhost`, not `127.0.0.1`).
- [ ] **The demo's copy** in `.pangloss/interface` is overwritten by every command, and stale until rebuilt.

- [ ] **Hard-coded strings**: every fixed text of the interface is listed in [interface-strings.md](interface-strings.md), for the translations. Add to it with each string written.

## Sessions and logging in

- [ ] **The API's cookie session is used as it is** (`POST/DELETE /api/users/session`, `POST /session/refresh`, `GET /users/me`: docs/api.md); the
      interface needed no routes of its own. The cookies (`pangloss_access` 30 min, `pangloss_refresh` 14 days) are HTTP-only, so the page
      cannot read them: it asks `/users/me`. They pass through the Vite proxy and a reverse proxy alike, being on the interface's origin.
- [ ] **`logIn`, `logOut`, `getCurrentUser`** (`interface-core/src/api/fetch.ts`); `getCurrentUser` with `refresh: true` (the browser) asks for a new
      access cookie on a 401 and tries again; the server does not (it cannot give the browser the cookie). `ApiClient` has `postForm`
      (logging in is an OAuth2 form, not JSON) and `delete`.
- [ ] **On the server**, `apiClient()` (`interface-app/src/api.ts`) makes a client for the request being rendered, passing on its `Cookie` header, so the
      page is rendered for the user. It must be called when the request is made, not at the top of a module. `getRequestEvent()` from `@solidjs/web`.
- [ ] **State**: `sessionQuery` (a router `query`, key `session`), read in an async memo in `Frame` with `{ deferStream: true }` (the server holds back
      the first part of the page, so the bar is not sent "not logged in" and then changed); `revalidate(sessionQuery.key)` after logging in or out.
- [ ] **The log in dialog** (replaces the `/login` page): the nav bar's *Log in* calls `openLogin()` (`useLoginDialog`, from `LoginDialogProvider`; anything can open
      it); `LoginDialog` (app) shows a `Modal` with the `LoginForm`, over the page it was opened on, and on success `revalidate`s the session and closes.
- [ ] **`Modal`** (primitive, overridable): a `Portal` on the body; the backdrop (`fixed inset-0 z-50`, dark and blurred) covers the page, so nothing behind it can be
      clicked; a click on the backdrop does *not* close it (typing is not lost); **Escape** and the close button call `onClose`; Tab goes round inside it; the focus
      goes in (`autofocus`, or the first control) and back to what had it; the page behind does not scroll. A portal is client-only: show it only after a click.
- [ ] **`userIsLoggedIn()`** and **`useCurrentUser()`** (`SessionProvider`, given the user by the app): for deciding what to show, such as
      `<Show when={userIsLoggedIn()}>`. For display only: the API refuses what needs a login anyway. Reading the user may wait, so read it inside a `<Loading>`
      (the console's *new* button has one). Used so far: the console's *new* button (only for someone logged in).
- [ ] **Tests of components** run in a DOM: a `*.test.tsx` file starts `// @vitest-environment happy-dom` and renders with `render` from `@solidjs/web` (`vitest.config.ts` gives Solid its browser build). Done for `Modal`, `LoginForm`, the session helper and the console's new button.
- [ ] **`RequireLogin`** (component): wrap a page (or part of one) that needs a login. No one logged in: none of it is shown, and the log in dialog opens over the page (`openLogin(onCancel)`); logging in shows it; giving up (Escape, the close button: `cancelLogin()`) calls `onCancel`, which goes home (`navigate("/", { replace: true })`, so Back does not return to the page). Logging out while on the page asks again; leaving the page closes the dialog. The server renders none of the page for an anonymous visitor (and the dialog appears after hydration). Reads the user, so it needs a `<Loading>` above (the frame has one). First used by `/:type/new` (a placeholder with only the console; the form is not built), which the console's *new* button links to.
- [ ] **Not done**: a 401 status for a restricted page rendered on the server (it is a 200 with nothing in it), what a 401 in the middle of a session shows, CSRF (only `SameSite` protects the cookies),
      `AUTH_COOKIE_SECURE` for HTTPS, a form with `formAction` (the login uses a plain handler), and the old stubs `POST/GET/DELETE /api/interface/session` (501) in
      `pangloss-interface`'s `api.py`, which this makes unnecessary.

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
- [ ] **Abstract types** now have the read routes (list, get) in the API, so their nav links work; the list of an abstract type holds the items of its subtypes.

## When they are connected up

- [ ] Sessions / the logged-in user (cookie, server-side render with the request's cookies).
- [ ] The log-in form and its place.
- [ ] Language selection, and how it reaches the translations of the models.
