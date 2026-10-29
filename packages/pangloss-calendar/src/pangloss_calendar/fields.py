"""Which fields of the models hold dates.

Every field of a concrete Document or Entity class that is typed with a `pangloss_dates` date (or a list of, or a
union with, one), found once from the model registry. A date in an embedded object inside a document is not
searched (the search is on the fields of the class itself). `CALENDAR_FIELDS = ["Letter.sent", ...]` narrows them
to those fields (a class matches its subclasses).
"""

from dataclasses import dataclass
from types import UnionType
from typing import Annotated, Any, Union, get_args, get_origin

from pangloss_models.model_bases.document import Document
from pangloss_models.model_bases.entity import Entity
from pangloss_models.model_registry import ModelRegistry

from pangloss_calendar.settings import setting


@dataclass(frozen=True)
class DateField:
    model: type
    field: str
    family: str
    """`""`, `"Julian"` or `"Gregorian"`: the prefix of the names of the date types that the field takes"""

    @property
    def name(self) -> str:
        return f"{self.model.__name__}.{self.field}"


def _classes(annotation: Any) -> list[type]:
    origin = get_origin(annotation)
    if origin is Annotated:
        return _classes(get_args(annotation)[0])
    if origin is Union or origin is UnionType or origin is list:
        return [c for arg in get_args(annotation) for c in _classes(arg)]
    return [annotation] if isinstance(annotation, type) else []


def family_of(annotation: Any) -> str | None:
    """The family of the dates a field takes, or None if it takes no date"""
    from pangloss_dates import models

    classes = [c for c in _classes(annotation) if issubclass(c, models.Date)]
    if not classes:
        return None
    names = {c.__name__ for c in classes}
    if any(name.startswith("Julian") for name in names):
        return "Julian"
    if any(name.startswith("Gregorian") for name in names):
        return "Gregorian"
    return ""


def _is_characterisation(model: type) -> bool:
    """(Characterisations are shown as what they are, not as documents with a date)"""
    from pangloss_calendar import models

    return issubclass(model, models.DateCharacterisation)


def calendar_fields(settings: Any = None) -> list[DateField]:
    """The date fields to look in (reads the registry each time: it is cheap, and the registry is what it is when asked)"""
    wanted = setting("CALENDAR_FIELDS", None, settings)
    found = []
    for model in ModelRegistry.all_models().values():
        if not (isinstance(model, type) and issubclass(model, (Document, Entity))):
            continue
        if model._meta.abstract or _is_characterisation(model):
            continue
        for name, info in model.model_fields.items():
            family = family_of(info.annotation)
            if family is None:
                continue
            found.append(DateField(model, name, family))
    if wanted is not None:
        found = [
            f
            for f in found
            if any(
                f.field == field and any(c.__name__ == cls for c in f.model.__mro__)
                for cls, _, field in (w.partition(".") for w in wanted)
            )
        ]
    return sorted(found, key=lambda f: f.name)
