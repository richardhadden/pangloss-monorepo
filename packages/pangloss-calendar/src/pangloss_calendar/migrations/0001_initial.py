"""0001_initial

The structure of the calendar graph: an index and a unique key for days, months, years and observances.
Written by hand (the calendar has no models); the nodes are made by `pangloss calendar seed`.
"""

from pangloss_models.migrations.files import changes_from_data

dependencies = []

changes = changes_from_data(
    [
        {
            "change": "AddIndex",
            "safety": "safe",
            "index": {
                "kind": "label+property",
                "label": "CalendarDay",
                "properties": ["jdn"],
            },
        },
        {
            "change": "AddIndex",
            "safety": "safe",
            "index": {
                "kind": "label+property",
                "label": "CalendarMonth",
                "properties": ["calendar", "year", "month"],
            },
        },
        {
            "change": "AddIndex",
            "safety": "safe",
            "index": {
                "kind": "label+property",
                "label": "CalendarYear",
                "properties": ["calendar", "year"],
            },
        },
        {
            "change": "AddIndex",
            "safety": "safe",
            "index": {
                "kind": "label+property",
                "label": "CalendarObservance",
                "properties": ["key"],
            },
        },
        {
            "change": "AddConstraint",
            "safety": "additive",
            "constraint": {
                "kind": "unique",
                "label": "CalendarDay",
                "properties": ["jdn"],
            },
        },
        {
            "change": "AddConstraint",
            "safety": "additive",
            "constraint": {
                "kind": "unique",
                "label": "CalendarMonth",
                "properties": ["calendar", "year", "month"],
            },
        },
        {
            "change": "AddConstraint",
            "safety": "additive",
            "constraint": {
                "kind": "unique",
                "label": "CalendarYear",
                "properties": ["calendar", "year"],
            },
        },
        {
            "change": "AddConstraint",
            "safety": "additive",
            "constraint": {
                "kind": "unique",
                "label": "CalendarObservance",
                "properties": ["key"],
            },
        },
    ]
)
