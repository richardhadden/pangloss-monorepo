"""0002_addfield_matchescriteria_same_one

Made by `pangloss makemigrations`; the answers a change needs may be filled in here.
"""

from pangloss_models.migrations import changes_from_data

dependencies = []
schema_hash = "c9d333cf7830ab130714fbb744298d56e90dfe0a8a1b2f0e90ca4f429e557377"

changes = changes_from_data(
    [
        {
            "change": "AddField",
            "safety": "safe",
            "model": "MatchesCriteria",
            "name": "same_one",
            "field_kind": "literal",
            "needs_value": False,
            "definition": {
                "name": "same_one",
                "key": "sameOne",
                "nullable": True,
                "kind": "literal",
                "type": {"type": "str", "format": "uuid"},
                "storage": {"kind": "property"},
            },
            "default": None,
            "from_narrowing": False,
        }
    ]
)
