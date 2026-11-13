"""Reading through claims of identity: the **cluster** of an entity (implementation_docs/entity-identity.md, part 2,
"Transitivity").

One source says A is B, another that B is C: A, B and C are a cluster. Nothing is stored of it. It is read when it is
asked for, from the statements as they are then, so a claim that is written, deleted or unpublished counts (or stops
counting) at once.

    found = await cluster(a)                 # a `Cluster`: its members, the claims that join them, what to warn of
    found = await cluster(a, steps="one")    # only what a statement says of A itself

- **What joins**: a relation marked `IdentityClaim()` between two entities, in a statement that is in no semantic
  space, in a document the reader sees. A claim inside a space (`Negative[...]`, `Hypothetical[...]`) joins nothing;
  one between two members of the cluster is given apart (`in_spaces`), named by its spaces, because it may contradict
  what joins them. What a space means is not known here.
- **Merged entities** count as what they were merged into: a claim that names B, merged into A since, is a claim
  about A (a merge leaves these relations where they are, `KeepOnMerge()`).
- **Bounded**: `MAX_STEPS` steps from the entity and `MAX_MEMBERS` members; past either, `truncated` says so.

On the server this reads the graph (a backend that runs Cypher); with the SDK it asks the API
(`/api/identity/{Type}/{id}/cluster`).
"""

from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel

MAX_STEPS = 10
"""How far from the entity a cluster is followed: a member is at most this many claims away"""

MAX_MEMBERS = 200
"""The most members read: a cluster is a few entities, and one of hundreds is a mistake in the data"""

DEFAULT_WARNING_SIZE = 5
"""From more members than this on, a cluster is `large` (the setting `IDENTITY_CLUSTER_WARNING`)"""

type Steps = Literal["all", "one"]


class _Wire(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class Ref(_Wire):
    """An entity, or a document"""

    type: str
    id: str
    label: str | None = None


class Member(Ref):
    """An entity of a cluster, other than the one asked about"""

    distance: int
    """How many claims from the entity asked about: 1 for one that a statement says is the same as it"""
    through: list[str] = Field(default_factory=list)
    """The members on the way to it (their ids, the nearest to the entity asked about first): empty at distance 1.
    "C, through B\""""


class Claim(_Wire):
    """One statement's claim that two entities are one"""

    id: str
    type: str
    label: str | None = None
    head: Ref
    """The document it is in (itself, if it is a head document)"""
    spaces: list[str] = Field(default_factory=list)
    """The semantic spaces it is in, outermost first: none for a claim that joins"""
    between: tuple[str, str]
    """The two members it is about (their ids; an entity merged since is the one it was merged into)"""
    argument: str | None = None


class Cluster(_Wire):
    entity: Ref
    """The entity asked about (the one it was merged into, if it was)"""
    steps: Steps = "all"
    members: list[Member] = Field(default_factory=list)
    """The others, the nearest first"""
    size: int = 1
    """How many entities: the members and the entity itself"""
    warning_size: int = DEFAULT_WARNING_SIZE
    large: bool = False
    """More than `warning_size` entities: one careless claim may have joined two clusters"""
    claims: list[Claim] = Field(default_factory=list)
    """The claims that join the members (those in no semantic space)"""
    in_spaces: list[Claim] = Field(default_factory=list)
    """The claims between two members that are in a semantic space: they join nothing, and may say the opposite"""
    truncated: bool = False
    """There is more of the cluster than was read (`MAX_STEPS`, `MAX_MEMBERS`)"""

    def ids(self) -> list[str]:
        """The ids of every entity of the cluster, the one asked about first"""
        return [self.entity.id, *(member.id for member in self.members)]

    def to_wire(self) -> dict[str, Any]:
        return self.model_dump(by_alias=True, mode="json")


class NoSuchEntity(LookupError):
    """There is no entity of that id (that the reader sees)"""


# ---------------------------------------------------------------------------
# What the models say
# ---------------------------------------------------------------------------


def stored_name(model: type) -> str:
    """The name a node of the class has in the database: `SameEntity`, for `SameEntity[Person]`"""
    origin = (getattr(model, "__pydantic_generic_metadata__", None) or {}).get("origin")
    return (origin or model).__name__


def claim_fields() -> dict[str, set[str]]:
    """The relations marked `IdentityClaim()`: by the stored name of each class that has one, the names of its fields"""
    from pangloss_models import ModelRegistry

    from pangloss_library.identity import IdentityClaim

    found: dict[str, set[str]] = {}
    for model in ModelRegistry.all_models().values():
        fields = getattr(getattr(model, "_meta", None), "fields", None)
        relations = getattr(fields, "relation_fields", None)
        if not isinstance(model, type) or not relations:
            continue
        for name, definition in relations.items():
            if any(isinstance(m, IdentityClaim) for m in definition.markers):
                found.setdefault(stored_name(model), set()).add(name)
    return found


def warning_size() -> int:
    from pangloss_core import settings as core_settings

    settings = core_settings.__dict__.get("SETTINGS")
    return int(getattr(settings, "IDENTITY_CLUSTER_WARNING", DEFAULT_WARNING_SIZE))


# ---------------------------------------------------------------------------
# Reading the graph
# ---------------------------------------------------------------------------


def _claims_query(edges: list[str]) -> str:
    """The claims that name the entities `$ids`, each with the other entity it names: one row for each pair"""
    from pangloss_core import backend
    from pangloss_cypher.transactions import dialect

    fragments = backend.current().fragments
    types = "|".join(fragments.field_edge(edge) for edge in sorted(edges))
    return f"""
    UNWIND $ids AS id
    MATCH (named:PGIndexableNode {{id: id}})<-[edge:{types}]-(claim)
    WHERE NOT coalesce(edge.reverse, false)
    MATCH (claim)-[other_edge:{types}]->(other:Entity)
    WHERE type(other_edge) = type(edge) AND NOT coalesce(other_edge.reverse, false) AND other.id <> id
          AND {fragments.not_deleted("other")}
    OPTIONAL MATCH (head:HeadNode {{id: claim.head_node_id}})
    WITH id, claim, type(edge) AS field, other, coalesce(head, claim) AS top
    WHERE {fragments.visible("top")}
    RETURN DISTINCT id AS named, field, claim.id AS claim, claim.type AS claim_type, claim.label AS claim_label,
           claim.argument AS argument, {dialect().meta_property("claim", "semantic_spaces")} AS spaces,
           top.id AS head, top.type AS head_type, top.label AS head_label,
           other.id AS other, other.type AS other_type, other.label AS other_label,
           other.merged_into AS other_merged_into
    """


ABSORBED = """
    UNWIND $ids AS id
    MATCH (m:PGMerge {survivor: id})
    WHERE m.state IN ['done', 'running']
    RETURN id AS survivor, m.absorbed AS absorbed
"""


def _entity_query() -> str:
    from pangloss_core import backend

    return f"""
    MATCH (e:PGIndexableNode {{id: $id}})
    WHERE e:Entity
    RETURN e.id AS id, e.type AS type, e.label AS label, e.merged_into AS merged_into,
           {backend.current().fragments.deleted("e")} AS deleted
    """


class _Reader:
    """One reading of a cluster, in one transaction"""

    def __init__(self, tx: Any, see_unpublished: bool):
        self.tx = tx
        self.see_unpublished = see_unpublished
        self.fields = claim_fields()
        self.edges = sorted({name for names in self.fields.values() for name in names})
        self.query = _claims_query(self.edges) if self.edges else ""
        # (an entity merged into another: the id of the one that stands for it, and that one)
        self.stands_for: dict[str, str] = {}
        self.known: dict[str, dict[str, Any]] = {}

    async def entity(self, id: str) -> dict[str, Any] | None:
        if id not in self.known:
            result = await self.tx.run(_entity_query(), id=id)
            rows = await result.data()
            self.known[id] = rows[0] if rows else {}
        return self.known[id] or None

    async def survivor(self, id: str) -> dict[str, Any] | None:
        """The entity that stands for the one of this id: itself, or what it was merged into (and that into...)"""
        seen: list[str] = []
        found = await self.entity(id)
        while found is not None and found["merged_into"] and len(seen) < MAX_STEPS:
            seen.append(found["id"])
            found = await self.entity(found["merged_into"])
        if found is None or found["deleted"] or found["merged_into"]:
            return None
        for each in seen:
            self.stands_for[each] = found["id"]
        return found

    async def absorbed(self, ids: list[str]) -> None:
        """Note the entities that were merged into these (and into those), which the claims may still name"""
        asked = list(ids)
        for _ in range(MAX_STEPS):
            if not asked:
                return
            result = await self.tx.run(ABSORBED, ids=asked)
            asked = []
            for row in await result.data():
                if row["absorbed"] not in self.stands_for:
                    self.stands_for[row["absorbed"]] = self.stands_for.get(
                        row["survivor"], row["survivor"]
                    )
                    asked.append(row["absorbed"])

    async def claims_of(self, ids: list[str]) -> list[dict[str, Any]]:
        """The claims that name these entities, or what was merged into them: rows with `a` and `b`, the two entities
        (as they stand now) a claim is between, and `other`, the second as it is"""
        if not self.query:
            return []
        await self.absorbed(ids)
        asked = ids + [b for b, a in self.stands_for.items() if a in ids]
        result = await self.tx.run(
            self.query, ids=asked, see_unpublished=self.see_unpublished
        )
        rows = []
        for row in await result.data():
            if row["field"] not in self.fields.get(row["claim_type"], ()):
                # (an edge of the same name that is not a claim)
                continue
            other = (
                await self.survivor(row["other"])
                if row["other_merged_into"]
                else {
                    "id": row["other"],
                    "type": row["other_type"],
                    "label": row["other_label"],
                }
            )
            a = self.stands_for.get(row["named"], row["named"])
            if other is None or other["id"] == a:
                # (deleted; or merged into the one it was said to be the same as, which the claim is the reason for)
                continue
            rows.append({**row, "a": a, "b": other["id"], "other_now": other})
        return rows


def _claim(row: dict[str, Any]) -> Claim:
    a, b = sorted((row["a"], row["b"]))
    return Claim(
        id=row["claim"],
        type=row["claim_type"],
        label=row["claim_label"],
        head=Ref(type=row["head_type"], id=row["head"], label=row["head_label"]),
        spaces=list(row["spaces"] or []),
        between=(a, b),
        argument=row["argument"] if isinstance(row["argument"], str) else None,
    )


async def read_cluster(tx: Any, id: str, steps: Steps = "all") -> Cluster:
    """The cluster of the entity, read in the transaction"""
    from pangloss_core import backend

    reader = _Reader(tx, backend.current().unpublished_visible())
    start = await reader.survivor(id)
    if start is None:
        raise NoSuchEntity(f"There is no entity {id}")
    limit = warning_size()
    members: dict[str, Member] = {}
    claims: dict[tuple[str, tuple[str, str]], Claim] = {}
    truncated = False
    frontier = [start["id"]]
    paths: dict[str, list[str]] = {start["id"]: []}
    most = 1 if steps == "one" else MAX_STEPS
    # (one step more than members are added at: for the claims among the last found, and to know if there is more)
    for step in range(1, most + 2):
        if not frontier:
            break
        found: list[str] = []
        for row in await reader.claims_of(frontier):
            claim = _claim(row)
            claims[(claim.id, claim.between)] = claim
            if claim.spaces or row["b"] in paths:
                continue
            if step > most or len(members) >= MAX_MEMBERS:
                # (it would join: there is more of the cluster than is followed. With `steps="one"` that is what was
                # asked for, and not said)
                truncated = truncated or steps == "all"
                continue
            other = row["other_now"]
            paths[row["b"]] = paths[row["a"]] + (
                [row["a"]] if row["a"] != start["id"] else []
            )
            members[row["b"]] = Member(
                type=other["type"],
                id=other["id"],
                label=other["label"],
                distance=step,
                through=paths[row["b"]],
            )
            found.append(row["b"])
        frontier = found
    inside = set(paths)
    among = [c for c in claims.values() if set(c.between) <= inside]
    nearest_first: list[Member] = sorted(
        members.values(), key=lambda m: (m.distance, m.label or "")
    )
    joining: list[Claim] = sorted(
        (c for c in among if not c.spaces), key=lambda c: c.id
    )
    apart: list[Claim] = sorted((c for c in among if c.spaces), key=lambda c: c.id)
    return Cluster(
        entity=Ref(type=start["type"], id=start["id"], label=start["label"]),
        steps=steps,
        members=nearest_first,
        size=len(members) + 1,
        warning_size=limit,
        large=len(members) + 1 > limit,
        claims=joining,
        in_spaces=apart,
        truncated=truncated,
    )


def _id(entity: Any) -> str:
    if isinstance(entity, dict):
        entity = entity.get("id")
    return str(getattr(entity, "id", entity))


def _is_server() -> bool:
    from pangloss_core import storage_of

    return bool(storage_of().capabilities.cypher)


async def _cluster_here(id: str, steps: Steps) -> Cluster:
    from pangloss_core import backend

    current = backend.current()
    database = current.database()

    @database.read_transaction
    @current.timeout_from_setting("SEARCH_TIMEOUT_SECONDS", 30)
    async def read(tx: Any) -> Cluster:
        return await read_cluster(tx, id, steps)

    return await read()


def _call(id: str, steps: Steps) -> Any:
    from pangloss_sdk.protocol import Call

    return Call("GET", f"/api/identity/{id}/cluster", params={"steps": steps})


def _answer(response: Any, id: str) -> Cluster:
    from pangloss_sdk.protocol import check

    if response.status_code == 404:
        raise NoSuchEntity(f"There is no entity {id}")
    check(response)
    return Cluster.model_validate(response.json())


async def _cluster_async(id: str, steps: Steps) -> Cluster:
    if _is_server():
        return await _cluster_here(id, steps)
    from pangloss_sdk.client import current_async_client

    return _answer(await current_async_client().send(_call(id, steps)), id)


def cluster(entity: Any, steps: Steps = "all") -> Any:
    """`await cluster(entity)`: the cluster of an entity (an id, or anything with one): the entities it is said to be
    the same as and, with `steps="all"` (the default), those they are said to be the same as, and so on; with
    `steps="one"`, only the first. Raises `NoSuchEntity`. As the models' functions are: a coroutine, or, with the
    blocking SDK (`connect(sync=True)`), the `Cluster`"""
    from pangloss_core import storage_of

    id = str(UUID(_id(entity)))
    storage = storage_of()
    if not storage.capabilities.cypher and storage.package.endswith("api_sync"):
        from pangloss_sdk.client import current_client

        return _answer(current_client().send(_call(id, steps)), id)
    return _cluster_async(id, steps)
