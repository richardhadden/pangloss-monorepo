"""0005_addfield_occupationtype_label_fr

Made by `pangloss makemigrations`; the answers a change needs may be filled in here.
"""

from pangloss_models.migrations import changes_from_data

dependencies = []
schema_hash = '5f8ede1b20b59d313a4ca801f225f009cf15f325f253d6b6d88235dec069d3ad'

changes = changes_from_data([{'change': 'AddField',
  'safety': 'safe',
  'model': 'OccupationType',
  'name': 'label_fr',
  'field_kind': 'literal',
  'needs_value': False,
  'definition': {'name': 'label_fr',
                 'key': 'labelFr',
                 'nullable': True,
                 'kind': 'literal',
                 'type': {'type': 'str'},
                 'storage': {'kind': 'property'}},
  'default': None,
  'from_narrowing': False}])
