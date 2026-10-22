"""Compare two snapshots (see `snapshot.py`) and say what changed.

    result = diff(old, new)
    result.changes     # the changes, in the order to apply them
    result.questions   # things only a person can say: was this a rename?

A rename cannot be told from "removed one thing and added another" by looking at the models,
so it is never assumed. Where something is removed and something of the same kind is added,
the pair is returned as a `PossibleRename`; the answer is given back:

    diff(old, new, confirmed=[the PossibleRenames that are renames],
                   declined=[those that are not])

A confirmed rename is a `RenameModel` / `RenameField` / ... and the data is compared under the
new name; a declined one is left as a removal and an addition. `result.is_final` is true when
nothing is left to ask.
"""

import json
import copy
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any

from pangloss_models.migrations.changes import (
    AddConstraint,
    AddEnumMember,
    AddIndex,
    AlterEnumMemberValue,
    AddField,
    AlterAnnotatedValue,
    AlterCardinality,
    AlterEdgeModel,
    AlterEmbedded,
    AlterListItemType,
    AlterLiteralType,
    AlterModelKind,
    AlterModelLabels,
    AlterModelOption,
    AlterNullability,
    AlterParentFields,
    AlterRelationTarget,
    AlterReverseName,
    ChangeWrapper,
    EmbeddedToLiterals,
    LiteralsToEmbedded,
    AnnotatedValueToLiteral,
    Change,
    ChangeFieldKind,
    CreateEnum,
    CreateModel,
    DeleteModel,
    LiteralToAnnotatedValue,
    PossibleRename,
    RecomputeFulfils,
    RemoveConstraint,
    RemoveEnum,
    RemoveIndex,
    RemoveEnumMember,
    RemoveField,
    RenameEnum,
    RenameEnumMember,
    RenameField,
    RenameModel,
    UnwrapRelation,
    WrapRelation,
)
from pangloss_models.migrations.snapshot import data_view
from pangloss_models.migrations.state import (
    same_structure,
    rename_enum,
    rename_enum_member,
    rename_field,
    rename_model,
)

DIRECT_OPTION_KINDS = {"document", "entity"}
WRAPPER_OPTION_KINDS = {
    "reifiedRelation",
    "reifiedRelationDocument",
    "semanticSpace",
    "conjunction",
}
MODEL_OPTIONS = [
    "abstract",
    "createWithId",
    "acceptUrlAsId",
    "requireLabel",
    "useInSemanticSpaceLabel",
    "typeParameters",
]
# How alike two models are (the fields they share, of all they have) to ask if one is a
# renaming of the other
MODEL_RENAME_SIMILARITY = 0.5


@dataclass
class DiffResult:
    changes: list[Change] = field(default_factory=list)
    questions: list[PossibleRename] = field(default_factory=list)

    @property
    def is_final(self) -> bool:
        return not self.questions


def diff(
    old: dict[str, Any],
    new: dict[str, Any],
    confirmed: Iterable[PossibleRename] = (),
    declined: Iterable[PossibleRename] = (),
) -> DiffResult:
    """The changes from the snapshot `old` to the snapshot `new`"""
    confirmed = list(confirmed)
    declined = set(declined)
    old, new = data_view(old), data_view(new)
    result = DiffResult()

    # Renames come first: once the old snapshot has the new names, what is left is compared
    # as it is, and a renamed thing that also changed shows how
    for rename in (r for r in confirmed if r.what == "model"):
        if rename.old in old["models"] and rename.new in new["models"]:
            old = rename_model(old, rename.old, rename.new)
            result.changes.append(RenameModel(old=rename.old, new=rename.new))
    for rename in (r for r in confirmed if r.what == "enum"):
        if rename.old in old["enums"] and rename.new in new["enums"]:
            old = rename_enum(old, rename.old, rename.new)
            result.changes.append(RenameEnum(old=rename.old, new=rename.new))
    for rename in (r for r in confirmed if r.what == "field"):
        scope = rename.scope
        model = old["models"].get(scope) if scope else None
        if scope and model and rename.old in fields_of(model) and rename.new in fields_of(
            new["models"].get(rename.scope, {})
        ):
            old = rename_field(old, scope, rename.old, rename.new)
            result.changes.append(
                RenameField(model=scope, old=rename.old, new=rename.new)
            )
    for rename in (r for r in confirmed if r.what == "enum_member"):
        scope = rename.scope
        enum = old["enums"].get(scope) if scope else None
        if scope and enum and rename.old in members_of(enum) and rename.new in members_of(
            new["enums"].get(rename.scope, {})
        ):
            old = rename_enum_member(old, scope, rename.old, rename.new)
            result.changes.append(
                RenameEnumMember(enum=scope, old=rename.old, new=rename.new)
            )

    old = rename_members_with_the_same_value(old, new, result)
    diff_enums(old, new, result)
    diff_structure(old, new, result)
    diff_models(old, new, result)
    diff_fulfils(old, new, result)

    result.questions = [
        q for q in possible_renames(old, new) if q not in declined
    ]
    result.changes.sort(key=lambda change: change.phase)  # (stable: keeps the order found)
    return result


# --- which classes a model fulfils ------------------------------------------------------------


def diff_fulfils(old: dict, new: dict, result: DiffResult) -> None:
    """A model whose fulfilment changed (what it fulfils, which of its fields stand in, what the
    classes require, their labels) has its nodes' labels worked out again"""
    from pangloss_models.migrations.fulfils import fulfilment

    for name, model in new["models"].items():
        if name not in old["models"]:
            continue  # (no nodes yet)
        before, after = fulfilment(old, name), fulfilment(new, name)
        if before != after or old["models"][name].get("fulfils", []) != model.get("fulfils", []):
            result.changes.append(
                RecomputeFulfils(
                    model=name, fulfils=copy.deepcopy(model.get("fulfils", [])), before=before, after=after
                )
            )


# --- the database's structure ------------------------------------------------------------------


def diff_structure(old: dict, new: dict, result: DiffResult) -> None:
    for key, add, remove, attribute in (
        ("indexes", AddIndex, RemoveIndex, "index"),
        ("constraints", AddConstraint, RemoveConstraint, "constraint"),
    ):
        had, have = old.get(key, []), new.get(key, [])
        result.changes += [add(**{attribute: e}) for e in have if not any(same_structure(e, o) for o in had)]
        result.changes += [remove(**{attribute: e}) for e in had if not any(same_structure(e, n) for n in have)]


# --- enums --------------------------------------------------------------------------------------


def members_of(enum: dict) -> list[str]:
    return [member["name"] for member in enum.get("members", [])]


def member_value(enum: dict, name: str) -> Any:
    return next((m["value"] for m in enum["members"] if m["name"] == name), None)


def rename_members_with_the_same_value(old: dict, new: dict, result: DiffResult) -> dict:
    """A member that has gone and one that has come with the same value are the same member under
    another name: an enum is stored as the values, so that is not a question, and it needs nothing
    done to the data"""
    for name, enum in new["enums"].items():
        if name not in old["enums"]:
            continue
        had, has = members_of(old["enums"][name]), members_of(enum)
        gone = [m for m in had if m not in has]
        came = [m for m in has if m not in had]
        for old_member in gone:
            value = member_value(old["enums"][name], old_member)
            matches = [m for m in came if member_value(enum, m) == value]
            same_value_before = [g for g in gone if member_value(old["enums"][name], g) == value]
            if len(matches) == 1 and len(same_value_before) == 1:
                old = rename_enum_member(old, name, old_member, matches[0])
                result.changes.append(RenameEnumMember(enum=name, old=old_member, new=matches[0]))
                came.remove(matches[0])
    return old


def diff_enums(old: dict, new: dict, result: DiffResult) -> None:
    for name, enum in new["enums"].items():
        if name not in old["enums"]:
            result.changes.append(CreateEnum(enum=name, definition=enum))
            continue
        had = members_of(old["enums"][name])
        for member in members_of(enum):
            if member not in had:
                result.changes.append(
                    AddEnumMember(enum=name, member=member, value=member_value(enum, member))
                )
            elif member_value(old["enums"][name], member) != member_value(enum, member):
                result.changes.append(
                    AlterEnumMemberValue(
                        enum=name,
                        member=member,
                        old=member_value(old["enums"][name], member),
                        new=member_value(enum, member),
                    )
                )
        for member in had:
            if member not in members_of(enum):
                result.changes.append(RemoveEnumMember(enum=name, member=member))
    for name in old["enums"]:
        if name not in new["enums"]:
            result.changes.append(RemoveEnum(enum=name))


# --- models -------------------------------------------------------------------------------------


def fields_of(model: dict) -> dict[str, dict]:
    return {entry["name"]: entry for entry in model.get("fields", [])}


def diff_models(old: dict, new: dict, result: DiffResult) -> None:
    for name, model in new["models"].items():
        if name not in old["models"]:
            result.changes.append(
                CreateModel(model=name, model_kind=model["kind"], definition=model)
            )
            # (its fields are part of creating it: nothing to add one by one)
            continue
        diff_model(name, old["models"][name], model, result, old, new)
    for name, model in old["models"].items():
        if name not in new["models"]:
            result.changes.append(DeleteModel(model=name, model_kind=model["kind"]))


def diff_model(
    name: str, old: dict, new: dict, result: DiffResult, old_snapshot: dict, new_snapshot: dict
) -> None:
    start = len(result.changes)
    if old["kind"] != new["kind"]:
        result.changes.append(AlterModelKind(model=name, old=old["kind"], new=new["kind"]))

    # (the kind and the model's own name are labels too; they are not changes of the parents)
    own = {name, old["kind"], new["kind"], "PGIndexableNode"}
    old_labels, new_labels = set(old.get("labels", [])) - own, set(new.get("labels", [])) - own
    if old_labels != new_labels:
        result.changes.append(
            AlterModelLabels(
                model=name,
                added=sorted(new_labels - old_labels),
                removed=sorted(old_labels - new_labels),
            )
        )

    for option in MODEL_OPTIONS:
        if old.get(option) != new.get(option):
            result.changes.append(
                AlterModelOption(
                    model=name, option=option, old=old.get(option), new=new.get(option)
                )
            )

    old_fields, new_fields = fields_of(old), fields_of(new)
    # (a field that another narrows is not a field of the model of its own, but is written)
    old_narrowed, new_narrowed = narrowed_fields(old), narrowed_fields(new)
    for field_name, entry in new_fields.items():
        if field_name not in old_fields:
            result.changes.append(
                AddField(
                    model=name,
                    name=field_name,
                    field_kind=entry["kind"],
                    needs_value=needs_value(entry),
                    definition=entry,
                    from_narrowing=field_name in old_narrowed,
                )
            )
        else:
            diff_field(name, old_fields[field_name], entry, result)
    for field_name, entry in old_fields.items():
        if field_name not in new_fields:
            result.changes.append(
                RemoveField(
                    model=name,
                    name=field_name,
                    field_kind=entry["kind"],
                    absorbed=field_name in new_narrowed,
                )
            )

    merge_embedded_changes(name, old, new, old_snapshot, new_snapshot, result, start)


def literal_shape(entry: dict) -> tuple:
    """What a literal field is, apart from its name"""
    return (entry["kind"], json.dumps(entry.get("type") or entry.get("item"), sort_keys=True))


def merge_embedded_changes(
    model: str,
    old: dict,
    new: dict,
    old_snapshot: dict,
    new_snapshot: dict,
    result: DiffResult,
    start: int,
) -> None:
    """Literal fields that became the fields of an embedded object (a field added that is one,
    and the fields of it removed), or the other way, are one change: the data is moved into a
    node, or out of one, and not removed and written again"""
    block = result.changes[start:]
    removed = {ch.name: ch for ch in block if isinstance(ch, RemoveField)}
    added = {ch.name: ch for ch in block if isinstance(ch, AddField)}
    old_fields, new_fields = fields_of(old), fields_of(new)

    for add in [a for a in added.values() if a.field_kind == "embedded"]:
        embedded = new_snapshot["models"].get(add.definition.get("model"))
        if not embedded:
            continue
        own = fields_of(embedded)
        covered = sorted(
            n
            for n, f in own.items()
            if n in removed
            and removed[n].field_kind in ("literal", "list")
            and literal_shape(old_fields[n]) == literal_shape(f)
        )
        uncovered_required = [n for n, f in own.items() if n not in covered and not f.get("nullable")]
        if not covered:
            continue
        merged = LiteralsToEmbedded(
            model=model,
            name=add.name,
            embedded_model=add.definition["model"],
            fields=covered,
            definition=add.definition,
        )
        result.changes[result.changes.index(add)] = merged
        for n in covered:
            result.changes.remove(removed[n])
        _ = uncovered_required  # (they are asked for: `defaults`)

    for remove in [r for r in removed.values() if r.field_kind == "embedded"]:
        embedded_name = old_fields[remove.name].get("model")
        embedded = old_snapshot["models"].get(embedded_name)
        if not embedded or not embedded_name:
            continue
        own = fields_of(embedded)
        covered = sorted(
            n
            for n, f in own.items()
            if n in added
            and added[n].field_kind in ("literal", "list")
            and literal_shape(new_fields[n]) == literal_shape(f)
        )
        if not covered:
            continue
        merged_back = EmbeddedToLiterals(
            model=model,
            name=remove.name,
            embedded_model=embedded_name,
            fields=covered,
            definitions=[new_fields[n] for n in covered],
        )
        result.changes[result.changes.index(remove)] = merged_back
        for n in covered:
            result.changes.remove(added[n])


def narrowed_fields(model: dict) -> set[str]:
    """The fields of the parents that the fields of a model narrow"""
    names: set[str] = set()
    for entry in model.get("fields", []):
        names |= parent_fields(entry)
    return names


def needs_value(entry: dict) -> bool:
    """Whether the nodes that exist need a value for a field that is added: a required
    literal, and nothing else (a relation or an optional value can be absent)"""
    if entry["kind"] in ("literal", "list", "annotatedValue", "typeVar"):
        return not entry.get("nullable", False)
    if entry["kind"] == "embedded":
        return True
    return False


# --- fields -------------------------------------------------------------------------------------


def diff_field(model: str, old: dict, new: dict, result: DiffResult) -> None:
    name = new["name"]
    old_kind, new_kind = old["kind"], new["kind"]

    if old_kind != new_kind:
        if old_kind == "literal" and new_kind == "annotatedValue":
            result.changes.append(
                LiteralToAnnotatedValue(
                    model=model, name=name, annotated_model=new["model"], definition=new
                )
            )
        elif old_kind == "annotatedValue" and new_kind == "literal":
            result.changes.append(
                AnnotatedValueToLiteral(
                    model=model, name=name, annotated_model=old["model"], definition=new
                )
            )
        else:
            result.changes.append(
                ChangeFieldKind(
                    model=model, name=name, old=old_kind, new=new_kind, definition=new
                )
            )
        return

    if old_kind == "literal":
        if old["type"] != new["type"]:
            result.changes.append(
                AlterLiteralType(model=model, name=name, old=old["type"], new=new["type"])
            )
    elif old_kind == "list":
        if old["item"] != new["item"]:
            result.changes.append(
                AlterListItemType(model=model, name=name, old=old["item"], new=new["item"])
            )
    elif old_kind == "annotatedValue":
        if old["model"] != new["model"] or old.get("valueType") != new.get("valueType"):
            result.changes.append(
                AlterAnnotatedValue(
                    model=model,
                    name=name,
                    old_model=old["model"],
                    new_model=new["model"],
                    old_value_type=old.get("valueType"),
                    new_value_type=new.get("valueType"),
                )
            )
    elif old_kind == "embedded":
        old_types, new_types = set(old.get("types", [])), set(new.get("types", []))
        if old["model"] != new["model"] or old_types != new_types:
            result.changes.append(
                AlterEmbedded(
                    model=model,
                    name=name,
                    old_model=old["model"],
                    new_model=new["model"],
                    added_types=sorted(new_types - old_types),
                    removed_types=sorted(old_types - new_types),
                    types=list(new.get("types", [])),
                )
            )
    elif old_kind == "relation":
        diff_relation(model, old, new, result)

    if old_kind in ("literal", "list", "annotatedValue") and old.get("nullable") != new.get(
        "nullable"
    ):
        result.changes.append(
            AlterNullability(model=model, name=name, nullable=bool(new.get("nullable")))
        )


# --- relations ----------------------------------------------------------------------------------


def option_leaves(option: dict) -> set[str]:
    """The models an option finally relates to: itself, or those in its parameters"""
    if option["kind"] in DIRECT_OPTION_KINDS:
        return {option["type"]}
    leaves: set[str] = set()
    for parameter in option.get("params", {}).values():
        for inner in parameter["options"]:
            leaves |= option_leaves(inner)
    return leaves


def option_key(option: dict) -> str:
    """A description of an option that is the same for the same option"""
    if option["kind"] == "typeVar":
        return f"typeVar:{option['name']}"
    if option["kind"] in DIRECT_OPTION_KINDS:
        return f"{option['kind']}:{option['type']}"
    params = ", ".join(
        f"{name}={'|'.join(sorted(option_key(o) for o in parameter['options']))}"
        for name, parameter in sorted(option.get("params", {}).items())
    )
    return f"{option['kind']}:{option.get('type')}[{params}]"


def edge_models(entry: dict) -> list[str]:
    return sorted({o["edgeModel"] for o in entry["options"] if o.get("edgeModel")})


def diff_relation(model: str, old: dict, new: dict, result: DiffResult) -> None:
    name = new["name"]
    old_options, new_options = old["options"], new["options"]

    wrapped = detect_wrap(old_options, new_options)
    if wrapped:
        wrapper, wrapper_kind, widened = wrapped
        if wrapper_kind[0] == "change":
            change = ChangeWrapper(
                model=model,
                name=name,
                old_wrapper=wrapper_kind[2],
                new_wrapper=wrapper,
                wrapper_kind=wrapper_kind[1],
                options=new_options,
            )
        else:
            change = (WrapRelation if wrapper_kind[0] == "wrap" else UnwrapRelation)(
                model=model,
                name=name,
                wrapper=wrapper,
                wrapper_kind=wrapper_kind[1],
                options=new_options,
            )
        result.changes.append(change)
        if widened["added"] or widened["removed"]:
            result.changes.append(
                AlterRelationTarget(
                    model=model,
                    name=name,
                    added=widened["added"],
                    removed=widened["removed"],
                    options=new_options,
                )
            )
    else:
        old_keys = {option_key(o) for o in old_options}
        new_keys = {option_key(o) for o in new_options}
        if old_keys != new_keys:
            result.changes.append(
                AlterRelationTarget(
                    model=model,
                    name=name,
                    added=sorted(new_keys - old_keys),
                    removed=sorted(old_keys - new_keys),
                    options=new_options,
                )
            )

    if old["many"] != new["many"]:
        result.changes.append(AlterCardinality(model=model, name=name, many=new["many"]))

    if old["reverseName"] != new["reverseName"]:
        result.changes.append(
            AlterReverseName(model=model, name=name, old=old["reverseName"], new=new["reverseName"])
        )

    if edge_models(old) != edge_models(new):
        result.changes.append(
            AlterEdgeModel(
                model=model,
                name=name,
                old=edge_models(old),
                new=edge_models(new),
                options=new_options,
            )
        )

    old_parents = parent_fields(old)
    new_parents = parent_fields(new)
    if old_parents != new_parents:
        result.changes.append(
            AlterParentFields(
                model=model,
                name=name,
                added=sorted(new_parents - old_parents),
                removed=sorted(old_parents - new_parents),
                edges=new.get("storage", {}).get("edges", []),
            )
        )


def detect_change_of_wrapper(old_options: list[dict], new_options: list[dict]):
    """A relation to `Old[T]` that is now to `New[T]`: one wrapper each, of the same kind, and
    they relate to the same models"""
    old_wrappers = {(o["type"], o["kind"]) for o in old_options}
    new_wrappers = {(o["type"], o["kind"]) for o in new_options}
    if len(old_wrappers) != 1 or len(new_wrappers) != 1 or old_wrappers == new_wrappers:
        return None
    (old_wrapper, old_kind), = old_wrappers
    (new_wrapper, new_kind), = new_wrappers
    if old_kind != new_kind:
        return None
    old_targets = set().union(*(option_leaves(o) for o in old_options))
    new_targets = set().union(*(option_leaves(o) for o in new_options))
    if not old_targets & new_targets:
        return None
    return (
        new_wrapper,
        ("change", new_kind, old_wrapper),
        {
            "added": sorted(new_targets - old_targets),
            "removed": sorted(old_targets - new_targets),
        },
    )


def parent_fields(entry: dict) -> set[str]:
    """The parent fields that a relation narrows: the edge pairs after its own"""
    return {edge[0] for edge in entry.get("storage", {}).get("edges", [])[1:]}


def detect_wrap(old_options: list[dict], new_options: list[dict]):
    """A relation that was to `T` and is now to `Wrapper[T]` (or the other way): every old
    option is direct, every new one is a wrapper, and they relate to the same models.

    Returns `(wrapper name, ("wrap" | "unwrap", wrapper kind), what else changed)` or None.
    """
    if not old_options or not new_options:
        return None

    def all_direct(options):
        return all(o["kind"] in DIRECT_OPTION_KINDS for o in options)

    def all_wrapped(options):
        return all(o["kind"] in WRAPPER_OPTION_KINDS for o in options)

    if all_wrapped(old_options) and all_wrapped(new_options):
        return detect_change_of_wrapper(old_options, new_options)
    if all_direct(old_options) and all_wrapped(new_options):
        direction, direct, wrapped = "wrap", old_options, new_options
    elif all_wrapped(old_options) and all_direct(new_options):
        direction, direct, wrapped = "unwrap", new_options, old_options
    else:
        return None

    wrappers = {(o["type"], o["kind"]) for o in wrapped}
    if len(wrappers) != 1:
        return None
    direct_targets = {o["type"] for o in direct}
    wrapped_targets = set().union(*(option_leaves(o) for o in wrapped))
    # (they must have something in common, or it is another relation altogether)
    if not direct_targets & wrapped_targets:
        return None

    (wrapper, wrapper_kind), = wrappers
    old_targets, new_targets = (
        (direct_targets, wrapped_targets)
        if direction == "wrap"
        else (wrapped_targets, direct_targets)
    )
    return (
        wrapper,
        (direction, wrapper_kind),
        {
            "added": sorted(new_targets - old_targets),
            "removed": sorted(old_targets - new_targets),
        },
    )


# --- renames: what to ask ---------------------------------------------------------------------------


def field_shape(entry: dict) -> Any:
    """What a field is, apart from its name: what a renamed field would still be"""
    shape = {key: value for key, value in entry.items() if key not in ("name", "key")}
    storage = shape.get("storage")
    if storage and storage.get("edges"):
        # (the edge names are made from the name)
        shape["storage"] = {"kind": storage["kind"], "parents": len(storage["edges"]) - 1}
    if "reverseName" in shape:
        shape["reverseName"] = None
    return shape


def possible_renames(old: dict, new: dict) -> list[PossibleRename]:
    """Everything that was removed and has something of the same kind added"""
    questions: list[PossibleRename] = []

    removed_models = [n for n in old["models"] if n not in new["models"]]
    added_models = [n for n in new["models"] if n not in old["models"]]
    for old_name in removed_models:
        for new_name in added_models:
            if similar_models(old["models"][old_name], new["models"][new_name]):
                questions.append(PossibleRename(what="model", old=old_name, new=new_name))

    removed_enums = [n for n in old["enums"] if n not in new["enums"]]
    added_enums = [n for n in new["enums"] if n not in old["enums"]]
    for old_name in removed_enums:
        for new_name in added_enums:
            if set(members_of(old["enums"][old_name])) & set(members_of(new["enums"][new_name])):
                questions.append(PossibleRename(what="enum", old=old_name, new=new_name))

    for name, model in new["models"].items():
        if name not in old["models"]:
            continue
        old_fields, new_fields = fields_of(old["models"][name]), fields_of(model)
        for old_field, old_entry in old_fields.items():
            if old_field in new_fields:
                continue
            for new_field, new_entry in new_fields.items():
                if new_field in old_fields:
                    continue
                if field_shape(old_entry) == field_shape(new_entry):
                    questions.append(
                        PossibleRename(what="field", scope=name, old=old_field, new=new_field)
                    )

    for name, enum in new["enums"].items():
        if name not in old["enums"]:
            continue
        had, has = members_of(old["enums"][name]), members_of(enum)
        for old_member in (m for m in had if m not in has):
            for new_member in (m for m in has if m not in had):
                questions.append(
                    PossibleRename(what="enum_member", scope=name, old=old_member, new=new_member)
                )
    return questions


def similar_models(old: dict, new: dict) -> bool:
    if old["kind"] != new["kind"]:
        return False
    old_fields, new_fields = fields_of(old), fields_of(new)
    if not old_fields and not new_fields:
        return True
    shared = set(old_fields) & set(new_fields)
    total = set(old_fields) | set(new_fields)
    return len(shared) / len(total) >= MODEL_RENAME_SIMILARITY
