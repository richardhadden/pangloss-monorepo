"""The indexes the dates ask for beyond those of their models: read by the database package, which puts them in the
snapshot that migrations are made from. A dateable document's copy of its sort day (`pangloss_dates.dateable`) is on
nodes of many models, all labelled `:Dateable`, so it is asked for here and not by a model."""

INDEXES = [
    {"kind": "label+property", "label": "Dateable", "properties": ["date_sort_day"]},
]
