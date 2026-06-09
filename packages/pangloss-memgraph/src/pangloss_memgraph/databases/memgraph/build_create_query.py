import datetime
import typing
import uuid

from pangloss_models.model_bases.base_models import _CreateDBBase
from pangloss_models.model_bases.document import _DocumentCreateDBBase
from pangloss_models.model_bases.entity import _EntityCreateDBBase
from pydantic import AnyUrl


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


def get_literal_fields_as_writable_dict(
    instance: _DocumentCreateDBBase | _EntityCreateDBBase,
) -> dict[str, typing.Any]:
    node_data = {
        "id": str(instance.id),
        "type": instance.type,
        "meta": {
            "created_by": "testuser",
            "created_when": str(datetime.datetime.now()),
            "updated_by": "testuser",
            "updated_when": str(datetime.datetime.now()),
        },
    }
    if label := getattr(instance, "label"):
        node_data["label"] = label
    for field_name in instance._meta.fields.literal_fields:
        if value := getattr(instance, field_name):
            node_data[field_name] = value
    return node_data


def get_label_query_string(
    instance: _CreateDBBase, extra_labels: list[str] | None = None
) -> str:
    all_labels = (
        [*instance._labels, *extra_labels] if extra_labels else instance._labels
    )
    return f"{':'.join(all_labels)}"


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
    node_data_dict = get_literal_fields_as_writable_dict(instance)
    print(instance)
    print(node_data_dict)
    # Add the dict to the query params and get back an Identifier
    node_data_identifier = query_object.params.add(node_data_dict)

    query_object.create_query_strings.append(f"""
        CREATE ({node_identifier}:{instance_labels})
        SET {node_identifier} = ${node_data_identifier}

    """)

    return query_object
