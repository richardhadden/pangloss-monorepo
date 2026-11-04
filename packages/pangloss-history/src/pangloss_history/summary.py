"""What changed in each version, field by field of the head node, against the version recorded before it: what the
interface's list of versions shows of each (docs/history-interface.md)"""

import re
from collections.abc import Sequence
from typing import Any

from pydantic.alias_generators import to_camel

from pangloss_history.diff import diff
from pangloss_history.store import CONTENT_OPERATIONS, HistoryRecord

# (a field of the head node: what a path starts with, up to the first `.` or `[`)
FIELD = re.compile(r"^[^.\[]+")
# (bookkeeping that is in the write form, but is not a change anyone made)
IGNORED = {"semantic_spaces"}


def field_changes(before: Any, after: Any) -> list[dict[str, Any]]:
    """`{key, kind, count}` for each field of the head node that differs: `added` or `removed` if every change under it
    is, otherwise `changed`; `count`, how many changes there are under it"""
    fields: dict[str, list[str]] = {}
    for change in diff(before, after):
        found = FIELD.match(change.path)
        if found is None or found.group(0) in IGNORED:
            continue
        fields.setdefault(found.group(0), []).append(change.kind)
    # (the label first, as the item shows it; then the fields in the order of the diff)
    names = sorted(fields, key=lambda name: name != "label")
    return [
        {
            "key": to_camel(name),
            "kind": fields[name][0] if len(set(fields[name])) == 1 else "changed",
            "count": len(fields[name]),
        }
        for name in names
    ]


def summarise(
    records: Sequence[HistoryRecord], content_of
) -> dict[int, dict[str, Any]]:
    """For each record with content (by `seq`): its label then, and its changes from the one with content before it
    (none for the first). `content_of(record)` gives the parsed content (the store gives the records without it)."""
    summaries: dict[int, dict[str, Any]] = {}
    previous: Any = None
    for record in records:
        if record.op not in CONTENT_OPERATIONS:
            continue
        data = content_of(record)
        if data is None:
            continue
        summaries[record.seq or 0] = {
            "label": data.get("label") if isinstance(data, dict) else None,
            "changes": field_changes(previous, data) if previous is not None else [],
        }
        previous = data
    return summaries
