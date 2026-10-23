"""0002_addindex_addindex_addconstraint

Made by `pangloss makemigrations`; the answers a change needs may be filled in here.
"""

from pangloss_models.migrations.files import changes_from_data

dependencies = []
schema_hash = '2c35a6a1bba7cdbf337b77840d50cf0fba9b8e58c40ae53d6b33033e3dd31b89'

changes = changes_from_data([{'change': 'AddIndex',
  'safety': 'safe',
  'index': {'kind': 'label+property', 'label': 'PGAccessToken', 'properties': ['token_hash']}},
 {'change': 'AddIndex',
  'safety': 'safe',
  'index': {'kind': 'label+property', 'label': 'PGRevokedSession', 'properties': ['jti']}},
 {'change': 'AddConstraint',
  'safety': 'additive',
  'constraint': {'kind': 'unique', 'label': 'PGAccessToken', 'properties': ['token_hash']}},
 {'change': 'AddConstraint',
  'safety': 'additive',
  'constraint': {'kind': 'unique', 'label': 'PGRevokedSession', 'properties': ['jti']}}])
