"""Put 2000 made-up people in the demo database, so that a list is long enough to scroll.

    python add_people.py          # (from this directory, after populate.py)

The names are from Monty Python, the Biggles books and other fiction: each canonical name
once, then first names and surnames from them put together. Each person has a fixed URL
(`.../person/literary-0001`), so it refuses to run twice.
"""

import asyncio
import random
import sys

from demo_app import models
from pangloss_cli import load_project
from pangloss_models import initialise
from pangloss_users import current_request_username
from pydantic import AnyHttpUrl

USERNAME = "demo"
BASE = "https://example.org/demo"
HOW_MANY = 2000

CANONICAL = [
    # Monty Python
    "Arthur, King of the Britons",
    "Sir Lancelot the Brave",
    "Sir Robin the Not-Quite-So-Brave",
    "Sir Galahad the Pure",
    "Sir Bedevere the Wise",
    "Patsy",
    "Tim the Enchanter",
    "Brian Cohen",
    "Reg",
    "Stan (Loretta)",
    "Biggus Dickus",
    "Incontinentia Buttocks",
    "Pontius Pilate",
    "Mandy Cohen",
    "Arthur Pewtey",
    "Mr Praline",
    "Mr Creosote",
    "Arthur Putey",
    "Dinsdale Piranha",
    "Doug Piranha",
    "Mr Gumby",
    "Spiny Norman",
    "Raymond Luxury-Yacht",
    "Ken Shabby",
    "Cardinal Ximénez",
    "Cardinal Biggles",
    "Cardinal Fang",
    "Mrs Premise",
    "Mrs Conclusion",
    "The Colonel",
    "Arthur Two Sheds Jackson",
    "Luigi Vercotti",
    "Eric Praline",
    "Mr Smoke-Too-Much",
    "Brother Maynard",
    "Roger the Shrubber",
    "Dennis the Peasant",
    "Mr Hilter",
    "Ron Obvious",
    "Mr Pither",
    # Biggles
    "James Bigglesworth",
    "Algernon Lacey",
    "Ginger Hebblethwaite",
    "Bertram Lissie",
    "Air Commodore Raymond",
    "Erich von Stalhein",
    "Wilks",
    "Smyth",
    "Tex O'Hara",
    "Tug Carrington",
    "Taffy Hughes",
    "Ferocity Blane",
    "Angus Mackail",
    "Henry Ponsonby",
    "Otto Brunow",
    "Bigglesworth Senior",
    "Marie Janis",
    "Flight Sergeant Smyth",
    # Wodehouse
    "Bertie Wooster",
    "Reginald Jeeves",
    "Aunt Agatha",
    "Aunt Dahlia",
    "Gussie Fink-Nottle",
    "Tuppy Glossop",
    "Madeline Bassett",
    "Roderick Spode",
    "Stiffy Byng",
    "Bingo Little",
    "Lord Emsworth",
    "Psmith",
    "Ukridge",
    "Galahad Threepwood",
    # Dickens
    "Samuel Pickwick",
    "Sam Weller",
    "Wilkins Micawber",
    "Uriah Heep",
    "Ebenezer Scrooge",
    "Bob Cratchit",
    "Miss Havisham",
    "Abel Magwitch",
    "Seth Pecksniff",
    "Sarah Gamp",
    "Wackford Squeers",
    "Mr Bumble",
    "Fagin",
    "Jack Dawkins",
    "Nicholas Nickleby",
    # Others
    "Don Quixote de la Mancha",
    "Sancho Panza",
    "Tristram Shandy",
    "Uncle Toby",
    "Baron Munchausen",
    "Gulliver",
    "Candide",
    "Doctor Pangloss",
    "Cunégonde",
    "Sherlock Holmes",
    "John Watson",
    "Mycroft Holmes",
    "Professor Moriarty",
    "Phileas Fogg",
    "Jean Passepartout",
    "Captain Nemo",
    "Long John Silver",
    "Ben Gunn",
    "Mr Toad",
    "Ratty",
    "Mole",
    "Badger",
    "Captain Haddock",
    "Professor Calculus",
    "Lucky Jim Dixon",
    "Ignatius J. Reilly",
    "Arthur Dent",
    "Ford Prefect",
    "Zaphod Beeblebrox",
    "Rincewind",
    "Granny Weatherwax",
    "Nanny Ogg",
    "Sam Vimes",
    "Cohen the Barbarian",
    "Flashman",
    "Horatio Hornblower",
    "Lemuel Gulliver",
    "Mrs Malaprop",
    "Lady Bracknell",
    "Algernon Moncrieff",
    "Jack Worthing",
    "Bulldog Drummond",
    "Lord Peter Wimsey",
    "Mervyn Bunter",
    "Augustus Fink",
]

FIRST = [
    "Arthur",
    "Lancelot",
    "Robin",
    "Galahad",
    "Bedevere",
    "Brian",
    "Reg",
    "Dinsdale",
    "Doug",
    "Raymond",
    "Ken",
    "Eric",
    "Ron",
    "Roger",
    "Dennis",
    "Luigi",
    "Biggus",
    "James",
    "Algernon",
    "Algy",
    "Ginger",
    "Bertie",
    "Erich",
    "Tug",
    "Taffy",
    "Angus",
    "Henry",
    "Otto",
    "Marie",
    "Reginald",
    "Augustus",
    "Gussie",
    "Tuppy",
    "Madeline",
    "Roderick",
    "Stiffy",
    "Bingo",
    "Clarence",
    "Galahad",
    "Samuel",
    "Wilkins",
    "Uriah",
    "Ebenezer",
    "Abel",
    "Seth",
    "Sarah",
    "Wackford",
    "Nicholas",
    "Tristram",
    "Toby",
    "Lemuel",
    "Phileas",
    "Jean",
    "Sherlock",
    "Mycroft",
    "Horatio",
    "Ignatius",
    "Ford",
    "Zaphod",
    "Esmerelda",
    "Gytha",
    "Samuel",
    "Harry",
    "Peter",
    "Mervyn",
    "Gwendolen",
    "Cecily",
    "Hugo",
    "Percy",
    "Archibald",
    "Hildegard",
    "Agatha",
    "Dahlia",
    "Cuthbert",
    "Montague",
    "Ermintrude",
    "Wilfred",
    "Cyril",
    "Basil",
    "Hector",
    "Lavinia",
]

SURNAMES = [
    "Pewtey",
    "Praline",
    "Creosote",
    "Piranha",
    "Gumby",
    "Luxury-Yacht",
    "Shabby",
    "Vercotti",
    "Pither",
    "Obvious",
    "Two Sheds",
    "Jackson",
    "Bigglesworth",
    "Lacey",
    "Hebblethwaite",
    "Lissie",
    "von Stalhein",
    "Carrington",
    "Hughes",
    "Blane",
    "Mackail",
    "Ponsonby",
    "Brunow",
    "Wooster",
    "Fink-Nottle",
    "Glossop",
    "Bassett",
    "Spode",
    "Byng",
    "Little",
    "Threepwood",
    "Ukridge",
    "Pickwick",
    "Weller",
    "Micawber",
    "Heep",
    "Scrooge",
    "Cratchit",
    "Havisham",
    "Magwitch",
    "Pecksniff",
    "Gamp",
    "Squeers",
    "Bumble",
    "Nickleby",
    "Shandy",
    "Munchausen",
    "Panza",
    "Holmes",
    "Watson",
    "Moriarty",
    "Fogg",
    "Passepartout",
    "Silver",
    "Gunn",
    "Haddock",
    "Dixon",
    "Reilly",
    "Dent",
    "Prefect",
    "Beeblebrox",
    "Weatherwax",
    "Ogg",
    "Vimes",
    "Flashman",
    "Hornblower",
    "Malaprop",
    "Bracknell",
    "Moncrieff",
    "Worthing",
    "Drummond",
    "Wimsey",
    "Bunter",
    "Smyth",
]

TITLES = [
    "",
    "",
    "",
    "",
    "Sir ",
    "Lady ",
    "Colonel ",
    "Squadron Leader ",
    "Reverend ",
    "Dr ",
    "Brother ",
]


def url(number: int) -> AnyHttpUrl:
    return AnyHttpUrl(f"{BASE}/person/literary-{number:04d}")


def names() -> list[str]:
    """The canonical names, then made-up ones, all different: always the same ones"""
    chosen = list(dict.fromkeys(CANONICAL))
    seen = set(chosen)
    rng = random.Random(1975)
    while len(chosen) < HOW_MANY:
        name = f"{rng.choice(TITLES)}{rng.choice(FIRST)} {rng.choice(SURNAMES)}"
        if name not in seen:
            seen.add(name)
            chosen.append(name)
    return chosen


async def add_people() -> None:
    rng = random.Random(42)
    for number, name in enumerate(names(), start=1):
        await models.Person.Create(
            id=url(number),
            create_new=True,
            label=name,
            known_as={"value": name, "certainty": rng.randint(1, 5)},
            born={"type": "ExactDate", "year": rng.randint(700, 1950)},
            aliases=[],
            has_type=[],
        ).save()
        if number % 100 == 0:
            print(f"  {number} written")


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
        if await models.Person.get(id=url(1)) is not None:
            sys.exit("The database already has the made-up people: nothing was written")
        await add_people()
    finally:
        await backend.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
