"""0004_removefield_datecharacterisation_rank_removefield_datecharac

Made by `pangloss makemigrations`: `use` and `rank` are no longer fields of the base class (a project declares on its own
subclass what else it wants of a characterisation). The nodes of a subclass that still has them (one that declares them
itself, as the demo's `Feast` does) keep their values; a subclass that does not has a removal of its own.
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
            "absorbed": False,
        },
        {
            "change": "RemoveField",
            "safety": "lossy",
            "model": "DateCharacterisation",
            "name": "use",
            "field_kind": "literal",
            "absorbed": False,
        },
    ]
)
