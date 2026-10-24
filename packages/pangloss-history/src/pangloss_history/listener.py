"""The listener that makes a record of each write (`pangloss_models.hooks.after_write`)"""

import json
import logging
from typing import Any

from pangloss_core import settings as core_settings
from pangloss_models import hooks
from pangloss_models.hooks import WriteEvent

from pangloss_history import config
from pangloss_history.recorder import Recorder, stop_at_exit
from pangloss_history.schema_position import schema_position
from pangloss_history.store import HistoryRecord, SqliteStore

logger = logging.getLogger("pangloss.history")

_recorder: Recorder | None = None


def get_recorder() -> Recorder:
    """The recorder, made when it is first needed (so the settings are there)"""
    global _recorder
    if _recorder is None:
        _recorder = Recorder(
            SqliteStore(config.db_path()),
            queue_size=config.setting("HISTORY_QUEUE_SIZE", config.DEFAULT_QUEUE_SIZE),
            batch_size=config.setting("HISTORY_BATCH_SIZE", config.DEFAULT_BATCH_SIZE),
            batch_ms=config.setting("HISTORY_BATCH_MS", config.DEFAULT_BATCH_MS),
        )
        stop_at_exit(_recorder)
    return _recorder


def reset_recorder() -> None:
    """Stop and forget the recorder (for tests, and a changed path)"""
    global _recorder
    if _recorder is not None:
        _recorder.stop()
    _recorder = None


def as_reference(node: dict[str, Any]) -> dict[str, Any]:
    """An entity written in a document (`create_new`) as a reference to it: the entity is a head
    node with its own history, and the document holds only the reference (which is also what an
    update of it holds)"""
    return {
        "id": node["id"],
        "type": node["type"],
        "label": None,
        **(
            {"edge_properties": node["edge_properties"]}
            if node.get("edge_properties")
            else {}
        ),
    }


def references_to_written_entities(value: Any) -> Any:
    if isinstance(value, dict):
        if value.get("create_new") and "id" in value and "type" in value:
            return as_reference(value)
        return {k: references_to_written_entities(v) for k, v in value.items()}
    if isinstance(value, list):
        return [references_to_written_entities(v) for v in value]
    return value


def serialise(payload: Any) -> str:
    """The write form as JSON. (Done now, so that what is kept is what was written, even if
    the caller changes the object afterwards.) An entity written inside a document is kept as the
    reference to it; the entity itself has its own record. (A head node that is an entity has
    `create_new` itself, and is kept whole.)"""
    data = json.loads(payload.model_dump_json())
    data = {k: references_to_written_entities(v) for k, v in data.items()}
    return json.dumps(data)


def records_of(event: WriteEvent, position: dict[str, str]) -> list[HistoryRecord]:
    # (an entity that the write made has its own first version, before the document that
    # named it)
    records = [
        HistoryRecord(
            head_id=entity.id,
            version=1,
            op="create",
            model=entity.type,
            at=event.at,
            who=event.user,
            schema_position=position,
            content=serialise(entity),
        )
        for entity in event.created_entities
    ]
    records.append(
        HistoryRecord(
            head_id=event.id,
            version=event.version,
            op="restore" if event.restored_from is not None else event.op,
            model=event.model.__name__,
            at=event.at,
            who=event.user,
            schema_position=position,
            content=serialise(event.payload) if event.payload is not None else None,
            restored_from=event.restored_from,
        )
    )
    return records


def on_write(event: WriteEvent) -> None:
    if event.model.__name__ in config.excluded_models():
        return
    settings = core_settings.__dict__.get("SETTINGS")
    apps = settings.INSTALLED_APPS if settings is not None else []
    recorder = get_recorder()
    for record in records_of(event, schema_position(apps)):
        recorder.submit(record)


def install() -> None:
    """Listen to writes (once)"""
    if on_write not in hooks.after_write:
        hooks.after_write.append(on_write)
