"""Upgrading a stored version to the models of now.

A version is the write form as it was when it was written. The migrations since then are known
(`schema_position` says where the database was), and each change in them has a meaning for a
stored document, the same as the Cypher operation has for the database. They are applied to the
document one change at a time, in the order of the migrations, with the snapshot of the models
kept up to date (to know which fields and labels a node had at that point).

What cannot be done is reported as a `Problem`, and the document is left as far upgraded as it can
be (see `docs/history.md`, "Restore as a draft"). A problem is `blocking` unless the upgrade lost
nothing that is not in history already (a field that has gone).

The document is never changed: an upgraded copy is made.
"""

import copy
import dataclasses
import datetime
from collections.abc import Iterable
from decimal import Decimal, InvalidOperation
from typing import Any

from pangloss_models.meta_kit import migrations as _migrations  # noqa: F401  (imports the package)
from pangloss_models.meta_kit.migrations import changes as c
from pangloss_models.meta_kit.migrations.files import Migration, MigrationGraph, graph_of
from pangloss_models.meta_kit.migrations.history import states_around
from pangloss_models.meta_kit.migrations.state import apply_change


@dataclasses.dataclass
class Problem:
    kind: str
    message: str
    path: str | None = None
    old_value: Any = None
    migration: str | None = None
    # Whether it stops the version being restored without someone's decision
    blocking: bool = True

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "kind": self.kind,
            "message": self.message,
            "blocking": self.blocking,
        }
        if self.path is not None:
            out["path"] = self.path
        if self.old_value is not None:
            out["oldValue"] = self.old_value
        if self.migration is not None:
            out["migration"] = self.migration
        return out


@dataclasses.dataclass
class Upgraded:
    data: Any
    problems: list[Problem]
    # The migrations that were applied to it, as `app.name`
    applied: list[str]

    @property
    def blocking(self) -> list[Problem]:
        return [p for p in self.problems if p.blocking]


class CannotFindPosition(Exception):
    pass


def migrations_after(
    graph: MigrationGraph, position: dict[str, str]
) -> tuple[list[Migration], dict[str, Any]]:
    """The migrations that came after `position` (`{app: last migration}`), in order, and the
    snapshot of the models as they were at it. Raises `CannotFindPosition` if the position is in
    the middle of a squashed migration whose originals are gone (or is not a migration at all)."""
    done: set[tuple[str, str]] = set()
    for app, name in position.items():
        key = (app, name)
        if key not in graph.migrations:
            # (a squashed migration stands in for the originals: only the last of them is a
            # position that it can be used for)
            squash = next(
                (
                    s
                    for s, originals in graph.stands_for.items()
                    if s[0] == app and key in originals
                ),
                None,
            )
            if squash is None or key != graph.stands_for[squash][-1]:
                raise CannotFindPosition(
                    f"{app}.{name} is not a migration that is there now (squashed away, or "
                    "removed): a version written then cannot be upgraded"
                )
            key = squash
        number = graph.migrations[key].number
        done |= {
            m.key
            for m in graph.migrations.values()
            if m.app == app and m.number <= number
        }
    _, _, state = states_around(graph, done)
    return [m for m in graph.order() if m.key not in done], state


def is_node(value: Any, state: dict[str, Any]) -> bool:
    return (
        isinstance(value, dict)
        and isinstance(value.get("type"), str)
        and value["type"] in state["models"]
    )


def is_reference(value: Any, state: dict[str, Any]) -> bool:
    """A reference to an entity (an entity is never part of the document it is named in)"""
    return is_node(value, state) and state["models"][value["type"]]["kind"] == "Entity"


class Upgrader:
    def __init__(self, data: Any, state: dict[str, Any]):
        self.data = copy.deepcopy(data)
        self.state = state
        self.problems: list[Problem] = []
        self.migration: str | None = None

    # -- looking --

    def nodes(self) -> list[tuple[str, dict[str, Any]]]:
        """Every node of the document (not the entities it refers to), with its path"""
        found: list[tuple[str, dict[str, Any]]] = []

        def visit(value: Any, path: str, root: bool) -> None:
            if isinstance(value, dict):
                if is_node(value, self.state):
                    if is_reference(value, self.state) and not root:
                        return
                    found.append((path, value))
                for key, inner in value.items():
                    visit(inner, f"{path}.{key}" if path else key, False)
            elif isinstance(value, list):
                for index, inner in enumerate(value):
                    visit(inner, f"{path}[{index}]", False)

        visit(self.data, "", True)
        return found

    def nodes_of(self, model: str) -> list[tuple[str, dict[str, Any]]]:
        """The nodes that are of the model, or of a model that has it as a parent or a trait"""
        return [
            (path, node)
            for path, node in self.nodes()
            if model in self.state["models"][node["type"]]["labels"]
        ]

    def field_of(self, node: dict[str, Any], name: str) -> dict[str, Any] | None:
        for entry in self.state["models"][node["type"]]["fields"]:
            if entry["name"] == name:
                return entry
        return None

    def problem(self, kind: str, message: str, **fields: Any) -> None:
        self.problems.append(Problem(kind, message, migration=self.migration, **fields))

    @staticmethod
    def at(path: str, name: str) -> str:
        return f"{path}.{name}" if path else name

    # -- the changes --

    def apply(self, change: c.Change) -> None:
        handler = HANDLERS.get(type(change))
        if handler is None:
            self.problem(
                "unsupported-change",
                f"{change.describe()}: this cannot be applied to a stored version (yet)",
            )
        elif handler is not nothing:
            handler(self, change)
        self.state = apply_change(self.state, change)

    def add_field(self, change: c.AddField) -> None:
        if change.from_narrowing:
            return
        definition = change.definition
        for path, node in self.nodes_of(change.model):
            if change.name in node:
                continue
            if change.default is not None:
                node[change.name] = copy.deepcopy(change.default)
            elif change.field_kind == "list" or (
                change.field_kind == "relation" and definition.get("many")
            ):
                node[change.name] = []
            elif definition.get("nullable") or not change.needs_value:
                node[change.name] = None
            else:
                self.problem(
                    "missing-required",
                    f"{change.model}.{change.name} was added after this version, and has no value",
                    path=self.at(path, change.name),
                )

    def remove_field(self, change: c.RemoveField) -> None:
        if change.absorbed:
            return
        for path, node in self.nodes_of(change.model):
            if change.name in node:
                old = node.pop(change.name)
                self.problem(
                    "removed-field",
                    f"{change.model}.{change.name} no longer exists (the value is in history)",
                    path=self.at(path, change.name),
                    old_value=old,
                    blocking=False,
                )

    def rename_field(self, change: c.RenameField) -> None:
        for _, node in self.nodes_of(change.model):
            if change.old in node:
                node[change.new] = node.pop(change.old)

    def rename_model(self, change: c.RenameModel) -> None:
        def visit(value: Any) -> None:
            if isinstance(value, dict):
                if value.get("type") == change.old:
                    value["type"] = change.new
                for inner in value.values():
                    visit(inner)
            elif isinstance(value, list):
                for inner in value:
                    visit(inner)

        visit(self.data)

    def delete_model(self, change: c.DeleteModel) -> None:
        for path, node in self.nodes():
            if node["type"] == change.model:
                self.problem(
                    "model-removed",
                    f"{change.model} no longer exists: there is nothing to restore it as",
                    path=path or None,
                )

    def convert(self, change: c.AlterLiteralType | c.AlterListItemType) -> None:
        enums = self.state["enums"]
        for path, node in self.nodes_of(change.model):
            if change.name not in node:
                continue
            here = self.at(path, change.name)
            value = node[change.name]
            if isinstance(change, c.AlterListItemType):
                if isinstance(value, list):
                    node[change.name] = [
                        self.convert_one(change, v, enums, here) for v in value
                    ]
            else:
                node[change.name] = self.convert_one(change, value, enums, here)

    def convert_one(self, change, value: Any, enums: dict, path: str) -> Any:
        if value is None:
            return None
        try:
            return convert_value(change.old, change.new, value, enums, change.mapping)
        except Unconvertible as error:
            if change.on_failure == "null":
                return None
            if change.on_failure == "default":
                return change.default
            self.problem(
                "type-changed",
                f"{change.model}.{change.name} changed type, and {value!r} cannot be converted: {error}",
                path=path,
                old_value=value,
            )
            return value

    def alter_nullability(self, change: c.AlterNullability) -> None:
        if change.nullable:
            return
        for path, node in self.nodes_of(change.model):
            if node.get(change.name) is None:
                if change.default is not None:
                    node[change.name] = change.default
                else:
                    self.problem(
                        "missing-required",
                        f"{change.model}.{change.name} may no longer be empty, and this version has no value",
                        path=self.at(path, change.name),
                    )

    def enum_fields(
        self, enum: str
    ) -> Iterable[tuple[str, dict[str, Any], dict[str, Any]]]:
        for path, node in self.nodes():
            for entry in self.state["models"][node["type"]]["fields"]:
                if entry["name"] not in node:
                    continue
                kind = (
                    entry.get("type")
                    if entry["kind"] == "literal"
                    else (entry.get("item") if entry["kind"] == "list" else None)
                )
                if kind and kind.get("type") == "enum" and kind.get("enum") == enum:
                    yield path, node, entry

    def alter_enum_member_value(self, change: c.AlterEnumMemberValue) -> None:
        def swap(value: Any) -> Any:
            return change.new if value == change.old else value

        for _, node, entry in self.enum_fields(change.enum):
            current = node[entry["name"]]
            node[entry["name"]] = (
                [swap(v) for v in current]
                if isinstance(current, list)
                else swap(current)
            )

    def remove_enum_member(self, change: c.RemoveEnumMember) -> None:
        members = {
            m["name"]: m["value"] for m in self.state["enums"][change.enum]["members"]
        }
        gone = members.get(change.member)
        replacement = members.get(change.replacement) if change.replacement else None
        for path, node, entry in self.enum_fields(change.enum):
            name = entry["name"]
            current = node[name]
            items = current if isinstance(current, list) else [current]
            if gone not in items:
                continue
            if replacement is None:
                self.problem(
                    "type-changed",
                    f"{change.enum}.{change.member} no longer exists",
                    path=self.at(path, name),
                    old_value=gone,
                )
                continue
            swapped = [replacement if v == gone else v for v in items]
            node[name] = swapped if isinstance(current, list) else swapped[0]

    def alter_relation_target(self, change: c.AlterRelationTarget) -> None:
        if not change.removed:
            return
        for path, node in self.nodes_of(change.model):
            value = node.get(change.name)
            items = value if isinstance(value, list) else [value]
            kept = []
            for item in items:
                if isinstance(item, dict) and item.get("type") in change.removed:
                    if change.on_narrowing == "remove":
                        self.problem(
                            "removed-field",
                            f"{change.model}.{change.name} can no longer be to a {item['type']}: removed",
                            path=self.at(path, change.name),
                            old_value=item,
                            blocking=False,
                        )
                        continue
                    self.problem(
                        "reference-not-allowed",
                        f"{change.model}.{change.name} can no longer be to a {item['type']}",
                        path=self.at(path, change.name),
                        old_value=item,
                    )
                kept.append(item)
            if isinstance(value, list):
                node[change.name] = kept
            elif value is not None and not kept:
                node[change.name] = None

    def alter_cardinality(self, change: c.AlterCardinality) -> None:
        for path, node in self.nodes_of(change.model):
            if change.name not in node:
                continue
            value = node[change.name]
            if change.many:
                if not isinstance(value, list):
                    node[change.name] = [] if value is None else [value]
            elif isinstance(value, list):
                if len(value) > 1 and change.keep != "first":
                    self.problem(
                        "cardinality-changed",
                        f"{change.model}.{change.name} is now a single value, and this version has {len(value)}",
                        path=self.at(path, change.name),
                        old_value=value,
                    )
                else:
                    node[change.name] = value[0] if value else None

    def hand_written(self, change: c.Change) -> None:
        self.problem(
            "hand-written-migration",
            f"{self.migration} has changes by hand ({change.describe()}): what it did to the data "
            "is not known here, so what this version means after it may have changed",
        )


class Unconvertible(Exception):
    pass


def convert_value(
    old: dict, new: dict, value: Any, enums: dict, mapping: dict | None = None
) -> Any:
    """What a stored value is as another type, as the Cypher of the migration makes it
    (`conversion.py`). Raises `Unconvertible` if it cannot be"""
    old_type, new_type = old["type"], new["type"]
    if old_type == new_type and (old_type != "enum" or old["enum"] == new["enum"]):
        return value
    try:
        if new_type == "enum":
            return to_enum(old, new, value, enums, mapping)
        if old_type == "enum":
            if new_type == "str":
                return str(value)
            raise Unconvertible(f"enum to {new_type} is not supported")
        match (old_type, new_type):
            case ("str", "int"):
                return int(str(value).strip())
            case ("str", "float"):
                return float(value)
            case ("str", "bool"):
                lowered = str(value).lower()
                if lowered not in ("true", "false"):
                    raise Unconvertible("not true or false")
                return lowered == "true"
            case ("str", "decimal"):
                Decimal(value)
                return value
            case ("str", "date"):
                return datetime.date.fromisoformat(value).isoformat()
            case ("int", "float"):
                return float(value)
            case ("int" | "float", "str"):
                return str(value)
            case ("int" | "float", "decimal"):
                return str(value)
            case ("int", "bool"):
                return value != 0
            case ("float", "int") | ("decimal", "int"):
                return int(float(value))
            case ("bool", "str"):
                return "true" if value else "false"
            case ("bool", "int"):
                return 1 if value else 0
            case ("decimal", "str") | ("date", "str"):
                return str(value)
            case ("decimal", "float"):
                return float(value)
    except (ValueError, TypeError, InvalidOperation) as error:
        raise Unconvertible(str(error)) from error
    raise Unconvertible(f"{old_type} to {new_type} is not supported")


def to_enum(old: dict, new: dict, value: Any, enums: dict, mapping: dict | None) -> Any:
    members = enums.get(new["enum"], {}).get("members", [])
    by_name = {m["name"]: m["value"] for m in members}
    pairs: dict[str, Any] = {}
    if old["type"] == "enum":
        before = enums.get(old["enum"], {}).get("members", [])
        for member in before:
            if member["name"] in by_name:
                pairs[str(member["value"])] = by_name[member["name"]]
        for old_name, new_name in (mapping or {}).items():
            source = next((m["value"] for m in before if m["name"] == old_name), None)
            if source is not None and new_name in by_name:
                pairs[str(source)] = by_name[new_name]
    else:
        pairs = {str(v): v for v in by_name.values()}
        for old_value, new_name in (mapping or {}).items():
            if new_name in by_name:
                pairs[str(old_value)] = by_name[new_name]
    text = str(value)
    if text not in pairs:
        raise Unconvertible(f"not a value of {new['enum']}")
    return pairs[text]


def nothing(upgrader: Upgrader, change: Any) -> None:
    """A change that has no meaning for a stored document (a label, an index, what is derived)"""


HANDLERS: dict[type, Any] = {
    c.AddField: Upgrader.add_field,
    c.RemoveField: Upgrader.remove_field,
    c.RenameField: Upgrader.rename_field,
    c.RenameModel: Upgrader.rename_model,
    c.DeleteModel: Upgrader.delete_model,
    c.AlterLiteralType: Upgrader.convert,
    c.AlterListItemType: Upgrader.convert,
    c.AlterNullability: Upgrader.alter_nullability,
    c.AlterEnumMemberValue: Upgrader.alter_enum_member_value,
    c.RemoveEnumMember: Upgrader.remove_enum_member,
    c.AlterRelationTarget: Upgrader.alter_relation_target,
    c.AlterCardinality: Upgrader.alter_cardinality,
    c.RunCypher: Upgrader.hand_written,
    c.RunPython: Upgrader.hand_written,
    # (an enum is stored as the values of its members, so the name of an enum or of a member, and
    # the existence of either, are not in the data)
    **{
        kind: nothing
        for kind in (
            c.CreateEnum,
            c.AddEnumMember,
            c.RenameEnumMember,
            c.RenameEnum,
            c.RemoveEnum,
            c.CreateModel,
            c.AlterModelKind,
            c.AlterModelLabels,
            c.AlterModelOption,
            c.ChangeFieldKind,
            c.AlterReverseName,
            c.AlterParentFields,
            c.AddIndex,
            c.RemoveIndex,
            c.AddConstraint,
            c.RemoveConstraint,
            c.RecomputeFulfils,
            c.StateOnly,
        )
    },
}


def apply_migrations(
    data: Any, state: dict[str, Any], migrations: Iterable[Migration]
) -> Upgraded:
    """`data` upgraded by the migrations, from models that were `state`"""
    upgrader = Upgrader(data, state)
    applied = []
    for migration in migrations:
        applied.append(f"{migration.app}.{migration.name}")
        upgrader.migration = applied[-1]
        for change in migration.changes:
            upgrader.apply(change)
    return Upgraded(upgrader.data, upgrader.problems, applied)


def upgrade(data: Any, position: dict[str, str], apps: list[str]) -> Upgraded:
    """`data`, a version written when the migrations were at `position`, as the models are now"""
    graph = graph_of(apps)
    try:
        pending, state = migrations_after(graph, position)
    except CannotFindPosition as error:
        return Upgraded(
            copy.deepcopy(data), [Problem("unknown-position", str(error))], applied=[]
        )
    return apply_migrations(data, state, pending)
