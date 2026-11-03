"""0004_removefield_datecharacterisation_rank_removefield_datecharac

Made by `pangloss makemigrations`, then changed by hand: `use` and `rank` are no longer fields of the base class (a
project declares on its own subclass what else it wants of a characterisation). The removal is marked `absorbed`, so
that the data is left alone: as written, it set `use` and `rank` to null on every `:DateCharacterisation` node, which
would have wiped them from a subclass that declares them itself (as the demo's `Feast` does). On a subclass that does
not, the old values stay on the nodes, unread.
"""

from pangloss_models.migrations.files import changes_from_data

dependencies = []
schema_hash = "6014980418dc5ae5ad5091afdf7c76b542577040a00e4d02d3db7e484056b950"

changes = changes_from_data(
    [
        {
            "change": "RemoveField",
            "safety": "lossy",
            "model": "DateCharacterisation",
            "name": "rank",
            "field_kind": "literal",
            "absorbed": True,
        },
        {
            "change": "RemoveField",
            "safety": "lossy",
            "model": "DateCharacterisation",
            "name": "use",
            "field_kind": "literal",
            "absorbed": True,
        },
    ]
)
