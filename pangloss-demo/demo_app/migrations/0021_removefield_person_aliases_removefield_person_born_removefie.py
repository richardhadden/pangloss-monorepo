"""0021_removefield_person_aliases_removefield_person_born_removefie

Made by `pangloss makemigrations`; the answers a change needs may be filled in here.
"""

from pangloss_models.migrations import changes_from_data

dependencies = []
schema_hash = 'e94e0fbdb446d9bd5ac43d815065e528d7fbfb2eced5866d25858dbeefa8aba2'

changes = changes_from_data([{'change': 'RemoveField',
  'safety': 'lossy',
  'model': 'Person',
  'name': 'aliases',
  'field_kind': 'list',
  'absorbed': False},
 {'change': 'RemoveField',
  'safety': 'lossy',
  'model': 'Person',
  'name': 'born',
  'field_kind': 'embedded',
  'absorbed': False},
 {'change': 'RemoveField',
  'safety': 'lossy',
  'model': 'Person',
  'name': 'has_type',
  'field_kind': 'relation',
  'absorbed': False},
 {'change': 'RemoveField',
  'safety': 'lossy',
  'model': 'Person',
  'name': 'known_as',
  'field_kind': 'annotatedValue',
  'absorbed': False}])
