"""The time part of similarity for Pangloss (an app: `INSTALLED_APPS += ["pangloss_dates_vectors"]`, with
`pangloss_dates` and `pangloss_vectors`): the dates of a document (`pangloss_dates`) as soft bumps along the years.
`maths.py` is the whole of the computing, with no database in it; `part.py` the part (`"time"`) it registers, at
weight 0, so that it counts only in a profile that weighs it; `settings.py` its settings (`DATES_VECTOR_DIMENSION`,
`DATES_VECTOR_WIDTH`). implementation_docs/similarity-build-plan.md, phase 9"""

__all__ = ["requires"]

# (it reads the dates with Cypher of its own, and its vectors are searched through the backend's vector index)
requires = {"cypher", "vector_index"}


def _install() -> None:
    # (nothing of the database, nor numpy, is imported here: a client of the SDK imports this package with the
    # models, and `maths` is imported only when a vector is made)
    from pangloss_dates_vectors import part, settings

    # (the settings checked at `initialise()`)
    settings.install()
    # (the part: `pangloss_vectors` stores, searches and keeps up what it computes)
    part.install()


_install()
