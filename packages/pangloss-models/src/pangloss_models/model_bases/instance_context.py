"""The semantic spaces and context labels of an instance about to be written (the algorithm is
`pangloss_models.context`, which migrations use too)"""

from typing import TYPE_CHECKING

from pangloss_models.context import propagate_context
from pangloss_models.model_bases.context_label import ContextLabel

lazy from pangloss_models.model_bases.document import (
    _DocumentCreateDBBase,
    _DocumentUpdateDBBase,
)
lazy from pangloss_models.model_bases.entity import (
    _EntityCreateDBBase,
    _EntityUpdateDBBase,
)
lazy from pangloss_models.model_bases.semantic_space import (
    _SemanticSpaceCreateDBBase,
    _SemanticSpaceUpdateDBBase,
)

if TYPE_CHECKING:
    from pangloss_models.model_bases.base_models import _CreateDBBase, _UpdateDBBase


class _InstanceContext:
    """How the models look at an instance they are about to write, for `propagate_context`"""

    def is_entity(self, node):
        return isinstance(node, (_EntityCreateDBBase, _EntityUpdateDBBase))

    def is_space(self, node):
        return isinstance(node, (_SemanticSpaceCreateDBBase, _SemanticSpaceUpdateDBBase))

    def in_context(self, node):
        return isinstance(
            node, (_DocumentCreateDBBase, _DocumentUpdateDBBase)
        ) and node._meta.use_in_semantic_space_label

    def type_of(self, node):
        return node.type

    def id_of(self, node):
        return str(node.id)

    def children(self, node):
        from pangloss_models.model_bases.base_models import _CreateDBBase, _UpdateDBBase

        for field_name in node._meta.fields.relation_fields:
            if related_item := getattr(node, field_name, None):
                if isinstance(related_item, list):
                    for ri in related_item:
                        if isinstance(ri, (_CreateDBBase, _UpdateDBBase)):
                            yield ri, True
                elif isinstance(related_item, (_CreateDBBase, _UpdateDBBase)):
                    yield related_item, False

    def assign(self, node, semantic_spaces, context_labels):
        node.semantic_spaces = semantic_spaces
        node.context_labels = context_labels


def recursively_propagate_context_types(
    item: _CreateDBBase | _UpdateDBBase,
    semantic_spaces: list[str],
    context_labels: list[ContextLabel],
    parent: _CreateDBBase | _UpdateDBBase | None,
):
    """Takes a _CreateDBBase instance and recursively adds type of semantic
    spaces to each contained type below that semantic space node"""
    propagate_context(item, semantic_spaces, context_labels, parent, _InstanceContext())
    return item
