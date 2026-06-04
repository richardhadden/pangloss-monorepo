from pangloss_core.settings import DatabaseSettings


class MemgraphSettings(DatabaseSettings):
    URL: str
    USERNAME: str
    PASSWORD: str
    DATABASE_NAME: str
