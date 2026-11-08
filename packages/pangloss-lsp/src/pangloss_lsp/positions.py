"""Offsets in a text, and the line and character an editor names them by."""

from lsprotocol import types


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
