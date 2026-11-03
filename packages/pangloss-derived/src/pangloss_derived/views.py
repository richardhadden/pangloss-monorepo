"""What a derived fact is read as: `SameFamily.View` (its ends and values, its context, and, when read one at a time, its
justifications: "why"), and `SameFamily.Where`, a filter of the facts of the class. Keys are camelCase in JSON, as the
other views of the API are."""

import datetime
import typing
from typing import TYPE_CHECKING, Any, Literal
from uuid import UUID

from pangloss_models.search_where import Written
from pydantic import BaseModel, ConfigDict, Field, create_model
from pydantic.alias_generators import to_camel

if TYPE_CHECKING:
    from pangloss_derived.declare import Derived


class Read(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class Ref(Read):
    """An entity or a head document, as a derived fact names it"""

    id: UUID | str
    type: str
    label: str | None = None


class Evidence(Ref):
    published: bool = True


class Context(Read):
    patterns: list[dict[str, Any]] = Field(default_factory=list)
    """For each pattern of the rule: the node it matched, and the semantic spaces it is in"""
    relations: list[dict[str, Any]] = Field(default_factory=list)
    """For each relation of the rule that bound a variable: the wrappers it passed through, and the properties of its
    edge (`{"percent": 40}`)"""


class JustificationView(Read):
    """One way the fact was derived: by which rule, from which documents, through what"""

    key: str
    rule: str
    description: str = ""
    types: list[str] = Field(default_factory=list)
    nodes: list[str] = Field(default_factory=list)
    evidence: list[Evidence] = Field(default_factory=list)
    context: Context = Field(default_factory=Context)
    context_labels: list[str] = Field(default_factory=list)
    derived_at: datetime.datetime | None = None


class DerivedView(Read):
    """A derived fact"""

    id: str
    type: str
    context_labels: list[str] = Field(default_factory=list)
    qualified_only: bool = False
    """Every justification has some context (a negation, an uncertain identification...): none is plain"""
    types: list[str] = Field(default_factory=list)
    """The types of the rules that derive it"""
    justification_count: int = 0
    justifications: list[JustificationView] | None = None
    """(When the fact is read by itself: the justifications the reader can see)"""
    derived: bool = True


class DerivedWhere(Written):
    """A filter of the facts of a class: each relation field by an id (or anything with one), each literal by its
    value; `plain` (only facts with a plain justification: `True`; only those with none: `False`), `context_label` (a
    justification has it in its context), `rule_type` (a rule of this type derives it). In a search, as `derived_` of
    an entity's `Where` (its JSON has the class as `type`)"""

    _model: typing.ClassVar["type[Derived] | None"] = None

    plain: bool | None = None
    context_label: str | None = None
    rule_type: str | None = None

    def to_json(self) -> Any:
        written = {
            name: ids(value) if name in self.relation_fields() else value
            for name, value in super().to_json().items()
        }
        if self._model is not None:
            return {"type": self._model.__name__, "where": written}
        return written

    @classmethod
    def relation_fields(cls) -> set[str]:
        model = cls._model
        if model is None:
            return set()
        return {f.name for f in model._fields.values() if f.kind == "relation"}


def ids(value: Any) -> Any:
    if isinstance(value, (UUID, str)) or value is None:
        return str(value) if value is not None else None
    return str(getattr(value, "id", value))


def make_views(model: type[Derived]) -> None:
    fields: dict[str, Any] = {}
    filters: dict[str, Any] = {}
    for field in model._fields.values():
        if field.kind == "relation":
            fields[field.name] = (Ref, ...)
            filters[field.name] = (Any, None)
        else:
            fields[field.name] = (field.model | None, None)
            filters[field.name] = (field.model | None, None)
    model.View = create_model(
        f"{model.__name__}View",
        __base__=DerivedView,
        __module__=model.__module__,
        __doc__=model.__doc__ or f"A derived {model.__name__}",
        type=(typing.cast(Any, Literal)[model.__name__], model.__name__),
        **fields,
    )
    model.Where = create_model(
        f"{model.__name__}Where",
        __base__=DerivedWhere,
        __module__=model.__module__,
        __doc__=f"A filter of the derived {model.__name__} facts",
        **filters,
    )
    model.Where._model = model
