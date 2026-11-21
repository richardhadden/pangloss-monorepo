"""Whether the vectors in use are those today's parts and settings would make: for each part and each profile, what is
in use and, if a rebuild is due, why, in words (`pangloss vectors status`, `GET /api/vectors/status`).

A **part** is due for a rebuild if it has never been built, if its `signature()` is not the one it was built with (the
models it reads, or a setting it depends on, changed: `VECTORS_CLASS_DECAY` for the class part), or if
`VECTORS_GRAPH_SEES` is not what it was built with. A part whose `requires` the backend lacks is said to be
unavailable, and is never due.

A **profile** is due if it has never been built, if its weights are not those it was built with, if its parts now make
vectors of another dimension (then its vector indexes are new ones, with the dimension in their names: a migration is
pending, which `pangloss showmigrations` reports, and a rebuild follows it), or if a part it weighs is due.

`status()` also says whether a rebuild is running now (`rebuilding`: who holds its lease, and since when), read with the
states.

`pangloss check` does not say it: it looks at the models and files only, without a database, and has no hook for an
app's check of one (implementation_docs/vectors.md, "Rebuild and status")."""

import dataclasses
import datetime
from collections.abc import Mapping
from typing import Any

from pangloss_vectors import store
from pangloss_vectors.parts import Part, parts, profiles
from pangloss_vectors.settings import graph_sees


@dataclasses.dataclass(frozen=True)
class PartStatus:
    part: str
    dimension: int
    """Of its vectors today"""
    signature: str
    """Today's"""
    generation: int | None
    """In use (None: never built)"""
    built_at: datetime.datetime | None
    count: int
    """Vectors in the generation in use"""
    stale: int
    """Of them, written approximately, waiting for a rebuild"""
    reasons: tuple[str, ...] = ()
    """Why a rebuild is due (none: it is not)"""
    unavailable: str | None = None
    """Why it cannot be built on this backend (its `requires`), if it cannot"""

    @property
    def rebuild_due(self) -> bool:
        return bool(self.reasons)


@dataclasses.dataclass(frozen=True)
class ProfileStatus:
    profile: str
    weights: Mapping[str, float]
    """Today's, of the parts above zero"""
    dimension: int
    """Of its vectors today"""
    generation: int | None
    built_at: datetime.datetime | None
    count: int
    reasons: tuple[str, ...] = ()

    @property
    def rebuild_due(self) -> bool:
        return bool(self.reasons)


@dataclasses.dataclass(frozen=True)
class Rebuilding:
    """A rebuild running now: who holds its lease (a user, the process and the host, as `VectorsRebuildBusy` names
    it), and since when"""

    by: str
    since: datetime.datetime


@dataclasses.dataclass(frozen=True)
class Status:
    parts: list[PartStatus]
    profiles: list[ProfileStatus]
    rebuilding: Rebuilding | None = None
    """The rebuild running now, whoever started it (the admin job, or `pangloss vectors rebuild`); read by `status()`
    only"""

    @property
    def rebuild_due(self) -> bool:
        return any(p.rebuild_due for p in self.parts) or any(
            p.rebuild_due for p in self.profiles
        )

    def profile(self, name: str) -> ProfileStatus | None:
        return next((p for p in self.profiles if p.profile == name), None)

    def as_json(self) -> dict[str, Any]:
        """As the API gives it (camelCase; the weights by the names of the parts)"""

        def when(moment: datetime.datetime | None) -> str | None:
            return None if moment is None else moment.isoformat()

        return {
            "rebuildDue": self.rebuild_due,
            "rebuilding": None
            if self.rebuilding is None
            else {"by": self.rebuilding.by, "since": when(self.rebuilding.since)},
            "parts": [
                {
                    "part": p.part,
                    "dimension": p.dimension,
                    "signature": p.signature,
                    "generation": p.generation,
                    "builtAt": when(p.built_at),
                    "count": p.count,
                    "stale": p.stale,
                    "rebuildDue": p.rebuild_due,
                    "reasons": list(p.reasons),
                    "unavailable": p.unavailable,
                }
                for p in self.parts
            ],
            "profiles": [
                {
                    "profile": p.profile,
                    "weights": dict(p.weights),
                    "dimension": p.dimension,
                    "generation": p.generation,
                    "builtAt": when(p.built_at),
                    "count": p.count,
                    "rebuildDue": p.rebuild_due,
                    "reasons": list(p.reasons),
                }
                for p in self.profiles
            ],
        }


def unavailable(
    made: Part, capabilities: Any = None, backend_name: str = ""
) -> str | None:
    """Why a part cannot be built on the backend in use (a capability of its `requires` the backend lacks), or None"""
    if capabilities is None:
        from pangloss_core import storage_of

        storage = storage_of()
        capabilities, backend_name = storage.capabilities, storage.name
    missing = sorted(
        name for name in made.requires if not getattr(capabilities, name, False)
    )
    if not missing:
        return None
    return f"it needs {', '.join(missing)}, which the backend {backend_name!r} does not have"


def weights_text(weights: Mapping[str, float]) -> str:
    return (
        ", ".join(f"{name} {weight:g}" for name, weight in sorted(weights.items()))
        or "none"
    )


def part_reasons(
    made: Part, state: store.PartState | None, sees: str
) -> tuple[str, ...]:
    if state is None:
        return ("it has never been built",)
    reasons = []
    if state.signature != made.signature():
        reasons.append(
            f"its signature is now {made.signature()}, not the {state.signature or '(none)'} it was built with: "
            "the models it reads or a setting it depends on changed"
        )
    if state.graph_sees != sees:
        reasons.append(
            f"VECTORS_GRAPH_SEES is now {sees!r}, not the {state.graph_sees or '(none)'!r} it was built with"
        )
    return tuple(reasons)


def profile_reasons(
    weights: Mapping[str, float],
    layout: store.Layout,
    state: store.ProfileState | None,
    due_parts: set[str],
) -> tuple[str, ...]:
    if state is None:
        return ("it has never been built",)
    reasons = []
    if dict(state.weights) != dict(weights):
        reasons.append(
            f"its weights are now {weights_text(weights)}, not the {weights_text(state.weights)} it was built with"
        )
    if state.dimension != layout.dimension:
        reasons.append(
            f"its parts now make vectors of dimension {layout.dimension}, not {state.dimension}: its vector indexes "
            "are new ones (a migration is pending), and it has to be rebuilt after the migration"
        )
    for name in sorted(set(weights) & due_parts):
        reasons.append(f"the {name} part it weighs has to be rebuilt")
    return tuple(reasons)


def status_of(found: store.States, rebuilding: Rebuilding | None = None) -> Status:
    """The status, from the states read (and the rebuild running, if it was read with them)"""
    from pangloss_core import storage_of

    storage = storage_of()
    sees = graph_sees()
    part_statuses = []
    for name, made in parts().items():
        state = found.parts.get(name)
        why_not = unavailable(made, storage.capabilities, storage.name)
        part_statuses.append(
            PartStatus(
                part=name,
                dimension=made.dimension(),
                signature=made.signature(),
                generation=None if state is None else state.generation,
                built_at=None if state is None else state.built_at,
                count=0 if state is None else state.count,
                stale=0 if state is None else state.stale,
                reasons=() if why_not else part_reasons(made, state, sees),
                unavailable=why_not,
            )
        )
    due_parts = {p.part for p in part_statuses if p.rebuild_due}
    profile_statuses = []
    for name, weights in profiles().items():
        if not weights:
            continue
        layout = store.layout(name, weights)
        state = found.profiles.get(name)
        profile_statuses.append(
            ProfileStatus(
                profile=name,
                weights=dict(layout.weights),
                dimension=layout.dimension,
                generation=None if state is None else state.generation,
                built_at=None if state is None else state.built_at,
                count=0 if state is None else state.count,
                reasons=profile_reasons(layout.weights, layout, state, due_parts),
            )
        )
    return Status(part_statuses, profile_statuses, rebuilding)


async def status() -> Status:
    """For each part and each profile: the generation in use, when it was built, how many vectors it has (and, of a
    part, how many stale), and whether a rebuild is due, with the reasons; and the rebuild running now, if one is. The
    states and the lease in one read"""
    from pangloss_core import backend

    # (here: `rebuild` imports this module)
    from pangloss_vectors.rebuild import running

    database = backend.current().database()

    @database.read_transaction
    async def read(tx: Any) -> tuple[store.States, Rebuilding | None]:
        return await store._states(tx), await running(tx)

    found, rebuilding = await read()
    return status_of(found, rebuilding)
