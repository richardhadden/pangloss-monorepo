# Look and feel ✅

How buttons, tables, badges and chips look in the interface, and why. It comes from a review of 2026-11-09 (branch
`look-and-feel-1`) that counted what there was, proposed one system, and built it. The review's screenshots and its
trial CSS are not kept; they are in the history of the repository (`docs/look-and-feel/`, before 2026-11-10).

## The rules

- **The look is flat.** Tints and hairlines; no gradients, highlights or shadows of light.
- **One button**: `buttonClass(kind, size, icon)` in `primitives/buttonClass.ts`, drawn by `Button`.
  - Kinds: *ordinary* (white, hairline), *primary* (slate-700), *danger* (red-100), *quiet* (no frame until
    hovered: rows of a table, secondary actions in panels), *add* (dashed).
  - Sizes: `sm` 26 px (forms, tables, panels) and `md` 32 px (the footer of every dialog, Log in). An icon-only
    button is 28 px wide at `sm`.
  - One hover (a step darker), one pressed, one focus ring, one disabled (`opacity-40`). Hover and press apply only
    to a button that is not disabled, so a disabled one keeps its tooltip.
- **The primary colour is slate-700, not sky**: sky is the colour of entities, so a sky button reads as "a Person".
- **A button that is part of a bar is the bar's own** (`barButtonClass`, `barIconButtonClass`): the console, head
  bars, chip segments. A close button is as tall as its bar, with a hairline on its left.
- **Choosing one of several is a segmented control** (`segmentedClass`, `segmentClass(chosen, content)`): review
  tabs, enum values, the search panel's choices, the date editor's "not known". No round pills.
- **One table** (`primitives/tableClass.ts`: `tableClass`, `tableHeadRowClass`, `tableHeadCellClass`,
  `tableRowClass`, `tableCellClass`): jobs, users, the review queue, the calendar's years.
- **An item in a table is a `ReferenceChip`**, at its normal size, as everywhere else.
- **One badge** (`badgeClass`; `numberBadgeClass` for a count): ADMIN, CURRENT, version numbers.
- **Users have no chip of their own**: a username is plain text or a link.
- List page rows are `px-2.5 py-1.5` (34 px; `ROW_HEIGHT` in `List.tsx` follows, since the rows are virtualised
  with a fixed pitch).

## What the review found

There was no button component in use: about 130 `<button>`s set their own classes, in 68 distinct class strings,
with nine ways to darken on hover, four of disabling, six icon sizes, and a focus style on about a third. Seven
pages drew rows of things seven ways; the review queue drew a document as a hand-made pill, not a chip. Status badges
had five looks.

## What was tried and taken out

Do not propose these again without a new reason:

- **Lighting.** One light from above: a half-pixel white highlight along the top of what is raised (buttons, chips,
  head bars, the console) and a shade beneath, the opposite for inputs, and a faint white wash over tints. It was
  built, looked at, and taken out.
- **Chips without their outer hairline.** Tried after the lighting; not liked either.

A fact found on the way that is still useful: a half-pixel `box-shadow` draws one device pixel on a retina screen,
which `border-[0.5px]` does not (Chrome draws that as a full CSS pixel).

## Not done

- A ⋯ menu for the rarer actions in a row of the users table (*End sessions*, *Tokens*).
