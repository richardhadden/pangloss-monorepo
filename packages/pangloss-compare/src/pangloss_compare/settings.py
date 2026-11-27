"""The settings of `pangloss-compare`, read from the project's settings object with their defaults
(implementation_docs/compare.md):

- `COMPARE_MOST_PAIRS` (200): the most pairs by rule a statement is given (`pairs.by_rule`); those past it are cut,
  and the answer says there were more. A whole number of 1 or more.
- `COMPARE_LEARN_FROM` (100): the fewest judgements a model of a fit (`pangloss compare learn`, `fits.py`) is made of
  for it to be used: each of the two models (one event or two; does this answer that) by itself. A whole number of 1
  or more.

Checked at `initialise()` when the app is installed (`check`).
"""

from typing import Any

from pangloss_models import ModelRegistry
from pangloss_models.exceptions import PanglossInitialisationError

DEFAULT_MOST_PAIRS = 200
DEFAULT_LEARN_FROM = 100

APP = "pangloss_compare"

__all__ = ["check", "learn_from", "most_pairs"]


def _settings(settings: Any) -> Any:
    if settings is not None:
        return settings
    from pangloss_core import settings as core_settings

    return core_settings.__dict__.get("SETTINGS")


def most_pairs(settings: Any = None) -> int:
    """`COMPARE_MOST_PAIRS`: the most pairs by rule a statement is given (200)"""
    value = getattr(_settings(settings), "COMPARE_MOST_PAIRS", DEFAULT_MOST_PAIRS)
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise PanglossInitialisationError(
            "COMPARE_MOST_PAIRS is a whole number of 1 or more (the most pairs by rule a statement is given), "
            f"not {value!r}"
        )
    return value


def learn_from(settings: Any = None) -> int:
    """`COMPARE_LEARN_FROM`: the fewest judgements a model of a fit is made of for it to be used (100)"""
    value = getattr(_settings(settings), "COMPARE_LEARN_FROM", DEFAULT_LEARN_FROM)
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise PanglossInitialisationError(
            "COMPARE_LEARN_FROM is a whole number of 1 or more (the fewest judgements a fitted model is made of for "
            f"it to be used), not {value!r}"
        )
    return value


def check() -> None:
    """(`ModelRegistry.after_finalise`) a project with this app installed has its settings checked at
    `initialise()`"""
    settings = _settings(None)
    if APP not in list(getattr(settings, "INSTALLED_APPS", None) or []):
        return
    most_pairs(settings)
    learn_from(settings)


def install() -> None:
    """(`pangloss_compare._install`)"""
    if check not in ModelRegistry.after_finalise:
        ModelRegistry.after_finalise.append(check)
