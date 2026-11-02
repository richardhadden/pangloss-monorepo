[x] Should show full trail of semantic spaces, and additional nesting ($rootcontext + order should show Order, then group next item etc, fully wrapped)
[x] ReifiedRelations do not need the field name "Target" — just show the content full width
[x] Viewing reverse through reified relation should show the whole field in the context of the document. At the moment it just has a type and ID.
[x] when viewing a document, the semantic space type in its wrapper is on the left. This eats up Y-axis screen real estate. Put the type at the top
[x] when viewing dates, we don't need the full:

Calendar
    julian
Precision
    range
Earliest fuzzy
    1994996
Earliest strict
    1994996
Latest strict
    1998647
Latest fuzzy
    1998647
Sort day
    1994996
End sort day
    1994996
EDTF
    075X

Just human readable date / range


[x] add created_by/when modified_by/when to the console. Put it to the right, in two rows, quite light slate font


[x] In console, replace the words created and modified with icons
[x] The date forms should not show the earliest/latest strict/fuzzy. These are not to be manually entered. Make nice components for Dates and put the in the dating package
[x] In the console, when the type is wrapped by semantic spaces, make the font of the semantic spaces smaller
[x] Make date typing fields (especially EDTF) reject wrong characters
[x] up and down buttons on number fields are ugly -- fix them properly to the right side of the input and style properly
[x] let's have some notifcation when creating/saving was successful (toast in bottom right?)
[x] in the nav bar, above all the item types, create a search box that filters the types — by any label language, matching any part of token. Should also have a clear search button
[x] Reverse view from entity, e.g. http://localhost:3000/Person/01a18ca9-703f-7157-9205-0b98ab6f4e56 Items in the same field should be centered vertically (they can be different heights as some are wrapped)
[x] More y height spacing between items in reverse relations from entity (screen shot it and take a look... a little too dense and confusing)
[x] where we have nested context labels in chips, make the context labels smaller font, and maybe slightly mute the background colour of the context labels
[x] Typology types are displayed differently in view and edit. Make them chips, like edit
[x] don't use dropdowns for enums, use selectable pills -- unless the options are a huge number (I assume date gregorian and julian are enum?)
[x] when adding an item to a list field (on clicking add), add a small flash or something (slightly thicker border/some shadow that fades out) around the newly created input (hard to see what's happened otherwise); and auto-focus the field
[ ] AnnotatedValue does not need to show the key "value", just the field
[ ] the "add statement" dropdown is ugly as hell. Maybe don't make it a dropdown, but make it a whole "Select a type" box, which is open if there is the possibility of adding another thing in this field. Make the types into proper buttons, not just text; and don't use "plain" (that was just my way of describing it)
[ ] in general, when adding something (a new statement for example), make it flash slightly so it's more obvious what's happened (same with pasting)
