"""Unions of the models that are given (`Create`, `Update`, ...) as tagged unions.

Pydantic checks the input against every member of a plain union, and against every member again if
none is exact, and a member that holds the union again (an `Order` that orders a statement, which may be an
`Order`) does the same for what is in it, so the time grew with every level of nesting, doubling at each. A tagged
union looks at the input once, and goes straight to the member that it is for.

`type` alone is not enough to tell the member: a reference to a `Person` (`{type, id}`), a new `Person` and
an update of a `Person` are all `Person`. So the tag is worked out from what is given: the members with the `type`
that was given, and of them the one that has the most of the fields it requires, then the most of the
fields given that it knows, then the first in the union. Only the names of the keys are looked at, never
what is below them, so the choice costs nothing however deep the input is. If what is given is wrong, the errors
are those of the member that it was closest to."""

from collections.abc import Mapping
from types import NoneType, UnionType
from typing import Any, Literal, Union, get_args, get_origin

from pydantic import BaseModel, GetCoreSchemaHandler
from pydantic.fields import FieldInfo

from pangloss_models.model_bases.base_models import _CreateDBBase
from pydantic_core import core_schema


def member_type(member: type[BaseModel]) -> Any:
    """The value of the `type` field of a member (`None` if it has none)"""
    field = member.model_fields.get("type")
    if field is None:
        return None
    if field.default is not None and not callable(field.default):
        return field.default
    args = get_args(field.annotation) if get_origin(field.annotation) is Literal else ()
    return args[0] if len(args) == 1 else None


def keys_of(name: str, field: Any) -> set[str]:
    """What a field may be called in the input (its name, and its alias, camelCase)"""
    keys = {name}
    for alias in (field.alias, field.validation_alias):
        if isinstance(alias, str):
            keys.add(alias)
    return keys


def accepts_none(field: Any) -> bool:
    return NoneType in get_args(field.annotation) or field.annotation is None


class MemberShape:
    """What is looked at to choose a member: the type, the keys that must be given, and those that may.

    The `id` of a `CreateDB` is not asked for: it is made when it is not given (`_CreateDBBase.ensure_id`)."""

    def __init__(self, member: type[BaseModel]):
        self.type = member_type(member)
        # (the keys a field may be given by, and whether `None` is a value for it)
        self.required: list[tuple[set[str], bool]] = []
        self.known: set[str] = set()
        makes_id = issubclass(member, _CreateDBBase)
        for name, field in member.model_fields.items():
            keys = keys_of(name, field)
            self.known |= keys
            if field.is_required() and not (name == "id" and makes_id):
                self.required.append((keys, accepts_none(field)))

    def missing(self, given: Mapping[str, Any]) -> int:
        """How many of the required fields are not given (`None` is not a value for a field that does not take it)"""
        return sum(
            1
            for keys, nullable in self.required
            if not any(key in given and (nullable or given[key] is not None) for key in keys)
        )

    def recognised(self, given: Mapping[str, Any]) -> int:
        return sum(1 for key, value in given.items() if key in self.known and value is not None)


class TaggedUnion:
    """Annotation metadata that makes the union it is on a tagged union, choosing the member as above.

    Put on a union of models as `Annotated[A | B | C, TaggedUnion(members)]`; the members are those of the union."""

    def __init__(self, members: list[type[BaseModel]]):
        self.members = members
        self.tags = tags_for(members)
        self._shapes: list[MemberShape] | None = None

    @property
    def shapes(self) -> list[MemberShape]:
        # (made when first used: the fields of the members are not all there when the union is made)
        if self._shapes is None:
            self._shapes = [MemberShape(member) for member in self.members]
        return self._shapes

    def choose(self, value: Any) -> str | None:
        if isinstance(value, BaseModel):
            for index, member in enumerate(self.members):
                if type(value) is member:
                    return self.tags[index]
            for index, member in enumerate(self.members):
                if isinstance(value, member):
                    return self.tags[index]
            return None
        if not isinstance(value, Mapping):
            return None
        shapes = self.shapes
        wanted = value.get("type")
        indexes = [i for i, shape in enumerate(shapes) if shape.type == wanted]
        if not indexes:
            indexes = list(range(len(shapes)))
        best = min(
            indexes,
            key=lambda i: (shapes[i].missing(value), -shapes[i].recognised(value), i),
        )
        return self.tags[best]

    def __get_pydantic_core_schema__(
        self, source: Any, handler: GetCoreSchemaHandler
    ) -> core_schema.CoreSchema:
        return self.tag(handler(source))

    def tag(self, schema: core_schema.CoreSchema) -> core_schema.CoreSchema:
        if schema["type"] == "nullable":
            # (a union that may also be `None`)
            return {**schema, "schema": self.tag(schema["schema"])}  # type: ignore[typeddict-item]
        choices = schema.get("choices") if schema["type"] == "union" else None
        if choices is None or len(choices) != len(self.members):
            # (Pydantic made something else of it: leave it as it is)
            return schema
        return core_schema.tagged_union_schema(
            choices=dict(zip(self.tags, choices)),  # type: ignore[arg-type]
            discriminator=self.choose,
        )


def choose_by_tag(kind: Any, field: FieldInfo) -> FieldInfo:
    """Make the member of the union that a field is chosen as above, if it is a union of models (or that or
    `None`). (A list of them has it in the `Annotated` inside it: `builder.wrap_in_union`; and a kind that is
    discriminated chooses by `type`.)"""
    annotation = field.annotation
    if kind.discriminated or get_origin(annotation) not in (Union, UnionType):
        return field
    members = [a for a in get_args(annotation) if a is not NoneType]
    if len(members) > 1 and all(
        isinstance(m, type) and issubclass(m, BaseModel) for m in members
    ):
        field.metadata = [*field.metadata, TaggedUnion(members)]
    return field


def tags_for(members: list[type[BaseModel]]) -> list[str]:
    """A tag for each member: its name (which is seen in the location of an error), made unique"""
    names = [member.__name__ for member in members]
    return [
        name if names.count(name) == 1 else f"{name}#{index}"
        for index, name in enumerate(names)
    ]
