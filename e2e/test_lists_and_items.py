"""A list with a search, and the page of one item with what it refers to"""

import re

import neo4j
from conftest import MEMGRAPH_AUTH, MEMGRAPH_URI
from helpers import box, hydrated
from playwright.sync_api import Page, expect


def results(page: Page):
    return page.locator("main ul > li")


def test_a_list_shows_every_item_and_how_many(page: Page, data):
    page.goto("/Person")
    expect(results(page)).to_have_count(3)
    expect(page.get_by_title("Found")).to_have_text("3")
    for name in ("Maximilian", "Marie of Burgundy", "Charles the Bold"):
        expect(page.get_by_role("link", name=name)).to_be_visible()


def test_a_search_narrows_the_list_and_is_kept_in_the_address(page: Page, data):
    page.goto("/Person")
    hydrated(page)
    page.get_by_role("searchbox").fill("Maxim")
    expect(results(page)).to_have_count(1)
    expect(page.get_by_title("Found")).to_have_text("1")
    page.wait_for_url("**/Person?q=Maxim")
    page.get_by_role("searchbox").fill("")
    expect(results(page)).to_have_count(3)


def test_typing_is_not_held_up_or_undone_by_the_searches_it_makes(page: Page, data):
    page.goto("/Person")
    hydrated(page)
    box = page.get_by_role("searchbox")
    # (slower than the debounce: a search is made after each key, while the next is typed)
    box.press_sequentially("Marie of B", delay=300)
    expect(box).to_have_value("Marie of B")
    page.wait_for_url("**/Person?q=Marie+of+B")
    expect(results(page)).to_have_count(1)
    expect(box).to_have_value("Marie of B")


def test_typing_on_a_list_page_goes_into_the_search(page: Page, data):
    page.goto("/Person")
    hydrated(page)
    box = page.get_by_role("searchbox", name="Search")
    expect(box).not_to_be_focused()
    # (with no box focused: the first letter is not lost, and the rest follow it)
    page.keyboard.type("Marie")
    expect(box).to_be_focused()
    expect(box).to_have_value("Marie")
    page.wait_for_url("**/Person?q=Marie")
    # (away from the box again, what is typed is added to what is there)
    box.blur()
    page.keyboard.type("x")
    expect(box).to_have_value("Mariex")


def test_there_is_a_space_between_the_console_and_the_list(page: Page, data):
    page.goto("/Person")
    hydrated(page)
    expect(results(page).first).to_be_visible()
    bar = box(page.get_by_role("searchbox", name="Search"))
    row = box(results(page).first)
    assert row["y"] - (bar["y"] + bar["height"]) >= 24


def test_the_arrows_in_the_search_choose_an_item_and_enter_opens_it(page: Page, data):
    page.goto("/Person")
    hydrated(page)
    expect(results(page).first).to_be_visible()
    selected = page.locator("main a[aria-current='true']")
    # (nothing is selected until the box has the focus)
    expect(selected).to_have_count(0)
    page.get_by_role("searchbox", name="Search").focus()
    expect(selected).to_have_count(1)
    first = selected.get_attribute("href")
    assert results(page).first.locator("a").get_attribute("href") == first
    page.keyboard.press("ArrowDown")
    expect(selected).not_to_have_attribute("href", first)
    page.keyboard.press("ArrowUp")
    expect(selected).to_have_attribute("href", first)
    page.keyboard.press("ArrowDown")
    second = selected.get_attribute("href")
    # (the colour of a row the mouse is over)
    plain = results(page).first
    page.mouse.move(800, 5)
    colour = selected.evaluate("e => getComputedStyle(e).backgroundColor")
    plain.hover()
    page.wait_for_function(
        "c => getComputedStyle(document.querySelector('main ul a')).backgroundColor === c", arg=colour
    )
    page.keyboard.press("Enter")
    page.wait_for_url(f"**{second}")


def test_a_new_search_selects_the_top_item(page: Page, data):
    page.goto("/Person")
    hydrated(page)
    box = page.get_by_role("searchbox", name="Search")
    box.focus()
    page.keyboard.press("ArrowDown")
    box.press_sequentially("Marie")
    page.wait_for_url("**/Person?q=Marie")
    selected = page.locator("main a[aria-current='true']")
    expect(selected).to_have_text(re.compile("Marie"))
    assert selected.get_attribute("href") == results(page).first.locator("a").get_attribute("href")
    page.keyboard.press("Enter")
    page.wait_for_url(re.compile(r"/Person/[0-9a-f-]+"))


def test_a_search_with_no_result_says_none(page: Page, data):
    page.goto("/Person")
    hydrated(page)
    page.get_by_role("searchbox").fill("zzzzz")
    expect(results(page)).to_have_count(0)
    expect(page.get_by_title("Found")).to_have_text("0")
    expect(page.get_by_title("Found")).to_have_class(re.compile("text-red-800"))


def test_an_address_with_a_search_shows_it(page: Page, data):
    page.goto("/Person?q=Marie")
    expect(results(page)).to_have_count(1)
    expect(page.get_by_role("searchbox")).to_have_value("Marie")
    expect(page.get_by_role("link", name="Marie of Burgundy")).to_be_visible()


def test_a_deep_search_looks_in_the_documents_and_is_made_when_asked_for(
    page: Page, data
):
    # ("Ghent" is in a statement about Marie, not in her label: an ordinary search does not find it)
    page.goto("/Person?q=Ghent")
    expect(results(page)).to_have_count(0)
    page.goto("/Person")
    hydrated(page)
    deep = page.get_by_role("button", name="Deep search", exact=True)
    expect(deep).to_have_attribute("aria-pressed", "false")
    deep.click()
    expect(deep).to_have_attribute("aria-pressed", "true")
    page.get_by_role("searchbox").fill("Ghent")
    # (a deep search is slow, so typing makes none: all three are still listed)
    page.wait_for_timeout(600)
    expect(results(page)).to_have_count(3)
    page.get_by_role("searchbox").press("Enter")
    page.wait_for_url(re.compile(r"deep=1"))
    expect(results(page)).to_have_count(1)
    expect(page.get_by_role("link", name="Marie of Burgundy")).to_be_visible()
    # (turning it off goes back to the ordinary search of the same text, which finds nothing)
    deep.click()
    expect(deep).to_have_attribute("aria-pressed", "false")
    expect(results(page)).to_have_count(0)


def test_the_run_button_makes_a_deep_search(page: Page, data):
    page.goto("/Person")
    hydrated(page)
    page.get_by_role("button", name="Deep search", exact=True).click()
    page.get_by_role("searchbox").fill("Ghent")
    run = page.get_by_role("button", name="Run deep search (Enter)")
    expect(run).to_be_enabled()
    run.click()
    expect(results(page)).to_have_count(1)
    # (it is up to date: there is nothing to run)
    expect(run).to_be_disabled()


def test_an_item_shows_its_fields_and_what_it_refers_to(page: Page, data):
    page.goto("/Person")
    page.get_by_role("link", name="Maximilian").click()
    page.wait_for_url(f"**/Person/{data.maximilian}")
    expect(page.get_by_role("heading", name="Maximilian")).to_be_visible()
    expect(page.get_by_text("Has role", exact=True)).to_be_visible()
    page.get_by_role("link", name="Maximilian's secretary").click()
    page.wait_for_url(f"**/Role/{data.secretary_role}")
    expect(page.get_by_role("heading", name="Maximilian's secretary")).to_be_visible()
    # (a field that is a type, and what refers to this role from the other side)
    expect(page.get_by_text("Has type", exact=True)).to_be_visible()
    expect(page.get_by_role("link", name=re.compile(r"\bSecretary$"))).to_be_visible()
    expect(page.get_by_role("link", name=re.compile(r"\bMaximilian$"))).to_be_visible()


def test_a_type_in_a_field_leads_to_the_page_of_the_type(page: Page, data):
    page.goto(f"/Role/{data.secretary_role}")
    page.get_by_role("link", name=re.compile(r"\bSecretary$")).click()
    page.wait_for_url(f"**/RoleType/{data.type_id('Secretary')}")
    expect(page.get_by_role("navigation", name="Path")).to_have_text(
        "All›Clerk›Secretary"
    )
    expect(page.get_by_role("link", name="Maximilian's secretary")).to_be_visible()


def test_an_item_with_nothing_to_show_has_no_empty_rows(page: Page, data):
    page.goto(f"/Person/{data.charles}")
    expect(page.get_by_role("heading", name="Charles the Bold")).to_be_visible()
    expect(page.get_by_text("Has role", exact=True)).to_have_count(0)


def test_the_arrows_in_the_search_keep_the_selected_item_on_show_in_a_long_list(page: Page, types):
    # (further than the first page, LIST_PAGE_SIZE: 50)
    api = types.admin()
    for number in range(70):
        api.ok("POST", "/api/Person", {"label": f"Person {number:03d}", "has_role": []})
    page.goto("/Person")
    hydrated(page)
    expect(page.get_by_title("Found")).to_have_text("70")
    page.get_by_role("searchbox", name="Search").focus()
    selected = page.locator("main a[aria-current='true']")

    def clear_of_the_bar():
        expect(selected).to_be_in_viewport(ratio=1)
        box = selected.bounding_box()
        assert box is not None and box["y"] >= 48

    for _ in range(60):
        page.keyboard.press("ArrowDown")
    expect(selected).to_contain_text("Person 060")
    clear_of_the_bar()
    for _ in range(45):
        page.keyboard.press("ArrowUp")
    expect(selected).to_contain_text("Person 015")
    clear_of_the_bar()


def test_a_long_list_is_loaded_as_it_is_scrolled_and_starts_where_it_was_left(
    page: Page, types
):
    # (more than a page, LIST_PAGE_SIZE: 50; numbered so each label is its own)
    api = types.admin()
    for number in range(130):
        api.ok("POST", "/api/Person", {"label": f"Person {number:03d}", "has_role": []})
    page.goto("/Person")
    hydrated(page)
    expect(page.get_by_title("Found")).to_have_text("130")
    # (only what is on show, and a few beyond, is rendered)
    assert results(page).count() < 60

    # The last ones are fetched when they are scrolled to
    page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
    expect(page.locator("main ul > li[data-index='129'] a")).to_be_visible()

    # Where it is is kept in the address, and the page loaded again starts there
    page.evaluate("window.scrollTo(0, document.body.scrollHeight / 2)")
    page.wait_for_url(re.compile(r"[?&]at=\d+"))
    at = int(re.search(r"at=(\d+)", page.url).group(1))  # ty: ignore[possibly-missing-attribute]
    assert 30 < at < 110
    label = page.locator(f"main ul > li[data-index='{at}']").text_content()
    page.reload()
    hydrated(page)
    expect(page.locator(f"main ul > li[data-index='{at}']")).to_have_text(label or "")
    expect(page.locator(f"main ul > li[data-index='{at}']")).to_be_in_viewport()

    # A new search starts at the top
    page.get_by_role("searchbox").fill("Person 00")
    expect(page.get_by_title("Found")).not_to_have_text("130")
    page.wait_for_url(re.compile(r"q=Person"))
    assert "at=" not in page.url
    assert page.evaluate("window.scrollY") == 0


def test_an_entity_that_much_refers_to_has_the_first_of_each_and_reads_more_when_asked(
    page: Page, types
):
    """The page of an entity is read with 25 of what refers to it in each field (thousands made a page of megabytes):
    a row that has more ends in "and N more", which reads them; and a module's view of what refers (by date) says
    how many it is without, and reads them all when asked"""
    api = types.admin()
    philip = api.ok("POST", "/api/Person", {"label": "Philip the Good", "has_role": []})
    person = {"type": "Person", "id": philip["id"]}
    for n in range(30):
        api.ok(
            "POST",
            "/api/Statement",
            {"label": f"Letter {n:02}", "text": "Wrote", "about": person},
        )
    for n in range(27):
        api.ok(
            "POST",
            "/api/Appointment",
            {
                "label": f"Office {n:02}",
                "appointed": person,
                "date": {
                    "type": "ExactDate",
                    "calendar": "julian",
                    "year": 1430 + n,
                },
            },
        )
    try:
        much_refers_to(page, philip["id"])
    finally:
        # (what this made, and nothing else: other tests count the statements and the people)
        driver = neo4j.GraphDatabase.driver(MEMGRAPH_URI, auth=MEMGRAPH_AUTH)
        try:
            driver.execute_query(  # ty: ignore[no-matching-overload]
                "MATCH (n) WHERE (n:Statement AND n.label STARTS WITH 'Letter ') "
                "OR (n:Appointment AND n.label STARTS WITH 'Office ') OR n.id = $id DETACH DELETE n",
                id=philip["id"],
                database_="memgraph",
            )
        finally:
            driver.close()


def much_refers_to(page: Page, philip: str) -> None:
    page.goto(f"/Person/{philip}")
    hydrated(page)
    expect(page.get_by_role("heading", name="Philip the Good")).to_be_visible()
    # (the page reads the person alone, and what refers to them apart: the second list, after the person's own fields)
    expect(page.get_by_test_id("incoming-by-field")).to_be_visible()
    letters = page.get_by_role("link", name=re.compile(r"Letter \d\d$"))
    offices = page.get_by_role("link", name=re.compile(r"Office \d\d$"))
    # (the first 25 of each, by label)
    expect(letters).to_have_count(25)
    expect(offices).to_have_count(25)
    expect(page.get_by_role("link", name="Letter 24")).to_be_visible()
    more = page.get_by_test_id("incoming-more")
    expect(more).to_have_count(2)
    assert sorted(more.all_text_contents()) == ["and 2 more", "and 5 more"]
    with page.expect_response(re.compile(r"/incoming/aboutReverse\?")) as asked:
        more.filter(has_text="and 5 more").click()
    assert asked.value.ok
    expect(letters).to_have_count(30)
    expect(page.get_by_role("link", name="Letter 29")).to_be_visible()
    # (that row has everything now: only the other still has its button)
    expect(more).to_have_text(["and 2 more"])

    # by date (the view of `pangloss_dates`): it has what the page has, says so, and reads the rest
    page.get_by_role("button", name="Sort by date").click()
    dated = page.locator("main section").get_by_test_id("dated-item")
    expect(dated).to_have_count(25)
    notice = page.get_by_test_id("incoming-not-read")
    expect(notice).to_contain_text("2 more refer to this and are not read yet")
    notice.get_by_role("button", name="Read them all").click()
    expect(dated).to_have_count(27)
    expect(notice).to_have_count(0)
    # (and back by field: nothing more to read)
    page.get_by_role("button", name="Sort by date").click()
    expect(offices).to_have_count(27)
    expect(more).to_have_count(0)
