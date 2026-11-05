"""A document is dateable by a trait: it has a `date`, and its reference view says when it was"""

from typing import Annotated

import pytest
from pangloss_dates.bounds import SortBy
from pangloss_dates.calendar import Calendar, to_jdn
from pangloss_models import initialise
from pangloss_models.export import export_models
from pangloss_models.model_bases.document import Document
from pangloss_models.model_bases.entity import Entity
from pangloss_models.model_bases.labels import labels_for_model
from pydantic import ValidationError

J = Calendar.JULIAN


@pytest.fixture
def dates():
    # (the registry is emptied before each test, so the modules make their classes again)
    import importlib

    from pangloss_dates import dateable, gregorian, julian, models

    for module in (models, julian, gregorian, dateable):
        importlib.reload(module)
    return models, dateable, julian


def exact(year, month=None, day=None, **extra):
    return {"type": "ExactDate", "year": year, "month": month, "day": day, **extra}


def written(model, **fields):
    return model.Create(label="x", **fields)._to_db_model()


def test_a_dateable_document_has_a_date_and_its_sort_days(dates):
    models, dateable, _ = dates

    class Event(Document, dateable.Dateable):
        pass

    initialise()
    assert "date" in Event.Create.model_fields
    # (what is worked out is not the client's to write)
    assert "date_sort_day" not in Event.Create.model_fields
    event = written(Event, date=exact(1500, 3, 2, calendar="julian"))
    assert event.date_sort_day == to_jdn(1500, 3, 2, J)
    assert event.date_end_sort_day == event.date_sort_day
    assert event.date_text == "1500-03-02"


def test_the_date_is_in_the_reference_view(dates):
    _, dateable, _ = dates

    class Event(Document, dateable.Dateable):
        pass

    initialise()
    assert {"date_sort_day", "date_end_sort_day", "date_text"} <= set(
        Event.ReferenceView.model_fields
    )
    view = Event.ReferenceView.model_validate(
        {
            "id": "01a1ab5c-037c-7058-9284-37a8dc3c01b5",
            "type": "Event",
            "label": "x",
            "date_sort_day": 2269004,
            "date_text": "1500",
        }
    )
    assert view.model_dump(by_alias=True)["dateText"] == "1500"


def test_a_dateable_read_before_its_date_was_stamped_has_none(dates):
    """(a document written before its class was dateable has no copy until it is saved again or migrated)"""
    _, dateable, _ = dates

    class Event(Document, dateable.Dateable):
        pass

    initialise()
    view = Event.ReferenceView.model_validate(
        {"id": "01a1ab5c-037c-7058-9284-37a8dc3c01b5", "type": "Event", "label": "x"}
    )
    assert view.date_sort_day is None and view.date_text is None


def test_an_entity_can_be_dateable_too(dates):
    _, dateable, _ = dates

    class Battle(Entity, dateable.SingleDateable):
        pass

    initialise()
    battle = written(Battle, date=exact(1513, 9, 9))
    assert battle.date_text == "1513-09-09"


@pytest.mark.parametrize(
    ("date", "text"),
    [
        (exact(1500), "1500"),
        (exact(1500, 3), "1500-03"),
        (
            {"type": "DateRange", "not_before": exact(1500), "not_after": exact(1502)},
            "1500–1502",
        ),
        (
            {
                "type": "DateRange",
                "not_before": exact(1500, 3),
                "not_after": {"type": "UnknownDate"},
            },
            "≥ 1500-03",
        ),
        (
            {
                "type": "DateRange",
                "not_before": {"type": "UnknownDate"},
                "not_after": exact(1502),
            },
            "≤ 1502",
        ),
        ({"type": "EDTFDate", "edtf": "1500~"}, "1500~"),
        ({"type": "UnknownDate"}, "?"),
        (
            {"type": "Period", "start": exact(1500), "end": exact(1520)},
            "1500–1520",
        ),
        (
            {"type": "Period", "start": exact(1500), "end": {"type": "OngoingDate"}},
            "1500–…",
        ),
        (
            {"type": "Period", "start": {"type": "UnknownDate"}, "end": exact(1520)},
            "?–1520",
        ),
        (
            {
                "type": "Recurrence",
                "frequency": "yearly",
                "weekdays": [],
                "excluded_days": [],
                "month": 3,
                "month_day": 21,
                "start": exact(1500),
                "end": exact(1520),
            },
            "↻ 1500–1520",
        ),
    ],
)
def test_the_date_text_uses_no_words(dates, date, text):
    _, dateable, _ = dates

    class Event(Document, dateable.Dateable):
        pass

    initialise()
    assert written(Event, date=date).date_text == text


def test_a_period_has_the_day_its_end_sorts_by(dates):
    _, dateable, _ = dates

    class Office(Document, dateable.PeriodDateable):
        pass

    initialise()
    office = written(
        Office,
        date={
            "type": "Period",
            "calendar": "julian",
            "start": exact(1500, calendar="julian"),
            "end": exact(1520, 6, 1, calendar="julian"),
        },
    )
    assert (
        office.date_sort_day == (to_jdn(1500, 1, 1, J) + to_jdn(1500, 12, 31, J)) // 2
    )
    assert office.date_end_sort_day == to_jdn(1520, 6, 1, J)


def test_single_and_period_dateables_take_only_their_kinds(dates):
    _, dateable, _ = dates

    class Birth(Document, dateable.SingleDateable):
        pass

    class Office(Document, dateable.PeriodDateable):
        pass

    initialise()
    period = {"type": "Period", "start": exact(1500), "end": exact(1520)}
    with pytest.raises(ValidationError):
        written(Birth, date=period)
    with pytest.raises(ValidationError):
        written(Office, date=exact(1500))
    # (that nothing is known is said by either)
    assert written(Birth, date={"type": "UnknownDate"}).date_text == "?"
    assert written(Office, date={"type": "UnknownDate"}).date_text == "?"


def test_a_class_may_narrow_the_date(dates):
    _, dateable, julian = dates

    class Event(Document, dateable.Dateable):
        date: julian.JulianDate

    initialise()
    with pytest.raises(ValidationError):
        written(Event, date=exact(1500, calendar="gregorian"))
    assert (
        written(Event, date={"type": "JulianExactDate", "year": 1500}).date_text
        == "1500"
    )


def test_a_sort_default_on_the_date_is_what_is_copied(dates):
    """(the field's markers are applied before the copy is made)"""
    models, dateable, _ = dates

    class Birth(Document, dateable.Dateable):
        date: Annotated[models.Date, models.SortDefault(SortBy.EARLIEST_STRICT)]

    initialise()
    birth = written(Birth, date=exact(1500, calendar="julian"))
    assert birth.date_sort_day == to_jdn(1500, 1, 1, J)


def test_the_copy_is_made_again_on_update(dates):
    _, dateable, _ = dates

    class Event(Document, dateable.Dateable):
        pass

    initialise()
    update = Event.Update.model_validate(
        {
            "id": "01a1ab5c-037c-7058-9284-37a8dc3c01b5",
            "type": "Event",
            "label": "x",
            "date": exact(1600),
        }
    )
    assert update._to_db_model().date_text == "1600"


def test_which_models_are_dateable(dates):
    _, dateable, _ = dates

    class Event(Document, dateable.Dateable):
        pass

    class Birth(Event, dateable.SingleDateable):
        pass

    class Note(Document):
        pass

    initialise()
    assert dateable.is_dateable(Event) and dateable.is_dateable(Birth)
    assert not dateable.is_dateable(Note)
    exported = export_models()["models"]
    assert "Dateable" in exported["Event"]["traits"]
    assert {"Dateable", "SingleDateable"} <= set(exported["Birth"]["traits"])
    assert exported["Note"]["traits"] == []
    # (the traits are heritable: they are labels of the nodes, to search or to point to "anything dateable")
    assert {"Dateable", "SingleDateable"} <= set(labels_for_model(Birth, "Document"))
