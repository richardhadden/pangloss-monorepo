"""0012_alterrelationtarget_memberof_member_alterrelationtarget_orde

The demo's own `Alternative` (and its edge model `Probability`) become the library's `WeightedAlternative` (and
`Likelihood`): the same fields, the same edges, the same `percent` on them. The library's models are in its own
migrations already, so this is not a rename that `makemigrations` can see: the nodes are moved by hand first
(`RunCypher`), and the models after, which then have no nodes of the old ones to delete.
"""

from pangloss_models.migrations import changes_from_data
from pangloss_models.migrations import changes as c

OLD, NEW = "Alternative", "WeightedAlternative"

dependencies = [['pangloss_library', '0001_initial']]
schema_hash = '812d2d37baf994195f2cbfed7d7b0d9a6f5beb009c4801bb1ce91ff170c21026'


def move(query: str, reverse_query: str, note: str) -> list[c.RunCypher]:
    """The query for each backend (it is plain Cypher: the same for both)"""
    return [
        c.RunCypher(
            query=query, reverse_query=reverse_query, dialect=dialect, note=note
        )
        for dialect in ("memgraph", "neo4j")
    ]


moves = [
    *move(
        f"MATCH (n:{OLD}) REMOVE n:{OLD} SET n:{NEW}",
        f"MATCH (n:{NEW}) REMOVE n:{NEW} SET n:{OLD}",
        "relabel the nodes",
    ),
    *move(
        f"MATCH (n:{NEW}) WHERE n.type = '{OLD}' SET n.type = '{NEW}'",
        # (undone in the opposite order: the nodes still have the new label here)
        f"MATCH (n:{NEW}) WHERE n.type = '{NEW}' SET n.type = '{OLD}'",
        "the type they have",
    ),
    *move(
        f"MATCH (n) WHERE n.head_node_type = '{OLD}' SET n.head_node_type = '{NEW}'",
        f"MATCH (n) WHERE n.head_node_type = '{NEW}' SET n.head_node_type = '{OLD}'",
        "the type of the head node, where a conjunction is one",
    ),
]

changes = changes_from_data(
    [
        *moves,
        {'change': 'AlterRelationTarget',
  'safety': 'lossy',
  'model': 'MemberOf',
  'name': 'member',
  'added': ['reifiedRelation:Identification[T=conjunction:WeightedAlternative[T=entity:Person]]'],
  'removed': ['reifiedRelation:Identification[T=conjunction:Alternative[T=entity:Person]]'],
  'options': [{'kind': 'entity', 'type': 'Group', 'edgeModel': None},
              {'kind': 'entity', 'type': 'Person', 'edgeModel': None},
              {'kind': 'reifiedRelation',
               'type': 'Identification',
               'edgeModel': None,
               'params': {'T': {'typeVar': 'T',
                                'options': [{'kind': 'conjunction',
                                             'type': 'WeightedAlternative',
                                             'edgeModel': None,
                                             'params': {'T': {'typeVar': 'T',
                                                              'options': [{'kind': 'entity',
                                                                           'type': 'Person',
                                                                           'edgeModel': None}]}}}]}}}],
  'on_narrowing': None},
 {'change': 'AlterRelationTarget',
  'safety': 'lossy',
  'model': 'Order',
  'name': 'ordered_by',
  'added': ['reifiedRelation:Identification[T=conjunction:WeightedAlternative[T=entity:Person]]'],
  'removed': ['reifiedRelation:Identification[T=conjunction:Alternative[T=entity:Person]]'],
  'options': [{'kind': 'entity', 'type': 'Group', 'edgeModel': None},
              {'kind': 'entity', 'type': 'Person', 'edgeModel': None},
              {'kind': 'reifiedRelation',
               'type': 'Identification',
               'edgeModel': None,
               'params': {'T': {'typeVar': 'T',
                                'options': [{'kind': 'conjunction',
                                             'type': 'WeightedAlternative',
                                             'edgeModel': None,
                                             'params': {'T': {'typeVar': 'T',
                                                              'options': [{'kind': 'entity',
                                                                           'type': 'Person',
                                                                           'edgeModel': None}]}}}]}}}],
  'on_narrowing': None},
 {'change': 'AlterRelationTarget',
  'safety': 'lossy',
  'model': 'Order',
  'name': 'ordered_to',
  'added': ['reifiedRelation:Identification[T=conjunction:WeightedAlternative[T=entity:Person]]'],
  'removed': ['reifiedRelation:Identification[T=conjunction:Alternative[T=entity:Person]]'],
  'options': [{'kind': 'entity', 'type': 'Group', 'edgeModel': None},
              {'kind': 'entity', 'type': 'Person', 'edgeModel': None},
              {'kind': 'reifiedRelation',
               'type': 'Identification',
               'edgeModel': None,
               'params': {'T': {'typeVar': 'T',
                                'options': [{'kind': 'conjunction',
                                             'type': 'WeightedAlternative',
                                             'edgeModel': None,
                                             'params': {'T': {'typeVar': 'T',
                                                              'options': [{'kind': 'entity',
                                                                           'type': 'Person',
                                                                           'edgeModel': None}]}}}]}}}],
  'on_narrowing': None},
 {'change': 'AlterRelationTarget',
  'safety': 'lossy',
  'model': 'Transfer',
  'name': 'given_by',
  'added': ['reifiedRelation:Identification[T=conjunction:WeightedAlternative[T=entity:Person]]'],
  'removed': ['reifiedRelation:Identification[T=conjunction:Alternative[T=entity:Person]]'],
  'options': [{'kind': 'entity', 'type': 'Group', 'edgeModel': None},
              {'kind': 'entity', 'type': 'Person', 'edgeModel': None},
              {'kind': 'reifiedRelation',
               'type': 'Identification',
               'edgeModel': None,
               'params': {'T': {'typeVar': 'T',
                                'options': [{'kind': 'conjunction',
                                             'type': 'WeightedAlternative',
                                             'edgeModel': None,
                                             'params': {'T': {'typeVar': 'T',
                                                              'options': [{'kind': 'entity',
                                                                           'type': 'Person',
                                                                           'edgeModel': None}]}}}]}}}],
  'on_narrowing': None},
 {'change': 'AlterRelationTarget',
  'safety': 'lossy',
  'model': 'Transfer',
  'name': 'given_to',
  'added': ['reifiedRelation:Identification[T=conjunction:WeightedAlternative[T=entity:Person]]'],
  'removed': ['reifiedRelation:Identification[T=conjunction:Alternative[T=entity:Person]]'],
  'options': [{'kind': 'entity', 'type': 'Group', 'edgeModel': None},
              {'kind': 'entity', 'type': 'Person', 'edgeModel': None},
              {'kind': 'reifiedRelation',
               'type': 'Identification',
               'edgeModel': None,
               'params': {'T': {'typeVar': 'T',
                                'options': [{'kind': 'conjunction',
                                             'type': 'WeightedAlternative',
                                             'edgeModel': None,
                                             'params': {'T': {'typeVar': 'T',
                                                              'options': [{'kind': 'entity',
                                                                           'type': 'Person',
                                                                           'edgeModel': None}]}}}]}}}],
  'on_narrowing': None},
 {'change': 'DeleteModel', 'safety': 'lossy', 'model': 'Alternative', 'model_kind': 'Conjunction'},
 {'change': 'DeleteModel', 'safety': 'lossy', 'model': 'Probability', 'model_kind': 'EdgeModel'}]
)
