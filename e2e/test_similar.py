"""Similarity (`pangloss_vectors`, with the graph part of `pangloss_fastrp`): its interface module adds a "Similar"
section after the contents of the page of every document and entity (`itemSections.Similar`), and a part of /admin
with the state of the vectors and a Rebuild button (`slots.admin`). The session rebuilds the vectors once, after the
project's data is made (conftest.py); the worker in the server keeps them current after each write, so each test
waits for it by asking the route until the item is worked out."""

import re
import time
from types import SimpleNamespace

import pytest
from conftest import OTHER_PASSWORD, OTHER_USERNAME, AUTHOR_PASSWORD, AUTHOR_USERNAME, Stack, forget
from helpers import hydrated, pick, until_similar
from playwright.sync_api import Page, expect


def made(api, kind: str, label: str, **fields) -> str:
    return api.ok("POST", f"/api/{kind}", {"label": label, **fields})["id"]


def ref(kind: str, id_: str) -> dict:
    return {"type": kind, "id": id_}


def similar_section(page: Page):
    return page.get_by_test_id("similar-section")


def rows_of(page: Page):
    return similar_section(page).get_by_test_id("similar-row")


def hrefs(page: Page) -> list[str]:
    return [link.get_attribute("href") or "" for link in rows_of(page).locator("a").all()]


@pytest.fixture
def families(types: Stack) -> SimpleNamespace:
    """Two families, each of three people who met (a `Meeting` of the three), and two people joined to nothing: the
    graph part sees the families through the meetings. Waits for the worker to have worked out Ann's similar"""
    forget("Meeting")
    api = types.admin()

    def person(name: str) -> str:
        return made(api, "Person", name, has_role=[])

    fairfax = {name: person(f"{name} Fairfax") for name in ("Ann", "Bea", "Cyd")}
    grey = {name: person(f"{name} Grey") for name in ("Dov", "Eli", "Fay")}
    alone = {name: person(f"{name} Alone") for name in ("Hal", "Ivo")}
    meetings = {
        "fairfax": made(api, "Meeting", "The Fairfaxes meet", attendees=[ref("Person", id_) for id_ in fairfax.values()]),
        "grey": made(api, "Meeting", "The Greys meet", attendees=[ref("Person", id_) for id_ in grey.values()]),
    }
    ann = fairfax["Ann"]
    family = {fairfax["Bea"], fairfax["Cyd"]}
    # (the family first, and the two joined to nothing after them, people as she is; the other family is like her
    # only in being people, which the chance of the graph part can take away: an item of a similarity of 0 or less
    # is not given)
    others = set(alone.values())
    until_similar(
        api,
        "Person",
        ann,
        lambda answer: {r["id"] for r in answer["results"][:2]} == family
        and others <= {r["id"] for r in answer["results"]},
        type="Person",
    )
    return SimpleNamespace(api=api, ann=ann, family=family, fairfax=fairfax, grey=grey, alone=alone, meetings=meetings)


def test_a_person_s_page_lists_their_family_first_as_chips_with_bars(page: Page, families):
    page.goto(f"/Person/{families.ann}")
    hydrated(page)
    section = similar_section(page)
    expect(section.locator("h2")).to_have_text("Similar")
    rows = rows_of(page)
    expect(rows.first).to_be_visible()
    expect(rows).not_to_have_count(0)
    # (nearest first: the two others of the family, then the rest)
    first_two = [rows.nth(n).locator("a").get_attribute("href") for n in (0, 1)]
    assert {href.rsplit("/", 1)[-1] for href in first_two if href} == families.family
    figures = [float(rows.nth(n).get_attribute("data-similarity") or "nan") for n in range(rows.count())]
    assert figures == sorted(figures, reverse=True)
    # (nothing that has nothing in common with her)
    assert all(figure > 0 for figure in figures)
    # (Ann is not among her own similar)
    assert f"/Person/{families.ann}" not in hrefs(page)
    # (each a chip, with a bar of its similarity that has a name, and the figure)
    first = rows.first
    expect(first.locator("a")).to_contain_text(re.compile(r"(Bea|Cyd) Fairfax"))
    bar = first.get_by_role("meter")
    expect(bar).to_have_attribute("aria-label", re.compile(r"^Similarity \d\.\d\d$"))
    expect(first).to_contain_text(re.compile(r"\d\.\d\d$"))
    # (the chips are one column, the bars another)
    chips = [box for box in (rows.nth(n).locator("a").bounding_box() for n in range(rows.count())) if box]
    bars = [box for box in (rows.nth(n).get_by_role("meter").bounding_box() for n in range(rows.count())) if box]
    assert len({round(box["x"]) for box in chips}) == 1
    assert len({round(box["x"]) for box in bars}) == 1


def test_the_menu_of_types_narrows_the_similar_to_people(page: Page, families):
    page.goto(f"/Person/{families.ann}")
    hydrated(page)
    menu = similar_section(page).get_by_role("combobox", name="Type")
    # (all types to start with, though a person is in the group of people)
    expect(menu).to_contain_text("All types")
    expect(rows_of(page).first).to_be_visible()
    # (the meetings are among all types)
    expect(rows_of(page).locator('a[href^="/Meeting/"]')).not_to_have_count(0)
    pick(menu, "Person")
    expect(rows_of(page).locator('a[href^="/Meeting/"]')).to_have_count(0)
    shown = {href.rsplit("/", 1)[-1] for href in hrefs(page)}
    assert families.family | set(families.alone.values()) <= shown
    assert all(href.startswith("/Person/") for href in hrefs(page))
    assert page.url.endswith(f"/Person/{families.ann}")


def test_a_nested_document_s_page_has_the_section(page: Page, types: Stack):
    """A bequest is part of a will: its page shows it inside the will, and the similar of the bequest itself"""
    forget("Will", "Bequest")
    api = types.admin()
    testator = made(api, "Person", "Thea Testator", has_role=[])
    heir = made(api, "Person", "Hugo Heir", has_role=[])
    will = made(
        api,
        "Will",
        "Will of Thea Testator",
        testator=ref("Person", testator),
        bequests=[
            {"type": "Bequest", "label": f"{item} to Hugo Heir", "item": item, "recipient": ref("Person", heir)}
            for item in ("A ring", "A book")
        ],
    )
    ring, book = (bequest["id"] for bequest in api.ok("GET", f"/api/Will/{will}")["bequests"])
    until_similar(api, "Bequest", ring, lambda answer: book in {r["id"] for r in answer["results"]})

    page.goto(f"/Bequest/{ring}")
    hydrated(page)
    expect(similar_section(page)).to_be_visible()
    expect(rows_of(page).locator(f'a[href="/Bequest/{book}"]')).to_be_visible()


@pytest.fixture
def reports(types: Stack) -> SimpleNamespace:
    """Three reports by ann: two published (by e2e, who did not make them) and one not. With `VECTORS_GRAPH_SEES` at
    its default, `everyone`, the unpublished one is not in the graph; it has a vector of the class part, as every
    report does, and so is the nearest of the others to a reader who may see it"""
    forget("Report", "ReportSection", "PGReviewComment", "Hearing", "Testimony")
    author = types.client(AUTHOR_USERNAME, AUTHOR_PASSWORD)
    api = types.admin()

    def report(label: str) -> str:
        return made(author, "Report", label, text="Things happened", sections=[], findings=[])

    first, second, waiting = report("First report"), report("Second report"), report("Waiting report")
    for published in (first, second):
        api.ok("POST", f"/api/review/{published}/status", {"status": "published"})
    # (as the logged-in reader sees them: the unpublished one too)
    until_similar(api, "Report", first, lambda answer: {second, waiting} <= {r["id"] for r in answer["results"]})
    return SimpleNamespace(first=first, second=second, waiting=waiting)


def test_a_reader_not_logged_in_never_sees_an_unpublished_item_among_the_similar(page: Page, reports):
    page.goto(f"/Report/{reports.first}")
    hydrated(page)
    expect(rows_of(page).locator(f'a[href="/Report/{reports.second}"]')).to_be_visible()
    expect(rows_of(page).locator(f'a[href="/Report/{reports.waiting}"]')).to_have_count(0)

    from conftest import PASSWORD, USERNAME

    response = page.request.post("/api/users/session", form={"username": USERNAME, "password": PASSWORD})
    assert response.ok, response.text()
    page.goto(f"/Report/{reports.first}")
    hydrated(page)
    expect(rows_of(page).locator(f'a[href="/Report/{reports.waiting}"]')).to_be_visible()


def vectors_admin(page: Page):
    return page.get_by_test_id("admin-vectors")


@pytest.fixture
def rebuild_jobs_forgotten(types: Stack):
    """After the test, the rebuild's job taken off the list of jobs once it is over, so that the tests of /admin find
    only their own"""
    yield
    api = types.admin()
    deadline = time.monotonic() + 60
    while True:
        jobs = [job for job in api.ok("GET", "/api/admin/jobs")["jobs"] if job["kind"] == "vectors_rebuild"]
        if all(job["state"] not in ("queued", "running") for job in jobs):
            break
        assert time.monotonic() < deadline, jobs
        time.sleep(0.3)
    for job in jobs:
        api.ok("DELETE", f"/api/admin/jobs/{job['id']}")


def test_the_admin_section_shows_the_figures_and_rebuild_changes_them_without_a_reload(
    logged_in: Page, rebuild_jobs_forgotten
):
    page = logged_in
    page.goto("/admin")
    hydrated(page)
    section = vectors_admin(page)
    expect(section.locator("h2")).to_have_text("Similarity")
    part = section.locator('[data-testid="vectors-part-row"][data-part="class"]')
    expect(part).to_be_visible()
    expect(section.locator('[data-testid="vectors-part-row"][data-part="graph"]')).to_be_visible()
    expect(section.locator('[data-testid="vectors-profile-row"][data-profile="default"]')).to_contain_text("class 0.1, graph 1")
    generation = part.get_by_test_id("vectors-generation")
    expect(generation).to_have_text(re.compile(r"^\d+$"))
    before = generation.inner_text()
    page.evaluate("window.__notReloaded = true")

    button = section.get_by_role("button", name="Rebuild", exact=True)
    expect(button).to_be_enabled()
    button.click()
    # (the job's process rebuilds every part: the feed brings the new generation)
    expect(generation).not_to_have_text(before, timeout=60_000)
    assert page.evaluate("window.__notReloaded") is True
    expect(button).to_be_enabled(timeout=30_000)


def test_someone_who_is_not_an_admin_does_not_get_the_section(page: Page, types: Stack):
    response = page.request.post("/api/users/session", form={"username": OTHER_USERNAME, "password": OTHER_PASSWORD})
    assert response.ok, response.text()
    page.goto("/admin")
    hydrated(page)
    expect(page.get_by_test_id("admin-page")).to_have_count(0)
    expect(vectors_admin(page)).to_have_count(0)
