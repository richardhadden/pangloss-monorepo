"""Models of the demo: a factoid database.

A **Factoid** is a claim made by a source (a Zotero item, `ZoteroBacked`, at a page of it), and contains a list of
**Statements**: things that happened between people, groups and places. The models are
small, and between them use most of what Pangloss has:

| Feature | Where |
|---------|-------|
| Documents, nested (a Factoid contains Statements) | `Factoid`, `Statement` |
| Entities, referred to by documents | `Person`, `Group`, `Place`, `Source` |
| Entity ids that are URLs, and entities written inline | `Source`, `Person` |
| Subclassing a document; an abstract base | `Statement` -> `Activity`, `Transfer` |
| A document that is only ever part of another (`create_directly=False`, inherited) | `Statement` |
| A trait: "any of these entities" | `Agent` (`Person` or `Group`) |
| Narrowing a field of the parent class | `Activity.carried_out_by` narrows `Statement.involves` |
| A reified relation (a relation with fields) | `AtPage[ZoteroBacked]`, `InRole[Agent]` |
| Sources from a Zotero library (`pangloss-zotero`), and an item made a project class by hand | `Factoid.source`, `Book` |
| Properties on an edge | `ViaEdge[Agent, Certainty]` |
| Dates (in the Julian calendar by setting, with doubt and ranges) | `Statement.date`, `Person.born` (`pangloss-dates`) |
| A vocabulary of types in a hierarchy | `OccupationTypology` (`pangloss-typology`) |
| Review before publishing | `Factoid` (`pangloss-review`) |
| An annotated value (a value with fields of its own) | `WithCertainty[str]` |
| Semantic spaces (a context for statements) | `Negative`, `Hypothetical`, `PositiveSubjunctive`, `NegativeSubjunctive` |
| A statement that holds another statement | `Order.thing_ordered` |
| Binding a value of the parent into its children | `Order.ordered_to` into the `given_by` or `ordered_by` of what is ordered |
| A conjunction (a join of several things) | `Causes` (and the library's `WeightedAlternative`, any number) |
| Shares that add up to 100, edited with sliders (`SumsTo`, `Slider`; `pangloss-library`) | `WeightedAlternative.alternatives` |
| A reified relation to a conjunction, with edge properties on its members | `Identification[WeightedAlternative[Person]]` (the edge is in `WeightedAlternative`) |
| Someone a source names who is not identified yet, where a person goes (`pangloss-review`: `ReviewMeta(allow_unreconciled=True)`) | `Person`; the rule of which are reconciled together is `Factoid`'s |
| An identification that a toolchain suggested, for a person to confirm (`pangloss-library`) | `IdentificationByToolchain[WeightedAlternative[Person]]`, wherever an `Identification` goes |
| Aligned to CIDOC-CRM in the RDF export (`pangloss-rdf`): plain mixins, which are not data, and a field's parent property | `Agent`, `Person`, `Group`, `Place`, `Statement`, `Activity` |
| Literals: enums, dates, decimals, a TypedDict, lists, validators | throughout |
| A document offered with a new entity, and written with it if filled in (a companion) | `Person`: a `Factoid` of a `Naming` and a `Gendering` |
| A statement that two people are one, with the statements of other factoids it rests on (`IdentityClaim()`, `Cites[T]`) | `SamePerson` |
| What a space or a conjunction does to a derived relation (`pangloss-derived`; the rules are in `derived.py`) | `WeightedAlternative` (exclusive), `InRole` |
"""

import datetime
from decimal import Decimal
from enum import Enum
from typing import Annotated, TypedDict

from annotated_types import Ge, MaxLen, MinLen
from pangloss_calendar import DateCharacterisation
from pangloss_dates import Date, Dateable, SortBy, SortDefault
from pangloss_derived import DerivedMeta
from pangloss_interface import InterfaceMeta
from pangloss_library import (
    Identification,
    IdentificationByToolchain,
    IdentityClaim,
    SameEntity,
    WeightedAlternative,
)
from pangloss_models import (
    AnnotatedValue,
    Cites,
    Companion,
    CompanionPart,
    Conjunction,
    CopyFromOuter,
    Document,
    EdgeModel,
    Entity,
    FieldBinding,
    FieldSubclassing,
    ReifiedRelation,
    RelationConfig,
    SemanticSpace,
    Standalone,
    Trait,
    ViaEdge,
    Within,
)
from pangloss_rdf import RDFField
from pangloss_rdf.ontologies.crm import (
    E5_Event,
    E7_Activity,
    E21_Person,
    E39_Actor,
    E53_Place,
    E74_Group,
    P7_took_place_at,
    P14_carried_out_by,
)
from pangloss_review import ReviewMeta
from pangloss_typology import Typed, Typology, TypologyMeta
from pangloss_zotero import ZoteroBacked

# ---------------------------------------------------------------------------
# Literals, and the small models that carry them
# ---------------------------------------------------------------------------


class Role(Enum):
    LEADER = "leader"
    WITNESS = "witness"
    PARTICIPANT = "participant"
    MESSENGER = "messenger"


class Gender(Enum):
    FEMALE = "female"
    MALE = "male"
    OTHER = "other"


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


class WithCertainty[T](AnnotatedValue[T]):
    """A value, with how certain it is (1 to 5)"""

    certainty: int


class AtPage[T](ReifiedRelation[T]):
    """A relation to something *at a page* of it"""

    # (where it is all a field holds, as a factoid's source, its type says nothing: only the source and the page)
    _interface_meta = InterfaceMeta(headless=True)
    # (inside a factoid's label: "Chronicle of Lanercost, p. 12")
    _meta = ReifiedRelation.Meta(label_template="{target}[, p. {page}]")

    page: str
    target: Annotated[list[T], MinLen(1), MaxLen(1)]


class InRole[T](ReifiedRelation[T]):
    """A relation to something *in a role*"""

    # (a derived relation through a role is as if there were no role: "took part" is plain)
    _derived_meta = DerivedMeta(derivation="transparent")
    # (inside an activity's label: "Robert Bruce (witness)")
    _meta = ReifiedRelation.Meta(label_template="{target} ({role})")

    role: Role


# ---------------------------------------------------------------------------
# Entities: the things that documents refer to
# ---------------------------------------------------------------------------


class Agent(Trait, E39_Actor):
    """Anyone who can act: a person or a group"""


class OccupationTypology(Typology):
    """What a person did: a hierarchy (a secretary is a court official is an official)"""

    _typology_meta = TypologyMeta(name="OccupationType")


class Person(Entity, Agent, E21_Person):
    """A person"""

    # Persons (and sources) can be given a URL as their id, such as an address in another
    # database, and be written in the same request as the factoid that needs them.
    # A person made in the interface is offered a factoid of its own, of the same source as the factoid it is made
    # from, saying what the source calls them and their gender: written with the person if it is filled in
    # (implementation_docs/companion-documents.md)
    _meta = Entity.Meta(
        create_with_id=True,
        create_inline=True,
        companions=[
            Companion(
                name="naming_and_gender",
                document="Factoid",
                field="statements",
                parts=[
                    CompanionPart(type="Naming", entity_field="named"),
                    CompanionPart(type="Gendering", entity_field="gendered"),
                ],
                copies=[CopyFromOuter(field="source")],
                offered=[Within(heads=["Factoid"]), Standalone()],
            )
        ],
    )
    # (someone a source names who has not been identified can stand where a person goes: an `Unreconciled`, which is
    # a task of review until a person is put in its place)
    _review_meta = ReviewMeta(allow_unreconciled=True)

    known_as: WithCertainty[str]
    born: Annotated[Date, SortDefault(SortBy.EARLIEST_FUZZY)]
    aliases: list[str]
    has_type: list[Typed[OccupationTypology]]


class Group(Entity, Agent, E74_Group):
    """A family, an order, an army..."""

    name: Annotated[str, MinLen(2), MaxLen(100)]


class Place(Entity, E53_Place):
    coordinates: Coordinates | None = None


class Feast(DateCharacterisation):
    """A day of the calendar: a saint's day every year (`when` a Recurrence), a council that sat once (an ExactDate or
    a DateRange), a Lent (a Period), or one attached to days by hand (NoRule). Shown by `pangloss_calendar`"""

    # (the base has only `when`: what else a feast is, a project says)
    use: str | None = None
    """The liturgical use it belongs to (Sarum, Roman...)"""
    rank: str | None = None
    """Its grade: double, semidouble, simple..."""


class Source(Entity):
    """A text that makes claims: a chronicle, a letter, a charter"""

    _meta = Entity.Meta(create_with_id=True, create_inline=True)

    author: str | None = None
    written: datetime.date | None = None
    edition_price: Decimal | None = None


# ---------------------------------------------------------------------------
# Documents: the factoid, and what it states
# ---------------------------------------------------------------------------


class Statement(Document, Dateable, E5_Event):
    """Something that happened between agents and in places (abstract: a kind of
    statement is one of the classes below). Dateable: it has a `date`, and says when in
    lists and on the pages of the people and places it involves"""

    # A statement is only ever part of a factoid: none of its kinds can be made on its own
    _meta = Document.Meta(abstract=True, create_directly=False)

    text: Annotated[str, MinLen(5)]
    involves: list[Agent]
    places: Annotated[list[Place], RDFField(parent=P7_took_place_at)]


class Activity(Statement, E7_Activity):
    """An agent did something, with others in different roles"""

    # "Meeting by Edward I, with Robert Bruce (witness) and John Balliol (leader), at Berwick, 10 May 1296"
    _meta = Document.Meta(
        label_template="{activity_type|capitalise} by {carried_out_by}"
        '[, with {participants|join(", ", " and ")}]'
        '[, at {places|join(", ", " and ")}]'
        "[, {date}]"
    )

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
        RDFField(parent=P14_carried_out_by),
    ]
    # (in the interface, a person or a group is searched for, and put in a role: `default_reified_type`)
    participants: Annotated[
        list[InRole[Agent]], RelationConfig(default_reified_type=InRole)
    ]


class Transfer(Statement):
    """Something passed from one agent to another"""

    # "Edward I gave 3 × horse to Robert Bruce, at Carlisle, 1297"
    _meta = Document.Meta(
        label_template="{given_by} gave {quantity} × {item} to {given_to}"
        '[, at {places|join(", ", " and ")}][, {date}]'
    )

    item: str
    quantity: Decimal
    given_by: Annotated[
        Agent
        | Identification[WeightedAlternative[Person]]
        | IdentificationByToolchain[WeightedAlternative[Person]],
        RelationConfig(
            reverse_name="gave",
            subclasses_parent_fields=[
                FieldSubclassing("involves", field_on_model=Statement)
            ],
        ),
    ]
    given_to: Annotated[
        Agent
        | Identification[WeightedAlternative[Person]]
        | IdentificationByToolchain[WeightedAlternative[Person]],
        RelationConfig(reverse_name="received"),
    ]


class Inference(Statement):
    """What is concluded from statements of other factoids, which it cites as evidence"""

    # (`Cites[Statement]`: the statements are named by id, not copied, and stay where they are. One that is cited
    # cannot be removed, and a change to it has to be confirmed and marks the citation "changed since cited")
    evidence: list[Cites[Statement]]


# `SameEntity[Person]` (`pangloss-library`) says that two people are one, with an argument in words. A project that
# wants the evidence as well writes its own class, as here:
# - what makes it a claim of identity is the marker on `people` (`IdentityClaim()`): each person's page lists what
#   they are said to be the same as; the two, and those they are said to be the same as in turn, can be shown
#   together and searched for together (`$same_as`); and if the two are later merged, the statement still names both;
# - `evidence` names statements of other factoids by id (`Cites`), without copying them: they stay where they are,
#   cannot be removed while cited, and a change to one is marked on the citation.
class SamePerson(Document):
    """Two people the sources name are one and the same: why, and the statements that show it"""

    _meta = Document.Meta(
        create_directly=False,
        label_template='{people|join(" is the same as ")}',
    )

    people: Annotated[list[Person], MinLen(2), MaxLen(2), IdentityClaim()]
    argument: Annotated[str, MinLen(5)]
    evidence: Annotated[list[Cites[Statement]], MinLen(1)]


class Naming(Statement):
    """What a source calls someone: their name, in parts"""

    # "Robert Bruce: Earl of Carrick Robert Bruce"; "Robert Bruce: Robert" (what is not given is left out)
    _meta = Document.Meta(label_template="{named}: [{title} ][{first_name}][ {family_name}]")

    # (a naming says what it says in its fields: no text or date needed)
    text: Annotated[str, MinLen(5)] | None = None
    date: Date | None = None
    named: Annotated[
        Person,
        RelationConfig(
            reverse_name="named_in",
            subclasses_parent_fields=[
                FieldSubclassing("involves", field_on_model=Statement)
            ],
        ),
    ]
    first_name: str | None = None
    family_name: str | None = None
    title: str | None = None


class Gendering(Statement):
    """The gender a source gives someone"""

    # "Robert Bruce: male"
    _meta = Document.Meta(label_template="{gendered}: {gender}")

    text: Annotated[str, MinLen(5)] | None = None
    date: Date | None = None
    gendered: Annotated[
        Person,
        RelationConfig(
            reverse_name="gendered_in",
            subclasses_parent_fields=[
                FieldSubclassing("involves", field_on_model=Statement)
            ],
        ),
    ]
    gender: Gender


class MemberOf(Statement):
    """Someone was a member of a group: of a family, an order, an army. (Two factoids that say so of two people make
    them members of the same group: see `derived.py`)"""

    # "Robert Bruce, member of the Bruce family, 1290"
    _meta = Document.Meta(label_template="{member}, member of {group}[, {date}]")

    member: Annotated[
        Agent
        | Identification[WeightedAlternative[Person]]
        | IdentificationByToolchain[WeightedAlternative[Person]],
        RelationConfig(
            reverse_name="member_of",
            subclasses_parent_fields=[
                FieldSubclassing("involves", field_on_model=Statement)
            ],
        ),
    ]
    group: Annotated[Group, RelationConfig(reverse_name="has_member")]


class Order(Statement):
    """Someone ordered something to be done: *something else*, which is a statement of
    its own, said in a subjunctive space, because it was wished, and not necessarily done"""

    # "Order from Edward I to Robert Bruce: Robert Bruce gave 3 × horse to John Balliol, 1297" (or "...: not: ...")
    _meta = Document.Meta(
        label_template="Order from {ordered_by} to {ordered_to}[, {date}][: {thing_ordered}]"
    )

    ordered_by: Annotated[
        Agent
        | Identification[WeightedAlternative[Person]]
        | IdentificationByToolchain[WeightedAlternative[Person]],
        RelationConfig(
            reverse_name="ordered",
            subclasses_parent_fields=[
                FieldSubclassing("involves", field_on_model=Statement)
            ],
        ),
    ]
    # Who received the order: the one who is to do what is ordered, so it is given to what is ordered (in the
    # subjunctive space) that does not say otherwise: who gives, in a transfer, or who orders, in an order passed on
    ordered_to: Annotated[
        Agent
        | Identification[WeightedAlternative[Person]]
        | IdentificationByToolchain[WeightedAlternative[Person]],
        RelationConfig(reverse_name="received_order"),
    ]
    thing_ordered: Annotated[
        PositiveSubjunctive[Statement] | NegativeSubjunctive[Statement],
        RelationConfig(
            bind_to_child_field=[
                FieldBinding(
                    bound_field="ordered_to", child_fields=["given_by", "ordered_by"]
                )
            ]
        ),
    ]


class PositiveSubjunctive[T](SemanticSpace[T]):
    """It was wished that this should happen (it did not necessarily)"""

    _interface_meta = InterfaceMeta(colour="green")


class NegativeSubjunctive[T](SemanticSpace[T]):
    """It was wished that this should *not* happen (and it did not necessarily not)"""

    _interface_meta = InterfaceMeta(colour="orange")
    # (a positive subjunctive has no template: it reads as what it holds, which the order's label says was wished)
    _meta = SemanticSpace.Meta(label_template='not: {contents|join("; ")}')


class Negative[T](SemanticSpace[T]):
    """It is *not* the case that..."""

    _interface_meta = InterfaceMeta(colour="rose")
    _meta = SemanticSpace.Meta(label_template='not: {contents|join("; ")}')


class Hypothetical[T](SemanticSpace[T]):
    """The source says it might have been so..."""

    _interface_meta = InterfaceMeta(colour="yellow")
    _meta = SemanticSpace.Meta(label_template='perhaps: {contents|join("; ")}')


class Causes[TCause, TResult](Conjunction):
    """One thing led to another"""

    _meta = Conjunction.Meta(label_template="{cause} → {result}")

    cause: TCause
    result: TResult


class PhysicalObject(Entity):
    """Any physical object"""


class Book(PhysicalObject, ZoteroBacked):
    """A book. It may be a Zotero item: no Zotero type is claimed, so an item comes in as a `ZoteroObject`, and a
    person makes it a `Book` by hand (or makes a `Book` and links it to an item)"""

    _meta = Entity.Meta(create_with_id=True, create_inline=True, accept_url_as_id=True)


class Artwork(PhysicalObject):
    """Any artwork object"""


class Painting(Artwork):
    """A painting"""


class CreationOfPhysicalObject(Statement):
    _meta = Document.Meta(label_template="{created_by} made {object_created}[, {date}]")

    created_by: Annotated[
        Person,
        RelationConfig(
            subclasses_parent_fields=[
                FieldSubclassing(field_name="involves", field_on_model=Statement)
            ]
        ),
    ]
    object_created: PhysicalObject


class CreationOfArtwork(CreationOfPhysicalObject):
    _meta = Document.Meta(
        label_template="{created_by} made {artwork_created}[, {date}]"
    )

    artwork_created: Annotated[
        Artwork,
        RelationConfig(
            subclasses_parent_fields=[
                FieldSubclassing(
                    field_name="object_created", field_on_model=CreationOfPhysicalObject
                )
            ]
        ),
    ]


class CreationOfPainting(CreationOfArtwork):
    _meta = Document.Meta(
        label_template="{created_by} painted {painting_created}[, {date}]"
    )

    painting_created: Annotated[
        Painting,
        RelationConfig(
            subclasses_parent_fields=[
                FieldSubclassing(
                    field_name="artwork_created", field_on_model=CreationOfArtwork
                )
            ]
        ),
    ]


class Factoid(Document):
    """What a source says, at a page: a set of statements"""

    # (checked by another user before it is published; the unreconciled mentions offered to be reconciled together
    # with one of a factoid's are those of the factoids of the same source)
    _review_meta = ReviewMeta(reviewable=True, reconcile_together=("source",))
    _interface_meta = InterfaceMeta(colour="orange")
    # "Chronicle of Lanercost, p. 12: Meeting by Edward I...; not: Robert Bruce gave..." (lists cut it short)
    # (`cited_with`: the source is part of what is cited when one of its statements is, so a change of it is a
    # change to each statement that another factoid cites)
    _meta = Document.Meta(
        label_template='{source}[: {statements|join("; ")}]', cited_with=["source"]
    )

    source: AtPage[ZoteroBacked]
    # (`SameEntity[Person]`: the source says two people are one, or, in `Negative`, that they are not; a person's
    # page lists what they are said to be the same as, and the two can be merged from there)
    statements: list[
        Statement
        | SameEntity[Person]
        | SamePerson
        | Negative[Statement | SameEntity[Person] | SamePerson]
        | Hypothetical[Statement | SameEntity[Person] | SamePerson]
        | Causes[Statement, Statement]
    ]
