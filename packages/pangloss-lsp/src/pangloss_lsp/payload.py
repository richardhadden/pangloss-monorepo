"""Completion in the dict literals of a payload: `{"type": "Person", "bornIn": ...}`.

Such a dict says which model it is for by its `"type"`, so the keys that model has can be offered (camelCase, as the
API takes them), and for `"type"` itself the names of the models. A dict that does not say is offered `type`.
"""

import re
from typing import Any

from lsprotocol import types
from pydantic.alias_generators import to_camel

from pangloss_lsp.context import scan
from pangloss_lsp.positions import position_of

# What every document and entity has, besides its fields
HEAD_KEYS = ("type", "label", "id")
HAS_HEAD = ("Document", "Entity", "ReifiedRelationDocument")
_TYPE_ENTRY = re.compile(r"\s*[\"']type[\"']\s*:\s*[\"'](\w+)[\"']\s*")
_KEY = re.compile(r"\s*([\"']?)(\w*)")
_TYPE_VALUE = re.compile(r"\s*[\"']type[\"']\s*:\s*([\"']?)(\w*)")


def complete_payload(
    schema: dict[str, Any], text: str, offset: int
) -> list[types.CompletionItem]:
    state = scan(text, offset)
    if not state.frames or state.frames[-1].char != "{" or state.in_comment:
        return []
    frame = state.frames[-1]
    models: dict[str, Any] = schema.get("models", {})
    if not models:
        return []

    commas = [c for c in frame.commas if c < offset]
    entry = text[(commas[-1] if commas else frame.position) + 1 : offset]

    in_string = state.quote is not None
    if in_string:
        prefix_start = (state.string_start or 0) + len(state.quote or "")
    else:
        word = re.search(r"\w*$", text[:offset])
        prefix_start = offset - (len(word[0]) if word else 0)

    # The entries of the dict, but the one being typed
    bounds = [frame.position, *frame.commas, frame.close or len(text)]
    others = [
        text[start + 1 : end]
        for start, end in zip(bounds, bounds[1:], strict=False)
        if not start < offset <= end
    ]
    named = next((m[1] for e in others if (m := _TYPE_ENTRY.fullmatch(e))), None)

    value = _TYPE_VALUE.fullmatch(entry)
    if value is not None:
        names = sorted(
            n
            for n, model in models.items()
            if "[" not in n and not model.get("abstract") and model.get("kind")
        )
        return [_item(text, prefix_start, offset, n, in_string, "model") for n in names]

    if _KEY.fullmatch(entry) is None:
        return []
    given = {m[1] for e in others if (m := re.match(r"\s*[\"'](\w+)[\"']\s*:", e))}
    model = models.get(named or "")
    if model is None:
        keys = ["type"]
    else:
        keys = [*HEAD_KEYS] if model.get("kind") in HAS_HEAD else ["type"]
        keys += [to_camel(field) for field in model.get("fields", {})]
    return [
        _item(text, prefix_start, offset, key, in_string, f"{named or 'a payload'} key")
        for key in keys
        if key not in given
    ]


def _item(
    text: str, start: int, end: int, label: str, in_string: bool, detail: str
) -> types.CompletionItem:
    return types.CompletionItem(
        label=label,
        kind=types.CompletionItemKind.Property,
        detail=detail,
        filter_text=label,
        text_edit=types.TextEdit(
            types.Range(position_of(text, start), position_of(text, end)),
            label if in_string else f'"{label}"',
        ),
    )
