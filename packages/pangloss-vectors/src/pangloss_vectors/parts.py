"""Parts and profiles: what every package that computes a vector is built against.

A **part** is one kind of vector of an item (`"class"`, here; `"graph"`, of `pangloss-fastrp`; a name or a time
later). It is an object with the attributes and methods of `Part`, given to `register_part` when its package is
imported. This package stores what a part computes, keeps it current and searches it; it knows nothing of how a part
is computed.

A **profile** is data: a weight for each part, by name (`VECTORS_PROFILES = {"default": {"graph": 1, "class": 0.1}}`).
A search scales the parts of its query by the weights of the profile it names. `"default"`, when the settings do not
give it, is every registered part at its own `weight`.

No numpy here: a vector is a sequence of floats. implementation_docs/similarity-build-plan.md, step 2.1.
"""

import hashlib
import json
from collections.abc import Awaitable, Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

from pangloss_models.exceptions import PanglossInitialisationError

type Vector = Sequence[float]

DEFAULT_PROFILE = "default"


@dataclass(frozen=True, slots=True)
class Item:
    """A head (a document or an entity) by its id and the name of its class"""

    id: str
    type: str


@dataclass(frozen=True, slots=True)
class VectorRow:
    """The vector of one item, as a part gives it to be written. `type` is the item's class: its groups (the labels
    a search narrows by) are worked out from it by the store"""

    of: str
    type: str
    vector: Vector


# What a part is given to write with: called with rows, any number of times (a page at a time). Where they go (a new
# generation, or the one in use) is the caller's business, not the part's.
type Writer = Callable[[Iterable[VectorRow]], Awaitable[None]]


@dataclass(frozen=True, slots=True)
class Changed:
    """What has changed since a part's vectors were last right: the heads written (created, updated, restored,
    published) and the ids of those gone (deleted, merged into another)"""

    written: tuple[Item, ...] = ()
    removed: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class Refreshed:
    """What a `refresh` did. `written` vectors are right; `stale` ones were written approximately (a neighbourhood
    past the part's cap) and wait for a rebuild. The vectors of `Changed.removed` are deleted by the caller"""

    written: int = 0
    stale: int = 0


@runtime_checkable
class Part(Protocol):
    """One kind of vector. An object, not a class: a part is made once its package is imported, and asked for
    `dimension()` and `signature()` only after `initialise()`, when the models are known"""

    name: str
    """`"class"`, `"graph"`: the key of a profile's weights, and the `part` of the stored vectors"""

    local: bool
    """Whether `refresh` can bring the vectors up to date after a write without a rebuild"""

    requires: frozenset[str]
    """Capabilities of the backend the part cannot do without (the names of `pangloss_core.storage.Capabilities`)"""

    weight: float
    """Its weight in the default profile, when the settings give none"""

    def dimension(self) -> int:
        """The length of its vectors"""
        ...

    def signature(self) -> str:
        """A hash of everything a rebuild depends on (the models it reads, its settings: `signature_of`). Stored with
        a generation: a server whose part says another is told that a rebuild is due"""
        ...

    async def rebuild(self, write: Writer) -> int:
        """Compute the vector of every item and give them to `write`, in pages. Gives how many"""
        ...

    async def refresh(self, changed: Changed, write: Writer) -> Refreshed:
        """Give `write` the vectors that `changed` makes different (those of the written items, and of whatever
        else depends on them). Only called if `local`"""
        ...

    async def overlay(self, plan: Any) -> dict[str, Vector]:
        """The vectors the heads of a write plan (`pangloss_cypher.write_plan.WritePlan`) would have were it
        written, by id; nothing is written"""
        ...


def signature_of(*values: Any) -> str:
    """A short hash of values that JSON can say (sets and tuples as sorted lists): for `Part.signature`"""

    def plain(value: Any) -> Any:
        if isinstance(value, Mapping):
            return {str(key): plain(item) for key, item in sorted(value.items())}
        if isinstance(value, (set, frozenset)):
            return sorted(plain(item) for item in value)
        if isinstance(value, (list, tuple)):
            return [plain(item) for item in value]
        return value

    text = json.dumps(plain(list(values)), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(text.encode()).hexdigest()[:16]


_PARTS: dict[str, Part] = {}


def register_part(part: Part) -> None:
    """Make a part known. Called by the part's package when it is imported; the same object again is nothing, another
    of the same name is refused"""
    if not isinstance(part, Part):
        raise PanglossInitialisationError(
            f"{part!r} is not a part: it needs name, local, requires, weight, dimension(), signature(), rebuild(), "
            "refresh() and overlay() (pangloss_vectors.parts.Part)"
        )
    if not part.name.isidentifier():
        raise PanglossInitialisationError(
            f"A part's name is a word of letters, digits and underscores (it is in the names of labels and indexes), "
            f"not {part.name!r}"
        )
    known = _PARTS.get(part.name)
    if known is part:
        return
    if known is not None:
        raise PanglossInitialisationError(
            f"Two parts are named {part.name!r}: {known!r} and {part!r}. A part's name is the key of its stored "
            "vectors, so one of them needs another"
        )
    _PARTS[part.name] = part


def unregister_part(name: str) -> None:
    """Forget a part (for tests; a package's part stays for the life of the process)"""
    _PARTS.pop(name, None)


def parts() -> dict[str, Part]:
    """The registered parts by name, in the order of their names"""
    return dict(sorted(_PARTS.items()))


def part(name: str) -> Part:
    try:
        return _PARTS[name]
    except KeyError:
        raise PanglossInitialisationError(
            f"There is no part named {name!r}: the parts are {', '.join(sorted(_PARTS)) or 'none'} (a part is "
            "registered when its package is imported: is it among INSTALLED_APPS?)"
        ) from None


def profiles(settings: Any = None) -> dict[str, dict[str, float]]:
    """The profiles: those of the settings (`VECTORS_PROFILES`), checked, and `"default"` if they do not give it.
    Refuses, by name, a profile that names a part that is not registered, a weight that is not a number of zero or
    more, and a profile whose weights are all zero"""
    if settings is None:
        from pangloss_core import settings as core_settings

        settings = core_settings.__dict__.get("SETTINGS")
    given = getattr(settings, "VECTORS_PROFILES", None) or {}
    found: dict[str, dict[str, float]] = {}
    for name, weights in given.items():
        if not isinstance(weights, Mapping):
            raise PanglossInitialisationError(
                f"VECTORS_PROFILES[{name!r}] is a weight for each part ({{'class': 1}}), not {weights!r}"
            )
        unknown = sorted(set(weights) - set(_PARTS))
        if unknown:
            raise PanglossInitialisationError(
                f"VECTORS_PROFILES[{name!r}] names {', '.join(repr(u) for u in unknown)}, which is not a part: the "
                f"parts are {', '.join(sorted(_PARTS)) or 'none'} (a part is registered when its package is "
                "imported: is it among INSTALLED_APPS?)"
            )
        for key, weight in weights.items():
            if (
                isinstance(weight, bool)
                or not isinstance(weight, (int, float))
                or weight < 0
            ):
                raise PanglossInitialisationError(
                    f"VECTORS_PROFILES[{name!r}][{key!r}] is a weight of zero or more, not {weight!r}"
                )
        if not any(weights.values()):
            raise PanglossInitialisationError(
                f"VECTORS_PROFILES[{name!r}] gives no part a weight above zero: it could find nothing"
            )
        found[name] = {key: float(weight) for key, weight in weights.items() if weight}
    if DEFAULT_PROFILE not in found:
        found[DEFAULT_PROFILE] = {
            name: float(made.weight) for name, made in parts().items() if made.weight
        }
    return found


def profile(name: str = DEFAULT_PROFILE, settings: Any = None) -> dict[str, float]:
    """The weights of a profile, by part; only the parts above zero"""
    known = profiles(settings)
    try:
        return known[name]
    except KeyError:
        raise KeyError(
            f"There is no profile named {name!r}: the profiles are {', '.join(sorted(known))}"
        ) from None
