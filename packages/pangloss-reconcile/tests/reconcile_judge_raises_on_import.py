"""A project's judge whose module cannot be imported (`test_reconcile_judging.py`: the import's own error in the
refusal of `RECONCILE_SUGGEST_WITH`; `live/test_reconcile_judge_live.py`: with no setting, never imported)"""

raise RuntimeError("this judge's module is broken")


def judge(asked):  # pragma: no cover
    return None
