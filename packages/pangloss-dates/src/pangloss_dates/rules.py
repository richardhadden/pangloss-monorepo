"""Dates in the rules of `pangloss-derived`: a variable of a date (`d: Var[Date]`, or of one family, `Var[JulianDate]`)
stands for the date of a field, and these constraints compare two of them by their bounds (day numbers, so the two may be
in different calendars):

    @rule
    def contemporaries(a: Var[Person], b: Var[Person], d1: Var[Date], d2: Var[Date]):
        return Contemporaries.Derive(first=a, second=b).when(
            HoldsOffice.Where(person=a, when=d1),
            HoldsOffice.Where(person=b, when=d2),
            overlaps(d1, d2),
        )

Each takes the **fuzzy** bounds by default (the range allowing for doubt: `1500~` reaches into 1499 and 1501), and the
**strict** bounds (as stated) with `strict=True`. So `overlaps` and `within` are generous by default (the dates might
overlap), and `before`, `after` and `during` are cautious (the one is before the other even allowing for doubt).

Needs `pangloss-derived`.
"""

import dataclasses
from typing import Any

from pangloss_derived import Constraint, Var


def is_date(model: Any) -> bool:
    """Whether the class is a date (of `pangloss_dates.models.Date`, by name: the tests make the family again)"""
    return isinstance(model, type) and any(
        c.__name__ == "Date" and c.__module__ == "pangloss_dates.models"
        for c in model.__mro__
    )


def _bounds(strict: bool) -> tuple[str, str]:
    which = "strict" if strict else "fuzzy"
    return f"earliest_{which}", f"latest_{which}"


@dataclasses.dataclass(frozen=True)
class DateConstraint(Constraint):
    a: Var
    b: Var
    strict: bool = False

    def variables(self) -> list[Var]:
        return [self.a, self.b]

    def check(self) -> str | None:
        for variable in self.variables():
            model = variable.model
            if not is_date(model):
                return (
                    f"{variable.name!r} is a Var[{getattr(model, '__name__', model)}], not a variable of a date "
                    "(Var[Date], or of a family: Var[JulianDate])"
                )
        return None

    def describe(self) -> str:
        suffix = ", strict=True" if self.strict else ""
        return f"{self.word}({self.a.name}, {self.b.name}{suffix})"

    word = "dates"


@dataclasses.dataclass(frozen=True)
class Overlaps(DateConstraint):
    """The two dates have a day in common (they might, by the fuzzy bounds; they do as stated, by the strict)"""

    word = "overlaps"

    def cypher(self, names, param) -> str:
        a, b = names(self.a), names(self.b)
        earliest, latest = _bounds(self.strict)
        return f"({a}.{earliest} <= {b}.{latest} AND {b}.{earliest} <= {a}.{latest})"


@dataclasses.dataclass(frozen=True)
class Before(DateConstraint):
    """The first ends before the second begins (whatever the doubt, by the fuzzy bounds; as stated, by the strict)"""

    word = "before"

    def cypher(self, names, param) -> str:
        a, b = names(self.a), names(self.b)
        earliest, latest = _bounds(self.strict)
        return f"{a}.{latest} < {b}.{earliest}"


@dataclasses.dataclass(frozen=True)
class During(DateConstraint):
    """The first lies within the second"""

    word = "during"

    def cypher(self, names, param) -> str:
        a, b = names(self.a), names(self.b)
        earliest, latest = _bounds(self.strict)
        return f"({b}.{earliest} <= {a}.{earliest} AND {a}.{latest} <= {b}.{latest})"


@dataclasses.dataclass(frozen=True)
class Within(DateConstraint):
    """The gap between the two dates is at most `days` (none, if they overlap): "within a year of each other" is
    `within(d1, d2, days=365)`"""

    days: int = 0
    word = "within"

    def describe(self) -> str:
        suffix = ", strict=True" if self.strict else ""
        return f"within({self.a.name}, {self.b.name}, days={self.days}{suffix})"

    def check(self) -> str | None:
        if not isinstance(self.days, int) or self.days < 0:
            return f"days must be a whole number of days, not {self.days!r}"
        return super().check()

    def cypher(self, names, param) -> str:
        a, b = names(self.a), names(self.b)
        earliest, latest = _bounds(self.strict)
        gap = param(self.days)
        return f"({a}.{earliest} - {b}.{latest} <= {gap} AND {b}.{earliest} - {a}.{latest} <= {gap})"


def overlaps(a: Var[Any], b: Var[Any], *, strict: bool = False) -> Constraint:
    """The two dates have a day in common"""
    return Overlaps(a, b, strict)


def before(a: Var[Any], b: Var[Any], *, strict: bool = False) -> Constraint:
    """`a` ends before `b` begins"""
    return Before(a, b, strict)


def after(a: Var[Any], b: Var[Any], *, strict: bool = False) -> Constraint:
    """`a` begins after `b` ends"""
    return Before(b, a, strict)


def during(a: Var[Any], b: Var[Any], *, strict: bool = False) -> Constraint:
    """`a` lies within `b`"""
    return During(a, b, strict)


def within(a: Var[Any], b: Var[Any], days: int, *, strict: bool = False) -> Constraint:
    """The gap between the two is at most `days` (none, if they overlap)"""
    return Within(a, b, strict, days)
