from inspect import iscoroutinefunction
from uuid import uuid7

import pytest
from pangloss_models import initialise
from pangloss_models.model_bases.document import Document
from typing_extensions import no_type_check


@pytest.mark.asyncio
async def test_document_get():
    class Statement(Document):
        pass

    initialise()

    assert Statement.get
    assert iscoroutinefunction(Statement.get)

    resp = await Statement.get(uuid7())
    assert resp


@no_type_check
@pytest.mark.asyncio
async def test_document_write():
    class Statement(Document):
        pass

    initialise()

    st = Statement.Create(label="A Statement")

    result = await st.save()
    assert result.id
    assert result.label == "A Statement"
    assert result.type == "Statement"
