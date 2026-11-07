"""Models of the smoke test: an early modern (1450-1650) factoid database.

A **Factoid** is what a source (a Zotero item, `ZoteroBacked`, at a page) says, and holds **statements** of any
kind: every kind is a subclass of the abstract `Statement`. Some kinds happen at a time and are dateable
(`Dateable`, `SingleDateable`, `PeriodDateable`); others are not (kinship, descriptions, names).

Entities: people, eight kinds of group, places in a hierarchy of kinds, objects, books (Zotero-backed),
commodities, currencies, offices, languages, feasts; and two typologies (occupations, titles).
"""

import datetime
from decimal import Decimal
from enum import Enum
from typing import Annotated, TypedDict

from annotated_types import Ge, Le, MaxLen, MinLen
from pangloss_calendar import DateCharacterisation
from pangloss_dates import (
    Date,
    Dateable,
    PeriodDateable,
    SingleDateable,
    SortBy,
    SortDefault,
)
from pangloss_derived import DerivedMeta
from pangloss_interface import InterfaceMeta
from pangloss_library import WeightedAlternative
from pangloss_models import (
    AnnotatedValue,
    Conjunction,
    Document,
    EdgeModel,
    Embedded,
    Entity,
    FieldBinding,
    FieldSubclassing,
    ReifiedRelation,
    RelationConfig,
    SemanticSpace,
    Trait,
    ViaEdge,
)
from pangloss_review import ReviewMeta
from pangloss_typology import Typed, Typology, TypologyMeta
from pangloss_zotero import ZoteroBacked

# ---------------------------------------------------------------------------
# Literals and small models
# ---------------------------------------------------------------------------


class Role(Enum):
    LEADER = "leader"
    WITNESS = "witness"
    PARTICIPANT = "participant"
    MESSENGER = "messenger"
    HOST = "host"


class Gender(Enum):
    FEMALE = "female"
    MALE = "male"
    UNKNOWN = "unknown"


class KinshipKind(Enum):
    PARENT = "parent"
    SIBLING = "sibling"
    COUSIN = "cousin"
    UNCLE_OR_AUNT = "uncle_or_aunt"
    GRANDPARENT = "grandparent"
    GODPARENT = "godparent"


class Coordinates(TypedDict):
    latitude: float
    longitude: float


class Certainty(EdgeModel):
    """How sure the source is of a relation"""

    level: Annotated[int, Ge(1), Le(5)]


class WithCertainty[T](AnnotatedValue[T]):
    """A value, with how certain it is (1 to 5)"""

    certainty: int


class AtPage[T](ReifiedRelation[T]):
    """A source at a page of it"""

    _interface_meta = InterfaceMeta(headless=True)

    page: str
    target: Annotated[list[T], MinLen(1), MaxLen(1)]


class InRole[T](ReifiedRelation[T]):
    """Someone in a role"""

    _derived_meta = DerivedMeta(derivation="transparent")

    role: Role


class Identification[T](ReifiedRelation[T]):
    """A name in the source, identified with one of several people"""

    _interface_meta = InterfaceMeta(collapse=True)

    identified_by: str
    target: Annotated[list[T], MinLen(1), MaxLen(1)]



class Attributed[T](ReifiedRelation[T]):
    """Who in the source says so"""

    attributed_by: str

# ---------------------------------------------------------------------------
# Entities
# ---------------------------------------------------------------------------


class Agent(Trait):
    """Anyone who can act: a person or a group"""


class OccupationTypology(Typology):
    """What a person did for a living"""

    _typology_meta = TypologyMeta(name="OccupationType")


class TitleTypology(Typology):
    """Titles and ranks: duke, count, baron, knight"""

    _typology_meta = TypologyMeta(name="TitleType")


class Person(Entity, Agent):
    """A person"""

    _meta = Entity.Meta(create_with_id=True, create_inline=True)

    known_as: WithCertainty[str]
    gender: Gender
    born: Annotated[Date, SortDefault(SortBy.EARLIEST_FUZZY)]
    aliases: list[str]
    has_type: list[Typed[OccupationTypology]]
    nickname: str | None = None


class Group(Entity, Agent):
    """Any group of people"""

    name: Annotated[str, MinLen(2), MaxLen(200)]


class Family(Group):
    """A family or house"""


class Guild(Group):
    """A guild of a craft or trade"""

    craft: str | None = None


class ReligiousOrder(Group):
    """An order of monks, friars or nuns"""


class Army(Group):
    """An army or a fleet"""


class TradingCompany(Group):
    """A company of merchants"""


class University(Group):
    """A university"""

    founded_year: int | None = None


class Monastery(Group):
    """A religious house"""


class Court(Group):
    """A princely or royal court"""


class Place(Entity):
    """Any place"""

    coordinates: Coordinates | None = None


class Settlement(Place):
    """A city, town or village"""

    _meta = Entity.Meta(indexes=["population_estimate"])

    population_estimate: int | None = None


class Region(Place):
    """A region, county, duchy or kingdom"""


class Building(Place):
    """A building: a church, a palace, a house"""


class PhysicalObject(Entity):
    """Any physical object"""


class Ship(PhysicalObject):
    """A ship"""

    tonnage: int | None = None


class Manuscript(PhysicalObject):
    """A manuscript"""

    shelfmark: str | None = None


class Artwork(PhysicalObject):
    """Any artwork"""


class Painting(Artwork):
    """A painting"""


class Sculpture(Artwork):
    """A sculpture"""


class Book(PhysicalObject, ZoteroBacked):
    """A printed book (a Zotero item made a Book by hand)"""

    _meta = Entity.Meta(create_with_id=True, create_inline=True, accept_url_as_id=True)


class Commodity(Entity):
    """Goods traded: pepper, wool, alum"""


class Currency(Entity):
    """A unit of money: the florin, the ducat"""


class Office(Entity):
    """An office that people held: Doge of Venice, Bishop of Trent"""

    has_type: list[Typed[TitleTypology]]


class Language(Entity):
    """A language"""

    iso_code: str | None = None


class Feast(DateCharacterisation):
    """A day of the calendar"""

    use: str | None = None
    rank: str | None = None


# ---------------------------------------------------------------------------
# Statements: all are subclasses of the abstract Statement
# ---------------------------------------------------------------------------


def narrows_involves() -> RelationConfig:
    return RelationConfig(subclasses_parent_fields=[FieldSubclassing("involves", field_on_model=Statement)])


class Statement(Document):
    """Anything a factoid says (abstract: one of the kinds below)"""

    _meta = Document.Meta(abstract=True, create_directly=False)

    text: Annotated[str, MinLen(5)]
    involves: list[Agent]


class DatedStatement(Statement, Dateable):
    """Something that happened at a time (any kind of date)"""

    _meta = Document.Meta(abstract=True)

    places: list[Place]


class EventStatement(Statement, SingleDateable):
    """Something that happened once, at a time (a day, a year, a range)"""

    _meta = Document.Meta(abstract=True)

    places: list[Place]


class PeriodStatement(Statement, PeriodDateable):
    """Something that lasted: an office, a residence"""

    _meta = Document.Meta(abstract=True)

    places: list[Place]


class UndatedStatement(Statement):
    """Something that is so, with no time: kinship, a description, a name"""

    _meta = Document.Meta(abstract=True)


# --- Life events (single dates) ------------------------------------------------


class Birth(EventStatement):
    child: Annotated[Person, narrows_involves()]
    parents: list[Person]


class Baptism(EventStatement):
    baptised: Annotated[Person, narrows_involves()]
    godparents: list[Person]


class Death(EventStatement):
    deceased: Annotated[Person, narrows_involves()]
    cause: str | None = None


class Burial(EventStatement):
    buried: Annotated[Person, narrows_involves()]


class Marriage(EventStatement):
    spouses: Annotated[list[Person], MinLen(2), MaxLen(2), narrows_involves()]
    dowry: Decimal | None = None


class Betrothal(EventStatement):
    betrothed: Annotated[list[Person], MinLen(2), MaxLen(2), narrows_involves()]


class Ordination(EventStatement):
    ordained: Annotated[Person, narrows_involves()]
    ordained_by: list[Person]


class Coronation(EventStatement):
    crowned: Annotated[Person, narrows_involves()]
    office: Office


class Knighting(EventStatement):
    knighted: Annotated[Person, narrows_involves()]
    knighted_by: list[Person]


class Ennoblement(EventStatement):
    ennobled: Annotated[Agent, narrows_involves()]
    has_type: list[Typed[TitleTypology]]


class Graduation(EventStatement):
    graduate: Annotated[Person, narrows_involves()]
    university: University
    degree: str


class Matriculation(EventStatement):
    student: Annotated[Person, narrows_involves()]
    university: University


class Execution(EventStatement):
    executed: Annotated[Person, narrows_involves()]


class Election(EventStatement):
    elected: Annotated[Person, narrows_involves()]
    office: Office
    votes: int | None = None


class Appointment(EventStatement):
    appointee: Annotated[Person, narrows_involves()]
    appointed_by: list[Agent]
    office: Office


class Dismissal(EventStatement):
    dismissed: Annotated[Person, narrows_involves()]
    office: Office


class Conversion(EventStatement):
    convert: Annotated[Person, narrows_involves()]
    from_faith: str
    to_faith: str


class Excommunication(EventStatement):
    excommunicated: Annotated[Agent, narrows_involves()]


class Founding(EventStatement):
    founder: Annotated[ViaEdge[Agent, Certainty], narrows_involves()]
    founded: Group


class Construction(EventStatement):
    builder: Annotated[list[Agent], narrows_involves()]
    building: Building


class Destruction(EventStatement):
    destroyed: Building
    destroyed_by: Annotated[list[Agent], narrows_involves()]


class Shipwreck(EventStatement):
    ship: Ship


class Canonisation(EventStatement):
    saint: Annotated[Person, narrows_involves()]


# --- Periods ------------------------------------------------------------------


class OfficeHolding(PeriodStatement):
    holder: Annotated[ViaEdge[Person, Certainty], narrows_involves()]
    office: Office


class Residence(PeriodStatement):
    resident: Annotated[Agent, narrows_involves()]


class Apprenticeship(PeriodStatement):
    apprentice: Annotated[Person, narrows_involves()]
    master: list[Agent]
    guild: list[Guild]


class Membership(PeriodStatement):
    member: Annotated[
        Agent | Identification[WeightedAlternative[Person]],
        RelationConfig(
            reverse_name="member_of",
            subclasses_parent_fields=[FieldSubclassing("involves", field_on_model=Statement)],
        ),
    ]
    group: Annotated[Group, RelationConfig(reverse_name="has_member")]


class Employment(PeriodStatement):
    employee: Annotated[Person, narrows_involves()]
    employer: list[Agent]
    wage: Decimal | None = None


class Imprisonment(PeriodStatement):
    prisoner: Annotated[Person, narrows_involves()]


class Exile(PeriodStatement):
    exiled: Annotated[Agent, narrows_involves()]


class Reign(PeriodStatement):
    ruler: Annotated[Person, narrows_involves()]
    realm: Region


class StudyAt(PeriodStatement):
    student: Annotated[Person, narrows_involves()]
    university: University


class Siege(PeriodStatement):
    besiegers: Annotated[list[Group], narrows_involves()]
    besieged: Settlement


class Pilgrimage(PeriodStatement):
    pilgrim: Annotated[Person, narrows_involves()]
    destination: Place


# --- Any date ------------------------------------------------------------------


class Meeting(DatedStatement):
    participants: Annotated[list[InRole[Agent]], RelationConfig(default_reified_type=InRole)]


class Letter(DatedStatement):
    sender: Annotated[Agent, narrows_involves()]
    recipient: Annotated[Agent, RelationConfig(reverse_name="received_letter")]
    language: list[Language]


class Gift(DatedStatement):
    item: str
    quantity: Decimal
    given_by: Annotated[
        Agent | Identification[WeightedAlternative[Person]],
        RelationConfig(
            reverse_name="gave",
            subclasses_parent_fields=[FieldSubclassing("involves", field_on_model=Statement)],
        ),
    ]
    given_to: Annotated[
        Agent | Identification[WeightedAlternative[Person]],
        RelationConfig(reverse_name="received"),
    ]


class Sale(DatedStatement):
    seller: Annotated[Agent, narrows_involves()]
    buyer: Annotated[Agent, RelationConfig(reverse_name="bought")]
    commodity: list[Commodity]
    price: Decimal
    currency: Currency


class Loan(DatedStatement):
    lender: Annotated[Agent, narrows_involves()]
    borrower: Annotated[Agent, RelationConfig(reverse_name="borrowed")]
    amount: Decimal
    currency: Currency
    interest_percent: float | None = None


class Payment(DatedStatement):
    payer: Annotated[Agent, narrows_involves()]
    payee: Annotated[Agent, RelationConfig(reverse_name="was_paid")]
    amount: Decimal
    currency: Currency


class Commission(DatedStatement):
    patron: Annotated[Agent, narrows_involves()]
    artist: Annotated[Person, RelationConfig(reverse_name="commissioned_from")]
    artwork: Artwork


class CreationOfPhysicalObject(DatedStatement):
    created_by: Annotated[Person, narrows_involves()]
    object_created: PhysicalObject


class CreationOfArtwork(CreationOfPhysicalObject):
    artwork_created: Annotated[
        Artwork,
        RelationConfig(
            subclasses_parent_fields=[
                FieldSubclassing(field_name="object_created", field_on_model=CreationOfPhysicalObject)
            ]
        ),
    ]


class Printing(DatedStatement):
    printer: Annotated[Agent, narrows_involves()]
    book: Book
    copies: int | None = None


class Authorship(DatedStatement):
    author: Annotated[Person, narrows_involves()]
    work: Book | Manuscript


class Translation(DatedStatement):
    translator: Annotated[Person, narrows_involves()]
    work: Book | Manuscript
    into: Language


class Battle(DatedStatement):
    sides: Annotated[list[Group], MinLen(2), narrows_involves()]
    victor: list[Group]
    casualties: int | None = None


class Treaty(DatedStatement):
    parties: Annotated[list[Agent], MinLen(2), narrows_involves()]
    terms: str


class Voyage(DatedStatement):
    ship: Ship
    captain: Annotated[list[Person], narrows_involves()]
    from_place: Place
    to_place: Place
    cargo: list[Commodity]


class Lawsuit(DatedStatement):
    plaintiff: Annotated[Agent, narrows_involves()]
    defendant: Annotated[Agent, RelationConfig(reverse_name="defended")]
    court: list[Court]
    matter: str


class Accusation(DatedStatement):
    accuser: Annotated[Agent, narrows_involves()]
    accused: Annotated[Agent, RelationConfig(reverse_name="was_accused")]
    charge: str


class Pardon(DatedStatement):
    pardoned: Annotated[Person, narrows_involves()]
    pardoned_by: list[Person]


class Petition(DatedStatement):
    petitioner: Annotated[Agent, narrows_involves()]
    petitioned: Annotated[Agent, RelationConfig(reverse_name="was_petitioned")]
    request: str


class Sermon(DatedStatement):
    preacher: Annotated[Person, narrows_involves()]
    theme: str


class Visit(DatedStatement):
    visitor: Annotated[Agent, narrows_involves()]
    host: list[Agent]


class Inheritance(DatedStatement):
    heir: Annotated[Person, narrows_involves()]
    from_deceased: Annotated[Person, RelationConfig(reverse_name="left_inheritance")]
    what: str


class Donation(DatedStatement):
    donor: Annotated[Agent, narrows_involves()]
    recipient_institution: Group
    amount: Decimal | None = None


class Order(DatedStatement):
    """Someone ordered something: another statement, in a subjunctive space"""

    ordered_by: Annotated[
        Agent | Identification[WeightedAlternative[Person]],
        RelationConfig(
            reverse_name="ordered",
            subclasses_parent_fields=[FieldSubclassing("involves", field_on_model=Statement)],
        ),
    ]
    ordered_to: Annotated[
        Agent | Identification[WeightedAlternative[Person]],
        RelationConfig(reverse_name="received_order"),
    ]
    thing_ordered: Annotated[
        PositiveSubjunctive[Statement] | NegativeSubjunctive[Statement],
        RelationConfig(
            bind_to_child_field=[
                FieldBinding(bound_field="ordered_to", child_fields=["given_by", "payer", "sender"])
            ]
        ),
    ]



# --- Deep nesting (added 2026-11-07) ------------------------------------------------


class Witnessing(DatedStatement):
    """Witnesses to something, each one reified four deep: who in the source names the witness, in what role, and
    which of several people the name is"""

    presided_by: Annotated[Agent, narrows_involves()]
    witnesses: Annotated[
        list[Attributed[InRole[Identification[WeightedAlternative[Person]]]]],
        RelationConfig(reverse_name="witnessed"),
    ]


class SealMatrix(Embedded):
    """The die a seal was struck from"""

    # (a relation to Person here crashes initialise(): PROBLEMS.md #37)
    engraved_by: str
    motto: str


class SealImpression(Embedded):
    """The wax, and what struck it"""

    wax_colour: str
    matrix: SealMatrix


class Seal(Embedded):
    """A seal on a document, as it is now"""

    condition: str
    impression: SealImpression


class SealedLetter(DatedStatement):
    """A letter described by its seal: embedded three deep"""

    sealed_by: Annotated[Agent, narrows_involves()]
    seal: Seal

# --- Undated -----------------------------------------------------------------------


class Kinship(UndatedStatement):
    person: Annotated[Person, narrows_involves()]
    relative: Annotated[Person, RelationConfig(reverse_name="relative_of")]
    kinship_kind: KinshipKind


class PhysicalDescription(UndatedStatement):
    described: Annotated[Person, narrows_involves()]
    description: str


class Characterisation(UndatedStatement):
    characterised: Annotated[Agent, narrows_involves()]
    trait: str


class NameVariant(UndatedStatement):
    named: Annotated[Agent, narrows_involves()]
    name: WithCertainty[str]


class Origin(UndatedStatement):
    native: Annotated[Person, narrows_involves()]
    origin: Place


class LanguageSpoken(UndatedStatement):
    speaker: Annotated[Person, narrows_involves()]
    language: Language
    fluency: Annotated[int | None, Ge(1), Le(5)] = None


class Ownership(UndatedStatement):
    owner: Annotated[Agent, narrows_involves()]
    owned: PhysicalObject


class LocatedIn(UndatedStatement):
    place: Place
    within: Place


class OccupationAscription(UndatedStatement):
    person: Annotated[Person, narrows_involves()]
    has_type: list[Typed[OccupationTypology]]


class Reputation(UndatedStatement):
    reputed: Annotated[Agent, narrows_involves()]
    reputation: str
    favourable: bool



class Report(UndatedStatement):
    """Someone reported a statement, which can itself be a report (of a report of an order of an order ...)"""

    reporter: Annotated[Agent, narrows_involves()]
    reported: Annotated[Hearsay[Statement], RelationConfig(reverse_name="reported_in")]

# ---------------------------------------------------------------------------
# Spaces, conjunctions, the factoid
# ---------------------------------------------------------------------------


class PositiveSubjunctive[T](SemanticSpace[T]):
    """It was wished that this should happen"""

    _interface_meta = InterfaceMeta(colour="green")


class NegativeSubjunctive[T](SemanticSpace[T]):
    """It was wished that this should not happen"""

    _interface_meta = InterfaceMeta(colour="orange")


class Negative[T](SemanticSpace[T]):
    """It is not the case that..."""

    _interface_meta = InterfaceMeta(colour="rose")


class Hypothetical[T](SemanticSpace[T]):
    """The source says it might have been so"""

    _interface_meta = InterfaceMeta(colour="yellow")



class Hearsay[T](SemanticSpace[T]):
    """Someone said that..."""

    _interface_meta = InterfaceMeta(colour="sky")

class Causes[TCause, TResult](Conjunction):
    """One thing led to another"""

    cause: TCause
    result: TResult


class Factoid(Document):
    """What a source says, at a page: a set of statements"""

    _review_meta = ReviewMeta(reviewable=True)

    source: AtPage[ZoteroBacked]
    statements: list[
        Statement | Negative[Statement] | Hypothetical[Statement] | Causes[Statement, Statement]
    ]
    recorded_on: datetime.date | None = None
