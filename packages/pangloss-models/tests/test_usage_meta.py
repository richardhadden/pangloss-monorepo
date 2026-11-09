"""`_usage_meta`: an entity that is of interest only if something refers to it"""

from typing import no_type_check

import pytest
from pangloss_models import (
    Document,
    Entity,
    PanglossMetaError,
    Usage,
    initialise,
    included_only_when_referenced,
)


@no_type_check
def test_a_class_says_it_and_its_subclasses_inherit_it():
    class Harvested(Entity):
        _usage_meta = Usage(include_only_when_referenced=True)

    class Book(Harvested):
        pass

    class Kept(Harvested):
        _usage_meta = Usage(include_only_when_referenced=False)

    class Person(Entity):
        pass

    assert included_only_when_referenced(Harvested)
    assert included_only_when_referenced(Book)
    assert not included_only_when_referenced(Kept)
    assert not included_only_when_referenced(Person)


@no_type_check
def test_a_function_is_asked_of_the_subclass():
    class Harvested(Entity):
        _usage_meta = Usage(
            include_only_when_referenced=lambda model: model.__name__ != "Handmade"
        )

    class Synced(Harvested):
        pass

    class Handmade(Harvested):
        pass

    assert included_only_when_referenced(Synced)
    assert not included_only_when_referenced(Handmade)


def test_a_value_that_means_nothing_is_refused():
    with pytest.raises(PanglossMetaError, match="include_only_when_referenced"):
        Usage(include_only_when_referenced="yes")  # ty: ignore[invalid-argument-type]


@no_type_check
def test_a_document_cannot_say_it():
    class Letter(Document):
        _usage_meta = Usage(include_only_when_referenced=True)

    with pytest.raises(PanglossMetaError, match="Letter.*Entity"):
        initialise()
