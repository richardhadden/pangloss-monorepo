"""What the demo derives from what its factoids say (`pangloss-derived`; see implementation_docs/derived.md).

Most factoids speak of one person at a time ("X was a member of the Medici"). The rules here make the relations between
people that follow, so that a network grows as factoids are added: nobody writes "X and Y are of one family", but two
factoids, perhaps from two sources, say it between them. Each derived edge keeps its justifications: the rule, the
factoids, and what they passed through (a negation, a weighted alternative).

Only the rules that join **two documents** are here. An edge that one document gives by itself is declared on its
class, in `models.py` (`_derives`): `GaveTo`, from the giver of a `Transfer` to its receiver, and `CoParticipants`,
between each two of the participants of an `Activity`. Those are `DerivedEdge` classes too, made when the models are
initialised: `DerivedEdge.named("GaveTo")`, or `from demo_app.models import GaveTo` once they are.
"""

from typing import Annotated

from pangloss_derived import DerivedEdge, SymmetricLabel, Var, rule

from demo_app.models import Group, MemberOf, Person, family, social


class SameGroup(DerivedEdge):
    """Members of the same group (a family, an order, an army)"""

    _meta = DerivedEdge.Meta(symmetric=True)

    first: Annotated[Person, SymmetricLabel("member")]
    second: Annotated[Person, SymmetricLabel("member")]
    group: Group


@rule(types=[family, social])
def same_group(a: Var[Person], b: Var[Person], group: Var[Group]):
    """Two people said (perhaps by different sources) to be members of one group"""
    return SameGroup.Derive(first=a, second=b, group=group).when(
        MemberOf.Where(member=a, group=group),
        MemberOf.Where(member=b, group=group),
    )
