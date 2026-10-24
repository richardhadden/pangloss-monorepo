"""What a dry run of a migration found: for each change, what it would do to the data."""

from dataclasses import dataclass, field
from typing import Literal

from pangloss_models.migrations import changes as c

COUNT_NAMES = {
    "nodes_created": "nodes made",
    "nodes_deleted": "nodes deleted",
    "relationships_created": "edges made",
    "relationships_deleted": "edges deleted",
    "properties_set": "properties set",
    "labels_added": "labels added",
    "labels_removed": "labels removed",
}


@dataclass
class ChangeReport:
    change: c.Change
    #: "counted": run and rolled back, with the counts; "ddl": not run (a change to the database
    #: itself cannot be tried); "error": it could not be applied, and why; "not tried": an earlier
    #: change failed
    status: Literal["counted", "ddl", "error", "not tried"]
    counts: dict[str, int] = field(default_factory=dict)
    message: str | None = None

    def summary(self) -> str:
        if self.status == "ddl":
            return "changes the database itself (an index or constraint: not tried)"
        if self.status == "not tried":
            return "not tried (an earlier change failed)"
        if self.status == "error":
            return f"WOULD FAIL: {self.message}"
        parts = [
            f"{self.counts[key]} {name}"
            for key, name in COUNT_NAMES.items()
            if self.counts.get(key)
        ]
        return ", ".join(parts) if parts else "no change to the data"


@dataclass
class MigrationReport:
    app: str
    name: str
    changes: list[ChangeReport] = field(default_factory=list)

    @property
    def failed(self) -> bool:
        return any(report.status == "error" for report in self.changes)
