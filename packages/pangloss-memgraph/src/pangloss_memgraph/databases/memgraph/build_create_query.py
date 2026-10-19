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
from pangloss_models.model_bases.annotated_value import AnnotatedValue
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
    def __new__(cls):
        return super().__new__(cls, "x" + uuid.uuid4().hex[:10].lower())


class QuerySubstring(str):
    def __new__(cls, query_string: str):
        return super().__new__(cls, query_string)


class QueryParams(dict[Identifier, dict[str, typing.Any] | typing.Any]):
    def add(self, item: dict[str, typing.Any] | typing.Any) -> Identifier:
        identifier = Identifier()
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
    references: list[ReferenceToExisting]
    nodes_to_write: list[NodeToWrite]
    # `meta` of nodes of the tree being replaced in an update, by node id, so that
    # `created_by` and `created_when` are kept
    previous_meta: dict[str, dict[str, typing.Any]]

    def __init__(self, head_id: uuid.UUID, head_type: str):
        self.match_query_strings = []
        self.create_query_strings = []
        self.merge_query_strings = []
        self.set_query_strings = []
        self.params = QueryParams()
        self.head_type = head_type
        self.head_id = head_id
        self.references = []
        self.nodes_to_write = []
        self.previous_meta = {}

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
    - `Enum` members are stored as their value. (To be replaced by Memgraph's
      native enum type, which needs to be created ahead of time.)
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

    # Entities given a URL as id keep the URL(s) so they can be found by them
    if urls := getattr(instance, "urls", None):
        node_data["urls"] = sorted(str(url) for url in urls)

    # Compare with None rather than truthiness: 0, 0.0, "" and [] are real values
    if (label := getattr(instance, "label", None)) is not None:
        node_data["label"] = label
    for field_name in instance._meta.fields.literal_fields:
        if (value := getattr(instance, field_name)) is not None:
            node_data[field_name] = convert_type_for_writing(value)
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
    relations, embedded objects and annotated values"""

    fields = instance._meta.fields

    for related_field_name, related_field_def in fields.relation_fields.items():
        type_options = substitute_type_vars(
            related_field_def.type_options, type_var_options or {}
        )
        for item in iter_values(getattr(instance, related_field_name, None)):
            match item:
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

    for annotated_field_name in fields.annotated_value_fields:
        for item in iter_values(getattr(instance, annotated_field_name, None)):
            build_annotated_value_query(
                query_object=query_object,
                instance=item,
                source_identifier=instance_identifier,
                field_name=annotated_field_name,
                head_node_type=head_node_type,
                head_node_id=head_node_id,
            )


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

    edge_properties_identifier: Identifier | None = None
    if edge_properties:
        edge_properties_identifier = query_object.params.add(
            convert_edge_properties_for_writing(edge_properties)
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
        forward_query_identifier = Identifier()
        reverse_query_identifier = Identifier()
        query_object.create_query_strings.append(f"""
            CREATE ({source_identifier})-[{forward_query_identifier}:{forward_name}]->({target_identifier})
            CREATE ({source_identifier})<-[{reverse_query_identifier}:{backward_name} {{reverse: true}}]-({target_identifier})
        """)
        if edge_properties_identifier:
            # `+=` adds to the edge's properties; `=` would replace them and
            # remove the {reverse: true} marker
            query_object.create_query_strings.append(f"""
                SET {forward_query_identifier} += ${edge_properties_identifier}
                SET {reverse_query_identifier} += ${edge_properties_identifier}
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

    node_identifier = Identifier()
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

    # Add the dict to the query params and get back an Identifier
    node_data_identifier = query_object.params.add(node_data_dict)

    query_object.create_query_strings.append(f"""
        MERGE ({node_identifier}:{instance_labels} {{id: ${node_id_identifier}}})
        ON CREATE SET {node_identifier} = ${node_data_identifier}
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


def build_annotated_value_query(
    query_object: QueryObject,
    instance: AnnotatedValue,
    source_identifier: Identifier,
    field_name: str,
    head_node_type: str,
    head_node_id: uuid.UUID,
):
    """An annotated value (a value with extra literal fields) is written as a
    node holding `value` and the extra fields"""

    # `WithCertainty[str]` is labelled `WithCertainty`
    instance_class = type(instance)
    base_class = instance_class.__pydantic_generic_metadata__["origin"] or instance_class
    type_name = base_class.__name__

    node_data: dict[str, typing.Any] = {
        "id": str(uuid.uuid7()),
        "type": type_name,
        "head_node_type": head_node_type,
        "head_node_id": str(head_node_id),
    }
    for key, value in instance.model_dump().items():
        if value is not None:
            node_data[key] = convert_type_for_writing(value)

    node_identifier = Identifier()
    node_data_identifier = query_object.params.add(node_data)
    query_object.create_query_strings.append(f"""
        CREATE ({node_identifier}:{type_name}:AnnotatedValue)
        SET {node_identifier} = ${node_data_identifier}
    """)

    build_edges(
        query_object,
        source_identifier,
        node_identifier,
        field_name,
        default_reverse_name(field_name),
        (),
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
    allowed_types = sorted(
        {
            type_option.annotated_type.__name__
            for type_option in type_options
            if isinstance(type_option, (RelationToEntity, RelationToDocument))
        }
    )

    query_object.references.append(
        ReferenceToExisting(
            value=str(instance.id),
            is_url=isinstance(instance.id, AnyUrl),
            allowed_types=tuple(allowed_types),
            field_name=field_name,
        )
    )

    instance_identifier = Identifier()
    id_identifier = query_object.params.add(str(instance.id))
    allowed_types_identifier = query_object.params.add(allowed_types)

    # An entity can be referred to by a URL, as well as by its id
    if isinstance(instance.id, AnyUrl):
        id_condition = f"${id_identifier} IN {instance_identifier}.urls"
        match_node = f"({instance_identifier}:PGIndexableNode)"
    else:
        id_condition = "true"
        match_node = f"({instance_identifier}:PGIndexableNode {{id: ${id_identifier}}})"

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
) -> QueryObject:

    # Initialise a query object with head values

    query_object = QueryObject(head_id=instance.id, head_type=instance.type)

    # Create an Identifier for the node
    node_identifier = Identifier()
    query_object.return_identifier = node_identifier

    # Map labels to a Cypher string
    instance_labels = get_label_query_string(instance, ["HeadNode", "PGIndexableNode"])

    # Transform literal fields into a writeable dict
    node_data_dict = get_node_fields_as_writable_dict(
        instance, is_new=True, is_head_node=True
    )

    # Add the dict to the query params and get back an Identifier
    node_data_identifier = query_object.params.add(node_data_dict)

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
        SET {node_identifier} = ${node_data_identifier}
        CREATE (creation:PGCreation)
        SET creation = ${creation_data_identifier}
        CREATE (creation)-[:is_creation_of]->({node_identifier})
        CREATE (creation)-[:created_by]->(user)
    """)

    # Attach all related nodes to the object
    build_attached_nodes(
        query_object, instance, node_identifier, instance.type, instance.id
    )

    return query_object
