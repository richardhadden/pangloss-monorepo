"""The settings of `pangloss-names`, read from the project's settings object with their defaults
(implementation_docs/similarity-build-plan.md, phase 8):

- `NAMES_DIMENSION` (256): the length of the name part's vectors. A whole number from 8 to 2048.

The table of variants (`variants()`) is empty for now: step 8.5 makes it a setting.
"""

from collections.abc import Iterable, Mapping
from typing import Any

from pangloss_models.exceptions import PanglossInitialisationError

DEFAULT_DIMENSION = 256
DIMENSIONS = (8, 2048)

__all__ = ["dimension", "variants"]


def _settings(settings: Any) -> Any:
    if settings is not None:
        return settings
    from pangloss_core import settings as core_settings

    return core_settings.__dict__.get("SETTINGS")


def dimension(settings: Any = None) -> int:
    """`NAMES_DIMENSION`: the length of the name part's vectors (256)"""
    value = getattr(_settings(settings), "NAMES_DIMENSION", DEFAULT_DIMENSION)
    low, high = DIMENSIONS
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or not low <= value <= high
    ):
        raise PanglossInitialisationError(
            f"NAMES_DIMENSION is a whole number from {low} to {high} (the length of the name part's vectors), "
            f"not {value!r}"
        )
    return value


def variants(settings: Any = None) -> Mapping[str, Iterable[str]]:
    """The table of variants: canonical forms of a word of a name, each with its variants (`{"Johannes": ["Hans",
    "Jan"]}`), as `maths.variants_table` takes it. Empty for now: step 8.5 of the build plan reads it from a file the
    project names (`NAMES_VARIANTS`)"""
    return {}
