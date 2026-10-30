"""A relation to a class that nothing can be created from is reported at the field, with details"""

from typing import no_type_check

import pytest
from pangloss_models import initialise
from pangloss_models.exceptions import PanglossModelError
from pangloss_models.model_bases.document import Document
from pangloss_models.model_bases.entity import Entity
from pangloss_models.model_bases.semantic_space import SemanticSpace
from pangloss_models.model_bases.trait import Trait


@no_type_check
def test_relation_to_an_abstract_class_with_no_subclass_is_refused():
    class Statement(Document):
        _meta = Document.Meta(abstract=True)

    class Negative[T](SemanticSpace[T]):
        pass

    class Factoid(Document):
        statements: list[Statement | Negative[Statement]]

    with pytest.raises(PanglossModelError) as error:
        initialise()

    message = str(error.value)
    assert "Factoid.statements points to Statement" in message
    assert "Statement is abstract and has no subclass" in message
    assert "Union" not in message


@no_type_check
def test_relation_to_an_abstract_class_with_only_abstract_subclasses_names_them():
    class Place(Entity):
        _meta = Entity.Meta(abstract=True)

    class Region(Place):
        _meta = Entity.Meta(abstract=True)

    class Letter(Document):
        sent_from: Place

    with pytest.raises(PanglossModelError) as error:
        initialise()

    assert "Letter.sent_from points to Place" in str(error.value)
    assert "all of its subclasses are abstract (Region)" in str(error.value)


@no_type_check
def test_relation_to_a_trait_that_nothing_has_is_refused():
    class Agent(Trait):
        pass

    class Letter(Document):
        sent_by: Agent

    with pytest.raises(PanglossModelError) as error:
        initialise()

    assert "Letter.sent_by points to Agent" in str(error.value)
    assert "trait that no Entity or Document has" in str(error.value)


@no_type_check
def test_every_such_relation_is_listed():
    class Statement(Document):
        _meta = Document.Meta(abstract=True)

    class Place(Entity):
        _meta = Entity.Meta(abstract=True)

    class Factoid(Document):
        statements: list[Statement]
        place: Place

    with pytest.raises(PanglossModelError) as error:
        initialise()

    assert "Factoid.statements" in str(error.value)
    assert "Factoid.place" in str(error.value)


@no_type_check
def test_an_abstract_class_that_nothing_points_to_is_allowed():
    class Template(Entity):
        _meta = Entity.Meta(abstract=True)

    class Other(Entity):
        pass

    initialise()
