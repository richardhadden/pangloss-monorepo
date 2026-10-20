"""What a person has to say for a change to be applied to data that exists.

`answers_needed(change, state)` lists the questions for a change; `with_answer` puts an answer
in the change. The answers are in the migration file, so they are written as data (a date as its
ISO text, a decimal as its text).
"""

import dataclasses
import datetime
from dataclasses import dataclass
from typing import Any

from pangloss_models.exceptions import PanglossMigrationError
from pangloss_models.migrations import changes as c
from pangloss_models.migrations.state import apply_change


@dataclass(frozen=True)
class Question:
    #: The field of the change that the answer is for; `defaults.x` is the key `x` of `defaults`
    field: str
    prompt: str
    #: The type of the answer, as a descriptor of the snapshot (None: it cannot be asked, and is
    #: written in the migration file)
    descriptor: dict[str, Any] | None
    #: May be left out (the change then fails if it turns out to be needed)
    optional: bool = False


def field_descriptor(entry: dict[str, Any]) -> dict[str, Any] | None:
    if entry["kind"] == "literal":
        return entry["type"]
    if entry["kind"] == "list":
        return {"type": "list", "item": entry["item"]}
    return None


def required_literals(model: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        f
        for f in model.get("fields", [])
        if f["kind"] in ("literal", "list") and not f.get("nullable") and f["name"] != "value"
    ]


def answers_needed(change: c.Change, state: dict[str, Any]) -> list[Question]:
    """The questions for a change, given the snapshot before it"""
    if isinstance(change, c.AddField) and change.needs_value and not change.from_narrowing:
        if change.default is None and change.definition["kind"] != "list":
            return [
                Question(
                    "default",
                    f"A value for {change.model}.{change.name} on the nodes that exist",
                    field_descriptor(change.definition),
                )
            ]
    if isinstance(change, c.AlterNullability) and not change.nullable and change.default is None:
        model = state["models"].get(change.model, {})
        entry = next((f for f in model.get("fields", []) if f["name"] == change.name), None)
        return [
            Question(
                "default",
                f"A value for {change.model}.{change.name} where there is none",
                field_descriptor(entry) if entry else None,
            )
        ]
    if isinstance(change, c.WrapRelation) and change.wrapper_kind == "reifiedRelation":
        wrapper = state["models"].get(change.wrapper, {})
        have = change.defaults or {}
        return [
            Question(
                f"defaults.{f['name']}",
                f"{change.wrapper}.{f['name']} for the relations of {change.model}.{change.name} that exist",
                field_descriptor(f),
            )
            for f in required_literals(wrapper)
            if f["name"] not in have
        ]
    if isinstance(change, c.ChangeWrapper):
        old = {f["name"] for f in state["models"].get(change.old_wrapper, {}).get("fields", [])}
        new = state["models"].get(change.new_wrapper, {})
        have = change.defaults or {}
        return [
            Question(
                f"defaults.{f['name']}",
                f"{change.new_wrapper}.{f['name']} for the relations of {change.model}.{change.name} that exist",
                field_descriptor(f),
            )
            for f in required_literals(new)
            if f["name"] not in old and f["name"] not in have
        ]
    if isinstance(change, c.LiteralsToEmbedded):
        embedded = state["models"].get(change.embedded_type or change.embedded_model, {})
        have = change.defaults or {}
        return [
            Question(
                f"defaults.{f['name']}",
                f"{change.embedded_model}.{f['name']} for the {change.model} that exist",
                field_descriptor(f),
            )
            for f in required_literals(embedded)
            if f["name"] not in change.fields and f["name"] not in have
        ]
    if isinstance(change, c.LiteralToAnnotatedValue):
        annotated = state["models"].get(change.annotated_model) or {}
        have = change.defaults or {}
        return [
            Question(
                f"defaults.{f['name']}",
                f"{change.annotated_model}.{f['name']} for the values of {change.model}.{change.name} that exist",
                field_descriptor(f),
            )
            for f in required_literals(annotated)
            if f["name"] not in have
        ]
    if isinstance(change, c.AlterEdgeModel) and change.new:
        have = change.defaults or {}
        asked = []
        for name in change.new:
            model = state["models"].get(name, {})
            asked += [
                Question(
                    f"defaults.{f['name']}",
                    f"{name}.{f['name']} on the edges of {change.model}.{change.name} that exist",
                    field_descriptor(f),
                )
                for f in required_literals(model)
                if f["name"] not in have
            ]
        return asked
    if isinstance(change, c.RemoveEnumMember) and change.replacement is None:
        members = [m["name"] for m in state["enums"].get(change.enum, {}).get("members", [])]
        others = [m for m in members if m != change.member]
        return [
            Question(
                "replacement",
                f"{change.enum}.{change.member} is to go. The member to give the values that have it "
                f"({', '.join(others)}; nothing: it fails if any do)",
                {"type": "str"},
                optional=True,
            )
        ]
    return []


def with_answer(change: c.Change, field: str, value: Any) -> c.Change:
    if "." in field:
        outer, key = field.split(".", 1)
        current = dict(getattr(change, outer) or {})
        current[key] = value
        return dataclasses.replace(change, **{outer: current})
    return dataclasses.replace(change, **{field: value})


def parse_value(text: str, descriptor: dict[str, Any], enums: dict[str, Any]) -> Any:
    """An answer typed by a person, as data for the migration file"""
    kind = descriptor["type"]
    text = text.strip()
    try:
        if kind == "int":
            return int(text)
        if kind == "float":
            return float(text)
        if kind == "bool":
            if text.lower() in ("true", "yes", "y", "1"):
                return True
            if text.lower() in ("false", "no", "n", "0"):
                return False
            raise ValueError(text)
        if kind in ("decimal",):
            float(text)  # (it must be a number: it is kept as the text)
            return text
        if kind == "date":
            return datetime.date.fromisoformat(text).isoformat()
        if kind == "enum":
            members = enums.get(descriptor["enum"], {}).get("members", [])
            for member in members:
                if text in (member["name"], str(member["value"])):
                    return member["name"]
            raise ValueError(text)
        if kind == "list":
            return [
                parse_value(part, descriptor["item"], enums)
                for part in text.split(",")
                if part.strip()
            ]
    except ValueError:
        raise PanglossMigrationError(f"'{text}' is not a valid {kind}") from None
    return text


def collect_questions(
    changes: list[c.Change], state: dict[str, Any]
) -> list[tuple[int, Question]]:
    """The questions for a list of changes (the position of the change, and the question), each
    asked of the snapshot just before it"""
    asked: list[tuple[int, Question]] = []
    for index, change in enumerate(changes):
        asked += [(index, question) for question in answers_needed(change, state)]
        state = apply_change(state, change)
    return asked
