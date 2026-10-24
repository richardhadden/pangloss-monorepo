"""Where history is kept: the `HistoryStore` interface, and the SQLite store that is the default.

A record is one write to a head node. Its content is the JSON of the write form (see
`docs/history.md`), kept once for each different content (the `blobs` table, by hash) and
compressed with zstd. Each operation opens its own short-lived connection, so the store can be
used from any thread; WAL mode lets readers work while the worker writes.
"""

import contextlib
import dataclasses
import datetime
import hashlib
import json
import sqlite3
from collections.abc import Generator, Sequence
from pathlib import Path
from typing import Any, Protocol
from uuid import UUID

import zstandard

OPERATIONS = ("create", "update", "delete", "undelete", "restore")
# The operations that have a version of their own (and content)
CONTENT_OPERATIONS = ("create", "update", "restore")


@dataclasses.dataclass(frozen=True)
class HistoryRecord:
    head_id: UUID
    # The version of the head node when it was written. A delete or undelete changes no
    # content, and has the version the node had.
    version: int
    op: str
    model: str
    at: datetime.datetime
    who: str
    # The last applied migration of each app
    schema_position: dict[str, str]
    # The write form, as JSON text. `None` for delete and undelete.
    content: str | None = None
    restored_from: int | None = None
    # Counts the records of a head node. Given by the store.
    seq: int | None = None

    @property
    def content_hash(self) -> str | None:
        if self.content is None:
            return None
        return hashlib.sha256(self.content.encode()).hexdigest()

    def data(self) -> Any:
        """The content, parsed"""
        return json.loads(self.content) if self.content is not None else None


class HistoryStore(Protocol):
    """What history needs of a store, so that a project can use what it likes"""

    def append(self, records: Sequence[HistoryRecord]) -> None:
        """Add the records (all of them, or none), in order"""

    def versions(self, head_id: UUID) -> list[HistoryRecord]:
        """Every record of a head node, in order, without content"""

    def get(self, head_id: UUID, version: int) -> HistoryRecord | None:
        """The latest record that has content and is of this version, with its content"""

    def latest_version(self, head_id: UUID) -> int | None:
        """The highest version recorded for a head node"""

    def position_counts(self) -> list[tuple[dict[str, str], int]]:
        """Each schema position that records were made at, and how many versions were"""

    def close(self) -> None: ...


SCHEMA = """
CREATE TABLE IF NOT EXISTS history (
    head_id TEXT NOT NULL,
    seq INTEGER NOT NULL,
    version INTEGER NOT NULL,
    op TEXT NOT NULL,
    model TEXT NOT NULL,
    at TEXT NOT NULL,
    who TEXT NOT NULL,
    schema_position TEXT NOT NULL,
    content_hash TEXT,
    restored_from INTEGER,
    PRIMARY KEY (head_id, seq)
) WITHOUT ROWID;
CREATE INDEX IF NOT EXISTS history_at ON history (at);
CREATE INDEX IF NOT EXISTS history_who ON history (who);
CREATE TABLE IF NOT EXISTS blobs (
    content_hash TEXT PRIMARY KEY,
    content BLOB NOT NULL
) WITHOUT ROWID;
"""

COLUMNS = "head_id, seq, version, op, model, at, who, schema_position, content_hash, restored_from"


def record_from_row(row: tuple, content: str | None = None) -> HistoryRecord:
    head_id, seq, version, op, model, at, who, position, _, restored_from = row
    return HistoryRecord(
        head_id=UUID(head_id),
        seq=seq,
        version=version,
        op=op,
        model=model,
        at=datetime.datetime.fromisoformat(at),
        who=who,
        schema_position=json.loads(position),
        content=content,
        restored_from=restored_from,
    )


class SqliteStore:
    def __init__(self, path: Path | str):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        # Best effort: a flush for each write is not worth it
        with self.connection() as db:
            db.execute("PRAGMA journal_mode=WAL")
            db.executescript(SCHEMA)
        self.compressor = zstandard.ZstdCompressor()
        self.decompressor = zstandard.ZstdDecompressor()

    @contextlib.contextmanager
    def connection(self) -> Generator[sqlite3.Connection]:
        db = sqlite3.connect(self.path, timeout=10)
        try:
            db.execute("PRAGMA synchronous=NORMAL")
            with db:  # (commits, or rolls back)
                yield db
        finally:
            db.close()

    def append(self, records: Sequence[HistoryRecord]) -> None:
        with self.connection() as db:
            for record in records:
                head_id = str(record.head_id)
                (seq,) = db.execute(
                    "SELECT coalesce(max(seq), 0) + 1 FROM history WHERE head_id = ?",
                    (head_id,),
                ).fetchone()
                content_hash = record.content_hash
                if content_hash is not None and record.content is not None:
                    db.execute(
                        "INSERT OR IGNORE INTO blobs VALUES (?, ?)",
                        (
                            content_hash,
                            self.compressor.compress(record.content.encode()),
                        ),
                    )
                db.execute(
                    f"INSERT INTO history ({COLUMNS}) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        head_id,
                        seq,
                        record.version,
                        record.op,
                        record.model,
                        record.at.isoformat(),
                        record.who,
                        json.dumps(record.schema_position, sort_keys=True),
                        content_hash,
                        record.restored_from,
                    ),
                )

    def versions(self, head_id: UUID) -> list[HistoryRecord]:
        with self.connection() as db:
            rows = db.execute(
                f"SELECT {COLUMNS} FROM history WHERE head_id = ? ORDER BY seq",
                (str(head_id),),
            ).fetchall()
        return [record_from_row(row) for row in rows]

    def get(self, head_id: UUID, version: int) -> HistoryRecord | None:
        with self.connection() as db:
            row = db.execute(
                f"SELECT {COLUMNS} FROM history WHERE head_id = ? AND version = ? "
                "AND content_hash IS NOT NULL ORDER BY seq DESC LIMIT 1",
                (str(head_id), version),
            ).fetchone()
            if row is None:
                return None
            (blob,) = db.execute(
                "SELECT content FROM blobs WHERE content_hash = ?", (row[8],)
            ).fetchone()
        return record_from_row(row, self.decompressor.decompress(blob).decode())

    def latest_version(self, head_id: UUID) -> int | None:
        with self.connection() as db:
            (version,) = db.execute(
                "SELECT max(version) FROM history WHERE head_id = ?", (str(head_id),)
            ).fetchone()
        return version

    def position_counts(self) -> list[tuple[dict[str, str], int]]:
        with self.connection() as db:
            rows = db.execute(
                "SELECT schema_position, count(*) FROM history WHERE content_hash IS NOT NULL "
                "GROUP BY schema_position"
            ).fetchall()
        return [(json.loads(position), count) for position, count in rows]

    def close(self) -> None:
        pass
