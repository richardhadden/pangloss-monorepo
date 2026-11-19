"""Matches criteria for Pangloss (an app: `INSTALLED_APPS += ["pangloss_criteria"]`): someone a source describes and
does not name, stored as a search and linked to everyone it fits. implementation_docs/matches-criteria.md"""

lazy from pangloss_criteria.pattern import (
    SearchPattern,
    check_stored,
    resolve_merged,
)

__all__ = [
    "SearchPattern",
    "check_stored",
    "resolve_merged",
]
