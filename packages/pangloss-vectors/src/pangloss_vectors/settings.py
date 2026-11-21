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
"""

from typing import Any, Literal

from pangloss_models.exceptions import PanglossInitialisationError

DEFAULT_OVERFETCH = 4
GRAPH_SEES = ("everyone", "logged_in")
DEFAULT_GRAPH_SEES = "everyone"


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
