"""Models of the demo: a factoid database.

A **Factoid** is a claim made by a **Source** (at a page of it), and contains a list of
**Statements**: things that happened between people, groups and places. The models are
small, and between them use most of what Pangloss has:

| Feature | Where |
|---------|-------|
| Documents, nested (a Factoid contains Statements) | `Factoid`, `Statement` |
| Entities, referred to by documents | `Person`, `Group`, `Place`, `Source` |
| Entity ids that are URLs, and entities written inline | `Source`, `Person` |
| Subclassing a document; an abstract base | `Statement` -> `Activity`, `Transfer` |
| A trait: "any of these entities" | `Agent` (`Person` or `Group`) |
| Narrowing a field of the parent class | `Activity.carried_out_by` narrows `Statement.involves` |
| A reified relation (a relation with fields) | `AtPage[Source]`, `InRole[Agent]` |
| Properties on an edge | `ViaEdge[Agent, Certainty]` |
| Dates (in the Julian calendar by setting, with doubt and ranges) | `Statement.date`, `Person.born` (`pangloss-dates`) |
| A vocabulary of types in a hierarchy | `OccupationTypology` (`pangloss-typology`) |
| Review before publishing | `Factoid` (`pangloss-review`) |
| An annotated value (a value with fields of its own) | `WithCertainty[str]` |
| Semantic spaces (a context for statements) | `Negative`, `Hypothetical`, `PositiveSubjunctive`, `NegativeSubjunctive` |
| A statement that holds another statement | `Order.thing_ordered` |
| A conjunction (a join of several things) | `Causes`, `Alternative` (any number) |
| A reified relation to a conjunction, with edge properties on its members | `Identification[Alternative[ViaEdge[Person, Probability]]]` |
| Binding a value of the parent into its children | `Factoid.year` into `Statement.year` |
| Literals: enums, dates, decimals, a TypedDict, lists, validators | throughout |
"""

import datetime
from decimal import Decimal
from enum import Enum
from typing import Annotated, TypedDict

from annotated_types import Ge, Le, MaxLen, MinLen
from pangloss_dates.bounds import SortBy
from pangloss_dates.models import Date, SortDefault
from pangloss_interface import InterfaceMeta
from pangloss_models.field_definitions import FieldBinding, FieldSubclassing
from pangloss_models.model_bases.annotated_value import AnnotatedValue
from pangloss_models.model_bases.configs import RelationConfig
from pangloss_models.model_bases.conjunction import Conjunction
from pangloss_models.model_bases.document import Document
from pangloss_models.model_bases.edge_model import EdgeModel
from pangloss_models.model_bases.entity import Entity
from pangloss_models.model_bases.helpers import ViaEdge
from pangloss_models.model_bases.reified_relation import ReifiedRelation
from pangloss_models.model_bases.semantic_space import SemanticSpace
from pangloss_models.model_bases.trait import Trait
from pangloss_review.meta import ReviewMeta
from pangloss_typology import Typed, Typology, TypologyMeta

# ---------------------------------------------------------------------------
# Literals, and the small models that carry them
# ---------------------------------------------------------------------------


class Role(Enum):
    LEADER = "leader"
    WITNESS = "witness"
    PARTICIPANT = "participant"
    MESSENGER = "messenger"


class ActivityType(Enum):
    MEETING = "meeting"
    JOURNEY = "journey"
    BATTLE = "battle"
    CEREMONY = "ceremony"
    CORRESPONDENCE = "correspondence"


class Coordinates(TypedDict):
    latitude: float
    longitude: float


class Certainty(EdgeModel):
    """How sure the source is of a relation: a property of the relation itself"""

    level: Annotated[int, Ge(1)]


class Probability(EdgeModel):
    """How likely it is that this is the one meant, out of the alternatives (1 to 100, in per cent)"""

    percent: Annotated[int, Ge(1), Le(100)]


class WithCertainty[T](AnnotatedValue[T]):
    """A value, with how certain it is (1 to 5)"""

    certainty: int


class AtPage[T](ReifiedRelation[T]):
    """A relation to something *at a page* of it"""

    page: str


class InRole[T](ReifiedRelation[T]):
    """A relation to something *in a role*"""

    role: Role


class Alternative[T](Conjunction):
    """One of several things, not known which: any number of statements or entities.
    `Alternative[ViaEdge[Person, Probability]]` gives each person how likely it is the one meant"""

    alternatives: list[T]


class Identification[T](ReifiedRelation[T]):
    """A name in the source that has been identified: the source says "Smith", and
    this says which people that could be. The target is one `Alternative`."""

    identified_by: str
    target: Annotated[list[T], MinLen(1), MaxLen(1)]


# ---------------------------------------------------------------------------
# Entities: the things that documents refer to
# ---------------------------------------------------------------------------


class Agent(Trait):
    """Anyone who can act: a person or a group"""


class OccupationTypology(Typology):
    """What a person did: a hierarchy (a secretary is a court official is an official)"""

    _typology_meta = TypologyMeta(name="OccupationType")


class Person(Entity, Agent):
    """A person"""

    # Persons (and sources) can be given a URL as their id, such as an address in another
    # database, and be written in the same request as the factoid that needs them
    _meta = Entity.Meta(create_with_id=True, create_inline=True)

    known_as: WithCertainty[str]
    born: Annotated[Date, SortDefault(SortBy.EARLIEST_FUZZY)]
    aliases: list[str]
    has_type: list[Typed[OccupationTypology]]


class Group(Entity, Agent):
    """A family, an order, an army..."""

    name: Annotated[str, MinLen(2), MaxLen(100)]


class Place(Entity):
    coordinates: Coordinates | None = None


class Source(Entity):
    """A text that makes claims: a chronicle, a letter, a charter"""

    _meta = Entity.Meta(create_with_id=True, create_inline=True)

    author: str | None = None
    written: datetime.date | None = None
    edition_price: Decimal | None = None


# ---------------------------------------------------------------------------
# Documents: the factoid, and what it states
# ---------------------------------------------------------------------------


class Statement(Document):
    """Something that happened between agents and in places (abstract: a kind of
    statement is one of the classes below)"""

    _meta = Document.Meta(abstract=True)

    text: Annotated[str, MinLen(5)]
    date: Date
    # (filled by the children below; see `year` on `Factoid`)
    year: int
    involves: list[Agent]
    places: list[Place]


class Activity(Statement):
    """An agent did something, with others in different roles"""

    activity_type: ActivityType
    # Narrows `involves` (which it also fills): it must be one agent, and it says how sure
    # the source is of it, on the relation itself
    carried_out_by: Annotated[
        ViaEdge[Agent, Certainty],
        RelationConfig(
            reverse_name="carried_out",
            subclasses_parent_fields=[
                FieldSubclassing("involves", field_on_model=Statement)
            ],
        ),
    ]
    participants: list[InRole[Agent]]


class Transfer(Statement):
    """Something passed from one agent to another"""

    item: str
    quantity: Decimal
    given_by: Annotated[
        Agent | Identification[Alternative[ViaEdge[Person, Probability]]],
        RelationConfig(
            reverse_name="gave",
            subclasses_parent_fields=[
                FieldSubclassing("involves", field_on_model=Statement)
            ],
        ),
    ]
    given_to: Annotated[
        Agent | Identification[Alternative[ViaEdge[Person, Probability]]],
        RelationConfig(reverse_name="received"),
    ]


class Order(Statement):
    """Someone ordered something to be done: *something else*, which is a statement of
    its own, said in a subjunctive space, because it was wished, and not necessarily done"""

    ordered_by: Annotated[
        Agent | Identification[Alternative[ViaEdge[Person, Probability]]],
        RelationConfig(
            reverse_name="ordered",
            subclasses_parent_fields=[
                FieldSubclassing("involves", field_on_model=Statement)
            ],
        ),
    ]
    thing_ordered: PositiveSubjunctive[Statement] | NegativeSubjunctive[Statement]


class PositiveSubjunctive[T](SemanticSpace[T]):
    """It was wished that this should happen (it did not necessarily)"""

    _interface_meta = InterfaceMeta(colour="green")


class NegativeSubjunctive[T](SemanticSpace[T]):
    """It was wished that this should *not* happen (and it did not necessarily not)"""

    _interface_meta = InterfaceMeta(colour="orange")


class Negative[T](SemanticSpace[T]):
    """It is *not* the case that..."""

    _interface_meta = InterfaceMeta(colour="rose")


class Hypothetical[T](SemanticSpace[T]):
    """The source says it might have been so..."""

    _interface_meta = InterfaceMeta(colour="yellow")


class Causes[TCause, TResult](Conjunction):
    """One thing led to another"""

    cause: TCause
    result: TResult


class Factoid(Document):
    """What a source says, at a page: a set of statements"""

    # Factoids are searched by year, so it has an index (and the label of every class has one already)
    _meta = Document.Meta(indexes=["year"])
    # (checked by another user before it is published)
    _review_meta = ReviewMeta(reviewable=True)

    year: int
    source: AtPage[Source]
    statements: Annotated[
        list[
            Statement
            | Negative[Statement]
            | Hypothetical[Statement]
            | Causes[Statement, Statement]
        ],
        # The year is entered once, and given to every statement that does not have one
        RelationConfig(
            bind_to_child_field=[
                FieldBinding(bound_field="year", child_fields=["year"])
            ]
        ),
    ]
