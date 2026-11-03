"""0001_initial

The structure of derived relations: facts (`PGDerived`) and their justifications (`PGJustification`), unique by key; the
justifications of a rule; the state of each rule and the lease of the worker. Written by hand (these nodes are not
models); they are made by the worker.
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
                "label": "PGDerived",
                "properties": ["key"],
            },
        },
        {
            "change": "AddIndex",
            "safety": "safe",
            "index": {
                "kind": "label+property",
                "label": "PGJustification",
                "properties": ["key"],
            },
        },
        {
            "change": "AddIndex",
            "safety": "safe",
            "index": {
                "kind": "label+property",
                "label": "PGJustification",
                "properties": ["rule"],
            },
        },
        {
            "change": "AddIndex",
            "safety": "safe",
            "index": {
                "kind": "label+property",
                "label": "PGDeriveRule",
                "properties": ["name"],
            },
        },
        {
            "change": "AddIndex",
            "safety": "safe",
            "index": {
                "kind": "label+property",
                "label": "PGDeriveWorker",
                "properties": ["kind"],
            },
        },
        {
            "change": "AddConstraint",
            "safety": "additive",
            "constraint": {
                "kind": "unique",
                "label": "PGDerived",
                "properties": ["key"],
            },
        },
        {
            "change": "AddConstraint",
            "safety": "additive",
            "constraint": {
                "kind": "unique",
                "label": "PGJustification",
                "properties": ["key"],
            },
        },
        {
            "change": "AddConstraint",
            "safety": "additive",
            "constraint": {
                "kind": "unique",
                "label": "PGDeriveRule",
                "properties": ["name"],
            },
        },
        {
            "change": "AddConstraint",
            "safety": "additive",
            "constraint": {
                "kind": "unique",
                "label": "PGDeriveWorker",
                "properties": ["kind"],
            },
        },
    ]
)
