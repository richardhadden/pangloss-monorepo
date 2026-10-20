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


def date(year: int, month: int = 1, day: int = 1, precision: str = "day") -> dict:
    return {"when": datetime.date(year, month, day), "precision": precision}


def ref(entity, type: str | None = None) -> dict:
    """A reference to an entity that has been saved"""
    return {"type": type or entity.type, "id": entity.id}


def via(entity, certainty: int) -> dict:
    """A reference to an entity, with how certain the source is of the relation"""
    return {**ref(entity), "edge_properties": {"level": certainty}}


def in_role(entity, role: str) -> dict:
    return {"type": "InRole", "role": role, "target": [ref(entity)]}


async def already_populated() -> bool:
    return await models.Source.get(id=url("source", "annales-regni-francorum")) is not None


async def populate() -> None:
    # --- Entities ----------------------------------------------------------
    charlemagne = await models.Person.Create(
        id=url("person", "charlemagne"),
        create_new=True,
        label="Charlemagne",
        known_as={"value": "Karolus Magnus", "certainty": 5},
        born=date(748, precision="year"),
        aliases=["Charles the Great", "Carolus"],
    ).save()
    leo = await models.Person.Create(
        id=url("person", "leo-iii"),
        create_new=True,
        label="Pope Leo III",
        known_as={"value": "Leo", "certainty": 5},
        born=date(750, precision="decade"),
        aliases=[],
    ).save()
    frankish_army = await models.Group.Create(label="The Frankish army", name="Franks").save()
    roman_church = await models.Group.Create(label="The Roman Church", name="Roman Church").save()

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
                    "date": date(800, 12, 26, precision="month"),
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
                        "date": date(799, 7, 1, precision="month"),
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
                "date": date(799, 6, 1, precision="month"),
                "year": 799,  # (the factoid's year is not used where there is one)
                "item": "letter",
                "quantity": "1",
                "given_by": {
                    "type": "Person",
                    "id": url("person", "alcuin"),
                    "create_new": True,
                    "label": "Alcuin of York",
                    "known_as": {"value": "Flaccus", "certainty": 3},
                    "born": date(735, precision="decade"),
                    "aliases": ["Albinus"],
                },
                "given_to": ref(charlemagne),
                "places": [],
            }
        ],
    ).save()

    print("Wrote 3 factoids:")
    for factoid in (coronation, einhard_life, letter):
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
