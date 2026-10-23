import base64
import dataclasses
import datetime
import lzma
import typing
import uuid
from decimal import Decimal
from enum import Enum
from typing import Any

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
from pydantic import AnyUrl, BaseModel


def compress(instance: BaseModel):

    stored_string = base64.b64encode(
        lzma.compress(
            instance.model_dump_json().encode("utf-8"), preset=9 | lzma.PRESET_EXTREME
        )
    ).decode("utf-8")
    return stored_string


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


class Identifier(str):
    """A name in a query, for a variable or a parameter. Made by `QueryParams.new_identifier`."""


class QuerySubstring(str):
    def __new__(cls, query_string: str):
        return super().__new__(cls, query_string)


class QueryParams(dict[Identifier, dict[str, typing.Any] | typing.Any]):
    """The parameters of a query, by name, and the names of a query.

    The names are `x1`, `x2`... in the order they are made in, so a query of the same shape has the
    same text each time and Memgraph, which keeps the plan of a query by its text, plans it once
    (names that were made at random were planned afresh every time)."""

    def __init__(self, *args: typing.Any, **kwargs: typing.Any) -> None:
        super().__init__(*args, **kwargs)
        self._made = 0

    def new_identifier(self) -> Identifier:
        self._made += 1
        return Identifier(f"x{self._made}")

    def add(self, item: dict[str, typing.Any] | typing.Any) -> Identifier:
        identifier = self.new_identifier()
        self.__setitem__(identifier, convert_type_for_writing(item))
        return identifier


@dataclasses.dataclass(frozen=True)
class ReferenceToExisting:
    """A reference to an existing entity, to be checked before writing"""

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


@dataclasses.dataclass(frozen=True)
class ExistingEntity:
    """What the database has for an `InlineEntity` that exists"""

    id: str
    labels: frozenset[str]
    deleted: bool


def inline_entity_key(instance: "_EntityCreateDBBase") -> InlineEntityKey:
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


class QueryObject:
    match_query_strings: list[str]
    create_query_strings: list[str]
    merge_query_strings: list[str]
    set_query_strings: list[str]
    params: QueryParams
    return_identifier: Identifier
    head_id: uuid.UUID
    head_type: str | None
    # What the query refers to and writes, so that it can be checked before it
    # is run
    urls_to_write: list[str]
    references: list[ReferenceToExisting]
    nodes_to_write: list[NodeToWrite]
    # `meta` of nodes of the tree being replaced in an update, by node id, so that
    # `created_by` and `created_when` are kept
    previous_meta: dict[str, dict[str, typing.Any]]
    # Identifiers of the existing nodes already matched by the query, so that an
    # entity referred to many times is matched once
    matched_references: dict[tuple, Identifier]
    # The entities written in the document: asked about before the query is built (the
    # query differs for those that exist), and then given back as `existing_entities`
    inline_entities: list[InlineEntity]
    existing_entities: dict[InlineEntityKey, ExistingEntity]
    # Identifiers of those in the query, so that one that is written twice is one
    inline_entity_identifiers: dict[InlineEntityKey, Identifier]

    def __init__(
        self,
        head_id: uuid.UUID,
        head_type: str,
        existing_entities: dict[InlineEntityKey, ExistingEntity] | None = None,
    ):
        self.match_query_strings = []
        self.create_query_strings = []
        self.merge_query_strings = []
        self.set_query_strings = []
        self.params = QueryParams()
        self.head_type = head_type
        self.head_id = head_id
        self.references = []
        self.urls_to_write = []
        self.nodes_to_write = []
        self.previous_meta = {}
        self.matched_references = {}
        self.inline_entities = []
        self.existing_entities = existing_entities or {}
        self.inline_entity_identifiers = {}

    def created_entities(self) -> tuple[typing.Any, ...]:
        """The entities that the query makes: written in the document, and not there already
        (`CreateDB` instances, one for each)"""
        created: dict[InlineEntityKey, typing.Any] = {}
        for entity in self.inline_entities:
            if entity.key not in self.existing_entities:
                created.setdefault(entity.key, entity.instance)
        return tuple(created.values())

    def to_query_string(self) -> typing.LiteralString:
        if not self.return_identifier:
            raise Exception("CreateQuery.to_query_string called on non-top-level node")
        return typing.cast(
            typing.LiteralString,
            f"""
            {"\n".join(self.match_query_strings)}
            {"\n".join(self.create_query_strings)}
            {"\n".join(self.set_query_strings)}
            {"\n".join(self.merge_query_strings)}
            RETURN {self.return_identifier}.id AS id
        """,
        )


def convert_type_for_writing(value):
    """Convert a Python value to something Memgraph can store as a property.

    - `Decimal` is stored as a string, to keep its exact value (Memgraph has no
      decimal type).
    - `Enum` members are stored as their values (a string or a number), so the
      database holds nothing of the enum but what it means.
    - Containers (including TypedDicts) are converted recursively."""
    match value:
        case uuid.UUID():
            return str(value)
        case AnyUrl():
            return str(value)
        case Enum():
            return convert_type_for_writing(value.value)
        case Decimal():
            return str(value)
        case set() | tuple() | list():
            return [convert_type_for_writing(v) for v in value]
        case dict():
            return {k: convert_type_for_writing(v) for k, v in value.items()}
        case _:
            return value


def convert_edge_properties_for_writing(edge_properties: EdgeModel) -> dict[str, Any]:
    edge_properties_dict = edge_properties.model_dump()
    for k, v in edge_properties_dict.items():
        edge_properties_dict[k] = convert_type_for_writing(v)
    return edge_properties_dict


class PropertyAssignments:
    """The properties to set on a node or edge, from a single parameter"""

    def __init__(self, params: QueryParams, properties: dict[str, typing.Any]):
        self.identifier = params.add(properties)

    def set_items(self, variable: str, replace: bool = False) -> str:
        """What to put after `SET` to give `variable` the properties: replacing
        its properties (`=`), or adding to them (`+=`)"""
        return f"{variable} {'=' if replace else '+='} ${self.identifier}"


def native_datetime(value: typing.Any) -> typing.Any:
    """Convert a neo4j DateTime to a Python datetime"""
    return value.to_native() if hasattr(value, "to_native") else value


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


def get_label_query_string(
    instance: _CreateDBBase, extra_labels: list[str] | None = None
) -> str:
    all_labels = (
        [*instance._labels, *extra_labels] if extra_labels else instance._labels
    )
    return f"{':'.join(all_labels)}"


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
            result.update(type_var_options[type_option.type_var_name])
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


def build_attached_nodes(
    query_object: QueryObject,
    instance: _AllCreateDBModels,
    instance_identifier: Identifier,
    head_node_type: str,
    head_node_id: uuid.UUID,
    type_var_options: TypeVarOptions | None = None,
):
    """Add queries for everything that is not a literal field of `instance`:
    relations and embedded objects"""

    fields = instance._meta.fields

    for related_field_name, related_field_def in fields.relation_fields.items():
        type_options = substitute_type_vars(
            related_field_def.type_options, type_var_options or {}
        )
        for item in iter_values(getattr(instance, related_field_name, None)):
            match item:
                case _CreateDBBase() | _UpdateDBBase() if (
                    item.__metatype__ == "Entity"
                ):
                    # (an entity of its own, not part of this document)
                    build_inline_entity_query(
                        query_object=query_object,
                        instance=typing.cast("_EntityCreateDBBase", item),
                        source_identifier=instance_identifier,
                        field_name=related_field_name,
                        reverse_name=related_field_def.reverse_name,
                        subclasses_parent_fields=related_field_def.subclasses_parent_fields,
                        type_options=type_options,
                    )
                case _CreateDBBase() | _UpdateDBBase():
                    build_related_node_query(
                        query_object=query_object,
                        instance=typing.cast(_AllCreateDBModels, item),
                        source_identifier=instance_identifier,
                        field_name=related_field_name,
                        reverse_name=related_field_def.reverse_name,
                        subclasses_parent_fields=related_field_def.subclasses_parent_fields,
                        type_options=type_options,
                        head_node_type=head_node_type,
                        head_node_id=head_node_id,
                    )
                case _ReferenceSetBase():
                    build_relation_to_existing_query(
                        query_object=query_object,
                        instance=item,
                        source_identifier=instance_identifier,
                        field_name=related_field_name,
                        reverse_name=related_field_def.reverse_name,
                        subclasses_parent_fields=related_field_def.subclasses_parent_fields,
                        type_options=type_options,
                    )

    # Embedded objects are nodes in their own right, attached like a nested document
    for embedded_field_name in fields.embedded_fields:
        for item in iter_values(getattr(instance, embedded_field_name, None)):
            if isinstance(item, (_CreateDBBase, _UpdateDBBase)):
                build_related_node_query(
                    query_object=query_object,
                    instance=typing.cast(_AllCreateDBModels, item),
                    source_identifier=instance_identifier,
                    field_name=embedded_field_name,
                    reverse_name=default_reverse_name(embedded_field_name),
                    subclasses_parent_fields=(),
                    type_options=(),
                    head_node_type=head_node_type,
                    head_node_id=head_node_id,
                )


def build_url_nodes(
    query_object: QueryObject, instance: "_EntityCreateDBBase", node_identifier: Identifier
) -> None:
    """The URLs of a new entity, as nodes (`PGUrl`) that it has, rather than as a
    property: a URL is unique, so that two entities cannot have it, even if they are
    made at the same time (a uniqueness constraint)."""
    for url in sorted(getattr(instance, "urls", None) or [], key=str):
        url_identifier = query_object.params.new_identifier()
        url_parameter = query_object.params.add(str(url))
        query_object.urls_to_write.append(str(url))
        query_object.create_query_strings.append(f"""
            CREATE ({url_identifier}:PGUrl {{url: ${url_parameter}}})
            CREATE ({node_identifier})-[:has_url]->({url_identifier})
        """)


def build_edges(
    query_object: QueryObject,
    source_identifier: Identifier,
    target_identifier: Identifier,
    field_name: str,
    reverse_name: str,
    subclasses_parent_fields: typing.Iterable[str | FieldSubclassing],
    edge_properties: EdgeModel | None = None,
):
    """Create the forward and reverse edges between two nodes — and the same
    pair for each parent field that the field subclasses — with any edge
    properties on all of them"""

    edge_property_assignments: PropertyAssignments | None = None
    if edge_properties:
        edge_property_assignments = PropertyAssignments(
            query_object.params, convert_edge_properties_for_writing(edge_properties)
        )

    edge_names = [(field_name, reverse_name)]
    for subclasses_field in subclasses_parent_fields:
        assert isinstance(subclasses_field, FieldSubclassing)
        edge_names.append(
            (
                subclasses_field.field_name,
                subclasses_field.field_on_model._meta.fields.relation_fields[
                    subclasses_field.field_name
                ].reverse_name,
            )
        )

    for forward_name, backward_name in edge_names:
        forward_query_identifier = query_object.params.new_identifier()
        reverse_query_identifier = query_object.params.new_identifier()
        query_object.create_query_strings.append(f"""
            CREATE ({source_identifier})-[{forward_query_identifier}:{forward_name}]->({target_identifier})
            CREATE ({source_identifier})<-[{reverse_query_identifier}:{backward_name} {{reverse: true}}]-({target_identifier})
        """)
        if edge_property_assignments:
            # `+=` adds to the edge's properties; `=` would replace them and
            # remove the {reverse: true} marker
            query_object.create_query_strings.append(f"""
                SET {edge_property_assignments.set_items(forward_query_identifier)}
                SET {edge_property_assignments.set_items(reverse_query_identifier)}
            """)


def build_related_node_query(
    query_object: QueryObject,
    instance: _AllCreateDBModels,
    source_identifier: Identifier,
    head_node_type: str,
    head_node_id: uuid.UUID,
    field_name: str,
    reverse_name: str,
    subclasses_parent_fields: typing.Iterable[str | FieldSubclassing],
    type_options: TypeOptions,
):

    node_identifier = query_object.params.new_identifier()
    instance_labels = get_label_query_string(instance, ["PGIndexableNode"])

    # Transform literal fields into a writeable dict
    node_data_dict = get_node_fields_as_writable_dict(
        instance,
        is_new=True,
        is_head_node=False,
        head_node_id=head_node_id,
        head_node_type=head_node_type,
        previous_meta=query_object.previous_meta.get(str(instance.id)),
    )
    query_object.nodes_to_write.append(
        NodeToWrite(id=str(instance.id), is_entity=instance.__metatype__ == "Entity")
    )

    # Add the node id identifier to params and get back an Identifier
    node_id_identifier = query_object.params.add(str(instance.id))

    # Add the properties to the query params
    node_data = PropertyAssignments(query_object.params, node_data_dict)

    query_object.create_query_strings.append(f"""
        MERGE ({node_identifier}:{instance_labels} {{id: ${node_id_identifier}}})
        ON CREATE SET {node_data.set_items(node_identifier, replace=True)}
    """)

    build_edges(
        query_object,
        source_identifier,
        node_identifier,
        field_name,
        reverse_name,
        subclasses_parent_fields,
        getattr(instance, "edge_properties", None),
    )

    # Attach all related nodes to the object; if this is a generic wrapper
    # (e.g. `Proxy[Person]`), its type variables are resolved from the field
    # it was attached through
    build_attached_nodes(
        query_object=query_object,
        instance=instance,
        instance_identifier=node_identifier,
        head_node_type=head_node_type,
        head_node_id=head_node_id,
        type_var_options=resolve_type_var_options(type_options, instance),
    )


def build_inline_entity_query(
    query_object: QueryObject,
    instance: "_EntityCreateDBBase",
    source_identifier: Identifier,
    field_name: str,
    reverse_name: str,
    subclasses_parent_fields: typing.Iterable[str | FieldSubclassing],
    type_options: TypeOptions,
):
    """An entity given in a document, with an id or URL of its own.

    It is not part of the document. If it exists, it is just related to, like any
    entity that is referred to. If not, it is created as `Entity.Create(...).save()`
    would create it: a head node, with its own record of creation, and nothing to
    do with the document (nor with the semantic spaces it is in)."""
    key = inline_entity_key(instance)
    query_object.inline_entities.append(
        InlineEntity(
            key=key,
            type=instance.type,
            field_name=field_name,
            allowed_types=tuple(allowed_type_names(type_options)),
            instance=instance,
        )
    )

    if key in query_object.inline_entity_identifiers:
        entity_identifier = query_object.inline_entity_identifiers[key]
    elif key in query_object.existing_entities:
        entity_identifier = query_object.params.new_identifier()
        existing_id = query_object.params.add(query_object.existing_entities[key].id)
        query_object.match_query_strings.append(
            f"MATCH ({entity_identifier}:PGIndexableNode {{id: ${existing_id}}})"
        )
        query_object.inline_entity_identifiers[key] = entity_identifier
    else:
        entity_identifier = query_object.params.new_identifier()
        query_object.inline_entity_identifiers[key] = entity_identifier
        entity_data = PropertyAssignments(
            query_object.params,
            get_node_fields_as_writable_dict(instance, is_new=True, is_head_node=True),
        )
        creation = query_object.params.new_identifier()
        creation_data = query_object.params.add(
            {
                "id": str(uuid.uuid7()),
                "created_when": datetime.datetime.now(datetime.UTC),
            }
        )
        query_object.create_query_strings.append(f"""
            CREATE ({entity_identifier}:{get_label_query_string(instance, ["HeadNode", "PGIndexableNode"])})
            SET {entity_data.set_items(entity_identifier, replace=True)}
            CREATE ({creation}:PGCreation)
            SET {creation} = ${creation_data}
            CREATE ({creation})-[:is_creation_of]->({entity_identifier})
            CREATE ({creation})-[:created_by]->(user)
        """)
        build_url_nodes(query_object, instance, entity_identifier)
        # Its own relations belong to it (it is the head node of them)
        build_attached_nodes(
            query_object=query_object,
            instance=typing.cast(_AllCreateDBModels, instance),
            instance_identifier=entity_identifier,
            head_node_type=instance.type,
            head_node_id=instance.id,
        )

    build_edges(
        query_object,
        source_identifier,
        entity_identifier,
        field_name,
        reverse_name,
        subclasses_parent_fields,
        getattr(instance, "edge_properties", None),
    )


def build_relation_to_existing_query(
    query_object: QueryObject,
    instance: _ReferenceSetBase,
    source_identifier: Identifier,
    field_name: str,
    reverse_name: str,
    subclasses_parent_fields: typing.Iterable[str | FieldSubclassing],
    type_options: TypeOptions,
):
    allowed_types = allowed_type_names(type_options)

    query_object.references.append(
        ReferenceToExisting(
            value=str(instance.id),
            is_url=isinstance(instance.id, AnyUrl),
            allowed_types=tuple(allowed_types),
            field_name=field_name,
        )
    )

    reference_key = (str(instance.id), tuple(allowed_types))
    if reference_key in query_object.matched_references:
        instance_identifier = query_object.matched_references[reference_key]
    else:
        instance_identifier = query_object.params.new_identifier()
        query_object.matched_references[reference_key] = instance_identifier
        id_identifier = query_object.params.add(str(instance.id))
        allowed_types_identifier = query_object.params.add(allowed_types)

        # An entity can be referred to by a URL, as well as by its id
        if isinstance(instance.id, AnyUrl):
            id_condition = "true"
            match_node = (
                f"(:PGUrl {{url: ${id_identifier}}})"
                f"<-[:has_url]-({instance_identifier}:PGIndexableNode)"
            )
        else:
            id_condition = "true"
            match_node = (
                f"({instance_identifier}:PGIndexableNode {{id: ${id_identifier}}})"
            )

        query_object.match_query_strings.append(
            f"""MATCH {match_node}
                WHERE {id_condition}
                AND ANY(label IN labels({instance_identifier}) WHERE label IN ${allowed_types_identifier})
            """
        )

    build_edges(
        query_object,
        source_identifier,
        instance_identifier,
        field_name,
        reverse_name,
        subclasses_parent_fields,
        getattr(instance, "edge_properties", None),
    )


def build_head_create_query(
    instance: _DocumentCreateDBBase | _EntityCreateDBBase,
    existing_entities: dict[InlineEntityKey, ExistingEntity] | None = None,
) -> QueryObject:

    # Initialise a query object with head values

    query_object = QueryObject(
        head_id=instance.id,
        head_type=instance.type,
        existing_entities=existing_entities,
    )

    # Create an Identifier for the node
    node_identifier = query_object.params.new_identifier()
    query_object.return_identifier = node_identifier

    # Map labels to a Cypher string
    instance_labels = get_label_query_string(instance, ["HeadNode", "PGIndexableNode"])

    # Transform literal fields into a writeable dict
    node_data_dict = get_node_fields_as_writable_dict(
        instance, is_new=True, is_head_node=True
    )

    # Add the properties to the query params
    node_data = PropertyAssignments(query_object.params, node_data_dict)

    # Build a Creation object connected to the created node and
    # current user
    creation_data_identifier = query_object.params.add(
        {
            "id": str(uuid.uuid7()),
            "created_when": datetime.datetime.now(datetime.UTC),
            # "data": compressed_data,
        }
    )

    # Match the current user username
    username_identifier = query_object.params.add(current_request_username.get())
    query_object.match_query_strings.append(
        f"""MATCH (user:PGUser {{username: ${username_identifier}}})"""
    )

    # Add Create and Set strings to query_object
    query_object.create_query_strings.append(f"""
        CREATE ({node_identifier}:{instance_labels})
        SET {node_data.set_items(node_identifier, replace=True)}
        CREATE (creation:PGCreation)
        SET creation = ${creation_data_identifier}
        CREATE (creation)-[:is_creation_of]->({node_identifier})
        CREATE (creation)-[:created_by]->(user)
    """)

    if isinstance(instance, _EntityCreateDBBase):
        build_url_nodes(query_object, instance, node_identifier)

    # Attach all related nodes to the object
    build_attached_nodes(
        query_object, instance, node_identifier, instance.type, instance.id
    )

    return query_object
