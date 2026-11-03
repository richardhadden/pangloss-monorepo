"""What a write of a document or an entity does, worked out from its `CreateDB` or `UpdateDB` instance with no database
and no query language: the nodes, with their labels and their properties; the relations between them; the existing
nodes referred to; the entities written in it; the URLs.

A `WritePlan` is a tree, in the order the instance is walked: a node has its relations, in the order of its fields, and
each goes to a node of the document, to an existing node (`ReferenceToExisting`), or to an entity written in the
document (`InlineEntity`). A relation is the names of its edges, forward and backward (the field's, and those of the
parent fields it subclasses): how a relation is stored, as two edges or otherwise, is for the renderer to say. So are the
records of creation and update, the user, and the encoding of the properties.

`render_write` makes the Cypher of a plan; the checks of `validate_write` read it.
"""

import dataclasses
import datetime
import typing
import uuid
from collections.abc import Iterator, Mapping

from pangloss_models import hooks
from pangloss_models.field_definitions import (
    FieldSubclassing,
    RelationOption,
    RelationToDocument,
    RelationToEntity,
    RelationToTypeVar,
)
from pangloss_models.model_bases.base_models import (
    _CreateDBBase,
    _ReferenceSetBase,
    _UpdateDBBase,
)
from pangloss_models.model_bases.conjunction import _ConjunctionCreateDBBase
from pangloss_models.model_bases.document import (
    _DocumentCreateDBBase,
    _DocumentUpdateDBBase,
)
from pangloss_models.model_bases.edge_model import EdgeModel
from pangloss_models.model_bases.embedded import _EmbeddedCreateDBBase
from pangloss_models.model_bases.entity import _EntityCreateDBBase, _EntityUpdateDBBase
from pangloss_models.model_bases.reified_relation import (
    _ReifiedRelationCreateDBBase,
    _ReifiedRelationDocumentCreateDBBase,
)
from pangloss_models.model_bases.semantic_space import _SemanticSpaceCreateDBBase
from pangloss_users import current_request_username
from pydantic import AnyUrl

from pangloss_cypher.values import convert_type_for_writing, native_datetime

type _AllCreateDBModels = (
    _DocumentUpdateDBBase
    | _EntityUpdateDBBase
    | _DocumentCreateDBBase
    | _EntityCreateDBBase
    | _ReifiedRelationCreateDBBase
    | _ReifiedRelationDocumentCreateDBBase
    | _ConjunctionCreateDBBase
    | _SemanticSpaceCreateDBBase
    | _EmbeddedCreateDBBase
)


# --- what a write refers to, to be checked before it is made ---------------------------------------------------------


@dataclasses.dataclass(frozen=True)
class ReferenceToExisting:
    """A reference to an existing entity (or document), to be checked before writing"""

    value: str
    is_url: bool
    allowed_types: tuple[str, ...]
    field_name: str


@dataclasses.dataclass(frozen=True)
class NodeToWrite:
    """A node that will be written below the head node"""

    id: str
    is_entity: bool


# How an entity that a document creates is looked up: by the URL it is given,
# or else by its id
type InlineEntityKey = tuple[str, str]


@dataclasses.dataclass(frozen=True)
class ExistingEntity:
    """What the database has for an `InlineEntity` that exists"""

    id: str
    labels: frozenset[str]
    deleted: bool


# --- the plan ---------------------------------------------------------------------------------------------------------


@dataclasses.dataclass
class PlannedNode:
    """A node to write: a head node, a node of the document below it, or an entity written in the document"""

    id: str
    type: str
    # the labels of its class (the renderer adds those of its place: `HeadNode`, `PGIndexableNode`)
    labels: tuple[str, ...]
    # its properties as they are written, but not encoded for a backend
    properties: dict[str, typing.Any]
    relations: list["Relation"] = dataclasses.field(default_factory=list)
    # (an entity's) its URLs, each a node of its own
    urls: tuple[str, ...] = ()


@dataclasses.dataclass(frozen=True)
class InlineEntity:
    """An entity written in a document, with an id or URL of its own (a `create_new`
    entity). It is an entity like any other, found if it exists, and created as
    one if it does not"""

    key: InlineEntityKey
    type: str
    field_name: str
    allowed_types: tuple[str, ...]
    # The `CreateDB` instance (what is written, if it does not exist)
    instance: typing.Any = dataclasses.field(compare=False, repr=False, default=None)
    # The entity, as a head node of its own, with its relations (written only if it does not exist)
    node: PlannedNode | None = dataclasses.field(
        compare=False, repr=False, default=None
    )


@dataclasses.dataclass
class Relation:
    """A value of a relation (or embedded) field: the edges to `target`, a pair for the field and one for each parent
    field that it subclasses (`(forward, backward)`, the field's first), with the properties of the edges"""

    edges: tuple[tuple[str, str], ...]
    edge_properties: dict[str, typing.Any] | None
    target: "PlannedNode | ReferenceToExisting | InlineEntity"


@dataclasses.dataclass
class WritePlan:
    """The write of a head node (a document or an entity): created, or the tree below it replaced (`is_update`)"""

    head: PlannedNode
    is_update: bool = False

    @property
    def head_id(self) -> uuid.UUID:
        return uuid.UUID(self.head.id)

    def walk(
        self, existing: Mapping[InlineEntityKey, ExistingEntity] | None = None
    ) -> Iterator[tuple[PlannedNode, Relation, bool]]:
        """Each relation that is written, with the node it is from, in the order of the plan, and whether its target is
        written for the first time here. An entity written in the document is written (with what is below it) at its
        first place, and only if it does not exist (`existing`); a reference to the same node twice is matched once"""
        existing = existing or {}
        seen_entities: set[InlineEntityKey] = set()
        seen_references: set[tuple[str, tuple[str, ...]]] = set()

        def below(node: PlannedNode) -> Iterator[tuple[PlannedNode, Relation, bool]]:
            for relation in node.relations:
                target = relation.target
                if isinstance(target, InlineEntity):
                    first = target.key not in seen_entities
                    seen_entities.add(target.key)
                    yield node, relation, first
                    if first and target.key not in existing and target.node:
                        yield from below(target.node)
                elif isinstance(target, ReferenceToExisting):
                    key = (target.value, target.allowed_types)
                    first = key not in seen_references
                    seen_references.add(key)
                    yield node, relation, first
                else:
                    yield node, relation, True
                    yield from below(target)

        yield from below(self.head)

    @property
    def inline_entities(self) -> list[InlineEntity]:
        """The entities written in the document, each time one is given (to be looked up before the plan is rendered:
        the query differs for those that exist)"""
        return [
            relation.target
            for _, relation, _ in self.walk()
            if isinstance(relation.target, InlineEntity)
        ]

    def references(
        self, existing: Mapping[InlineEntityKey, ExistingEntity] | None = None
    ) -> list[ReferenceToExisting]:
        return [
            relation.target
            for _, relation, _ in self.walk(existing)
            if isinstance(relation.target, ReferenceToExisting)
        ]

    def nodes_to_write(
        self, existing: Mapping[InlineEntityKey, ExistingEntity] | None = None
    ) -> list[NodeToWrite]:
        """The nodes written below a head node (the head node's, or an entity's written in the document)"""
        return [
            NodeToWrite(id=relation.target.id, is_entity=False)
            for _, relation, _ in self.walk(existing)
            if isinstance(relation.target, PlannedNode)
        ]

    def created_entities(
        self, existing: Mapping[InlineEntityKey, ExistingEntity] | None = None
    ) -> tuple[typing.Any, ...]:
        """The entities that the write makes: written in the document, and not there already (`CreateDB` instances, one
        for each)"""
        existing = existing or {}
        created: dict[InlineEntityKey, typing.Any] = {}
        for entity in self.inline_entities:
            if entity.key not in existing:
                created.setdefault(entity.key, entity.instance)
        return tuple(created.values())

    def urls_to_write(
        self, existing: Mapping[InlineEntityKey, ExistingEntity] | None = None
    ) -> list[str]:
        """The URLs of the entities the write makes (the head node's, if it is a new entity)"""
        existing = existing or {}
        urls = [] if self.is_update else list(self.head.urls)
        for _, relation, first in self.walk(existing):
            target = relation.target
            if (
                isinstance(target, InlineEntity)
                and first
                and target.key not in existing
                and target.node
            ):
                urls += target.node.urls
        return urls


# --- from an instance to a plan ---------------------------------------------------------------------------------------


def inline_entity_key(instance: _EntityCreateDBBase) -> InlineEntityKey:
    if instance.urls:
        return ("url", str(sorted(instance.urls, key=str)[0]))
    return ("id", str(instance.id))


def allowed_type_names(type_options: typing.Iterable[RelationOption]) -> list[str]:
    return sorted(
        {
            type_option.annotated_type.__name__
            for type_option in type_options
            if isinstance(type_option, (RelationToEntity, RelationToDocument))
        }
    )


def convert_edge_properties_for_writing(
    edge_properties: EdgeModel,
) -> dict[str, typing.Any]:
    edge_properties_dict = edge_properties.model_dump()
    for k, v in edge_properties_dict.items():
        edge_properties_dict[k] = convert_type_for_writing(v)
    return edge_properties_dict


def default_reverse_name(field_name: str) -> str:
    """Reverse edge name for fields that do not define one (embedded objects,
    annotated values)"""
    return f"{field_name}_reverse"


def iter_values(value: typing.Any) -> list[typing.Any]:
    """Normalise a field value (None, a single item or a list) to a list"""
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def get_node_fields_as_writable_dict(
    instance: _AllCreateDBModels,
    is_new: bool = False,
    is_head_node: bool = False,
    head_node_type: str | None = None,
    head_node_id: uuid.UUID | None = None,
    previous_meta: dict[str, typing.Any] | None = None,
) -> dict[str, typing.Any]:

    node_data: dict[str, typing.Any] = {
        "id": str(instance.id),
        "type": instance.type,
    }

    # If it's new, we can create the whole meta object; otherwise, must be
    # updated granularly to preserve the created_by/created_when
    if is_new and not is_head_node:
        now = datetime.datetime.now(datetime.UTC)
        # If this node is being rewritten by an update, it keeps its creation info
        previous_meta = previous_meta or {}
        node_data["meta"] = {
            "created_by": previous_meta.get("created_by")
            or current_request_username.get(),
            "created_when": native_datetime(previous_meta.get("created_when")) or now,
            "updated_by": current_request_username.get(),
            "updated_when": now,
            "semantic_spaces": instance.semantic_spaces,
            "context_labels": instance.context_labels,
        }

    if not is_head_node:
        node_data["head_node_type"] = head_node_type
        node_data["head_node_id"] = str(head_node_id)

    # Compare with None rather than truthiness: 0, 0.0, "" and [] are real values
    if (label := getattr(instance, "label", None)) is not None:
        node_data["label"] = label
    for field_name in instance._meta.fields.literal_fields:
        if (value := getattr(instance, field_name)) is not None:
            node_data[field_name] = convert_type_for_writing(value)

    # An annotated value (a value with extra literal fields) is stored on the node
    # as a map, e.g. {value: "John", certainty: 2}
    for field_name in instance._meta.fields.annotated_value_fields:
        if (annotated_value := getattr(instance, field_name, None)) is not None:
            node_data[field_name] = convert_type_for_writing(
                annotated_value.model_dump()
            )
    return node_data


type TypeOptions = typing.Iterable[RelationOption]
type TypeVarOptions = typing.Mapping[str, typing.Iterable[RelationOption]]


def substitute_type_vars(
    type_options: TypeOptions, type_var_options: TypeVarOptions
) -> set[RelationOption]:
    """Replace any type variable in a field's type options (e.g. `target: list[T]`
    on a reified relation) with the options the type variable was given by the
    field that uses the generic wrapper (e.g. `Proxy[Person]`)"""
    result: set[RelationOption] = set()
    for type_option in type_options:
        if (
            isinstance(type_option, RelationToTypeVar)
            and type_option.type_var_name in type_var_options
        ):
            result.update(
                type_option.stand_in(type_var_options[type_option.type_var_name])
            )
        else:
            result.add(type_option)
    return result


def resolve_type_var_options(
    type_options: TypeOptions, instance: _AllCreateDBModels
) -> dict[str, set[RelationOption]]:
    """If `instance` is a generic wrapper (reified relation, semantic space,
    conjunction), find what its type variables were bound to in the field it
    is being attached through"""
    resolved: dict[str, set[RelationOption]] = {}
    for type_option in type_options:
        parameter_type_options = getattr(type_option, "parameter_type_options", None)
        base_type = getattr(type_option, "base_type", None)
        if not parameter_type_options or base_type is None:
            continue
        if base_type.__name__ != instance.type:
            continue
        for type_var_name, parameter in parameter_type_options.items():
            resolved.setdefault(type_var_name, set()).update(parameter.type_options)
    return resolved


def edge_names(
    field_name: str,
    reverse_name: str,
    subclasses_parent_fields: typing.Iterable[str | FieldSubclassing],
) -> tuple[tuple[str, str], ...]:
    """The field's pair of names, and the pair of each parent field that it subclasses"""
    names = [(field_name, reverse_name)]
    for subclasses_field in subclasses_parent_fields:
        assert isinstance(subclasses_field, FieldSubclassing)
        names.append(
            (
                subclasses_field.field_name,
                subclasses_field.field_on_model._meta.fields.relation_fields[
                    subclasses_field.field_name
                ].reverse_name,
            )
        )
    return tuple(names)


def _edge_properties(item: typing.Any) -> dict[str, typing.Any] | None:
    edge_properties = getattr(item, "edge_properties", None)
    return (
        convert_edge_properties_for_writing(edge_properties)
        if edge_properties
        else None
    )


class _Planner:
    def __init__(self, previous_meta: dict[str, dict[str, typing.Any]] | None = None):
        # `meta` of the nodes of a tree an update replaces, by id, so that they keep their creation
        self.previous_meta = previous_meta or {}

    def relations_of(
        self,
        instance: _AllCreateDBModels,
        head_node_type: str,
        head_node_id: uuid.UUID,
        type_var_options: TypeVarOptions | None = None,
    ) -> list[Relation]:
        """The relations of `instance` (and its embedded objects), in the order of its fields"""
        fields = instance._meta.fields
        relations: list[Relation] = []

        for field_name, field in fields.relation_fields.items():
            type_options = substitute_type_vars(
                field.type_options, type_var_options or {}
            )
            names = edge_names(
                field_name, field.reverse_name, field.subclasses_parent_fields
            )
            for item in iter_values(getattr(instance, field_name, None)):
                match item:
                    case _CreateDBBase() | _UpdateDBBase() if (
                        item.__metatype__ == "Entity"
                    ):
                        # (an entity of its own, not part of this document)
                        target = self.inline_entity(
                            typing.cast("_EntityCreateDBBase", item),
                            field_name,
                            type_options,
                        )
                    case _CreateDBBase() | _UpdateDBBase():
                        target = self.tree_node(
                            typing.cast(_AllCreateDBModels, item),
                            head_node_type,
                            head_node_id,
                            type_options,
                        )
                    case _ReferenceSetBase():
                        target = ReferenceToExisting(
                            value=str(item.id),
                            is_url=isinstance(item.id, AnyUrl),
                            allowed_types=tuple(allowed_type_names(type_options)),
                            field_name=field_name,
                        )
                    case _:
                        continue
                relations.append(Relation(names, _edge_properties(item), target))

        # Embedded objects are nodes in their own right, attached like a nested document
        for field_name in fields.embedded_fields:
            for item in iter_values(getattr(instance, field_name, None)):
                if isinstance(item, (_CreateDBBase, _UpdateDBBase)):
                    target = self.tree_node(
                        typing.cast(_AllCreateDBModels, item),
                        head_node_type,
                        head_node_id,
                        (),
                    )
                    relations.append(
                        Relation(
                            ((field_name, default_reverse_name(field_name)),),
                            _edge_properties(item),
                            target,
                        )
                    )
        return relations

    def tree_node(
        self,
        instance: _AllCreateDBModels,
        head_node_type: str,
        head_node_id: uuid.UUID,
        type_options: TypeOptions,
    ) -> PlannedNode:
        """A node of the document below its head node"""
        node = PlannedNode(
            id=str(instance.id),
            type=instance.type,
            labels=tuple(instance._labels),
            properties=get_node_fields_as_writable_dict(
                instance,
                is_new=True,
                is_head_node=False,
                head_node_id=head_node_id,
                head_node_type=head_node_type,
                previous_meta=self.previous_meta.get(str(instance.id)),
            ),
        )
        # (if this is a generic wrapper, such as `Proxy[Person]`, its type variables are resolved from the field it was
        # attached through)
        node.relations = self.relations_of(
            instance,
            head_node_type,
            head_node_id,
            resolve_type_var_options(type_options, instance),
        )
        return node

    def inline_entity(
        self,
        instance: _EntityCreateDBBase,
        field_name: str,
        type_options: TypeOptions,
    ) -> InlineEntity:
        """An entity given in a document, with an id or URL of its own.

        It is not part of the document. If it exists, it is just related to, like any
        entity that is referred to. If not, it is created as `Entity.Create(...).save()`
        would create it: a head node, with its own record of creation, and nothing to
        do with the document (nor with the semantic spaces it is in)."""
        node = PlannedNode(
            id=str(instance.id),
            type=instance.type,
            labels=tuple(instance._labels),
            properties=get_node_fields_as_writable_dict(
                instance, is_new=True, is_head_node=True
            ),
            urls=tuple(
                str(url)
                for url in sorted(getattr(instance, "urls", None) or [], key=str)
            ),
        )
        # Its own relations belong to it (it is the head node of them)
        node.relations = self.relations_of(
            typing.cast(_AllCreateDBModels, instance), instance.type, instance.id
        )
        return InlineEntity(
            key=inline_entity_key(instance),
            type=instance.type,
            field_name=field_name,
            allowed_types=tuple(allowed_type_names(type_options)),
            instance=instance,
            node=node,
        )


def plan_create(instance: _DocumentCreateDBBase | _EntityCreateDBBase) -> WritePlan:
    """The creation of a document or an entity"""
    properties = get_node_fields_as_writable_dict(
        instance, is_new=True, is_head_node=True
    )
    # what installed apps want on a new head node (such as `published: false`)
    # (a review status that the document itself says is asked for, over one the call asked for)
    with hooks.requesting_review_status(getattr(instance, "review_status", None)):
        properties.update(hooks.properties_for_new_head(instance._owner))
    head = PlannedNode(
        id=str(instance.id),
        type=instance.type,
        labels=tuple(instance._labels),
        properties=properties,
        urls=tuple(
            str(url) for url in sorted(getattr(instance, "urls", None) or [], key=str)
        )
        if isinstance(instance, _EntityCreateDBBase)
        else (),
    )
    head.relations = _Planner().relations_of(instance, instance.type, instance.id)
    return WritePlan(head=head)


def plan_update(
    instance: _DocumentUpdateDBBase | _EntityUpdateDBBase,
    previous_meta: dict[str, dict[str, typing.Any]] | None = None,
) -> WritePlan:
    """The tree below an existing head node, written anew (`build_replace_head_query` deletes the old one and gives the
    head node its properties). `previous_meta`: the `meta` of the nodes of the old tree, by id, for their creation"""
    head = PlannedNode(
        id=str(instance.id),
        type=instance.type,
        labels=tuple(instance._labels),
        properties={},
    )
    head.relations = _Planner(previous_meta).relations_of(
        instance, instance.type, instance.id
    )
    return WritePlan(head=head, is_update=True)
