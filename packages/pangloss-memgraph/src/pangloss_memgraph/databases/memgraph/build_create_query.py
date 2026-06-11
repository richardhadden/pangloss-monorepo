import datetime
import typing
import uuid
from collections.abc import Iterable

from more_itertools import always_iterable
from pangloss_models.field_definitions import (
    FieldDefinition,
    FieldSubclassing,
    RelationFieldDefinition,
)
from pangloss_models.model_bases.base_models import _CreateDBBase, _ReferenceSetBase
from pangloss_models.model_bases.conjunction import _ConjunctionCreateDBBase
from pangloss_models.model_bases.document import _DocumentCreateDBBase
from pangloss_models.model_bases.embedded import _EmbeddedCreateDBBase
from pangloss_models.model_bases.entity import _EntityCreateDBBase
from pangloss_models.model_bases.reified_relation import (
    _ReifiedRelationCreateDBBase,
    _ReifiedRelationDocumentCreateDBBase,
)
from pangloss_models.model_bases.semantic_space import _SemanticSpaceCreateDBBase
from pangloss_users import current_request_username
from pydantic import AnyUrl

type _AllCreateDBModels = (
    _DocumentCreateDBBase
    | _EntityCreateDBBase
    | _ReifiedRelationCreateDBBase
    | _ReifiedRelationDocumentCreateDBBase
    | _ConjunctionCreateDBBase
    | _SemanticSpaceCreateDBBase
    | _EmbeddedCreateDBBase
)


class Identifier(str):
    def __new__(cls):
        return super().__new__(cls, "x" + uuid.uuid4().hex[:6].lower())


class QuerySubstring(str):
    def __new__(cls, query_string: str):
        return super().__new__(cls, query_string)


class QueryParams(dict[Identifier, dict[str, typing.Any] | typing.Any]):
    def add(self, item: dict[str, typing.Any] | typing.Any) -> Identifier:
        identifier = Identifier()
        self.__setitem__(identifier, item)
        return identifier


class QueryObject:
    match_query_strings: list[str]
    create_query_strings: list[str]
    merge_query_strings: list[str]
    set_query_strings: list[str]
    params: QueryParams
    return_identifier: Identifier
    head_id: uuid.UUID
    head_type: str | None

    def __init__(self, head_id: uuid.UUID, head_type: str):
        self.match_query_strings = []
        self.create_query_strings = []
        self.merge_query_strings = []
        self.set_query_strings = []
        self.params = QueryParams()
        self.head_type = head_type
        self.head_id = head_id

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
            RETURN {self.return_identifier}
        """,
        )


def convert_type_for_writing(value):
    match value:
        case uuid.UUID():
            return str(value)
        case AnyUrl():
            return str(value)
        case set():
            return list(value)
        case tuple():
            return list(value)
        case _:
            return value


def get_node_fields_as_writable_dict(
    instance: _AllCreateDBModels,
    is_new: bool = False,
    is_head_node: bool = False,
    head_node_type: str | None = None,
    head_node_id: uuid.UUID | None = None,
) -> dict[str, typing.Any]:

    node_data: dict[str, typing.Any] = {
        "id": str(instance.id),
        "type": instance.type,
    }

    # If it's new, we can create the whole meta object; otherwise, must be
    # updated granularly to preserve the created_by/created_when
    if is_new:
        node_data["meta"] = {
            "created_by": current_request_username.get(),
            "created_when": datetime.datetime.now(),
            "updated_by": current_request_username.get(),
            "updated_when": datetime.datetime.now(),
        }

    if not is_head_node:
        node_data["head_node_type"] = head_node_type
        node_data["head_node_id"] = head_node_id

    if label := getattr(instance, "label"):
        node_data["label"] = label
    for field_name in instance._meta.fields.literal_fields:
        if value := getattr(instance, field_name):
            node_data[field_name] = convert_type_for_writing(value)
    return node_data


def get_label_query_string(
    instance: _CreateDBBase, extra_labels: list[str] | None = None
) -> str:
    all_labels = (
        [*instance._labels, *extra_labels] if extra_labels else instance._labels
    )
    return f"{':'.join(all_labels)}"


def build_related_node_query(
    query_object: QueryObject,
    instance: _AllCreateDBModels,
    source_identifier: Identifier,
    head_node_type: str,
    head_node_id: uuid.UUID,
    field_definition: RelationFieldDefinition,
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
    )

    # Add the dict to the query params and get back an Identifier
    node_data_identifier = query_object.params.add(node_data_dict)

    query_object.create_query_strings.append(f"""
        CREATE ({node_identifier}:{instance_labels})
        CREATE ({source_identifier})-[:{field_definition.field_name}]->({node_identifier})
        CREATE ({source_identifier})<-[:{field_definition.reverse_name}]-({node_identifier})
        SET {node_identifier} = ${node_data_identifier}
    """)


def build_relation_query(
    query_object: QueryObject,
    instance: _ReferenceSetBase,
    source_identifier: Identifier,
    field_definition: RelationFieldDefinition,
):

    instance_identifier = Identifier()
    id_identifier = query_object.params.add(str(instance.id))
    query_object.match_query_strings.append(
        f"""MATCH ({instance_identifier}:PGIndexableNode {{id: ${id_identifier}}})"""
    )
    query_object.create_query_strings.append(f"""
        CREATE ({source_identifier})-[:{field_definition.field_name}]->({instance_identifier})
        CREATE ({source_identifier})<-[:{field_definition.reverse_name}]-({instance_identifier})
    """)

    """ TODO: add subclassed fields
    for subclasses_field in field_definition.subclasses_parent_fields:
        assert isinstance(subclasses_field, FieldSubclassing)
        subclasses_field.field_name
    """


def build_attached_nodes(
    query_object: QueryObject,
    instance: _AllCreateDBModels,
    instance_identifier: Identifier,
    head_node_type: str,
    head_node_id: uuid.UUID,
):
    for (
        related_field_name,
        related_field_def,
    ) in instance._meta.fields.relation_fields.items():
        if field_value := getattr(instance, related_field_name, None):
            # Todo: check this actually works properly;
            #
            if isinstance(field_value, list):
                items = field_value
            else:
                items = [field_value]

            for item in items:
                match item:
                    case _CreateDBBase():
                        build_related_node_query(
                            query_object=query_object,
                            instance=typing.cast(_AllCreateDBModels, item),
                            source_identifier=instance_identifier,
                            field_definition=related_field_def,
                            head_node_type=head_node_type,
                            head_node_id=head_node_id,
                        )
                    case _ReferenceSetBase():
                        build_relation_query(
                            query_object=query_object,
                            instance=item,
                            source_identifier=instance_identifier,
                            field_definition=related_field_def,
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

    # Add Create and Set strings to query_object
    query_object.create_query_strings.append(f"""
        CREATE ({node_identifier}:{instance_labels})
        SET {node_identifier} = ${node_data_identifier}

    """)

    # Attach all related nodes to the object
    build_attached_nodes(
        query_object, instance, node_identifier, instance.type, instance.id
    )

    return query_object
