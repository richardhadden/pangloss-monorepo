"""Accents are folded in searches: `zurich`, `ZURICH` and `Zürich` all find "Zürich", and `strasse` finds "Straße".
(The behaviour is the same on both backends, by different means)"""

from typing import no_type_check

import pytest
from pangloss_models import initialise
from pangloss_models.model_bases.document import Document
from pangloss_models.model_bases.entity import Entity

pytestmark = pytest.mark.asyncio(loop_scope="session")


def models():
    class Place(Entity):
        pass

    class Letter(Document):
        sent_to: Place

    initialise()
    return Place, Letter


def labels(found):
    return sorted(item.label for item in found.results)


@no_type_check
@pytest.mark.parametrize(
    "typed", ["zurich", "ZURICH", "Zürich", "zür", "strasse", "Straße"]
)
@pytest.mark.parametrize("deep", [False, True])
async def test_a_list_finds_what_is_written_with_or_without_accents(
    clear_database, typed, deep
):
    Place, Letter = models()
    zurich = await Place.Create(label="Hauptstraße, Zürich").save()
    await Place.Create(label="Geneva").save()
    # (a deep list of entities finds those that something refers to)
    await Letter.Create(
        label="A letter", sent_to=Place.ReferenceSet(id=zurich.id)
    ).save()

    found = await Place.list(search_terms=typed, deep_search=deep)

    assert labels(found) == ["Hauptstraße, Zürich"]


@no_type_check
@pytest.mark.parametrize("typed", ["zurich", "ZURICH", "Zürich", "strasse"])
async def test_autocomplete_finds_what_is_written_with_or_without_accents(
    clear_database, typed
):
    Place, _ = models()
    await Place.Create(label="Hauptstraße, Zürich").save()
    await Place.Create(label="Geneva").save()

    found = await Entity.autocomplete(typed, types=[Place])

    assert labels(found) == ["Hauptstraße, Zürich"]


@no_type_check
async def test_a_label_changed_is_found_by_its_new_words_only(clear_database):
    Place, _ = models()
    place = await Place.Create(label="Zürich").save()
    await Place.Update(id=place.id, label="Genève").save()

    assert labels(await Place.list(search_terms="geneve")) == ["Genève"]
    assert labels(await Place.list(search_terms="zurich")) == []
