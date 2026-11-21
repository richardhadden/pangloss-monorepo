"""0024_addindex_addindex_addindex

Made by `pangloss makemigrations`; the answers a change needs may be filled in here.
"""

from pangloss_models.migrations import changes_from_data

dependencies = []
schema_hash = 'f9cbb761d545ed4c07effd50562da4c79d062524a757093b1f16b1ca87e50e63'

changes = changes_from_data([{'change': 'AddIndex',
  'safety': 'safe',
  'index': {'kind': 'vector',
            'name': 'pgv_default_165',
            'label': 'PGV_default_165',
            'properties': ['vector'],
            'dimension': 165,
            'metric': 'cos',
            'quantization': False}},
 {'change': 'AddIndex',
  'safety': 'safe',
  'index': {'kind': 'vector',
            'name': 'pgv_default_165_person',
            'label': 'PGV_default_165_Person',
            'properties': ['vector'],
            'dimension': 165,
            'metric': 'cos',
            'quantization': False}},
 {'change': 'AddIndex',
  'safety': 'safe',
  'index': {'kind': 'vector',
            'name': 'pgv_default_165_statement',
            'label': 'PGV_default_165_Statement',
            'properties': ['vector'],
            'dimension': 165,
            'metric': 'cos',
            'quantization': False}}])
