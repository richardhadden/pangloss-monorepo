"""0004_verdicts

Three verdicts more a person may say of a pair (D7 widened): `complied`, `permission_used` and
`done_not_carried_out`. The models only: nothing in the database changes. Made by the planner against the shipped
migrations, as `tests/test_shipped_migrations.py` asks.
"""

from pangloss_models.migrations import changes_from_data

dependencies = [["pangloss_compare", "0003_field_names"]]
schema_hash = "1bd024143faf99d53bf6abd823910e8ad2de320ca2cc5736570cd352daaaf4fa"

changes = changes_from_data(
    [
        {
            "change": "StateOnly",
            "safety": "safe",
            "changes": [
                {
                    "change": "AlterLiteralType",
                    "safety": "transforming",
                    "model": "EventJudgement",
                    "name": "verdict",
                    "old": {
                        "type": "literal",
                        "values": [
                            "agree",
                            "disagree",
                            "two_events",
                            "carried_out",
                            "carried_out_otherwise",
                            "not_carried_out",
                            "breach",
                        ],
                    },
                    "new": {
                        "type": "literal",
                        "values": [
                            "agree",
                            "disagree",
                            "two_events",
                            "carried_out",
                            "carried_out_otherwise",
                            "not_carried_out",
                            "breach",
                            "complied",
                            "permission_used",
                            "done_not_carried_out",
                        ],
                    },
                    "on_failure": None,
                    "default": None,
                    "mapping": None,
                }
            ],
        }
    ]
)
