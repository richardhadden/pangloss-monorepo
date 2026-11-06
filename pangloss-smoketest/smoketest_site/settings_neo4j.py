"""The same project on Neo4j (:7699), for the smoke test of pangloss-neo4j: `PANGLOSS_SETTINGS=smoketest_site.settings_neo4j`"""

from pangloss_neo4j.databases.neo4j.settings import Neo4jDatabaseSettings

from smoketest_site.settings import Settings as MemgraphSettings


class Settings(MemgraphSettings):
    INSTALLED_APPS: list[str] = ["pangloss_neo4j", *MemgraphSettings.model_fields["INSTALLED_APPS"].default[1:]]
    STORAGE: str | None = "pangloss_neo4j:storage"
    DATABASE: Neo4jDatabaseSettings = Neo4jDatabaseSettings(  # ty: ignore[invalid-attribute-override]
        DB_URL="bolt://localhost:7699",
        DB_USERNAME="neo4j",
        DB_PASSWORD="smoketest-neo4j-pw",
        DATABASE_NAME="neo4j",
    )
    # (not the Memgraph project's Zotero library twice: the Neo4j copy does not sync)
    ZOTERO_LIBRARIES: list[str] = []


Settings()
