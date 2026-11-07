"""The server does not start with an `AUTHJWT_SECRET_KEY` that is easy to guess"""

import pytest
from pangloss_api import create_app
from pangloss_api.app import MIN_SECRET_LENGTH


def test_a_short_secret_key_is_refused(settings):
    settings.AUTHJWT_SECRET_KEY = "x" * (MIN_SECRET_LENGTH - 1)
    with pytest.raises(RuntimeError, match="AUTHJWT_SECRET_KEY is shorter"):
        create_app()
    settings.AUTHJWT_SECRET_KEY = "x" * MIN_SECRET_LENGTH
    create_app()
