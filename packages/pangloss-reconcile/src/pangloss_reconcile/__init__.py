"""Reconciliation for Pangloss (an app: `INSTALLED_APPS += ["pangloss_reconcile"]`, with `pangloss_vectors` and its
parts): for each stand-in of a document (an unknown, `pangloss_vectors.unknowns_of`: review's `Unreconciled`), the
entities it may be, found and scored by the parts of similarity, and nothing written. `candidates.py` finds them
(`candidates_of`), `score.py` scores them (no database in it), `settings.py` holds the settings
(`RECONCILE_PROFILE`, `RECONCILE_FETCH`, `RECONCILE_WEIGHTS`, checked at `initialise()`), `stored.py` plans a document
already stored, and `api.py` gives the two routes (`POST /api/reconcile/candidates`, `GET
/api/reconcile/candidates/{id}`); `decisions.py` keeps what was offered and chosen, `learning.py` (no database in
it) and `fits.py` learn from it (`pangloss reconcile learn`); `suggest.py` (no database in it) decides what to suggest,
`marking.py` what leaves a document for the worker that writes it, `suggesting.py` (`pangloss reconcile worker`), `judging.py` (no database in it) what a project's judge in it is given and answers (`Asked`, `Unchanged`, `Leave`, `Suggest`). It knows the parts only through `pangloss_vectors.parts`, and the stand-ins only
through `unknowns_of`. implementation_docs/reconcile.md; implementation_docs/similarity-build-plan.md, phases 10 and 11"""

lazy from pangloss_reconcile.candidates import (
    Candidate,
    Found,
    TooManyUnknowns,
    candidates_of,
)

# (what a project's judge is given and answers, `RECONCILE_SUGGEST_WITH`: so that it can type its function)
lazy from pangloss_reconcile.judging import Asked, Leave, Suggest, Unchanged

__all__ = [
    "Asked",
    "Candidate",
    "Found",
    "Leave",
    "Suggest",
    "TooManyUnknowns",
    "Unchanged",
    "candidates_of",
    "requires",
]

# (it runs Cypher of its own to find a stored stand-in, and searches through `pangloss_vectors`, which needs both)
requires = {"cypher", "vector_index"}


def _install() -> None:
    # (nothing of the database is imported here: the settings are checked at `initialise()` when the app is installed,
    # and the listener of resolved stand-ins does nothing unless it is)
    from pangloss_reconcile import decisions, marking, settings

    settings.install()
    decisions.install()
    # (the instruction `suggest` of a write, and what marks a document for the worker that suggests)
    marking.install()


_install()
