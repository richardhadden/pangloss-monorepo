from pangloss_models import initialise
from pangloss_models.model_bases.document import Document


def test_doc():
    class Statement(Document):
        pass

    initialise()

    st = Statement.Create(label="A Statement")
    st.save()

    assert False
