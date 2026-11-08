"""The inlay hints: what the source does not say about a field, after its line."""

import re
from dataclasses import dataclass

from pangloss_lsp.context import enclosing_class, line_end_depths


@dataclass(frozen=True)
class Hint:
    line: int
    character: int
    label: str
    tooltip: str | None = None


def hints_in(
    hints: dict[str, dict[str, str]], text: str, first: int, last: int
) -> list[Hint]:
    """The hints for the fields declared on lines `first` to `last`, after the line the field's statement ends on"""
    if not hints:
        return []
    lines = text.splitlines()
    depths = line_end_depths(text)
    found: list[Hint] = []
    # (a statement that began above the range may end in it, so go from the top of what was asked for, not its middle)
    for number in range(max(first, 0), min(last + 1, len(lines))):
        declared = re.match(r"\s+([A-Za-z_]\w*)\s*:", lines[number])
        if declared is None or declared[1].startswith("_"):
            continue
        # (a line inside the brackets of a statement above is not a field)
        if number > 0 and depths[number - 1] > 0:
            continue
        owner = enclosing_class(lines, number)
        if owner is None:
            continue
        hint = hints.get(f"{owner[0]}.{declared[1]}")
        if hint is None:
            continue
        end = number
        while end < len(lines) - 1 and depths[end] > 0:
            end += 1
        found.append(
            Hint(end, len(lines[end].rstrip()), hint["label"], hint.get("tooltip"))
        )
    return found
