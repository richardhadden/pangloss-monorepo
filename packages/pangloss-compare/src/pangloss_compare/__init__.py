"""Comparison of statements for Pangloss (an app: `INSTALLED_APPS += ["pangloss_compare"]`): which statements tell
of one event, and how they stand to each other. Being built (implementation_docs/spaces-and-comparison-plan.md, phase
6): so far `CompareMeta`, what a class says of its comparison, its checks at `initialise()` and the readers of it
(`meta.py`: `compare_meta`, `compared_classes`, `identifying_fields`, `related`, `common_class`, `space_compared`,
`orientation_of`); the verdict on two statements as plain data (`maths.py`) and each class's rules for it
(`rules.py`); stored statements read as that data (`reading.py`: `read`); the statements a statement is compared with
by rule (`pairs.py`: `by_rule`, `pairs_of`); its setting (`settings.py`: `COMPARE_MOST_PAIRS`).
implementation_docs/compare.md"""

lazy from pangloss_compare.meta import CompareMeta

__all__ = ["CompareMeta", "requires"]

# (it reads stored statements with Cypher of its own: `reading.py`, `pairs.py`)
requires = {"cypher"}


def _install() -> None:
    from pangloss_compare import meta, settings

    meta.install()
    # (the settings checked at `initialise()`)
    settings.install()


_install()
