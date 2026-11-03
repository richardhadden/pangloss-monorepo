# Vertical rhythm review, 2026-11-03

Pages looked at (1400 px wide, demo models and `populate.py` data, scratch stack): home, Person list,
Person view/edit/new (Charlemagne), Factoid list/view/edit/new ("Charlemagne is crowned emperor").
Gaps measured from screenshots and, where it mattered, from the DOM (`getBoundingClientRect`).

The base rhythm is sound: a field row is `pt-5` under a faint rule, nested blocks `gap-5`, items in a
row `gap-y-4` (`gap-y-6` in rows of what refers to the item). Labels line up with their first value.
What is off is where one of these meets another.

## Findings

1. **An opened block has more room below it than above (view).** The wrapper of an expanded
   relation/document in a row has `mb-4 last:mb-0` (`ItemContents.tsx:315`, `:409`) *on top of* the
   row's `gap-y-*`. Person view, ORDERED: chip → opened Order 24 px; opened Order → next chip 40 px.
   In ordinary rows it is 16 above / 32 below. Same after "Leo crowns Charlemagne" before the
   Hypothetical space. This is the most visible one: the block looks attached to the chip above it.

2. **The date editor's rows go unruled, ruled, unruled (edit).** The date inputs and CALENDAR have
   no rule between them (Calendar is the first row of the editor's `ModelFields`, so
   `first:border-t-0`), SOURCE TEXT and SORT BY have rules, then READS sits under Sort by with no rule
   and less room (`DateEditor.tsx:135`). It is repeated for every date on a factoid, so the edit page
   has a stutter every screen or so.

3. **The search box under a list of blocks is closer than the blocks are to each other (edit).**
   Factoid edit, PARTICIPANTS: In role → In role 24 px (`gap-y-6`), last In role → "Find Group,
   Person…" 16 px (`gap-4` of the field, `ModelFields.tsx:640`). The box reads as part of the last
   block, not the field. With chips (Has type, Places) 16 px looks right.

4. **Rows of what refers to the item are taller (view).** `pt-7` instead of `pt-5` (`ItemContents.tsx:58`),
   deliberate (they are centred and some chips are in spaces), but on a Person page the switch from
   its own fields (rule → content 21 px) to CARRIED OUT, GAVE, ORDERED… (29 px) is a step change
   halfway down. Possibly the "a little off" feeling on view pages.

5. Minor: in a view, nested sub-fields of a value (Known as → Certainty) are 8 px apart (`gap-2`) while
   the items of a list (Aliases) are 16 px; both read as "lines of one field", and the difference
   shows when they are a row apart.

Not problems: head bar → title → rule → first row; space boxes (label/content/bottom padding balance);
list page rows (8 px gaps, 33 px below the bar); new page.

## Suggested small changes

1. Drop `mb-4 … last:mb-0` from the two wrappers; let the row's gap space blocks evenly (24 px
   incoming, 16 px otherwise). If blocks want more air, raise the row gap when it has a block, both sides.
2. Move READS up, straight under the date inputs (it reads them back), so what follows is Calendar,
   Source text, Sort by, with rules between each (give Calendar a rule too, i.e. not `first:`).
3. Field `gap-4` → `gap-6` when the list holds blocks (not chips), matching the gap between them.
4. `pt-7` → `pt-6` for incoming rows, or the same `pt-5` and keep the more room *between* their items.
5. Leave, or `gap-2` → `gap-3` for nested sub-fields in a view.
