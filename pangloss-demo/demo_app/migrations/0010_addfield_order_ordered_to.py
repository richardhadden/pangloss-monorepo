"""0010_addfield_order_ordered_to

Made by `pangloss makemigrations`; the answers a change needs may be filled in here.
"""

from pangloss_models.migrations import changes_from_data

dependencies = []
schema_hash = 'f409dd5aed9b5b393f7d070f476b6f814f0f83885ae8bf85180e5dc1a85a131b'

changes = changes_from_data([{'change': 'AddField',
  'safety': 'safe',
  'model': 'Order',
  'name': 'ordered_to',
  'field_kind': 'relation',
  'needs_value': False,
  'definition': {'name': 'ordered_to',
                 'key': 'orderedTo',
                 'nullable': False,
                 'kind': 'relation',
                 'many': False,
                 'reverseName': 'received_order',
                 'options': [{'kind': 'entity', 'type': 'Group', 'edgeModel': None},
                             {'kind': 'entity', 'type': 'Person', 'edgeModel': None},
                             {'kind': 'reifiedRelation',
                              'type': 'Identification',
                              'edgeModel': None,
                              'params': {'T': {'typeVar': 'T',
                                               'options': [{'kind': 'conjunction',
                                                            'type': 'Alternative',
                                                            'edgeModel': None,
                                                            'params': {'T': {'typeVar': 'T',
                                                                             'options': [{'kind': 'entity',
                                                                                          'type': 'Person',
                                                                                          'edgeModel': 'Probability'}]}}}]}}}],
                 'storage': {'kind': 'edge', 'edges': [['ordered_to', 'received_order']]}},
  'default': None,
  'from_narrowing': False}])
