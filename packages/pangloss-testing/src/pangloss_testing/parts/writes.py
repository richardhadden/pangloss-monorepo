"""The writes the suite of the parts makes, on `pangloss_testing.similar_models`: a document of every shape written
(`write_shapes`, the payloads of `notes/similarity-evaluation/stored_shapes.py`), and each kind of write after it, by
name (`WRITES`), with what each takes away (`GONE`). They were `pangloss-fastrp`'s (`fastrp_live_support.py` and
`test_fastrp_worker_live.py`), which import them from here."""

from collections.abc import Awaitable, Callable
from typing import Any, no_type_check

NAMES = ["Ada", "Ben", "Cy", "Dee", "Eve", "Fay", "Gus", "Parent"]


def ref(item: Any, kind: str = "Person") -> dict[str, Any]:
    """A reference to anything with an `id`"""
    return {"type": kind, "id": item.id}


def ref_to(id: str, kind: str = "Person") -> dict[str, Any]:
    """A reference to an id"""
    return {"type": kind, "id": id}


def people(ids: dict[str, str], *names: str) -> dict[str, Any]:
    """The people of `ids` by name, as the payloads take them (anything with an `id`)"""
    from types import SimpleNamespace

    return {name: SimpleNamespace(id=ids[name]) for name in names}


def alternatives(ben: Any, cy: Any) -> dict[str, Any]:
    """Ben at 70%, Cy at 30%, through an identification"""
    return {
        "type": "Identification",
        "target": [
            {
                "type": "WeightedAlternative",
                "alternatives": [
                    {**ref(ben), "edge_properties": {"percent": 70}},
                    {**ref(cy), "edge_properties": {"percent": 30}},
                ],
            }
        ],
    }


def transfer(people: dict[str, Any]) -> dict[str, Any]:
    return {
        "type": "Transfer",
        "label": "Ada gave to Ben or Cy",
        "given_by": ref(people["Ada"]),
        "given_to": alternatives(people["Ben"], people["Cy"]),
    }


def meeting(people: dict[str, Any], place: Any) -> dict[str, Any]:
    return {
        "type": "Activity",
        "label": "Ada met Dee and Eve",
        "carried_out_by": ref(people["Ada"]),
        "participants": [
            {
                "type": "InRole",
                "role": "guest",
                "at": {"type": "Place", "id": place.id},
                "target": [ref(people["Dee"])],
            },
            {
                "type": "Sworn",
                "role": "witness",
                "oath": "on the book",
                "target": [ref(people["Eve"])],
            },
        ],
    }


def described(people: dict[str, Any], group: Any) -> dict[str, Any]:
    """A transfer from someone described: a member of the group"""
    return {
        "type": "Transfer",
        "label": "A member gave to Ada",
        "given_by": {
            "type": "MatchesCriteria",
            "wording": "a member of the guild",
            "criteria": {
                "type": "Person",
                "where": {
                    "$incoming": [
                        {
                            "type": "MemberOf",
                            "field": "member",
                            "where": {"group": {"is": str(group.id)}},
                        }
                    ]
                },
            },
        },
        "given_to": ref(people["Ada"]),
    }


@no_type_check
async def write_shapes(m, db_driver, published: bool | None = None) -> dict[str, str]:
    """A document of every shape, the criteria and derived workers run after: the ids by name (the people by theirs;
    `group`, `place`; the factoids `gift`, `no gift`, `meeting`, `members`, `member gift`, `inference`, `two names`,
    `Fay's parent`, `Gus's parent`; the statements in them `transfer`, `denied`, `activity`, `fay member`,
    `gus member`, `member transfer`, `inference statement`, `same`, `Fay child`, `Gus child`; the derived `siblings`
    and its `sibling`). `published`: given to each factoid's `save` (with `declare(reviewed=True)`)"""
    from pangloss_criteria import run_pending
    from pangloss_derived.worker import run_pending_derivations

    from pangloss_testing.live import run

    saved = {} if published is None else {"published": published}
    ids: dict[str, str] = {}
    people = {}
    for name in NAMES:
        people[name] = await m.Person.Create(label=name).save()
        ids[name] = str(people[name].id)
    group = await m.Group.Create(label="The guild").save()
    place = await m.Place.Create(label="York").save()
    ids |= {"group": str(group.id), "place": str(place.id)}

    async def factoid(name: str, statements: list) -> Any:
        made = await m.Factoid.Create(label=name, statements=statements).save(**saved)
        ids[name] = str(made.id)
        return await m.Factoid.get(made.id)

    gift = await factoid("gift", [transfer(people)])
    ids["transfer"] = str(gift.statements[0].id)
    denied = await factoid(
        "no gift", [{"type": "Negative", "contents": [transfer(people)]}]
    )
    ids["denied"] = str(denied.statements[0].contents[0].id)
    met = await factoid("meeting", [meeting(people, place)])
    ids["activity"] = str(met.statements[0].id)
    members = await factoid(
        "members",
        [
            {
                "type": "MemberOf",
                "label": f"{name} of the guild",
                "member": ref(people[name]),
                "group": ref(group, "Group"),
            }
            for name in ["Fay", "Gus"]
        ],
    )
    ids["fay member"] = str(members.statements[0].id)
    ids["gus member"] = str(members.statements[1].id)
    gave = await factoid("member gift", [described(people, group)])
    ids["member transfer"] = str(gave.statements[0].id)
    inference = await factoid(
        "inference",
        [
            {
                "type": "Inference",
                "label": "So Ada knew Ben or Cy",
                "evidence": [{"type": "Transfer", "id": ids["transfer"]}],
            }
        ],
    )
    ids["inference statement"] = str(inference.statements[0].id)
    same = await factoid(
        "two names",
        [
            {
                "type": "SameEntity",
                "label": "Dee is Eve",
                "target": [ref(people["Dee"]), ref(people["Eve"])],
            }
        ],
    )
    ids["same"] = str(same.statements[0].id)
    for child in ["Fay", "Gus"]:
        made = await factoid(
            f"{child}'s parent",
            [
                {
                    "type": "ChildOf",
                    "label": f"{child}, child of Parent",
                    "child": ref(people[child]),
                    "parent": ref(people["Parent"]),
                }
            ],
        )
        ids[f"{child} child"] = str(made.statements[0].id)
    await run_pending()
    await run_pending_derivations()
    await run_pending()
    for row in run(
        db_driver,
        "MATCH (d:DerivedFactoid)-[:statements]->(s) RETURN d.id AS id, s.id AS sibling",
    ):
        ids["siblings"], ids["sibling"] = row["id"], row["sibling"]
    return ids


# ---------------------------------------------------------------------------
# Each kind of write, after `write_shapes`
# ---------------------------------------------------------------------------


@no_type_check
async def create(m, ids) -> None:
    await m.Factoid.Create(
        label="another gift",
        statements=[
            {
                "type": "Transfer",
                "label": "Gus gave to Parent",
                "given_by": ref_to(ids["Gus"]),
                "given_to": ref_to(ids["Parent"]),
            }
        ],
    ).save()


@no_type_check
async def update_that_adds_a_reference(m, ids) -> None:
    await m.Factoid.Update(
        id=ids["two names"],
        label="two names",
        statements=[
            {
                "type": "SameEntity",
                "label": "Dee is Eve",
                "target": [ref_to(ids["Dee"]), ref_to(ids["Eve"])],
            },
            {
                "type": "Transfer",
                "label": "Gus gave to Parent",
                "given_by": ref_to(ids["Gus"]),
                "given_to": ref_to(ids["Parent"]),
            },
        ],
    ).save()


@no_type_check
async def update_that_drops_a_reference(m, ids) -> None:
    """The meeting without Eve (and so without the `Sworn` that held her), nor the place"""
    await m.Factoid.Update(
        id=ids["meeting"],
        label="meeting",
        statements=[
            {
                "type": "Activity",
                "label": "Ada met Dee",
                "carried_out_by": ref_to(ids["Ada"]),
                "participants": [
                    {"type": "InRole", "role": "guest", "target": [ref_to(ids["Dee"])]}
                ],
            }
        ],
    ).save()


@no_type_check
async def update_that_replaces_its_statements(m, ids) -> None:
    """Fay's parent written again as a transfer: its old statement gone (and the siblings derived from it), a new
    one"""
    await m.Factoid.Update(
        id=ids["Fay's parent"],
        label="Fay's parent",
        statements=[
            {
                "type": "Transfer",
                "label": "Fay gave to Gus",
                "given_by": ref_to(ids["Fay"]),
                "given_to": ref_to(ids["Gus"]),
            }
        ],
    ).save()


@no_type_check
async def update_that_renames_a_person(m, ids) -> None:
    """Ada's label changed (an update of an entity: what a part of names reads)"""
    await m.Person.Update(id=ids["Ada"], label="Ada of York").save()


@no_type_check
async def delete(m, ids) -> None:
    await m.Factoid.delete(ids["meeting"])


@no_type_check
async def new_citation(m, ids) -> None:
    await m.Factoid.Create(
        label="another inference",
        statements=[
            {
                "type": "Inference",
                "label": "So Ada knew Dee",
                "evidence": [{"type": "Activity", "id": ids["activity"]}],
            }
        ],
    ).save()


@no_type_check
async def criteria_change_candidates(m, ids) -> None:
    """Ben joins the guild: the description of a member in "member gift" has him as a candidate more (the criteria
    worker writes it, `set_computed`)"""
    await m.Factoid.Create(
        label="Ben joins",
        statements=[
            {
                "type": "MemberOf",
                "label": "Ben of the guild",
                "member": ref_to(ids["Ben"]),
                "group": ref_to(ids["group"], "Group"),
            }
        ],
    ).save()


type Write = Callable[[Any, dict[str, str]], Awaitable[None]]

WRITES: dict[str, Write] = {
    "a create": create,
    "an update that adds a reference": update_that_adds_a_reference,
    "an update that drops a reference": update_that_drops_a_reference,
    "an update that replaces its statements": update_that_replaces_its_statements,
    "an update of an entity that changes its label": update_that_renames_a_person,
    "a delete": delete,
    "a new citation": new_citation,
    "a criteria evaluation that changes candidates": criteria_change_candidates,
}

# What each write takes away, by the names of `write_shapes`: none of them keeps a vector of any part after it (an
# update writes what is below the head again, with new ids)
GONE: dict[str, tuple[str, ...]] = {
    "an update that drops a reference": ("activity",),
    "an update that replaces its statements": ("Fay child",),
    "a delete": ("meeting", "activity"),
}
