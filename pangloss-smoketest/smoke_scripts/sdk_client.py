"""The project's SDK, used as a client would: run by `sdk_client.sh` in an environment that has only the SDK and
what it needs (no interface, no database driver, no web framework).

    PANGLOSS_URL=http://localhost:8010 PANGLOSS_TOKEN=pgl_... python sdk_client.py
"""

import asyncio
import importlib.util
import os

import smoketest_site_sdk as sdk

sdk.connect(os.environ.get("PANGLOSS_URL", "http://localhost:8010"), token=os.environ["PANGLOSS_TOKEN"])

from pangloss_dates import ExactDate  # noqa: E402
from smoke.models import Book, Death, Factoid, OccupationType, Person  # noqa: E402


async def main() -> None:
    for name in ("pangloss_interface", "fastapi", "neo4j", "pangloss_api", "pangloss_users", "pangloss_memgraph"):
        assert importlib.util.find_spec(name) is None, f"{name} is installed here"
    print("no interface, web framework or database driver here")

    print("SDK:", await sdk.check())

    people = await Person.list(search_terms="Bartolomeo", page_size=3)
    print(f"{people.count} people called Bartolomeo; the first: {people.results[0].label}")
    found = await Person.search(Person.Where(nickname={"eq": "nobody has this"}))
    print(f"a typed search: {found.count} found")

    occupation = (await OccupationType.list(page_size=1)).results[0]
    book = (await Book.list(page_size=1)).results[0]
    person = await Person.Create(
        label="Sdk Client (made through the SDK)",
        known_as={"value": "Sdk Client", "certainty": 3},
        gender="unknown",
        born=ExactDate.Create(year=1500),
        aliases=[],
        has_type=[{"type": "OccupationType", "id": occupation.id}],
    ).save()
    print("made", person.type, person.id)

    factoid = await Factoid.Create(
        label="Death of Sdk Client (made through the SDK)",
        source={"type": "AtPage", "page": "12", "target": [{"type": book.type, "id": book.id}]},
        statements=[
            Death.Create(
                label="Death of Sdk Client",
                text="He died.",
                date=ExactDate.Create(year=1560, month=3),
                places=[],
                deceased={"type": "Person", "id": person.id},
                cause="fever",
            )
        ],
    ).save(detail=True)
    statement = factoid.statements[0]
    print("made", factoid.type, factoid.id, "with a", statement.type, "dated", statement.date.year, statement.date.month)
    assert statement.deceased.id == person.id

    read = await Person.get(person.id)
    assert read is not None and read.has_type[0].id == occupation.id
    print("read back:", read.label, "born", read.born.year, "a", read.has_type[0].label)

    await Factoid.delete(factoid.id)
    await Person.delete(person.id)
    assert await Factoid.get(factoid.id) is None
    print("deleted both")
    await sdk.disconnect()


asyncio.run(main())
