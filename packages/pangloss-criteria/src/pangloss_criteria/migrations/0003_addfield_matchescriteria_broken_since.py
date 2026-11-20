"""0003_addfield_matchescriteria_broken_since

Made by `pangloss makemigrations`; the answers a change needs may be filled in here.
"""

from pangloss_models.migrations import changes_from_data

dependencies = []
schema_hash = "f19b9b2e0e6695aefbf8a09dfc4577627772004868fcdf2302a93e3a5f72ef5e"

changes = changes_from_data(
    [
        {
            "change": "AddField",
            "safety": "safe",
            "model": "MatchesCriteria",
            "name": "broken_since",
            "field_kind": "literal",
            "needs_value": False,
            "definition": {
                "name": "broken_since",
                "key": "brokenSince",
                "nullable": True,
                "kind": "literal",
                "type": {"type": "str"},
                "storage": {"kind": "property"},
            },
            "default": None,
            "from_narrowing": False,
        }
    ]
)
