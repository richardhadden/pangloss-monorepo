"""The name part of similarity for Pangloss (an app: `INSTALLED_APPS += ["pangloss_names"]`, with
`pangloss_vectors`): the trigrams of an item's names, hashed and weighted by rarity. `maths.py` is the whole of the
computing, with no database in it; `NamesMeta` what a class says of its names (`meta.py`); `part.py` the part
(`"name"`) it registers, at weight 0, so that it counts only in a profile that weighs it.
implementation_docs/similarity-build-plan.md, phase 8"""

lazy from pangloss_names.meta import NamesMeta

__all__ = ["NamesMeta", "requires"]

# (it reads the names with Cypher of its own, and its vectors are searched through the backend's vector index)
requires = {"cypher", "vector_index"}


def _install() -> None:
    # (nothing of the database, nor numpy, is imported here: a client of the SDK imports this package with the
    # models, and `maths` is imported only when a vector is made)
    from pangloss_names import meta, part

    meta.install()
    # (the part: `pangloss_vectors` stores, searches and keeps up what it computes)
    part.install()


_install()
