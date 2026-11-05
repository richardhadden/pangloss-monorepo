"""0014_alterrelationtarget_factoid_source

A factoid's source is a Zotero item (`ZoteroObject`) instead of a `Source`. Something to test the Zotero
sources on: every factoid's `AtPage` is moved by hand (`RunCypher`) from its `Source` to one book of the
library (Le Glay, *Négociations diplomatiques entre la France et l'Autriche*, 1845), whatever its source was.
Where the book is not there (a database without the library), nothing is moved, and the change after fails
if a factoid has a source. It cannot be undone: which source each factoid had is not kept.
"""

from pangloss_models.migrations import changes_from_data
from pangloss_models.migrations import changes as c

BOOK = "01a1a6dd-eead-75ec-b1ac-8056709f34d9"

MOVE = """
MATCH (:Factoid)-[:source]->(a:AtPage)-[t:target]->(:Source)
MATCH (book:ZoteroObject {id: $book})
CREATE (a)-[:target {pg_position: t.pg_position}]->(book)
DELETE t
"""

dependencies = [['pangloss_zotero', '0001_initial']]
schema_hash = '10928d9caad70aa0effb84670330a00d75b22d17ec2626d5e92eb26a9e0a8f6b'

changes = changes_from_data([
  *(c.RunCypher(query=MOVE, parameters={'book': BOOK}, dialect=dialect, lossy=True, affects=['Factoid'],
                note='point every factoid at the book') for dialect in ('memgraph', 'neo4j')),
  {'change': 'AlterRelationTarget',
  'safety': 'lossy',
  'model': 'Factoid',
  'name': 'source',
  'added': ['reifiedRelation:AtPage[T=entity:ZoteroObject]'],
  'removed': ['reifiedRelation:AtPage[T=entity:Source]'],
  'options': [{'kind': 'reifiedRelation',
               'type': 'AtPage',
               'edgeModel': None,
               'params': {'T': {'typeVar': 'T',
                                'options': [{'kind': 'entity',
                                             'type': 'ZoteroObject',
                                             'edgeModel': None}]}}}],
  'on_narrowing': 'fail'}])
