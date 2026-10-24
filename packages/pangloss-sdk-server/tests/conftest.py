import sys

import pytest
from pangloss_core.settings import ClientSettings
from pangloss_models.model_registry import ModelRegistry
from server_support import write

MODELS = """
    from pangloss_models.model_bases.document import Document
    from pangloss_models.model_bases.entity import Entity

    from shop.helpers import SHOUT


    class Person(Entity):
        pass


    class Statement(Document):
        text: str
        about: Person
"""


@pytest.fixture(autouse=True)
def clean_registry():
    ModelRegistry._reset()
    ClientSettings(INSTALLED_APPS=[], DATABASE_MODULE="pangloss_sdk.databases.api")
    yield
    ModelRegistry._reset()
    for name in [n for n in sys.modules if n == "shop" or n.startswith("shop.")]:
        del sys.modules[name]


@pytest.fixture
def project(tmp_path, monkeypatch):
    """A project in a temporary directory: the app `shop`, with models that import a helper"""
    write(
        tmp_path,
        {
            "shop/__init__.py": "",
            "shop/models.py": MODELS,
            "shop/helpers.py": "SHOUT = 'hey'\n",
            "shop/unrelated.py": "NOT_IMPORTED = True\n",
            "pyproject.toml": "[tool.pangloss]\nsettings = 'shop_settings'\n",
        },
    )
    monkeypatch.syspath_prepend(str(tmp_path))
    return tmp_path
