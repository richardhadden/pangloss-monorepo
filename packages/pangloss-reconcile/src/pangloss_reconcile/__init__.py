"""Reconciliation for Pangloss (an app: `INSTALLED_APPS += ["pangloss_reconcile"]`, with `pangloss_vectors` and its
parts): for each stand-in of a document (an unknown, `pangloss_vectors.unknowns_of`: review's `Unreconciled`), the
entities it may be, found and scored by the parts of similarity, and nothing written. `candidates.py` finds them
(`candidates_of`), `score.py` scores them (no database in it), `settings.py` holds the settings
(`RECONCILE_PROFILE`, `RECONCILE_FETCH`, `RECONCILE_WEIGHTS`, checked at `initialise()`), `stored.py` plans a document
already stored, and `api.py` gives the two routes (`POST /api/reconcile/candidates`, `GET
/api/reconcile/candidates/{id}`). It knows the parts only through `pangloss_vectors.parts`, and the stand-ins only
through `unknowns_of`. implementation_docs/reconcile.md; implementation_docs/similarity-build-plan.md, phase 10"""

lazy from pangloss_reconcile.candidates import (
    Candidate,
    Found,
    TooManyUnknowns,
    candidates_of,
)

__all__ = ["Candidate", "Found", "TooManyUnknowns", "candidates_of", "requires"]

# (it runs Cypher of its own to find a stored stand-in, and searches through `pangloss_vectors`, which needs both)
requires = {"cypher", "vector_index"}


def _install() -> None:
    # (nothing of the database is imported here: the settings are checked at `initialise()` when the app is installed)
    from pangloss_reconcile import settings

    settings.install()


_install()
