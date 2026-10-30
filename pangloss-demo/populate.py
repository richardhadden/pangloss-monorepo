"""Put some data in the demo database: a few factoids about the year 800.

    python populate.py            # (from this directory; see docs/demo-setup.md)

The database must be set up (`pangloss setup-database`) and have a user called `demo`
(`pangloss users create`): what is written is recorded as written by them. It refuses to
run twice, as the entities have fixed URLs.
"""

import asyncio
import datetime
import sys

from demo_app import models
from pangloss_cli.project import load_project
from pangloss_models import initialise
from pangloss_users import current_request_username
from pydantic import AnyHttpUrl

USERNAME = "demo"
BASE = "https://example.org/demo"


def url(kind: str, name: str) -> AnyHttpUrl:
    return AnyHttpUrl(f"{BASE}/{kind}/{name}")


def date(year: int, month: int | None = None, day: int | None = None) -> dict:
    """A date (Julian: that is the setting), as exact as it is given: `date(800)` is the year, `date(800, 12, 25)` the day"""
    given = {"year": year, "month": month, "day": day}
    return {"type": "ExactDate", **{k: v for k, v in given.items() if v}}


def edtf(text: str) -> dict:
    """A date written in EDTF: `1500-03~` is about March 1500"""
    return {"type": "EDTFDate", "edtf": text}


def ref(entity, type: str | None = None) -> dict:
    """A reference to an entity that has been saved"""
    return {"type": type or entity.type, "id": entity.id}


def via(entity, certainty: int) -> dict:
    """A reference to an entity, with how certain the source is of the relation"""
    return {**ref(entity), "edge_properties": {"level": certainty}}


def in_role(entity, role: str) -> dict:
    return {"type": "InRole", "role": role, "target": [ref(entity)]}


async def already_populated() -> bool:
    return (
        await models.Source.get(id=url("source", "annales-regni-francorum")) is not None
    )


async def populate() -> None:
    # --- The vocabulary of occupations -----------------------------------------------
    ruler = await models.OccupationTypology.create("Ruler")
    king = await models.OccupationTypology.create("King", supertype=ruler.id)
    cleric = await models.OccupationTypology.create("Cleric")
    pope = await models.OccupationTypology.create("Pope", supertype=cleric.id)
    scholar = await models.OccupationTypology.create("Scholar")
    count = await models.OccupationTypology.create("Count", supertype=ruler.id)

    def typed(*types) -> list[dict]:
        return [{"type": "OccupationType", "id": t.id} for t in types]

    # --- Entities ----------------------------------------------------------
    charlemagne = await models.Person.Create(
        id=url("person", "charlemagne"),
        create_new=True,
        label="Charlemagne",
        known_as={"value": "Karolus Magnus", "certainty": 5},
        born=date(748),
        aliases=["Charles the Great", "Carolus"],
        has_type=typed(king),
    ).save()
    leo = await models.Person.Create(
        id=url("person", "leo-iii"),
        create_new=True,
        label="Pope Leo III",
        known_as={"value": "Leo", "certainty": 5},
        born=edtf("075X"),
        aliases=[],
        has_type=typed(pope),
    ).save()
    # (two men the sources call "Wido": see the last factoid)
    wido_of_spoleto = await models.Person.Create(
        label="Wido of Spoleto",
        known_as={"value": "Wido", "certainty": 4},
        born=edtf("0770~"),
        aliases=[],
        has_type=typed(count),
    ).save()
    wido_of_brittany = await models.Person.Create(
        label="Wido, prefect of the Breton March",
        known_as={"value": "Wido", "certainty": 4},
        born=edtf("0750~"),
        aliases=[],
        has_type=typed(count),
    ).save()
    frankish_army = await models.Group.Create(
        label="The Frankish army", name="Franks"
    ).save()
    roman_church = await models.Group.Create(
        label="The Roman Church", name="Roman Church"
    ).save()

    rome = await models.Place.Create(
        label="Rome", coordinates={"latitude": 41.9, "longitude": 12.5}
    ).save()
    peters = await models.Place.Create(
        label="Old St Peter's Basilica",
        coordinates={"latitude": 41.902, "longitude": 12.453},
    ).save()
    paderborn = await models.Place.Create(label="Paderborn").save()

    annales = await models.Source.Create(
        id=url("source", "annales-regni-francorum"),
        create_new=True,
        label="Annales regni Francorum",
        written=datetime.date(829, 1, 1),
    ).save()

    # --- A factoid: the coronation -------------------------------------------------
    # `year` is given once, on the factoid: the statements get it too. A statement can
    # be a Negative or Hypothetical one, or two that cause one another.
    coronation = await models.Factoid.Create(
        label="Charlemagne is crowned emperor",
        year=800,
        source={"type": "AtPage", "page": "s.a. 800", "target": [ref(annales)]},
        statements=[
            {
                "type": "Activity",
                "label": "Leo crowns Charlemagne",
                "text": "On Christmas Day, Leo placed a crown on Charlemagne's head",
                "date": date(800, 12, 25),
                "activity_type": "ceremony",
                "carried_out_by": via(leo, certainty=5),
                "participants": [
                    in_role(charlemagne, "participant"),
                    in_role(frankish_army, "witness"),
                ],
                "places": [ref(peters)],
            },
            {
                "type": "Causes",
                "cause": {
                    "type": "Activity",
                    "label": "The people acclaim Charlemagne",
                    "text": "The Roman people shouted three times: long life to Charles",
                    "date": date(800, 12, 25),
                    "activity_type": "ceremony",
                    "carried_out_by": via(roman_church, certainty=3),
                    "participants": [],
                    "places": [ref(peters)],
                },
                "result": {
                    "type": "Transfer",
                    "label": "Charlemagne's gifts",
                    "text": "Charlemagne gave silver to the church of St Peter",
                    "date": date(800, 12),
                    "item": "silver, in talents",
                    "quantity": "2.5",
                    "given_by": ref(charlemagne),
                    "given_to": ref(roman_church),
                    "places": [ref(peters)],
                },
            },
            {
                "type": "Hypothetical",
                "contents": [
                    {
                        "type": "Activity",
                        "label": "A coronation at Paderborn",
                        "text": "It was said the crown might have been given at Paderborn",
                        "date": date(799, 7),
                        "activity_type": "meeting",
                        "carried_out_by": via(leo, certainty=1),
                        "participants": [in_role(charlemagne, "leader")],
                        "places": [ref(paderborn)],
                    }
                ],
            },
        ],
    ).save()

    # --- A factoid with its source written in it --------------------------------------
    # (the source, and the person, are made by the same request that makes the factoid)
    einhard_life = await models.Factoid.Create(
        label="Charlemagne did not expect to be crowned",
        year=800,
        source={
            "type": "AtPage",
            "page": "ch. 28",
            "target": [
                {
                    "type": "Source",
                    "id": url("source", "vita-karoli"),
                    "create_new": True,
                    "label": "Vita Karoli Magni",
                    "author": "Einhard",
                    "written": datetime.date(828, 1, 1),
                    "edition_price": "12.50",
                }
            ],
        },
        statements=[
            {
                "type": "Negative",
                "contents": [
                    {
                        "type": "Activity",
                        "label": "Charlemagne knew of the coronation",
                        "text": "Charlemagne would not have entered the church, had he known",
                        # (no `year`: it is Factoid.year)
                        "date": date(800, 12, 25),
                        "activity_type": "ceremony",
                        "carried_out_by": via(charlemagne, certainty=4),
                        "participants": [in_role(leo, "leader")],
                        "places": [ref(peters)],
                    }
                ],
            },
            {
                "type": "Activity",
                "label": "Charlemagne goes to Rome",
                "text": "He went to Rome to restore the state of the church",
                "date": date(800, 11, 24),
                "activity_type": "journey",
                "carried_out_by": via(charlemagne, certainty=5),
                "participants": [in_role(frankish_army, "participant")],
                "places": [ref(rome)],
            },
        ],
    ).save()

    # --- A letter, with a person written in it -------------------------------------------
    # (an entity can be written in the request that refers to it; not where the relation has
    # properties of its own, as `carried_out_by` does)
    letter = await models.Factoid.Create(
        label="Alcuin sends Charlemagne a letter",
        year=799,
        source={
            "type": "AtPage",
            "page": "letter 174",
            "target": [ref(await models.Source.get(id=url("source", "vita-karoli")))],
        },
        statements=[
            {
                "type": "Transfer",
                "label": "Alcuin's letter",
                "text": "Alcuin sent the king a letter about the dangers to the church",
                "date": date(799, 6),
                "year": 799,  # (the factoid's year is not used where there is one)
                "item": "letter",
                "quantity": "1",
                "given_by": {
                    "type": "Person",
                    "id": url("person", "alcuin"),
                    "create_new": True,
                    "label": "Alcuin of York",
                    "known_as": {"value": "Flaccus", "certainty": 3},
                    "born": edtf("0735~"),
                    "aliases": ["Albinus"],
                    "has_type": typed(scholar, cleric),
                },
                "given_to": ref(charlemagne),
                "places": [],
            }
        ],
    ).save()

    # --- Orders, and a name that could be one of two men ------------------------------
    # An order holds another statement, said in a subjunctive space: it was wished (or
    # wished not), and not necessarily done. In the Transfer, the source says only
    # "Wido": `Identification` records that, and the `Alternative` it is identified with
    # holds both men, each with how likely it is that he is the one meant.
    def identified(name: str, alternatives: list[tuple]) -> dict:
        return {
            "type": "Identification",
            "identified_by": name,
            "target": [
                {
                    "type": "Alternative",
                    "alternatives": [
                        {**ref(person), "edge_properties": {"percent": percent}}
                        for person, percent in alternatives
                    ],
                }
            ],
        }

    orders = await models.Factoid.Create(
        label="Charlemagne orders gifts, and forbids a trade",
        year=802,
        source={"type": "AtPage", "page": "s.a. 802", "target": [ref(annales)]},
        statements=[
            {
                "type": "Order",
                "label": "Charlemagne orders a gift to Wido",
                "text": "The emperor ordered that silver be given to Wido",
                "date": date(802, 3),
                "ordered_by": ref(charlemagne),
                "places": [ref(paderborn)],
                "thing_ordered": {
                    "type": "PositiveSubjunctive",
                    "contents": [
                        {
                            "type": "Transfer",
                            "label": "Silver for Wido",
                            "text": "Silver was to be given to Wido for his service",
                            "date": date(802, 3),
                            "item": "silver, in talents",
                            "quantity": "1",
                            "given_by": ref(charlemagne),
                            "given_to": identified(
                                "Wido", [(wido_of_spoleto, 70), (wido_of_brittany, 30)]
                            ),
                            "places": [],
                        }
                    ],
                },
            },
            {
                "type": "Order",
                "label": "Charlemagne forbids the sale of arms",
                "text": "He commanded that no arms be sold beyond the border",
                "date": date(802, 10),
                "ordered_by": identified("the lord", [(charlemagne, 90), (leo, 10)]),
                "places": [],
                "thing_ordered": {
                    "type": "NegativeSubjunctive",
                    "contents": [
                        {
                            "type": "Transfer",
                            "label": "Arms sold abroad",
                            "text": "Arms were sold to the Saxons across the border",
                            "date": date(802, 10),
                            "item": "swords",
                            "quantity": "40",
                            "given_by": ref(frankish_army),
                            "given_to": ref(roman_church),
                            "places": [],
                        }
                    ],
                },
            },
        ],
    ).save()

    print("Wrote 4 factoids:")
    for factoid in (coronation, einhard_life, letter, orders):
        print(f"  {factoid.id}  {factoid.label}")


async def main() -> None:
    project = load_project()
    if project.settings is None:
        sys.exit(project.settings_error)
    backend = project.require_database()
    project.import_models()
    initialise()

    # (what is written is recorded as written by this user)
    current_request_username.set(USERNAME)

    await backend.connect()
    try:
        if await already_populated():
            sys.exit("The database already has the demo data: nothing was written")
        await populate()
    finally:
        await backend.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
