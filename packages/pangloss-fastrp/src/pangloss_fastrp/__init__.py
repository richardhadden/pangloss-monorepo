"""The graph part of similarity for Pangloss (an app: `INSTALLED_APPS += ["pangloss_fastrp"]`, with
`pangloss_vectors`): FastRP over the joined graph of documents and entities. `maths.py` is the whole of the
computing, with no database in it; `maps.py` the rules it follows, worked out of the models; `FastRPMeta` what a
class says of them; `cypher_reader.py` what it reads of the database; `part.py` the parts it registers: `"graph"`,
and the second, `"actual"`, in which a document joins by what the walk says of its path (`walk.py`), idle unless a
profile weighs it. implementation_docs/similarity-build-plan.md, phase 3; implementation_docs/spaces-and-comparison-plan.md,
step 5.4"""

from pangloss_models import ModelRegistry

lazy from pangloss_fastrp.meta import FastRPMeta
lazy from pangloss_fastrp.maps import graph_maps

__all__ = ["FastRPMeta", "graph_maps", "requires"]

# (its reader runs Cypher of its own, and its vectors are searched through the backend's vector index)
requires = {"cypher", "vector_index"}


def _install() -> None:
    # (nothing of the database, nor numpy, is imported here: a client of the SDK imports this package with the
    # models, and `maths` is imported only when the maps or the vectors are wanted)
    from pangloss_fastrp import maps, meta, part, settings

    meta.install()
    # (`FASTRP_DEGREE_WEIGHTS` checked at `initialise()`)
    settings.install()
    # (the part: `pangloss_vectors` stores, searches and keeps up what it computes)
    part.install()
    for hooks in (ModelRegistry.on_reset, ModelRegistry.after_finalise):
        if maps.forget not in hooks:
            hooks.append(maps.forget)


_install()
