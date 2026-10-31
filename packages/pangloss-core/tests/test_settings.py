import pytest
from pangloss_core import settings
from pydantic import ValidationError


class Settings(settings.ClientSettings):
    pass


def test_a_settings_object_that_fails_validation_leaves_the_previous_one():
    good = Settings(INSTALLED_APPS=[], DATABASE_MODULE="somewhere")
    assert settings.SETTINGS is good

    with pytest.raises(ValidationError):
        Settings(INSTALLED_APPS="not a list")

    assert settings.SETTINGS is good
    assert settings.SETTINGS.DATABASE_MODULE == "somewhere"
