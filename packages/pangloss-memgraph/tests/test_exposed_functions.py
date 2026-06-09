from inspect import iscoroutinefunction
from uuid import uuid7

import pytest
from pangloss_models import initialise
from pangloss_models.model_bases.document import Document


@pytest.mark.asyncio
async def test_document_get():
    class Statement(Document):
        pass

    initialise()

    assert Statement.get
    assert iscoroutinefunction(Statement.get)

    resp = await Statement.get(uuid7())
    assert resp
