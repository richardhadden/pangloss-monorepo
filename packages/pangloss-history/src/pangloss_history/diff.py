"""The differences between two versions, from their two snapshots (computed when asked for)"""

from dataclasses import asdict, dataclass
from typing import Any, Literal


@dataclass(frozen=True)
class Change:
    path: str
    kind: Literal["added", "removed", "changed"]
    old: Any = None
    new: Any = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def is_identified(items: list[Any]) -> bool:
    """A list of objects that each have an id (nested nodes), which are compared by id and
    not by place"""
    return bool(items) and all(isinstance(i, dict) and "id" in i for i in items)


def diff(old: Any, new: Any, path: str = "") -> list[Change]:
    if isinstance(old, dict) and isinstance(new, dict):
        changes: list[Change] = []
        for key in sorted(old.keys() | new.keys()):
            here = f"{path}.{key}" if path else key
            if key not in new:
                changes.append(Change(here, "removed", old=old[key]))
            elif key not in old:
                changes.append(Change(here, "added", new=new[key]))
            else:
                changes.extend(diff(old[key], new[key], here))
        return changes

    if isinstance(old, list) and isinstance(new, list):
        if is_identified(old + new):
            before = {str(i["id"]): i for i in old}
            after = {str(i["id"]): i for i in new}
            changes = []
            for id in [*before, *(i for i in after if i not in before)]:
                here = f"{path}[{id}]"
                if id not in after:
                    changes.append(Change(here, "removed", old=before[id]))
                elif id not in before:
                    changes.append(Change(here, "added", new=after[id]))
                else:
                    changes.extend(diff(before[id], after[id], here))
            return changes
        changes = []
        for index in range(max(len(old), len(new))):
            here = f"{path}[{index}]"
            if index >= len(new):
                changes.append(Change(here, "removed", old=old[index]))
            elif index >= len(old):
                changes.append(Change(here, "added", new=new[index]))
            else:
                changes.extend(diff(old[index], new[index], here))
        return changes

    return [] if old == new else [Change(path, "changed", old=old, new=new)]
