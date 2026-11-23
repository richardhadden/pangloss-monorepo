# Learning (`pangloss-learn`) 🚧

A small library that fits a weighted model from people's decisions. It is **not an app**: it has no settings, no
models, no database and nothing of Pangloss in it, and depends on numpy alone. **Used by `pangloss-reconcile`**
(step 11.5 of [the build plan](similarity-build-plan.md)): its retraining, `pangloss reconcile learn`, fits a ranking
model with `fit` and compares it with the hand-set score by `compare`, and fits a "none of these" model and compares
it with always answering the commoner by `compare_calls` ([reconcile.md](reconcile.md), "Learning from decisions").
**A model is used at a request** by reconciliation's stored route (step 11.6): `Model.score` of the "none of these"
model of the fit in use, over the head of the list answered, gives `new` ([reconcile.md](reconcile.md), "None of
these"); the ranking model is fitted and recorded, and used by nothing. Comparison (phase 12) is to use it too.

## What it has ✅

```python
from pangloss_learn import Example, compare, fit

examples = [
    Example({"name": 0.97, "graph": 0.41, "shared": 1.1}, yes=True, group="mention-1"),
    Example({"name": 0.97, "graph": 0.12, "shared": 0.0}, yes=False, group="mention-1"),
    ...
]
model = fit(examples, ["name", "graph", "shared"])
model.score({"name": 0.9, "graph": 0.3, "shared": 0.7})     # a likelihood, 0 to 1
found = compare(examples, ["name", "graph", "shared"], lambda f: f["name"] + 0.25 * f["graph"])
found.no_worse                                               # is the fitted model at least as often right
```

- **An example** is one thing that was offered when a person decided: its features (numbers by name), whether it
  was the one taken, and the decision it was offered in (`group`).
- **`fit`** is a logistic regression: the likelihood of "yes" is `1 / (1 + exp(-(w·x + c)))`, found by Newton's
  steps with a ridge (every weight but the constant is pulled towards 0, so that examples a feature divides
  cleanly do not send its weight off). The rows are put in one order first: the same examples, in any order, give
  the same model to the last bit. Features are not rescaled.
- **A `Model`** is plain data (`features`, `weights`, `constant`, how many `examples` and how many `yes`, the
  `ridge`, and `fitted_at`, which the caller says: the maths knows no clock), `to_json()` and `Model.from_json()`.
  `score` refuses features that lack one the model weighs.
- **`compare`** deals the decisions into folds by a seed; for each fold a model is fitted on the others; in each
  decision of the fold, is the one taken the one the model scores highest, and the one the baseline does. A
  decision in which nothing offered was taken is not counted. `Compared(decisions, model, baseline)`.
- **`compare_calls`** is the same question of a model that says yes or no of a whole decision ("none of those
  offered is the one"): each example is a decision by itself; the model's call is "yes" at a likelihood of a half
  or more; it is compared with always answering whichever was the commoner among the examples of the other folds.
  The examples are put in one order first, so any order gives the same answer.
- **`Unfittable`** (a `ValueError`) says why: no features, too few examples, all of one answer, an example without
  a feature, a number that is not one.

## What was measured before it ([the build plan](similarity-build-plan.md), phase 11)

On the planted world, for reconciliation: a fitted **ranking** is no better at size than a score set by hand once
the shared entities are in it, and is much worse fitted on few decisions or on the five a dialog shows. What
fitting buys is the likelihood that a mention is **none of those offered** (AUC 0.80 to 0.87 against 0.6 by the
best score). So a model is to be used only past a least number of decisions and when `compare` says it is no worse.

## Not built ⏳

Comparison's use of it (phase 12).
