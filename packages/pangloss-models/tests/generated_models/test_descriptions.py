from typing import Annotated

from pangloss_models import Description, Document, Embedded, Entity, initialise


def test_model_description():
    class Person(Entity):
        """Describes a Person"""

    initialise()

    assert Person._meta.description == "Describes a Person"

    assert Person.Update._meta.description == "Describes a Person"

    assert Person.Create.__doc__ == "Describes a Person"
    assert Person.Update.__doc__ == "Describes a Person"
    assert Person.ReferenceSet.__doc__ == "Describes a Person"
    assert Person.ReferenceView.__doc__ == "Describes a Person"


def test_field_descriptions():
    class Statement(Document):
        number: Annotated[int, Description("Describes a number")]
        dude: Annotated[Dude, "A dude"]
        date: Annotated[Date, "A date"]

    class Dude(Entity):
        pass

    class Date(Embedded):
        pass

    initialise()

    assert Statement._meta.fields["number"].description == "Describes a number"
    assert Statement._meta.fields["dude"].description == "A dude"
    assert Statement._meta.fields["date"].description == "A date"

    assert Statement.Create.model_fields["number"].description == "Describes a number"
