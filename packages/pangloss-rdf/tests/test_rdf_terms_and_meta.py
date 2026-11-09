import pytest
from pangloss_models import Document, Entity, ReifiedRelation, initialise
from pangloss_models.exceptions import PanglossMetaError
from pangloss_rdf import IRI, RDFMeta
from pangloss_rdf.meta import is_excluded, own_rdf_meta


@pytest.mark.parametrize(
    "value", ["relative/path", "https://a.org/with space", "https://a.org/<b>", ""]
)
def test_an_iri_that_could_not_be_written_is_refused(value):
    with pytest.raises(ValueError, match="not an absolute IRI"):
        IRI(value)


@pytest.mark.parametrize("name", ["a.b", "a/b", "1a", "", "a b"])
def test_a_class_name_must_fit_in_a_uri(name):
    with pytest.raises(PanglossMetaError, match="cannot be part of a URI"):
        RDFMeta(class_name=name)


def test_a_class_uri_must_be_absolute():
    with pytest.raises(PanglossMetaError, match="not an absolute URI"):
        RDFMeta(class_uri="Person")


def test_name_and_uri_cannot_both_be_given():
    with pytest.raises(PanglossMetaError, match="not both"):
        RDFMeta(class_name="A", class_uri="https://a.org/A")


def test_a_slot_of_the_wrong_type_is_an_error():
    with pytest.raises(PanglossMetaError, match="must be a RDFMeta"):

        class Person(Entity):
            _rdf_meta = "Human"


def test_a_name_is_not_inherited_but_exclude_is():
    class Thing(Entity):
        _rdf_meta = RDFMeta(class_name="Item", exclude=True)

    class Book(Thing):
        pass

    assert own_rdf_meta(Thing).class_name == "Item"
    assert own_rdf_meta(Book) is None
    assert is_excluded(Book)


def test_a_use_of_a_generic_has_the_generics_meta():
    class Person(Entity):
        pass

    class InRole[T](ReifiedRelation[T]):
        _rdf_meta = RDFMeta(class_name="Role")

        role: str

    class Letter(Document):
        about: list[InRole[Person]]

    initialise()
    assert own_rdf_meta(InRole[Person]).class_name == "Role"
