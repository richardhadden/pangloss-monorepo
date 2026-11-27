"""The settings of `pangloss-fastrp`, read from the project's settings object with their defaults
(implementation_docs/similarity-build-plan.md, phase 3):

- `FASTRP_STEPS` (`[0, 1, 1]`): the weight of each step of FastRP in the vector, the first step first. With `k`
  steps an item's vector depends on what is within `k` joins of it, and a change is followed `2k - 1` joins out. A
  list of 1 to 8 numbers of 0 or more, not all 0.
- `FASTRP_DIMENSION` (128): the length of the graph part's vectors. A whole number from 8 to 2048.
- `FASTRP_REFRESH_CAP` (50,000): the most nodes a refresh after a write reads around what changed. Past it the
  refresh writes approximate vectors for the documents written (`approximate.py`) and reports them as stale, for a
  rebuild. A whole number of 1 or more.
- `FASTRP_DEGREE_WEIGHTS` (`DEFAULT_DEGREE_WEIGHTS`): of the second part, `"actual"` (`pangloss_fastrp.walk`), the
  weight at which a document joins that the walk says is neither asserted nor denied and leans for, by its degree
  (`pangloss_models.DEGREE_STEPS`), and `"none"` where no degree is entered and its class has no default. Every one
  named, each a number from 0 to 1; 0 is out of the graph. Checked at `initialise()` (`check`).

What the graph holds (`VECTORS_GRAPH_SEES`) is `pangloss-vectors`' setting, read by `graph_sees`.
"""

from collections.abc import Mapping, Sequence
from typing import Any

from pangloss_models import ModelRegistry
from pangloss_models.exceptions import PanglossInitialisationError
from pangloss_vectors.settings import graph_sees

APP = "pangloss_fastrp"

DEFAULT_STEPS = (0.0, 1.0, 1.0)
MAX_STEPS = 8
DEFAULT_DIMENSION = 128
DIMENSIONS = (8, 2048)
DEFAULT_REFRESH_CAP = 50_000
# (the key of the weight of what leans for with no degree entered and no default of its class)
NO_DEGREE = "none"
# (the first guess of implementation_docs/spaces-and-comparison-plan.md, step 5.3, kept after 5.4 was measured)
DEFAULT_DEGREE_WEIGHTS = {
    "impossible": 0.0,
    "unlikely": 0.2,
    "possible": 0.4,
    "likely": 0.6,
    "expected": 0.8,
    NO_DEGREE: 0.5,
}

__all__ = ["degree_weights", "dimension", "graph_sees", "refresh_cap", "steps"]


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


def degree_weights(settings: Any = None) -> dict[str, float]:
    """`FASTRP_DEGREE_WEIGHTS`: the weight of a document of the second part that leans for, by its degree, and
    `"none"` (`DEFAULT_DEGREE_WEIGHTS`)"""
    from pangloss_models import DEGREE_STEPS

    value = getattr(_settings(settings), "FASTRP_DEGREE_WEIGHTS", None)
    if value is None:
        return dict(DEFAULT_DEGREE_WEIGHTS)
    names = (*DEGREE_STEPS, NO_DEGREE)
    if (
        not isinstance(value, Mapping)
        or set(value) != set(names)
        or not all(_is_number(v) and 0 <= v <= 1 for v in value.values())
    ):
        missing = sorted(set(names) - set(value)) if isinstance(value, Mapping) else []
        unknown = (
            sorted(str(k) for k in set(value) - set(names))
            if isinstance(value, Mapping)
            else []
        )
        said = "".join(
            [
                f"; it leaves out {', '.join(repr(n) for n in missing)}" if missing else "",
                f"; it names {', '.join(repr(n) for n in unknown)}, which is no degree" if unknown else "",
            ]
        )  # fmt: skip
        raise PanglossInitialisationError(
            f"FASTRP_DEGREE_WEIGHTS is a weight from 0 to 1 for each of {', '.join(repr(n) for n in names)} (the "
            "weight at which a statement of the actual network joins that leans for, by its degree; 'none' where "
            f"no degree is said), as {DEFAULT_DEGREE_WEIGHTS!r}, not {value!r}{said}"
        )
    return {name: float(value[name]) for name in names}


def check() -> None:
    """(`ModelRegistry.after_finalise`) a project with this app installed has `FASTRP_DEGREE_WEIGHTS` checked at
    `initialise()`. (The other settings are checked where they are read: by the maps, at a rebuild, a refresh or the
    status)"""
    settings = _settings(None)
    if APP not in list(getattr(settings, "INSTALLED_APPS", None) or []):
        return
    degree_weights(settings)


def install() -> None:
    """(`pangloss_fastrp._install`)"""
    if check not in ModelRegistry.after_finalise:
        ModelRegistry.after_finalise.append(check)
