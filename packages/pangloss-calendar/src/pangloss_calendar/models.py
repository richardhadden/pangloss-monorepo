"""What a project says about a day, a month, a year or any span of days: a feast, a term day, a market day.

`DateCharacterisation` is abstract: a project subclasses it for what it needs, and the subclass is an ordinary entity
(it is edited, translated and related to other entities like any other):

    class FeastDay(DateCharacterisation):
        saint: list[Saint]
        use: str | None = None     # (anything else a project wants to say of one: a liturgical use, a rank...)

    FeastDay.Create(label="Benedict", use="sarum", saint=[...], when={
        "type": "JulianRecurrence", "frequency": "yearly", "month": 3, "month_day": 21, ...})

`when` says whether it repeats or not, by its kind: a `Recurrence` is the rule it falls by, every year (or week, or
month), in the rule's own calendar (`easter_offset` for the days that move with Easter), within its lifetime; an
`ExactDate`, a `DateRange` or an `EDTFDate` is one day (as roughly known as the date says: a year, a month, a range),
once; a `Period` is a span of days, once (Lent 735; the plague). Or it is `NoRule`, and the characterisation is attached
by hand to days, months, years or spans (`/api/calendar/attach`). A repeated event of another model can fall on a
characterisation's days with `feast = "<id of the characterisation>"` in its rule.
"""

from pangloss_dates.models import DateRange, EDTFDate, ExactDate, Period, Recurrence
from pangloss_models.model_bases.embedded import Embedded
from pangloss_models.model_bases.entity import Entity


class NoRule(Embedded):
    """A characterisation that has no rule: it is attached to days, months, years or spans by hand"""


class DateCharacterisation(Entity):
    _meta = Entity.Meta(abstract=True)

    when: Recurrence | ExactDate | DateRange | EDTFDate | Period | NoRule
    """Repeated (a `Recurrence`: the rule it falls by), once on one day (an `ExactDate`, `DateRange` or `EDTFDate`), once over
    a span (a `Period`), or `NoRule` if it is attached by hand"""
