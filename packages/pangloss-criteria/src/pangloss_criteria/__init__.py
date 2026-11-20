"""Matches criteria for Pangloss (an app: `INSTALLED_APPS += ["pangloss_criteria"]`): someone a source describes and
does not name, stored as a search and linked to everyone it fits. implementation_docs/matches-criteria.md"""

from typing import Any

from pangloss_models import ModelRegistry, hooks

lazy from pangloss_criteria.access import (
    BrokenDescription,
    BrokenPage,
    Candidate,
    CandidatesPage,
    Preview,
    Reference,
    Resolved,
    broken,
    candidates,
    preview,
    resolve,
    settled,
)
lazy from pangloss_criteria.evaluate import Evaluation, evaluate
lazy from pangloss_criteria.maintenance import CriteriaWorkerBusy, Rebuilt, rebuild
lazy from pangloss_criteria.meta import CriteriaMeta, NoCriteria
lazy from pangloss_criteria.migrating import rewrite
lazy from pangloss_criteria.models import MatchesCriteria
lazy from pangloss_criteria.pattern import (
    SearchPattern,
    check_stored,
    resolve_merged,
)
lazy from pangloss_criteria.worker import idle, run_pending

__all__ = [
    "BrokenDescription",
    "BrokenPage",
    "Candidate",
    "CandidatesPage",
    "CriteriaMeta",
    "CriteriaWorkerBusy",
    "Evaluation",
    "MatchesCriteria",
    "NoCriteria",
    "Preview",
    "Rebuilt",
    "Reference",
    "Resolved",
    "SearchPattern",
    "broken",
    "candidates",
    "check_stored",
    "evaluate",
    "idle",
    "preview",
    "rebuild",
    "requires",
    "resolve",
    "resolve_merged",
    "rewrite",
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


def described() -> bool:
    """Whether the models have descriptions at all (the app's class is declared once its models are imported, as
    those of an installed app are): a project without them has no criteria to keep"""
    return "MatchesCriteria" in ModelRegistry.all_models()


async def rewrite_in_migration(tx: Any, step: hooks.MigrationStep) -> None:
    """(`hooks.migration_changes`) the stored criteria brought through a change of a migration, in its transaction"""
    if not described():
        return
    from pangloss_criteria import migrating

    await migrating.in_migration(tx, step)


async def check_after_migrate(migrated: hooks.Migrated) -> None:
    """(`hooks.after_migrate`) the stored criteria checked against the models, once they describe the data"""
    if not described():
        return
    from pangloss_criteria import migrating

    await migrating.after_migrate(migrated)


def forget_models() -> None:
    """(`ModelRegistry.on_reset`) what was worked out of the models is of the models before. (Only of the modules
    that are loaded: loading `holders` would load `models`, which declares the class in the registry just reset)"""
    import sys

    for name in ("pangloss_criteria.holders", "pangloss_criteria.analysis"):
        module = sys.modules.get(name)
        if module is not None:
            module.forget()


def _install() -> None:
    # (nothing of the database is imported here: a client of the SDK imports this package with the models)
    if pending_work_of in hooks.pending_work:
        return
    hooks.pending_work.append(pending_work_of)
    # (the mark of an update keeps what the document named and was before it: `pangloss_cypher.pending`)
    hooks.pending_keeps_before.add("criteria")
    hooks.after_write.append(wake_worker)
    hooks.work_marked.append(wake_for_marked)
    # (what a migration does to the criteria: `pangloss_criteria.migrating`)
    hooks.migration_changes.append(rewrite_in_migration)
    hooks.after_migrate.append(check_after_migrate)
    ModelRegistry.on_reset.append(forget_models)


_install()
