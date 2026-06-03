from dataclasses import dataclass, field

from annotated_types import BaseMetadata

from pangloss_models.field_definitions import FieldBinding


@dataclass
class RelationConfig:
    reverse_name: str | None = None
    subclasses_parent_fields: list = field(default_factory=list)
    bind_to_child_field: list[FieldBinding] = field(default_factory=list)
    validators: list[BaseMetadata] = field(default_factory=list)
    description: str | None = None

    def __post_init__(self):
        if self.reverse_name:
            self.reverse_name = self.reverse_name.lower().replace(" ", "_")
