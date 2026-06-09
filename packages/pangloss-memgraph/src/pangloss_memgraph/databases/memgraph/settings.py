from pangloss_core.settings import DatabaseSettings


class MemgraphDatabaseSettings(DatabaseSettings):
    DB_URL: str
    DB_USERNAME: str
    DB_PASSWORD: str
    DATABASE_NAME: str
