"""A calendar for Pangloss. The parts that need no database (`days`, `observances`, `views`) are plain Python"""

lazy from pangloss_calendar.models import DateCharacterisation, NoRule

__all__ = ["DateCharacterisation", "NoRule", "requires"]

# (what the storage backend must be able to do: the calendar runs its own Cypher. Checked at start-up, see
# `pangloss_core.storage.check_requirements`)
requires = {"cypher"}
