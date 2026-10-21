"""Going backwards: the changes that undo a migration.

`reverse_changes(changes, state)` gives, for the changes of a migration and the snapshot before
them, the changes that undo them: in the order to apply them (the last first), each the inverse of
one change, worked out from the snapshot before that change. They are ordinary changes, so
applying them to a database is what applying any changes is.

What can be undone is the models, always; the data only as far as the change allows. A change that
lost data (a field removed, a relation unwrapped) is undone as far as the structure goes, the
values are not brought back: such a reversal is `lossy`. A change that has no inverse raises
`PanglossMigrationIrreversible`. Where the inverse needs a value that only a person can give (a
default for a field that comes back), the change has it as `None`, and `questions` asks it.

Every reversal is checked: applied to the snapshot after the changes, it must give the snapshot
before.
"""

import copy
import dataclasses
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Any

from pangloss_models.exceptions import PanglossMigrationIrreversible
from pangloss_models.migrations import changes as c
from pangloss_models.migrations.snapshot import data_view
from pangloss_models.migrations.state import apply_change, field_entry, model_entry

Inverse = Callable[[Any, dict[str, Any]], list[c.Change]]


@dataclass
class Reversal:
    #: The changes that undo the migration, in the order to apply them
    changes: list[c.Change] = field(default_factory=list)
    #: Whether data that the migration changed or removed is not brought back
    lossy: bool = False


def reverse_changes(changes: Sequence[c.Change], state: dict[str, Any]) -> Reversal:
    """The changes that undo `changes`, which were applied to the snapshot `state`"""
    reversal = Reversal()
    inverses: list[list[c.Change]] = []
    current = state  # (the snapshot before each change)
    for change in changes:
        inverse = INVERSES.get(type(change))
        if inverse is None:
            raise PanglossMigrationIrreversible(f"{change.describe()}: cannot be undone")
        try:
            inverses.append(inverse(change, current))
        except PanglossMigrationIrreversible as error:
            raise PanglossMigrationIrreversible(f"{change.describe()}: {error}") from None
        except KeyError as error:
            raise PanglossMigrationIrreversible(
                f"{change.describe()}: {error.args[0] if error.args else error}"
            ) from None
        reversal.lossy = reversal.lossy or change.safety == "lossy" or loses_information(change)
        current = apply_change(current, change)
    for inverse in reversed(inverses):
        reversal.changes.extend(inverse)
    if data_view(replay_all(current, reversal.changes)) != data_view(state):
        raise PanglossMigrationIrreversible(
            "undoing it does not bring back the models as they were before it"
        )
    reversal.lossy = reversal.lossy or any(ch.safety == "lossy" for ch in reversal.changes)
    return reversal


def replay_all(snapshot: dict[str, Any], changes: Sequence[c.Change]) -> dict[str, Any]:
    for change in changes:
        snapshot = apply_change(snapshot, change)
    return snapshot


# --- the inverses --------------------------------------------------------------------------------


def swapped(change: Any, **given: Any) -> list[c.Change]:
    return [dataclasses.replace(change, **given)]


def _rename(change, before):
    return swapped(change, old=change.new, new=change.old)


def _rename_field(change, before):
    return swapped(change, old=change.new, new=change.old)


def _alter_member_value(change: c.AlterEnumMemberValue, before):
    return swapped(change, old=change.new, new=change.old)


def _create_enum(change: c.CreateEnum, before):
    return [c.RemoveEnum(enum=change.enum)]


def _remove_enum(change: c.RemoveEnum, before):
    return [c.CreateEnum(enum=change.enum, definition=copy.deepcopy(before["enums"][change.enum]))]


def _add_enum_member(change: c.AddEnumMember, before):
    # (the database enum keeps it; the data that has it fails, as the answer is not to be had)
    return [c.RemoveEnumMember(enum=change.enum, member=change.member)]


def _remove_enum_member(change: c.RemoveEnumMember, before):
    members = {m["name"]: m for m in before["enums"][change.enum]["members"]}
    return [
        c.AddEnumMember(
            enum=change.enum, member=change.member, value=members[change.member].get("value")
        )
    ]


def _create_model(change: c.CreateModel, before):
    return [c.DeleteModel(model=change.model, model_kind=change.model_kind)]


def _delete_model(change: c.DeleteModel, before):
    return [
        c.CreateModel(
            model=change.model,
            model_kind=change.model_kind,
            definition=copy.deepcopy(model_entry(before, change.model)),
        )
    ]


def _alter_model_labels(change: c.AlterModelLabels, before):
    return swapped(change, added=change.removed, removed=change.added)


def _alter_model_option(change: c.AlterModelOption, before):
    return swapped(change, old=change.new, new=change.old)


def _add_field(change: c.AddField, before):
    entry = change.definition
    if change.from_narrowing:
        return [
            c.RemoveField(
                model=change.model, name=change.name, field_kind=entry["kind"], absorbed=True
            )
        ]
    return [c.RemoveField(model=change.model, name=change.name, field_kind=change.field_kind)]


def _remove_field(change: c.RemoveField, before):
    entry = copy.deepcopy(field_entry(before, change.model, change.name))
    from pangloss_models.migrations.diff import needs_value

    return [
        c.AddField(
            model=change.model,
            name=change.name,
            field_kind=change.field_kind,
            needs_value=False if change.absorbed else needs_value(entry),
            definition=entry,
            from_narrowing=change.absorbed,
        )
    ]


def inverted_mapping(mapping: dict[str, Any] | None) -> dict[str, Any] | None:
    if mapping is None:
        return None
    if len(set(map(str, mapping.values()))) != len(mapping):
        raise PanglossMigrationIrreversible("the mapping of values is not one to one")
    return {str(new): old for old, new in mapping.items()}


def _alter_type(change, before):
    return swapped(
        change,
        old=change.new,
        new=change.old,
        on_failure=None,
        default=None,
        mapping=inverted_mapping(change.mapping),
    )


def _alter_nullability(change: c.AlterNullability, before):
    return swapped(change, nullable=not change.nullable, default=None)


def _replace_back(kind: type[c.Change], **extra: Any):
    def inverse(change, before):
        entry = copy.deepcopy(field_entry(before, change.model, change.name))
        return [
            kind(
                model=change.model,
                name=change.name,
                annotated_model=change.annotated_model,
                definition=entry,
                **extra,
            )
        ]

    return inverse


def _alter_annotated_value(change: c.AlterAnnotatedValue, before):
    return swapped(
        change,
        old_model=change.new_model,
        new_model=change.old_model,
        old_value_type=change.new_value_type,
        new_value_type=change.old_value_type,
    )


def _alter_embedded(change: c.AlterEmbedded, before):
    entry = field_entry(before, change.model, change.name)
    return swapped(
        change,
        old_model=change.new_model,
        new_model=change.old_model,
        added_types=change.removed_types,
        removed_types=change.added_types,
        types=list(entry.get("types", [])),
    )


def _alter_relation_target(change: c.AlterRelationTarget, before):
    entry = field_entry(before, change.model, change.name)
    return swapped(
        change,
        added=change.removed,
        removed=change.added,
        options=copy.deepcopy(entry.get("options", [])),
        # (narrowing again: the edges that point at what was added fail it, rather than go)
        on_narrowing="fail" if change.added else None,
    )


def _alter_cardinality(change: c.AlterCardinality, before):
    return swapped(change, many=not change.many, keep=None if change.many is False else "fail")


def _alter_reverse_name(change: c.AlterReverseName, before):
    return swapped(change, old=change.new, new=change.old)


def _alter_edge_model(change: c.AlterEdgeModel, before):
    entry = field_entry(before, change.model, change.name)
    return swapped(
        change,
        old=change.new,
        new=change.old,
        options=copy.deepcopy(entry.get("options", [])),
        defaults=None,
    )


def _alter_parent_fields(change: c.AlterParentFields, before):
    entry = field_entry(before, change.model, change.name)
    return swapped(
        change,
        added=change.removed,
        removed=change.added,
        edges=copy.deepcopy(entry.get("storage", {}).get("edges", [])),
    )


def _wrap(change: c.WrapRelation, before):
    entry = field_entry(before, change.model, change.name)
    return [
        c.UnwrapRelation(
            model=change.model,
            name=change.name,
            wrapper=change.wrapper,
            wrapper_kind=change.wrapper_kind,
            options=copy.deepcopy(entry.get("options", [])),
        )
    ]


def _unwrap(change: c.UnwrapRelation, before):
    entry = field_entry(before, change.model, change.name)
    return [
        c.WrapRelation(
            model=change.model,
            name=change.name,
            wrapper=change.wrapper,
            wrapper_kind=change.wrapper_kind,
            options=copy.deepcopy(entry.get("options", [])),
        )
    ]


def _change_wrapper(change: c.ChangeWrapper, before):
    entry = field_entry(before, change.model, change.name)
    return swapped(
        change,
        old_wrapper=change.new_wrapper,
        new_wrapper=change.old_wrapper,
        options=copy.deepcopy(entry.get("options", [])),
        defaults=None,
    )


def _literals_to_embedded(change: c.LiteralsToEmbedded, before):
    model = model_entry(before, change.model)
    definitions = [copy.deepcopy(f) for f in model["fields"] if f["name"] in change.fields]
    return [
        c.EmbeddedToLiterals(
            model=change.model,
            name=change.name,
            embedded_model=change.embedded_model,
            fields=list(change.fields),
            definitions=definitions,
        )
    ]


def _embedded_to_literals(change: c.EmbeddedToLiterals, before):
    entry = copy.deepcopy(field_entry(before, change.model, change.name))
    return [
        c.LiteralsToEmbedded(
            model=change.model,
            name=change.name,
            embedded_model=change.embedded_model,
            fields=list(change.fields),
            definition=entry,
        )
    ]


def _run_cypher(change: c.RunCypher, before):
    if change.reverse_query is None:
        raise PanglossMigrationIrreversible("it has no `reverse_query`")
    return [
        c.RunCypher(
            query=change.reverse_query,
            parameters=change.reverse_parameters or {},
            lossy=change.lossy,
            affects=change.affects,
            note=f"undo: {change.note}" if change.note else "",
            reverse_query=change.query,
            reverse_parameters=change.parameters,
        )
    ]


def _run_python(change: c.RunPython, before):
    if change.reverse_function is None:
        raise PanglossMigrationIrreversible("it has no `reverse_function`")
    return [
        c.RunPython(
            function=change.reverse_function,
            lossy=change.lossy,
            affects=change.affects,
            note=f"undo: {change.note}" if change.note else "",
            reverse_function=change.function,
        )
    ]


def _state_only(change: c.StateOnly, before):
    return [c.StateOnly(changes=tuple(reverse_changes(change.changes, before).changes))]


def _opposite(kind: type[c.Change], attribute: str):
    def inverse(change, before):
        return [kind(**{attribute: copy.deepcopy(getattr(change, attribute))})]

    return inverse


INVERSES: dict[type, Inverse] = {
    c.AddIndex: _opposite(c.RemoveIndex, "index"),
    c.RemoveIndex: _opposite(c.AddIndex, "index"),
    c.AddConstraint: _opposite(c.RemoveConstraint, "constraint"),
    c.RemoveConstraint: _opposite(c.AddConstraint, "constraint"),
    c.RenameModel: _rename,
    c.RenameField: _rename_field,
    c.RenameEnumMember: _rename,
    c.RenameEnum: _rename,
    c.AlterEnumMemberValue: _alter_member_value,
    c.CreateEnum: _create_enum,
    c.RemoveEnum: _remove_enum,
    c.AddEnumMember: _add_enum_member,
    c.RemoveEnumMember: _remove_enum_member,
    c.CreateModel: _create_model,
    c.DeleteModel: _delete_model,
    c.AlterModelLabels: _alter_model_labels,
    c.AlterModelOption: _alter_model_option,
    c.AddField: _add_field,
    c.RemoveField: _remove_field,
    c.AlterLiteralType: _alter_type,
    c.AlterListItemType: _alter_type,
    c.AlterNullability: _alter_nullability,
    c.LiteralToAnnotatedValue: _replace_back(c.AnnotatedValueToLiteral),
    c.AnnotatedValueToLiteral: _replace_back(c.LiteralToAnnotatedValue),
    c.AlterAnnotatedValue: _alter_annotated_value,
    c.AlterEmbedded: _alter_embedded,
    c.AlterRelationTarget: _alter_relation_target,
    c.AlterCardinality: _alter_cardinality,
    c.AlterReverseName: _alter_reverse_name,
    c.AlterEdgeModel: _alter_edge_model,
    c.AlterParentFields: _alter_parent_fields,
    c.WrapRelation: _wrap,
    c.UnwrapRelation: _unwrap,
    c.ChangeWrapper: _change_wrapper,
    c.LiteralsToEmbedded: _literals_to_embedded,
    c.EmbeddedToLiterals: _embedded_to_literals,
    c.RunCypher: _run_cypher,
    c.RunPython: _run_python,
    c.StateOnly: _state_only,
}

# Not undone: AlterModelKind and ChangeFieldKind (they were done by hand).


def loses_information(change: c.Change) -> bool:
    """Whether undoing a change does not bring back what it did, though it is not marked as lossy:
    values moved to another member or type, nulls that were given a value"""
    if isinstance(change, c.AlterNullability):
        return not change.nullable
    return isinstance(change, (c.RemoveEnumMember, c.AlterLiteralType, c.AlterListItemType))
