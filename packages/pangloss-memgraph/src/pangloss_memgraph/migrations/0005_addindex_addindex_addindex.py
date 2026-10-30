"""0005_addindex_addindex_addindex

Label indexes for the labels that queries scan whole: the migration lock that every write checks, the users,
a user's tokens, and the head nodes of the review queue. Without one Memgraph reads every node of the database for each
(12 ms for the lock at 600,000 nodes; 0.3 ms with an index).

Made by `pangloss makemigrations`; the answers a change needs may be filled in here.
"""

from pangloss_models.migrations.files import changes_from_data

dependencies = []
schema_hash = "d00855e120a0ac4434d6ac083d875b0ffb1e161841df9390dcb5f80e3e5a3708"

changes = changes_from_data(
    [
        {
            "change": "AddIndex",
            "safety": "safe",
            "index": {"kind": "label", "label": "HeadNode", "properties": []},
        },
        {
            "change": "AddIndex",
            "safety": "safe",
            "index": {"kind": "label", "label": "PGAccessToken", "properties": []},
        },
        {
            "change": "AddIndex",
            "safety": "safe",
            "index": {"kind": "label", "label": "PGMigrationLock", "properties": []},
        },
        {
            "change": "AddIndex",
            "safety": "safe",
            "index": {"kind": "label", "label": "PGUser", "properties": []},
        },
    ]
)
