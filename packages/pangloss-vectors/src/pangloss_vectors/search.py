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
many, until it has asked for more than twice the vectors the profile's state counts, or 4096. A small database asks
once.
"""

import dataclasses
from collections.abc import Mapping
from typing import Any, Literal

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


def search_query(index: str) -> str:
    """The query of a search of the vector index `index` (a name `store` made, written into the text): the profile's
    generation in use, the nearest `$fetch` of the index in it, each but `$of` matched to its head by id and kept if
    the reader may look through it (`fragments.listed`: not deleted, published unless `$see_unpublished`, not merged
    into another), the first `$k`"""
    from pangloss_core import backend

    current = backend.current()
    search = current.dialect.vector_search(
        index, "$fetch", "$vector", carry=["generation"]
    )
    return (
        f"MATCH (s:{store.PROFILE_STATE} {{profile: $profile}}) "
        "WITH s.generation AS generation "
        f"{search} "
        "WITH node, score, generation "
        "WHERE node.generation = generation AND node.of <> $of "
        "MATCH (item:HeadNode {id: node.of}) "
        f"WHERE {current.fragments.listed('item')} "
        "RETURN item.id AS id, item.type AS type, score "
        "ORDER BY score DESC, item.id LIMIT $k"
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


async def nearest(
    of: str | None = None,
    *,
    vector: Mapping[str, Vector] | None = None,
    profile: str = DEFAULT_PROFILE,
    group: str | None = None,
    k: int = 10,
    see_unpublished: bool = False,
) -> Nearest:
    """The `k` items nearest the item `of` (by its vectors in use; an entity merged into another answers for its
    survivor), or nearest `vector` (the vectors of parts, by name), by the profile's weights; never the item itself.
    Narrowed to a group (a class with `VectorsMeta(searchable=True)`) if one is named, and refused (`NotAGroup`) if
    the name is not one's. Unpublished documents only with `see_unpublished`"""
    if (of is None) == (vector is None):
        raise ValueError("A search is from an item (`of`) or from a vector, not both")
    if isinstance(k, bool) or not isinstance(k, int) or k < 1:
        raise ValueError(f"A search asks for 1 or more items, not {k!r}")
    lay = store.layout(profile)
    query = search_query(_index(lay, group))
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
        fetch = k * overfetch() + (1 if item else 0)
        enough = min(2 * state.count + 1, MOST_FETCHED)
        while True:
            hits = await _ask(
                tx,
                query,
                profile=profile,
                fetch=fetch,
                vector=query_vector,
                of=item,
                k=k,
                see_unpublished=see_unpublished,
            )
            if len(hits) >= k or fetch >= enough:
                return Nearest("ok", hits)
            fetch = min(fetch * FETCH_GROWTH, enough)

    return await search()
