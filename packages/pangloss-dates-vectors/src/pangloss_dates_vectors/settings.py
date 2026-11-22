"""The settings of `pangloss-dates-vectors`, read from the project's settings object with their defaults
(implementation_docs/similarity-build-plan.md, "9.2 as built"):

- `DATES_VECTOR_DIMENSION` (128): the length of the time part's vectors, the places of the ring the years go round.
  A whole number from 8 to 2048.
- `DATES_VECTOR_WIDTH` (2): the years between two places of the ring, and the spread of the bump a date is blurred
  by. A number of years more than 0 and at most 100 (`1`, `2.5`).

Two dates `dimension × width` years apart (256, as they are given) have the same vector. Both are checked at
`initialise()` when the app is installed (`check`), and both are in the part's signature, so a change of either makes
a rebuild of the time part due.
"""

from typing import TYPE_CHECKING, Any

from pangloss_models import ModelRegistry
from pangloss_models.exceptions import PanglossInitialisationError

if TYPE_CHECKING:
    from pangloss_dates_vectors.maths import Ring

DEFAULT_DIMENSION = 128
DIMENSIONS = (8, 2048)
DEFAULT_WIDTH = 2
# (years: more than 0, and at most this)
WIDEST = 100

APP = "pangloss_dates_vectors"

__all__ = ["check", "dimension", "ring", "width"]


def _settings(settings: Any) -> Any:
    if settings is not None:
        return settings
    from pangloss_core import settings as core_settings

    return core_settings.__dict__.get("SETTINGS")


def dimension(settings: Any = None) -> int:
    """`DATES_VECTOR_DIMENSION`: the length of the time part's vectors (128)"""
    value = getattr(_settings(settings), "DATES_VECTOR_DIMENSION", DEFAULT_DIMENSION)
    low, high = DIMENSIONS
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or not low <= value <= high
    ):
        raise PanglossInitialisationError(
            f"DATES_VECTOR_DIMENSION is a whole number from {low} to {high} (the length of the time part's vectors), "
            f"not {value!r}"
        )
    return value


def width(settings: Any = None) -> float:
    """`DATES_VECTOR_WIDTH`: the years between two places of the ring (2)"""
    value = getattr(_settings(settings), "DATES_VECTOR_WIDTH", DEFAULT_WIDTH)
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        # (`not 0 < value`, so that a NaN is refused too)
        or not 0 < value <= WIDEST
    ):
        raise PanglossInitialisationError(
            f"DATES_VECTOR_WIDTH is a number of years more than 0 and at most {WIDEST} (the years between two places "
            f"of the time part's vectors), not {value!r}"
        )
    return float(value)


def ring(settings: Any = None) -> Ring:
    """The ring of the settings (`maths.Ring`)"""
    from pangloss_dates_vectors.maths import Ring

    settings = _settings(settings)
    return Ring(dimension=dimension(settings), width=width(settings))


def check() -> None:
    """(`ModelRegistry.after_finalise`) a project with this app installed has its settings checked at
    `initialise()`"""
    settings = _settings(None)
    if APP not in list(getattr(settings, "INSTALLED_APPS", None) or []):
        return
    dimension(settings)
    width(settings)


def install() -> None:
    """(`pangloss_dates_vectors._install`)"""
    if check not in ModelRegistry.after_finalise:
        ModelRegistry.after_finalise.append(check)
