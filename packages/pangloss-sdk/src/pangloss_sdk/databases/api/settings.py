from pangloss_core.settings import DatabaseSettings
from pydantic import AnyHttpUrl


class ApiAsDatabaseSettings(DatabaseSettings):
    URL: AnyHttpUrl
    USERNAME: str
    PASSWORD: str
