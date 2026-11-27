"""The settings of `pangloss-compare`, read from the project's settings object with their defaults
(implementation_docs/compare.md):

- `COMPARE_MOST_PAIRS` (200): the most pairs by rule a statement is given (`pairs.by_rule`); those past it are cut,
  and the answer says there were more. A whole number of 1 or more.
- `COMPARE_LEARN_FROM` (100): the fewest judgements a model of a fit (`pangloss compare learn`, `fits.py`) is made of
  for it to be used: each of the two models (one event or two; does this answer that) by itself. A whole number of 1
  or more.

The pairs through near entities (step 6.4, `near.py`):

- `COMPARE_PROFILE` (None): the profile of `pangloss-vectors` the entities nearest a statement's identifying entities
  are found by. None: reconciliation's (`pangloss_reconcile.settings.profile()`) when `pangloss_reconcile` is
  installed; otherwise there are no pairs through near entities. Refused if it is not text, if `pangloss_vectors` is
  not installed (among `INSTALLED_APPS` and importable), or if it names no profile of `VECTORS_PROFILES`.
- `COMPARE_NEAR_K` (5): how many near entities each identifying entity is given (`nearest(k=...)`). A whole number
  of 1 or more.
- `COMPARE_NEAR` (0.6): the least score (`Hit.score`) of a near entity. A number from 0 to 1.

Checked at `initialise()` when the app is installed (`check`). Neither `pangloss-vectors` nor `pangloss-reconcile` is
a dependency: each is imported only when it is installed.
"""

from typing import Any

from pangloss_models import ModelRegistry
from pangloss_models.exceptions import PanglossInitialisationError

DEFAULT_MOST_PAIRS = 200
DEFAULT_LEARN_FROM = 100
DEFAULT_NEAR_K = 5
DEFAULT_NEAR = 0.6

APP = "pangloss_compare"
VECTORS = "pangloss_vectors"
RECONCILE = "pangloss_reconcile"

__all__ = [
    "check",
    "learn_from",
    "most_pairs",
    "near_floor",
    "near_k",
    "near_profile",
    "vectors_installed",
]


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


def _apps(settings: Any) -> list[str]:
    return list(getattr(settings, "INSTALLED_APPS", None) or [])


def _importable(name: str) -> bool:
    import importlib.util

    try:
        return importlib.util.find_spec(name) is not None
    except ValueError, ImportError:
        return False


def vectors_installed(settings: Any = None) -> bool:
    """Whether `pangloss_vectors` is among `INSTALLED_APPS` and can be imported"""
    return VECTORS in _apps(_settings(settings)) and _importable(VECTORS)


def near_profile(settings: Any = None) -> str | None:
    """`COMPARE_PROFILE`, or the profile chosen without it (reconciliation's, when `pangloss_reconcile` is
    installed), or None: no pairs through near entities. Refused (`PanglossInitialisationError`) with what to set"""
    settings = _settings(settings)
    named = getattr(settings, "COMPARE_PROFILE", None)
    vectors = vectors_installed(settings)
    if named is not None:
        if not isinstance(named, str):
            raise PanglossInitialisationError(
                f"COMPARE_PROFILE is the name of a profile of pangloss_vectors (VECTORS_PROFILES), or None, not "
                f"{named!r}"
            )
        if not vectors:
            raise PanglossInitialisationError(
                f"COMPARE_PROFILE names {named!r}, but pangloss_vectors is not installed: add it to INSTALLED_APPS, "
                "or leave COMPARE_PROFILE unset (no pairs through near entities)"
            )
        from pangloss_vectors.parts import profiles

        known = profiles(settings)
        if named not in known:
            raise PanglossInitialisationError(
                f"COMPARE_PROFILE names {named!r}, which is not a profile: the profiles are "
                f"{', '.join(sorted(known))} (VECTORS_PROFILES)"
            )
        return named
    if vectors and RECONCILE in _apps(settings) and _importable(RECONCILE):
        from pangloss_reconcile import settings as reconcile_settings

        return reconcile_settings.profile(settings)
    return None


def near_k(settings: Any = None) -> int:
    """`COMPARE_NEAR_K`: how many near entities each identifying entity is given (5)"""
    value = getattr(_settings(settings), "COMPARE_NEAR_K", DEFAULT_NEAR_K)
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise PanglossInitialisationError(
            "COMPARE_NEAR_K is a whole number of 1 or more (how many near entities each identifying entity of a "
            f"statement is given), not {value!r}"
        )
    return value


def near_floor(settings: Any = None) -> float:
    """`COMPARE_NEAR`: the least score of a near entity (0.6)"""
    value = getattr(_settings(settings), "COMPARE_NEAR", DEFAULT_NEAR)
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not 0 <= value <= 1
    ):
        raise PanglossInitialisationError(
            f"COMPARE_NEAR is a number from 0 to 1 (the least score of a near entity), not {value!r}"
        )
    return float(value)


def check() -> None:
    """(`ModelRegistry.after_finalise`) a project with this app installed has its settings checked at
    `initialise()`"""
    settings = _settings(None)
    if APP not in list(getattr(settings, "INSTALLED_APPS", None) or []):
        return
    most_pairs(settings)
    learn_from(settings)
    near_k(settings)
    near_floor(settings)
    if vectors_installed(settings):
        # (every part registered first, as vectors' own check does)
        from pangloss_vectors import import_installed_apps

        import_installed_apps(settings)
    near_profile(settings)


def install() -> None:
    """(`pangloss_compare._install`)"""
    if check not in ModelRegistry.after_finalise:
        ModelRegistry.after_finalise.append(check)
