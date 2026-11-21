"""The nearest items to one, or to a vector: through the vector index of a profile (or of a profile and a group), in
the generation the profile's state says is in use, cut to what the reader may see
(implementation_docs/similarity-build-plan.md, step 2.4).

The query vector is made as the stored ones are (`store.Layout.combine` of today's layout of the profile), so the
score of a hit is the cosine of the two combined vectors: the weighted mean of the cosines of the parts.

**Asked again while short.** The index is asked for `k × VECTORS_OVERFETCH` (one more for the item itself). Some of
what it gives is not a hit: of the other generation, during a rebuild (both are in the index until the old one is
dropped); of what the reader may not see; and, on Memgraph, nodes deleted since they were indexed, which keep their
places among the nearest until the database collects them (about 30 s: notes/similarity-evaluation/deleted_in_index.py)
and are dropped by `Dialect.vector_search`. So while there are fewer than `k` hits it asks again for four times as
many, until it has asked for more than twice the vectors the profile's state counts (those in use, and those deleted
in place since it was built, which on Memgraph may still hold places in the index: `ProfileState.removed`), or 4096.
A small database asks once.

**Narrowed to classes** (`nearest(types=...)`, step 7a.4): a filter of the whole index by class finds too few (the
nearest of an item in it are items of its own kind: notes/similarity-evaluation/field_types_recall.txt), so the
classes asked for are searched in two ways, merged by score (both give the cosine), each item once, the first `k`
(`narrowed` says which): a group all of whose classes with vectors are among them, through the group's own index, as
above; every other class by an **exact scan** of its profile vectors in the database (`scan_query`), scored by the
dialect's cosine (`Dialect.vector_cosine`). The scan is linear in the vectors of its classes (on Memgraph about
6.5 µs a vector: 1,800 in 13 ms, 82,000 in 0.53 s), so a large class that is searched often should be a group. Being
exact, it is asked again while short only for what the reader may not see, and not once it has had every vector of
its classes (`scan_count_query`, asked when it is first short).

**Classes by use** (step 7a.5, `by_use.py`): narrowed to a class that another is below only by use (`Role`, above a
typology's `RoleType`), a hit of the other is kept only where a relation that counts points at it (`_used`, in the end
both ways share). Nothing stored says it, and the clause is in the query only when the request has such a class.
"""

import dataclasses
from collections.abc import Collection, Mapping
from typing import Any, Literal

from pangloss_models import Document, Entity, ModelRegistry

from pangloss_vectors import meta, store
from pangloss_vectors.parts import DEFAULT_PROFILE, Vector
from pangloss_vectors.settings import overfetch

type Status = Literal["ok", "pending", "rebuild_due"]

# (the most a search asks the index for, however short it is)
MOST_FETCHED = 4096
# (how many times as many it asks for again)
FETCH_GROWTH = 4


@dataclasses.dataclass(frozen=True, slots=True)
class Hit:
    """An item near the one searched from: its id, class and the cosine of their vectors (1, the same)"""

    id: str
    type: str
    score: float


@dataclasses.dataclass(frozen=True, slots=True)
class Nearest:
    """What a search found. `status`: `"ok"`; `"pending"` (the item has no vector yet, or the profile has not been
    built), or `"rebuild_due"` (the profile's vectors in use are not of the dimension its parts make today); `hits`,
    nearest first, only with `"ok"`"""

    status: Status
    hits: list[Hit] = dataclasses.field(default_factory=list)


class NotAGroup(ValueError):
    """A search narrowed to a class that is not a group (`VectorsMeta(searchable=True)`), which has no index"""


def search_query(index: str, excluding: bool = False, by_use: bool = False) -> str:
    """The query of a search of the vector index `index` (a name `store` made, written into the text): the profile's
    generation in use, the nearest `$fetch` of the index in it, each but `$of` matched to its item by id (a head, or a
    document nested in one) and kept if the reader may look through it (`fragments.listed`, by its head: not deleted,
    published unless `$see_unpublished`, not merged into another), the first `$k`. With `excluding`, an item whose class
    is among `$excluded` (`meta.excluded`) is no hit either: a class left out since the vectors in use were built
    keeps them until the rebuild (and without it, the query is the one it has always been). With `by_use`, an item
    whose class is among `$by_use_types` is a hit only where something uses it as a class it is by use (`_used`)"""
    from pangloss_core import backend

    search = backend.current().dialect.vector_search(
        index, "$fetch", "$vector", carry=["generation"]
    )
    return (
        f"MATCH (s:{store.PROFILE_STATE} {{profile: $profile}}) "
        "WITH s.generation AS generation "
        f"{search} "
        "WITH node, score, generation "
        "WHERE node.generation = generation AND node.of <> $of "
        + _hits("AND NOT item.type IN $excluded " if excluding else "", by_use)
    )


def scan_query(by_use: bool = False) -> str:
    """The query of an exact scan of the profile vectors of the classes `$types` (no vector index: step 7a.4): those
    of the generation in use, but `$of`'s, each scored by the cosine of its vector and `$vector`
    (`Dialect.vector_cosine`, the number the index gives), the best `$fetch`, then matched to their items and cut to
    what the reader may see as `search_query` does, the first `$k`. An item whose class is not among `$types` (it
    changed since its vector was written) is no hit.

    It finds the vectors of each class by the index on `PGProfileVector(type)`, and reads each once: the rest of the
    conditions are after a `WITH`, which on Memgraph keeps the planner from choosing the index on `generation`
    instead, which reads the whole generation once for each class (notes/similarity-evaluation/field_types_recall.txt).
    Linear in the vectors of the classes: about 6.5 µs a vector on Memgraph. `by_use` as for `search_query`"""
    from pangloss_core import backend

    cosine = backend.current().dialect.vector_cosine("v.vector", "$vector")
    return (
        f"MATCH (s:{store.PROFILE_STATE} {{profile: $profile}}) "
        "WITH s.generation AS generation "
        "UNWIND $types AS t "
        f"MATCH (v:{store.PROFILE_VECTOR} {{type: t}}) "
        "WITH v, generation "
        "WHERE v.profile = $profile AND v.generation = generation AND v.of <> $of "
        f"WITH v AS node, {cosine} AS score "
        "ORDER BY score DESC, node.of LIMIT $fetch "
        + _hits("AND item.type IN $types ", by_use)
    )


def scan_count_query() -> str:
    """How many profile vectors of the classes `$types` there are in the generation in use: what a scan could give
    at most, so that one short of `$k` hits is not asked again when it has had them all"""
    return (
        f"MATCH (s:{store.PROFILE_STATE} {{profile: $profile}}) "
        "WITH s.generation AS generation "
        "UNWIND $types AS t "
        f"MATCH (v:{store.PROFILE_VECTOR} {{type: t}}) "
        "WITH v, generation "
        "WHERE v.profile = $profile AND v.generation = generation "
        "RETURN count(v) AS count"
    )


def _hits(condition: str, by_use: bool = False) -> str:
    """The end of a search: each of `node` (a profile vector), with its `score`, matched to its item by id and kept
    if the reader may look through it and `condition` holds (`AND ...`), the first `$k`; with `by_use`, `_used` too"""
    from pangloss_core import backend

    fragments = backend.current().fragments
    head = fragments.head_of("item", "item_head")
    return (
        "MATCH (item:PGIndexableNode {id: node.of}) "
        f"{head.match} "
        "WITH node, score, item, item_head "
        # (a nested document whose head is not there is no hit)
        "WHERE (item.head_node_id IS NULL OR item_head IS NOT NULL) "
        f"AND {fragments.listed('item', head)} "
        f"{condition}"
        + (_used() if by_use else "")
        + "RETURN item.id AS id, item.type AS type, score "
        "ORDER BY score DESC, item.id LIMIT $k"
    )


def _used() -> str:
    """(after the conditions of `_hits`) an item of a class among `$by_use_types` is kept only if a relation that
    counts (`$by_use`: `{type, source, edge}`, `by_use.parameters`) points at it by its forward edge, from a node the
    reader may look through by its head as the item is (`fragments.listed`), not the item itself, not a relation the
    server computes nor one of a class whose references do not count. Asked for those items only: for the others the
    subquery is given no row. (A `CALL` that counts, as `fragments.uses_of` does, which both backends run; about the
    cost of an `EXISTS` on Memgraph: notes/similarity-evaluation/used_as_trial.py)"""
    from pangloss_core import backend

    fragments = backend.current().fragments
    head = fragments.head_of("user", "user_head")
    return (
        "CALL (item) { "
        "WITH item WHERE item.type IN $by_use_types "
        "MATCH (item)<-[use]-(user:PGIndexableNode) "
        f"WHERE {fragments.forward('use')}{fragments.reference('use')} "
        "AND any(u IN $by_use WHERE u.type = item.type AND u.source = user.type "
        "AND u.edge = type(use)) "
        f"{head.match} "
        f"WITH item, user, user_head, {head} AS holder "
        "WHERE (user.head_node_id IS NULL OR user_head IS NOT NULL) "
        f"AND {fragments.listed('user', head)} "
        f"AND holder <> item{fragments.counted('holder')} "
        "RETURN count(user) AS uses "
        "} "
        "WITH item, score, uses "
        "WHERE uses > 0 OR NOT item.type IN $by_use_types "
    )


async def _ask(tx: Any, query: str, **parameters: Any) -> list[Hit]:
    """One query of the index (a function of its own, so that a test can count them)"""
    result = await tx.run(query, **parameters)
    return [
        Hit(id=str(r["id"]), type=r["type"], score=float(r["score"]))
        async for r in result
    ]


def _index(lay: store.Layout, group: str | None) -> str:
    if group is None:
        return lay.index_name
    known = meta.groups()
    if group not in known:
        raise NotAGroup(
            f"{group!r} is not a group a search can be narrowed to: the groups are "
            f"{', '.join(known) or 'none'} (a class with VectorsMeta(searchable=True))"
        )
    return lay.group_index_name(group)


@dataclasses.dataclass(frozen=True, slots=True)
class Narrowed:
    """How a search narrowed to classes is made: `groups`, each asked through its own vector index, and `scanned`,
    the classes no chosen group covers, by the exact scan (`scan_query`). Both in the order of their names"""

    groups: tuple[str, ...] = ()
    scanned: tuple[str, ...] = ()


def narrowed(types: Collection[str]) -> Narrowed:
    """How a search narrowed to these classes (concrete classes of documents or entities, by name) is made. A group
    is asked through its index when every class of it that has vectors is among them (an excluded class of the group
    need not be: its items are never hits); the fewest indexes, so a group inside a chosen one is not chosen; every
    other class asked for is scanned. A class without vectors (`meta.excluded`) is neither: it is never found"""
    from pangloss_vectors.fields import NotAClass, concrete_classes

    asked = set()
    for name in types:
        model = meta.model_named(name)
        if not (isinstance(model, type) and issubclass(model, (Document, Entity))):
            raise NotAClass(
                f"{name!r} is not a class of documents or entities: a search is narrowed to those"
            )
        asked.add(name)
    left_out = set(meta.excluded())
    wanted = asked - left_out
    candidates = []
    for group in meta.groups():
        classes = set(concrete_classes(ModelRegistry._model_dict[group])) - left_out
        if classes and classes <= wanted:
            candidates.append((group, classes))
    # (the largest first: groups are classes, so one inside another is a subset of it, and is left out)
    candidates.sort(key=lambda found: (-len(found[1]), found[0]))
    chosen: list[str] = []
    covered: set[str] = set()
    for group, classes in candidates:
        if classes - covered:
            chosen.append(group)
            covered |= classes
    return Narrowed(tuple(sorted(chosen)), tuple(sorted(wanted - covered)))


@dataclasses.dataclass(frozen=True, slots=True)
class _Way:
    """One query of a search, and what it is given besides the common parameters"""

    query: str
    parameters: Mapping[str, Any] = dataclasses.field(default_factory=dict)
    count: str | None = None
    """(a scan) the query of how many it could give at most, asked once it is short"""


def _merged(found: list[list[Hit]], k: int) -> list[Hit]:
    """The hits of several ways, each item once (at its best score), by score and then id, the first `k`"""
    if len(found) == 1:
        return found[0]
    best: dict[str, Hit] = {}
    for hits in found:
        for hit in hits:
            if hit.id not in best or hit.score > best[hit.id].score:
                best[hit.id] = hit
    return sorted(best.values(), key=lambda hit: (-hit.score, hit.id))[:k]


async def nearest(
    of: str | None = None,
    *,
    vector: Mapping[str, Vector] | None = None,
    profile: str = DEFAULT_PROFILE,
    group: str | None = None,
    types: Collection[str] | None = None,
    k: int = 10,
    see_unpublished: bool = False,
    asked: Collection[str] | None = None,
) -> Nearest:
    """The `k` items nearest the item `of` (by its vectors in use; an entity merged into another answers for its
    survivor; `of` may be a nested document's id, and the items found may be nested documents), or nearest `vector`
    (the vectors of parts, by name), by the profile's weights; never the item itself.
    Narrowed to a group (a class with `VectorsMeta(searchable=True)`) if one is named, and refused (`NotAGroup`) if
    the name is not one's; or to `types`, concrete classes of documents or entities by name (`narrowed`: through the
    index of each group they cover, and an exact scan of the rest, merged by score; `fields.NotAClass` for a name that
    is no such class's; one without vectors is never found). Unpublished documents only with `see_unpublished`.

    Narrowed either way, an item of a class that the names the search was narrowed by reach only through a class it
    is by use (a `RoleType` searched as a `Role`: `by_use.given_by_use`) is a hit only where something uses it as one.
    `asked` is those names, as a `type` and a `field` of the route give them (`Role`, `Activity.carried_out_by`): what
    `types` was made of (`type=Role` and `type=Role&type=RoleType` give the same classes, but the second asks a type as
    itself). Without it, the group, or the `types` themselves. A search that is not narrowed gives every item"""
    if (of is None) == (vector is None):
        raise ValueError("A search is from an item (`of`) or from a vector, not both")
    if isinstance(k, bool) or not isinstance(k, int) or k < 1:
        raise ValueError(f"A search asks for 1 or more items, not {k!r}")
    if group is not None and types is not None:
        raise ValueError(
            "A search is narrowed to a group or to types, not both: a group's classes are types"
        )
    if types is not None and (isinstance(types, str) or not types):
        raise ValueError(
            f"A search narrowed to types names one or more classes, not {types!r}"
        )
    lay = store.layout(profile)
    # (the classes that have no vectors: a hit of one is left out, though its vectors are there until a rebuild)
    left_out = meta.excluded()
    from pangloss_vectors import by_use
    from pangloss_vectors.fields import concrete_classes

    if types is None:
        index = _index(lay, group)
        given_by_use = (
            by_use.given_by_use(
                concrete_classes(ModelRegistry._model_dict[group]),
                [group] if asked is None else asked,
            )
            if group is not None
            else []
        )
        ways = [
            _Way(
                search_query(index, excluding=bool(left_out), by_use=bool(given_by_use))
            )
        ]
    else:
        narrowing = narrowed(types)
        given_by_use = by_use.given_by_use(
            types, list(types) if asked is None else asked
        )
        ways = [
            _Way(
                search_query(
                    lay.group_index_name(name),
                    excluding=bool(left_out),
                    by_use=bool(given_by_use),
                )
            )
            for name in narrowing.groups
        ]
        if narrowing.scanned:
            ways.append(
                _Way(
                    scan_query(by_use=bool(given_by_use)),
                    {"types": list(narrowing.scanned)},
                    count=scan_count_query(),
                )
            )
    # (what the query of a class given only by use is given: nothing, and no clause, for a search without one)
    uses = by_use.parameters(given_by_use) if given_by_use else {}
    from pangloss_core import backend
    from pangloss_cypher.validate_write import survivors_of

    database = backend.current().database()

    @database.read_transaction
    async def search(tx: Any) -> Nearest:
        found = await store._states(tx)
        state = found.profiles.get(profile)
        if state is None:
            return Nearest("pending")
        if state.dimension != lay.dimension:
            return Nearest("rebuild_due")
        if of is not None:
            item = (await survivors_of(tx, [str(of)])).get(str(of), str(of))
            query_vector = lay.combine(await store.read_in(tx, item, found))
            if not any(query_vector):
                return Nearest("pending")
        else:
            # (no item has the id "": `<> null` would leave out every hit)
            item = ""
            query_vector = lay.combine(dict(vector or {}))
            if not any(query_vector):
                raise ValueError(
                    f"The vector given has nothing of the parts of the profile {profile!r} "
                    f"({', '.join(lay.weights)}): there is nothing to search by"
                )
        first = k * overfetch() + (1 if item else 0)
        enough = min(2 * (state.count + state.removed) + 1, MOST_FETCHED)
        # (each way asked again while it is short: an index for the reasons above; a scan, which is exact, only for
        # what the reader may not see, and not once it has had every vector of its classes)
        found_by_way = []
        for way in ways:
            fetch = first
            most = enough
            counted = False
            while True:
                hits = await _ask(
                    tx,
                    way.query,
                    profile=profile,
                    fetch=fetch,
                    vector=query_vector,
                    of=item,
                    k=k,
                    see_unpublished=see_unpublished,
                    excluded=left_out,
                    **uses,
                    **way.parameters,
                )
                if len(hits) >= k or fetch >= most:
                    break
                if way.count is not None and not counted:
                    counted = True
                    result = await tx.run(
                        way.count, profile=profile, types=way.parameters["types"]
                    )
                    there = [record["count"] async for record in result]
                    most = min(enough, there[0] if there else 0)
                    if fetch >= most:
                        break
                fetch = min(fetch * FETCH_GROWTH, most)
            found_by_way.append(hits)
        return Nearest("ok", _merged(found_by_way, k))

    return await search()
