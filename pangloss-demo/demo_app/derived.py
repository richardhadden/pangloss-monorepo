"""What the demo derives from what its factoids say (`pangloss-derived`; see docs/derived.md).

Most factoids speak of one person at a time ("X was a member of the Medici"). The rules here make the relations between
people that follow, so that a network grows as factoids are added: nobody writes "X and Y are of one family", but two
factoids, perhaps from two sources, say it between them. Each derived fact keeps its justifications: the rule, the
factoids, and what they passed through (a negation, an uncertain identification).
"""

from typing import Annotated

from pangloss_derived import Derived, RuleType, SymmetricLabel, Var, rule

from demo_app.models import Activity, Agent, Group, MemberOf, Person, Transfer

family = RuleType("family", "Ties of family and of membership")
social = RuleType("social", "Who had to do with whom")
exchange = RuleType("exchange", "What passed between agents")


class SameGroup(Derived):
    """Members of the same group (a family, an order, an army)"""

    _meta = Derived.Meta(symmetric=True)

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


class CoParticipants(Derived):
    """Took part in the same activity"""

    _meta = Derived.Meta(symmetric=True)

    first: Annotated[Agent, SymmetricLabel("participant")]
    second: Annotated[Agent, SymmetricLabel("participant")]


@rule(types=[social])
def co_participants(a: Var[Agent], b: Var[Agent], act: Var[Activity]):
    """Two agents among the participants of one activity"""
    return CoParticipants.Derive(first=a, second=b).when(
        Activity.Where(is_=act, participants=a),
        Activity.Where(is_=act, participants=b),
    )


class GaveTo(Derived):
    """Gave something to"""

    giver: Agent
    receiver: Agent


@rule(types=[exchange, social])
def gave_to(a: Var[Agent], b: Var[Agent]):
    """A transfer from one agent to another (each of the people an identification may be, in turn)"""
    return GaveTo.Derive(giver=a, receiver=b).when(
        Transfer.Where(given_by=a, given_to=b)
    )
