"""`pangloss calendar <command>`: make the days, link the characterisations, and look at how it stands (added to the
`pangloss` command for an installed app with a `cli.py`)."""

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any

import typer
from pangloss_dates.calendar import Calendar, from_jdn

from pangloss_calendar import settings as calendar_settings

cli = typer.Typer(
    name="calendar",
    help="Days, months, years and what characterises them",
    no_args_is_help=True,
)


def run_connected[T](ctx: typer.Context, function: Callable[[], Awaitable[T]]) -> T:
    """Import and initialise the models, then run a coroutine function with the database connected"""
    from pangloss_models import initialise

    project = ctx.obj
    backend = project.require_database()
    project.import_models()
    initialise()

    async def main() -> T:
        await backend.connect()
        try:
            return await function()
        finally:
            await backend.disconnect()

    return asyncio.run(main())


def settings_of(ctx: typer.Context) -> Any:
    return ctx.obj.require_settings()


def say_link(report) -> str:
    text = f"{report.edges} edges for {report.characterisations} characterisations"
    if report.extended:
        text += f"; {report.extended} days made beyond the span"
    if report.clipped:
        text += f"; {report.clipped} rules reach beyond the calendar (only the days within it are linked)"
    if report.outside:
        text += (
            f"; {report.outside} rules are wholly beyond the calendar and have no edges"
        )
    return text


@cli.command()
def seed(
    ctx: typer.Context,
    first: int | None = typer.Option(
        None, "--from", help="First year (default: CALENDAR_FIRST_YEAR)"
    ),
    last: int | None = typer.Option(
        None, "--to", help="Last year (default: CALENDAR_LAST_YEAR)"
    ),
    calendar: str | None = typer.Option(
        None,
        "--calendar",
        help="The calendar the years are in (default: CALENDAR_DEFAULT)",
    ),
) -> None:
    """Make the days from 1 January of the first year to 31 December of the last, with their months and years in both
    calendars (again is harmless), then link the characterisations that have a rule"""
    from pangloss_calendar import graph

    settings = settings_of(ctx)
    first = first if first is not None else calendar_settings.first_year(settings)
    last = last if last is not None else calendar_settings.last_year(settings)
    if first is None or last is None:
        typer.secho(
            "Give --from and --to, or set CALENDAR_FIRST_YEAR and CALENDAR_LAST_YEAR "
            "(there is no default span)",
            fg="red",
            err=True,
        )
        raise typer.Exit(2)
    if first > last:
        typer.secho(f"{first} is after {last}", fg="red", err=True)
        raise typer.Exit(2)
    try:
        chosen = (
            Calendar(calendar)
            if calendar
            else calendar_settings.calendar_default(settings)
        )
    except ValueError as error:
        typer.secho(f"{error}: use julian or gregorian", fg="red", err=True)
        raise typer.Exit(2) from error

    async def work():
        made = await graph.seed(first, last, chosen)
        low, high = calendar_settings.reach_days(settings)
        span = calendar_settings.span_days(settings)
        return made, await graph.link_rules(low, high, span)

    try:
        made, report = run_connected(ctx, work)
    except calendar_settings.NoSpan:
        made, report = run_connected(ctx, lambda: graph.seed(first, last, chosen)), None
    typer.echo(f"{made} days made ({first} to {last}, {chosen.value})")
    if report is not None:
        typer.echo(say_link(report))


@cli.command()
def link(ctx: typer.Context) -> None:
    """Make again the edges from days to the characterisations whose rule falls on them (after a characterisation has
    been made or changed). What was attached by hand is not touched. Rules are linked within the span and the margin
    beyond it (CALENDAR_EXTEND_MARGIN_YEARS, 10 by default), where days are made if they are missing; anything further
    out is left alone."""
    from pangloss_calendar import graph

    settings = settings_of(ctx)
    try:
        low, high = calendar_settings.reach_days(settings)
        span = calendar_settings.span_days(settings)
    except calendar_settings.NoSpan as error:
        typer.secho(str(error), fg="red", err=True)
        raise typer.Exit(2) from error
    report = run_connected(ctx, lambda: graph.link_rules(low, high, span))
    typer.echo(say_link(report))


@cli.command()
def status(ctx: typer.Context) -> None:
    """How much of the calendar there is"""
    from pangloss_calendar import graph

    found = run_connected(ctx, graph.status)
    if not found["days"]:
        typer.echo("No days: run `pangloss calendar seed`")
        return
    first = from_jdn(found["first"], Calendar.JULIAN)
    last = from_jdn(found["last"], Calendar.JULIAN)
    typer.echo(
        f"{found['days']} days (Julian {first.year}-{first.month:02d}-{first.day:02d} to "
        f"{last.year}-{last.month:02d}-{last.day:02d}), {found['months']} months, "
        f"{found['years']} years, {found['characterised']} characterisation edges"
    )
