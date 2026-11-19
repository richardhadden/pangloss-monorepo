"""Matches criteria for Pangloss (an app: `INSTALLED_APPS += ["pangloss_criteria"]`): someone a source describes and
does not name, stored as a search and linked to everyone it fits. implementation_docs/matches-criteria.md"""

from pangloss_models import ModelRegistry, hooks

lazy from pangloss_criteria.evaluate import Evaluation, evaluate
lazy from pangloss_criteria.meta import CriteriaMeta, NoCriteria
lazy from pangloss_criteria.models import MatchesCriteria
lazy from pangloss_criteria.pattern import (
    SearchPattern,
    check_stored,
    resolve_merged,
)
lazy from pangloss_criteria.worker import idle, run_pending, settled

__all__ = [
    "CriteriaMeta",
    "Evaluation",
    "MatchesCriteria",
    "NoCriteria",
    "SearchPattern",
    "check_stored",
    "evaluate",
    "idle",
    "requires",
    "resolve_merged",
    "run_pending",
    "settled",
]

# (the worker reads the descriptions of the heads it claims with Cypher of its own, and claims them from the kit's
# queue: checked at start-up, see `pangloss_core.storage.check_requirements`)
requires = {"cypher"}


def pending_work_of(model: type) -> list[str]:
    """(`hooks.pending_work`) a write of a head that can hold a description, or that the criteria of one could
    reach, leaves work for the worker"""
    from pangloss_criteria import holders

    return holders.pending_work_of(model)


def wake_worker(event: hooks.WriteEvent) -> None:
    """(`hooks.after_write`) wake the worker of this process, if it runs"""
    from pangloss_criteria.worker import worker

    worker.listen(event)


def wake_for_marked(model: type) -> None:
    """(`hooks.work_marked`) wake the worker of this process, if it runs"""
    from pangloss_criteria.worker import worker

    worker.marked(model)


def forget_models() -> None:
    """(`ModelRegistry.on_reset`) what was worked out of the models is of the models before"""
    from pangloss_criteria import holders

    holders.forget()


def _install() -> None:
    # (nothing of the database is imported here: a client of the SDK imports this package with the models)
    if pending_work_of in hooks.pending_work:
        return
    hooks.pending_work.append(pending_work_of)
    # (the mark of an update keeps what the document named and was before it: `pangloss_cypher.pending`)
    hooks.pending_keeps_before.add("criteria")
    hooks.after_write.append(wake_worker)
    hooks.work_marked.append(wake_for_marked)
    ModelRegistry.on_reset.append(forget_models)


_install()
