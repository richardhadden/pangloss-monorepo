"""0026_addindex_addindex_addindex

Made by `pangloss makemigrations`; the answers a change needs may be filled in here.
"""

from pangloss_models.migrations import changes_from_data

dependencies = []
schema_hash = '44bab801e4887c4d7c276d00e48230b2de2c60aa7acc0fff2a7ee5bbfe74a08e'

changes = changes_from_data([{'change': 'AddIndex',
  'safety': 'safe',
  'index': {'kind': 'vector',
            'name': 'pgv_when_293',
            'label': 'PGV_when_293',
            'properties': ['vector'],
            'dimension': 293,
            'metric': 'cos',
            'quantization': False}},
 {'change': 'AddIndex',
  'safety': 'safe',
  'index': {'kind': 'vector',
            'name': 'pgv_when_293_person',
            'label': 'PGV_when_293_Person',
            'properties': ['vector'],
            'dimension': 293,
            'metric': 'cos',
            'quantization': False}},
 {'change': 'AddIndex',
  'safety': 'safe',
  'index': {'kind': 'vector',
            'name': 'pgv_when_293_statement',
            'label': 'PGV_when_293_Statement',
            'properties': ['vector'],
            'dimension': 293,
            'metric': 'cos',
            'quantization': False}}])
