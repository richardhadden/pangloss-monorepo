"""What the smoke test derives from its factoids (`pangloss-derived`)"""

from typing import Annotated

from pangloss_derived import Derived, RuleType, SymmetricLabel, Var, rule

from smoke.models import Agent, Gift, Group, Meeting, Membership, Person

social = RuleType("social", "Who had to do with whom")
exchange = RuleType("exchange", "What passed between agents")


class SameGroup(Derived):
    """Members of the same group"""

    _meta = Derived.Meta(symmetric=True)

    first: Annotated[Person, SymmetricLabel("member")]
    second: Annotated[Person, SymmetricLabel("member")]
    group: Group


@rule(types=[social])
def same_group(a: Var[Person], b: Var[Person], group: Var[Group]):
    """Two people said to be members of one group"""
    return SameGroup.Derive(first=a, second=b, group=group).when(
        Membership.Where(member=a, group=group),
        Membership.Where(member=b, group=group),
    )


class MetWith(Derived):
    """Took part in the same meeting"""

    _meta = Derived.Meta(symmetric=True)

    first: Annotated[Agent, SymmetricLabel("participant")]
    second: Annotated[Agent, SymmetricLabel("participant")]


@rule(types=[social])
def met_with(a: Var[Agent], b: Var[Agent], m: Var[Meeting]):
    """Two agents among the participants of one meeting"""
    return MetWith.Derive(first=a, second=b).when(
        Meeting.Where(is_=m, participants=a),
        Meeting.Where(is_=m, participants=b),
    )


class GaveTo(Derived):
    """Gave something to"""

    giver: Agent
    receiver: Agent


@rule(types=[exchange])
def gave_to(a: Var[Agent], b: Var[Agent]):
    """A gift from one agent to another"""
    return GaveTo.Derive(giver=a, receiver=b).when(Gift.Where(given_by=a, given_to=b))
