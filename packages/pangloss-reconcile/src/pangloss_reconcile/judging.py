"""A project's own judge in the worker that suggests (step 10.5c' of implementation_docs/similarity-build-plan.md;
implementation_docs/reconcile.md, "A project's judge"). No database in it: what the judge is given (`Asked`), what it
answers (`Unchanged`, `Leave`, `Suggest`), the answer's shape checked and made a decision (`checked`), and the judge
awaited under its timeout (`call`). The worker (`suggesting.judged`) builds `Asked`, and tries what a `Suggest` would
write before it writes it.

`RECONCILE_SUGGEST_WITH = "package.module:function"` names the judge. The worker calls it once for each stand-in
whose place takes a suggestion and that is not tried with today's digest, after the candidates are found and
`suggest.decide_for` has decided, before anything is written and outside any transaction, with one argument, an
`Asked`. It answers:

- `None` or `Unchanged()`: the decision stands;
- `Leave()`: nothing is suggested for this mention (noted as tried, as a decision of nothing is);
- `Suggest(alternatives=[(reference, weight), ...], fields={...})`: its own alternatives, entities by
  `{"type", "id"}` with weights above 0 (any entity the place takes: not only the candidates), which the worker makes
  whole per cent of (`suggest.percentages`, heaviest first; where the place takes one entity, the heaviest alone), and
  values for further fields of the suggestion's class (`RECONCILE_SUGGEST_AS`), never one the worker fills
  (`WORKER_FIELDS`).

Anything else, or a `Suggest` of the wrong shape, is a `BadAnswer`; a judge that raises, does not answer within
`RECONCILE_SUGGEST_TIMEOUT` seconds, or answers badly fails **for that mention only**: it is left as it is, not noted
as tried, and the built-in decision is not used in its place."""

import asyncio
import dataclasses
import inspect
import math
from collections.abc import Callable, Mapping, Sequence
from typing import Any, Literal
from uuid import UUID

from pangloss_reconcile.suggest import Alternative, Decision, percentages

__all__ = [
    "Asked",
    "BadAnswer",
    "Leave",
    "Suggest",
    "TimedOut",
    "Unchanged",
    "Verdict",
    "WORKER_FIELDS",
    "call",
    "checked",
]

# The fields of a suggestion the worker fills: a judge's `Suggest.fields` may name none of them
WORKER_FIELDS = (
    "type",
    "id",
    "text",
    "uris",
    "identified_by",
    "toolchain_version",
    "target",
    "edge_properties",
)

# The most alternatives a suggestion may have (each has at least 1 per cent)
MOST_ALTERNATIVES = 100

type Shape = Literal["alternatives", "one"]


@dataclasses.dataclass(frozen=True)
class Asked:
    """What a judge is given about one stand-in: plain data only (dicts, lists, text, numbers), made for this call.

    - `stand_in`: `{"id", "label", "stood_for", "uris", "place", "held_by"}`: the class it stands for, its URIs, the
      names of the fields from the head down to it, and the class of the node that holds it;
    - `document`: the head as the worker read it, as Python names it (`view.model_dump(mode="json",
      by_alias=False)`);
    - `candidates`: as the reconcile dialog would be answered (the first `candidates.DISPLAYED`, best first), each
      `{"id", "type", "label", "score", "scores", "shared"}`, `scores` by part, `shared` the entities it is named with
      (`{"id", "type", "label", "documents"}`, as the stored route answers them);
    - `decision`: what the worker decided (`{"alternatives": [{"id", "type", "percent"}], "reason"}`; no alternatives:
      nothing would be suggested, and why: `none`, `low`, `new`);
    - `takes`: `{"shape", "classes"}`: `"alternatives"` (a suggestion over weighted alternatives) or `"one"` (of one
      entity), and the names of the classes of entity the place takes (what a `Suggest` may name)"""

    stand_in: dict[str, Any]
    document: dict[str, Any]
    candidates: list[dict[str, Any]]
    decision: dict[str, Any]
    takes: dict[str, Any]


@dataclasses.dataclass(frozen=True)
class Unchanged:
    """The worker's decision stands (as `None` does)"""


@dataclasses.dataclass(frozen=True)
class Leave:
    """Nothing is suggested for this mention: it is left, and noted as tried"""


@dataclasses.dataclass(frozen=True)
class Suggest:
    """The judge's own alternatives: `(reference, weight)`, a reference `{"type", "id"}` of an entity the place takes
    (among the candidates or not), a weight a number above 0; and `fields`, values for further fields of the
    suggestion's class (none of `WORKER_FIELDS`)"""

    alternatives: Sequence[tuple[Mapping[str, Any], float]]
    fields: Mapping[str, Any] = dataclasses.field(default_factory=dict)


class TimedOut(Exception):
    """A judge that did not answer within its timeout (`call`)"""


class BadAnswer(ValueError):
    """A judge's answer that is not one of the three, or a `Suggest` of the wrong shape: said with what was wrong"""


@dataclasses.dataclass(frozen=True)
class Verdict:
    """What is written for a stand-in after the judge: the decision (no alternatives: nothing), the further fields of
    the suggestion, and whether the judge replaced the worker's decision (`Suggest` or `Leave`)"""

    decision: Decision
    fields: dict[str, Any] = dataclasses.field(default_factory=dict)
    by_judge: bool = False


def _weight(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    value = float(value)
    return value if math.isfinite(value) and value > 0 else None


def _reference(value: Any, n: int) -> tuple[str, str]:
    if not isinstance(value, Mapping):
        raise BadAnswer(
            f"Suggest's alternative {n}: the reference is a mapping {{'type', 'id'}}, not {value!r}"
        )
    type_name, id = value.get("type"), value.get("id")
    if not isinstance(type_name, str) or not type_name:
        raise BadAnswer(
            f"Suggest's alternative {n}: the reference has no 'type' (the name of the entity's class): {dict(value)!r}"
        )
    if id is None:
        raise BadAnswer(
            f"Suggest's alternative {n}: the reference has no 'id': {dict(value)!r}"
        )
    try:
        parsed = id if isinstance(id, UUID) else UUID(str(id))
    except ValueError:
        raise BadAnswer(
            f"Suggest's alternative {n}: the reference's 'id' is no UUID: {id!r}"
        ) from None
    return type_name, str(parsed)


def checked(answer: Any, shape: Shape, decision: Decision) -> Verdict:
    """The judge's `answer` made what is written for a stand-in whose place takes `shape`, the worker having decided
    `decision`. `BadAnswer`, saying what was wrong, for another type, or a `Suggest` with no alternative, more than
    `MOST_ALTERNATIVES`, an alternative that is not a pair, a reference without a type or an id (a UUID), the same
    entity twice, a weight that is not a number above 0, or `fields` that is not a mapping of names or names one of
    `WORKER_FIELDS`. Whether the entities exist and the place takes them, and whether the class has those fields, is
    not known here: the worker tries it before it writes"""
    if answer is None or isinstance(answer, Unchanged):
        return Verdict(decision)
    if isinstance(answer, Leave):
        return Verdict(Decision((), "left"), by_judge=True)
    if not isinstance(answer, Suggest):
        raise BadAnswer(
            f"A judge answers None, Unchanged(), Leave() or Suggest(...), not {type(answer).__name__}: {answer!r}"
        )
    given = answer.alternatives
    if isinstance(given, (str, bytes, Mapping)) or not isinstance(given, Sequence):
        raise BadAnswer(
            f"Suggest's alternatives are a list of (reference, weight), not {given!r}"
        )
    if not given:
        raise BadAnswer("Suggest has no alternative: answer Leave() to suggest nothing")
    if len(given) > MOST_ALTERNATIVES:
        raise BadAnswer(
            f"Suggest has {len(given)} alternatives: at most {MOST_ALTERNATIVES} (each has at least 1 per cent)"
        )
    pairs: list[tuple[str, str, float]] = []
    seen: set[str] = set()
    for n, pair in enumerate(given, start=1):
        if isinstance(pair, (str, bytes, Mapping)) or not isinstance(pair, Sequence):
            raise BadAnswer(
                f"Suggest's alternative {n} is a pair (reference, weight), not {pair!r}"
            )
        if len(pair) != 2:
            raise BadAnswer(
                f"Suggest's alternative {n} is a pair (reference, weight), not {len(pair)} values: {pair!r}"
            )
        type_name, id = _reference(pair[0], n)
        weight = _weight(pair[1])
        if weight is None:
            raise BadAnswer(
                f"Suggest's alternative {n} ({type_name} {id}): the weight is a number above 0, not {pair[1]!r}"
            )
        if id in seen:
            raise BadAnswer(
                f"Suggest names {type_name} {id} twice: each entity once, with its weight"
            )
        seen.add(id)
        pairs.append((type_name, id, weight))
    fields = answer.fields
    if not isinstance(fields, Mapping):
        raise BadAnswer(
            f"Suggest's fields are a mapping of field names to values, not {fields!r}"
        )
    for name in fields:
        if not isinstance(name, str):
            raise BadAnswer(f"Suggest's fields are named by text, not {name!r}")
    workers = sorted(name for name in fields if name in WORKER_FIELDS)
    if workers:
        raise BadAnswer(
            f"Suggest's fields name {', '.join(workers)}, which the worker fills ({', '.join(WORKER_FIELDS)}): "
            "give only further fields of the suggestion's class"
        )
    # (heaviest first; equal weights in the judge's order)
    ordered = sorted(pairs, key=lambda each: -each[2])
    if shape == "one":
        type_name, id, _ = ordered[0]
        alternatives: tuple[Alternative, ...] = (Alternative(id, type_name, 100),)
    else:
        shares = percentages([weight for _, _, weight in ordered])
        alternatives = tuple(
            Alternative(id, type_name, percent)
            for (type_name, id, _), percent in zip(ordered, shares, strict=True)
        )
    return Verdict(Decision(alternatives, "judged"), dict(fields), by_judge=True)


async def call(function: Callable[[Asked], Any], asked: Asked, timeout: float) -> Any:
    """The judge's answer to `asked`, within `timeout` seconds (`TimedOut` otherwise: a `TimeoutError` the judge
    raises itself, of a call of its own, is raised as it is). An async function is
    awaited (and cancelled at the timeout); a sync one is run in a thread, so that the loop, and the renewal of the
    worker's lease and claims, goes on meanwhile (a thread cannot be stopped: one past its timeout runs on, and its
    answer is not used). What a sync function gives that can be awaited is awaited too"""
    limit = asyncio.timeout(timeout)
    try:
        async with limit:
            if inspect.iscoroutinefunction(function):
                answer = await function(asked)
            else:
                answer = await asyncio.to_thread(function, asked)
            if inspect.isawaitable(answer):
                answer = await answer
    except TimeoutError:
        if limit.expired():
            raise TimedOut(f"no answer within {timeout:g} s") from None
        raise
    return answer
