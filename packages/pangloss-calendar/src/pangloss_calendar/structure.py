"""The indexes and unique keys of the calendar's own nodes (not models): read by the database package, which puts them in
the snapshot that migrations are made from, so that `makemigrations` knows `migrations/0001_initial.py` makes them."""

INDEXES = [
    {"kind": "label+property", "label": "CalendarDay", "properties": ["jdn"]},
    {
        "kind": "label+property",
        "label": "CalendarMonth",
        "properties": ["calendar", "year", "month"],
    },
    {
        "kind": "label+property",
        "label": "CalendarYear",
        "properties": ["calendar", "year"],
    },
    {
        "kind": "label+property",
        "label": "CalendarSpan",
        "properties": ["first_jdn", "last_jdn"],
    },
]

CONSTRAINTS = [
    {"kind": "unique", "label": entry["label"], "properties": entry["properties"]}
    for entry in INDEXES
]
