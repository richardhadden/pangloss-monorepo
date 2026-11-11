"""Pangloss models: declare research data as Python classes, and generate their create, update and view models.

What a project or an add-on uses is imported from here (`from pangloss_models import Document, initialise`), not from
the module it is kept in; the imports are lazy, so nothing is loaded until it is used. See implementation_docs/imports.md.
"""

lazy from pangloss_models.creators import Creator, ToolchainRun
lazy from pangloss_models.model_bases.annotated_value import AnnotatedValue
lazy from pangloss_models.model_bases.configs import RelationConfig
lazy from pangloss_models.model_bases.conjunction import Conjunction
lazy from pangloss_models.model_bases.context_label import ContextLabel
lazy from pangloss_models.model_bases.document import Document
lazy from pangloss_models.model_bases.edge_model import EdgeModel
lazy from pangloss_models.model_bases.embedded import Embedded
lazy from pangloss_models.model_bases.entity import Entity
lazy from pangloss_models.model_bases.helpers import (
    DBField,
    Description,
    Fulfils,
    ViaEdge,
)
lazy from pangloss_models.model_bases.reified_relation import (
    ReifiedRelation,
    ReifiedRelationDocument,
)
lazy from pangloss_models.model_bases.semantic_space import SemanticSpace
lazy from pangloss_models.model_bases.trait import (
    NonHeritableTrait,
    Trait,
)
lazy from pangloss_models.field_definitions import (
    FieldBinding,
    FieldSubclassing,
)
lazy from pangloss_models.validators import SumsTo
lazy from pangloss_models.markers import FieldMarker
lazy from pangloss_models.literals import (
    LiteralCodec,
    register_codec,
)
lazy from pangloss_models.search import (
    AnyOf,
    Match,
    Not,
    OrderBy,
    Var,
)
lazy from pangloss_models.search_where import (
    AnyRel,
    Choice,
    Compare,
    IncomingFrom,
    Items,
    Rel,
    Text,
    Where,
)
lazy from pangloss_models.hooks import WriteEvent
lazy from pangloss_models.meta_slots import register_meta_slot
lazy from pangloss_models.protection import (
    Protection,
    protection_of,
)
lazy from pangloss_models.usage import (
    Usage,
    included_only_when_referenced,
)
lazy from pangloss_models.export import export_models
lazy from pangloss_models.label_templates import (
    Formatter,
    LabelTemplate,
    register_label_formatter,
)
lazy from pangloss_models.text import fold
lazy from pangloss_models.exceptions import (
    PanglossAwaitingInitialisation,
    PanglossBulkLoadError,
    PanglossBulkRecordError,
    PanglossClassChangeError,
    PanglossConflictError,
    PanglossEntityInUseError,
    PanglossImportError,
    PanglossInitialisationError,
    PanglossInternalError,
    PanglossMetaError,
    PanglossMigrationAnswerNeeded,
    PanglossMigrationError,
    PanglossMigrationIrreversible,
    PanglossMigrationNotSupported,
    PanglossModelError,
    PanglossModelWarning,
    PanglossNotCreatableError,
    PanglossNotDeletableError,
    PanglossNotDeletedError,
    PanglossNotFoundError,
    PanglossReadOnlyError,
    PanglossReferenceError,
    PanglossRuntimeError,
    PanglossSearchError,
    PanglossSearchTimeoutError,
    PanglossServerOnly,
    PanglossUnknownTypeError,
    PanglossUserDisabledError,
    PanglossUserNotFoundError,
    PanglossVersionConflictError,
    PanglossWriteError,
    PanglossWriteRefused,
)
lazy from pangloss_models.write_checks import (
    before_create,
    before_update,
    create_validator,
    update_validator,
)

from pangloss_models import hooks
from pangloss_models import protection  # (registers the `_protect_meta` slot)
from pangloss_models import usage  # (registers the `_usage_meta` slot)
from pangloss_models.model_registry import ModelRegistry
from pangloss_models.server_only import server_only

initialise = ModelRegistry.finalise

__all__ = [
    "Creator",
    "ToolchainRun",
    "AnnotatedValue",
    "AnyOf",
    "AnyRel",
    "Choice",
    "Compare",
    "Conjunction",
    "ContextLabel",
    "DBField",
    "Description",
    "Document",
    "EdgeModel",
    "Embedded",
    "Entity",
    "export_models",
    "FieldBinding",
    "FieldMarker",
    "FieldSubclassing",
    "fold",
    "Formatter",
    "Fulfils",
    "hooks",
    "IncomingFrom",
    "initialise",
    "Items",
    "LabelTemplate",
    "LiteralCodec",
    "Match",
    "ModelRegistry",
    "NonHeritableTrait",
    "Not",
    "OrderBy",
    "PanglossAwaitingInitialisation",
    "PanglossBulkLoadError",
    "PanglossBulkRecordError",
    "PanglossClassChangeError",
    "PanglossConflictError",
    "PanglossEntityInUseError",
    "PanglossImportError",
    "PanglossInitialisationError",
    "PanglossInternalError",
    "PanglossMetaError",
    "PanglossMigrationAnswerNeeded",
    "PanglossMigrationError",
    "PanglossMigrationIrreversible",
    "PanglossMigrationNotSupported",
    "PanglossModelError",
    "PanglossModelWarning",
    "PanglossNotCreatableError",
    "PanglossNotDeletableError",
    "PanglossNotDeletedError",
    "PanglossNotFoundError",
    "PanglossReadOnlyError",
    "PanglossReferenceError",
    "PanglossRuntimeError",
    "PanglossSearchError",
    "PanglossSearchTimeoutError",
    "PanglossServerOnly",
    "PanglossUnknownTypeError",
    "PanglossUserDisabledError",
    "PanglossUserNotFoundError",
    "PanglossVersionConflictError",
    "PanglossWriteError",
    "PanglossWriteRefused",
    "before_create",
    "before_update",
    "create_validator",
    "update_validator",
    "Protection",
    "Usage",
    "included_only_when_referenced",
    "protection",
    "usage",
    "protection_of",
    "register_meta_slot",
    "ReifiedRelation",
    "register_codec",
    "register_label_formatter",
    "ReifiedRelationDocument",
    "Rel",
    "RelationConfig",
    "SemanticSpace",
    "server_only",
    "SumsTo",
    "Text",
    "Trait",
    "Var",
    "ViaEdge",
    "Where",
    "WriteEvent",
]
