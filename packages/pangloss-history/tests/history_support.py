"""Records to put in a store"""

import datetime
import json
from uuid import UUID, uuid7

from pangloss_history.store import HistoryRecord

AT = datetime.datetime(2026, 10, 23, 12, 0, tzinfo=datetime.UTC)


def record(
    head_id: UUID | None = None,
    version: int = 1,
    op: str = "create",
    content: dict | None = None,
    model: str = "Statement",
    who: str = "john",
    **fields,
) -> HistoryRecord:
    has_content = op in ("create", "update", "restore")
    if content is None and has_content:
        content = {"text": f"version {version}"}
    return HistoryRecord(
        head_id=head_id or uuid7(),
        version=version,
        op=op,
        model=model,
        at=AT,
        who=who,
        schema_position={"letters": "0001_initial"},
        content=json.dumps(content) if content is not None else None,
        **fields,
    )
