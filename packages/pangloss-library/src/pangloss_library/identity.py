"""Claims that two entities are one (implementation_docs/entity-identity.md, part 2).

`IdentityClaim()` marks the relation of a statement that names the entities said to be the same:

    class SameAs(Statement):
        entities: Annotated[list[Person], MinLen(2), MaxLen(2), IdentityClaim()]

It is a `KeepOnMerge()`: if the two are later merged, the statement still names both (the second as "merged into" the
first), and does not come to say that an entity is itself. The interface module of this package reads it: an
entity's page lists what it is said to be the same as, with the statements that say so.

Nothing reads through these claims unless it is asked to (`pangloss_library.clusters`): the entities joined by
claims are a **cluster**, `await cluster(entity)`, and a search can ask for any entity of one:

    Birth.search(Birth.Where(person=Person.Where(same_as_=a)))
    {"type": "Birth", "where": {"person": {"where": {"$same_as": "<id of A>"}}}}
    {"$same_as": {"id": "<id of A>", "steps": "one"}}        # only what a statement says of A itself

`SameEntity[Person]` (`pangloss_library.models`) is a ready-made statement with such a relation.
"""

from typing import Any
from uuid import UUID

from pangloss_models import KeepOnMerge, PanglossSearchError
from pangloss_models.search import Checked, Extension, register_extension
from pangloss_models.search_where import WhereExtension, where_extensions

KEY = "$same_as"


class IdentityClaim(KeepOnMerge):
    """On a relation to entities: the statement claims that the entities it names are one and the same"""

    def export(self) -> dict[str, Any]:
        # (said for a project's own subclass too: the interface asks this, not the name)
        return {**super().export(), "identityClaim": True}


def check_same_as(model: type, value: Any, top: bool, path: str) -> Checked:
    """`$same_as` on the pattern of an entity: it is the entity named, or of its cluster"""
    field = f"{path}{KEY}"
    steps = "all"
    if isinstance(value, dict) and "steps" in value:
        steps = value["steps"]
    entity = value.get("id") if isinstance(value, dict) else value
    entity = getattr(entity, "id", entity)
    try:
        id = str(UUID(str(entity)))
    except ValueError:
        raise PanglossSearchError(
            f"{field}: needs the id of an entity (or {{'id': ..., 'steps': 'one'}}), not {value!r}"
        ) from None
    if steps not in ("all", "one"):
        raise PanglossSearchError(
            f"{field}: 'steps' is 'all' (the whole cluster) or 'one' (only what is said of the entity itself), "
            f"not {steps!r}"
        )
    # (the cluster is read once, before the search is made a query: `Checked.prepare`)
    found: list[str] = []
    read = False

    async def prepare() -> None:
        nonlocal read
        from pangloss_library.clusters import NoSuchEntity, cluster

        try:
            found[:] = (await cluster(id, steps)).ids()
        except NoSuchEntity:
            found[:] = []
        read = True

    def cypher(compiler: Any, var: str) -> str:
        if not read:
            raise PanglossSearchError(
                f"{field}: a cluster is read when a search is run, and cannot be part of a rule"
            )
        return f"{var}.id IN {compiler.param(list(found))}"

    return Checked(cypher, "an entity of the cluster", prepare)


def install() -> None:
    """(At import) the key of a search, and the `same_as_` field of every entity's `Where`"""
    register_extension(Extension(KEY, check_same_as, kinds=("entity",)))
    if not any(e.name == "same_as_" for e in where_extensions):
        where_extensions.append(
            WhereExtension("same_as_", KEY, UUID | str | dict, ("Entity",))
        )


install()
