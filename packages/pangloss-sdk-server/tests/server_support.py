"""Helpers of the tests"""

import importlib
import textwrap
from pathlib import Path
from types import SimpleNamespace

from pangloss_models import initialise


def write(root: Path, files: dict[str, str]) -> None:
    for name, source in files.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(textwrap.dedent(source).lstrip("\n"))


def settings_for(**extra) -> SimpleNamespace:
    return SimpleNamespace(PROJECT_NAME="shop", INSTALLED_APPS=["shop"], **extra)


def load_models(settings=None):

    importlib.import_module("shop.models")
    initialise()


API_TESTS = Path(__file__).parents[2] / "pangloss-api/tests"
