"""0002_rename_daterange_ends

Written by hand (the planner, seeing new types as well as new names, would have removed the old ends and their data):
the ends of a `DateRange` are `not_before` and `not_after` (the names of the Text Encoding Initiative), and either may
be an `UnknownDate` (a widening: no data changes). And the index of a dateable document's sort day
(`pangloss_dates.structure`).
"""

from pangloss_models.migrations import changes_from_data

dependencies = [["pangloss_dates", "0001_initial"]]
schema_hash = "edae4bf0be05f69c1ba747c756f3703d45644d4d044a01a7e917407aea3a2a15"

changes = changes_from_data(
    [
        {
            "change": "RenameField",
            "safety": "transforming",
            "model": "DateRange",
            "old": "earliest",
            "new": "not_before",
        },
        {
            "change": "RenameField",
            "safety": "transforming",
            "model": "DateRange",
            "old": "latest",
            "new": "not_after",
        },
        {
            "change": "AlterEmbedded",
            "safety": "safe",
            "model": "DateRange",
            "name": "not_before",
            "old_model": "ExactDate",
            "new_model": None,
            "added_types": ["UnknownDate"],
            "removed_types": [],
            "types": ["ExactDate", "UnknownDate"],
        },
        {
            "change": "AlterEmbedded",
            "safety": "safe",
            "model": "DateRange",
            "name": "not_after",
            "old_model": "ExactDate",
            "new_model": None,
            "added_types": ["UnknownDate"],
            "removed_types": [],
            "types": ["ExactDate", "UnknownDate"],
        },
        {
            "change": "AddIndex",
            "safety": "safe",
            "index": {
                "kind": "label+property",
                "label": "Dateable",
                "properties": ["date_sort_day"],
            },
        },
    ]
)
