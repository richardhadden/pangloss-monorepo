"""0003_field_names

A judgement's `fields` are `FieldName`s (`field_names.py`): text as before, camelCase in JSON. The models only:
nothing in the database changes. Made by the planner (`pangloss_models.migrations.planner.plan`) against the shipped
migrations, as `tests/test_shipped_migrations.py` asks.
"""

from pangloss_models.migrations import changes_from_data

dependencies = [["pangloss_compare", "0002_models"]]
schema_hash = "d521d378933f4ca5244c8c55fac1fe54396b112e15129681c4c50715607deb2e"

changes = changes_from_data(
    [
        {
            "change": "StateOnly",
            "safety": "safe",
            "changes": [
                {
                    "change": "AlterListItemType",
                    "safety": "transforming",
                    "model": "EventJudgement",
                    "name": "fields",
                    "old": {"type": "str"},
                    "new": {"type": "str", "format": "field-name"},
                    "on_failure": None,
                    "default": None,
                    "mapping": None,
                }
            ],
        }
    ]
)
