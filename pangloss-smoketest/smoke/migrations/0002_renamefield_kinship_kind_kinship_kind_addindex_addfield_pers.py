"""0002_renamefield_kinship_kind_kinship_kind_addindex_addfield_pers

Made by `pangloss makemigrations`; the answers a change needs may be filled in here.
"""

from pangloss_models.migrations import changes_from_data

dependencies = []
schema_hash = '274740ed0a25364d8073ac862f117889f8b762be5cd5dd39ee9dca278f45e13f'

changes = changes_from_data([{'change': 'RenameField',
  'safety': 'transforming',
  'model': 'Kinship',
  'old': 'kind',
  'new': 'kinship_kind'},
 {'change': 'AddIndex',
  'safety': 'safe',
  'index': {'kind': 'label+property',
            'label': 'Settlement',
            'properties': ['population_estimate']}},
 {'change': 'AddField',
  'safety': 'safe',
  'model': 'Person',
  'name': 'nickname',
  'field_kind': 'literal',
  'needs_value': False,
  'definition': {'name': 'nickname',
                 'key': 'nickname',
                 'nullable': True,
                 'kind': 'literal',
                 'type': {'type': 'str'},
                 'storage': {'kind': 'property'}},
  'default': None,
  'from_narrowing': False}])
