"""Claims that two entities are one (implementation_docs/entity-identity.md, part 2).

`IdentityClaim()` marks the relation of a statement that names the entities said to be the same:

    class SameAs(Statement):
        entities: Annotated[list[Person], MinLen(2), MaxLen(2), IdentityClaim()]

It is a `KeepOnMerge()`: if the two are later merged, the statement still names both (the second as "merged into" the
first), and does not come to say that an entity is itself. The interface module of this package reads it: an
entity's page lists what it is said to be the same as, with the statements that say so. (A derived rule over it,
for reading through identities, is not built yet.)

`SameEntity[Person]` (`pangloss_library.models`) is a ready-made statement with such a relation.
"""

from typing import Any

from pangloss_models import KeepOnMerge


class IdentityClaim(KeepOnMerge):
    """On a relation to entities: the statement claims that the entities it names are one and the same"""

    def export(self) -> dict[str, Any]:
        # (said for a project's own subclass too: the interface asks this, not the name)
        return {**super().export(), "identityClaim": True}
