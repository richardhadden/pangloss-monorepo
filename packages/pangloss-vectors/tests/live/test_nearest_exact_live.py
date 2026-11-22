"""`nearest(..., exact=True)` on the backend under test (implementation_docs/similarity-build-plan.md, phase 10, row d):
the exact ways whatever the number of the profile's vectors, so that items whose vectors repeat are all found above
`VECTORS_EXACT_UP_TO` (set to 1 here), narrowed or not; without it, the index is asked there (whether the index
finds them is the backend's, and not asserted)."""

from types import SimpleNamespace
from typing import no_type_check

import pytest
from pangloss_models import Entity, ModelRegistry, initialise
from pangloss_vectors import VectorRow, VectorsMeta, nearest, search, store
from vectors_live_support import build, drop_vector_indexes, make_vector_indexes
from vectors_support import SizedPart

pytestmark = pytest.mark.asyncio(loop_scope="session")


@pytest.fixture
def vectors(db_driver, clear_database, parts_of_the_test, settings, monkeypatch):
    """One part, `a` (3 numbers); a profile of more vectors than `VECTORS_EXACT_UP_TO`, which is 1"""
    parts_of_the_test(SizedPart("a", 3, weight=1))
    monkeypatch.setattr(settings, "VECTORS_EXACT_UP_TO", 1)
    drop_vector_indexes(db_driver)
    yield
    drop_vector_indexes(db_driver)


@pytest.fixture
def queries(monkeypatch) -> list[str]:
    """The text of each query a search makes"""
    texts: list[str] = []
    ask = search._ask

    async def noted(tx, query, **parameters):
        texts.append(query)
        return await ask(tx, query, **parameters)

    monkeypatch.setattr(search, "_ask", noted)
    return texts


@no_type_check
def declare() -> SimpleNamespace:
    """`Person` (a group) above `Saint`; `Place` (in no group)"""
    ModelRegistry._reset()

    class Person(Entity):
        _vectors_meta = VectorsMeta(searchable=True)

    class Saint(Person):
        pass

    class Place(Entity):
        pass

    initialise()
    return SimpleNamespace(Person=Person, Saint=Saint, Place=Place)


ONE = [1.0, 0.0, 0.0]

# (by label: its class and its vector. Twelve share the vector searched by, of three classes; thirty-four do not)
ROWS = {
    **{f"namesake {n}": ("Person", ONE) for n in range(6)},
    **{f"saint {n}": ("Saint", ONE) for n in range(3)},
    **{f"same place {n}": ("Place", ONE) for n in range(3)},
    **{f"other {n}": ("Person", [0.0, 1.0, 0.0]) for n in range(20)},
    **{f"near {n}": ("Person", [1.0, 1.0, float(n)]) for n in range(8)},
    **{f"other place {n}": ("Place", [0.0, 0.0, 1.0]) for n in range(6)},
}


async def planted(m) -> dict[str, str]:
    """The items of `ROWS` saved, the part built from their vectors and the indexes made: ids by label"""
    made = {}
    for label, (class_name, _) in ROWS.items():
        made[label] = str((await getattr(m, class_name).Create(label=label).save()).id)
    await build(
        "a",
        [
            VectorRow(made[label], class_name, v)
            for label, (class_name, v) in ROWS.items()
        ],
    )
    await make_vector_indexes()
    return made


def repeated(made: dict[str, str], *classes: str) -> set[str]:
    return {made[label] for label, (c, v) in ROWS.items() if v == ONE and c in classes}


NARROWINGS = {
    "not narrowed": ({}, ("Person", "Saint", "Place")),
    "a group": ({"group": "Person"}, ("Person", "Saint")),
    "types of a group": ({"types": ["Person", "Saint"]}, ("Person", "Saint")),
    "a class in no group": ({"types": ["Place"]}, ("Place",)),
    "a class of a group and one in none": (
        {"types": ["Saint", "Place"]},
        ("Saint", "Place"),
    ),
}


@pytest.mark.parametrize("narrowing", list(NARROWINGS))
async def test_exact_finds_every_item_whose_vector_repeats_above_the_setting(
    vectors, queries, narrowing
):
    asked, classes = NARROWINGS[narrowing]
    m = declare()
    made = await planted(m)
    wanted = repeated(made, *classes)
    lay = store.layout("default")
    scans = {search.scan_all_query(lay.label), search.scan_query()}

    found = await nearest(vector={"a": ONE}, k=len(wanted) + 3, exact=True, **asked)

    assert found.status == "ok"
    assert {hit.id for hit in found.hits[: len(wanted)]} == wanted
    assert [hit.score for hit in found.hits[: len(wanted)]] == pytest.approx(
        [1.0] * len(wanted), abs=1e-6
    )
    assert all(hit.score < 1 - 1e-6 for hit in found.hits[len(wanted) :])
    assert all(hit.type in classes for hit in found.hits)
    # (no index asked: only the exact scans)
    assert queries and set(queries) <= scans


@pytest.mark.parametrize("narrowing", ["not narrowed", "a group"])
async def test_without_exact_the_index_is_asked_above_the_setting(
    vectors, queries, narrowing
):
    asked, _ = NARROWINGS[narrowing]
    m = declare()
    await planted(m)
    lay = store.layout("default")
    index = lay.group_index_name("Person") if asked else lay.index_name

    found = await nearest(vector={"a": ONE}, k=5, **asked)

    assert found.status == "ok"
    assert search.search_query(index) in queries
    assert search.scan_all_query(lay.label) not in queries
    assert search.scan_query() not in queries
