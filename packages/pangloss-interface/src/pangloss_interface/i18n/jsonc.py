"""JSONC: JSON with `//` and `/* */` comments.

Reading takes the comments out (`strip_comments`) and gives the rest to `json`. Writing is `render`,
which writes a nested dict in one fixed form and can put comment lines above a key: the comments are the
generator's, made again each time, so a person's own comments are not kept (see `docs/translations.md`).
"""

import json
from collections.abc import Mapping
from typing import Any


class JsoncError(ValueError):
    pass


def strip_comments(text: str) -> str:
    """The text without its comments. Each comment is replaced by spaces (newlines stay), so that a
    position in an error of `json` is where it is in the text. A `//` inside a string is not a comment.

    Trailing commas are not part of JSONC, and are not accepted."""
    out: list[str] = []
    i, n = 0, len(text)
    while i < n:
        char = text[i]
        if char == '"':
            start = i
            i += 1
            while i < n and text[i] != '"':
                i += 2 if text[i] == "\\" else 1
            i += 1
            out.append(text[start:i])
        elif text.startswith("//", i):
            end = text.find("\n", i)
            end = n if end == -1 else end
            out.append(" " * (end - i))
            i = end
        elif text.startswith("/*", i):
            end = text.find("*/", i + 2)
            if end == -1:
                raise JsoncError(f"a comment that is not closed (at character {i})")
            out.append("".join("\n" if c == "\n" else " " for c in text[i : end + 2]))
            i = end + 2
        else:
            out.append(char)
            i += 1
    return "".join(out)


def loads(text: str) -> Any:
    try:
        return json.loads(strip_comments(text))
    except json.JSONDecodeError as error:
        raise JsoncError(
            f"{error.msg} (line {error.lineno}, column {error.colno})"
        ) from error


Comments = Mapping[tuple[str, ...], list[str]]


def render(
    data: Mapping[str, Any],
    comments: Comments | None = None,
    header: list[str] | None = None,
) -> str:
    """A nested dict as JSONC: indented by 2, keys in the order given, text as it is (not `\\u` escaped).
    `comments` has lines to put above the key at a path; `header` has lines for the top"""
    comments = comments or {}
    lines = [f"// {line}".rstrip() for line in header or []]

    def write(value: Any, path: tuple[str, ...], indent: str) -> str:
        if isinstance(value, Mapping):
            if not value:
                return "{}"
            inner = indent + "  "
            rows = []
            for index, (key, item) in enumerate(value.items()):
                here = (*path, key)
                for comment in comments.get(here, []):
                    rows.append(f"{inner}// {comment}".rstrip())
                comma = "," if index < len(value) - 1 else ""
                rows.append(
                    f"{inner}{json.dumps(key, ensure_ascii=False)}: "
                    f"{write(item, here, inner)}{comma}"
                )
            return "{\n" + "\n".join(rows) + f"\n{indent}}}"
        return json.dumps(value, ensure_ascii=False)

    return "\n".join([*lines, write(data, (), "")]) + "\n"
