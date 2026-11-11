"""Labels worked out from what an item holds: `Meta(label_template=...)` (implementation_docs/label-templates.md).

A template is text with placeholders, `"Birth of {person}[ at {place}][, {date}]"`. It is worked out on what a client
holds (camelCase JSON, references as `{type, id, label}`), in the same way here and in the interface
(`interface-core/src/schema/labelTemplate.ts`); the cases of `tests/label_cases.json` are run by both. On a write the
server works out each automatic label again (`fill_labels` in the backend), and keeps that one.

    template    := (text | placeholder | group)*
    placeholder := "{" path ("|" filter)* "}"          path: field names, dotted (bequests.recipient)
    group       := "[" template "]"                    left out if any placeholder in it is empty
    filter      := name ("(" "text" ("," "text")* ")")?
    escapes     := \\{ \\} \\[ \\] \\\\  (and \\" in the text of a filter)
"""

import re
from collections.abc import Awaitable, Callable, Iterable, Iterator, Mapping
from dataclasses import dataclass, field
from typing import Annotated, Any

from pydantic import BeforeValidator

from pangloss_models.exceptions import AtString, PanglossMetaError, did_you_mean

# --- the template, as declared ----------------------------------------------------------------------------


@dataclass(frozen=True)
class Text:
    text: str


@dataclass(frozen=True)
class Filter:
    name: str
    args: tuple[str, ...] = ()
    # (the template of `each`, read once)
    template: tuple[Part, ...] | None = None


@dataclass(frozen=True)
class Placeholder:
    path: tuple[str, ...]
    filters: tuple[Filter, ...] = ()


@dataclass(frozen=True)
class Group:
    parts: tuple[Part, ...]


type Part = Text | Placeholder | Group

# The filters, and how many texts each takes (`join` one or two: the separator, and the one before the last)
FILTERS: dict[str, tuple[int, int]] = {
    "join": (0, 2),
    "first": (0, 0),
    "last": (0, 0),
    "count": (0, 0),
    "default": (1, 1),
    "each": (1, 1),
    "lower": (0, 0),
    "capitalise": (0, 0),
}

NAME = re.compile(r"[A-Za-z_]\w*")


class _Parser:
    def __init__(self, source: str):
        self.source = source
        self.at = 0

    def fail(self, problem: str) -> PanglossMetaError:
        return PanglossMetaError(
            f"label_template {self.source!r}: {problem} (at {self.at})",
            at_string=AtString("label_template", self.source),
        )

    def template(self, until: str | None = None) -> tuple[Part, ...]:
        parts: list[Part] = []
        text: list[str] = []

        def flush():
            if text:
                parts.append(Text("".join(text)))
                text.clear()

        while self.at < len(self.source):
            char = self.source[self.at]
            if char == "\\":
                if self.at + 1 >= len(self.source):
                    raise self.fail("a \\ at the end")
                text.append(self.source[self.at + 1])
                self.at += 2
            elif char == "{":
                flush()
                self.at += 1
                parts.append(self.placeholder())
            elif char == "[":
                flush()
                self.at += 1
                inner = self.template(until="]")
                parts.append(Group(inner))
            elif char == "]":
                if until != "]":
                    raise self.fail(
                        "a ] with no [ before it (write \\] for the character)"
                    )
                flush()
                self.at += 1
                return tuple(parts)
            elif char == "}":
                raise self.fail("a } with no { before it (write \\} for the character)")
            else:
                text.append(char)
                self.at += 1
        if until is not None:
            raise self.fail("a [ that is not closed")
        flush()
        return tuple(parts)

    def space(self):
        while self.at < len(self.source) and self.source[self.at] == " ":
            self.at += 1

    def name(self, what: str) -> str:
        self.space()
        found = NAME.match(self.source, self.at)
        if not found:
            raise self.fail(f"the name of {what} expected")
        self.at = found.end()
        self.space()
        return found.group()

    def placeholder(self) -> Placeholder:
        path = [self.name("a field")]
        while self.source.startswith(".", self.at):
            self.at += 1
            path.append(self.name("a field"))
        filters: list[Filter] = []
        while self.source.startswith("|", self.at):
            self.at += 1
            filters.append(self.filter())
        if not self.source.startswith("}", self.at):
            raise self.fail("a } expected")
        self.at += 1
        return Placeholder(tuple(path), tuple(filters))

    def filter(self) -> Filter:
        name = self.name("a filter")
        if name not in FILTERS:
            raise self.fail(
                f"there is no filter '{name}'." + did_you_mean(name, FILTERS)
            )
        args: list[str] = []
        if self.source.startswith("(", self.at):
            self.at += 1
            self.space()
            while not self.source.startswith(")", self.at):
                args.append(self.quoted())
                self.space()
                if self.source.startswith(",", self.at):
                    self.at += 1
                    self.space()
                elif not self.source.startswith(")", self.at):
                    raise self.fail("a , or a ) expected")
            self.at += 1
            self.space()
        least, most = FILTERS[name]
        if not least <= len(args) <= most:
            wanted = str(least) if least == most else f"{least} to {most}"
            raise self.fail(f"'{name}' takes {wanted} text(s), not {len(args)}")
        template = None
        if name == "each":
            template = _Parser(args[0]).template()
        return Filter(name, tuple(args), template)

    def quoted(self) -> str:
        if not self.source.startswith('"', self.at):
            raise self.fail('a text in "" expected')
        self.at += 1
        text: list[str] = []
        while self.at < len(self.source):
            char = self.source[self.at]
            if char == "\\" and self.at + 1 < len(self.source):
                # (kept as it is, but for \" and \\: the text of `each` is a template, with escapes of its own)
                following = self.source[self.at + 1]
                text.append(following if following in '"\\' else char + following)
                self.at += 2
            elif char == '"':
                self.at += 1
                return "".join(text)
            else:
                text.append(char)
                self.at += 1
        raise self.fail('a text in "" that is not closed')


def parse(source: str) -> tuple[Part, ...]:
    """The parts of a template (`PanglossMetaError` if it cannot be read)"""
    return _Parser(source).template()


class LabelTemplate:
    """How the label of a model is worked out from what it holds: one template, or several, tried in order (the
    first that has no empty placeholder outside a `[...]` group is taken)"""

    __slots__ = ("alternatives", "parsed")

    def __init__(self, *alternatives: str):
        if not alternatives or not all(isinstance(a, str) for a in alternatives):
            raise PanglossMetaError(
                f"LabelTemplate{alternatives!r}: one template or more, each a string"
            )
        self.alternatives: tuple[str, ...] = tuple(alternatives)
        self.parsed: tuple[tuple[Part, ...], ...] = tuple(
            parse(a) for a in alternatives
        )

    def __eq__(self, other: object) -> bool:
        return (
            isinstance(other, LabelTemplate) and other.alternatives == self.alternatives
        )

    def __hash__(self) -> int:
        return hash(self.alternatives)

    def __repr__(self) -> str:
        return f"LabelTemplate({', '.join(map(repr, self.alternatives))})"

    def export(self) -> dict[str, Any]:
        return {"alternatives": list(self.alternatives)}


class Formatter:
    """A label made by a function an app registers, `"app:name"`, in Python (`register_label_formatter`) and in its
    interface module (`labelFormatters` of the manifest): for an embedded object such as a date, which no template
    says well"""

    __slots__ = ("name",)

    def __init__(self, name: str):
        if not isinstance(name, str) or not re.fullmatch(r"\w+:\w+", name):
            raise PanglossMetaError(
                f"Formatter({name!r}): the name is 'app:name'",
                at_string=AtString("label_template", str(name)),
            )
        self.name = name

    def __eq__(self, other: object) -> bool:
        return isinstance(other, Formatter) and other.name == self.name

    def __hash__(self) -> int:
        return hash(self.name)

    def __repr__(self) -> str:
        return f"Formatter({self.name!r})"

    def export(self) -> dict[str, Any]:
        return {"formatter": self.name}


def as_label_template(value: Any) -> LabelTemplate | Formatter | None:
    """What `Meta(label_template=...)` is given, as it is kept: a string is a template of its own"""
    if value is None or isinstance(value, (LabelTemplate, Formatter)):
        return value
    if isinstance(value, str):
        return LabelTemplate(value)
    raise PanglossMetaError(
        f"label_template={value!r}: a string, a LabelTemplate(...) or a Formatter(...)"
    )


# What a `Meta` keeps of `label_template=` (inherited, as the other options of a `Meta` are)
LabelTemplateOption = Annotated[
    LabelTemplate | Formatter | None, BeforeValidator(as_label_template)
]


# --- formatters ---------------------------------------------------------------------------------------------

# A formatter is given the JSON of the object (camelCase, as a client holds it) and gives its text, or None
LabelFormatter = Callable[[Mapping[str, Any]], str | None]
_formatters: dict[str, LabelFormatter] = {}


def register_label_formatter(name: str, formatter: LabelFormatter) -> None:
    """Named `"app:name"` by `Formatter(...)`; the app's interface module gives the same name in `labelFormatters`"""
    Formatter(name)
    _formatters[name] = formatter


def label_formatter(name: str) -> LabelFormatter | None:
    return _formatters.get(name)


# --- what the models are, to the interpreter ---------------------------------------------------------------

# Kinds without a label of their own whose text is what they hold
WRAPPERS = ("ReifiedRelation", "Conjunction", "SemanticSpace")
# The keys of a node that are not what it holds
NOT_CONTENTS = ("meta", "edgeProperties", "type", "id", "label", "labelAuto")
# The keys a walk through an item does not go into: what is said of it, not what it holds (`contextLabels` name the
# items around it, by type and id)
NOT_WALKED = ("meta", "edgeProperties", "contextLabels", "semanticSpaces")


@dataclass(frozen=True)
class LabelField:
    name: str
    key: str
    kind: str


@dataclass(frozen=True)
class LabelModel:
    """What the interpreter needs to know of a model: the same as the interface reads from the export"""

    kind: str
    require_label: bool
    template: LabelTemplate | Formatter | None
    fields: tuple[LabelField, ...]

    def field(self, name: str) -> LabelField | None:
        return next((f for f in self.fields if f.name == name), None)

    @property
    def content_keys(self) -> list[str]:
        """What a wrapper holds: a reified relation its `target`, anything else its relations"""
        if self.kind == "ReifiedRelation":
            return ["target"]
        return [f.key for f in self.fields if f.kind == "relation"]

    @property
    def derives_label(self) -> bool:
        """Its label is kept, and worked out by a template"""
        return self.require_label and isinstance(self.template, LabelTemplate)


@dataclass
class LabelSchema:
    models: Mapping[str, LabelModel]
    formatters: Callable[[str], LabelFormatter | None] = label_formatter

    def model_of(self, value: Any) -> LabelModel | None:
        if isinstance(value, dict) and isinstance(value.get("type"), str):
            return self.models.get(value["type"])
        return None

    @classmethod
    def from_json(cls, models: Mapping[str, Any], **kwargs) -> LabelSchema:
        """From what `label_schema_json` gives (the shared cases)"""
        return cls(
            {
                name: LabelModel(
                    kind=model["kind"],
                    require_label=model["requireLabel"],
                    template=_template_from_json(model.get("labelTemplate")),
                    fields=tuple(LabelField(**f) for f in model["fields"]),
                )
                for name, model in models.items()
            },
            **kwargs,
        )


def _template_from_json(value: Any) -> LabelTemplate | Formatter | None:
    if not value:
        return None
    if "formatter" in value:
        return Formatter(value["formatter"])
    return LabelTemplate(*value["alternatives"])


def label_schema_json(schema: LabelSchema) -> dict[str, Any]:
    return {
        name: {
            "kind": model.kind,
            "requireLabel": model.require_label,
            "labelTemplate": model.template.export() if model.template else None,
            "fields": [
                {"name": f.name, "key": f.key, "kind": f.kind} for f in model.fields
            ],
        }
        for name, model in sorted(schema.models.items())
    }


# --- working it out --------------------------------------------------------------------------------------


def _flat(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return [item for each in value for item in _flat(each)]
    return [value]


def resolve(value: Any, path: Iterable[str], schema: LabelSchema) -> list[Any]:
    """What a path reaches from `value`: through a list, each item; through a wrapper that has no such field
    (a reified relation, a conjunction), what it holds"""
    current = _flat(value)
    for name in path:
        current = [found for item in current for found in _step(item, name, schema)]
    return current


def _open(values: list[Any], schema: LabelSchema) -> list[Any]:
    return [held for item in values for held in _opened(item, schema)]


def _opened(item: Any, schema: LabelSchema) -> list[Any]:
    """A wrapper with no template of its own, as what it holds (so that `count` and `join` take its members: `each`,
    `first` and `last` take the wrappers themselves); anything else as it is"""
    model = schema.model_of(item)
    if model is None or model.kind not in WRAPPERS or model.template is not None:
        return [item]
    return [
        opened
        for key in model.content_keys
        for held in _flat(item.get(key))
        for opened in _opened(held, schema)
    ]


def _step(item: Any, name: str, schema: LabelSchema) -> list[Any]:
    model = schema.model_of(item)
    if model is None:
        # (an annotated value, `{value, certainty}`: its keys are its fields)
        return _flat(item.get(name)) if isinstance(item, dict) else []
    if found := model.field(name):
        return _flat(item.get(found.key))
    if model.kind in WRAPPERS:
        return [
            reached
            for key in model.content_keys
            for held in _flat(item.get(key))
            for reached in _step(held, name, schema)
        ]
    return []


def _number(value: float) -> str:
    # (as JavaScript writes it: 2.0 is "2")
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


def text_of(value: Any, schema: LabelSchema) -> str | None:
    """A value as text in a label (None: nothing)"""
    if value is None:
        return None
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return _number(value)
    if isinstance(value, str):
        return value or None
    if isinstance(value, list):
        texts = [t for t in (text_of(v, schema) for v in value) if t]
        return ", ".join(texts) or None
    if not isinstance(value, dict):
        return None
    if isinstance(label := value.get("label"), str) and label:
        return label
    model = schema.model_of(value)
    if model is None:
        return text_of(value.get("value"), schema) if "value" in value else None
    if isinstance(model.template, Formatter):
        formatter = schema.formatters(model.template.name)
        return (formatter(value) or None) if formatter else None
    if isinstance(model.template, LabelTemplate):
        return render(model.template, value, schema)
    if model.kind in WRAPPERS:
        return text_of(
            [held for key in model.content_keys for held in _flat(value.get(key))],
            schema,
        )
    return None


SPACES = re.compile(r"\s+")


def render(template: LabelTemplate, value: Any, schema: LabelSchema) -> str | None:
    """The label `template` gives for `value` (None: none of its alternatives gives one)"""
    return render_parsed(template.parsed, value, schema)


def render_parsed(
    alternatives: Iterable[tuple[Part, ...]], value: Any, schema: LabelSchema
) -> str | None:
    for parts in alternatives:
        made = _parts(parts, value, schema)
        if made is not None and (made := SPACES.sub(" ", made).strip()):
            return made
    return None


def _parts(parts: Iterable[Part], value: Any, schema: LabelSchema) -> str | None:
    out: list[str] = []
    for part in parts:
        if isinstance(part, Text):
            out.append(part.text)
        elif isinstance(part, Group):
            if (inner := _parts(part.parts, value, schema)) is not None:
                out.append(inner)
        else:
            text = _placeholder(part, value, schema)
            if text is None:
                return None
            out.append(text)
    return "".join(out)


def _placeholder(part: Placeholder, value: Any, schema: LabelSchema) -> str | None:
    # (a list of values until a filter makes them one text)
    values: list[Any] = resolve(value, part.path, schema)
    for each in part.filters:
        match each.name:
            case "each":
                assert each.template is not None
                values = [
                    made
                    for item in values
                    if (made := render_parsed([each.template], item, schema))
                ]
            case "first":
                values = values[:1]
            case "last":
                values = values[-1:]
            case "count":
                values = _open(values, schema)
                values = [str(len(values))] if values else []
            case "join":
                texts = [
                    t for t in (text_of(v, schema) for v in _open(values, schema)) if t
                ]
                separator = each.args[0] if each.args else ", "
                last = each.args[1] if len(each.args) > 1 else separator
                joined = (
                    separator.join(texts[:-1]) + last + texts[-1]
                    if len(texts) > 1
                    else "".join(texts)
                )
                values = [joined] if joined else []
            case "default":
                if not text_of(values, schema):
                    values = [each.args[0]]
            case "lower" | "capitalise":
                text = text_of(values, schema)
                if text and each.name == "lower":
                    text = text.lower()
                elif text:
                    text = text[0].upper() + text[1:]
                values = [text] if text else []
    return text_of(_open(values, schema), schema)


def is_reference(value: dict[str, Any]) -> bool:
    """A reference to an item of its own (`{type, id, label}`), not one written here"""
    return all(key in NOT_CONTENTS for key in value)


def is_automatic(value: dict[str, Any]) -> bool:
    """Its label is to be worked out: it says so, or says nothing and has none"""
    auto = value.get("labelAuto")
    return auto is True or (auto is None and not value.get("label"))


@dataclass
class Derived:
    """What `derive_labels` worked out, by the id of each node whose class has a template"""

    labels: dict[str, tuple[str | None, bool]] = field(default_factory=dict)
    # (the path to each node whose template gave nothing, for one that must have a label)
    empty: list[tuple[tuple[str | int, ...], str]] = field(default_factory=list)


def derive_labels(root: Any, schema: LabelSchema, *, is_root: bool = True) -> Derived:
    """Works out the labels of `root` and of what it holds, innermost first, in place: `label`, and `labelAuto`
    true. A node whose label was written by hand gets `labelAuto` false"""
    derived = Derived()

    def visit(value: Any, path: tuple[str | int, ...], top: bool) -> None:
        if isinstance(value, list):
            for index, item in enumerate(value):
                visit(item, (*path, index), False)
            return
        if not isinstance(value, dict):
            return
        if not top and is_reference(value):
            return
        for key, item in value.items():
            if key not in NOT_WALKED:
                visit(item, (*path, key), False)
        model = schema.model_of(value)
        if model is None or not model.derives_label:
            return
        if is_automatic(value):
            assert isinstance(model.template, LabelTemplate)
            label = render(model.template, value, schema)
            value["label"] = label or ""
            value["labelAuto"] = True
            if not label:
                derived.empty.append((path, value["type"]))
        else:
            value["labelAuto"] = False
        if isinstance(value.get("id"), str):
            derived.labels[value["id"]] = (value.get("label"), value["labelAuto"])

    visit(root, (), is_root)
    return derived


def walk_dicts(value: Any) -> Iterator[dict[str, Any]]:
    if isinstance(value, list):
        for item in value:
            yield from walk_dicts(item)
    elif isinstance(value, dict):
        yield value
        for key, item in value.items():
            if key not in NOT_WALKED:
                yield from walk_dicts(item)


# --- on a write ----------------------------------------------------------------------------------------------

_schema: tuple[frozenset[int], LabelSchema] | None = None


def models_schema() -> LabelSchema:
    """The schema of the initialised models, as the interface has it (made from `export_models()`, once for each
    set of models)"""
    global _schema
    from pangloss_models.export import export_models
    from pangloss_models.model_registry import ModelRegistry

    key = frozenset(map(id, ModelRegistry._models))
    if _schema is None or _schema[0] != key:
        exported = export_models()["models"]
        _schema = (
            key,
            LabelSchema(
                {
                    name: LabelModel(
                        kind=model["kind"],
                        require_label=model["requireLabel"],
                        template=_template_of_class(ModelRegistry, name),
                        fields=tuple(
                            LabelField(f["name"], f["key"], f["kind"])
                            for f in model["fields"]
                        ),
                    )
                    for name, model in exported.items()
                }
            ),
        )
    return _schema[1]


def _template_of_class(registry: Any, name: str) -> LabelTemplate | Formatter | None:
    model = registry._model_dict.get(name)
    return getattr(getattr(model, "_meta", None), "label_template", None)


def _below(value: Any) -> Iterator[dict[str, Any]]:
    """Every object under the root, not the root itself"""
    if isinstance(value, dict):
        for key, item in value.items():
            if key not in NOT_WALKED:
                yield from walk_dicts(item)
    elif isinstance(value, list):
        yield from walk_dicts(value)


# Reads the labels of items by their ids (those it does not find are left out): the backend's
LabelReader = Callable[[list[str]], Awaitable[Mapping[str, str]]]


async def fill_labels(instance: Any, read_labels: LabelReader) -> None:
    """Works out the labels of a document (or an entity) about to be written, and of what it holds, where they are
    automatic: on the models for the database (`CreateDB`, `UpdateDB`), before the write is planned. What it refers
    to is named by its label in the database, read by `read_labels` (once, for all of them, and only if a template
    is to be worked out). `PanglossWriteRefused` for a label that must be given and that its template gives nothing
    for"""
    from pydantic import BaseModel
    from pydantic.alias_generators import to_snake

    from pangloss_models.exceptions import PanglossWriteRefused

    schema = models_schema()
    if not any(model.derives_label for model in schema.models.values()):
        return
    data = instance.model_dump(by_alias=True, mode="json")

    def derives(value: dict[str, Any]) -> bool:
        model = schema.model_of(value)
        return model is not None and model.derives_label

    if not derives(data) and not any(
        derives(d) and not is_reference(d) for d in _below(data)
    ):
        return
    unnamed = sorted(
        {
            d["id"]
            for d in _below(data)
            if is_reference(d) and not d.get("label") and isinstance(d.get("id"), str)
        }
    )
    if unnamed:
        found = await read_labels(unnamed)
        for d in _below(data):
            if is_reference(d) and not d.get("label") and d.get("id") in found:
                d["label"] = found[d["id"]]

    derived = derive_labels(data, schema)
    if derived.empty:
        path, type_name = derived.empty[0]
        error = PanglossWriteRefused(
            f"{type_name}: its label_template gives no label for what it holds, and it must have one: give a "
            "label, or fill in what the template names",
            field="label",
        )
        error.path = (
            *(to_snake(p) if isinstance(p, str) else p for p in path),
            "label",
        )
        raise error

    def put_back(value: Any) -> None:
        if isinstance(value, list):
            for item in value:
                put_back(item)
        elif isinstance(value, BaseModel):
            fields = type(value).model_fields
            if "label_auto" in fields and (
                made := derived.labels.get(str(getattr(value, "id", "")))
            ):
                value.label, value.label_auto = made
            for name in fields:
                if name not in ("meta", "edge_properties", "context_labels"):
                    put_back(getattr(value, name, None))

    put_back(instance)
