"""A planted prosopography with a known truth, on the models of `pangloss_testing.similar_models`: what the parts of
similarity are measured on (implementation_docs/similarity-build-plan.md, step 8.1). No database and nothing but the
standard library: the same seed gives the same world, in any process.

    world = planted.world(seed=1, people=300)
    world.entities      the `Create` payloads of the people (the mentions among them), groups and places, with ids
    world.factoids      the `Create` payloads of the factoids that name them
    world.mentions      the truth: for each mention (a person as one source spells them), who it is
    world.variants      the given names: each canonical form and its variants
    world.years         the year of each factoid, by its label (for the time part: the models have no dates yet)

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

Sizes: a family is about 5 people and 47 stored nodes of the models, so `people=32_000` is about 300,000 of them
(measured: 122,777 records, 302,239 nodes of the models; 629,927 nodes with the records of who made each and the
marks that writes leave for the workers).
"""

import dataclasses
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
    """`same` name, another `spelling` of the surname, a `variant` of the given name, or `both`"""


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

    def truth(self) -> dict[str, Any]:
        """What is true of the world and not said in it, as JSON can say it"""
        return {
            "seed": self.seed,
            "people": [dataclasses.asdict(p) for p in self.people],
            "mentions": [dataclasses.asdict(m) for m in self.mentions],
            "namesakes": self.namesakes,
            "variants": self.variants,
            "years": self.years,
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


def world(seed: int = 1, people: int = 300, mentioned: float = 0.2) -> World:
    """A world of about `people` people (families of 3 to 7), of whom the share `mentioned` are named once more as a
    mention"""
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
    return World(seed, everyone, groups, places, factoids, mentions, years)


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
    return sum(1 for before, tied, _ in found if before + tied <= most) / len(found)
