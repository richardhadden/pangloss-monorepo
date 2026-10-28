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

- [ ] **`NavBar`** (`interface-core/src/components/NavBar.tsx`): fixed, full height, 2.5rem wide retracted, overlays the
      page when expanded; the content scrolls inside it; the page needs `pl-12`. Overridable (`ComponentMap`).
- [ ] **`NavBarProps`**: `user`, `onLogin`, `onLogout`, `language`, `onLanguage`; `children` are the expanded content.
- [ ] **Icons** (SVGs, emoji, icon cells) always have `select-none`.
- [ ] **Chrome text** (everything that is not content: the bar, and later headers, buttons, labels) is `uppercase font-semibold`;
      on the bar it is set once on the `<nav>` and inherited (buttons too: `styles.css` undoes the reset that stops them). Content is not.
- [ ] **Top row of the bar**: the Home link (`homeHref`, expanded only) on the left and the hamburger on the right, which
      turns 90° (animated) while the bar is expanded. `NavRow` has `ruled={false}` for the first row.
- [ ] **Expanding**: on hover of any of the bar, or the toggle button (for touch).
- [ ] **`useNavExpanded` / `NavExpandedProvider`**: the shared signal, so anything can close the bar
      (`setNavExpanded(false)`); a context, not a module signal, so server renders do not share it.
- [ ] **Login status row**: the icon (✕ not logged in, ✓ logged in) and the log in / log out button.
- [ ] **Language row**: the flag of the selected language (emoji for now: `en` → 🇬🇧, `de` → 🇦🇹) and, expanded,
      the other languages.
- [ ] **`NavRow` and `NavIconCell`** (primitives, not in the component map): a 2.5rem-high row of the bar, and the 2.5rem-square
      icon cell in it (a button with `onClick`, otherwise a labelled icon); how a new row of the bar is made.
- [ ] **`NavRowButton`** (primitive): the bar's text button, a link with `href` or else a button; `inRow` inside a
      `NavRow`, `indent` steps the text in (0.75rem each) without narrowing the button. Used for log in/out, the
      languages and the Entity/Document types; a link closes the bar (`setNavExpanded(false)`), which stays closed until the pointer leaves and returns.
- [ ] **Entities and Documents in the bar** (`NavModelList`, `modelHierarchy` in `schema`): shown only when expanded;
      each type links to `/<Type>`; ordered by the type hierarchy (siblings alphabetical), indented 0.75rem per level;
      abstract types are included (their list page shows their subtypes). A type whose parent is of another kind is top level.
- [ ] **`For` in Solid 2.0**: the item is a plain value, the index the accessor (the reverse of 1.x).
- [ ] **`Frame`** in `App.tsx`: how the bar and the page are put together.

## Development

- [ ] **Seeing changes**: `pangloss dev` and `pangloss interface dev --link` in `pangloss-demo`, then
      `http://localhost:3000` (`localhost`, not `127.0.0.1`).
- [ ] **The demo's copy** in `.pangloss/interface` is overwritten by every command, and stale until rebuilt.

## When they are connected up

- [ ] Sessions / the logged-in user (cookie, server-side render with the request's cookies).
- [ ] The log-in form and its place.
- [ ] Language selection, and how it reaches the translations of the models.
