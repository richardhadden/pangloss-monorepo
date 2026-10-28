"""`save(published=..., review_status=...)`: what the SDK sends with a create or update"""

from types import SimpleNamespace
from uuid import uuid4

import pytest
from pangloss_sdk import protocol


class Letter:
    pass


def instance():
    return SimpleNamespace(
        _owner=Letter,
        id=uuid4(),
        model_dump=lambda **_: {"type": "Letter"},
    )


@pytest.mark.parametrize(
    ("kwargs", "params"),
    [
        ({}, None),
        ({"detail": True}, {"detail": "true"}),
        ({"published": True}, {"review_status": "checked"}),
        ({"published": False}, {"review_status": "unchecked"}),
        ({"review_status": "errors_found"}, {"review_status": "errors_found"}),
        (
            {"detail": True, "published": True},
            {"detail": "true", "review_status": "checked"},
        ),
    ],
)
def test_a_create_and_an_update_say_the_status_in_the_query(kwargs, params):
    assert protocol.create(instance(), **kwargs).params == params
    assert protocol.update(instance(), **kwargs).params == params


def test_published_and_a_status_may_not_both_be_given():
    with pytest.raises(ValueError):
        protocol.create(instance(), published=True, review_status="checked")
