"""A stored version, upgraded to the models of now, and what is wrong with it: a *draft*"""

import dataclasses
from typing import Any

from pangloss_core import settings as core_settings
from pydantic import ValidationError

from pangloss_history.schema_position import schema_position
from pangloss_history.store import HistoryRecord
from pangloss_history.upgrade import Problem, upgrade


@dataclasses.dataclass
class Draft:
    data: Any
    problems: list[Problem]
    upgraded: bool

    @property
    def blocking(self) -> list[Problem]:
        return [p for p in self.problems if p.blocking]


def installed_apps() -> list[str]:
    settings = core_settings.__dict__.get("SETTINGS")
    return list(settings.INSTALLED_APPS) if settings is not None else []


def validation_problems(model: Any, data: Any) -> list[Problem]:
    """What the model's `Update` finds wrong with the content"""
    try:
        model.Update.model_validate(data)
    except ValidationError as error:
        return [
            Problem(
                "validation",
                item["msg"],
                path=".".join(str(part) for part in item["loc"]) or None,
                old_value=item.get("input")
                if isinstance(item.get("input"), (str, int, float, bool))
                else None,
            )
            for item in error.errors()
        ]
    return []


def make_draft(record: HistoryRecord, model: Any) -> Draft:
    apps = installed_apps()
    data = record.data()
    problems: list[Problem] = []
    upgraded = record.schema_position != schema_position(apps)
    if upgraded:
        result = upgrade(data, record.schema_position, apps)
        data, problems = result.data, result.problems
    return Draft(data, [*problems, *validation_problems(model, data)], upgraded)
