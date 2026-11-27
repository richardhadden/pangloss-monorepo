"""Comparison of statements for Pangloss (an app: `INSTALLED_APPS += ["pangloss_compare"]`): which statements tell
of one event, and how they stand to each other. Being built (implementation_docs/spaces-and-comparison-plan.md, phase
6): so far `CompareMeta`, what a class says of its comparison, its checks at `initialise()` and the readers of it
(`meta.py`: `compare_meta`, `compared_classes`, `identifying_fields`, `related`, `common_class`, `space_compared`,
`orientation_of`). implementation_docs/compare.md"""

lazy from pangloss_compare.meta import CompareMeta

__all__ = ["CompareMeta"]


def _install() -> None:
    from pangloss_compare import meta

    meta.install()


_install()
