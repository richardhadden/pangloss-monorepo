"""What the driver is made with (`Neo4jDialect.driver_options`)"""

import neo4j
from pangloss_neo4j.databases.neo4j.dialect import Neo4jDialect


def test_the_driver_is_not_told_of_what_every_query_would_be_reported_for():
    """Deprecations, and (on a new database) names that no data has yet: each was a log line, the second with the
    whole query, for every read until some data existed"""
    disabled = Neo4jDialect().driver_options()["notifications_disabled_classifications"]
    assert set(disabled) == {
        neo4j.NotificationDisabledClassification.DEPRECATION,
        neo4j.NotificationDisabledClassification.UNRECOGNIZED,
    }
    # (and a driver takes them)
    driver = neo4j.AsyncGraphDatabase.driver(
        "bolt://localhost:1", auth=("x", "x"), **Neo4jDialect().driver_options()
    )
    assert driver is not None
