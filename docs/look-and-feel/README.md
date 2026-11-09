# Look and feel review (2026-11-09)

✅ Built on branch `look-and-feel-1`, without the lighting (see [As built](#as-built) at the end). The review below is kept as written:
its "proposed" screenshots are real pages with CSS (and, for the review queue, a small DOM change) injected by
Playwright, mock-ups made before anything was built; the rules in [`experiment/`](experiment/) pick elements by
their Tailwind class strings, fine for a screenshot and not how it was built.

All screenshots are at 2× (retina), taken from a scratch project with the demo's models and `populate.py` data
(the demo database was not touched).

Folders:

- [`buttons/`](buttons/): one crop of each distinct button style found on real pages (48 distinct class strings,
  377 buttons, not counting the navigation bar and the console), named `<family>-<where>.png`;
  `_all-buttons.png` is the labelled contact sheet; `_proposed-system.png` the proposal.
- [`chips/`](chips/): chips and badges as they are now; `_all-chips.png` is the sheet.
- [`screenshots/`](screenshots/): whole pages, `-before` and the proposals (`-outline`, `-gradient`, `-full`).
- [`experiment/`](experiment/): the injected CSS (`light.css`, `buttons.css`, `tables.css`).

---

## 1. Buttons

### What there is

![Every button style, grouped](buttons/_all-buttons.png)

There is no button component in use. `primitives/Button.tsx` exists, with a `pg-button` class that no CSS defines;
only `EntityCard` uses it. Instead about 130 `<button>`s set their own classes: **68 distinct class strings** in the
source. Shared constants (`smallButtonClass`, `addSlotClass`, `headButtonClass`, …) cover the form; each module
writes its own.

The differences that show:

| | Variants found | Where |
|---|---|---|
| **Ordinary** button background | `bg-slate-100/60` (form, `smallButtonClass`), `bg-white` (admin, users, quick search, restore dialog), `bg-slate-300/60` with no border (login) | form vs modules |
| **Ordinary** height / padding | 26 px with `px-2` or `px-3`; 36 px (`h-9`, restore dialog); 40 px full width (login) | `JobsSection` and `UsersAdminSection` each define their own `button` constant, differing only in `px-3`/`px-2` |
| **Primary** colour and size | `bg-sky-600`: 28 px (`Composer` Send), 36 px (`VersionDrawer`, `RestoreDialog`). Save in the console is green. Login has no primary at all | sky is also the colour of *entities* (`kindTint`), so a sky button reads as "a Person" |
| **Destructive** | `bg-red-100` hairline (delete, stash: same constant copied into two files); solid `bg-red-800` (search NOT when on); `text-red-800` only (✕ buttons) | `DeleteDialog.tsx:7` and `StashDialog.tsx:6` hold the same `dangerButtonClass` |
| **Dashed "add"** | 30 px full width (`addSlotClass`), 26 px (`TypeTree`), 22 px `py-0.5` (`addConditionClass`) | three heights for one idea |
| **Choosing one of several** | `rounded-full` pills (`LiteralEditor`, `SearchPanel`), the only round corners in an interface of 2 px corners; `rounded-sm border-slate-300` (`DateEditor` "unknown"); segmented tabs with `px-2` (`ReviewPanel`) and `px-4` (`ReviewQueue`); the NOT toggle | four idioms |
| **Icon-only** | 20, 24, 28, 30, 32 and 48 px squares | 28 (head bar, chip) and 48 (console, modal close) are deliberate; 20/24/32 are not |
| **Hover** | `hover:bg-slate-100`, `-200`, `-200/70`, `-300/50`, `-400/30`, `-400/40`, `brightness-90`, `brightness-95`, an inset `100vmax` shadow | nine ways to darken |
| **Disabled** | `opacity-40`, `opacity-50`, `text-slate-400`, `pointer-events-none` | |
| **Focus** | a visible focus style on about a third; none on the module buttons (`JobsSection`, `UsersAdminSection`, `ReviewQueue`, `Composer`) | keyboard users lose their place |

### Proposal: one button, five kinds, two sizes

![Proposed button system](buttons/_proposed-system.png)

- **Kinds**: *ordinary* (white, hairline), *primary* (slate-700, the colour already used for "selected" in the
  segmented tabs and pills, so it does not collide with the entity/document colours), *destructive* (the existing
  red-100), *quiet* (no frame until hovered: for rows of a table and secondary actions in panels), *add* (dashed).
- **Sizes**: `sm` 26 px (forms, tables, panels) and `md` 32 px (dialog footers, the login button). Nothing at 22, 36
  or 40.
- **Icon-only**: 28 px wide at `sm`; the 48 px console/modal size stays as the bar's own.
- **Choosing one of several**: one segmented control (the review tabs' look) for both the review tabs and the
  enum pills; drop `rounded-full`.
- **States**: one hover (a step darker), one pressed (inset shade), one focus ring (`outline-2 outline-offset-1
  outline-slate-500/60`), one disabled (`opacity-40`).
- Make `Button` the real primitive (`kind`, `size`, `icon`) and have `smallButtonClass`, `dangerButtonClass`,
  `addSlotClass` and the modules' local `button` constants use it. The console's own buttons, the head-bar segments
  and the chip segments stay as they are: they are part of a bar, not free-standing buttons.

In context (left: now, right: proposed, with the lighting of §2):

| Now | Proposed |
|---|---|
| ![](screenshots/restore-before.png) | ![](screenshots/restore-full.png) |
| ![](screenshots/delete-before.png) | ![](screenshots/delete-full.png) |
| ![](screenshots/stash-before.png) | ![](screenshots/stash-full.png) |
| ![](screenshots/login-before.png) | ![](screenshots/login-full.png) |

Restore: the drawer's "Restore to this point" (36 px, sky) and the dialog's Cancel/Restore (36 px) now match the
other dialogs' 32 px footer. Login: the grey slab becomes the primary button, the same as Restore.

---

## 2. Lighting: hairlines and very faint gradients

Everything is flat at the moment: tints, hairlines, no light. The experiment assumes **one light from above**:

- what is *raised* (buttons, chips, head bars, the console) gets a half-pixel white highlight along its top edge
  (`inset 0 .5px 0 rgb(255 255 255/.75)`) and a half-pixel shade under it (`0 .5px 1px rgb(15 23 42/.08)`);
- what is *recessed* (inputs, selects, the search box) gets the opposite: a faint inner shade at the top;
- a pressed button turns from raised to recessed;
- *gradient* variant only: a white→transparent wash over the top of tints (2–28 % white) and of the console bar,
  and a 3–7 % wash on the primary button.

A half-pixel `box-shadow` draws one device pixel on a retina screen, which a `border-[0.5px]` does not (Chrome draws
that as a full CSS pixel), so this is a way to get true hairlines of light.

Close up (4×), the edit form, *now / hairlines only / hairlines + gradient*:

![](screenshots/zoom-before.png)
![](screenshots/zoom-outline.png)
![](screenshots/zoom-gradient.png)

Whole pages:

| Now | Hairlines only | Hairlines + gradient |
|---|---|---|
| ![](screenshots/edit-before.png) | ![](screenshots/edit-outline.png) | ![](screenshots/edit-gradient.png) |
| ![](screenshots/item-before.png) | ![](screenshots/item-outline.png) | ![](screenshots/item-gradient.png) |
| ![](screenshots/search-before.png) | ![](screenshots/search-outline.png) | ![](screenshots/search-gradient.png) |

My view: **hairlines + gradient**, at these strengths. At normal size it is barely noticeable, as intended: chips
and head bars read as things you can pick up, inputs as places to type into, and the console sits slightly above
the page. Stronger than this (I tried 14 %/5 % on the primary button first) starts to look like 2010 and was
toned down. Two cautions:

- The well shadow must be limited to framed inputs: applied to every `input`, it showed the borderless in-place
  inputs of the users table and the edit page's title.
- Chips in tinted semantic spaces (the yellow *Hypothetical* band) keep their highlight; check it on every space
  colour before adopting.

How to build it: two or three theme values in `styles.css` (`--shadow-raised`, `--shadow-well`,
`--bg-image-sheen`) used as Tailwind utilities (`shadow-raised`, `bg-sheen`) in `typeChipClass`, `headBarClass`,
the chip frame, `inputClass` and the new `Button`.

---

## 3. Tables, and chips inside them

### What there is

![Chips and badges now](chips/_all-chips.png)

Seven places show rows of things, and each draws them differently:

| Page | Row | The item in it |
|---|---|---|
| List page (`/Person`) | 46 px, each row a full-width chip, 8 px apart, indented 24 px from the console | a giant chip (`px-4 py-3`) |
| Review queue | `<table>`, `py-2`, `border-slate-300` rule | **not a ReferenceChip**: a hand-made 0.65rem type pill, unframed, and the label as plain link text. This breaks the "always a chip" rule |
| Users (admin) | `<table>`, `py-1.5`, five framed buttons in every row | username as plain link; status as a square `ADMIN` badge with no radius |
| Jobs (admin) | `<table>`, `py-2` | |
| Years (calendar) | `<table>`, `py-1.5` and `pr-4` (the others `pr-3`) | a round count badge and a word |
| History compare | a CSS grid with `role="table"`, `gap-x-3`, so each column is a separate box with gaps between | ReferenceChips (fine) |
| `/users` | `<div>` rows with `px-1` inset, so the names do not line up with the heading | |

The table heads match (copied between files: `border-b-[0.5px] border-slate-400/70 text-xs font-semibold
text-slate-500 uppercase`); the bodies do not. Status badges have five looks (`ADMIN`, `v1`, `CURRENT`, the
count circle, the amber comment count).

### Proposal

- **One table style** (a `DataTable` or a set of class constants beside the form's): header as now; rows 7 px top
  and bottom, a `slate-500/28` hairline, a faint hover, `pr-3.5` cells, middle-aligned.
- **An item in a table is a ReferenceChip**, at its normal size, never a pill. The review queue's status flag
  stays to the left of the chip.
- **Row actions are quiet buttons**: the five framed buttons in each users row become frameless until hovered.
  (Further: put the rarer ones, *End sessions* and *Tokens*, under a ⋯ menu.)
- **One badge**: `rounded-xs px-1.5 py-px text-xs font-semibold uppercase` in a tint, for ADMIN, CURRENT and the
  version numbers.
- **List page rows**: the same chip, at `px-2.5 py-1.5` instead of `px-4 py-3`, so a list of 2000 people is not a
  wall of tiles. (The rows are virtualised with a fixed pitch, so the gap stays until `VirtualRows`' estimate
  changes too.)
- **History compare**: no gap between columns, so it reads as one table.

| Now | Proposed |
|---|---|
| ![](screenshots/review-before.png) | ![](screenshots/review-full.png) |
| ![](screenshots/admin-before.png) | ![](screenshots/admin-full.png) |
| ![](screenshots/list-before.png) | ![](screenshots/list-full.png) |
| ![](screenshots/compare-before.png) | ![](screenshots/compare-full.png) |
| ![](screenshots/years-before.png) | ![](screenshots/years-full.png) |
| ![](screenshots/users-before.png) | ![](screenshots/users-full.png) |

(The years table shows 0 events because the scratch project counted no date fields; that is not a fault of the
page.)

---

## 4. Smaller things noticed on the way

- The history page's H1 has no rule under it; every other page's does.
- The list page indents its rows 24 px from the console's left edge; tables and forms start at the edge.
- The users admin table squeezes the email column at 1100 px wide (the button wall takes the room); quiet buttons
  or a ⋯ menu fix this too.
- The review queue's FACTOID pill passes `"Document"` to `kindTint` (`ReviewQueue.tsx:80`); with a chip that call
  goes away.

## Decisions (2026-11-09)

The user asked for the suggestions here to be implemented (branch `look-and-feel-1`), which settles:

1. The primary colour is **slate-700**, not sky.
2. Lighting: **hairlines + gradient**, at the strengths above. *Reversed once built and seen*: all the lighting
   (sheens, half-pixel highlights and shades) was taken out again; buttons, chips and bars are flat. A further
   try without the outer hairlines of chips (`no-outline/`) was not liked either.
3. Users get **no chip of their own** for now (not proposed; a username stays plain text or a link).
4. **`Button` is built** as the shared primitive, with the class function behind it shared too.

## As built

On branch `look-and-feel-1`, in Tailwind utilities, not the experiment's CSS. **No lighting**: it was built, looked
at, and taken out (see Decisions); what is below is flat.

- **`primitives/buttonClass.ts`**: `buttonClass(kind, size, icon)` (ordinary, primary, danger, quiet, add; `sm` 26px,
  `md` 32px), `segmentedClass` / `segmentClass(chosen, content)`, `badgeClass`, `numberBadgeClass`, and
  `barButtonClass` / `barIconButtonClass` for a button that is part of a bar. `Button` draws `buttonClass` (`kind`,
  `size`, `icon`, `label`). `smallButtonClass` and `addSlotClass` are `buttonClass("ordinary")` and
  `buttonClass("add")`; the modules' own button constants are gone. Hover and press apply only to a button that is
  not disabled, so a disabled one keeps its tooltip.
- **Close buttons are as tall as their bar**, with a hairline on their left, as the console's are: the history
  panel (and its Compare all), the version drawer, the review panel and every dialog (`barIconButtonClass`).
- **The footer of every dialog is `md`** (32px): delete, stash, retype, restore, the users' dialogs, Zotero's unlink.
- **`primitives/tableClass.ts`**: `tableClass`, `tableHeadRowClass`, `tableHeadCellClass`, `tableRowClass`,
  `tableCellClass`, used by the jobs, users, review queue and years tables.
- Primary actions are slate-700: Send, Restore, Restore to this point, Stash, the dialogs' submit, Log in (now 32px).
  Delete, Leave without saving and Unlink are `danger`; "and N more", pagination and the actions in the users and
  jobs rows are `quiet`; the add buttons of the form, the search panel and the typology are `add` at 26px.
- Enum values (`LiteralEditor`, the search panel's choices) and the date editor's "not known" are segments, not
  round pills.
- The review queue shows each document as a `ReferenceChip`.
- A subdocument's head bar that is a link darkens on hover as a chip that is a link does (`headBarLinkClass`).
- List page rows are `px-2.5 py-1.5` (34px at one pixel to the pixel; `ROW_HEIGHT` in `List.tsx` follows).
- The history page's heading has the rule the other pages have; its compare grid has no gaps between columns;
  its version and "current" labels are badges.
- `/users` rows line up with the heading.

Not done: the ⋯ menu for the rarer actions in a users row.

| Edit form | Review queue | Users admin |
|---|---|---|
| ![](built/edit.png) | ![](built/review.png) | ![](built/admin.png) |
| **List** | **Restore dialog** | **Choosing a type** |
| ![](built/list.png) | ![](built/restore.png) | ![](built/add_menu.png) |
| **Review panel** | **History panel** | **Delete dialog** |
| ![](built/review_panel.png) | ![](built/history_panel.png) | ![](built/delete.png) |
| **History compare** | | |
| ![](built/compare.png) | | |
