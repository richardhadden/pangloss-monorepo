"""Templates: what a rule writes into a derived document. See implementation_docs/derived.md ("Derived documents").

    DerivedFactoid.Derive(statements=[Sibling.Template(people=[a, b], certainty=p)])

`Model.Template(...)` is shaped like `Model.Create(...)`, but a relation to an entity, and a literal, may be a variable
of the rule. `initialise()` makes one for every class a derived document can hold (and `Derive`, the head of a rule,
for the derived document class itself), checks each template a rule gives against the models (`TemplateCheck`), and
keeps it as data (`TNode`): so it has a hash, `explain` can show it, and the classes of the nodes it writes are known
exactly (which is what the check for loops between rules reads). `fill` makes the payload of one document from it,
given what the variables are.
"""

import dataclasses
import operator
import typing
from collections.abc import Sequence
from functools import reduce
from typing import Annotated, Any, ClassVar

from pangloss_models import Document, Embedded, Entity, ModelRegistry, Var
from pangloss_models.field_definitions import (
    AnnotatedValueFieldDefinition,
    EmbeddedFieldDefinition,
    ListFieldDefinition,
    LiteralFieldDefinition,
    RelationFieldDefinition,
    RelationToCitation,
    RelationToConjunction,
    RelationToDocument,
    RelationToEntity,
    RelationToReifiedRelation,
    RelationToReifiedRelationDocument,
    RelationToSemanticSpace,
)
from pangloss_models.computed import computed_fields
from pangloss_models.search import without_none
from pangloss_models.search_where import StubAnnotation
from pydantic import BaseModel, ConfigDict, TypeAdapter, ValidationError, create_model

from pangloss_derived.declare import Body, Head
from pangloss_derived.documents import derived_document_classes, source_fields
from pangloss_derived.registry import PanglossDerivedError

WRAPPER_OPTIONS = (
    RelationToSemanticSpace,
    RelationToConjunction,
    RelationToReifiedRelation,
    RelationToReifiedRelationDocument,
)


# ---------------------------------------------------------------------------
# What a rule writes
# ---------------------------------------------------------------------------


class TemplateBase(BaseModel):
    """`Sibling.Template(people=[a, b])`: a node of a derived document, as its rule gives it. What each field may
    hold is checked by `initialise()`, which can say which rule it is in and where"""

    model_config = ConfigDict(extra="forbid", arbitrary_types_allowed=True)
    _model: ClassVar[type]
    # (its stub has its `__init__` written out, so that a type checker checks the variables: `pangloss_models.typestubs`)
    _stub_init: ClassVar[bool] = True

    def given(self) -> dict[str, Any]:
        """The fields the rule gave, by name"""
        # (in the order of the class, not of a set: the order the variables are met in is part of what a rule is)
        return {
            name: getattr(self, name)
            for name in type(self).model_fields
            if name in self.model_fields_set
        }


class DeriveDocumentBase(TemplateBase):
    """The head of a rule that derives a document: `DerivedFactoid.Derive(statements=[...])`, then `.when(...)`"""

    def when(
        self,
        *items: Any,
        block: Any = (),
        allow: Any = (),
        status: Sequence[str] | None = None,
    ) -> Body:
        return Head(type(self)._model, {}, self).when(
            *items, block=block, allow=allow, status=status
        )


class Via:
    """In a template, a relation with the properties of its edge (a field of `ViaEdge[Person, Certainty]`):
    `Via(a, Certainty.Template(certainty=p))`. As a `Create` takes the reference with its `edge_properties`"""

    __slots__ = ("edge", "target")

    def __init__(self, target: Any, edge: Any):
        self.target = target
        self.edge = edge

    def __repr__(self) -> str:
        return f"Via({self.target!r}, {self.edge!r})"


# ---------------------------------------------------------------------------
# Making the classes
# ---------------------------------------------------------------------------


def subclasses_of(model: type) -> list[type]:
    return [
        m
        for m in ModelRegistry.all_models().values()
        if isinstance(m, type) and issubclass(m, model)
    ]


def is_generated_here(model: type) -> bool:
    """(a citation node is made by the core, and written by it: not by a template)"""
    return model.__module__ != "pangloss_models.citations"


def left_to_people(option: Any) -> bool:
    """What a relation takes that a template does not write: what stands in for an entity (`hooks.StandIn`: an
    `Unreconciled` is a task for a person), and a wrapper with a relation the server computes (a `MatchesCriteria`:
    its candidates are found for it, and a derived document rests on what is known)"""
    if isinstance(option, RelationToDocument) and option.stands_in_for:
        return True
    return isinstance(option, WRAPPER_OPTIONS) and bool(
        computed_fields(option.base_type).relations
    )


class Reach:
    """The classes a document of a class can hold, as a template names them: documents and embedded objects by
    their own class, a wrapper by its class without its parameters (`InRole`, not `InRole[Person]`), and the edge
    models of its relations"""

    def __init__(self) -> None:
        self.walked: set[type] = set()
        self.templated: dict[type, None] = {}
        self.edge_models: dict[type, None] = {}

    def model(self, model: type, own_class: bool = True) -> None:
        if model in self.walked:
            return
        self.walked.add(model)
        if own_class:
            self.templated[model] = None
        fields = getattr(getattr(model, "_meta", None), "fields", None) or {}
        for definition in fields.values():
            if isinstance(definition, EmbeddedFieldDefinition):
                for option in definition.type_options:
                    for sub in subclasses_of(option.annotated_type):
                        self.model(sub)
            elif isinstance(definition, RelationFieldDefinition):
                for option in definition.type_options:
                    self.option(option)

    def option(self, option: Any) -> None:
        if option.edge_model is not None:
            self.edge_models[option.edge_model] = None
        if isinstance(option, RelationToCitation) or left_to_people(option):
            return
        if isinstance(option, RelationToDocument):
            for sub in subclasses_of(option.annotated_type):
                if is_generated_here(sub):
                    self.model(sub)
        elif isinstance(option, WRAPPER_OPTIONS):
            self.templated[option.base_type] = None
            # (its fields are those of the class with its parameters, which say what each holds)
            self.model(typing.cast(type, option.annotated_type), own_class=False)
            for parameter in option.parameter_type_options.values():
                for inner in parameter.type_options:
                    self.option(inner)


def declared_field(model: Any, name: str) -> Any:
    """The field as a `Create` of the class has it (which says whether it must be given), or, where there is none (an
    edge model; the field of a wrapper that is of its parameter), as the class declares it"""
    create = model.__dict__.get("Create")
    if create is not None and name in create.model_fields:
        return create.model_fields[name]
    return model.model_fields.get(name)


def is_citation_field(definition: Any) -> bool:
    return isinstance(definition, RelationFieldDefinition) and any(
        isinstance(o, RelationToCitation) for o in definition.type_options
    )


def template_field_names(model: Any) -> list[str]:
    """The fields a template of the class has: those a `Create` has, but the citations (the worker fills the
    `DerivedFrom` of a derived document; no other citation is written by a template)"""
    names = []
    create = model.__dict__.get("Create")
    if create is not None and "label" in create.model_fields:
        names.append("label")
    for name, definition in model._meta.fields.items():
        if definition.db_field or is_citation_field(definition):
            continue
        names.append(name)
    return names


def parent_models(model: type) -> list[type]:
    """The declared classes of the same kind that the class is a direct subclass of"""
    return [
        base
        for base in model.__bases__
        if base in ModelRegistry._model_set
        and getattr(base, "__metatype__", None) == getattr(model, "__metatype__", 0)
        and getattr(getattr(base, "_meta", None), "fields", None) is not None
    ]


def make_class(
    model: type, made: dict[type, type[TemplateBase]], name: str = "Template"
) -> type[TemplateBase]:
    known = made.get(model)
    if known is not None and name == "Template":
        return known
    if name == "Template":
        bases = tuple(make_class(parent, made) for parent in parent_models(model))
    else:
        bases = (DeriveDocumentBase,)
    fields: dict[str, Any] = {}
    for field_name in template_field_names(model):
        declared = declared_field(model, field_name)
        required = declared is not None and declared.is_required()
        fields[field_name] = (Any, ...) if required else (Any, None)
    # (a field of a parent that this class does not have, because a field of its own narrows it and fills it
    # (`subclasses_parent_fields`): not asked for here. Given all the same, it is refused as no field of the class)
    for base in bases:
        for inherited in getattr(base, "model_fields", {}):
            if inherited not in fields:
                fields[inherited] = (Any, None)
    template = create_model(
        f"{model.__name__}{name}",
        __base__=bases or TemplateBase,
        __module__=model.__module__,
        __doc__=(
            f"The head of a rule that derives a {model.__name__}"
            if name == "Derive"
            else f"A {model.__name__} in a derived document, as a rule gives it"
        ),
        **fields,
    )
    template._model = model
    if name == "Template":
        made[model] = template
    setattr(model, name, template)
    return template


def var_of(model: Any) -> Any:
    return Var[model]  # (made at runtime: the type is the field's)


def union(members: list[Any]) -> Any:
    unique = list(dict.fromkeys(members))
    return reduce(operator.or_, unique) if unique else Any


def option_annotations(option: Any, made: dict[type, type[TemplateBase]]) -> list[Any]:
    """What a type checker is to take for one option of a relation"""
    if isinstance(option, RelationToCitation) or left_to_people(option):
        return []
    if isinstance(option, RelationToEntity):
        found: list[Any] = [var_of(option.annotated_type)]
        reference = option.annotated_type.__dict__.get("ReferenceSet")
        if reference is not None:
            found.append(reference)
        if option.edge_model is not None:
            found.append(Via)
        return found
    if isinstance(option, RelationToDocument):
        template = made.get(option.annotated_type)
        if template is not None:
            return [template]
        return [made[m] for m in subclasses_of(option.annotated_type) if m in made]
    if isinstance(option, WRAPPER_OPTIONS):
        template = made.get(option.base_type)
        return [template] if template is not None else [Any]
    return [Any]


def stub_annotation_of(
    model: Any, name: str, made: dict[type, type[TemplateBase]]
) -> Any:
    """The type of a template's field as a stub has it (when validated, a field takes anything: `TemplateCheck` says
    what is wrong, with the rule and the place)"""
    if name == "label":
        return var_of(str) | str
    definition = model._meta.fields[name]
    if isinstance(definition, ListFieldDefinition):
        inner: Any = var_of(definition.inner_type) | definition.inner_type
        return list[inner]
    if isinstance(definition, LiteralFieldDefinition):
        base = without_none(definition.annotated_type)
        annotation = var_of(base) | base
        return (
            annotation | None if base is not definition.annotated_type else annotation
        )
    if isinstance(definition, EmbeddedFieldDefinition):
        members = [
            made[m]
            for option in definition.type_options
            for m in subclasses_of(option.annotated_type)
            if m in made
        ]
        annotation = union(members)
        return annotation | None if definition.optional and members else annotation
    if isinstance(definition, RelationFieldDefinition):
        members = [
            a
            for option in sorted(
                definition.type_options, key=lambda o: str(o.annotated_type)
            )
            for a in option_annotations(option, made)
        ]
        if not members or any(m is Any for m in members):
            item: Any = Any
        else:
            item = union(members)
        if definition.wrapper is not None:
            return list[item]
        return item | None if definition.optional and item is not Any else item
    return Any


def make_templates() -> None:
    """Give `Template` to every class a derived document can hold, and `Derive` to each derived document class"""
    every: list[Any] = derived_document_classes()
    heads = [m for m in every if not m._meta.abstract]
    if not heads:
        return
    reach = Reach()
    for head in heads:
        reach.model(head)
    made: dict[type, type[TemplateBase]] = {}
    for model in [*reach.templated, *reach.edge_models]:
        make_class(model, made)
    derives = [make_class(head, made, "Derive") for head in heads]
    for template in [*made.values(), *derives]:
        for name, field in template.model_fields.items():
            try:
                annotation = stub_annotation_of(template._model, name, made)
            except KeyError, TypeError:
                annotation = Any
            field.metadata.append(StubAnnotation(annotation))


# ---------------------------------------------------------------------------
# A template as data
# ---------------------------------------------------------------------------


@dataclasses.dataclass(frozen=True)
class TVar:
    """The value of a variable: of an entity (a reference to it), or a literal"""

    name: str
    entity: bool


@dataclasses.dataclass(frozen=True)
class TValue:
    """A value the rule gives as it is"""

    value: Any


@dataclasses.dataclass(frozen=True)
class TRef:
    """An entity the rule names itself"""

    type: str
    id: str


@dataclasses.dataclass(frozen=True)
class TVia:
    """A reference with the properties of its edge"""

    target: TVar | TRef
    edge: dict[str, Any]


@dataclasses.dataclass(frozen=True)
class TNode:
    """A node to write: of the class `model` (a wrapper's with its parameters, as its payload names it), with its
    fields, each an item (`TVar`, `TValue`, `TRef`, `TVia`, `TNode`) or a tuple of them"""

    model: Any
    fields: dict[str, Any]

    @property
    def type(self) -> str:
        """As a payload names it: a wrapper by its class without its parameters (`InRole`)"""
        return (origin_of(self.model) or self.model).__name__


def origin_of(model: type) -> type | None:
    """The class a class with parameters (`InRole[Person]`) is made from"""
    return (getattr(model, "__pydantic_generic_metadata__", None) or {}).get("origin")


type Item = TVar | TValue | TRef | TVia | TNode


def nodes_of(node: TNode) -> list[TNode]:
    """The node and every node in it"""
    found = [node]
    for value in node.fields.values():
        for item in value if isinstance(value, tuple) else (value,):
            if isinstance(item, TNode):
                found += nodes_of(item)
    return found


def written_classes(node: TNode) -> list[type]:
    """The classes of the nodes a template writes (a wrapper's without its parameters as well)"""
    found: dict[type, None] = {}
    for inner in nodes_of(node):
        found[inner.model] = None
        origin = origin_of(inner.model)
        if origin is not None:
            found[origin] = None
    return list(found)


def fill(node: TNode, bindings: dict[str, Any]) -> dict[str, Any]:
    """The payload of the node (what its `Create` takes), with the variables as `bindings` has them: a literal's
    value, an entity's reference (`{"type": "Person", "id": ...}`)"""

    def item(value: Any) -> Any:
        if isinstance(value, tuple):
            return [item(v) for v in value]
        if isinstance(value, TNode):
            return fill(value, bindings)
        if isinstance(value, TVar):
            return bindings[value.name]
        if isinstance(value, TRef):
            return {"type": value.type, "id": value.id}
        if isinstance(value, TVia):
            return {
                **item(value.target),
                "edge_properties": {k: item(v) for k, v in value.edge.items()},
            }
        return value.value

    return {"type": node.type, **{k: item(v) for k, v in node.fields.items()}}


def describe(node: TNode) -> str:
    """A template in one line (`explain`)"""

    def item(value: Any) -> str:
        if isinstance(value, tuple):
            return "[" + ", ".join(item(v) for v in value) + "]"
        if isinstance(value, TNode):
            return describe(value)
        if isinstance(value, TVar):
            return value.name
        if isinstance(value, TRef):
            return f"{value.type}:{value.id}"
        if isinstance(value, TVia):
            edge = ", ".join(f"{k}: {item(v)}" for k, v in value.edge.items())
            return f"{item(value.target)} via {{{edge}}}"
        return repr(value.value)

    fields = ", ".join(f"{k}: {item(v)}" for k, v in node.fields.items())
    return f"{node.type}{{{fields}}}"


# ---------------------------------------------------------------------------
# Checking one
# ---------------------------------------------------------------------------


def is_node_variable(variable: Var) -> bool:
    """Whether the variable is of a node (an entity, a document, an embedded object, a trait of them) and not of a
    literal"""
    from pangloss_models.utils import model_is_trait

    model = variable.model
    return isinstance(model, type) and (
        issubclass(model, (Entity, Document, Embedded)) or model_is_trait(model)
    )


def type_name(value: Any) -> str:
    return getattr(value, "__name__", None) or str(value)


class TemplateCheck:
    """Checks the template of a rule against the models, and makes it data. `classes`: the class of each variable of a
    node, as the body of the rule leaves it (a `Var[Agent]` that a pattern has at a field of `Person` is a `Person`)"""

    def __init__(self, rule: str, variables: dict[str, Var], classes: dict[str, type]):
        self.rule = rule
        self.variables = variables
        self.classes = classes
        self.used: dict[str, None] = {}
        """The variables the template has, in the order met"""

    def fail(self, path: str, message: str) -> typing.NoReturn:
        raise PanglossDerivedError(f"Rule {self.rule}: {path}: {message}")

    # -- nodes --

    def head(self, template: Any, model: type) -> TNode:
        return self.node(template, model, model.__name__, head=True)

    def node(
        self, template: TemplateBase, model: type, path: str, head: bool = False
    ) -> TNode:
        meta: Any = getattr(model, "_meta", None)
        if getattr(meta, "abstract", False):
            self.fail(
                path,
                f"{model.__name__} is abstract: a template is of a class that documents can be of",
            )
        definitions = meta.fields
        fields: dict[str, Any] = {}
        for name, value in template.given().items():
            where = f"{path}.{name}"
            if name == "label":
                fields[name] = self.literal(value, str, where, None)
                continue
            definition = definitions.get(name)
            if definition is None:
                self.fail(where, f"is not a field of {model.__name__}")
            fields[name] = self.field(value, model, name, definition, where)
        create = model.__dict__.get("Create")
        for name, field in (create.model_fields if create is not None else {}).items():
            if name in fields or name == "type":
                continue
            definition = definitions.get(name)
            if definition is not None and is_citation_field(definition):
                if head and name in source_fields(model):
                    continue  # (the worker fills it)
                if definition.wrapper is not None:
                    fields[name] = ()
                elif field.is_required():
                    self.fail(
                        f"{path}.{name}",
                        "is a citation that has to be given, and a template writes none: a "
                        f"{model.__name__} cannot be in a derived document",
                    )
                continue
            if field.is_required():
                self.fail(
                    path,
                    f"{name} is not given"
                    + (
                        " (or give the class a label_template)"
                        if name == "label"
                        else ""
                    ),
                )
        return TNode(model, fields)

    def field(
        self, value: Any, model: type, name: str, definition: Any, where: str
    ) -> Any:
        declared = declared_field(model, name)
        if isinstance(definition, ListFieldDefinition):
            if isinstance(value, Var) or not isinstance(value, (list, tuple, set)):
                self.fail(
                    where,
                    f"is a list: give a list (of values and variables), not {value!r}",
                )
            if not any(isinstance(v, Var) for v in value):
                return TValue(self.validated(value, declared, where))
            return tuple(
                self.literal(v, definition.inner_type, f"{where}[{i}]", None)
                for i, v in enumerate(value)
            )
        if isinstance(definition, LiteralFieldDefinition):
            return self.literal(value, definition.annotated_type, where, declared)
        if isinstance(definition, AnnotatedValueFieldDefinition):
            if isinstance(value, Var):
                self.fail(
                    where, "an annotated value is given as it is: it takes no variable"
                )
            return TValue(self.validated(value, declared, where))
        if isinstance(definition, EmbeddedFieldDefinition):
            return self.embedded(value, definition, where)
        if isinstance(definition, RelationFieldDefinition):
            return self.relation(value, definition, where)
        self.fail(where, "a template cannot give a field of this kind")

    # -- literals --

    def validated(self, value: Any, declared: Any, where: str) -> Any:
        if declared is None:
            return value
        annotation = (
            Annotated[declared.annotation, *declared.metadata]
            if declared.metadata
            else declared.annotation
        )
        try:
            return TypeAdapter(annotation).validate_python(value)
        except ValidationError as error:
            first = error.errors()[0]
            self.fail(where, f"{value!r} is not right: {first['msg']}")

    def variable(self, variable: Var, where: str) -> Var:
        if self.variables.get(variable.name) is not variable:
            self.fail(where, f"{variable!r} is not a variable of the rule")
        self.used[variable.name] = None
        return variable

    def literal(self, value: Any, annotation: Any, where: str, declared: Any) -> Item:
        base = without_none(annotation)
        if isinstance(value, Var):
            self.variable(value, where)
            if is_node_variable(value):
                self.fail(
                    where,
                    f"is a value ({type_name(base)}): the variable {value.name!r} is a "
                    f"{type_name(value.model)}",
                )
            fits = value.model is base or (
                isinstance(value.model, type)
                and isinstance(base, type)
                and issubclass(value.model, base)
            )
            if not fits:
                self.fail(
                    where,
                    f"a Var[{type_name(value.model)}] cannot be a {type_name(base)}",
                )
            return TVar(value.name, False)
        if isinstance(value, (TemplateBase, Via)):
            self.fail(where, f"is a value ({type_name(base)}), not {value!r}")
        if declared is None:
            try:
                return TValue(TypeAdapter(annotation).validate_python(value))
            except ValidationError as error:
                self.fail(where, f"{value!r} is not right: {error.errors()[0]['msg']}")
        return TValue(self.validated(value, declared, where))

    # -- embedded objects --

    def embedded(
        self, value: Any, definition: EmbeddedFieldDefinition, where: str
    ) -> Item:
        if value is None:
            if definition.optional:
                return TValue(None)
            self.fail(where, "has to be given")
        if isinstance(value, Var):
            self.fail(
                where,
                "an embedded object is written out in a template (its values may be variables): a variable cannot "
                "stand for the whole of one",
            )
        allowed = [o.annotated_type for o in definition.type_options]
        if not isinstance(value, TemplateBase):
            names = " or ".join(f"{a.__name__}.Template(...)" for a in allowed)
            self.fail(where, f"takes {names}, not {value!r}")
        model = type(value)._model
        if not any(issubclass(model, a) for a in allowed):
            names = ", ".join(a.__name__ for a in allowed)
            self.fail(where, f"takes {names}: not a {model.__name__}")
        return self.node(value, model, where)

    # -- relations --

    def relation(
        self, value: Any, definition: RelationFieldDefinition, where: str
    ) -> Any:
        options = [
            o
            for o in definition.type_options
            if not isinstance(o, RelationToCitation) and not left_to_people(o)
        ]
        if definition.wrapper is not None:
            if isinstance(value, (Var, TemplateBase, Via, dict)) or not isinstance(
                value, (list, tuple)
            ):
                self.fail(where, f"is a list: give a list, not {value!r}")
            return tuple(
                self.item(v, options, f"{where}[{i}]") for i, v in enumerate(value)
            )
        if value is None:
            if definition.optional:
                return TValue(None)
            self.fail(where, "has to be given")
        if isinstance(value, (list, tuple)):
            self.fail(where, "is one, not a list")
        return self.item(value, options, where)

    def taken(self, options: list[Any]) -> str:
        names = []
        for option in options:
            if isinstance(option, WRAPPER_OPTIONS):
                names.append(option.base_type.__name__)
            else:
                names.append(type_name(option.annotated_type))
        return ", ".join(sorted(names)) or "nothing"

    def item(self, value: Any, options: list[Any], where: str) -> Item:
        if isinstance(value, Via):
            return self.via(value, options, where)
        if isinstance(value, Var):
            found = self.entity_variable(value, options, where)
            return self.with_edge(TVar(value.name, True), found, where)
        if isinstance(value, TemplateBase):
            return self.nested(value, options, where)
        reference = self.reference(value)
        if reference is not None:
            found = [
                o
                for o in options
                if isinstance(o, RelationToEntity)
                and any(
                    m.__name__ == reference.type
                    for m in subclasses_of(o.annotated_type)
                )
            ]
            if not found:
                self.fail(
                    where,
                    f"takes {self.taken(options)}: not a reference to a {reference.type}",
                )
            return self.with_edge(reference, found, where)
        self.fail(
            where,
            f"takes a variable, a Template or a reference ({{'type': ..., 'id': ...}}): not {value!r}",
        )

    def reference(self, value: Any) -> TRef | None:
        if isinstance(value, BaseModel) and not isinstance(value, TemplateBase):
            value = {
                "type": getattr(value, "type", None),
                "id": getattr(value, "id", None),
            }
        if isinstance(value, dict) and set(value) == {"type", "id"} and value["id"]:
            return TRef(str(value["type"]), str(value["id"]))
        return None

    def with_edge(self, target: TVar | TRef, options: list[Any], where: str) -> Item:
        """A reference given without a `Via`: refused where the relation's edge has properties that must be given;
        where it has properties that need not be, they are given as none (a `Create` wants them said)"""
        edged = False
        for option in options:
            edge = option.edge_model
            if edge is None:
                continue
            edged = True
            required = [n for n, f in edge.model_fields.items() if f.is_required()]
            if required:
                self.fail(
                    where,
                    f"the relation has the properties of a {edge.__name__} ({', '.join(required)}): give "
                    f"Via(..., {edge.__name__}.Template(...))",
                )
        return TVia(target, {}) if edged else target

    def entity_variable(
        self, variable: Var, options: list[Any], where: str
    ) -> list[Any]:
        """The options that take the variable: every class it can be of must be one a relation to an entity takes"""
        self.variable(variable, where)
        model = self.classes.get(variable.name, variable.model)
        if not is_node_variable(variable):
            self.fail(
                where,
                f"takes {self.taken(options)}: the variable {variable.name!r} is a value "
                f"({type_name(variable.model)})",
            )
        if not issubclass(model, Entity) and not any(
            issubclass(m, Entity) for m in subclasses_of(model)
        ):
            self.fail(
                where,
                f"the variable {variable.name!r} is a {model.__name__}, which is part of the document it was found "
                "in: a derived document cannot hold it too. Write what it says as a Template, with its entities "
                "and values as variables",
            )
        entities = [o for o in options if isinstance(o, RelationToEntity)]
        concrete = [
            m
            for m in subclasses_of(model)
            if getattr(m, "__metatype__", None) == "Entity"
            and issubclass(m, Entity)
            and not getattr(m._meta, "abstract", False)
        ]
        found: dict[int, Any] = {}
        for candidate in concrete or [model]:
            takers = [o for o in entities if issubclass(candidate, o.annotated_type)]
            if not takers:
                self.fail(
                    where,
                    f"takes {self.taken(options)}: the variable {variable.name!r} can be a {candidate.__name__}"
                    + (
                        f" (it is declared a {model.__name__}: declare it of a narrower class, Var[...])"
                        if candidate is not model
                        else ""
                    ),
                )
            for taker in takers:
                found[id(taker)] = taker
        return list(found.values())

    def via(self, value: Via, options: list[Any], where: str) -> TVia:
        edge = value.edge
        if not isinstance(edge, TemplateBase):
            self.fail(
                where,
                f"Via(target, edge): the edge is the Template of an edge model, not {edge!r}",
            )
        edge_model = type(edge)._model
        with_edge = [o for o in options if o.edge_model is edge_model]
        if not with_edge:
            has = sorted({o.edge_model.__name__ for o in options if o.edge_model})
            self.fail(
                where,
                f"the relation has no properties of a {edge_model.__name__}"
                + (
                    f" (it has those of {', '.join(has)})"
                    if has
                    else " (its edge has none)"
                ),
            )
        if isinstance(value.target, Var):
            self.entity_variable(value.target, with_edge, where)
            target: TVar | TRef = TVar(value.target.name, True)
        else:
            reference = self.reference(value.target)
            if reference is None:
                self.fail(
                    where,
                    f"Via(target, edge): the target is a variable or a reference, not {value.target!r}",
                )
            target = reference
        properties: dict[str, Any] = {}
        for name, given in edge.given().items():
            definition = edge_model._meta.fields.get(name)
            if definition is None:
                self.fail(where, f"{name} is not a field of {edge_model.__name__}")
            properties[name] = self.field(
                given,
                edge_model,
                name,
                definition,
                f"{where} ({edge_model.__name__}.{name})",
            )
        return TVia(target, properties)

    def nested(self, value: TemplateBase, options: list[Any], where: str) -> TNode:
        model = type(value)._model
        if getattr(getattr(model, "_meta", None), "abstract", False):
            self.fail(
                where,
                f"{model.__name__} is abstract: a template is of a class that documents can be of",
            )
        documents = [
            o
            for o in options
            if isinstance(o, RelationToDocument) and issubclass(model, o.annotated_type)
        ]
        if documents:
            return self.node(value, model, where)
        wrappers = [
            o
            for o in options
            if isinstance(o, WRAPPER_OPTIONS) and o.base_type is model
        ]
        if not wrappers:
            self.fail(where, f"takes {self.taken(options)}: not a {model.__name__}")
        problem: PanglossDerivedError | None = None
        for option in wrappers:
            try:
                return self.node(value, typing.cast(type, option.annotated_type), where)
            except PanglossDerivedError as error:
                problem = error
        assert problem is not None
        raise problem
