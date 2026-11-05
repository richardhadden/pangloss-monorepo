"""0008_addindex_createmodel_feast

Made by `pangloss makemigrations`; the answers a change needs may be filled in here.
"""

from pangloss_models.migrations import changes_from_data

dependencies = [['pangloss_calendar', '0002_addindex_createmodel_datecharacterisation_createmodel_norule'],
 ['pangloss_dates', '0001_initial']]
schema_hash = '9e0e8dcfce264de575e6540a14681ecfcfe7241bd77bc70067243fd400cd1eeb'

changes = changes_from_data([{'change': 'AddIndex',
  'safety': 'safe',
  'index': {'kind': 'label', 'label': 'Feast', 'properties': []}},
 {'change': 'CreateModel',
  'safety': 'safe',
  'model': 'Feast',
  'model_kind': 'Entity',
  'definition': {'name': 'Feast',
                 'kind': 'Entity',
                 'abstract': False,
                 'parent': 'DateCharacterisation',
                 'typeParameters': [],
                 'createWithId': False,
                 'acceptUrlAsId': True,
                 'requireLabel': True,
                 'useInSemanticSpaceLabel': True,
                 'fields': [{'name': 'rank',
                             'key': 'rank',
                             'nullable': True,
                             'kind': 'literal',
                             'type': {'type': 'str'},
                             'storage': {'kind': 'property'}},
                            {'name': 'use',
                             'key': 'use',
                             'nullable': True,
                             'kind': 'literal',
                             'type': {'type': 'str'},
                             'storage': {'kind': 'property'}},
                            {'name': 'when',
                             'key': 'when',
                             'nullable': False,
                             'kind': 'embedded',
                             'model': None,
                             'types': ['DateRange',
                                       'EDTFDate',
                                       'ExactDate',
                                       'NoRule',
                                       'Period',
                                       'Recurrence'],
                             'storage': {'kind': 'embedded_node',
                                         'edges': [['when', 'when_reverse']]}}],
                 'labels': ['DateCharacterisation', 'Entity', 'Feast']}}])
