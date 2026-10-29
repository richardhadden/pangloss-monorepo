"""The commands that need no database: refusals"""

from types import SimpleNamespace

from pangloss_calendar.cli import cli
from typer.testing import CliRunner

runner = CliRunner()
project = SimpleNamespace(require_settings=lambda: SimpleNamespace())


def test_seed_without_a_span_is_refused():
    result = runner.invoke(cli, ["seed"], obj=project)
    assert result.exit_code == 2
    assert "CALENDAR_FIRST_YEAR" in result.output


def test_seed_with_the_years_the_wrong_way_round_is_refused():
    result = runner.invoke(cli, ["seed", "--from", "1600", "--to", "1500"], obj=project)
    assert result.exit_code == 2


def test_link_without_a_span_is_refused():
    result = runner.invoke(cli, ["link"], obj=project)
    assert result.exit_code == 2
    assert "CALENDAR_FIRST_YEAR" in result.output
