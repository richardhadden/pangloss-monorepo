"""The changes that can be found between two snapshots.

Each is a small immutable record of one thing that changed, with how safe it is
(`safety`, as in `docs/migrations.md` section 5) and a description for a person. What a
change does to the data is the business of the operations that are made from them later.
"""

from dataclasses import asdict, dataclass, field
from typing import Any, ClassVar, Literal

Safety = Literal["safe", "additive", "transforming", "lossy", "manual"]

# The order they are applied in: renames first (everything after uses the new names), then
# what others need is made, and what is gone is last
PHASE_RENAME = 0
PHASE_CREATE = 1
PHASE_ALTER = 2
PHASE_ADD_FIELD = 3
PHASE_REMOVE_FIELD = 4
PHASE_REMOVE = 5
PHASE_FULFILS = 6  # (last: it is worked out from the models as they are then)


@dataclass(frozen=True, kw_only=True)
class Change:
    """One thing that changed.

    The fields say what changed and what it is now (so that applying the changes to the
    old snapshot gives the new: `state.replay`). Some also have fields for an *answer* that
    only a person can give (a value for existing nodes, what to do with what does not
    convert); they are `None` as found by `diff`, and are filled in when the migration is
    written. A change that needs one and has none cannot be applied to a database."""

    phase: ClassVar[int] = PHASE_ALTER
    safety: ClassVar[Safety] = "safe"

    @property
    def kind(self) -> str:
        return type(self).__name__

    def describe(self) -> str:
        raise NotImplementedError

    def to_dict(self) -> dict[str, Any]:
        """The change as plain data, for a migration file (`change_from_dict` reads it)"""
        return {"change": self.kind, "safety": self.safety, **asdict(self)}


@dataclass(frozen=True, kw_only=True)
class PossibleRename:
    """Something was removed and something like it added: a rename? Only a person can
    say (the answer is given to `diff`), so it is a question, not a change."""

    what: Literal["model", "enum", "field", "enum_member"]
    # The model or enum it is in (None for a model or an enum)
    scope: str | None = None
    old: str
    new: str

    def question(self) -> str:
        if self.what in ("model", "enum"):
            return f"Was the {self.what} '{self.old}' renamed to '{self.new}'?"
        return (
            f"In '{self.scope}', was the "
            f"{'field' if self.what == 'field' else 'enum member'} '{self.old}' "
            f"renamed to '{self.new}'?"
        )


# --- enums -------------------------------------------------------------------------------


@dataclass(frozen=True, kw_only=True)
class CreateEnum(Change):
    phase: ClassVar[int] = PHASE_CREATE
    enum: str
    # The enum as in a snapshot: {"name": ..., "members": [{"name": ..., "value": ...}]}
    definition: dict[str, Any] = field(default_factory=dict)

    @property
    def members(self) -> list[str]:
        return [m["name"] for m in self.definition.get("members", [])]

    def describe(self) -> str:
        return f"Create the enum {self.enum} ({', '.join(self.members)})"


@dataclass(frozen=True, kw_only=True)
class AddEnumMember(Change):
    phase: ClassVar[int] = PHASE_CREATE
    enum: str
    member: str
    value: Any = None

    def describe(self) -> str:
        return f"Add {self.member} to the enum {self.enum}"


@dataclass(frozen=True, kw_only=True)
class RenameEnumMember(Change):
    """The name of a member changed and its value did not: an enum is stored as the values of its
    members, so nothing is stored of the name and there is nothing to do to the data"""

    phase: ClassVar[int] = PHASE_RENAME
    enum: str
    old: str
    new: str

    def describe(self) -> str:
        return f"Rename {self.enum}.{self.old} to {self.new} (the value is the same)"


@dataclass(frozen=True, kw_only=True)
class AlterEnumMemberValue(Change):
    """The value of a member changed: the data that has the old value is given the new"""

    safety: ClassVar[Safety] = "transforming"
    enum: str
    member: str
    old: Any
    new: Any

    def describe(self) -> str:
        return f"The value of {self.enum}.{self.member} changes from {self.old!r} to {self.new!r} (stored values follow)"


@dataclass(frozen=True, kw_only=True)
class RenameEnum(Change):
    """An enum has another name: nothing is stored of it, so there is nothing to do to the data"""

    phase: ClassVar[int] = PHASE_RENAME
    old: str
    new: str

    def describe(self) -> str:
        return f"Rename the enum {self.old} to {self.new}"


@dataclass(frozen=True, kw_only=True)
class RemoveEnumMember(Change):
    """A member that the models no longer have: the data that has its value has to be moved"""

    phase: ClassVar[int] = PHASE_REMOVE
    safety: ClassVar[Safety] = "transforming"
    enum: str
    member: str
    # Answer: the member that values with this one are given (None: fail if any have it)
    replacement: str | None = None

    def describe(self) -> str:
        return (
            f"Stop using {self.enum}.{self.member}: values that have it are moved"
        )


@dataclass(frozen=True, kw_only=True)
class RemoveEnum(Change):
    phase: ClassVar[int] = PHASE_REMOVE
    safety: ClassVar[Safety] = "transforming"
    enum: str

    def describe(self) -> str:
        return f"Stop using the enum {self.enum}"


# --- models ------------------------------------------------------------------------------


@dataclass(frozen=True, kw_only=True)
class CreateModel(Change):
    phase: ClassVar[int] = PHASE_CREATE
    model: str
    model_kind: str
    # The model as in a snapshot, with its fields
    definition: dict[str, Any] = field(default_factory=dict)

    def describe(self) -> str:
        return f"Create the {self.model_kind} {self.model}"


@dataclass(frozen=True, kw_only=True)
class DeleteModel(Change):
    phase: ClassVar[int] = PHASE_REMOVE
    safety: ClassVar[Safety] = "lossy"
    model: str
    model_kind: str

    def describe(self) -> str:
        return f"Delete the {self.model_kind} {self.model} and all its nodes"


@dataclass(frozen=True, kw_only=True)
class RenameModel(Change):
    phase: ClassVar[int] = PHASE_RENAME
    safety: ClassVar[Safety] = "transforming"
    old: str
    new: str

    def describe(self) -> str:
        return f"Rename the model {self.old} to {self.new} (its label and `type`)"


@dataclass(frozen=True, kw_only=True)
class AlterModelKind(Change):
    safety: ClassVar[Safety] = "manual"
    model: str
    old: str
    new: str

    def describe(self) -> str:
        return f"{self.model} changed from a {self.old} to a {self.new}: the kind of a model cannot be changed"


@dataclass(frozen=True, kw_only=True)
class AlterModelLabels(Change):
    """A parent class or a trait was added or removed: the labels of its nodes change"""

    safety: ClassVar[Safety] = "transforming"
    model: str
    added: list[str] = field(default_factory=list)
    removed: list[str] = field(default_factory=list)

    def describe(self) -> str:
        parts = [f"add the labels {', '.join(self.added)}" if self.added else "",
                 f"remove the labels {', '.join(self.removed)}" if self.removed else ""]
        return f"On {self.model}: " + "; ".join(p for p in parts if p)


@dataclass(frozen=True, kw_only=True)
class AlterModelOption(Change):
    model: str
    option: str
    old: Any
    new: Any

    def describe(self) -> str:
        return f"{self.model}: {self.option} {self.old!r} -> {self.new!r}"


# --- fields ------------------------------------------------------------------------------


@dataclass(frozen=True, kw_only=True)
class AddField(Change):
    phase: ClassVar[int] = PHASE_ADD_FIELD
    model: str
    name: str
    field_kind: str
    # Nodes that exist have no value: a required field needs one to be given
    needs_value: bool
    # The field as in a snapshot
    definition: dict[str, Any] = field(default_factory=dict)
    # Answer: the value for the nodes that exist (a literal; a list for a list field)
    default: Any = None
    # The field was written by a field that narrowed it (its edges are there): nothing to write
    from_narrowing: bool = False

    @property
    def safety(self) -> Safety:  # type: ignore[override]
        return "additive" if self.needs_value and not self.from_narrowing else "safe"

    def describe(self) -> str:
        extra = " (a value is needed for the nodes that exist)" if self.needs_value else ""
        return f"Add the {self.field_kind} field {self.model}.{self.name}{extra}"


@dataclass(frozen=True, kw_only=True)
class RemoveField(Change):
    phase: ClassVar[int] = PHASE_REMOVE_FIELD
    model: str
    name: str
    field_kind: str
    # A field that narrows it writes its edges now: the field is not removed from the data
    absorbed: bool = False

    @property
    def safety(self) -> Safety:  # type: ignore[override]
        return "safe" if self.absorbed else "lossy"

    def describe(self) -> str:
        if self.absorbed:
            return f"{self.model}.{self.name} is now written by the field that narrows it"
        return f"Remove the {self.field_kind} field {self.model}.{self.name} and its data"


@dataclass(frozen=True, kw_only=True)
class RenameField(Change):
    phase: ClassVar[int] = PHASE_RENAME
    safety: ClassVar[Safety] = "transforming"
    model: str
    old: str
    new: str

    def describe(self) -> str:
        return f"Rename the field {self.model}.{self.old} to {self.new}"


@dataclass(frozen=True, kw_only=True)
class AlterLiteralType(Change):
    safety: ClassVar[Safety] = "transforming"
    model: str
    name: str
    old: dict[str, Any]
    new: dict[str, Any]
    # Answers: what to do with a value that does not convert ("fail", "null" or "default"),
    # the value for "default", and for an enum the member to give each old value
    on_failure: str | None = None
    default: Any = None
    mapping: dict[str, Any] | None = None

    def describe(self) -> str:
        return f"{self.model}.{self.name}: type {_type_name(self.old)} -> {_type_name(self.new)}"


@dataclass(frozen=True, kw_only=True)
class AlterListItemType(Change):
    safety: ClassVar[Safety] = "transforming"
    model: str
    name: str
    old: dict[str, Any]
    new: dict[str, Any]
    on_failure: str | None = None
    default: Any = None
    mapping: dict[str, Any] | None = None

    def describe(self) -> str:
        return (
            f"{self.model}.{self.name}: items {_type_name(self.old)} -> {_type_name(self.new)}"
        )


@dataclass(frozen=True, kw_only=True)
class AlterNullability(Change):
    model: str
    name: str
    nullable: bool
    # Answer, for a field that may no longer be null: the value where there is none
    default: Any = None

    @property
    def safety(self) -> Safety:  # type: ignore[override]
        return "safe" if self.nullable else "additive"

    def describe(self) -> str:
        if self.nullable:
            return f"{self.model}.{self.name} may now be null"
        return f"{self.model}.{self.name} may no longer be null (a value is needed where it is)"


@dataclass(frozen=True, kw_only=True)
class ChangeFieldKind(Change):
    """The field is another kind of field (a literal that is now a relation...)"""

    safety: ClassVar[Safety] = "manual"
    model: str
    name: str
    old: str
    new: str
    definition: dict[str, Any] = field(default_factory=dict)

    def describe(self) -> str:
        return f"{self.model}.{self.name} changed from a {self.old} to a {self.new} field: the kind of a field cannot be changed"


@dataclass(frozen=True, kw_only=True)
class LiteralToAnnotatedValue(Change):
    safety: ClassVar[Safety] = "transforming"
    model: str
    name: str
    annotated_model: str
    definition: dict[str, Any] = field(default_factory=dict)
    # Answer: the values of the extra fields of the annotated value, for the values that exist
    defaults: dict[str, Any] | None = None

    def describe(self) -> str:
        return f"{self.model}.{self.name}: the value is wrapped as {self.annotated_model} (values given a default for the extra fields)"


@dataclass(frozen=True, kw_only=True)
class AnnotatedValueToLiteral(Change):
    safety: ClassVar[Safety] = "lossy"
    model: str
    name: str
    annotated_model: str
    definition: dict[str, Any] = field(default_factory=dict)

    def describe(self) -> str:
        return f"{self.model}.{self.name}: {self.annotated_model} unwrapped to the value (the extra fields are lost)"


@dataclass(frozen=True, kw_only=True)
class AlterAnnotatedValue(Change):
    safety: ClassVar[Safety] = "transforming"
    model: str
    name: str
    old_model: str | None
    new_model: str | None
    old_value_type: dict[str, Any] | None
    new_value_type: dict[str, Any] | None

    def describe(self) -> str:
        return f"{self.model}.{self.name}: annotated value {self.old_model} -> {self.new_model}"


@dataclass(frozen=True, kw_only=True)
class AlterEmbedded(Change):
    model: str
    name: str
    old_model: str | None
    new_model: str | None
    added_types: list[str] = field(default_factory=list)
    removed_types: list[str] = field(default_factory=list)
    types: list[str] = field(default_factory=list)

    @property
    def safety(self) -> Safety:  # type: ignore[override]
        return "lossy" if self.removed_types or self.old_model != self.new_model else "safe"

    def describe(self) -> str:
        return f"{self.model}.{self.name}: embedded {self.old_model} -> {self.new_model}"


# --- relations ---------------------------------------------------------------------------


@dataclass(frozen=True, kw_only=True)
class AlterRelationTarget(Change):
    """What the relation can be to has changed. Widening (only `added`) needs nothing;
    narrowing (anything `removed`) needs the edges that point at it to be checked."""

    model: str
    name: str
    added: list[str] = field(default_factory=list)
    removed: list[str] = field(default_factory=list)
    # What it can be to now (the options of the field in a snapshot)
    options: list[dict[str, Any]] = field(default_factory=list)
    # Answer, if something was removed: "fail" or "remove" the edges that point at it
    on_narrowing: str | None = None

    @property
    def safety(self) -> Safety:  # type: ignore[override]
        return "lossy" if self.removed else "safe"

    def describe(self) -> str:
        parts = [f"now also {', '.join(self.added)}" if self.added else "",
                 f"no longer {', '.join(self.removed)}" if self.removed else ""]
        return f"{self.model}.{self.name}: " + "; ".join(p for p in parts if p)


@dataclass(frozen=True, kw_only=True)
class AlterCardinality(Change):
    model: str
    name: str
    many: bool
    # Answer, for a list that is now a single value: "fail", or "first" (by creation of
    # the edge) to keep one of several
    keep: str | None = None

    @property
    def safety(self) -> Safety:  # type: ignore[override]
        return "safe" if self.many else "lossy"

    def describe(self) -> str:
        if self.many:
            return f"{self.model}.{self.name} is now a list"
        return f"{self.model}.{self.name} is now a single value (where there are several, one is kept)"


@dataclass(frozen=True, kw_only=True)
class AlterReverseName(Change):
    safety: ClassVar[Safety] = "transforming"
    model: str
    name: str
    old: str
    new: str

    def describe(self) -> str:
        return f"{self.model}.{self.name}: the reverse edges {self.old} -> {self.new}"


@dataclass(frozen=True, kw_only=True)
class AlterEdgeModel(Change):
    model: str
    name: str
    old: list[str] = field(default_factory=list)
    new: list[str] = field(default_factory=list)
    options: list[dict[str, Any]] = field(default_factory=list)
    # Answer, for an edge model that is added: the values of its fields for the edges that exist
    defaults: dict[str, Any] | None = None

    @property
    def safety(self) -> Safety:  # type: ignore[override]
        return "additive" if self.new else "lossy"

    def describe(self) -> str:
        return f"{self.model}.{self.name}: properties on the edge {self.old} -> {self.new}"


@dataclass(frozen=True, kw_only=True)
class AlterParentFields(Change):
    """The parent fields that this field narrows have changed: the edge pair is written
    for each of them as well"""

    model: str
    name: str
    added: list[str] = field(default_factory=list)
    removed: list[str] = field(default_factory=list)
    # The edge pairs of the field now, as `storage["edges"]` of a snapshot
    edges: list[list[str | None]] = field(default_factory=list)

    @property
    def safety(self) -> Safety:  # type: ignore[override]
        return "lossy" if self.removed else "additive"

    def describe(self) -> str:
        parts = [f"now also narrows {', '.join(self.added)}" if self.added else "",
                 f"no longer narrows {', '.join(self.removed)}" if self.removed else ""]
        return f"{self.model}.{self.name}: " + "; ".join(p for p in parts if p)


@dataclass(frozen=True, kw_only=True)
class WrapRelation(Change):
    """A relation to `T` is now to `Wrapper[T]`: a node is inserted on each edge"""

    safety: ClassVar[Safety] = "transforming"
    model: str
    name: str
    wrapper: str
    wrapper_kind: str
    # What the relation can be to now (the options of the field in a snapshot)
    options: list[dict[str, Any]] = field(default_factory=list)
    # Answer: the values of the wrapper's own fields for the relations that exist
    defaults: dict[str, Any] | None = None

    def describe(self) -> str:
        return f"{self.model}.{self.name}: each relation is wrapped in a {self.wrapper} ({self.wrapper_kind})"


@dataclass(frozen=True, kw_only=True)
class UnwrapRelation(Change):
    """A relation to `Wrapper[T]` is now to `T`: the node on each edge is removed"""

    safety: ClassVar[Safety] = "lossy"
    model: str
    name: str
    wrapper: str
    wrapper_kind: str
    options: list[dict[str, Any]] = field(default_factory=list)

    def describe(self) -> str:
        return f"{self.model}.{self.name}: each {self.wrapper} ({self.wrapper_kind}) is removed, and what it held"


@dataclass(frozen=True, kw_only=True)
class ChangeWrapper(Change):
    """A relation to `Old[T]` is now to `New[T]`: each node of the old is made one of the new"""

    safety: ClassVar[Safety] = "transforming"
    model: str
    name: str
    old_wrapper: str
    new_wrapper: str
    wrapper_kind: str
    options: list[dict[str, Any]] = field(default_factory=list)
    # Answer: the values of the fields of the new wrapper that the old has not
    defaults: dict[str, Any] | None = None

    def describe(self) -> str:
        return (
            f"{self.model}.{self.name}: each {self.old_wrapper} becomes a {self.new_wrapper}"
            f" (the fields it has not are given values; those the new has not are lost)"
        )


@dataclass(frozen=True, kw_only=True)
class LiteralsToEmbedded(Change):
    """Literal fields that are now the fields of an embedded object: a node for each"""

    safety: ClassVar[Safety] = "transforming"
    model: str
    name: str
    embedded_model: str
    fields: list[str] = field(default_factory=list)
    # The field as in a snapshot, and the literal fields it replaces
    definition: dict[str, Any] = field(default_factory=dict)
    # Answer: the values of the embedded object's other fields (it may be abstract: its `type`)
    defaults: dict[str, Any] | None = None
    embedded_type: str | None = None

    def describe(self) -> str:
        return (
            f"{self.model}: {', '.join(self.fields)} become the fields of the {self.embedded_model} "
            f"{self.name}"
        )


@dataclass(frozen=True, kw_only=True)
class EmbeddedToLiterals(Change):
    """The fields of an embedded object are now literal fields of the model that holds it"""

    safety: ClassVar[Safety] = "lossy"
    model: str
    name: str
    embedded_model: str
    fields: list[str] = field(default_factory=list)
    # The literal fields as in a snapshot
    definitions: list[dict[str, Any]] = field(default_factory=list)

    def describe(self) -> str:
        return (
            f"{self.model}: the {self.embedded_model} {self.name} is removed, and its fields "
            f"{', '.join(self.fields)} are fields of {self.model} (any other fields of it are lost)"
        )


# --- the database's own structure ---------------------------------------------------------


def structure_name(entry: dict[str, Any]) -> str:
    """How an index or a constraint is called: `:Label(property, ...)`"""
    text = f":{entry['label']}({', '.join(entry['properties'])})"
    return f"{entry['name']} on {text}" if entry.get("name") else text


@dataclass(frozen=True, kw_only=True)
class AddIndex(Change):
    """An index on a label and properties (`kind` `"label+property"`), or a text index (`"text"`,
    with a `name`). Made outside a transaction, and if it is not there already."""

    phase: ClassVar[int] = PHASE_CREATE
    index: dict[str, Any]

    def describe(self) -> str:
        return f"Create the {'text ' if self.index.get('kind') == 'text' else ''}index {structure_name(self.index)}"


@dataclass(frozen=True, kw_only=True)
class RemoveIndex(Change):
    phase: ClassVar[int] = PHASE_REMOVE
    index: dict[str, Any]

    def describe(self) -> str:
        return f"Drop the {'text ' if self.index.get('kind') == 'text' else ''}index {structure_name(self.index)}"


@dataclass(frozen=True, kw_only=True)
class AddConstraint(Change):
    """A uniqueness constraint (`kind` `"unique"`): it fails if the data already breaks it"""

    phase: ClassVar[int] = PHASE_CREATE
    safety: ClassVar[Safety] = "additive"
    constraint: dict[str, Any]

    def describe(self) -> str:
        return f"Require {structure_name(self.constraint)} to be unique"


@dataclass(frozen=True, kw_only=True)
class RemoveConstraint(Change):
    phase: ClassVar[int] = PHASE_REMOVE
    constraint: dict[str, Any]

    def describe(self) -> str:
        return f"Stop requiring {structure_name(self.constraint)} to be unique"


# --- which classes a node fulfils ---------------------------------------------------------


@dataclass(frozen=True, kw_only=True)
class RecomputeFulfils(Change):
    """What a model fulfils (`Fulfils`) has changed: the nodes of exactly that model are given the
    labels of the classes they fulfil now, and lose those of the classes they no longer do.

    `fulfils` is what the model declares now (as the snapshot has it); `before` and `after` say for
    each class its labels and what a node needs to have to fulfil it (see `fulfils.fulfilment`)."""

    phase: ClassVar[int] = PHASE_FULFILS
    safety: ClassVar[Safety] = "transforming"
    model: str
    fulfils: list[dict[str, Any]] = field(default_factory=list)
    before: list[dict[str, Any]] = field(default_factory=list)
    after: list[dict[str, Any]] = field(default_factory=list)

    def describe(self) -> str:
        classes = sorted({e["class"] for e in [*self.before, *self.after]})
        return f"{self.model}: which of {', '.join(classes) or 'none'} its nodes fulfil is worked out again (their labels)"


# --- by hand -----------------------------------------------------------------------------


@dataclass(frozen=True, kw_only=True)
class RunCypher(Change):
    """A query written by hand, run in the transaction of the migration. It does not change what
    the models are (that is the other changes, or `StateOnly`), only the data.

    DDL (enums, indexes) cannot be run: Memgraph refuses it in a transaction."""

    query: str
    parameters: dict[str, Any] = field(default_factory=dict)
    # Whether it loses data (asked about before it is applied)
    lossy: bool = False
    # The models it changes, to read them afterwards (None: all of them)
    affects: list[str] | None = None
    note: str = ""
    # What undoes it (going backwards): without a query, the migration cannot be undone
    reverse_query: str | None = None
    reverse_parameters: dict[str, Any] | None = None

    @property
    def safety(self) -> Safety:  # type: ignore[override]
        return "lossy" if self.lossy else "transforming"

    def describe(self) -> str:
        return f"Run a query: {self.note or ' '.join(self.query.split())[:70]}"


@dataclass(frozen=True, kw_only=True)
class RunPython(Change):
    """A function written by hand, called as `function(tx, state)` in the transaction of the
    migration (`tx.run(...)` makes a query; `state` is the snapshot of the models before it). It may
    be `async`. Given as `"package.module:name"`, or as the function itself, which is kept as that.

    The checksum of the migration is of the name: a change to the function is not noticed."""

    function: str
    lossy: bool = False
    affects: list[str] | None = None
    note: str = ""
    # What undoes it (going backwards), given in the same way as `function`
    reverse_function: str | None = None

    def __post_init__(self) -> None:
        for name in ("function", "reverse_function"):
            function = getattr(self, name)
            if callable(function):
                object.__setattr__(self, name, f"{function.__module__}:{function.__qualname__}")

    @property
    def safety(self) -> Safety:  # type: ignore[override]
        return "lossy" if self.lossy else "transforming"

    def resolve(self, function: str | None = None) -> Any:
        """The function itself (or, given its name, that one)"""
        import importlib

        function = function or self.function
        module, _, path = function.partition(":")
        if not path:
            raise ValueError(f"'{function}' is not 'module:function'")
        found: Any = importlib.import_module(module)
        for part in path.split("."):
            found = getattr(found, part)
        return found

    def describe(self) -> str:
        return f"Run {self.function}" + (f": {self.note}" if self.note else "")


@dataclass(frozen=True, kw_only=True)
class StateOnly(Change):
    """Changes to what the models are, without anything done to the data: for a change that was
    refused as `[NEEDS CODE]`, whose data was moved by a `RunCypher` or `RunPython` before it."""

    changes: tuple[Change, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "changes",
            tuple(change_from_dict(i) if isinstance(i, dict) else i for i in self.changes),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "change": self.kind,
            "safety": self.safety,
            "changes": [change.to_dict() for change in self.changes],
        }

    def describe(self) -> str:
        return "The models (only): " + "; ".join(change.describe() for change in self.changes)


def _type_name(descriptor: dict[str, Any]) -> str:
    if descriptor.get("type") == "enum":
        return f"enum {descriptor['enum']}"
    if descriptor.get("type") == "list":
        return f"list[{_type_name(descriptor['item'])}]"
    return str(descriptor.get("type"))


def change_from_dict(data: dict[str, Any]) -> Change:
    """A change from what `Change.to_dict()` made"""
    data = dict(data)
    name = data.pop("change")
    data.pop("safety", None)
    try:
        cls = _change_types()[name]
    except KeyError:
        raise ValueError(f"There is no change called {name}") from None
    return cls(**data)


def _change_types() -> dict[str, type[Change]]:
    types: dict[str, type[Change]] = {}
    pending = list(Change.__subclasses__())
    while pending:
        cls = pending.pop()
        types[cls.__name__] = cls
        pending.extend(cls.__subclasses__())
    return types
