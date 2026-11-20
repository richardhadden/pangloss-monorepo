"""A stored search pattern brought through one change of a migration (implementation_docs/matches-criteria.md,
"Migrations that make a pattern invalid").

A pattern is what `pangloss_models.search` reads (`{"type": "Person", "where": {...}}`), kept as data: the criteria of
a description (`pangloss-criteria`), in the database and in the versions history keeps. It names classes, fields,
enum values, wrappers and edge models, so a change of the models can make it wrong. `upgrade(pattern, change,
before)` gives it as the change leaves it:

| Change | What happens to a pattern |
|---|---|
| `RenameModel` | Every class it names: its `type`, those of the patterns in it, `$incoming`, `$somewhere`, `$spaces`, a wrapper in `through`, an edge model in `edge` |
| `RenameField` | The key of the field in a `where` of that class or a class below it; `field` of `$incoming`; and so in the `where` of a `through` step (the wrapper's own values) and of an `edge` (the edge model's) |
| `AlterEnumMemberValue` | The values compared with a field of the enum |
| `AlterLiteralType`, `AlterListItemType` | The values compared with the field, converted as the data is (`conversion`). One that cannot be is **broken** |
| `ChangeWrapper` | The wrapper's name in `through` of the field |
| `RemoveField`, `DeleteModel`, `RemoveEnumMember`; `AlterRelationTarget` that leaves out a class a pattern of the field is of, or a wrapper it passes through | **Broken** |
| Anything else (`RenameEnumMember`, `AddField`, `RunPython`, `RunCypher`, `StateOnly`, an index...) | Nothing |

**Broken** is said (`Result.broken`: the first thing that broke it, with its path as the check of a search writes
one), and **the condition is left in place**, never dropped: without "employer is Maximilian" a description of his
secretaries would find every secretary. The rest of the pattern is upgraded as far as it can be.

What a level of the pattern is of is worked out from the **snapshot before the change** (the classes of the code
are those of the end of the migrations): a relation's pattern is of its `type`, or of the one class the relation
can hold. A key of a search extension (`$derived`, `$derived_document`) is the extension's own, and is left as it
is; so is anything the walk does not understand. It never raises: the check of the pattern against the models
afterwards is the guard.
"""

import copy
from dataclasses import dataclass
from typing import Any

from pangloss_models.migrations import changes as c
from pangloss_models.migrations.conversion import Unconvertible, convert_value
from pangloss_models.migrations.state import apply_change

# The keys of a `where` that are not fields, and that the walk knows (`pangloss_models.search.SearchKey`)
ALL, ANY_OF, NOT = "$all", "$any_of", "$not"
ANY, MENTIONS, SOMEWHERE, INCOMING, SPACES = (
    "$any",
    "$mentions",
    "$somewhere",
    "$incoming",
    "$spaces",
)

# The operators of a condition whose operands are values of the field (and, for a list, its items)
VALUE_OPERATORS = (
    "eq",
    "ne",
    "gt",
    "gte",
    "lt",
    "lte",
    "between",
    "in",
    "contains",
    "contains_any",
    "contains_all",
    "starts_with",
)
# (of those, the ones whose operand is a list of values)
LIST_OPERANDS = ("between", "in", "contains_any", "contains_all")

DIRECT_KINDS = {"document", "entity"}
WRAPPER_KINDS = {
    "reifiedRelation",
    "reifiedRelationDocument",
    "semanticSpace",
    "conjunction",
}

# The changes that can alter a pattern (an `AlterRelationTarget` only if it takes something away)
ALTERING = (
    c.RenameModel,
    c.RenameField,
    c.AlterEnumMemberValue,
    c.AlterLiteralType,
    c.AlterListItemType,
    c.ChangeWrapper,
    c.RemoveField,
    c.DeleteModel,
    c.RemoveEnumMember,
)


@dataclass(frozen=True)
class Broken:
    """Where a change made a pattern wrong, and how"""

    path: str
    """Where in the pattern, as the check of a search names it (`holder.office`, `$incoming.employer.is`, `type`)"""
    reason: str

    def __str__(self) -> str:
        return f"{self.path}: {self.reason}"


@dataclass(frozen=True)
class Result:
    pattern: Any
    """The pattern after the change: a new one (what was given is never changed)"""
    changed: bool
    broken: Broken | None = None
    """The first thing the change made wrong; the pattern is then as far upgraded as it can be, with that left in
    place"""


def may_alter(change: Any) -> bool:
    """Whether a change of this kind can alter a stored pattern at all"""
    if isinstance(change, c.AlterRelationTarget):
        return bool(change.removed)
    return isinstance(change, ALTERING)


def upgrade(
    pattern: Any,
    change: Any,
    before: dict[str, Any],
    after: dict[str, Any] | None = None,
) -> Result:
    """The pattern as the change leaves it. `before`: the snapshot of the models before the change; `after`, after it
    (worked out from `before` if not given)"""
    pattern = copy.deepcopy(pattern)
    if not may_alter(change) or not isinstance(pattern, dict):
        return Result(pattern, False)
    if after is None:
        try:
            after = apply_change(before, change)
        except KeyError, ValueError, NotImplementedError:
            # (a change the snapshot does not fit: nothing is known of what it does)
            return Result(pattern, False)
    walk = _Walk(change, _Models(before), _Models(after))
    made = walk.pattern(pattern)
    return Result(made, made != pattern, walk.broken)


# --- the models, as a snapshot has them --------------------------------------------------------------------------------


class _Models:
    def __init__(self, snapshot: dict[str, Any]):
        self.models: dict[str, Any] = snapshot.get("models") or {}
        self.enums: dict[str, Any] = snapshot.get("enums") or {}

    def labels(self, name: str) -> list[str]:
        return list((self.models.get(name) or {}).get("labels") or [name])

    def below(self, name: str | None, parent: str | None) -> bool:
        """Whether `name` is the class `parent` or one below it (a subclass; a class with the trait)"""
        if name is None or parent is None:
            return False
        return name == parent or parent in self.labels(name)

    def at_or_below(self, name: str) -> list[str]:
        return [other for other in self.models if self.below(other, name)]

    def field(self, model: str | None, name: str) -> dict[str, Any] | None:
        if model is None:
            return None
        for entry in (self.models.get(model) or {}).get("fields") or []:
            if isinstance(entry, dict) and entry.get("name") == name:
                return entry
        return None

    def relations_below(self, model: str) -> dict[str, list[dict[str, Any]]]:
        """The relations of a class and of the classes below it, by name: their entries"""
        found: dict[str, list[dict[str, Any]]] = {}
        for other in self.at_or_below(model):
            for entry in self.models[other].get("fields") or []:
                if isinstance(entry, dict) and entry.get("kind") == "relation":
                    found.setdefault(entry["name"], []).append(entry)
        return found

    def leaves(self, options: Any) -> list[str]:
        """The classes at the end of a relation, through the wrappers on the way"""
        found: list[str] = []
        for option in options or []:
            kind = option.get("kind") if isinstance(option, dict) else None
            if kind in DIRECT_KINDS and isinstance(option.get("type"), str):
                found.append(option["type"])
            elif kind in WRAPPER_KINDS:
                for parameter in (option.get("params") or {}).values():
                    found += self.leaves((parameter or {}).get("options"))
        return list(dict.fromkeys(found))

    def wrappers(self, options: Any) -> set[str]:
        """The wrapper classes a relation can pass through"""
        found: set[str] = set()
        for option in options or []:
            if isinstance(option, dict) and option.get("kind") in WRAPPER_KINDS:
                if isinstance(option.get("type"), str):
                    found.add(option["type"])
                for parameter in (option.get("params") or {}).values():
                    found |= self.wrappers((parameter or {}).get("options"))
        return found

    def held(self, entry: dict[str, Any]) -> list[str]:
        """What a relation or an embedded field can be to"""
        if entry.get("kind") == "embedded":
            types = [t for t in entry.get("types") or [] if isinstance(t, str)]
            model = entry.get("model")
            return list(dict.fromkeys([model, *types])) if model else types
        return self.leaves(entry.get("options"))

    def root_of(self, entry: dict[str, Any] | None) -> str | None:
        """The class a pattern of the field is of when it does not say (the one class the field holds, of those that
        none of the others is a parent of), or None"""
        if entry is None:
            return None
        if entry.get("kind") == "embedded" and isinstance(entry.get("model"), str):
            return entry["model"]
        held = self.held(entry)
        roots = [
            name
            for name in held
            if not any(other != name and self.below(name, other) for other in held)
        ]
        return roots[0] if len(roots) == 1 else None

    def related(self, name: str, other: str) -> bool:
        return self.below(name, other) or self.below(other, name)


# --- the walk -------------------------------------------------------------------------------------------------------


class _Walk:
    def __init__(self, change: Any, before: _Models, after: _Models):
        self.change = change
        self.before = before
        self.after = after
        self.broken: Broken | None = None

    def fail(self, path: str, reason: str) -> None:
        if self.broken is None:
            self.broken = Broken(path or "type", reason)

    def of_change(self, model: str | None) -> bool:
        """Whether a level of the class is one the change is of: its class, or a class below it"""
        return self.before.below(model, getattr(self.change, "model", None))

    # -- what is named --

    def class_name(self, name: Any, path: str) -> Any:
        """A class the pattern names, renamed; or said to be gone"""
        change = self.change
        if not isinstance(name, str):
            return name
        if isinstance(change, c.RenameModel) and name == change.old:
            return change.new
        if isinstance(change, c.DeleteModel) and name == change.model:
            self.fail(path, f"the model {name} was deleted")
        return name

    def field_name(self, model: str | None, key: str, path: str) -> str:
        """A field of a level of the class `model`, renamed; or said to be gone"""
        change = self.change
        if isinstance(change, c.RenameField) and key == change.old:
            if self.before.field(model, key) is not None and self.of_change(model):
                return change.new
        if (
            isinstance(change, c.RemoveField)
            and key == change.name
            and self.of_change(model)
            and self.before.field(model, key) is not None
            and self.after.field(model, key) is None
        ):
            self.fail(path, f"the field '{key}' of {change.model} was removed")
        return key

    # -- a pattern, and a where --

    def pattern(self, pattern: dict[str, Any], path: str = "") -> dict[str, Any]:
        """`{"type", "where"}` (the root, or one of `$somewhere`)"""
        made = dict(pattern)
        model = pattern.get("type")
        if "type" in pattern:
            made["type"] = self.class_name(model, path or "type")
        if isinstance(pattern.get("where"), dict):
            made["where"] = self.where(
                model if isinstance(model, str) else None,
                pattern["where"],
                f"{path}." if path else "",
            )
        return made

    def where(
        self, model: str | None, where: dict[str, Any], path: str
    ) -> dict[str, Any]:
        made: dict[str, Any] = {}
        for key, value in where.items():
            if not isinstance(key, str):
                made[key] = value
            elif key in (ALL, ANY_OF) and isinstance(value, list):
                made[key] = [
                    self.where(model, each, path) if isinstance(each, dict) else each
                    for each in value
                ]
            elif key == NOT and isinstance(value, dict):
                made[key] = self.where(model, value, path)
            elif key in (ANY, MENTIONS) and isinstance(value, dict):
                made[key] = self.relation(model, None, None, value, f"{path}{key}")
            elif key == SOMEWHERE and isinstance(value, list):
                made[key] = [
                    self.pattern(each, f"{path}{key}")
                    if isinstance(each, dict)
                    else each
                    for each in value
                ]
            elif key == INCOMING and isinstance(value, (list, dict)):
                items = [
                    self.incoming(model, each, f"{path}{key}")
                    for each in (value if isinstance(value, list) else [value])
                ]
                made[key] = items if isinstance(value, list) else items[0]
            elif key == SPACES and isinstance(value, list):
                made[key] = [self.class_name(each, f"{path}{key}") for each in value]
            elif key.startswith("$"):
                # (an extension's own, a rule's, or one not known: left as it is)
                made[key] = value
            else:
                field = f"{path}{key}"
                renamed = self.field_name(model, key, field)
                if renamed != key and (renamed in where or renamed in made):
                    renamed = key  # (both there: not for the walk to choose)
                made[renamed] = self.condition(model, key, value, field)
        return made

    def condition(self, model: str | None, key: str, value: Any, path: str) -> Any:
        """What a field of the class is to be"""
        if not isinstance(value, dict):
            return value
        entry = self.before.field(model, key)
        kind = entry.get("kind") if entry else None
        if kind in ("literal", "list"):
            assert entry is not None
            return self.literal(model, key, entry, value, path)
        if kind in ("relation", "embedded") or (
            entry is None and {"type", "where", "through", "edge"} & set(value)
        ):
            return self.relation(model, key, entry, value, path)
        return value

    # -- values --

    def literal(
        self,
        model: str | None,
        key: str,
        entry: dict[str, Any],
        condition: dict[str, Any],
        path: str,
    ) -> dict[str, Any]:
        made = dict(condition)
        for operator, operand in condition.items():
            if operator in VALUE_OPERATORS:
                made[operator] = self.operand(
                    model, key, entry, operator, operand, f"{path}.{operator}"
                )
        return made

    def operand(
        self,
        model: str | None,
        key: str,
        entry: dict[str, Any],
        operator: str,
        operand: Any,
        path: str,
    ) -> Any:
        change = self.change
        descriptor = (
            entry.get("type") if entry["kind"] == "literal" else entry.get("item")
        )
        descriptor = descriptor if isinstance(descriptor, dict) else {}

        def each(convert) -> Any:
            if operator in LIST_OPERANDS and isinstance(operand, list):
                return [convert(item) for item in operand]
            return convert(operand)

        of_enum = descriptor.get("type") == "enum" and descriptor.get(
            "enum"
        ) == getattr(change, "enum", None)
        if isinstance(change, c.AlterEnumMemberValue) and of_enum:
            return each(lambda value: change.new if value == change.old else value)
        if isinstance(change, c.RemoveEnumMember) and of_enum:
            members = (self.before.enums.get(change.enum) or {}).get("members") or []
            gone = next(
                (m.get("value") for m in members if m.get("name") == change.member),
                None,
            )
            values = operand if isinstance(operand, list) else [operand]
            if gone is not None and gone in values:
                self.fail(path, f"{gone!r} ({change.enum}.{change.member}) was removed")
            return operand
        converting = (
            isinstance(change, c.AlterLiteralType)
            and entry["kind"] == "literal"
            # (of text alone: the check refuses them of any other type)
            and operator not in ("contains", "starts_with")
        ) or (isinstance(change, c.AlterListItemType) and entry["kind"] == "list")
        if (
            converting
            and key == change.name
            # (the field of this class that the change is of: a class below it has an entry of its own, and a
            # change of its own, and a value converted twice could be wrong)
            and model == change.model
            and descriptor == change.old
        ):

            def convert(value: Any) -> Any:
                if value is None:
                    return None
                try:
                    return convert_value(
                        change.old, change.new, value, self.before.enums, change.mapping
                    )
                except Unconvertible as error:
                    self.fail(
                        path,
                        f"{value!r} cannot be a value of {change.model}.{change.name} now: {error}",
                    )
                    return value

            return each(convert)
        return operand

    # -- relations --

    def relation(
        self,
        model: str | None,
        key: str | None,
        entry: dict[str, Any] | None,
        condition: dict[str, Any],
        path: str,
    ) -> dict[str, Any]:
        """A condition of a relation (or an embedded object): a pattern for what it is to (`type`, `where`), the
        wrappers on the way (`through`), the edge (`edge`). `key` and `entry`: the field (none for `$any`)"""
        made = dict(condition)
        target = condition.get("type")
        if isinstance(target, str):
            made["type"] = self.class_name(target, path)
            self.target_left_out(model, key, target, path)
        # (the way first, then what is at the end of it)
        if isinstance(condition.get("through"), list):
            made["through"] = [
                self.step(model, key, step, path) for step in condition["through"]
            ]
        if isinstance(condition.get("edge"), dict):
            made["edge"] = self.edge(condition["edge"], f"{path}.edge")
        if isinstance(condition.get("where"), dict):
            inner = target if isinstance(target, str) else self.before.root_of(entry)
            made["where"] = self.where(inner, condition["where"], f"{path}.")
        return made

    def step(self, model: str | None, key: str | None, step: Any, path: str) -> Any:
        """A wrapper of `through`: its name, or `{"type", "where", "edge"}`"""
        if isinstance(step, str):
            return self.wrapper(model, key, step, f"{path}.through")
        if not isinstance(step, dict):
            return step
        made = dict(step)
        name = step.get("type")
        if isinstance(name, str):
            made["type"] = self.wrapper(model, key, name, f"{path}.through")
        here = f"{path}.through.{name}"
        if isinstance(step.get("where"), dict):
            made["where"] = self.where(
                name if isinstance(name, str) else None, step["where"], f"{here}."
            )
        if isinstance(step.get("edge"), dict):
            made["edge"] = self.edge(step["edge"], f"{here}.edge")
        return made

    def wrapper(self, model: str | None, key: str | None, name: str, path: str) -> str:
        """The name of a wrapper a relation of the class passes through"""
        change = self.change
        name = self.class_name(name, path)
        if (
            key is None
            or key != getattr(change, "name", None)
            or not self.of_change(model)
        ):
            return name
        if isinstance(change, c.ChangeWrapper) and name == change.old_wrapper:
            return change.new_wrapper
        if isinstance(change, c.AlterRelationTarget):
            was, now = self.before.field(model, key), self.after.field(model, key)
            if (
                was is not None
                and now is not None
                and name in self.before.wrappers(was.get("options"))
                and name not in self.after.wrappers(now.get("options"))
            ):
                self.fail(path, f"{model}.{key} no longer passes through {name}")
        return name

    def target_left_out(
        self, model: str | None, key: str | None, target: str, path: str
    ) -> None:
        """(`AlterRelationTarget`) a pattern of the field is of a class it no longer holds"""
        change = self.change
        if (
            not isinstance(change, c.AlterRelationTarget)
            or key is None
            or key != change.name
            or not self.of_change(model)
        ):
            return
        was, now = self.before.field(model, key), self.after.field(model, key)
        if was is None or now is None:
            return
        held = self.after.held(now)
        if any(self.after.related(target, other) for other in held):
            return
        if any(self.before.related(target, other) for other in self.before.held(was)):
            self.fail(path, f"{model}.{key} no longer holds a {target}")

    def edge(self, edge: dict[str, Any], path: str) -> dict[str, Any]:
        """`{"type": <an edge model>, "where": <its values>}`"""
        made = dict(edge)
        name = edge.get("type")
        if isinstance(name, str):
            made["type"] = self.class_name(name, path)
        if isinstance(edge.get("where"), dict):
            made["where"] = self.where(
                name if isinstance(name, str) else None, edge["where"], f"{path}."
            )
        return made

    # -- what refers to an entity --

    def incoming(self, model: str | None, item: Any, path: str) -> Any:
        """One of `$incoming`: `{"type", "field", "through", "where"}`, a node of `type` that refers to the entity
        (of the class `model`) by its relation `field`"""
        if not isinstance(item, dict):
            return item
        made = dict(item)
        source = item.get("type")
        source = source if isinstance(source, str) else None
        if "type" in item:
            made["type"] = self.class_name(item.get("type"), path)
        field = item.get("field")
        if source is not None and isinstance(field, str):
            made["field"] = self.incoming_field(model, source, field, path)
        if isinstance(item.get("through"), list):
            made["through"] = [
                self.incoming_wrapper(source, field, name, f"{path}.through")
                for name in item["through"]
            ]
        if isinstance(item.get("where"), dict):
            made["where"] = self.where(source, item["where"], f"{path}.")
        return made

    def by_relation(self, source: str) -> bool:
        """Whether the change is of a class that a node of `source` can be (it, one below it, or one above it,
        whose relations a node of `source` has)"""
        changed = getattr(self.change, "model", None)
        return isinstance(changed, str) and self.before.related(changed, source)

    def incoming_field(
        self, model: str | None, source: str, field: str, path: str
    ) -> str:
        """The relation (of `source`, or of a class below it) that refers to the entity"""
        change = self.change
        if not self.by_relation(source):
            return field
        before = self.before.relations_below(source)
        after = self.after.relations_below(source)
        if isinstance(change, c.RenameField) and field == change.old:
            # (once no class of those it can be has the field by its old name)
            if field in before and field not in after and change.new in after:
                return change.new
        if isinstance(change, c.RemoveField) and field == change.name:
            if field in before and field not in after:
                self.fail(
                    path,
                    f"{source} has no relation '{field}' now: the field '{field}' of {change.model} was removed",
                )
        if (
            isinstance(change, c.AlterRelationTarget)
            and field == change.name
            and model is not None
        ):
            entity: str = model

            def reaches(models: _Models, entries: list[dict[str, Any]]) -> bool:
                return any(
                    models.related(entity, held)
                    for entry in entries
                    for held in models.held(entry)
                )

            if reaches(self.before, before.get(field, [])) and not reaches(
                self.after, after.get(field, [])
            ):
                self.fail(path, f"{source}.{field} no longer refers to a {model}")
        return field

    def incoming_wrapper(
        self, source: str | None, field: Any, name: Any, path: str
    ) -> Any:
        change = self.change
        name = self.class_name(name, path)
        if (
            isinstance(change, c.ChangeWrapper)
            and source is not None
            and name == change.old_wrapper
            and field in (None, change.name)
            and self.by_relation(source)
        ):
            return change.new_wrapper
        return name


__all__ = ["Broken", "Result", "may_alter", "upgrade"]
