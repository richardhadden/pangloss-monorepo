"""0002_review_status_published

Written by hand (2026-11-10): the review status of a published document is `published`. It was called `checked`
until now, and documents checked before have that on their head node: they are given the new name. (`checked` is
still taken wherever a status is given: `pangloss_models.hooks.review_status_name`.) The models do not change.
"""

from pangloss_models.migrations import changes as c
from pangloss_models.migrations import changes_from_data

dependencies = []
schema_hash = "2c3a165fb814f5e94e83746a907e29484f48269df37fdef12986f785fcfc6d15"

OLD, NEW = "checked", "published"

changes = changes_from_data(
    [
        # (plain Cypher, the same for both backends; no model is changed by it, so none is read back)
        c.RunCypher(
            query=f"MATCH (n:HeadNode) WHERE n.review_status = '{OLD}' SET n.review_status = '{NEW}'",
            reverse_query=f"MATCH (n:HeadNode) WHERE n.review_status = '{NEW}' SET n.review_status = '{OLD}'",
            dialect=dialect,
            affects=[],
            note="the status of a published document is called `published`",
        )
        for dialect in ("memgraph", "neo4j")
    ]
)
