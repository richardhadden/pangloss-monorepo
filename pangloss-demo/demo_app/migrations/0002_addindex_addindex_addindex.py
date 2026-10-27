"""0002_addindex_addindex_addindex

Made by `pangloss makemigrations`; the answers a change needs may be filled in here.
"""

from pangloss_models.migrations.files import changes_from_data

dependencies = []
schema_hash = '75060b44d83e87f9adc7ff4ee86ff96ae05862be88c998268cee5d8408129d85'

changes = changes_from_data([{'change': 'AddIndex',
  'safety': 'safe',
  'index': {'kind': 'label', 'label': 'Activity', 'properties': []}},
 {'change': 'AddIndex',
  'safety': 'safe',
  'index': {'kind': 'label', 'label': 'Factoid', 'properties': []}},
 {'change': 'AddIndex',
  'safety': 'safe',
  'index': {'kind': 'label', 'label': 'Group', 'properties': []}},
 {'change': 'AddIndex',
  'safety': 'safe',
  'index': {'kind': 'label', 'label': 'Person', 'properties': []}},
 {'change': 'AddIndex',
  'safety': 'safe',
  'index': {'kind': 'label', 'label': 'Place', 'properties': []}},
 {'change': 'AddIndex',
  'safety': 'safe',
  'index': {'kind': 'label', 'label': 'Source', 'properties': []}},
 {'change': 'AddIndex',
  'safety': 'safe',
  'index': {'kind': 'label', 'label': 'Statement', 'properties': []}},
 {'change': 'AddIndex',
  'safety': 'safe',
  'index': {'kind': 'label', 'label': 'Transfer', 'properties': []}},
 {'change': 'AddIndex',
  'safety': 'safe',
  'index': {'kind': 'label+property', 'label': 'Factoid', 'properties': ['year']}}])
