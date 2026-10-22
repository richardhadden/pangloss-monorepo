"""The five models that are made from a declared model for writing and reading, described as data.

`Create` and `Update` are what a client sends, `CreateDB` and `UpdateDB` are what is written to the
database, and `View` is what is read. They are built by the same code (`builder.py`), which is
driven by a `ModelKind` for each. Everything that differs between them is a field here, so the
differences can be seen together, and each can be changed (or removed) in one place.

Some differences are by design (a client model has bindings and descriptions, a database model has
neither); some look accidental and are kept as they were. Those are marked `quirk:`, and listed in
`docs/initialise-models-cleanup.md`, "Decisions needed".
"""

from dataclasses import dataclass
from typing import Literal

from pangloss_models.model_bases.annotated_value import AnnotatedValue  # noqa: F401 (documented)
from pangloss_models.model_bases.conjunction import (
    Conjunction,
    _ConjunctionCreateBase,
    _ConjunctionCreateDBBase,
    _ConjunctionUpdateBase,
    _ConjunctionUpdateDBBase,
    _ConjunctionViewBase,
)
from pangloss_models.model_bases.document import (
    Document,
    _DocumentCreateBase,
    _DocumentCreateDBBase,
    _DocumentUpdateBase,
    _DocumentUpdateDBBase,
    _DocumentViewBase,
)
from pangloss_models.model_bases.embedded import (
    Embedded,
    _EmbeddedCreateBase,
    _EmbeddedCreateDBBase,
    _EmbeddedUpdateBase,
    _EmbeddedUpdateDBBAse,
    _EmbeddedViewBase,
)
from pangloss_models.model_bases.entity import (
    Entity,
    _EntityCreateBase,
    _EntityCreateDBBase,
    _EntityUpdateBase,
    _EntityUpdateDBBase,
    _EntityViewBase,
)
from pangloss_models.model_bases.reified_relation import (
    ReifiedRelation,
    ReifiedRelationDocument,
    _ReifiedRelationCreateBase,
    _ReifiedRelationCreateDBBase,
    _ReifiedRelationDocumentCreateBase,
    _ReifiedRelationDocumentCreateDBBase,
    _ReifiedRelationDocumentUpdateBase,
    _ReifiedRelationDocumentUpdateDBBase,
    _ReifiedRelationDocumentViewBase,
    _ReifiedRelationUpdateBase,
    _ReifiedRelationUpdateDBBase,
    _ReifiedRelationViewBase,
)
from pangloss_models.model_bases.semantic_space import (
    SemanticSpace,
    _SemanticSpaceCreateBase,
    _SemanticSpaceCreateDBBase,
    _SemanticSpaceUpdateBase,
    _SemanticSpaceUpdateDBBase,
    _SemanticSpaceViewBase,
)

# Where a relation is being worked out:
#   "field":   a relation field of a declared model (`Statement.about: Person`)
#   "typevar": what a generic wrapper's type variable stands for (`Person` in `InRole[Person]`)
#   "direct":  a relation field of the wrapper itself, that is not its type variable
Site = Literal["field", "typevar", "direct"]

# The conditions that can make a field optional (see `FieldRule`):
#   "bound":    a binding of the parent gives the field its value, so it need not be given
#   "fulfil":   a class that `Fulfils` another supplies the field, so it need not be given
#   "optional": the type of the field is itself optional (`int | None`)
Condition = Literal["bound", "fulfil", "optional"]


@dataclass(frozen=True)
class FieldRule:
    """When a field is nullable, and when it has a default of `None`"""

    nullable_when: frozenset[Condition] = frozenset()
    default_none_when: frozenset[Condition] = frozenset()


def rule(nullable: set[Condition], default_none: set[Condition]) -> FieldRule:
    return FieldRule(frozenset(nullable), frozenset(default_none))


@dataclass(frozen=True)
class ModelKind:
    attribute: str
    """The name of the model, and the attribute of the declared class that it is set on"""
    bases: tuple[tuple[type, type], ...]
    """The base class for each kind of declared model (the first that matches is used)"""
    offers: tuple[str, ...]
    """The models offered for a document, an embedded object or a generic in a relation: this one,
    and any other that may be given in its place (`Update` takes a new `Create` too)"""

    # --- entities ---------------------------------------------------------------------------------
    reference: str
    """What an entity is referred to by: `ReferenceSet` (to write) or `ReferenceView` (to read)"""
    inline: str
    """The model of an entity that is made when a document names it (`create_inline`)"""
    inline_plain: bool
    """Whether it is offered for a relation with no edge model"""
    inline_with_edge: frozenset[Site]
    """The sites where it is offered for a relation with an edge model. quirk: a relation field of a
    declared model in a client model does not offer it, and everywhere else does"""
    inline_first: frozenset[tuple[Site, bool]]
    """Where it comes before the reference in the union, as (site, has an edge model). The database
    models put it first so that a new entity is not taken for a reference to an existing one.
    quirk: the order is not the same at every site, nor in every model"""

    # --- documents --------------------------------------------------------------------------------
    document_typevar: tuple[str, ...] | None = None
    """If a document that a wrapper's type variable stands for offers its models in another order than
    `offers`. quirk: `Update` puts `Create` first there (the order of a union can decide which member
    pydantic uses when more than one fits)"""
    document_direct: tuple[str, ...] | None = None
    """If a generic's own document relation offers other models than `offers`. quirk: `Update` offers
    only `Create` there, so a document of a wrapper cannot be given as an update"""

    # --- how the models are made ------------------------------------------------------------------
    bound_suffix: str = ""
    """The end of the name of a model made for bindings. quirk: `Update` has none"""
    type_uses_field: bool = False
    """quirk: the `type` of `Update` is given as `Field(default=...)`, the others as a plain default"""
    id_fields: bool = False
    """Whether `id` and `create_new` are added (if the class can be given an id)"""
    bound_id_fields: bool = False
    base_validators: bool = False
    """Whether the model has the validator that `id` and `create_new` go together"""
    generic_validators: bool = False
    bound_validators: bool = False

    # --- what is applied --------------------------------------------------------------------------
    applies_bindings: bool = False
    skip_db_fields: bool = False
    """Client models leave out fields that are only written to the database (`DBField`)"""
    descriptions: bool = False
    discriminated: bool = False
    """Whether the union of a relation is discriminated on `type`"""
    empty_list_default: bool = False
    """Whether a list relation with nothing in it has an empty list (nothing is stored, so none read)"""
    bind_generic_itself: bool = False
    """Whether the bindings are applied to the model made for a generic. quirk: not for `Update`
    (the code that did so assigned its result to a name that was never used)"""
    cache_generic: bool = False
    """quirk: only the models made for generics in `Update` are cached"""
    copy_fields_from: str = ""
    """quirk: the model whose fields are copied onto the model made for a generic. For `Update` that is
    `Create`"""

    # --- the optional fields ----------------------------------------------------------------------
    literal: FieldRule = FieldRule()
    embedded: FieldRule = FieldRule()
    relation: FieldRule = FieldRule()
    annotated_value: FieldRule = FieldRule()


def bases_for(suffix: str, embedded_base: type | None = None) -> tuple[tuple[type, type], ...]:
    """The base classes `_<Kind><Suffix>Base` of the generated model of each declared kind"""
    pairs = {
        "Create": (
            _DocumentCreateBase,
            _EntityCreateBase,
            _ReifiedRelationCreateBase,
            _ReifiedRelationDocumentCreateBase,
            _ConjunctionCreateBase,
            _SemanticSpaceCreateBase,
            _EmbeddedCreateBase,
        ),
        "CreateDB": (
            _DocumentCreateDBBase,
            _EntityCreateDBBase,
            _ReifiedRelationCreateDBBase,
            _ReifiedRelationDocumentCreateDBBase,
            _ConjunctionCreateDBBase,
            _SemanticSpaceCreateDBBase,
            _EmbeddedCreateDBBase,
        ),
        "Update": (
            _DocumentUpdateBase,
            _EntityUpdateBase,
            _ReifiedRelationUpdateBase,
            _ReifiedRelationDocumentUpdateBase,
            _ConjunctionUpdateBase,
            _SemanticSpaceUpdateBase,
            _EmbeddedUpdateBase,
        ),
        "UpdateDB": (
            _DocumentUpdateDBBase,
            _EntityUpdateDBBase,
            _ReifiedRelationUpdateDBBase,
            _ReifiedRelationDocumentUpdateDBBase,
            _ConjunctionUpdateDBBase,
            _SemanticSpaceUpdateDBBase,
            _EmbeddedUpdateDBBAse,
        ),
        "View": (
            _DocumentViewBase,
            _EntityViewBase,
            _ReifiedRelationViewBase,
            _ReifiedRelationDocumentViewBase,
            _ConjunctionViewBase,
            _SemanticSpaceViewBase,
            _EmbeddedViewBase,
        ),
    }[suffix]
    # (the order matters: ReifiedRelationDocument is checked after ReifiedRelation, as it always was)
    declared = (
        Document,
        Entity,
        ReifiedRelation,
        ReifiedRelationDocument,
        Conjunction,
        SemanticSpace,
        Embedded,
    )
    return tuple(zip(declared, pairs))


CLIENT_LITERAL = rule({"bound", "fulfil"}, {"bound", "fulfil", "optional"})

CREATE = ModelKind(
    attribute="Create",
    bases=bases_for("Create"),
    offers=("Create",),
    reference="ReferenceSet",
    inline="Create",
    inline_plain=True,
    inline_with_edge=frozenset({"typevar", "direct"}),
    inline_first=frozenset({("typevar", False)}),
    bound_suffix="Create",
    id_fields=True,
    bound_id_fields=True,
    base_validators=True,
    generic_validators=True,
    bound_validators=True,
    applies_bindings=True,
    skip_db_fields=True,
    descriptions=True,
    bind_generic_itself=True,
    copy_fields_from="Create",
    literal=CLIENT_LITERAL,
    embedded=rule({"bound"}, {"bound"}),
    relation=rule({"bound", "fulfil"}, {"bound", "fulfil"}),
    annotated_value=rule({"bound"}, {"bound"}),
)

UPDATE = ModelKind(
    attribute="Update",
    bases=bases_for("Update"),
    offers=("Update", "Create"),
    reference="ReferenceSet",
    inline="Create",
    inline_plain=True,
    inline_with_edge=frozenset({"typevar", "direct"}),
    inline_first=frozenset(),
    document_typevar=("Create", "Update"),
    document_direct=("Create",),
    bound_suffix="",
    type_uses_field=True,
    generic_validators=True,
    bound_validators=True,
    applies_bindings=True,
    skip_db_fields=True,
    descriptions=True,
    cache_generic=True,
    copy_fields_from="Create",
    literal=CLIENT_LITERAL,
    embedded=rule({"bound", "fulfil"}, {"bound"}),
    relation=rule({"bound", "fulfil"}, {"bound", "fulfil"}),
    annotated_value=rule({"bound", "fulfil"}, {"bound"}),
)

CREATE_DB = ModelKind(
    attribute="CreateDB",
    bases=bases_for("CreateDB"),
    offers=("CreateDB",),
    reference="ReferenceSet",
    inline="CreateDB",
    inline_plain=True,
    inline_with_edge=frozenset({"field", "typevar", "direct"}),
    inline_first=frozenset(
        {("field", False), ("typevar", True), ("typevar", False), ("direct", True)}
    ),
    id_fields=True,
    base_validators=True,
    generic_validators=True,
    copy_fields_from="CreateDB",
    literal=rule(set(), {"fulfil", "optional"}),
    embedded=rule(set(), {"fulfil"}),
    relation=rule({"fulfil"}, {"fulfil"}),
    annotated_value=rule(set(), {"fulfil"}),
)

UPDATE_DB = ModelKind(
    attribute="UpdateDB",
    bases=bases_for("UpdateDB"),
    offers=("UpdateDB", "CreateDB"),
    reference="ReferenceSet",
    inline="CreateDB",
    inline_plain=True,
    inline_with_edge=frozenset({"field", "typevar", "direct"}),
    inline_first=frozenset(
        {
            ("field", False),
            ("field", True),
            ("typevar", True),
            ("typevar", False),
            ("direct", True),
            ("direct", False),
        }
    ),
    id_fields=True,
    copy_fields_from="UpdateDB",
    literal=rule(set(), {"optional"}),
    embedded=rule(set(), set()),
    relation=rule({"fulfil"}, {"fulfil"}),
    annotated_value=rule(set(), set()),
)

VIEW = ModelKind(
    attribute="View",
    bases=bases_for("View"),
    offers=("View",),
    reference="ReferenceView",
    inline="View",
    inline_plain=False,
    inline_with_edge=frozenset({"direct"}),
    inline_first=frozenset(),
    bound_suffix="View",
    applies_bindings=True,
    skip_db_fields=True,
    descriptions=True,
    discriminated=True,
    empty_list_default=True,
    bind_generic_itself=True,
    copy_fields_from="View",
    literal=CLIENT_LITERAL,
    embedded=rule({"bound"}, {"bound"}),
    relation=rule({"bound", "fulfil"}, {"bound", "fulfil"}),
    annotated_value=rule({"bound"}, {"bound"}),
)

KINDS: dict[str, ModelKind] = {
    kind.attribute: kind for kind in (CREATE, UPDATE, CREATE_DB, UPDATE_DB, VIEW)
}
