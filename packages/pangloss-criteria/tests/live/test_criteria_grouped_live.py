"""Identical criteria, evaluated once (`evaluate.evaluate_many`, implementation_docs/matches-criteria.md, "Identical
criteria, evaluated once"): jobs in full with the same criteria are one group, evaluated without rule 2; each member's
result is the group's less what its own document names, with exact counts. What each member is given must be what
evaluating it alone (`evaluate`) gives, field by field, with fewer searches"""

import importlib
from typing import Any, no_type_check

import pangloss_core.settings as core_settings
import pangloss_criteria.models
import pytest
from criteria_court_support import Court, secretary_of
from pangloss_core import storage_of
from pangloss_criteria import run_pending
from pangloss_criteria.evaluate import Counts, Job, evaluate, evaluate_many
from pangloss_criteria.pattern import SearchPattern
from pangloss_models import Document, Entity, initialise

pytestmark = pytest.mark.asyncio(loop_scope="session")

evaluating = importlib.import_module("pangloss_criteria.evaluate")

SECRETARIES = ["Waldauf", "Serntein", "Lang", "Dorn", "Fuchsmagen", "Stürtzel"]
HIDDEN = "Hölzl"
"""A secretary whose office is not published: a candidate for a logged-in reader only"""


def models():
    # (the registry was reset, and a module is only run once: its class is declared again)
    importlib.reload(pangloss_criteria.models)
    MatchesCriteria = pangloss_criteria.models.MatchesCriteria

    class Person(Entity):
        title: str | None = None

    class Office(Entity):
        pass

    class HoldsOffice(Document):
        holder: list[Person | MatchesCriteria[Person]]
        office: Office
        employer: Person

    class Activity(Document):
        carried_out_by: list[Person | MatchesCriteria[Person]]
        witnessed_by: list[Person]

    initialise()
    return Person, Office, HoldsOffice, Activity


@no_type_check
async def a_court() -> Court:
    court = Court(*models())
    for name in SECRETARIES:
        await court.holds(name)
    hidden = await court.holds(HIDDEN)
    await storage_of().operations.set_published_in_db(
        court.HoldsOffice, hidden.id, False
    )
    await court.holds("Fugger", office="Banker")
    # (doctors: every secretary, and Fugger)
    for name in [*SECRETARIES, HIDDEN, "Fugger"]:
        court.people[name] = await court.Person.Update(
            id=court.people[name].id, label=name, title="Dr"
        ).save(detail=True)
    await run_pending()
    return court


def ids(court, *names) -> set[str]:
    return {str(court.people[name].id) for name in names}


@no_type_check
def jobs_of(court, criteria) -> list[Job]:
    """Documents with the same criteria, each naming other entities: nothing; a match; a match and one that is not;
    one no reader but a logged-in one sees; and most of the matches"""
    named = {
        "nothing": set(),
        "a match": ids(court, "Waldauf"),
        "a match and another": ids(court, "Serntein", "Fugger", "Maximilian"),
        "a hidden one": ids(court, HIDDEN, "Lang"),
        "the first by label": ids(court, "Dorn", "Fuchsmagen", HIDDEN),
        "none that match": ids(court, "Fugger"),
    }
    return [
        Job(key, SearchPattern(criteria), without) for key, without in named.items()
    ]


class Searches:
    """How many times the operations were asked to search (`count`: `search_ids`, and `search_ids_among`, which is
    one query for searches of one shape on Memgraph); and of those, how many searches in full (`in_full`: not
    among ids given), whatever their shape"""

    def __init__(self, monkeypatch):
        self.count = 0
        self.in_full = 0
        operations = storage_of().operations
        plain, among = operations.search_ids, operations.search_ids_among

        async def search_ids(*args, **kwargs):
            self.count += 1
            self.in_full += 1
            return await plain(*args, **kwargs)

        async def search_ids_among(searches, **kwargs):
            self.count += 1
            return await among(searches, **kwargs)

        monkeypatch.setattr(operations, "search_ids", search_ids)
        monkeypatch.setattr(operations, "search_ids_among", search_ids_among)


async def alone(jobs: list[Job]) -> dict[str, Any]:
    return {job.key: await evaluate(job.pattern, job.without) for job in jobs}


def lower_the_cap(monkeypatch, to: int) -> None:
    monkeypatch.setitem(core_settings.SETTINGS.__dict__, "CRITERIA_MAX_CANDIDATES", to)


def assert_the_same(grouped: dict[str, Any], each: dict[str, Any]) -> None:
    assert set(grouped) == set(each)
    for key, found in each.items():
        got = grouped[key]
        assert got.candidates == found.candidates, key
        assert (got.count, got.count_everyone) == (found.count, found.count_everyone), (
            key
        )
        assert got == found, key


@no_type_check
async def criteria_of(court, kind: str) -> dict:
    """`anchored`: secretaries of Maximilian (from the anchor); `root first`: doctors (no anchor)"""
    if kind == "anchored":
        return secretary_of(
            await court.office("Secretary"), await court.person("Maximilian")
        )
    return {"type": "Person", "where": {"title": {"eq": "Dr"}}}


@no_type_check
@pytest.mark.parametrize("kind", ["anchored", "root first"])
async def test_identical_criteria_are_evaluated_once_and_each_is_given_its_own_result(
    clear_database, monkeypatch, kind
):
    court = await a_court()
    jobs = jobs_of(court, await criteria_of(court, kind))
    each = await alone(jobs)

    searches = Searches(monkeypatch)
    counts = Counts()
    grouped = await evaluate_many(jobs, counts=counts)

    assert_the_same(grouped, each)
    assert counts.shared == len(jobs)
    assert (counts.anchored, counts.root_first) == (
        (1, 0) if kind == "anchored" else (0, 1)
    )
    # (the group's two searches, as each reader; alone, two for each)
    assert searches.count == 2
    assert searches.in_full == (0 if kind == "anchored" else 2)
    # (what the test is of: the documents' results are not all the same)
    assert len({(found.count, found.count_everyone) for found in each.values()}) > 2
    if kind == "anchored":
        assert each["a hidden one"].count == each["a hidden one"].count_everyone + 0
        assert each["nothing"].count == each["nothing"].count_everyone + 1


@no_type_check
@pytest.mark.parametrize("kind", ["anchored", "root first"])
async def test_a_group_whose_result_is_too_broad_has_exact_counts(
    clear_database, monkeypatch, kind
):
    court = await a_court()
    lower_the_cap(monkeypatch, 2)
    jobs = jobs_of(court, await criteria_of(court, kind))
    each = await alone(jobs)
    assert any(found.too_broad for found in each.values())

    searches = Searches(monkeypatch)
    counts = Counts()
    grouped = await evaluate_many(jobs, counts=counts)

    assert_the_same(grouped, each)
    assert counts.shared == len(jobs)
    assert all(len(found.candidates) <= 2 for found in grouped.values())
    # (the group's two, and for each reader one call for every member whose document names something, among those
    # ids; alone, two for each)
    assert searches.count == 4
    assert searches.in_full == (0 if kind == "anchored" else 2)


@no_type_check
async def test_a_member_whose_document_names_too_much_is_evaluated_alone(
    clear_database, monkeypatch
):
    court = await a_court()
    monkeypatch.setattr(evaluating, "MAX_WITHOUT", 2)
    jobs = jobs_of(court, await criteria_of(court, "anchored"))
    each = await alone(jobs)

    counts = Counts()
    grouped = await evaluate_many(jobs, counts=counts)

    assert_the_same(grouped, each)
    # ("a match and another" and "the first by label" name three: alone)
    assert counts.shared == len(jobs) - 2
    assert counts.anchored == 3


@no_type_check
async def test_only_jobs_in_full_are_grouped_and_a_group_of_one_is_as_before(
    clear_database, monkeypatch
):
    court = await a_court()
    criteria = await criteria_of(court, "anchored")
    seeded = Job(
        "seeded",
        SearchPattern(criteria),
        set(),
        among=ids(court, "Waldauf", "Lang", "Fugger"),
    )
    one = Job("one", SearchPattern(await criteria_of(court, "root first")), set())
    in_full = Job("in full", SearchPattern(criteria), ids(court, "Lang"))

    counts = Counts()
    grouped = await evaluate_many([seeded, one, in_full], counts=counts)

    assert counts.shared == 0
    assert (counts.seeded, counts.anchored, counts.root_first) == (1, 1, 1)
    assert [c["label"] for c in grouped["seeded"].candidates] == ["Lang", "Waldauf"]
    assert grouped["one"] == await evaluate(one.pattern)
    assert grouped["in full"] == await evaluate(in_full.pattern, in_full.without)


@no_type_check
async def test_the_ids_of_merged_entities_are_resolved_before_criteria_are_grouped(
    clear_database,
):
    court = await a_court()
    criteria = await criteria_of(court, "anchored")
    other = await court.Person.Create(label="Maximilian I").save()
    await court.Person.merge(absorb=other.id, into=court.people["Maximilian"].id)
    # (written with the absorbed id: the same criteria as the others once resolved)
    absorbed = secretary_of(await court.office("Secretary"), other)
    jobs = [
        Job("as written", SearchPattern(criteria), ids(court, "Waldauf")),
        Job("absorbed", SearchPattern(absorbed), ids(court, "Lang")),
    ]
    counts = Counts()
    grouped = await evaluate_many(jobs, counts=counts)
    assert counts.shared == 2
    assert grouped["absorbed"] == await evaluate(jobs[1].pattern, jobs[1].without)
    assert grouped["as written"] == await evaluate(jobs[0].pattern, jobs[0].without)
