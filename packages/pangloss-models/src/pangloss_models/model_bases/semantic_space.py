from typing import Annotated, ClassVar, Literal

from pydantic import ConfigDict, Field
from pydantic.dataclasses import dataclass

from pangloss_models.field_definitions import (
    FieldDefinition,
    ModelFieldDict,
    ModelFields,
)
from pangloss_models.label_templates import LabelTemplateOption
from pangloss_models.meta_kit import BaseMeta, InheritValue, MetaRules, WithMeta
from pangloss_models.model_bases.base_models import (
    DeclaredClassMeta,
    _CreateBase,
    _CreateDBBase,
    _DeclaredClass,
    _UpdateBase,
    _UpdateDBBase,
    _ViewBase,
)

# The degree of what a space holds, in five steps (as an `Expectation` is judged)
DegreeStep = Literal["impossible", "unlikely", "possible", "likely", "expected"]
DEGREE_STEPS: tuple[DegreeStep, ...] = (
    "impossible",
    "unlikely",
    "possible",
    "likely",
    "expected",
)


@dataclass(frozen=True)
class Modal:
    """What a space says of its contents as a modality: `Modal("necessity", "command")` (it is ordered),
    `Modal("possibility", "epistemic")` (it may be so), `Modal("necessity", "command", of_not=True)` (it is ordered
    that it not be). The flavour is the project's own word: two spaces are of one modality when their flavours are
    the same."""

    force: Literal["necessity", "possibility"]
    flavour: Annotated[str, Field(min_length=1, pattern=r"^\S+$")]
    of_not: bool = False


class SemanticSpaceMeta(BaseMeta, DeclaredClassMeta):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    _owner_class: type[SemanticSpace] | InheritValue = InheritValue.AS_DEFAULT
    # How its label is worked out from what it holds (`pangloss_models.label_templates`): kept as its label if it has
    # one, else how it reads in the label of what holds it
    label_template: LabelTemplateOption = None
    abstract: Annotated[bool, MetaRules.DO_NOT_INHERIT] = False
    require_label: bool | InheritValue = False
    # What the space says of its contents (implementation_docs/semantic-space-fields.md). They are not data: a change
    # of one changes nothing stored. A subclass inherits each and may set any anew.
    # Whether what is inside is asserted (`1`), neither asserted nor denied (`0`) or denied (`-1`). `None`: what
    # `logical` implies (`veridicality`)
    veridical: Literal[1, 0, -1] | None = None
    # Whether the contents describe the world or say how it is to be (an order, a wish)
    fit: Literal["describes", "prescribes"] = "describes"
    # Its logic, where it has one that a program can use: a negation, or a modality
    logical: Literal["not"] | Modal | None = None
    # Whether it holds one item only. `None`: what `logical` implies (`is_unary`)
    unary: bool | None = None
    # How far its contents are taken to be so when nothing says otherwise of a statement, in five steps: an order
    # above a request. Only of a space whose contents are neither asserted nor denied
    degree: DegreeStep | None = None
    field_definitions: Annotated[ModelFields, MetaRules.DO_NOT_INHERIT] = Field(
        default_factory=ModelFields
    )

    @property
    def fields(self) -> ModelFieldDict[str, FieldDefinition]:
        return self.field_definitions.fields

    @property
    def veridicality(self) -> Literal[1, 0, -1]:
        """`veridical`, or what `logical` implies where it is not set: denied for a "not", else neither asserted
        nor denied"""
        if self.veridical is not None:
            return self.veridical
        return -1 if self.logical == "not" else 0

    @property
    def is_unary(self) -> bool:
        """`unary`, or what `logical` implies where it is not set: one item for a "not" and for a modality of not
        (of two items under a "not", neither is denied by itself)"""
        if self.unary is not None:
            return self.unary
        return self.logical == "not" or (
            isinstance(self.logical, Modal) and self.logical.of_not
        )


class _SemanticSpaceCreateBase(_CreateBase):
    pass


class _SemanticSpaceCreateDBBase(_CreateDBBase):
    pass


class _SemanticSpaceUpdateBase(_UpdateBase):
    pass


class _SemanticSpaceUpdateDBBase(_UpdateDBBase):
    pass


class _SemanticSpaceViewBase(_ViewBase):
    pass


class SemanticSpace[TContents](_DeclaredClass, WithMeta[SemanticSpaceMeta]):
    __metatype__ = "SemanticSpace"
    _meta: ClassVar[SemanticSpaceMeta] = SemanticSpaceMeta()
    Meta: ClassVar[type[SemanticSpaceMeta]] = SemanticSpaceMeta

    Create: ClassVar[type[_SemanticSpaceCreateBase]]
    CreateDB: ClassVar[type[_SemanticSpaceCreateDBBase]]
    Update: ClassVar[type[_SemanticSpaceUpdateBase]]
    UpdateDB: ClassVar[type[_SemanticSpaceUpdateDBBase]]

    View: ClassVar[type[_SemanticSpaceViewBase]]

    contents: list[TContents]
