"""`pangloss calendar seed`, `link` and `status`, run against the database (on the backend under test)"""

from types import SimpleNamespace
from typing import no_type_check

from calendar_live_support import structure
from pangloss_testing.live import initialise_database, run_command, run_connected

from pangloss_calendar.cli import cli
from test_calendar_characterisations_live import make_feasts, models

# (1500 to 1501, Julian: a leap year and a common one)
SPAN = SimpleNamespace(
    CALENDAR_FIRST_YEAR=1500, CALENDAR_LAST_YEAR=1501, DATES_DEFAULT_CALENDAR="julian"
)


def calendar(backend, settings, *arguments):
    return run_command(cli, backend, *arguments, settings=settings)


@no_type_check
def test_seed_makes_the_days_and_links_the_feasts_and_status_says_how_much_there_is(
    clear_database, clear_calendar, command_backend
):
    FeastDay, _ = models()

    async def prepare():
        await initialise_database()
        await structure()
        await make_feasts(FeastDay)

    run_connected(command_backend, prepare)

    empty = calendar(command_backend, SPAN, "status")
    assert empty.exit_code == 0, empty.output
    assert empty.output.strip() == "No days: run `pangloss calendar seed`"

    seeded = calendar(command_backend, SPAN, "seed")
    assert seeded.exit_code == 0, seeded.output
    made, linked = seeded.output.strip().splitlines()
    assert made == "731 days made (1500 to 1501, julian)"
    # (Benedict and Pentecost each reach beyond the margin, and one feast is wholly outside the calendar)
    assert linked.startswith("44 edges for 3 characterisations")
    assert (
        "rules reach beyond the calendar" in linked
        and "1 rules are wholly beyond the calendar" in linked
    )

    status = calendar(command_backend, SPAN, "status")
    assert status.exit_code == 0, status.output
    # (the days the rules reached were made too, within the margin beyond the span: 1490 to 1511)
    assert status.output.strip() == (
        "7750 days (Julian 1490-03-21 to 1511-06-08), 512 months, 44 years, 44 characterisation edges"
    )

    # (again: the same edges; the days are there)
    linked_again = calendar(command_backend, SPAN, "link")
    assert linked_again.exit_code == 0, linked_again.output
    assert linked_again.output.strip().startswith("44 edges for 3 characterisations")


@no_type_check
def test_seed_with_years_and_no_span_makes_only_the_days(
    clear_database, clear_calendar, command_backend
):
    models()
    run_connected(command_backend, structure)
    no_span = SimpleNamespace(DATES_DEFAULT_CALENDAR="julian")

    seeded = calendar(
        command_backend,
        no_span,
        "seed",
        "--from",
        "1500",
        "--to",
        "1500",
        "--calendar",
        "gregorian",
    )
    assert seeded.exit_code == 0, seeded.output
    assert seeded.output.strip() == "365 days made (1500 to 1500, gregorian)"
    assert (
        "365 days (Julian 1499-12-23 to 1500-12-21)"
        in calendar(command_backend, no_span, "status").output
    )

    wrong = calendar(
        command_backend,
        no_span,
        "seed",
        "--from",
        "1500",
        "--to",
        "1500",
        "--calendar",
        "mayan",
    )
    assert wrong.exit_code == 2
    assert "use julian or gregorian" in wrong.output
