"""The planted models as the worker is measured on them at size (step 10.5g of implementation_docs/similarity-build-plan.md;
`notes/similarity-evaluation/planted.py worker`): `pangloss_testing.similar_models.declare(suggested=True)` lets a
participant, in its place and in an `InRole`, be the class the worker writes by default
(`IdentificationByToolchainFromText`, below `IdentificationByToolchain`) and the class that becomes when confirmed
(`IdentificationFromText`, below `Identification`), and leaves `carried_out_by` an agent (or a stand-in) only. No
database."""

from typing import Any

import pytest
from pangloss_models import hooks
from pangloss_testing.similar_models import declare, mention_stand_in
from pydantic import ValidationError

from pangloss_reconcile.suggest import Alternative
from pangloss_reconcile.suggesting import suggestion

PERSON = "0b9f4c1e-8a2d-4e43-9a51-3c0d6a1b2f70"
OTHER = "5d2e7a90-1c3b-4f86-8e0a-97b4c2d1e6f3"
PLACE = "a7c1e2f3-4b5d-4c6e-8f70-1a2b3c4d5e6f"


@pytest.fixture
def mention():
    made = mention_stand_in()
    hooks.stand_ins.append(made)
    yield
    hooks.stand_ins.remove(made)


def guessed(kind: str = "IdentificationByToolchainFromText") -> dict[str, Any]:
    """A suggestion of two people, in the shape the worker writes (`suggesting.suggestion`, "alternatives"), as a
    `Create` takes it"""
    made = suggestion(
        {"type": "Mention", "label": "Hans Gruber", "mentioned_type": "Person"},
        "alternatives",
        [Alternative(PERSON, "Person", 70), Alternative(OTHER, "Person", 30)],
        id="4b0f6a3e-2d1c-4e5f-9a8b-7c6d5e4f3a2b",
        suggest_as=kind,
        toolchain="pangloss-reconcile",
        version="profile who",
    )
    # (a `Create` gives a nested node no id: the worker's own update does)
    made.pop("id")
    return made


def of_kind(kind: str) -> dict[str, Any]:
    """The same suggestion as a `kind`: with only the fields the class has (a confirmed one has no toolchain, a plain
    one no `text`)"""
    made = guessed(kind)
    if kind in ("Identification", "IdentificationByToolchain"):
        made.pop("text")
    if kind in ("Identification", "IdentificationFromText"):
        made.pop("identified_by")
        made.pop("toolchain_version")
    return made


def hearing(
    participant: dict[str, Any], by: dict[str, Any] | None = None
) -> dict[str, Any]:
    return {
        "type": "Factoid",
        "label": "A hearing",
        "statements": [
            {
                "type": "Activity",
                "label": "A hearing with Hans Gruber",
                "carried_out_by": by or {"type": "Person", "id": OTHER},
                "participants": [participant],
            }
        ],
    }


def in_role(target: dict[str, Any]) -> dict[str, Any]:
    return {
        "type": "InRole",
        "role": "witness",
        "at": {"type": "Place", "id": PLACE},
        "target": [target],
    }


def test_a_participant_takes_the_worker_s_suggestion_and_what_it_becomes_in_a_role_and_beside_one(
    mention,
):
    m = declare(stand_in=True, suggested=True)
    for kind in (
        "IdentificationByToolchainFromText",
        "IdentificationFromText",
        "IdentificationByToolchain",
        "Identification",
    ):
        m.Factoid.Create(**hearing(in_role(of_kind(kind))))
        m.Factoid.Create(**hearing(of_kind(kind)))


def test_carried_out_by_takes_a_stand_in_and_no_suggestion(mention):
    m = declare(stand_in=True, suggested=True)
    m.Factoid.Create(
        **hearing(
            in_role({"type": "Person", "id": PERSON}),
            by={"type": "Mention", "label": "Hans Gruber", "mentioned_type": "Person"},
        )
    )
    with pytest.raises(ValidationError):
        m.Factoid.Create(
            **hearing(in_role({"type": "Person", "id": PERSON}), by=guessed())
        )


def test_without_suggested_a_participant_takes_no_suggestion(mention):
    m = declare(stand_in=True)
    with pytest.raises(ValidationError):
        m.Factoid.Create(**hearing(in_role(guessed())))
