"""0004_removefield_datecharacterisation_rank_removefield_datecharac

Made by `pangloss makemigrations`, then changed by hand (and applied so: it is not to be changed again, or a database that
has it refuses to start): `use` and `rank` are no longer fields of the base class (a project declares on its own subclass
what else it wants of a characterisation). The removal is marked `absorbed`, so that it leaves the data alone. That was
needed before 2be4fba, when removing a field from a base set it to null on every node of the base's label, a subclass's
that declares it itself included; since then a subclass that still has the field keeps it anyway, and one that does not
has a removal of its own.
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
