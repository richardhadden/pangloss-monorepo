"""What to offer at the cursor, and what to say of the word under it.

The schema (`pangloss_models.editor_schema`) is what `pangloss check` knew of the project at its last run. This turns
it and the text of the buffer into completion items; it does not talk to the editor.
"""

import ast
import re
from typing import Any

from lsprotocol import types

from pangloss_lsp.context import (
    CallContext,
    bases_of,
    call_at,
    class_body_word,
    enclosing_class,
    field_of_statement,
    fields_declared_in,
)

# The options that name a field of the class they are written in
FIELD_OPTIONS = frozenset(
    {"view_extra_fields", "reference_view_extra_fields", "hide_on_forms", "bound_field"}
)
# ... that name a model (by its name as a string)
MODEL_OPTIONS = frozenset({"allowed_type_names", "excluded_type_names"})
# ... that name a model's class
CLASS_OPTIONS = {"default_reified_type": ("ReifiedRelation", "ReifiedRelationDocument")}

# (what "label" is: every document and entity has one, and may index it; it is not one of the fields)
HAS_LABEL = ("Document", "Entity")


def resolve_call(schema: dict[str, Any], callee: str) -> dict[str, Any] | None:
    """The options of `Document.Meta`, `Person.Meta`, `pangloss_models.RelationConfig`, `InterfaceMeta`..."""
    parts = callee.split(".")
    aliases, calls = schema.get("aliases", {}), schema.get("calls", {})
    for name in (callee, ".".join(parts[-2:])):
        if name in aliases:
            return calls.get(aliases[name])
    return calls.get(parts[-1])


def short(type_text: str) -> str:
    return type_text if len(type_text) <= 48 else type_text[:45] + "..."


def parameter_markdown(parameter: dict[str, Any]) -> str:
    default = f" = {parameter['default']}" if parameter.get("default") else ""
    heading = f"`{parameter['name']}: {short(parameter['type'])}{default}`"
    return f"{heading}\n\n{parameter['doc']}" if parameter.get("doc") else heading


def offset_of(text: str, position: types.Position) -> int:
    offset = 0
    for number, line in enumerate(text.splitlines(keepends=True)):
        if number == position.line:
            return offset + min(position.character, len(line.rstrip("\r\n")))
        offset += len(line)
    return len(text)


def position_of(text: str, offset: int) -> types.Position:
    line = text.count("\n", 0, offset)
    return types.Position(
        line=line, character=offset - (text.rfind("\n", 0, offset) + 1)
    )


def _item(
    text: str,
    start: int,
    end: int,
    label: str,
    new_text: str,
    kind: types.CompletionItemKind,
    detail: str | None = None,
    documentation: str | None = None,
    sort: str | None = None,
) -> types.CompletionItem:
    return types.CompletionItem(
        label=label,
        kind=kind,
        detail=detail,
        documentation=types.MarkupContent(types.MarkupKind.Markdown, documentation)
        if documentation
        else None,
        sort_text=sort,
        filter_text=label,
        text_edit=types.TextEdit(
            types.Range(position_of(text, start), position_of(text, end)), new_text
        ),
    )


def candidate_values(
    schema: dict[str, Any],
    ctx: CallContext,
    parameter: dict[str, Any],
    text: str,
) -> list[tuple[str, bool]]:
    """What the option can be given, as `(text, is it a string)`"""
    name = parameter["name"]
    lines = text.splitlines()
    owner = enclosing_class(lines, ctx.statement_line)
    models: dict[str, Any] = schema.get("models", {})

    if name == "indexes" or name in FIELD_OPTIONS:
        if owner is None:
            return []
        model = models.get(owner[0], {})
        known: dict[str, str] = model.get("fields", {})
        typed = [f for f in fields_declared_in(lines, owner[1]) if f not in known]
        if name == "indexes":
            # (an index is of a value the node itself holds)
            names = [f for f, kind in known.items() if kind in ("literal", "list")]
            names += typed
            if model.get("kind", "Document") in HAS_LABEL:
                names.append("label")
        else:
            names = [*known, *typed]
        return [(n, True) for n in dict.fromkeys(names)]
    if name in MODEL_OPTIONS:
        return [(n, True) for n in sorted(models)]
    if name in CLASS_OPTIONS:
        wanted = CLASS_OPTIONS[name]
        return [
            (n, False)
            for n, model in sorted(models.items())
            if model.get("kind") in wanted
        ]
    if name == "reverse_name":
        field = field_of_statement(lines, ctx.statement_line)
        return [(f"{field}_reverse", True)] if field else []
    return [tuple(choice) for choice in parameter.get("choices", [])]  # type: ignore[misc]


def complete_call(
    schema: dict[str, Any], text: str, offset: int
) -> list[types.CompletionItem]:
    ctx = call_at(text, offset)
    if ctx is None:
        return []
    call = resolve_call(schema, ctx.callee)
    if call is None:
        return []
    parameters = {p["name"]: p for p in call["parameters"]}

    if ctx.at_name:
        return [
            _item(
                text,
                ctx.prefix_start,
                offset,
                name,
                f"{name}=",
                types.CompletionItemKind.Property,
                detail=short(parameter["type"]),
                documentation=parameter_markdown(parameter),
                sort=f"{index:03}",
            )
            for index, (name, parameter) in enumerate(parameters.items())
            if name not in ctx.used
        ]

    parameter = parameters.get(ctx.keyword or "")
    if parameter is None:
        return []
    items = []
    for index, (value, is_string) in enumerate(
        candidate_values(schema, ctx, parameter, text)
    ):
        if ctx.in_string:
            if not is_string:
                continue
            new_text = value
        else:
            new_text = f'"{value}"' if is_string else value
        items.append(
            _item(
                text,
                ctx.prefix_start,
                offset,
                value,
                new_text,
                types.CompletionItemKind.Value
                if is_string
                else types.CompletionItemKind.EnumMember,
                detail=parameter["name"],
                sort=f"{index:03}",
            )
        )
    return items


def import_edit(text: str, module: str, name: str) -> types.TextEdit | None:
    """`from module import name`, after the last import of the file, unless the file has it already"""
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return None
    last = 0
    for node in tree.body:
        if isinstance(node, ast.ImportFrom | ast.Import):
            if any((alias.asname or alias.name) == name for alias in node.names):
                return None
            last = node.end_lineno or node.lineno
        elif (
            last == 0
            and isinstance(node, ast.Expr)
            and isinstance(node.value, ast.Constant)
            and isinstance(node.value.value, str)
        ):
            last = node.end_lineno or node.lineno
    where = types.Position(line=last, character=0)
    return types.TextEdit(types.Range(where, where), f"from {module} import {name}\n")


def complete_class_body(
    schema: dict[str, Any], text: str, offset: int
) -> list[types.CompletionItem]:
    """At the start of a line in a class body: the `_x_meta` slots the installed apps registered, and `_meta`"""
    word = class_body_word(text, offset)
    if word is None or not word[1].startswith("_"):
        return []
    start, _ = word
    lines = text.splitlines()
    line = text.count("\n", 0, offset)
    owner = enclosing_class(lines, line)
    if owner is None:
        return []

    entries: list[tuple[str, str, str, str | None, types.TextEdit | None]] = []
    for base in bases_of(lines, owner[1]):
        meta = schema.get("aliases", {}).get(f"{base}.Meta")
        if meta:
            entries.append(("_meta", f"{base}.Meta", meta, None, None))
            break
    for slot in schema.get("slots", []):
        entries.append(
            (
                slot["name"],
                slot["class"],
                slot["class"],
                slot.get("doc"),
                import_edit(text, slot["module"], slot["class"]),
            )
        )
    return [
        types.CompletionItem(
            label=name,
            kind=types.CompletionItemKind.Field,
            detail=call,
            documentation=types.MarkupContent(types.MarkupKind.Markdown, doc)
            if doc
            else None,
            filter_text=name,
            insert_text_format=types.InsertTextFormat.Snippet,
            text_edit=types.TextEdit(
                types.Range(position_of(text, start), position_of(text, offset)),
                f"{name} = {call}($0)",
            ),
            additional_text_edits=[edit] if edit else None,
        )
        for name, call, _, doc, edit in entries
    ]


def complete(
    schema: dict[str, Any], text: str, offset: int
) -> list[types.CompletionItem]:
    return complete_call(schema, text, offset) or complete_class_body(
        schema, text, offset
    )


def hover_on_parameter(schema: dict[str, Any], text: str, offset: int) -> str | None:
    """The documentation of the option the cursor is on, in `Meta(indexes=[...])`"""
    word = re.search(r"\w*$", text[:offset])
    following = re.match(r"\w*", text[offset:])
    if not word or not word[0] and not (following and following[0]):
        return None
    end = offset + (len(following[0]) if following else 0)
    name = text[offset - len(word[0]) : end]
    if not re.match(r"\s*=(?!=)", text[end:]):
        return None
    # (the word is an argument's name, so far as the text before it goes: the `=` is after)
    ctx = call_at(text, end)
    if ctx is None or not ctx.at_name:
        return None
    call = resolve_call(schema, ctx.callee)
    if call is None:
        return None
    for parameter in call["parameters"]:
        if parameter["name"] == name:
            return parameter_markdown(parameter)
    return None
