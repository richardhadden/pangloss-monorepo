"""The settings of `pangloss-fastrp`, read from the project's settings object with their defaults
(implementation_docs/similarity-build-plan.md, phase 3):

- `FASTRP_STEPS` (`[0, 1, 1]`): the weight of each step of FastRP in the vector, the first step first. With `k`
  steps an item's vector depends on what is within `k` joins of it, and a change is followed `2k - 1` joins out. A
  list of 1 to 8 numbers of 0 or more, not all 0.
- `FASTRP_DIMENSION` (128): the length of the graph part's vectors. A whole number from 8 to 2048.
- `FASTRP_REFRESH_CAP` (50,000): the most nodes a refresh after a write reads around what changed. Past it the
  refresh writes nothing and reports the heads written as stale, for a rebuild (phase 5 will write an approximation
  instead). A whole number of 1 or more.

What the graph holds (`VECTORS_GRAPH_SEES`) is `pangloss-vectors`' setting, read by `graph_sees`.
"""

from collections.abc import Sequence
from typing import Any

from pangloss_models.exceptions import PanglossInitialisationError
from pangloss_vectors.settings import graph_sees

DEFAULT_STEPS = (0.0, 1.0, 1.0)
MAX_STEPS = 8
DEFAULT_DIMENSION = 128
DIMENSIONS = (8, 2048)
DEFAULT_REFRESH_CAP = 50_000

__all__ = ["dimension", "graph_sees", "refresh_cap", "steps"]


def _settings(settings: Any) -> Any:
    if settings is not None:
        return settings
    from pangloss_core import settings as core_settings

    return core_settings.__dict__.get("SETTINGS")


def _is_number(value: Any) -> bool:
    return not isinstance(value, bool) and isinstance(value, (int, float))


def steps(settings: Any = None) -> list[float]:
    """`FASTRP_STEPS`: the weight of each step in the vector (`[0, 1, 1]`)"""
    value = getattr(_settings(settings), "FASTRP_STEPS", DEFAULT_STEPS)
    if (
        isinstance(value, (str, bytes))
        or not isinstance(value, Sequence)
        or not 1 <= len(value) <= MAX_STEPS
        or not all(_is_number(v) and v >= 0 for v in value)
        or not any(value)
    ):
        raise PanglossInitialisationError(
            f"FASTRP_STEPS is a list of 1 to {MAX_STEPS} numbers of 0 or more, not all 0 (the weight of each step "
            f"of FastRP in the vector, as [0, 1, 1]), not {value!r}"
        )
    return [float(v) for v in value]


def dimension(settings: Any = None) -> int:
    """`FASTRP_DIMENSION`: the length of the graph part's vectors (128)"""
    value = getattr(_settings(settings), "FASTRP_DIMENSION", DEFAULT_DIMENSION)
    low, high = DIMENSIONS
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or not low <= value <= high
    ):
        raise PanglossInitialisationError(
            f"FASTRP_DIMENSION is a whole number from {low} to {high} (the length of the graph part's vectors), "
            f"not {value!r}"
        )
    return value


def refresh_cap(settings: Any = None) -> int:
    """`FASTRP_REFRESH_CAP`: the most nodes a refresh reads around what changed (50,000)"""
    value = getattr(_settings(settings), "FASTRP_REFRESH_CAP", DEFAULT_REFRESH_CAP)
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise PanglossInitialisationError(
            f"FASTRP_REFRESH_CAP is a whole number of 1 or more (the most nodes a refresh after a write reads around "
            f"what changed), not {value!r}"
        )
    return value
