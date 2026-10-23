"""One set of models that uses every kind of model and every way of relating them, to be
initialised and compared with the stored snapshot (`test_generated_models_snapshot.py`).

It is the demo project's models, plus what the demo does not use: `Fulfils`, a
`NonHeritableTrait`, a `ReifiedRelationDocument`, relations to generic wrappers *with* an edge model,
bindings on embedded and annotated values, `DBField`, a document with no label, and an entity with
a URL for an id but no `create_inline`.

The classes are made inside a function, because the registry is emptied before every test.
"""

import datetime
from decimal import Decimal
from enum import Enum
from typing import Annotated, TypedDict

from annotated_types import Ge, MaxLen, MinLen
from pydantic import Field
from pangloss_models.field_definitions import FieldBinding, FieldSubclassing
from pangloss_models.model_bases.annotated_value import AnnotatedValue
from pangloss_models.model_bases.configs import RelationConfig
from pangloss_models.model_bases.conjunction import Conjunction
from pangloss_models.model_bases.document import Document
from pangloss_models.model_bases.edge_model import EdgeModel
from pangloss_models.model_bases.embedded import Embedded
from pangloss_models.model_bases.entity import Entity
from pangloss_models.model_bases.helpers import DBField, Fulfils, ViaEdge
from pangloss_models.model_bases.reified_relation import (
    ReifiedRelation,
    ReifiedRelationDocument,
)
from pangloss_models.model_bases.semantic_space import SemanticSpace
from pangloss_models.model_bases.trait import NonHeritableTrait, Trait


def declare() -> None:
    class Precision(Enum):
        DAY = "day"
        YEAR = "year"

    class Role(Enum):
        LEADER = "leader"
        WITNESS = "witness"

    class Coordinates(TypedDict):
        latitude: float
        longitude: float

    class Date(Embedded):
        """A date, with how exactly it is known"""

        when: datetime.date
        precision: Precision

    class Certainty(EdgeModel):
        level: Annotated[int, Ge(1)]

    class Weight(EdgeModel):
        weight: float

    class WithCertainty[T](AnnotatedValue[T]):
        certainty: int

    class AtPage[T](ReifiedRelation[T]):
        page: str

    class InRole[T](ReifiedRelation[T]):
        role: Role

    class LivedIn[T](ReifiedRelationDocument[T]):
        """A relation that is a document of its own, with fields"""

        years: int

    class Agent(Trait):
        """Anyone who can act"""

    class Attested[T](ReifiedRelation[T]):
        """A relation with a document and an embedded object of its own"""

        note: Annotated[Note, RelationConfig(description="The note made when it was attested")]
        dated: Date

    class Marker(NonHeritableTrait):
        """A trait whose fields are not inherited indirectly"""

    class Person(Entity, Agent):
        _meta = Entity.Meta(create_with_id=True, create_inline=True)

        known_as: WithCertainty[str]
        born: Date
        aliases: list[str]
        nickname: str | None
        note: str | None = Field(default=None, description="A note on the person")
        db_flag: Annotated[bool | None, DBField]

    class Group(Entity, Agent):
        name: Annotated[str, MinLen(2), MaxLen(100)]

    class Place(Entity):
        """An entity with a URL for an id, but that cannot be written in a document"""

        coordinates: Coordinates | None = None

    class Source(Entity):
        _meta = Entity.Meta(create_with_id=True, create_inline=True)

        author: str | None = None
        written: datetime.date | None = None
        edition_price: Decimal | None = None

    class Office(Entity, Marker):
        title: str

    # --- Fulfils: a document that supplies what another requires -----------------------

    class Appointment(Document):
        holder: Person
        office: Office
        started: Date
        reference_code: str

    class Grant(Document, Fulfils[Appointment]):
        granted_by: Annotated[
            Person,
            RelationConfig(
                subclasses_parent_fields=[
                    FieldSubclassing("holder", field_on_model=Appointment)
                ]
            ),
        ]

    # --- Statements, and wrappers around them ------------------------------------------

    class Statement(Document):
        _meta = Document.Meta(abstract=True)

        text: Annotated[str, MinLen(5)]
        date: Date
        year: int
        involves: list[Agent]
        places: list[Place]

    class Activity(Statement):
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
        # a relation to a generic wrapper, with an edge model on the relation
        witnesses: list[ViaEdge[InRole[Agent], Weight]]
        # a relation to a generic whose own field is an entity (not a type variable)
        lived: list[LivedIn[Place]]

    class Transfer(Statement):
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
        pass

    class Hypothetical[T](SemanticSpace[T]):
        pass

    class Causes[TCause, TResult](Conjunction):
        cause: TCause
        result: TResult

    class Note(Document):
        """A document with no label"""

        _meta = Document.Meta(require_label=False)

        body: str
        about: Person

    class Doubt(Document):
        """An entity reached through a wrapper inside a semantic space (it has a reverse relation)"""

        perhaps: Hypothetical[InRole[Agent]]
        joined: Causes[Place, Person]
        attested: Attested[Person]

    class Factoid(Document):
        year: int
        source: AtPage[Source]
        # bindings: to a literal (`year`), to an embedded object (`date`), and to an annotated
        # value (`known_as`), through wrappers
        statements: Annotated[
            list[
                Statement
                | Negative[Statement]
                | Hypothetical[Statement]
                | Causes[Statement, Statement]
            ],
            RelationConfig(
                bind_to_child_field=[
                    FieldBinding(bound_field="year", child_fields=["year"]),
                    FieldBinding(
                        bound_field="year",
                        child_fields=["date"],
                        allowed_type_names=["Activity"],
                        converter=lambda year: None,
                    ),
                ]
            ),
        ]
        notes: Annotated[
            list[Note],
            RelationConfig(
                description="Notes on the factoid",
                bind_to_child_field=[
                    FieldBinding(bound_field="year", child_fields=["body"])
                ],
            ),
        ]
        # a relation to a trait
        involved: list[Agent]
