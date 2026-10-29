"""`pangloss calendar <command>`: make the days, load the feasts, and look at how it stands (added to the
`pangloss` command for an installed app with a `cli.py`)."""

import asyncio
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

import typer
from pangloss_dates.calendar import Calendar, from_jdn

from pangloss_calendar import settings as calendar_settings
from pangloss_calendar.observances import InvalidObservance, parse

cli = typer.Typer(
    name="calendar",
    help="Days, months, years and feasts",
    no_args_is_help=True,
)


def run_connected[T](ctx: typer.Context, function: Callable[[], Awaitable[T]]) -> T:
    """Run a coroutine function with the database connected"""
    project = ctx.obj
    backend = project.require_database()

    async def main() -> T:
        await backend.connect()
        try:
            return await function()
        finally:
            await backend.disconnect()

    return asyncio.run(main())


def settings_of(ctx: typer.Context) -> Any:
    return ctx.obj.require_settings()


def calendars_of(names: list[str], settings: Any) -> list[Calendar]:
    try:
        return [Calendar(name) for name in names] or [
            calendar_settings.calendar_default(settings)
        ]
    except ValueError as error:
        typer.secho(f"{error}: use julian or gregorian", fg="red", err=True)
        raise typer.Exit(2) from error


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
    """Make the days from 1 January of the first year to 31 December of the last, with their months and
    years in both calendars (again is harmless), and link the observances that are loaded"""
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
    (chosen,) = calendars_of([calendar] if calendar else [], settings)

    async def work():
        made = await graph.seed(first, last, chosen)
        linked = await graph.link_observances([chosen])
        return made, linked

    made, linked = run_connected(ctx, work)
    typer.echo(
        f"{made} days made ({first} to {last}, {chosen.value}); {linked} observance edges"
    )


@cli.command("load-observances")
def load_observances(
    ctx: typer.Context,
    file: Path = typer.Argument(
        ..., exists=True, dir_okay=False, help="A TOML file of observances"
    ),
    calendar: list[str] = typer.Option(
        [],
        "--calendar",
        help="A calendar to link the feasts in (default: CALENDAR_DEFAULT)",
    ),
) -> None:
    """Make or correct the observances in a file (by key) and link them to the days that exist"""
    from pangloss_calendar import graph

    settings = settings_of(ctx)
    try:
        observances = parse(file.read_text(encoding="utf-8"))
    except InvalidObservance as error:
        typer.secho(f"{file}: {error}", fg="red", err=True)
        raise typer.Exit(1) from error
    chosen = calendars_of(calendar, settings)
    edges = run_connected(ctx, lambda: graph.load_observances(observances, chosen))
    typer.echo(f"{len(observances)} observances loaded; {edges} edges")


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
        f"{found['years']} years, {found['observances']} observances"
    )
