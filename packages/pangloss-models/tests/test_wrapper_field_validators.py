"""The validators of a generic wrapper's fields (`MinLen`, `MaxLen` on `target: list[T]`) are checked where the
wrapper is used, as those of any model's fields are"""

from typing import Annotated, no_type_check
from uuid import uuid7

import pytest
from annotated_types import MaxLen, MinLen
from pangloss_models import initialise
from pangloss_models.model_bases.conjunction import Conjunction
from pangloss_models.model_bases.document import Document
from pangloss_models.model_bases.entity import Entity
from pangloss_models.model_bases.reified_relation import ReifiedRelation
from pydantic import ValidationError


@no_type_check
def test_the_lengths_of_a_wrapper_field_are_checked():
    class Person(Entity):
        pass

    class Identification[T](ReifiedRelation[T]):
        target: Annotated[list[T], MinLen(1), MaxLen(1)]

    class Both[T](Conjunction):
        things: Annotated[list[T], MinLen(2)]

    class Statement(Document):
        who: Identification[Person]
        pair: Both[Person]

    initialise()
    people = lambda n: [{"type": "Person", "id": uuid7()} for _ in range(n)]  # noqa: E731

    def statement(targets: int, things: int):
        return Statement.Create(
            label="S",
            who={"type": "Identification", "target": people(targets)},
            pair={"type": "Both", "things": people(things)},
        )

    statement(1, 2)
    for targets, things in ((0, 2), (2, 2), (1, 1)):
        with pytest.raises(ValidationError):
            statement(targets, things)
