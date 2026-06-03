import datetime

from pangloss_models.model_bases.document import Document, DocumentMeta
from pangloss_models.model_bases.embedded import Embedded, EmbeddedMeta


def test_meta_inheritance_of_abstract():
    class Statement(Document):
        _meta = DocumentMeta(abstract=True)

    class Action(Statement):
        pass

    class CreationOfArtwork(Action):
        _meta = DocumentMeta(abstract=True)

    class CreationOfPainting(CreationOfArtwork):
        pass

    assert Statement._meta.abstract is True
    assert Action._meta.abstract is False
    assert CreationOfArtwork._meta._owner_class is CreationOfArtwork
    assert CreationOfArtwork._meta.abstract is True
    assert CreationOfPainting._meta.abstract is False


def test_meta_inheritance_of_abstract_on_embedded():
    class Date(Embedded):
        _meta = EmbeddedMeta(abstract=True)
        when: datetime.datetime

    class Statement(Document):
        date: Date

    class SpecialDate(Date):
        pass

    assert Date._meta.abstract is True
    assert SpecialDate._meta.abstract is False
