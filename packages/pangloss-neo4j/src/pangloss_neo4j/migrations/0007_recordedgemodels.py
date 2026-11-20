"""0007_recordedgemodels

An edge says which edge model its values are of (`pg_edge_model`, the name of the class): two edge models can have
fields of the same names, and a search of one must not find an edge of the other. The models write it from now on; here
the edges that exist are given it, by what the models say each is of.
"""

from pangloss_models.migrations import changes_from_data

dependencies = []

changes = changes_from_data(
    [
        {
            "change": "RecordEdgeModels",
            "safety": "transforming",
        },
    ]
)
