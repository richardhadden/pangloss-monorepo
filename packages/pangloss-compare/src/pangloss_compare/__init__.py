"""Comparison of statements for Pangloss (an app: `INSTALLED_APPS += ["pangloss_compare"]`): which statements tell
of one event, and how they stand to each other. Being built (implementation_docs/spaces-and-comparison-plan.md, phase
6): so far `CompareMeta`, what a class says of its comparison, its checks at `initialise()` and the readers of it
(`meta.py`: `compare_meta`, `compared_classes`, `identifying_fields`, `related`, `common_class`, `space_compared`,
`orientation_of`); the verdict on two statements as plain data (`maths.py`) and each class's rules for it
(`rules.py`); stored statements read as that data (`reading.py`: `read`); the statements a statement is compared with
by rule (`pairs.py`: `by_rule`, `pairs_of`); its setting (`settings.py`: `COMPARE_MOST_PAIRS`); what a person says
of two statements (`models.py`: `EventJudgement`, which the project's class cites them from) and those read for a
statement's pairs (`judgements.py`); a statement compared with its pairs, a person's judgement overriding
(`compare.py`: `compare`), and its route, `GET /api/compare/{type}/{ref}` (`api.py`).
implementation_docs/compare.md"""

lazy from pangloss_compare.meta import CompareMeta
lazy from pangloss_compare.models import EventJudgement

__all__ = ["CompareMeta", "EventJudgement", "requires"]

# (it reads stored statements with Cypher of its own: `reading.py`, `pairs.py`)
requires = {"cypher"}


def _install() -> None:
    from pangloss_models import hooks

    from pangloss_compare import meta, settings

    meta.install()
    # (the settings checked at `initialise()`)
    settings.install()
    # (which classes are compared, told to the interface: its section asks the route of those only)
    if meta.definition_extras not in hooks.definition_extras:
        hooks.definition_extras.append(meta.definition_extras)
    # (a judgement is never changed once made: the interface offers no Edit of one)
    if meta.never_updated not in hooks.not_updated:
        hooks.not_updated.append(meta.never_updated)


_install()
