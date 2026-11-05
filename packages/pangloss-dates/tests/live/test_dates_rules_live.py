"""Dates in the rules of `pangloss-derived`: `Var[Date]` and the constraints on two dates' bounds"""

import importlib
from typing import no_type_check

import pytest
from pangloss_models import Document, Entity, initialise
from pangloss_testing.live import run

from pangloss_derived import Derived, PanglossDerivedError, Var, rule
from pangloss_derived.worker import run_pending_derivations

pytestmark = pytest.mark.asyncio(loop_scope="session")


@no_type_check
def models(constraint):
    from pangloss_dates import rules
    from pangloss_dates import models as dates

    importlib.reload(dates)  # (the registry was reset: the date family again)
    Date = dates.Date

    class Person(Entity):
        pass

    class Office(Entity):
        pass

    class HoldsOffice(Document):
        person: Person
        office: Office
        when: Date

    class Contemporaries(Derived):
        """Held office at the same time"""

        _meta = Derived.Meta(symmetric=True)
        first: Person
        second: Person

    @rule
    def contemporaries(a: Var[Person], b: Var[Person], d1: Var[Date], d2: Var[Date]):
        return Contemporaries.Derive(first=a, second=b).when(
            HoldsOffice.Where(person=a, when=d1),
            HoldsOffice.Where(person=b, when=d2),
            constraint(rules, d1, d2),
        )

    initialise()
    return Person, Office, HoldsOffice, Contemporaries


def year(y, approximate=False):
    return (
        {"type": "EDTFDate", "edtf": f"{y:04d}~"}
        if approximate
        else {"type": "ExactDate", "year": y}
    )


def span(y1, y2):
    return {"type": "DateRange", "not_before": year(y1), "not_after": year(y2)}


async def pairs(Contemporaries):
    page = await Contemporaries.list(page_size=100)
    return sorted(tuple(sorted([v.first.label, v.second.label])) for v in page.results)


@no_type_check
async def write(db_driver, constraint, dates):
    # (each scenario starts afresh: the people of the last would pair with those of this one)
    run(db_driver, "MATCH (n) WHERE NOT n:PGUser DETACH DELETE n")
    Person, Office, HoldsOffice, Contemporaries = models(constraint)
    office = await Office.Create(label="O").save()
    for name, when in dates.items():
        person = await Person.Create(label=name).save()
        await HoldsOffice.Create(
            label=f"{name} holds",
            person={"type": "Person", "id": person.id},
            office={"type": "Office", "id": office.id},
            when=when,
        ).save()
    await run_pending_derivations()
    return Contemporaries


@no_type_check
async def test_overlaps_by_the_fuzzy_bounds_and_strictly(clear_database, db_driver):
    dates = {
        "A": span(800, 810),
        "B": span(805, 815),
        "C": span(811, 820),
        "D": year(821, approximate=True),
    }
    # (fuzzy: "about 821" reaches into 820; so D might overlap C, but as stated it does not)
    C = await write(db_driver, lambda r, a, b: r.overlaps(a, b), dates)
    assert await pairs(C) == [("A", "B"), ("B", "C"), ("C", "D")]
    C = await write(db_driver, lambda r, a, b: r.overlaps(a, b, strict=True), dates)
    assert await pairs(C) == [("A", "B"), ("B", "C")]


@no_type_check
async def test_before_during_and_within(clear_database, db_driver):
    dates = {
        "A": span(800, 810),
        "B": span(805, 815),
        "C": span(811, 820),
        "D": span(830, 831),
    }
    Before = await write(db_driver, lambda r, a, b: r.before(a, b), dates)
    # (symmetric: each pair once, whichever is before)
    assert await pairs(Before) == [("A", "C"), ("A", "D"), ("B", "D"), ("C", "D")]
    During = await write(
        db_driver,
        lambda r, a, b: r.during(a, b),
        {"A": span(800, 820), "B": span(805, 810), "C": span(815, 825)},
    )
    assert await pairs(During) == [("A", "B")]
    # (within ten years, by the gap between the ranges: C to D is 10 years less a day)
    Within = await write(db_driver, lambda r, a, b: r.within(a, b, days=3660), dates)
    assert await pairs(Within) == [("A", "B"), ("A", "C"), ("B", "C"), ("C", "D")]
    # (within a year: A ends the day before C begins)
    Within = await write(db_driver, lambda r, a, b: r.within(a, b, days=365), dates)
    assert await pairs(Within) == [("A", "B"), ("A", "C"), ("B", "C")]


@no_type_check
async def test_a_date_constraint_refuses_a_variable_that_is_not_a_date(clear_database):
    from pangloss_dates import rules
    from pangloss_dates import models as dates

    importlib.reload(dates)
    Date = dates.Date

    class Person(Entity):
        pass

    class HoldsOffice(Document):
        person: Person
        when: Date

    class Contemporaries(Derived):
        _meta = Derived.Meta(symmetric=True)
        first: Person
        second: Person

    @rule
    def contemporaries(a: Var[Person], b: Var[Person], d1: Var[Date], d2: Var[Date]):
        return Contemporaries.Derive(first=a, second=b).when(
            HoldsOffice.Where(person=a, when=d1),
            HoldsOffice.Where(person=b, when=d2),
            rules.overlaps(a, d2),
        )

    with pytest.raises(
        PanglossDerivedError,
        match=r"overlaps\(a, d2\): 'a' is a Var\[Person\], not a variable of a date",
    ):
        initialise()
