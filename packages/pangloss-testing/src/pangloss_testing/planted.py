"""A planted prosopography with a known truth, on the models of `pangloss_testing.similar_models`: what the parts of
similarity are measured on (implementation_docs/similarity-build-plan.md, step 8.1). No database and nothing but the
standard library: the same seed gives the same world, in any process.

    world = planted.world(seed=1, people=300)
    world.entities      the `Create` payloads of the people (the mentions among them), groups and places, with ids
    world.factoids      the `Create` payloads of the factoids that name them
    world.mentions      the truth: for each mention (a person as one source spells them), who it is
    world.variants      the given names: each canonical form and its variants
    world.years         the year of each factoid, by its label

    dated = planted.world(seed=1, people=300, dated=True)       (for the time part: `declare(dated=True)`)
    dated.dates         the date each factoid's statements say (`when`), by the factoid's label: a `Date` payload
    dated.events        the truth: the labels of the factoids that report each event more than one reports
    dated.series        the truth: the events of each thing that happened year after year, in their order

    compared = planted.world(seed=1, people=300, compared=True)  (dated too: `declare(compared=True)`)
    compared.told       the truth: each statement added for comparison, by its label (which no other has): the
                        factoid it is in, the event it tells of, the spaces it is in, the order that prescribes it
    compared.verdicts   the truth: each pair of them that tells of one event (or was planted as two), and how
                        the two stand to each other (`RELATIONS`)
    compared.liveness   the truth: of each statement said not to be so, how far it was to be expected
    compared.sources    the sources (`Factoid.source`), and `compared.things`, the pictures made

What is planted:

- **Families** of two parents and some children, of one surname, living at a place; the adults are members of one or
  two groups. Surnames are shared by several families, and given names are few and unevenly common, so **many people
  have the same name** as someone of another family (`world.namesakes`).
- **Factoids** say it: `ChildOf`, `Sibling`, `MemberOf`, an `Activity` with participants `InRole` at the family's
  place, a `Transfer` between members of a group (one in ten to an `Identification` of two alternatives).
- **Mentions.** A share of the people are named once more by another source: a `Person` of their own (as a project
  has before the two are reconciled), under the same name, another spelling of the surname, a variant of the given
  name, or both, in one `Activity` with people of their family and group. Which person a mention is, is the truth;
  nothing in the data says it.
- **Dates** (`dated=True`; the people, the mentions and every factoid above are the same with or without).
  Everything happened on a day; a factoid says it as its source knew it: the day, the month, the year, or some
  years it was within. **Other reports**: a share of the gatherings are told once more, by a source that names
  fewer of the people and says the date its own way. **Year after year**: some adults pay their group its dues on
  the same day for six to twelve years, each payment reported twice, by the same people to the same group, so that
  nothing but the date tells one year's from the next. Which factoids are of one event is the truth
  (`world.events`); nothing in the data says it.

- **For comparison** (`compared=True`; everything above is the same with or without, and what is added comes
  after it). Each family has each of the cases of `COMPARED` with the chance the table gives, each a pair of
  statements (in two factoids, or in one where the case says so) and what the pair is, in `world.verdicts`:
  - *one event told twice*: a birth (once for each person) told alike, or with another place, or another date; a
    making told as a `Making` and as a `MakingOfPicture`, alike or with another maker; a gathering told alike, with
    one participant another person, or some days off; and, as **two** events, a second thing made and a second
    gathering of the same people a year or more later;
  - *an assertion and what does not assert*: a gathering denied by another source (`Negative`), said to have been
    possible (`Hypothetical`, some with a degree entered), `Reported` or `Believed`, each leaning for or against
    (holding a `Negative`), and "it cannot have been" (`Negative[Hypothetical[...]]`, a denial, since `Must`
    commits); and two that assert nothing, leaning the same way or not;
  - *within one factoid*: a source that contradicts itself, and one event entered twice;
  - *what is prescribed and what came of it*: an `Order` to give (the date in it a target) carried out on the day,
    late, or not; an order not to, kept or broken; a permission used; three in ten told with what came of them in
    one factoid; and an order not to give to a group whose `Rule` obliges it (two orders at odds);
  - *absences*: each group of three or more holds an assembly, its roll an `Attendance` for those present and a
    `Negative` of one for members who were not (expected: liveness 1) and, for half of them, for someone with no tie
    to the group (not expected: liveness 0).

  Each factoid added has a source; two factoids of a pair are of one source one time in five. Any two of these
  statements that `world.verdicts` does not pair are of two events (`World.relation`). A person's birth is told by
  one case only, and every other case makes an event of its own, so nothing planted is one event by chance.

Sizes: a family is about 5 people and 47 stored nodes of the models, so `people=32_000` is about 300,000 of them
(measured: 122,777 records, 302,239 nodes of the models; 629,927 nodes with the records of who made each and the
marks that writes leave for the workers).
"""

import dataclasses
import datetime
import random
import uuid
from typing import Any

# A canonical given name and its variants (a project's table of variants, step 8.5, is this)
GIVEN: dict[str, list[str]] = {
    "Johannes": ["Johann", "Hans", "Jan", "Hannes"],
    "Margarethe": ["Margarete", "Grete", "Greta", "Margit"],
    "Heinrich": ["Heinz", "Hinrich", "Henrik"],
    "Elisabeth": ["Elsbeth", "Liesl", "Else", "Elise"],
    "Friedrich": ["Fritz", "Frederik", "Friedel"],
    "Katharina": ["Katharine", "Kathe", "Trine", "Katrin"],
    "Wilhelm": ["Willem", "Willi", "Helm"],
    "Anna": ["Anne", "Anke", "Annchen"],
    "Nikolaus": ["Niklas", "Klaus", "Nickel"],
    "Barbara": ["Barbel", "Babette"],
    "Konrad": ["Kunz", "Kurt", "Conrad"],
    "Dorothea": ["Dorte", "Thea", "Dorothee"],
    "Georg": ["Jorg", "Jurgen", "Jorge"],
    "Ursula": ["Ursel", "Ulla", "Orsola"],
    "Matthias": ["Mathis", "Matz", "Mattes"],
    "Agnes": ["Agnete", "Nesa"],
    "Jakob": ["Jacob", "Jockel", "Kobus"],
    "Christina": ["Christine", "Stina", "Kristin"],
    "Peter": ["Petrus", "Peer", "Pieter"],
    "Magdalena": ["Magda", "Lena", "Madlen"],
    "Michael": ["Michel", "Mikel"],
    "Sophia": ["Sophie", "Fieke"],
    "Andreas": ["Andres", "Anders", "Drewes"],
    "Gertrud": ["Gertraud", "Trude", "Gesa"],
}

_ONSETS = ["B", "Br", "D", "F", "G", "Gr", "H", "K", "Kr", "L", "M", "N", "P", "R", "S", "Sch", "St", "T", "V", "W", "Z"]  # fmt: skip
_MIDDLES = ["a", "au", "e", "ei", "i", "o", "u", "ie", "eu", "ay", "ey"]
_ENDS = ["ber", "cker", "dt", "ff", "ger", "hl", "ler", "mann", "ner", "rich", "ss", "tner", "tz", "ld", "nn", "ll"]  # fmt: skip
_SECONDS = ["", "", "", "en", "er", "ing", "hof", "berg", "stein", "bach"]

# Another spelling of a surname: the first rule that changes it, from a start the name chooses
_SPELLINGS = [
    ("ay", "ai"), ("ey", "ei"), ("ei", "ey"), ("ai", "ay"), ("ck", "k"), ("tz", "z"), ("ff", "f"), ("ss", "s"),
    ("nn", "n"), ("ll", "l"), ("dt", "t"), ("ie", "i"), ("K", "C"), ("V", "F"), ("F", "V"), ("au", "aw"),
    ("eu", "oi"), ("mann", "man"), ("er", "ner"), ("i", "ie"), ("z", "tz"), ("t", "dt"), ("k", "ck"),
]  # fmt: skip

ROLES = ["witness", "guest", "guarantor", "godparent", "heir"]
KINDS = ("same", "spelling", "variant", "both")


@dataclasses.dataclass(frozen=True)
class Person:
    id: str
    given: str
    """The canonical form of the given name"""
    surname: str
    family: int
    born: int
    label: str
    """As stored: mostly the canonical name, sometimes a variant"""


@dataclasses.dataclass(frozen=True)
class Mention:
    id: str
    """The id of the mention's own `Person`"""
    label: str
    person: str
    """The id of the person it is: the truth"""
    kind: str
    """`same` name, another `spelling` of the surname, a `variant` of the given name, or `both`: **against the
    person's canonical name**, not the label the person is stored under, which is itself a variant for about one
    person in seven (so a `same` mention is not always the stored label, and a `variant` one sometimes is)"""


# How two statements stand to each other (implementation_docs/semantic-space-fields.md, "Contents find, spaces
# decide"): the first three are of two that assert; the rest of the table's rows that are planted
RELATIONS = (
    "agree", "disagree", "two",
    "contradiction", "support", "tension", "compatible", "at_odds",
    "carried_out", "carried_out_otherwise", "not_carried_out", "breach", "complied", "permission_used",
    "orders_at_odds",
)  # fmt: skip

# The cases planted for comparison: the chance that a family has each (the last two: that a group's assembly has)
COMPARED: dict[str, float] = {
    "birth_agree": 0.15, "birth_place": 0.1, "birth_date": 0.1,
    "making_specific": 0.1, "making_maker": 0.08, "making_two": 0.08,
    "gathering_agree": 0.1, "gathering_participant": 0.1, "gathering_date": 0.1, "gathering_two": 0.1,
    "gathering_denied": 0.1, "gathering_might": 0.08, "gathering_cannot": 0.06,
    "gathering_reported": 0.08, "gathering_reported_not": 0.06,
    "gathering_believed": 0.06, "gathering_believed_not": 0.06,
    "reports_compatible": 0.06, "reports_at_odds": 0.06,
    "self_contradiction": 0.05, "entered_twice": 0.05,
    "order_on_time": 0.1, "order_late": 0.1, "order_not": 0.1,
    "forbidden_kept": 0.08, "forbidden_broken": 0.08, "permission_used": 0.08, "orders_at_odds": 0.06,
    "absence_expected": 1.0, "absence_unexpected": 0.5,
}  # fmt: skip

# What each case's pair is
RELATION_OF: dict[str, str] = {
    "birth_agree": "agree", "birth_place": "disagree", "birth_date": "disagree",
    "making_specific": "agree", "making_maker": "disagree", "making_two": "two",
    "gathering_agree": "agree", "gathering_participant": "disagree", "gathering_date": "disagree",
    "gathering_two": "two",
    "gathering_denied": "contradiction", "gathering_might": "support", "gathering_cannot": "contradiction",
    "gathering_reported": "support", "gathering_reported_not": "tension",
    "gathering_believed": "support", "gathering_believed_not": "tension",
    "reports_compatible": "compatible", "reports_at_odds": "at_odds",
    "self_contradiction": "contradiction", "entered_twice": "agree",
    "order_on_time": "carried_out", "order_late": "carried_out_otherwise", "order_not": "not_carried_out",
    "forbidden_kept": "complied", "forbidden_broken": "breach", "permission_used": "permission_used",
    "orders_at_odds": "orders_at_odds",
}  # fmt: skip


@dataclasses.dataclass(frozen=True)
class Told:
    """A statement added for comparison"""

    label: str
    """Its label, which no other statement of the world has"""
    factoid: str
    """The label of its factoid"""
    case: str
    """The case of `COMPARED` it was planted by"""
    event: str
    """What it tells of: two statements of one event have the same. Of what is prescribed (and of what is said
    not to have been), the event that would be"""
    spaces: tuple[str, ...] = ()
    """The spaces it is in, outermost first; none when it is asserted"""
    order: str | None = None
    """The label of the order or rule whose space holds it"""


@dataclasses.dataclass(frozen=True)
class Verdict:
    """How two statements added for comparison stand to each other"""

    a: str
    b: str
    """The two statements' labels: `a` the first told, and of a prescription and what came of it, what is
    prescribed"""
    relation: str
    """One of `RELATIONS`"""
    case: str
    fields: tuple[str, ...] = ()
    """Where they disagree, the fields; where an order was carried out otherwise, the targets missed"""
    same_factoid: bool = False
    same_source: bool = False


@dataclasses.dataclass(frozen=True)
class Liveness:
    """Of a statement said not to be so: how far it was to be expected"""

    value: float
    grounds: str
    """`reported` (another statement says or supposes it), `ordered`, `forbidden`, `member` (of the group whose
    assembly it is), or `none`"""


@dataclasses.dataclass
class World:
    seed: int
    people: list[Person]
    groups: list[dict[str, Any]]
    places: list[dict[str, Any]]
    factoids: list[dict[str, Any]]
    mentions: list[Mention]
    years: dict[str, int]
    variants: dict[str, list[str]] = dataclasses.field(
        default_factory=lambda: {k: list(v) for k, v in GIVEN.items()}
    )
    dates: dict[str, dict[str, Any]] = dataclasses.field(default_factory=dict)
    events: dict[str, list[str]] = dataclasses.field(default_factory=dict)
    series: dict[str, list[str]] = dataclasses.field(default_factory=dict)
    sources: list[dict[str, Any]] = dataclasses.field(default_factory=list)
    things: list[dict[str, Any]] = dataclasses.field(default_factory=list)
    told: dict[str, Told] = dataclasses.field(default_factory=dict)
    verdicts: list[Verdict] = dataclasses.field(default_factory=list)
    liveness: dict[str, Liveness] = dataclasses.field(default_factory=dict)
    _factoids: dict[str, dict[str, Any]] | None = dataclasses.field(
        default=None, repr=False, compare=False
    )

    @property
    def entities(self) -> list[dict[str, Any]]:
        """The `Create` payloads of every entity, with its id: the people, the mentions, the groups, the places"""
        # (`create_new`: an id given to a `Create` says so, or it is taken for a reference)
        return [
            {**entity, "create_new": True}
            for entity in (
                *(
                    {"type": "Person", "id": p.id, "label": p.label}
                    for p in self.people
                ),
                *(
                    {"type": "Person", "id": m.id, "label": m.label}
                    for m in self.mentions
                ),
                *self.groups,
                *self.places,
                *self.sources,
                *self.things,
            )
        ]

    def records(self) -> list[dict[str, Any]]:
        """Everything in the order it can be written: the entities, then the factoids"""
        return [*self.entities, *self.factoids]

    @property
    def namesakes(self) -> dict[str, list[str]]:
        """The ids of the people of each canonical name that more than one person has"""
        by_name: dict[str, list[str]] = {}
        for person in self.people:
            by_name.setdefault(f"{person.given} {person.surname}", []).append(person.id)
        return {name: ids for name, ids in sorted(by_name.items()) if len(ids) > 1}

    def relation(self, a: str, b: str) -> str:
        """How two statements added for comparison (by their labels, in either order) stand to each other: what
        `verdicts` says of the pair, and `two` of a pair it does not have"""
        for verdict in self.verdicts:
            if {verdict.a, verdict.b} == {a, b}:
                return verdict.relation
        if a not in self.told or b not in self.told:
            raise KeyError("Not a statement added for comparison")
        return "two"

    def statement(self, label: str) -> dict[str, Any]:
        """The payload of a statement added for comparison, by its label"""

        def find(value: Any) -> dict[str, Any] | None:
            if isinstance(value, dict):
                if value.get("label") == label:
                    return value
                value = list(value.values())
            if isinstance(value, list):
                for inner in value:
                    if (found := find(inner)) is not None:
                        return found
            return None

        if self._factoids is None:
            self._factoids = {factoid["label"]: factoid for factoid in self.factoids}
        found = find(self._factoids[self.told[label].factoid]["statements"])
        assert found is not None
        return found

    def truth(self) -> dict[str, Any]:
        """What is true of the world and not said in it, as JSON can say it"""
        return {
            "seed": self.seed,
            "people": [dataclasses.asdict(p) for p in self.people],
            "mentions": [dataclasses.asdict(m) for m in self.mentions],
            "namesakes": self.namesakes,
            "variants": self.variants,
            "years": self.years,
            "dates": self.dates,
            "events": self.events,
            "series": self.series,
            "told": {label: dataclasses.asdict(t) for label, t in self.told.items()},
            "verdicts": [dataclasses.asdict(v) for v in self.verdicts],
            "liveness": {
                label: dataclasses.asdict(live) for label, live in self.liveness.items()
            },
        }


def respelled(surname: str, choice: int) -> str:
    """Another spelling of a surname (the same for the same `choice`), or the surname if no rule changes it"""
    for offset in range(len(_SPELLINGS)):
        old, new = _SPELLINGS[(choice + offset) % len(_SPELLINGS)]
        if old in surname:
            at = surname.index(old)
            return surname[:at] + new + surname[at + len(old) :]
    return surname


def _ref(id: str, kind: str = "Person") -> dict[str, Any]:
    return {"type": kind, "id": id}


def world(
    seed: int = 1,
    people: int = 300,
    mentioned: float = 0.2,
    dated: bool = False,
    compared: bool = False,
) -> World:
    """A world of about `people` people (families of 3 to 7), of whom the share `mentioned` are named once more as a
    mention. `dated`: every statement says when (`when`, a date of `pangloss_dates`), and there are other reports
    of some events and payments made year after year (for models declared with `declare(dated=True)`). `compared`: dated, and with the
    cases of `COMPARED` after everything else (for models declared with `declare(compared=True)`)"""
    rng = random.Random(seed)

    def new_id() -> str:
        return str(uuid.UUID(int=rng.getrandbits(128), version=4))

    families = max(2, people // 5)
    surnames = sorted(
        {
            rng.choice(_ONSETS)
            + rng.choice(_MIDDLES)
            + rng.choice(_ENDS)
            + rng.choice(_SECONDS)
            for _ in range(max(2, families // 2))
        }
    )
    given = list(GIVEN)
    # (unevenly common: the first names of the list are given several times as often as the last)
    weights = [1.0 / (1 + n) ** 0.7 for n in range(len(given))]
    places = [{"type": "Place", "id": new_id(), "label": f"{rng.choice(surnames)}dorf {n}"} for n in range(max(1, families // 8))]  # fmt: skip
    groups = [{"type": "Group", "id": new_id(), "label": f"The guild of {rng.choice(surnames)} {n}"} for n in range(max(1, families // 5))]  # fmt: skip

    everyone: list[Person] = []
    factoids: list[dict[str, Any]] = []
    years: dict[str, int] = {}
    members: dict[str, list[Person]] = {g["id"]: [] for g in groups}
    homes: dict[int, str] = {}
    household: dict[int, list[Person]] = {}
    groups_of: dict[int, list[str]] = {}

    def person(family: int, surname: str, born: int) -> Person:
        name = rng.choices(given, weights)[0]
        said = rng.choice(GIVEN[name]) if rng.random() < 0.15 else name
        made = Person(new_id(), name, surname, family, born, f"{said} {surname}")
        everyone.append(made)
        return made

    def factoid(label: str, year: int, statements: list[dict[str, Any]]) -> None:
        label = f"{label} ({len(factoids)})"
        factoids.append({"type": "Factoid", "label": label, "statements": statements})
        years[label] = year

    def activity(label: str, by: str, others: list[str], place: str) -> dict[str, Any]:
        return {
            "type": "Activity",
            "label": label,
            "carried_out_by": _ref(by),
            "participants": [
                {
                    "type": "InRole",
                    "role": rng.choice(ROLES),
                    "at": _ref(place, "Place"),
                    "target": [_ref(other)],
                }
                for other in others
            ],
        }

    for family in range(families):
        surname = rng.choice(surnames)
        married = 1400 + rng.randrange(200)
        parents = [
            person(family, surname, married - 20 - rng.randrange(15)) for _ in range(2)
        ]
        children = [person(family, surname, married + 1 + 2 * n + rng.randrange(2)) for n in range(1 + rng.randrange(5))]  # fmt: skip
        household[family] = [*parents, *children]
        homes[family] = rng.choice(places)["id"]
        groups_of[family] = [
            g["id"] for g in rng.sample(groups, min(len(groups), 1 + rng.randrange(2)))
        ]
        for child in children:
            factoid(
                f"The parents of {child.label}",
                child.born,
                [
                    {
                        "type": "ChildOf",
                        "label": f"{child.label}, child of {parent.label}",
                        "child": _ref(child.id),
                        "parent": _ref(parent.id),
                    }  # fmt: skip
                    for parent in parents
                ],
            )
        if len(children) > 1:
            factoid(
                f"The children of {parents[0].label}",
                children[-1].born,
                [
                    {
                        "type": "Sibling",
                        "label": "Brothers and sisters",
                        "people": [_ref(c.id) for c in children],
                    }
                ],
            )
        for adult in parents:
            for group in groups_of[family]:
                members[group].append(adult)
                factoid(
                    f"{adult.label} joins",
                    married + rng.randrange(10),
                    [
                        {
                            "type": "MemberOf",
                            "label": f"{adult.label}, a member",
                            "member": _ref(adult.id),
                            "group": _ref(group, "Group"),
                        }
                    ],  # fmt: skip
                )

    def company(person_: Person, most: int) -> list[str]:
        """People the person is found with: of the family, and of the family's groups"""
        near = [p for p in household[person_.family] if p.id != person_.id]
        for group in groups_of[person_.family]:
            near += [
                p
                for p in rng.sample(members[group], min(2, len(members[group])))
                if p.id != person_.id
            ]
        chosen = rng.sample(near, min(most, len(near)))
        return list(dict.fromkeys(p.id for p in chosen))

    for family in range(families):
        parents = household[family][:2]
        for _ in range(3):
            host = rng.choice(household[family])
            factoid(
                f"A gathering at the house of {host.label}",
                host.born + 20 + rng.randrange(30),
                [
                    activity(
                        f"{host.label} gathers people",
                        host.id,
                        company(host, 3),
                        homes[family],
                    )
                ],
            )
        for giver in parents:
            fellows = [
                p for g in groups_of[family] for p in members[g] if p.id != giver.id
            ]
            if not fellows:
                continue
            receiver = rng.choice(fellows)
            given_to: dict[str, Any] = _ref(receiver.id)
            other = rng.choice(everyone)
            if rng.random() < 0.1 and other.id not in (receiver.id, giver.id):
                given_to = {
                    "type": "Identification",
                    "target": [
                        {
                            "type": "WeightedAlternative",
                            "alternatives": [
                                {
                                    **_ref(receiver.id),
                                    "edge_properties": {"percent": 70},
                                },
                                {**_ref(other.id), "edge_properties": {"percent": 30}},
                            ],
                        }
                    ],
                }
            factoid(
                f"A gift of {giver.label}",
                giver.born + 25 + rng.randrange(25),
                [
                    {
                        "type": "Transfer",
                        "label": f"{giver.label} gives",
                        "given_by": _ref(giver.id),
                        "given_to": given_to,
                    }
                ],  # fmt: skip
            )

    mentions: list[Mention] = []
    for known in rng.sample(everyone, int(len(everyone) * mentioned)):
        kind = rng.choice(KINDS)
        name = (
            rng.choice(GIVEN[known.given])
            if kind in ("variant", "both")
            else known.given
        )
        surname = respelled(known.surname, rng.randrange(len(_SPELLINGS))) if kind in ("spelling", "both") else known.surname  # fmt: skip
        if f"{name} {surname}" == f"{known.given} {known.surname}":
            kind = "same"
        mention = Mention(new_id(), f"{name} {surname}", known.id, kind)
        mentions.append(mention)
        others = company(known, 3)
        by, named = (
            (others[0], [mention.id, *others[1:]]) if others else (mention.id, [])
        )
        factoid(
            f"A hearing that names {mention.label}",
            known.born + 20 + rng.randrange(30),
            [
                activity(
                    f"A hearing with {mention.label}", by, named, homes[known.family]
                )
            ],
        )
    made = World(seed, everyone, groups, places, factoids, mentions, years)
    if dated or compared:
        _date(made, household, groups_of, homes)
    if compared:
        _compare(made, household, groups_of, homes, members)
    return made


def _exact(year: int, month: int | None = None, day: int | None = None) -> dict:
    said: dict[str, Any] = {"type": "ExactDate", "year": year}
    if month is not None:
        said["month"] = month
    if day is not None:
        said["day"] = day
    return said


def _said(rng: random.Random, day: tuple[int, int, int], years: bool = True) -> dict:
    """A day as a source says it: the day, its month, its year, or (`years`) some years it was within"""
    year, month, number = day
    how = rng.random()
    if how < 0.4:
        return _exact(year, month, number)
    if how < 0.55:
        return _exact(year, month)
    if how < 0.85 or not years:
        return _exact(year)
    return {
        "type": "DateRange",
        "not_before": _exact(year - rng.randrange(6)),
        "not_after": _exact(year + rng.randrange(6)),
    }


def _date(
    world: World,
    household: dict[int, list[Person]],
    groups_of: dict[int, list[str]],
    homes: dict[int, str],
) -> None:
    """The dates of a world, with a generator of their own (so that the world without them is the same): every
    statement says when; some gatherings are reported once more; some adults pay dues year after year"""
    rng = random.Random(f"{world.seed} dates")
    days: dict[str, tuple[int, int, int]] = {}
    for factoid in world.factoids:
        label = factoid["label"]
        days[label] = (world.years[label], 1 + rng.randrange(12), 1 + rng.randrange(28))
        world.dates[label] = _said(rng, days[label])
        for statement in factoid["statements"]:
            statement["when"] = world.dates[label]

    def report(label: str, event: str, day: tuple[int, int, int], statement: dict, years: bool = True) -> None:  # fmt: skip
        label = f"{label} ({len(world.factoids)})"
        world.dates[label] = _said(rng, day, years)
        world.factoids.append(
            {
                "type": "Factoid",
                "label": label,
                "statements": [{**statement, "when": world.dates[label]}],
            }
        )
        world.years[label] = day[0]
        world.events.setdefault(event, []).append(label)

    gatherings = [f for f in world.factoids if f["label"].startswith("A gathering")]
    for told in rng.sample(gatherings, len(gatherings) // 6):
        [activity] = told["statements"]
        kept = [p for p in activity["participants"] if rng.random() < 0.7]
        world.events[told["label"]] = [told["label"]]
        report(
            f"Another account of {activity['label']}",
            told["label"],
            days[told["label"]],
            {
                "type": "Activity",
                "label": f"It is said that {activity['label']}",
                "carried_out_by": activity["carried_out_by"],
                "participants": kept,
            },
        )
    for family in sorted(household):
        if rng.random() >= 0.1:
            continue
        payer = rng.choice(household[family][:2])
        group = rng.choice(groups_of[family])
        month, number = 1 + rng.randrange(12), 1 + rng.randrange(28)
        first = payer.born + 25 + rng.randrange(10)
        name = f"The dues of {payer.label} ({family})"
        for year in range(first, first + 6 + rng.randrange(7)):
            event = f"{name}, {year}"
            world.series.setdefault(name, []).append(event)
            for source in ("the roll", "the account book"):
                report(
                    f"{payer.label} pays dues, by {source}",
                    event,
                    (year, month, number),
                    {
                        "type": "Transfer",
                        "label": f"{payer.label} pays dues",
                        "given_by": _ref(payer.id),
                        "given_to": _ref(group, "Group"),
                    },
                    years=False,
                )


def _labels(value: Any) -> Any:
    """The label of every statement of a payload"""
    if isinstance(value, dict):
        if "label" in value:
            yield value["label"]
        value = list(value.values())
    if isinstance(value, list):
        for inner in value:
            yield from _labels(inner)


def _later(day: tuple[int, int, int], days: int) -> tuple[int, int, int]:
    moved = datetime.date(*day) + datetime.timedelta(days=days)
    return (moved.year, moved.month, moved.day)


def _compare(
    world: World,
    household: dict[int, list[Person]],
    groups_of: dict[int, list[str]],
    homes: dict[int, str],
    members: dict[str, list[Person]],
) -> None:
    """The cases of `COMPARED`, with a generator of their own (so that the world without them is the same)"""
    rng = random.Random(f"{world.seed} compared")

    def new_id() -> str:
        return str(uuid.UUID(int=rng.getrandbits(128), version=4))

    families = sorted(household)
    world.sources = [
        {"type": "Source", "id": new_id(), "label": f"The chronicle of {world.places[n % len(world.places)]['label']} ({n})"}
        for n in range(max(2, len(families) // 10))
    ]  # fmt: skip
    source_of: dict[str, str] = {}
    made = [0]
    waiting: list[tuple[str, str, str, tuple[str, ...], str | None]] = []

    def statement(kind: str, text: str, day: Any, **fields: Any) -> dict[str, Any]:
        """A statement with a label of its own. `day`: a day (said exactly), a date as said, or None (no date)"""
        made[0] += 1
        said = _exact(*day) if isinstance(day, tuple) else day
        when = {} if said is None else {"when": said}
        return {"type": kind, "label": f"{text} [c{made[0]}]", **when, **fields}

    def tell(case: str, event: str, told: dict[str, Any], *spaces: str, order: dict[str, Any] | None = None) -> dict[str, Any]:  # fmt: skip
        """Note what a statement tells of, and give it inside its spaces (outermost first), as a factoid or a
        field takes it"""
        waiting.append(
            (
                told["label"],
                case,
                event,
                spaces,
                None if order is None else order["label"],
            )
        )
        for space in reversed(spaces):
            told = {"type": space, "contents": [told]}
        return told

    def factoid(text: str, day: tuple[int, int, int], statements: list[dict[str, Any]], source: str) -> str:  # fmt: skip
        label = f"{text} ({len(world.factoids)})"
        world.factoids.append(
            {
                "type": "Factoid",
                "label": label,
                "statements": statements,
                "source": _ref(source, "Source"),
            }
        )
        world.years[label] = day[0]
        world.dates[label] = _exact(*day)
        source_of[label] = source
        # (what was told and is in this factoid: the other of a pair waits for its own)
        here = set(_labels(statements))
        for told, case, event, spaces, order in [w for w in waiting if w[0] in here]:
            world.told[told] = Told(told, label, case, event, spaces, order)
        waiting[:] = [w for w in waiting if w[0] not in here]
        return label

    def two_sources() -> tuple[str, str]:
        """The sources of the two factoids of a pair: the same one time in five"""
        first = rng.choice(world.sources)["id"]
        if rng.random() < 0.2:
            return first, first
        return first, rng.choice([s["id"] for s in world.sources if s["id"] != first])

    def judge(case: str, a: dict[str, Any], b: dict[str, Any], *fields: str) -> None:
        one, other = world.told[a["label"]], world.told[b["label"]]
        world.verdicts.append(
            Verdict(
                a["label"],
                b["label"],
                RELATION_OF[case],
                case,
                fields,
                one.factoid == other.factoid,
                source_of[one.factoid] == source_of[other.factoid],
            )
        )

    def live(told: dict[str, Any], value: float, grounds: str) -> None:
        world.liveness[told["label"]] = Liveness(value, grounds)

    def a_day(year: int) -> tuple[int, int, int]:
        return (year, 1 + rng.randrange(12), 1 + rng.randrange(28))

    def company(person_: Person, most: int) -> list[str]:
        near = [p for p in household[person_.family] if p.id != person_.id]
        for group in groups_of[person_.family]:
            near += [p for p in rng.sample(members[group], min(2, len(members[group]))) if p.id != person_.id]  # fmt: skip
        chosen = rng.sample(near, min(most, len(near)))
        return list(dict.fromkeys(p.id for p in chosen))

    def roles(others: list[str], place: str) -> list[dict[str, Any]]:
        return [
            {"type": "InRole", "role": rng.choice(ROLES), "at": _ref(place, "Place"), "target": [_ref(other)]}
            for other in others
        ]  # fmt: skip

    def again(told: dict[str, Any], day: Any, **changed: Any) -> dict[str, Any]:
        """The same statement told once more, with a label of its own"""
        kept = {k: v for k, v in told.items() if k not in ("type", "label", "when")}
        return statement(told["type"], told["label"].rsplit(" [c", 1)[0], day, **{**kept, **changed})  # fmt: skip

    born_told: set[str] = set()

    def birth(case: str, family: int) -> None:
        children = [c for c in household[family][2:] if c.id not in born_told]
        others = [p["id"] for p in world.places if p["id"] != homes[family]]
        if not children or (case == "birth_place" and not others):
            return
        child = rng.choice(children)
        born_told.add(child.id)
        day = a_day(child.born)
        event = f"the birth of {child.id}"
        exactly = case == "birth_date"
        first = statement("Birth", f"{child.label} is born", day if exactly else _said(rng, day), person=_ref(child.id), place=_ref(homes[family], "Place"))  # fmt: skip
        if case == "birth_agree":
            second = again(first, _said(rng, day))
        elif case == "birth_place":
            second = again(first, _said(rng, day), place=_ref(rng.choice(others), "Place"))  # fmt: skip
        else:
            second = again(first, _later(day, 400 + rng.randrange(1600)))
        one, other = two_sources()
        factoid(f"The birth of {child.label}", day, [tell(case, event, first)], one)
        factoid(f"Another account of the birth of {child.label}", day, [tell(case, event, second)], other)  # fmt: skip
        judge(case, first, second, *{"birth_place": ["place"], "birth_date": ["when"]}.get(case, []))  # fmt: skip

    def making(case: str, family: int) -> None:
        parents = household[family][:2]
        maker = rng.choice(parents)
        spouse = next(p for p in parents if p.id != maker.id)
        day = a_day(maker.born + 25 + rng.randrange(20))

        def picture() -> dict[str, Any]:
            thing = {"type": "Picture", "id": new_id(), "label": f"A picture from the house of {maker.label} ({len(world.things)})"}  # fmt: skip
            world.things.append(thing)
            return _ref(thing["id"], "Picture")

        thing = picture()
        event = f"the making of {thing['id']}"
        first = statement("Making", f"{maker.label} makes a thing", _said(rng, day), made_by=_ref(maker.id), made=thing)  # fmt: skip
        if case == "making_two":
            another = picture()
            second = statement("Making", f"{maker.label} makes a thing", _later(day, 30 + rng.randrange(300)), made_by=_ref(maker.id), made=another)  # fmt: skip
            events = (event, f"the making of {another['id']}")
        else:
            by = spouse if case == "making_maker" else maker
            second = statement("MakingOfPicture", f"{by.label} paints a picture", _said(rng, day), made_by=_ref(by.id), picture_made=thing)  # fmt: skip
            events = (event, event)
        one, other = two_sources()
        factoid(f"A thing made by {maker.label}", day, [tell(case, events[0], first)], one)  # fmt: skip
        factoid(f"A picture and its maker, {maker.label}", day, [tell(case, events[1], second)], other)  # fmt: skip
        judge(case, first, second, *(["made_by"] if case == "making_maker" else []))

    # Of a gathering told by a second source: the spaces of the second (and of the first, where it does not assert)
    second_spaces: dict[str, tuple[tuple[str, ...], tuple[str, ...]]] = {
        "gathering_denied": ((), ("Negative",)),
        "gathering_might": ((), ("Hypothetical",)),
        "gathering_cannot": ((), ("Negative", "Hypothetical")),
        "gathering_reported": ((), ("Reported",)),
        "gathering_reported_not": ((), ("Reported", "Negative")),
        "gathering_believed": ((), ("Believed",)),
        "gathering_believed_not": ((), ("Believed", "Negative")),
        "reports_compatible": (("Reported",), ("Believed",)),
        "reports_at_odds": (("Reported",), ("Believed", "Negative")),
        "self_contradiction": ((), ("Negative",)),
    }

    def gathering(case: str, family: int) -> None:
        host = rng.choice(household[family])
        others = company(host, 3)
        if not others:
            return
        day = a_day(host.born + 20 + rng.randrange(30))
        made[0] += 1
        event = f"the gathering {made[0]}"
        events = (event, event)
        fields: list[str] = []
        exactly = case in ("gathering_date", "gathering_two")
        first = statement("Activity", f"{host.label} gathers people", day if exactly else _said(rng, day), carried_out_by=_ref(host.id), participants=roles(others, homes[family]))  # fmt: skip
        if case == "gathering_participant":
            stranger = rng.choice([p for p in world.people if p.id != host.id and p.id not in others])  # fmt: skip
            second = again(first, _said(rng, day), participants=roles([*others[:-1], stranger.id], homes[family]))  # fmt: skip
            fields = ["participants"]
        elif case == "gathering_date":
            second = again(first, _later(day, rng.choice([-1, 1]) * (2 + rng.randrange(19))))  # fmt: skip
            fields = ["when"]
        elif case == "gathering_two":
            second = again(first, _later(day, 300 + rng.randrange(600)))
            made[0] += 1
            events = (event, f"the gathering {made[0]}")
        else:
            kept = [p for p in first["participants"] if rng.random() < 0.7]
            second = again(first, _said(rng, day), participants=kept)
        before, after = second_spaces.get(case, ((), ()))
        items = [tell(case, events[0], first, *before), tell(case, events[1], second, *after)]  # fmt: skip
        if "Hypothetical" in after and after[0] == "Hypothetical":
            # (how likely, as whoever enters it says: for some)
            if (degree := rng.choice([None, "possible", "likely"])) is not None:
                items[1]["how_likely"] = degree
        if case in ("self_contradiction", "entered_twice"):
            factoid(f"A gathering at the house of {host.label}, told twice", day, items, rng.choice(world.sources)["id"])  # fmt: skip
        else:
            one, other = two_sources()
            factoid(f"A gathering at the house of {host.label}", day, [items[0]], one)  # fmt: skip
            factoid(f"What is said of a gathering at the house of {host.label}", day, [items[1]], other)  # fmt: skip
        judge(case, first, second, *fields)
        if "Negative" in after:
            live(second, 1.0, "reported")

    def order(case: str, family: int) -> None:
        orderer = rng.choice(household[family][:2])
        group = rng.choice(groups_of[family])
        doers = [p for p in members[group] if p.id != orderer.id]
        if not doers:
            return
        doer = rng.choice(doers)
        receivers = [p for p in household[family] if p.id not in (orderer.id, doer.id)]
        if not receivers:
            return
        receiver = rng.choice(receivers)
        target = a_day(orderer.born + 25 + rng.randrange(25))
        ordered = _later(target, -(10 + rng.randrange(50)))
        made[0] += 1
        event = f"the giving {made[0]}"
        to = _ref(group, "Group") if case == "orders_at_odds" else _ref(receiver.id)
        to_label = "the group" if case == "orders_at_odds" else receiver.label
        text = f"{doer.label} gives to {to_label}"
        space = {"forbidden_kept": "Forbidden", "forbidden_broken": "Forbidden", "orders_at_odds": "Forbidden", "permission_used": "Permitted"}.get(case, "Ordered")  # fmt: skip
        # (the date in an order is a target; what is forbidden or allowed has none)
        thing = statement("Transfer", text, target if space == "Ordered" else None, given_by=_ref(doer.id), given_to=to)  # fmt: skip
        said = statement("Order", f"{orderer.label} orders {doer.label}", ordered, ordered_by=_ref(orderer.id), ordered_to=[_ref(doer.id)])  # fmt: skip
        said["thing_ordered"] = tell(case, event, thing, space, order=said)
        said = tell(case, f"{event}, ordered", said)
        if case == "orders_at_odds":
            obliged = statement("Transfer", text, None, given_by=_ref(doer.id), given_to=to)  # fmt: skip
            rule = statement("Rule", "The statute of the group", _later(ordered, -rng.randrange(2000)), ruled_by=_ref(group, "Group"), binds=[_ref(doer.id)])  # fmt: skip
            rule["ruled"] = tell(case, event, obliged, "Obliged", order=rule)
            rule = tell(case, f"{event}, ruled", rule)
            one, other = two_sources()
            factoid(f"An order of {orderer.label}", ordered, [said], one)
            factoid("A statute of the group", ordered, [rule], other)
            judge(case, thing, obliged)
            return
        if case in ("order_on_time", "order_not"):
            came = target
        elif case == "order_late":
            came = _later(target, 1 + rng.randrange(30))
        else:
            came = _later(ordered, 5 + rng.randrange(200))
        denied = case in ("order_not", "forbidden_kept")
        outcome = statement("Transfer", text, came, given_by=_ref(doer.id), given_to=to)  # fmt: skip
        item = tell(case, event, outcome, *(("Negative",) if denied else ()))
        if rng.random() < 0.3:
            factoid(f"An order of {orderer.label}, and what came of it", ordered, [said, item], rng.choice(world.sources)["id"])  # fmt: skip
        else:
            one, other = two_sources()
            factoid(f"An order of {orderer.label}", ordered, [said], one)
            factoid(f"What {doer.label} did", came, [item], other)
        judge(case, thing, outcome, *(["when"] if case == "order_late" else []))
        if denied:
            live(outcome, 1.0, "ordered" if case == "order_not" else "forbidden")

    for family in families:
        for case, share in COMPARED.items():
            if case.startswith("absence") or rng.random() >= share:
                continue
            if case.startswith("birth"):
                birth(case, family)
            elif case.startswith("making"):
                making(case, family)
            elif case.startswith(("order", "forbidden", "permission")):
                order(case, family)
            else:
                gathering(case, family)

    # The assemblies: who was there, and who is said not to have been
    group_families = {g["id"]: {f for f in families if g["id"] in groups_of[f]} for g in world.groups}  # fmt: skip
    for group in world.groups:
        of = members[group["id"]]
        if len(of) < 3:
            continue
        day = a_day(max(p.born for p in of) + 25 + rng.randrange(10))
        present = rng.sample(of, min(len(of) - 1, 2 + rng.randrange(4)))
        missing = [p for p in of if p not in present]
        absent = [(p, 1.0, "member", "absence_expected") for p in rng.sample(missing, min(len(missing), 1 + rng.randrange(2)))]  # fmt: skip
        strangers = [p for p in world.people if p.family not in group_families[group["id"]]]  # fmt: skip
        if strangers and rng.random() < COMPARED["absence_unexpected"]:
            absent.append((rng.choice(strangers), 0.0, "none", "absence_unexpected"))
        items = []

        def attendance(
            person_: Person,
            day: tuple[int, int, int] = day,
            group: dict[str, Any] = group,
        ) -> dict[str, Any]:
            return statement(
                "Attendance",
                f"{person_.label} at the assembly",
                day,
                attended_by=_ref(person_.id),
                assembly_of=_ref(group["id"], "Group"),
            )

        for person_ in present:
            items.append(tell("present", f"{person_.id} at the assembly of {group['id']}", attendance(person_)))  # fmt: skip
        for person_, value, grounds, case in absent:
            told = attendance(person_)
            items.append(tell(case, f"{person_.id} at the assembly of {group['id']}", told, "Negative"))  # fmt: skip
            live(told, value, grounds)
        factoid(f"The roll of the assembly of {group['label']}", day, items, rng.choice(world.sources)["id"])  # fmt: skip


def places(
    world: World, people: Any, mentions: Any, tolerance: float = 1e-6
) -> list[tuple[int, int, str]]:
    """How well vectors find who a mention is. `people` and `mentions` are arrays (numpy, which is imported only
    here) with a row of length one, or of zeros, for each of `world.people` and `world.mentions`, in their order.
    For each mention: how many people are nearer it than the person it is, how many are as near as that person
    (the person among them, so 1 or more: namesakes have the same name vector), and the mention's kind"""
    import numpy as np

    row = {person.id: n for n, person in enumerate(world.people)}
    found = []
    for start in range(0, len(world.mentions), 500):
        chunk = world.mentions[start : start + 500]
        scores = np.asarray(mentions[start : start + 500]) @ np.asarray(people).T
        for n, mention in enumerate(chunk):
            right = scores[n, row[mention.person]]
            before = int((scores[n] > right + tolerance).sum())
            tied = int((np.abs(scores[n] - right) <= tolerance).sum())
            found.append((before, tied, mention.kind))
    return found


def within(found: list[tuple[int, int, str]], most: int) -> float:
    """The share of mentions whose person is among the `most` nearest, the people as near as the person counted
    before them (the worst case)"""
    if not found:
        raise ValueError("No mention to rank: a world made with `mentioned=0` has none")
    return sum(1 for before, tied, _ in found if before + tied <= most) / len(found)
