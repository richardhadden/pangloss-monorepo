"""Versions that were written and not recorded (best effort: it is information, not an error)"""

from collections.abc import Iterable

from pangloss_history.store import CONTENT_OPERATIONS, HistoryRecord


def find_gaps(records: Iterable[HistoryRecord], current_version: int) -> list[int]:
    """The versions from 1 to the graph's version that have no record"""
    recorded = {r.version for r in records if r.op in CONTENT_OPERATIONS}
    return [v for v in range(1, current_version + 1) if v not in recorded]
