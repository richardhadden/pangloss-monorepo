# %% [markdown]
# # Using a project's models from outside it, through the SDK
#
# This is run **outside** `pangloss-demo`, in an environment that has the SDK the server
# built (`pangloss-demo-sdk`) and `pangloss-sdk`, and nothing else of Pangloss: no database
# driver, no web framework. The models are the ones in `demo_app/models.py`, but
# `Person.get`, `Factoid.Create(...).save()` and the rest are requests to the API.
#
#     PANGLOSS_URL=http://127.0.0.1:8765 PANGLOSS_USERNAME=... PANGLOSS_PASSWORD=... \
#         python sdk_demo.py [--keep]
#
# (`run.sh` makes the environment and runs this.) With no username and password, a login
# is asked for at the first request that needs one.
# It is written as cells (`# %%`), so an editor or Jupytext can open it as a notebook.

# %% Connect: initialises the models, with the model functions bound to the API
import asyncio
import datetime
import os
import sys

import pangloss_demo_sdk as sdk
import pangloss_sdk
from pangloss_models.exceptions import PanglossVersionConflictError

KEEP = "--keep" in sys.argv

sdk.connect(os.environ.get("PANGLOSS_URL", "http://127.0.0.1:8765"))

# (these are the project's own models, under their own names: the code is the same as on the server)
from demo_app.models import Factoid, Person, Place, Source  # noqa: E402


def date(year: int, month: int = 1, day: int = 1, precision: str = "day") -> dict:
    return {"when": datetime.date(year, month, day), "precision": precision}


def ref(entity) -> dict:
    return {"type": entity.type, "id": entity.id}


async def main() -> None:
    # %% Is this SDK the server's? (the answer comes with every request too)
    status = await sdk.check()
    print("SDK:", status)

    # %% Read, which needs no login
    first_page = await Person.list(page_size=5)
    print(f"{len(first_page.results)} people on the first page")

    # %% Write: this is when the login is asked for (or the username and password are taken from the environment)
    charlemagne = await Person.Create(
        label="Charlemagne (SDK demo)",
        known_as={"value": "Karolus Magnus", "certainty": 5},
        born=date(748, precision="year"),
        aliases=["Charles the Great"],
    ).save()
    rome = await Place.Create(label="Rome (SDK demo)", coordinates={"latitude": 41.9, "longitude": 12.5}).save()
    annales = await Source.Create(
        label="Annales regni Francorum (SDK demo)", written=datetime.date(829, 1, 1)
    ).save()
    print("made", charlemagne.id, rome.id, annales.id)

    # %% A document that refers to them, with a statement inside it
    factoid = await Factoid.Create(
        label="Charlemagne is in Rome (SDK demo)",
        year=800,
        source={"type": "AtPage", "page": "s.a. 800", "target": [ref(annales)]},
        statements=[
            {
                "type": "Activity",
                "label": "Charlemagne arrives",
                "text": "Charles came to Rome",
                "date": date(800, 11, 24),
                "activity_type": "meeting",
                "carried_out_by": {**ref(charlemagne), "edge_properties": {"level": 4}},
                "participants": [],
                "places": [ref(rome)],
            }
        ],
    ).save(detail=True)
    print("factoid", factoid.id, "with", len(factoid.statements), "statement")

    # %% Read it back, by id; an entity is found by its URL too
    again = await Factoid.get(factoid.id)
    assert again is not None and again.label == factoid.label
    by_url = await Person.get(charlemagne.id)
    assert by_url is not None
    print("read back:", again.label, "|", by_url.label)

    # %% Update: read it for editing, change it, save it against the version that was read
    editing = await Person.get_for_edit(charlemagne.id)
    based_on = editing.meta.version

    def changed(label: str):
        return Person.Update(
            id=charlemagne.id,
            label=label,
            known_as={"value": "Karolus Magnus", "certainty": 5},
            born=date(748, precision="year"),
            aliases=["Charles the Great"],
        )

    await changed("Charlemagne, emperor (SDK demo)").save(expected_version=based_on)
    print("updated: version", based_on, "->", based_on + 1)

    # %% Someone else got there first: saving against the version that was read is refused,
    # with the exception the server's own database module raises
    try:
        await changed("Karl der Große (SDK demo)").save(expected_version=based_on)
    except PanglossVersionConflictError as error:
        print("conflict: the latest version is", error.current_version)

    # %% Go through everything of a kind, page by page
    count = 0
    async for person in pangloss_sdk.iterate(Person.list, page_size=2):
        count += 1
    print(count, "people in all")

    # %% Clean up (so that it can be run again); what is referred to is deleted last
    if not KEEP:
        await Factoid.delete(factoid.id)
        for entity, model in ((charlemagne, Person), (rome, Place), (annales, Source)):
            await model.delete(entity.id)
        print("removed what this made")

    await sdk.disconnect()


# %%
asyncio.run(main())
