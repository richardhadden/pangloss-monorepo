"""What a project says about a day, a month, a year or any span of days: a feast, a term day, a market day.

`DateCharacterisation` is abstract: a project subclasses it for what it needs, and the subclass is an ordinary entity
(it is edited, translated and related to other entities like any other):

    class FeastDay(DateCharacterisation):
        saint: list[Saint]

    FeastDay.Create(label="Benedict", use="sarum", rank="major", when={
        "type": "JulianRecurrence", "frequency": "yearly", "month": 3, "month_day": 21, ...})

`when` is a `Recurrence`, the rule it falls by: the days it falls on, in the rule's own calendar (`easter_offset` for
the days that move with Easter), within its lifetime. Or it is `NoRule`, and the characterisation is attached by hand to days, months, years or spans (`/api/calendar/attach`). A repeated event of another model can
fall on a characterisation's days with `feast = "<id of the characterisation>"` in its rule.
"""

from pangloss_dates.models import Recurrence
from pangloss_models.model_bases.embedded import Embedded
from pangloss_models.model_bases.entity import Entity


class NoRule(Embedded):
    """A characterisation that has no rule: it is attached to days, months, years or spans by hand"""


class DateCharacterisation(Entity):
    _meta = Entity.Meta(abstract=True)

    use: str | None = None
    """The liturgical use, or whatever a project divides its characterisations by (`CALENDAR_USE` shows one)"""
    rank: str | None = None
    """The project's own scale"""
    when: Recurrence | NoRule
    """The rule it falls by, or `NoRule` if it is attached by hand"""
