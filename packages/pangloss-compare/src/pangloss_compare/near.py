"""The statements a statement is compared with through NEAR ENTITIES (implementation_docs/spaces-and-comparison-plan.md,
step 6.4, as the user decided it: "6.4, the entities measured"):

    await searched(told, profile=..., k=..., floor=..., see_unpublished=..., types_of=...) -> Searched
    candidates(named, searched, own=..., by_rule=..., most=...) -> (list[NearPair], more)
    substituted(other, pair) -> Told                       # the other read with each X' as the X it is near
    shown(verdict) -> bool                                 # neither `two` nor `nothing`

For each identifying field (its root name) of the statement and each real entity X it names there (as `reading`
gives them: no stand-in, nothing below a guess not confirmed, a merged entity as the one kept), the entities X'
nearest X by a profile of `pangloss-vectors` that knows names (`COMPARE_PROFILE`, `settings.near_profile`):
`pangloss_vectors.nearest(of=X, types=<the concrete entity classes that field can reach>, k=COMPARE_NEAR_K)`, those
scoring `COMPARE_NEAR` or more. Then the rule of 6.3 with X' in X's place (`pairs.naming`: statements of related
classes naming X' in the same identifying field, that the reader may see, a merge followed), less the statement
itself and every pair by rule. At most `COMPARE_MOST_PAIRS`, those through the nearest entity first, then by id
(`more`: some were cut), before any verdict. The verdict (`maths.verdict`) is of the statement and the other with
each X' read as the X it is near (in its fields and in `prescribed.by`/`to`); a pair is given only where the relation
is neither `two` nor `nothing`. Each such pair is conditional: "one event if X and X' are one".

Only identifying entities (the reason `"rule"` of 6.3); nothing through whom a prescription is to (`"addressee"`).

**What a search answers** (`Searched.state`): `ok`; `pending` (the profile not built yet, or an entity with no
vector yet) and `rebuild_due` (the profile's vectors not of the dimension its parts make today), as `nearest` says
them, the worst of the searches (`rebuild_due`, then `pending`): a search that is not ok gives no near entities, the
others still do. An entity of a class without vectors (`pangloss_vectors.meta.included`) is not searched from.

Nothing is written. Neither `pangloss-vectors` nor `pangloss-reconcile` is imported unless installed."""

import dataclasses
from collections.abc import Callable, Iterable, Mapping, Sequence
from typing import Any

from pangloss_compare import maths, meta, reading

NEAR = "near"
OK, PENDING, REBUILD_DUE, NONE = "ok", "pending", "rebuild_due", "none"

# (the worse of two states: a search that is not ok says why there may be none)
_WORSE = {OK: 0, PENDING: 1, REBUILD_DUE: 2}

# Where the maths says the two are not one thing: not given through near entities
APART = ("two", "nothing")


@dataclasses.dataclass(frozen=True)
class Through:
    """A reason of a pair through near entities: the statement names `entity` (X) in `field` (the root name), the
    other names `near` (X') there, and X' is near X with this score"""

    field: str
    entity: str
    near: str
    score: float


@dataclasses.dataclass(frozen=True)
class NearPair:
    """A statement found through near entities, and each reason"""

    id: str
    by: tuple[Through, ...]

    @property
    def best(self) -> float:
        return max(t.score for t in self.by)


@dataclasses.dataclass(frozen=True)
class Searched:
    """What the searches found: of each root field, of each X' found, each X it is near and the score (nearest
    first, then by X's id); and the state (the module's docstring)"""

    near: Mapping[str, Mapping[str, tuple[tuple[str, float], ...]]] = dataclasses.field(
        default_factory=dict
    )
    state: str = OK


def worse(a: str, b: str) -> str:
    return a if _WORSE[a] >= _WORSE[b] else b


# --- the classes searched ----------------------------------------------------------------------------------


def _entity_classes(definition: Any) -> list[str]:
    """The concrete entity classes a relation reaches, through the wrappers on its way, as search reaches them
    (`pangloss_models.search.leaf_classes`, the walk of `reaches_an_entity`)"""
    from pangloss_models import Entity, ModelRegistry
    from pangloss_models.exceptions import PanglossSearchError
    from pangloss_models.search import leaf_classes
    from pangloss_models.utils import get_concrete_types

    found: list[type] = []
    for option in definition.type_options:
        reached: list[type] = []
        try:
            leaf_classes(definition.field_name, option, reached, [False])
        except PanglossSearchError:
            continue
        found.extend(reached)
    names: set[str] = set()
    for cls in found:
        if not isinstance(cls, type):
            continue
        for concrete in get_concrete_types(cls):
            if (
                isinstance(concrete, type)
                and issubclass(concrete, Entity)
                and not concrete._meta.abstract
                and ModelRegistry._model_dict.get(concrete.__name__) is concrete
            ):
                names.add(concrete.__name__)
    return sorted(names)


def types_of(told: maths.Told, root: str) -> tuple[list[str], list[str]]:
    """The concrete entity classes an X' of the identifying field `root` may be of: those the fields that count as
    `root` reach, in the statement's class and in each related class; and those fields, as `Model.field` (what
    `nearest` is given as `asked`, which says a class is asked as itself where a field holds it so:
    `pangloss_vectors.by_use`)"""
    from pangloss_compare.pairs import _related

    known = reading.Known()
    classes: set[str] = set()
    asked: list[str] = []
    for name in dict.fromkeys([told.type, *_related(told.type, known.compared)]):
        if root not in known.compared.get(name, meta.DEFAULT).identifying:
            continue
        model = reading._model(name)
        fields = getattr(getattr(model, "_meta", None), "fields", None)
        if fields is None:
            continue
        for edge, counted in known.shape(name).fields.items():
            definition = fields.relation_fields.get(edge)
            if counted != root or definition is None:
                continue
            reached = _entity_classes(definition)
            if reached:
                classes.update(reached)
                asked.append(f"{name}.{edge}")
    return sorted(classes), sorted(set(asked))


# --- the searches ------------------------------------------------------------------------------------------


async def searched(
    told: maths.Told,
    *,
    profile: str,
    k: int,
    floor: float,
    see_unpublished: bool,
    classes: Mapping[str, str],
    types: Callable[[maths.Told, str], tuple[list[str], list[str]]] = types_of,
) -> Searched:
    """The near entities of each identifying entity of `told` (the module's docstring). `classes`: the class of
    each of its entities, by id (an entity whose class has no vectors, or is not given, is not searched from). Each
    search is `nearest`'s own read transaction"""
    from pangloss_vectors import meta as vectors_meta
    from pangloss_vectors.search import nearest

    rules = meta.compare_meta(told.type)
    if rules is None:
        return Searched()
    state = OK
    found: dict[str, dict[str, list[tuple[str, float]]]] = {}
    for root in dict.fromkeys(rules.identifying):
        entities = sorted(told.fields.get(root, ()))
        if not entities:
            continue
        reach, asked = types(told, root)
        if not reach:
            continue
        for entity in entities:
            kind = classes.get(entity)
            if kind is None or not vectors_meta.included(kind):
                continue
            answer = await nearest(
                entity,
                profile=profile,
                types=reach,
                asked=asked,
                k=k,
                see_unpublished=see_unpublished,
            )
            if answer.status != OK:
                state = worse(state, answer.status)
                continue
            for hit in answer.hits:
                if hit.score < floor or hit.id == entity:
                    continue
                found.setdefault(root, {}).setdefault(hit.id, []).append(
                    (entity, float(hit.score))
                )
    return Searched(
        {
            root: {
                near: tuple(sorted(through, key=lambda t: (-t[1], t[0])))
                for near, through in by_near.items()
            }
            for root, by_near in found.items()
        },
        state,
    )


# --- the pure part -----------------------------------------------------------------------------------------


def candidates(
    named: Mapping[str, Iterable[tuple[str, str]]],
    near: Mapping[str, Mapping[str, Sequence[tuple[str, float]]]],
    *,
    own: str,
    by_rule: Iterable[str],
    most: int,
) -> tuple[list[NearPair], bool]:
    """The pairs through near entities: of the statements `named` (by id, each `(field, X')` it names, `pairs.naming`)
    those that are not `own` nor a pair by rule, each with every `(field, X, X', score)` it is reached through; at
    most `most`, the nearest-scored first, then by id; and whether some were cut"""
    left_out = {own, *by_rule}
    found: list[NearPair] = []
    for id, names in named.items():
        if id in left_out:
            continue
        by = sorted(
            {
                Through(field, entity, other, score)
                for field, other in names
                for entity, score in near.get(field, {}).get(other, ())
            },
            key=lambda t: (-t.score, t.field, t.entity, t.near),
        )
        if by:
            found.append(NearPair(id, tuple(by)))
    found.sort(key=lambda p: (-p.best, p.id))
    return found[:most], len(found) > most


def substituted(other: maths.Told, pair: NearPair) -> maths.Told:
    """The other statement with each X' it is reached through read as its X (in its fields, and in what is
    prescribed by and to); an X' near several X as the nearest of them (the first of `pair.by` that names it)"""
    as_x: dict[str, str] = {}
    for through in pair.by:
        as_x.setdefault(through.near, through.entity)

    def read(ids: frozenset[str]) -> frozenset[str]:
        return frozenset(as_x.get(id, id) for id in ids)

    prescribed = other.prescribed
    if prescribed is not None:
        prescribed = dataclasses.replace(
            prescribed, by=read(prescribed.by), to=read(prescribed.to)
        )
    return dataclasses.replace(
        other,
        fields={name: read(ids) for name, ids in other.fields.items()},
        prescribed=prescribed,
    )


def shown(verdict: maths.Verdict) -> bool:
    """A pair through near entities is given only where the two may be one thing: neither `two` nor `nothing`"""
    return verdict.relation not in APART
