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
`pangloss_library` and `pangloss_criteria` installed; `declare(reviewed=True)` makes `Factoid` reviewed
(`pangloss_review`: a new one is not published unless it is saved with `published=True`); `declare(dated=True)`
gives every statement a date it may say (`Statement.when`, of `pangloss_dates`), a person a date of birth
(`Person.born`) and a participant a time (`InRole.during`), for the time part; `declare(stand_in=True)` declares
`Mention`, someone named and not identified, which the caller makes a stand-in for a person (`MENTION`, given to
`hooks.stand_ins` before `declare` and taken away after: `pangloss_testing.parts.suite`); `declare(suggested=True)`
lets a participant of an activity be identified, or suggested by a toolchain (`Activity.participants` also takes
`Identification[WeightedAlternative[Person]]` and `IdentificationByToolchain[WeightedAlternative[Person]]`, beside an
`InRole` and inside one), for what is below a suggestion that no person has confirmed (`hooks.unconfirmed`); the
classes below those two are taken too, so also what `pangloss-reconcile`'s worker writes by default
(`IdentificationByToolchainFromText`) and what that becomes when confirmed (`IdentificationFromText`): the worker
measured at size (`notes/similarity-evaluation/planted.py worker`) is declared so.

`declare(compared=True)` (dated too, whatever `dated` says) declares what the comparison of statements is measured
on (implementation_docs/spaces-and-comparison-plan.md, step 5.1; the data is `planted.world(compared=True)`):

| What | Where |
|---|---|
| A class of which there is one for each person | `Birth` |
| A general and a specific class, the field narrowed | `Making`, `MakingOfPicture` (`picture_made` narrows `made`) |
| Who was at a group's assembly | `Attendance` |
| A possibility with a degree entered, a necessity that commits | `Hypothetical` (`how_likely`), `Must` |
| What is said and not vouched for | `Reported`, `Believed`, each taking a `Negative` |
| "It cannot have been so" | `Negative[Hypothetical[...]]` |
| What is prescribed, by whom and to whom | `Order.thing_ordered`: `Ordered`, `Forbidden` (below it), `Permitted` |
| A prescription of another flavour and authority | `Rule.ruled`: `Obliged` (a group's statute) |
| Where a factoid is from | `Factoid.source` |

`Negative` is a "not" with or without `compared`."""

import importlib
from typing import Annotated, Any, no_type_check


class Names(dict):
    __getattr__ = dict.__getitem__


def mention_stand_in() -> Any:
    """The stand-in `Mention` is with `declare(stand_in=True)`: a document given in the place of a person, whose
    `mentioned_type` names the class it stands for (`StandIn.named_type`). The caller appends it to
    `hooks.stand_ins` before `declare` and removes it after"""
    from pangloss_models import hooks

    return hooks.StandIn(
        document="Mention",
        stands_for=lambda model: model.__name__ == "Person",
        named_type="mentioned_type",
    )


@no_type_check
def declare(
    reviewed: bool = False,
    dated: bool = False,
    stand_in: bool = False,
    suggested: bool = False,
    compared: bool = False,
) -> Any:
    """Declare the models and initialise them: gives the classes by name. `reviewed`: `Factoid` is reviewed.
    `dated`: every statement may say when (`when`, a date of `pangloss_dates`, which is then imported: for the time
    part of similarity, whose tests have it installed), a person when born (`born`), a participant when (`during`).
    `stand_in`: `Mention` is declared (a stand-in only while `mention_stand_in()` is among `hooks.stand_ins`).
    `suggested`: a participant may be an identification or a toolchain's suggestion, and an `InRole` may hold one.
    `compared`: the classes and spaces the comparison of statements is measured on (the table above), with dates"""
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
        Attribution,
        Cites,
        Degree,
        DegreeStep,
        Document,
        Entity,
        FieldSubclassing,
        ModelRegistry,
        Modal,
        ReifiedRelation,
        RelationConfig,
        SemanticSpace,
        Trait,
        initialise,
    )

    # (a module is only run once, and the registry was reset: the packages' models are declared again)
    dated = dated or compared
    ModelRegistry._reset()
    importlib.reload(pangloss_library.models)
    importlib.reload(pangloss_criteria.models)
    if reviewed:
        import pangloss_review.models

        importlib.reload(pangloss_review.models)
        from pangloss_review import ReviewMeta

        review_meta = ReviewMeta(reviewable=True)
    if dated:
        import pangloss_dates.models

        importlib.reload(pangloss_dates.models)
        Date = pangloss_dates.models.Date
    library = pangloss_library.models
    Identification = library.Identification
    WeightedAlternative = library.WeightedAlternative
    SameEntity = library.SameEntity
    Suggestion = library.IdentificationByToolchain

    class Agent(Trait):
        pass

    class Person(Entity, Agent):
        _meta = Entity.Meta(create_with_id=True)
        _criteria_meta = CriteriaMeta(allowed=True)
        if dated:
            # (an entity with a date of its own)
            born: Date | None = None

    # (ids of their own, so that a file for a bulk load can name them: `pangloss_testing.planted`)
    class Group(Entity, Agent):
        _meta = Entity.Meta(create_with_id=True)

    class Place(Entity):
        _meta = Entity.Meta(create_with_id=True)

    class InRole[T](ReifiedRelation[T]):
        role: str
        at: Place | None = None
        if dated:
            # (a date on a wrapper: the time part counts it for the head alone)
            during: Date | None = None

    class Sworn[T](InRole[T]):
        """A class below a wrapper: a field that names `InRole` takes it"""

        oath: str = ""

    class Negative[T](SemanticSpace[T]):
        """The source says this is not so"""

        _meta = SemanticSpace.Meta(logical="not")

    if compared:

        class Source(Entity):
            _meta = Entity.Meta(create_with_id=True)

        class Thing(Entity):
            _meta = Entity.Meta(create_with_id=True)

        class Picture(Thing):
            _meta = Entity.Meta(create_with_id=True)

        class Hypothetical[T](SemanticSpace[T]):
            """It may have been so"""

            _meta = SemanticSpace.Meta(logical=Modal("possibility", "epistemic"))
            how_likely: Annotated[DegreeStep | None, Degree()] = None

        class Must[T](SemanticSpace[T]):
            """It must have been so, and the source commits to it: so "it cannot have been" (a `Negative` of a
            `Hypothetical`) is a denial"""

            _meta = SemanticSpace.Meta(
                logical=Modal("necessity", "epistemic"), veridical=1
            )

        class Reported[T](SemanticSpace[T]):
            """Someone said so; the source does not vouch for it"""

            _meta = SemanticSpace.Meta(veridical=0, degree="likely")

        class Believed[T](SemanticSpace[T]):
            """Someone thought so"""

            _meta = SemanticSpace.Meta(veridical=0, degree="possible")

        class Ordered[T](SemanticSpace[T]):
            """Someone ordered that it be so"""

            _meta = SemanticSpace.Meta(
                logical=Modal("necessity", "command"),
                fit="prescribes",
                degree="expected",
            )

        class Forbidden[T](Ordered[T]):
            """Someone ordered that it not be so"""

            _meta = SemanticSpace.Meta(
                logical=Modal("necessity", "command", of_not=True)
            )

        class Permitted[T](SemanticSpace[T]):
            """Someone allowed it"""

            _meta = SemanticSpace.Meta(
                logical=Modal("possibility", "command"), fit="prescribes"
            )

        class Obliged[T](SemanticSpace[T]):
            """A group's statute asks it of its members: another flavour, and another authority, than an order"""

            _meta = SemanticSpace.Meta(
                logical=Modal("necessity", "statute"), fit="prescribes", degree="likely"
            )

    if stand_in:

        class Mention(Document):
            """Someone named and not identified: a stand-in for a person (`mention_stand_in`)"""

            _meta = Document.Meta(create_directly=False)
            mentioned_type: str

    class Statement(Document):
        _meta = Document.Meta(abstract=True, create_directly=False)
        if dated:
            when: Date | None = None

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
        if suggested:
            # (identified, or suggested and not confirmed: beside a role, and in one)
            participants: list[
                InRole[
                    Agent
                    | Identification[WeightedAlternative[Person]]
                    | Suggestion[WeightedAlternative[Person]]
                ]
                | Identification[WeightedAlternative[Person]]
                | Suggestion[WeightedAlternative[Person]]
            ]
        else:
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

    if compared:

        class Birth(Statement):
            """Once for each person: two of one person tell of one event, whatever else they say"""

            person: Person
            place: Place | None = None

        class Making(Statement):
            made_by: Agent
            made: Thing

        class MakingOfPicture(Making):
            picture_made: Annotated[
                Picture,
                RelationConfig(
                    subclasses_parent_fields=[
                        FieldSubclassing("made", field_on_model=Making)
                    ]
                ),
            ]

        class Attendance(Statement):
            """Someone was at a group's assembly"""

            attended_by: Person
            assembly_of: Group

        class Order(Statement):
            ordered_by: Agent
            ordered_to: list[Agent]
            thing_ordered: Annotated[
                Ordered[Statement] | Permitted[Statement],
                Attribution(by="ordered_by", to="ordered_to"),
            ]

        class Rule(Statement):
            ruled_by: Group
            binds: list[Agent]
            ruled: Annotated[Obliged[Statement], Attribution(by="ruled_by", to="binds")]

    class Factoid(Document):
        if compared:
            statements: list[
                Statement
                | SameEntity[Person]
                | Negative[Statement | Hypothetical[Statement]]
                | Hypothetical[Statement]
                | Must[Statement]
                | Reported[Statement | Negative[Statement]]
                | Believed[Statement | Negative[Statement]]
            ]
            source: Source | None = None
        else:
            statements: list[Statement | SameEntity[Person] | Negative[Statement]]
        if reviewed:
            _review_meta = review_meta

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
