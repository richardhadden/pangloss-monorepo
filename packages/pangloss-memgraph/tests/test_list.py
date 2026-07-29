from typing import no_type_check

import pytest
from pangloss_models import initialise
from pangloss_models.model_bases.base_models import _ListItems
from pangloss_models.model_bases.document import Document

pytestmark = pytest.mark.asyncio(loop_scope="session")


LABELS = [
    "John Smith ate an Alligator",
    "John Smith ate a Bear",
    "John Smith ate a Cat",
    "John Smith ate a Dog",
    "John Smith ate an Elephant",
    "John Smith ate a Fox",
    "John Smith ate a Giraffe",
    "John Smith ate a Horse",
    "John Smith ate an Iguana",
    "John Smith ate a Jaguar",
    "John Smith ate a Kangaroo",
    "John Smith ate a Lion",
    "John Smith ate a Moose",
    "John Smith ate a Newt",
    "John Smith ate an Octopus",
    "John Smith ate a Penguin",
    "John Smith ate a Quail",
    "John Smith ate a Rabbit",
    "John Smith ate a Snake",
    "John Smith ate a Tiger",
    "John Smith ate an Urchin",
    "John Smith ate a Vulture",
    "John Smith ate a Walrus",
    "John Smith ate a Xenops",
    "John Smith ate a Yak",
    "John Smith ate a Zebra",
]


@no_type_check
async def test_read_nested_object(clear_database):

    class Factoid(Document):
        pass

    class SubFactoid(Factoid):
        pass

    initialise()

    for label in LABELS:
        factoid = Factoid.Create(label=label)
        await factoid.save()

        subfactoid = SubFactoid.Create(label=label)
        await subfactoid.save()

    result: _ListItems = await Factoid.list()

    assert result.count == 52
    assert result.page == 1
    assert result.next_page == 2
    assert result.previous_page is None
    assert result.page_size == 50

    # check we have some proper types being return
    assert any(r.type == "SubFactoid" for r in result.results)
    assert any(r.type == "Factoid" for r in result.results)

    assert any(isinstance(r, SubFactoid.ReferenceView) for r in result.results)
    assert any(isinstance(r, Factoid.ReferenceView) for r in result.results)
