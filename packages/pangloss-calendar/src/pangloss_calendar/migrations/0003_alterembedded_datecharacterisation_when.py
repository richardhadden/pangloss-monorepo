"""0003_alterembedded_datecharacterisation_when

Made by `pangloss makemigrations`; the answers a change needs may be filled in here.
"""

from pangloss_models.migrations.files import changes_from_data

dependencies = [["pangloss_dates", "0001_initial"]]
schema_hash = "9e0e8dcfce264de575e6540a14681ecfcfe7241bd77bc70067243fd400cd1eeb"

changes = changes_from_data(
    [
        {
            "change": "AlterEmbedded",
            "safety": "safe",
            "model": "DateCharacterisation",
            "name": "when",
            "old_model": None,
            "new_model": None,
            "added_types": ["DateRange", "EDTFDate", "ExactDate", "Period"],
            "removed_types": [],
            "types": [
                "DateRange",
                "EDTFDate",
                "ExactDate",
                "NoRule",
                "Period",
                "Recurrence",
            ],
        }
    ]
)
