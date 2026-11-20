"""Models with every shape the joined graph of similarity has a rule for (implementation_docs/graph-embeddings.md,
"The joined graph, as now proposed"): for the live tests of `pangloss-vectors` and `pangloss-fastrp`, and for
`notes/similarity-evaluation/stored_shapes.py`, which prints what each is stored as.

| Shape | Where |
|---|---|
| A nested document | `Factoid.statements` |
| A wrapper before an entity, and two with a share | `Transfer.given_to`: `Identification[WeightedAlternative[Person]]` |
| The same inside a space | `Factoid.statements`: `Negative[Statement]` |
| A class below a wrapper | `Sworn[T](InRole[T])`, taken by `Activity.participants` |
| A wrapper with a relation of its own | `InRole.at` |
| A field that subclasses a parent's | `Activity.carried_out_by` (and `involves`) |
| A wrapper that is a document | `SameEntity[Person]` |
| A computed relation | `MatchesCriteria` where a person goes (`Transfer.given_by`) |
| A citation | `Inference.evidence` |
| A derived edge with a shortcut, and a derived document | `SameGroup`, `DerivedFactoid` |

`declare()` is called by each test (the registry is reset between tests), with the apps `pangloss_derived`,
`pangloss_library` and `pangloss_criteria` installed."""

import importlib
from typing import Annotated, Any, no_type_check


class Names(dict):
    __getattr__ = dict.__getitem__


@no_type_check
def declare() -> Any:
    """Declare the models and initialise them: gives the classes by name"""
    import pangloss_criteria.models
    import pangloss_library.models
    from pangloss_criteria import CriteriaMeta
    from pangloss_derived import (
        DerivedDocument,
        DerivedEdge,
        DerivedFrom,
        SymmetricLabel,
        Var,
        rule,
        unordered,
    )
    from pangloss_models import (
        Cites,
        Document,
        Entity,
        FieldSubclassing,
        ModelRegistry,
        ReifiedRelation,
        RelationConfig,
        SemanticSpace,
        Trait,
        initialise,
    )

    # (a module is only run once, and the registry was reset: the packages' models are declared again)
    ModelRegistry._reset()
    importlib.reload(pangloss_library.models)
    importlib.reload(pangloss_criteria.models)
    library = pangloss_library.models
    Identification = library.Identification
    WeightedAlternative = library.WeightedAlternative
    SameEntity = library.SameEntity

    class Agent(Trait):
        pass

    class Person(Entity, Agent):
        _meta = Entity.Meta(create_with_id=True)
        _criteria_meta = CriteriaMeta(allowed=True)

    class Group(Entity, Agent):
        pass

    class Place(Entity):
        pass

    class InRole[T](ReifiedRelation[T]):
        role: str
        at: Place | None = None

    class Sworn[T](InRole[T]):
        """A class below a wrapper: a field that names `InRole` takes it"""

        oath: str = ""

    class Negative[T](SemanticSpace[T]):
        pass

    class Statement(Document):
        _meta = Document.Meta(abstract=True, create_directly=False)

    class Event(Statement):
        _meta = Document.Meta(abstract=True, create_directly=False)
        involves: list[Agent]

    class Activity(Event):
        carried_out_by: Annotated[
            Agent,
            RelationConfig(
                reverse_name="carried_out",
                subclasses_parent_fields=[
                    FieldSubclassing("involves", field_on_model=Event)
                ],
            ),
        ]
        participants: list[InRole[Agent]]

    class Transfer(Statement):
        given_by: Agent
        given_to: Agent | Identification[WeightedAlternative[Person]]

    class MemberOf(Statement):
        member: Person
        group: Group

    class ChildOf(Statement):
        child: Person
        parent: Person

    class Sibling(Statement):
        people: list[Person]

    class Inference(Statement):
        evidence: list[Cites[Statement]]

    class Factoid(Document):
        statements: list[Statement | SameEntity[Person] | Negative[Statement]]

    class DerivedFactoid(Document, DerivedDocument):
        sources: list[DerivedFrom[Factoid]]
        statements: list[Statement]

    class SameGroup(DerivedEdge):
        """Members of the same group"""

        _meta = DerivedEdge.Meta(symmetric=True, shortcut=True)
        first: Annotated[Person, SymmetricLabel("member")]
        second: Annotated[Person, SymmetricLabel("member")]
        group: Group

    @rule
    def same_group(a: Var[Person], b: Var[Person], g: Var[Group]):
        """Two people said to be members of one group"""
        return SameGroup.Derive(first=a, second=b, group=g).when(
            MemberOf.Where(member=a, group=g),
            MemberOf.Where(member=b, group=g),
        )

    @rule
    def siblings(a: Var[Person], b: Var[Person], p: Var[Person]):
        """Two children of one parent are siblings"""
        return DerivedFactoid.Derive(
            label="Siblings",
            statements=[Sibling.Template(label="Siblings", people=[a, b])],
        ).when(
            ChildOf.Where(child=a, parent=p),
            ChildOf.Where(child=b, parent=p),
            unordered(a, b),
        )

    initialise()
    return Names(locals())
