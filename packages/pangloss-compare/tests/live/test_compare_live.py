"""The models comparison is measured on (`similar_models.declare(compared=True)`, with `pangloss_compare` installed)
written and read back on the backend under test (implementation_docs/spaces-and-comparison-plan.md, step 6.1)"""

from typing import no_type_check

import pytest
from pangloss_compare.meta import compared_classes, identifying_fields

pytestmark = pytest.mark.asyncio(loop_scope="session")


@no_type_check
async def test_a_factoid_with_a_birth_is_written_and_read_back(clear_database):
    from pangloss_testing.similar_models import declare

    m = declare(compared=True)
    assert "Birth" in compared_classes()
    person = await m.Person.Create(label="Guido").save()
    place = await m.Place.Create(label="Spoleto").save()
    source = await m.Source.Create(label="A chronicle").save()
    saved = await m.Factoid.Create(
        label="Guido is born at Spoleto",
        source={"type": "Source", "id": source.id},
        statements=[
            {
                "type": "Birth",
                "label": "Guido is born",
                "when": {"type": "ExactDate", "year": 880},
                "person": {"type": "Person", "id": person.id},
                "place": {"type": "Place", "id": place.id},
            }
        ],
    ).save()

    read = await m.Factoid.get(saved.id)
    (birth,) = read.statements
    assert birth.type == "Birth"
    assert birth.label == "Guido is born"
    assert birth.person.id == person.id
    assert birth.place.id == place.id
    assert read.source.id == source.id
    # (what says which birth it is, read from what was read back)
    assert {
        name: [getattr(birth, field).id for field in fields]
        for name, fields in identifying_fields(m.Birth).items()
    } == {"person": [person.id]}
