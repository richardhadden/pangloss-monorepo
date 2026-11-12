"""Claims that two entities are one (implementation_docs/entity-identity.md, part 2).

`IdentityClaim()` marks the relation of a statement that names the entities said to be the same:

    class SameAs(Statement):
        entities: Annotated[list[Person], MinLen(2), MaxLen(2), IdentityClaim()]

It is a `KeepOnMerge()`: if the two are later merged, the statement still names both (the second as "merged into" the
first), and does not come to say that an entity is itself. What else reads it (the section of an entity's page that
lists what it is said to be the same as, a derived rule) is not built yet.
"""

from pangloss_models import KeepOnMerge


class IdentityClaim(KeepOnMerge):
    """On a relation to entities: the statement claims that the entities it names are one and the same"""
