"""Shared by the live tests of the criteria worker: Maximilian's court, his secretaries, and an activity carried out by
someone described as one of them"""

from typing import Any


def ref(item) -> dict[str, Any]:
    return {"type": type(item)._owner.__name__, "id": item.id}


def secretary_of(office, employer) -> dict:
    return {
        "type": "Person",
        "where": {
            "$incoming": [
                {
                    "type": "HoldsOffice",
                    "field": "holder",
                    "where": {
                        "office": {"is": str(office.id)},
                        "employer": {"is": str(employer.id)},
                    },
                }
            ]
        },
    }


class Court:
    """Maximilian and his secretaries, by label"""

    def __init__(self, Person, Office, HoldsOffice, Activity):
        self.Person, self.Office, self.HoldsOffice, self.Activity = (
            Person,
            Office,
            HoldsOffice,
            Activity,
        )
        self.people: dict[str, Any] = {}
        self.offices: dict[str, Any] = {}

    async def person(self, label):
        if label not in self.people:
            self.people[label] = await self.Person.Create(label=label).save()
        return self.people[label]

    async def office(self, label):
        if label not in self.offices:
            self.offices[label] = await self.Office.Create(label=label).save()
        return self.offices[label]

    async def holds(self, holder, employer="Maximilian", office="Secretary"):
        """`holder` holds the office under the employer: gives the document"""
        return await self.HoldsOffice.Create(
            label=f"{holder} is {office} of {employer}",
            holder=[ref(await self.person(holder))],
            office=ref(await self.office(office)),
            employer=ref(await self.person(employer)),
        ).save()

    async def described(
        self,
        label="A letter carried",
        wording="N. N.",
        named=(),
        criteria=None,
        **more,
    ):
        """An activity carried out by someone described as a secretary of Maximilian (or by the criteria given), and
        by those named"""
        if criteria is None:
            criteria = secretary_of(
                await self.office("Secretary"), await self.person("Maximilian")
            )
        return await self.Activity.Create(
            label=label,
            carried_out_by=[
                *[ref(await self.person(name)) for name in named],
                {"type": "MatchesCriteria", "wording": wording, "criteria": criteria},
            ],
            **{"witnessed_by": [], **more},
        ).save(detail=True)


def description_of(activity):
    return next(
        item for item in activity.carried_out_by if item.type == "MatchesCriteria"
    )


def candidates(activity) -> list[str]:
    return [person.label for person in description_of(activity).target]


def run_database() -> str:
    from pangloss_testing.backends import under_test

    return under_test().database
