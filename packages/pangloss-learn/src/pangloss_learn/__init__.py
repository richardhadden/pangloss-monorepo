"""Fitting a weighted model from people's decisions, with no database and nothing of Pangloss in it (`maths.py` is
the whole of it): `fit` (a logistic regression), `Model` (plain data, to and from JSON, `Model.score`), `compare`
(is a fitted model better than a score set by hand, on decisions it was not fitted on), `compare_calls` (the same of
a model that says yes or no of a whole decision, against always answering the commoner or a score set by hand;
`CallsCompared`, its answer with how many calls differ, and a check that allows for chance).
implementation_docs/similarity-build-plan.md, phase 11; implementation_docs/learn.md"""

lazy from pangloss_learn.maths import (
    CallsCompared,
    Compared,
    Example,
    Model,
    Unfittable,
    compare,
    compare_calls,
    fit,
    folds_of,
)

__all__ = [
    "CallsCompared",
    "Compared",
    "Example",
    "Model",
    "Unfittable",
    "compare",
    "compare_calls",
    "fit",
    "folds_of",
]
