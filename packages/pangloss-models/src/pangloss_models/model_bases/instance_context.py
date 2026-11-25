"""The path of each node of an instance about to be written, with its semantic spaces (the
algorithm is `pangloss_models.context`, which migrations use too)"""

from typing import TYPE_CHECKING

from pangloss_models.context import (
    KIND_OF,
    PathEntry,
    propagate_context,
    spaces_of,
)
from pangloss_models.markers import degree_field
lazy from pangloss_models.model_bases.entity import (
    _EntityCreateDBBase,
    _EntityUpdateDBBase,
)

if TYPE_CHECKING:
    from pangloss_models.model_bases.base_models import _CreateDBBase, _UpdateDBBase


class _InstanceContext:
    """How the models look at an instance they are about to write, for `propagate_context`"""

    def is_entity(self, node):
        return isinstance(node, (_EntityCreateDBBase, _EntityUpdateDBBase))

    def kind_of(self, node):
        return KIND_OF[node.__metatype__]

    def type_of(self, node):
        return node.type

    def id_of(self, node):
        return str(node.id)

    def degree_of(self, node):
        name = degree_field(node._meta.fields)
        value = getattr(node, name, None) if name else None
        return None if value is None else str(getattr(value, "value", value))

    def children(self, node):
        from pangloss_models.model_bases.base_models import _CreateDBBase, _UpdateDBBase

        fields = node._meta.fields
        for field_name in (*fields.relation_fields, *fields.embedded_fields):
            related_item = getattr(node, field_name, None)
            if not related_item:
                continue
            if not isinstance(related_item, list):
                related_item = [related_item]
            for item in related_item:
                if isinstance(item, (_CreateDBBase, _UpdateDBBase)):
                    yield field_name, item

    def assign(self, node, path: list[PathEntry]):
        node.context_path = path
        node.semantic_spaces = spaces_of(path)


def propagate_instance_context(item: _CreateDBBase | _UpdateDBBase):
    """Give a `CreateDB` or `UpdateDB` instance, and each node it holds, its path, with the semantic spaces
    that follow from it"""
    propagate_context(item, _InstanceContext())
    return item
