"""The settings of `pangloss-vectors`, read from the project's settings object with their defaults
(implementation_docs/similarity-build-plan.md):

- `VECTORS_PROFILES`: a weight for each part, by profile (`{"default": {"graph": 1, "class": 0.1}}`); read and
  checked by `parts.profiles`, at `initialise()`. Without it, `"default"` is every registered part at its own weight.
- `VECTORS_OVERFETCH` (4): a search asks the vector index for this many times the hits it wants, since some of
  those it gives are of items the reader may not see, or that were deleted since. An int of 1 or more.
- `VECTORS_GRAPH_SEES` (`"everyone"`): what the graph a vector is computed from holds. `"everyone"`, the cautious
  default: only what a reader who is not logged in may see (no unpublished documents, no candidates with
  `seen_by: "logged_in"`). `"logged_in"`: everything that is not deleted, as soon as it is written. Search results
  are cut to what the reader may see either way, but with `"logged_in"` what they cannot see has shaped the vectors
  (implementation_docs/graph-embeddings.md, "The joined graph, as now proposed").
- `VECTORS_MIGRATIONS_APP` (none): the installed app whose migrations make the vector indexes of the profiles. Without
  it, the app that holds the most classes of documents and entities outside the `pangloss_*` packages; read by
  `structure.project_app`.
- `VECTORS_CLASS_DECAY` (0.5): how much of a class the class part gives each class above it (`class_part.py`): the
  class's parent at this, the parent's parent at its square, and so on. A number from 0 (no hierarchy: only the class
  itself) to 1 (every class above counts as the class itself).
- `VECTORS_WORKER_IN_SERVER` (true): the worker that keeps the vectors current after writes runs in the server, as a
  background task (`api.py`); false to run it in a process of its own, `pangloss vectors worker`.
- `VECTORS_REBUILD_AFTER` (none): a number of stale vectors (written approximately, or left out of date, by a refresh
  past a part's cap) past which the worker starts a rebuild of the part: the admin job `vectors_rebuild` if
  `pangloss_admin` is installed, or else the rebuild itself, in the worker. None: a rebuild is started by hand.
- `VECTORS_EXCLUDE` (none): classes of documents or entities, by name, whose items have no vectors, nor those of the
  classes below them: the project's last word, over a class's own `VectorsMeta` (`meta.included`).
- `VECTORS_INCLUDE` (none): the documents that stand in for an entity (`hooks.stand_ins`: review's `Unreconciled`)
  have no vectors unless this names them (or a class above them). Both lists are checked at `initialise()`
  (`meta.check_settings`).
"""

from typing import Any, Literal

from pangloss_models.exceptions import PanglossInitialisationError

DEFAULT_OVERFETCH = 4
GRAPH_SEES = ("everyone", "logged_in")
DEFAULT_GRAPH_SEES = "everyone"
DEFAULT_CLASS_DECAY = 0.5


def _settings(settings: Any) -> Any:
    if settings is not None:
        return settings
    from pangloss_core import settings as core_settings

    return core_settings.__dict__.get("SETTINGS")


def overfetch(settings: Any = None) -> int:
    """`VECTORS_OVERFETCH`: how many times the hits wanted a search asks the vector index for (4)"""
    value = getattr(_settings(settings), "VECTORS_OVERFETCH", DEFAULT_OVERFETCH)
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise PanglossInitialisationError(
            f"VECTORS_OVERFETCH is a whole number of 1 or more (how many times the hits wanted a search asks the "
            f"vector index for), not {value!r}"
        )
    return value


def graph_sees(settings: Any = None) -> Literal["everyone", "logged_in"]:
    """`VECTORS_GRAPH_SEES`: what the graph the vectors are computed from holds, `"everyone"` (the default) or
    `"logged_in"`"""
    value = getattr(_settings(settings), "VECTORS_GRAPH_SEES", DEFAULT_GRAPH_SEES)
    if value == "everyone":
        return "everyone"
    if value == "logged_in":
        return "logged_in"
    raise PanglossInitialisationError(
        f"VECTORS_GRAPH_SEES is 'everyone' or 'logged_in' (what the graph the vectors are computed from holds), "
        f"not {value!r}"
    )


def class_decay(settings: Any = None) -> float:
    """`VECTORS_CLASS_DECAY`: what the class part gives a parent class, against 1 for the class itself (0.5)"""
    value = getattr(_settings(settings), "VECTORS_CLASS_DECAY", DEFAULT_CLASS_DECAY)
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not 0 <= value <= 1
    ):
        raise PanglossInitialisationError(
            f"VECTORS_CLASS_DECAY is a number from 0 to 1 (what the class part gives a parent class, against 1 for "
            f"the class itself), not {value!r}"
        )
    return float(value)


def rebuild_after(settings: Any = None) -> int | None:
    """`VECTORS_REBUILD_AFTER`: how many stale vectors of a part make the worker start its rebuild (None: never)"""
    value = getattr(_settings(settings), "VECTORS_REBUILD_AFTER", None)
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise PanglossInitialisationError(
            f"VECTORS_REBUILD_AFTER is a whole number of 0 or more (how many stale vectors of a part make the worker "
            f"start its rebuild), or None, not {value!r}"
        )
    return value


def worker_in_server(settings: Any = None) -> bool:
    """`VECTORS_WORKER_IN_SERVER`: whether the worker runs in the server (true)"""
    return bool(getattr(_settings(settings), "VECTORS_WORKER_IN_SERVER", True))


def _names(setting: str, settings: Any) -> list[str]:
    value = getattr(_settings(settings), setting, None)
    if value is None:
        return []
    if not isinstance(value, (list, tuple)) or not all(
        isinstance(name, str) for name in value
    ):
        raise PanglossInitialisationError(
            f"{setting} is a list of the names of classes of documents or entities (['Note']), not {value!r}"
        )
    return list(value)


def vectors_exclude(settings: Any = None) -> list[str]:
    """`VECTORS_EXCLUDE`: the classes, by name, whose items (and those of the classes below them) have no vectors"""
    return _names("VECTORS_EXCLUDE", settings)


def vectors_include(settings: Any = None) -> list[str]:
    """`VECTORS_INCLUDE`: the stand-ins' documents, by name, that have vectors all the same"""
    return _names("VECTORS_INCLUDE", settings)
