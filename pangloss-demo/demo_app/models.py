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
| An embedded object | `Date` |
| An annotated value (a value with fields of its own) | `WithCertainty[str]` |
| Semantic spaces (a context for statements) | `Negative`, `Hypothetical` |
| A conjunction (a join of several things) | `Causes` |
| Binding a value of the parent into its children | `Factoid.year` into `Statement.year` |
| Literals: enums, dates, decimals, a TypedDict, lists, validators | throughout |
"""

import datetime
from decimal import Decimal
from enum import Enum
from typing import Annotated, TypedDict

from annotated_types import Ge, MaxLen, MinLen
from pangloss_models.field_definitions import FieldBinding, FieldSubclassing
from pangloss_models.model_bases.annotated_value import AnnotatedValue
from pangloss_models.model_bases.configs import RelationConfig
from pangloss_models.model_bases.conjunction import Conjunction
from pangloss_models.model_bases.document import Document
from pangloss_models.model_bases.edge_model import EdgeModel
from pangloss_models.model_bases.embedded import Embedded
from pangloss_models.model_bases.entity import Entity
from pangloss_models.model_bases.helpers import ViaEdge
from pangloss_models.model_bases.reified_relation import ReifiedRelation
from pangloss_models.model_bases.semantic_space import SemanticSpace
from pangloss_models.model_bases.trait import Trait

# ---------------------------------------------------------------------------
# Literals, and the small models that carry them
# ---------------------------------------------------------------------------


class Precision(Enum):
    """How exactly a date is known"""

    DAY = "day"
    MONTH = "month"
    YEAR = "year"
    DECADE = "decade"


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


class Date(Embedded):
    """A date, with how exactly it is known. Part of whatever has it."""

    when: datetime.date
    precision: Precision


class Certainty(EdgeModel):
    """How sure the source is of a relation: a property of the relation itself"""

    level: Annotated[int, Ge(1)]


class WithCertainty[T](AnnotatedValue[T]):
    """A value, with how certain it is (1 to 5)"""

    certainty: int


class AtPage[T](ReifiedRelation[T]):
    """A relation to something *at a page* of it"""

    page: str


class InRole[T](ReifiedRelation[T]):
    """A relation to something *in a role*"""

    role: Role


# ---------------------------------------------------------------------------
# Entities: the things that documents refer to
# ---------------------------------------------------------------------------


class Agent(Trait):
    """Anyone who can act: a person or a group"""


class Person(Entity, Agent):
    """A person"""

    # Persons (and sources) can be given a URL as their id, such as an address in another
    # database, and be written in the same request as the factoid that needs them
    _meta = Entity.Meta(create_with_id=True, create_inline=True)

    known_as: WithCertainty[str]
    born: Date
    aliases: list[str]


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
        Agent,
        RelationConfig(
            reverse_name="gave",
            subclasses_parent_fields=[
                FieldSubclassing("involves", field_on_model=Statement)
            ],
        ),
    ]
    given_to: Annotated[Agent, RelationConfig(reverse_name="received")]


class Negative[T](SemanticSpace[T]):
    """It is *not* the case that..."""


class Hypothetical[T](SemanticSpace[T]):
    """The source says it might have been so..."""


class Causes[TCause, TResult](Conjunction):
    """One thing led to another"""

    cause: TCause
    result: TResult


class Factoid(Document):
    """What a source says, at a page: a set of statements"""

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
