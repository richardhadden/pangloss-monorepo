"""The settings of `pangloss-compare`, read from the project's settings object with their defaults
(implementation_docs/compare.md):

- `COMPARE_MOST_PAIRS` (200): the most pairs by rule a statement is given (`pairs.by_rule`); those past it are cut,
  and the answer says there were more. A whole number of 1 or more.
- `COMPARE_LEARN_FROM` (100): the fewest judgements a model of a fit (`pangloss compare learn`, `fits.py`) is made of
  for it to be used: each of the two models (one event or two; does this answer that) by itself. A whole number of 1
  or more.
- `COMPARE_LEARN_MARGIN` (1.0): how far a fitted model may be worse than the hand-set score on the judgements held
  out and still be used, for chance: it is refused only when the hand-set score is right more often by more than this
  times the square root of the number of held-out judgements the two call differently. A number of 0 or more; 0 is
  "no worse" (right as often as the hand-set score or more).

The pairs through near entities (step 6.4, `near.py`):

- `COMPARE_PROFILE` (None): the profile of `pangloss-vectors` the entities nearest a statement's identifying entities
  are found by. None: reconciliation's (`pangloss_reconcile.settings.profile()`) when `pangloss_reconcile` is
  installed; otherwise there are no pairs through near entities. Refused if it is not text, if `pangloss_vectors` is
  not installed (among `INSTALLED_APPS` and importable), or if it names no profile of `VECTORS_PROFILES`, or one that
  weighs no part that knows names (`name_parts`: a part of `pangloss_names`). Reconciliation's choice is taken only if
  it weighs one; otherwise there are no pairs through near entities, as with no profile.
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
DEFAULT_LEARN_MARGIN = 1.0
DEFAULT_NEAR_K = 5
DEFAULT_NEAR = 0.6

APP = "pangloss_compare"
VECTORS = "pangloss_vectors"
RECONCILE = "pangloss_reconcile"
NAMES = "pangloss_names"

__all__ = [
    "check",
    "learn_from",
    "learn_margin",
    "name_parts",
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


def learn_margin(settings: Any = None) -> float:
    """`COMPARE_LEARN_MARGIN`: how far a fitted model may be worse than the hand-set score, for chance (1.0)"""
    value = getattr(_settings(settings), "COMPARE_LEARN_MARGIN", DEFAULT_LEARN_MARGIN)
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not 0 <= value < float("inf")
    ):
        raise PanglossInitialisationError(
            "COMPARE_LEARN_MARGIN is a number of 0 or more (how many times the square root of the judgements the fit "
            "and the hand-set score call differently the hand-set score may be right more often, for a fit still to "
            f"be used; 0: no worse), not {value!r}"
        )
    return float(value)


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


def name_parts() -> list[str]:
    """The names of the parts registered with `pangloss_vectors` that know names: those of `pangloss_names` (told by
    their class, `pangloss_names.part.NamePart`, whatever a part is called; a part is registered when its package is
    imported, so none is of it unless it has been)"""
    import sys

    from pangloss_vectors.parts import parts

    module = sys.modules.get(f"{NAMES}.part")
    kind = getattr(module, "NamePart", None)
    if not isinstance(kind, type):
        return []
    return sorted(name for name, part in parts().items() if isinstance(part, kind))


def knows_names(profile: str, settings: Any = None) -> bool:
    """Whether the profile weighs a part that knows names (`name_parts`)"""
    from pangloss_vectors.parts import profiles

    weights = profiles(_settings(settings)).get(profile, {})
    return any(weights.get(name, 0) > 0 for name in name_parts())


def _knowing_names(profile: str, settings: Any, how: str) -> str:
    """The profile, refused unless it weighs a part that knows names: near entities are who may be one another, and
    only a part of names tells a person's double from someone near in the graph"""
    knowing = name_parts()
    if not knows_names(profile, settings):
        raise PanglossInitialisationError(
            f"{how} {profile!r}, which weighs no part that knows names "
            f"({', '.join(knowing) or 'none is registered: install pangloss_names'}): the near entities of comparison "
            "are those that may be one another, which only names tell. Set COMPARE_PROFILE to a profile that weighs "
            f"one, or give {profile!r} a weight for one in VECTORS_PROFILES"
        )
    return profile


def near_profile(settings: Any = None) -> str | None:
    """`COMPARE_PROFILE`, or the profile chosen without it (reconciliation's, when `pangloss_reconcile` is
    installed, and only if it weighs a part that knows names, `name_parts`), or None: no pairs through near entities.
    Refused (`PanglossInitialisationError`) with what to set, and where `COMPARE_PROFILE` names a profile that weighs
    no part that knows names (reconciliation's choice that weighs none is no refusal: there are then no such pairs,
    as with no profile)"""
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
        return _knowing_names(named, settings, "COMPARE_PROFILE names")
    if vectors and RECONCILE in _apps(settings) and _importable(RECONCILE):
        from pangloss_reconcile import settings as reconcile_settings

        chosen = reconcile_settings.profile(settings)
        return chosen if knows_names(chosen, settings) else None
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
    learn_margin(settings)
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
