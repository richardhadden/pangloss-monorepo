"""0004_addfield_occupationtype_label_de

Made by `pangloss makemigrations`; the answers a change needs may be filled in here.
"""

from pangloss_models.migrations.files import changes_from_data

dependencies = []
schema_hash = '7faaa806bb0bdf6d93e03ea6e887c864461b676bafc5c1ff5eba4e05c19c65ae'

changes = changes_from_data([{'change': 'AddField',
  'safety': 'safe',
  'model': 'OccupationType',
  'name': 'label_de',
  'field_kind': 'literal',
  'needs_value': False,
  'definition': {'name': 'label_de',
                 'key': 'labelDe',
                 'nullable': True,
                 'kind': 'literal',
                 'type': {'type': 'str'},
                 'storage': {'kind': 'property'}},
  'default': None,
  'from_narrowing': False}])
