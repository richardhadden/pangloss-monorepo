from uuid import uuid7

from pangloss_models import initialise
from pangloss_models.model_bases.document import Document


def test_get_item():
    class Statement(Document):
        pass

    initialise()

    print(Statement.get(id=uuid7()))

    assert False
