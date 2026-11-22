"""0025_addindex_addindex_addindex

Made by `pangloss makemigrations`; the answers a change needs may be filled in here.
"""

from pangloss_models.migrations import changes_from_data

dependencies = []
schema_hash = '00a7b5d56a7f80ff1a594f803042b1ba12f90a485f7daecddda4d4b4e5152745'

changes = changes_from_data([{'change': 'AddIndex',
  'safety': 'safe',
  'index': {'kind': 'vector',
            'name': 'pgv_who_384',
            'label': 'PGV_who_384',
            'properties': ['vector'],
            'dimension': 384,
            'metric': 'cos',
            'quantization': False}},
 {'change': 'AddIndex',
  'safety': 'safe',
  'index': {'kind': 'vector',
            'name': 'pgv_who_384_person',
            'label': 'PGV_who_384_Person',
            'properties': ['vector'],
            'dimension': 384,
            'metric': 'cos',
            'quantization': False}},
 {'change': 'AddIndex',
  'safety': 'safe',
  'index': {'kind': 'vector',
            'name': 'pgv_who_384_statement',
            'label': 'PGV_who_384_Statement',
            'properties': ['vector'],
            'dimension': 384,
            'metric': 'cos',
            'quantization': False}}])
