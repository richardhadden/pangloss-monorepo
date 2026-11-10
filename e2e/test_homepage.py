"""The homepage (the project's own, made by `pangloss interface new-homepage`), its search, and a project's own page"""

import re
import subprocess

from helpers import expand_nav, hydrated
from playwright.sync_api import Page, expect


def test_the_homepage_has_the_name_of_the_project_and_no_results_at_first(
    page: Page, data
):
    page.goto("/")
    hydrated(page)
    expect(page.get_by_role("heading", level=1)).to_have_text("e2e project")
    expect(page.get_by_role("searchbox", name="Quick search")).to_be_focused()
    expect(page.locator("main li")).to_have_count(0)


def test_search_everything_finds_documents_and_entities_and_opens_one(page: Page, data):
    page.goto("/")
    hydrated(page)
    box = page.get_by_role("searchbox", name="Quick search")
    box.fill("Maximilian")
    link = page.locator('main li a[href*="/Person/"]', has_text="Maximilian").first
    expect(link).to_be_visible()
    link.click()
    page.wait_for_url("**/Person/**")


def test_the_arrows_choose_a_result_and_enter_opens_it(page: Page, data):
    page.goto("/")
    hydrated(page)
    box = page.get_by_role("searchbox", name="Quick search")
    box.fill("Maximilian")
    link = page.locator("main li a", has_text="Maximilian").first
    expect(link).to_be_visible()
    href = link.get_attribute("href")
    box.press("ArrowDown")
    expect(page.locator("main li[aria-current]")).to_have_count(1)
    expect(box).to_be_focused()
    box.press("Enter")
    page.wait_for_url(f"**{href}")


def test_an_item_links_to_its_json_in_a_new_tab(page: Page, data):
    page.goto("/")
    hydrated(page)
    page.get_by_role("searchbox", name="Quick search").fill("Maximilian")
    page.locator('main li a[href*="/Person/"]', has_text="Maximilian").first.click()
    page.wait_for_url("**/Person/**")
    item_id = page.url.rsplit("/", 1)[-1]
    rdf = page.get_by_role("button", name="View as RDF")
    rdf.click()
    expect(page.get_by_role("menuitem")).to_have_count(6)
    # (really on the screen: the console bar clips what is placed in it, and a click by the test would scroll to it anyway)
    assert page.get_by_role("menuitem", name="N-Quads").evaluate(
        "e => { const b = e.getBoundingClientRect(); return document.elementFromPoint(b.x + b.width / 2, b.y + b.height / 2) === e }"
    )
    expect(page.get_by_role("link", name="View as JSON")).to_have_count(0)
    with page.context.expect_page() as opened:
        page.get_by_role("menuitem", name="API JSON").click()
    opened.value.wait_for_load_state()
    assert opened.value.url.endswith(f"/api/Person/{item_id}")
    assert f'"id":"{item_id}"' in opened.value.content()
    rdf.click()
    with page.context.expect_page() as opened:
        page.get_by_role("menuitem", name="JSON-LD").click()
    opened.value.wait_for_load_state()
    assert f"/api/rdf/Person/{item_id}?format=jsonld" in opened.value.url
    assert f"Person/{item_id}" in opened.value.content()
    expect(page.get_by_role("menu")).to_have_count(0)
    # (the keys: Down opens it and goes in, Escape closes it and comes back)
    rdf.focus()
    page.keyboard.press("ArrowDown")
    expect(page.get_by_role("menuitem", name="Turtle")).to_be_focused()
    page.keyboard.press("ArrowDown")
    expect(page.get_by_role("menuitem", name="JSON-LD")).to_be_focused()
    page.keyboard.press("Escape")
    expect(page.get_by_role("menu")).to_have_count(0)
    expect(rdf).to_be_focused()
    # (a click elsewhere closes it)
    rdf.click()
    page.locator("main").click(position={"x": 5, "y": 5})
    expect(page.get_by_role("menu")).to_have_count(0)
    # (a URI of the export, through the interface's server: the data for a client of it, and text for a browser)
    origin = page.url.split("/Person/")[0]
    data = page.request.get(
        f"{origin}/entity/Person/{item_id}", headers={"Accept": "text/turtle"}
    )
    assert data.ok and data.headers["content-type"].startswith("text/turtle")
    assert item_id in data.text()
    page.goto(f"/entity/Person/{item_id}")
    assert f"/api/rdf/Person/{item_id}" in page.url


def test_a_type_word_becomes_a_chip_and_backspace_turns_it_back(page: Page, data):
    page.goto("/")
    hydrated(page)
    box = page.get_by_role("searchbox", name="Quick search")
    box.press_sequentially("person ")
    chip = page.get_by_test_id("search-type-chip")
    expect(chip).to_have_text("Person")
    expect(box).to_have_value("")
    # (the chip alone lists the most connected of the type)
    expect(page.locator('main li a[href*="/Person/"]').first).to_be_visible()
    box.press("Backspace")
    expect(chip).to_have_count(0)
    expect(box).to_have_value("person")


def test_the_console_links_the_pages_and_marks_where_you_are(page: Page, data):
    page.goto("/")
    hydrated(page)
    console = page.get_by_role("navigation", name="Pages")
    console.get_by_role("link", name="About").click()
    page.wait_for_url("**/about")
    expect(page.get_by_role("heading", level=1, name="About")).to_be_visible()
    hydrated(page)
    page.get_by_role("navigation", name="Pages").get_by_role(
        "link", name="Home"
    ).click()
    expect(page.get_by_role("searchbox", name="Quick search")).to_be_visible()


def test_types_are_offered_while_typing_and_tab_takes_one(page: Page, data):
    page.goto("/")
    hydrated(page)
    box = page.get_by_role("searchbox", name="Quick search")
    box.press_sequentially("pers")
    expect(page.get_by_role("option", name="Person")).to_be_visible()
    expect(page.get_by_test_id("search-type-completion")).to_contain_text("on")
    box.press("Tab")
    expect(page.get_by_test_id("search-type-chip")).to_have_text("Person")
    expect(box).to_have_value("")
    expect(box).to_be_focused()


def test_a_long_type_of_several_words_is_offered_and_finds_what_is_inside_documents(
    page: Page, data
):
    painting = data.api.ok("POST", "/api/Painting", {"label": "The altarpiece"})["id"]
    data.api.ok(
        "POST",
        "/api/Provenance",
        {
            "label": "Where it came from",
            "subject": {"type": "Painting", "id": painting},
            "steps": [{"type": "CreationOfPainting", "label": "Making the altarpiece"}],
        },
    )
    page.goto("/")
    hydrated(page)
    box = page.get_by_role("searchbox", name="Quick search")
    box.press_sequentially("creation of")
    expect(page.get_by_role("option")).to_have_text(
        ["Creation of artwork", "Creation of painting", "Creation of physical object"]
    )
    expect(page.get_by_test_id("search-type-completion")).to_contain_text("artwork")
    box.press("Tab")
    chip = page.get_by_test_id("search-type-chip")
    expect(chip).to_have_attribute("data-type-info", "CreationOfArtwork")
    result = page.locator(
        'main li a[href*="/CreationOfPainting/"]', has_text="Making the altarpiece"
    )
    expect(result).to_be_visible()
    result.click()
    page.wait_for_url("**/CreationOfPainting/**")
    expect(page.get_by_text("Making the altarpiece").first).to_be_visible()


def test_more_of_a_type_opens_its_list_with_the_words(page: Page, data):
    page.goto("/")
    hydrated(page)
    box = page.get_by_role("searchbox", name="Quick search")
    box.press_sequentially("person ma")
    more = page.get_by_test_id("search-more")
    expect(more).to_have_attribute("href", "/Person?q=ma")
    expect(more).to_contain_text("More")
    more.click()
    page.wait_for_url("**/Person?q=ma")
    expect(page.get_by_role("link", name="Maximilian")).to_be_visible()


def test_the_search_is_kept_in_the_address_and_comes_back(page: Page, data):
    page.goto("/")
    hydrated(page)
    box = page.get_by_role("searchbox", name="Quick search")
    box.press_sequentially("person ma")
    page.wait_for_url("**/?q=ma&type=Person")
    page.reload()
    hydrated(page)
    expect(page.get_by_test_id("search-type-chip")).to_have_text("Person")
    expect(page.get_by_role("searchbox", name="Quick search")).to_have_value("ma")
    expect(
        page.locator('main li a[href*="/Person/"]', has_text="Maximilian")
    ).to_be_visible()


def test_results_are_in_the_page_the_server_sends(page: Page, data, stack):
    html = page.request.get("/?q=Maximilian").text()
    assert "Maximilian" in html


def test_select_all_and_backspace_empties_the_chip_too(page: Page, data):
    page.goto("/")
    hydrated(page)
    box = page.get_by_role("searchbox", name="Quick search")
    box.press_sequentially("person ma")
    chip = page.get_by_test_id("search-type-chip")
    expect(chip).to_be_visible()
    box.press("ControlOrMeta+a")
    box.press("Backspace")
    expect(chip).to_have_count(0)
    expect(box).to_have_value("")
    expect(page.locator("main li")).to_have_count(0)


def test_a_project_page_passes_the_type_check(stack):
    # (the pages are outside the interface's workspace, so the types of their JSX have to be found from there)
    assert (stack.project / "pages/About.tsx").exists()
    done = subprocess.run(
        ["npx", "tsc", "--noEmit", "-p", "interface-app/tsconfig.json"],
        cwd=stack.project / ".pangloss/interface",
        capture_output=True,
        text=True,
        check=False,
    )
    assert [
        line for line in done.stdout.splitlines() if "pages/About.tsx" in line
    ] == []


def test_changing_the_language_leaves_what_is_in_the_search_box_alone(page: Page, data):
    """The box is given its text once, from the address the page was opened at; a change of language draws its words
    again (the label, the placeholder), and until 2026-11-10 put that first text back with them"""
    # (opened with a search in the address, which is then deleted: the box stays empty)
    page.goto("/?q=Maximilian")
    hydrated(page)
    box = page.locator('main input[type="search"]')
    expect(box).to_have_value("Maximilian")
    expect(page.locator("main li[data-item-id]").first).to_be_visible()
    box.fill("")
    expect(page).to_have_url(re.compile(r"/$"))
    expand_nav(page)
    page.get_by_role("button", name="Deutsch").click()
    expect(page.locator("html")).to_have_attribute("lang", "de")
    expect(box).to_have_attribute("placeholder", re.compile(r"^(?!Quick search).+"))
    expect(box).to_have_value("")

    # (and what has been typed since the page was opened is not taken away either)
    box.fill("Marie")
    expect(page.locator("main li[data-item-id]").first).to_be_visible()
    page.get_by_role("button", name="English").click()
    expect(page.locator("html")).to_have_attribute("lang", "en")
    expect(box).to_have_attribute("placeholder", "Quick search")
    expect(box).to_have_value("Marie")
