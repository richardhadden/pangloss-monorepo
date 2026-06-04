from typing import no_type_check
from uuid import uuid7

from pangloss_models import initialise
from pangloss_models.model_bases.document import Document


@no_type_check
def test_get_item():
    """Currently tests a hard-coded return type to make sure database module bindings work"""

    class Statement(Document):
        pass

    initialise()

    st = Statement.get(id=uuid7())

    assert isinstance(st, Statement.HeadView)

    assert st.id
    assert st.label == "A document"
    assert st.type == "Statement"
