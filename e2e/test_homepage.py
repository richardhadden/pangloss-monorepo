"""The homepage (the project's own, made by `pangloss interface new-homepage`), its search, and a project's own page"""

from helpers import hydrated
from playwright.sync_api import Page, expect


def test_the_homepage_has_the_name_of_the_project_and_no_results_at_first(page: Page, data):
    page.goto("/")
    hydrated(page)
    expect(page.get_by_role("heading", level=1)).to_have_text("e2e project")
    expect(page.get_by_role("searchbox", name="Search everything")).to_be_focused()
    expect(page.locator("main li")).to_have_count(0)


def test_search_everything_finds_documents_and_entities_and_opens_one(page: Page, data):
    page.goto("/")
    hydrated(page)
    box = page.get_by_role("searchbox", name="Search everything")
    box.fill("Maximilian")
    link = page.locator('main li a[href*="/Person/"]', has_text="Maximilian").first
    expect(link).to_be_visible()
    link.click()
    page.wait_for_url("**/Person/**")


def test_a_type_word_becomes_a_chip_and_backspace_turns_it_back(page: Page, data):
    page.goto("/")
    hydrated(page)
    box = page.get_by_role("searchbox", name="Search everything")
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
    page.get_by_role("navigation", name="Pages").get_by_role("link", name="Home").click()
    expect(page.get_by_role("searchbox", name="Search everything")).to_be_visible()


def test_types_are_offered_while_typing_and_tab_takes_one(page: Page, data):
    page.goto("/")
    hydrated(page)
    box = page.get_by_role("searchbox", name="Search everything")
    box.press_sequentially("pers")
    expect(page.get_by_role("option", name="Person")).to_be_visible()
    expect(page.get_by_test_id("search-type-completion")).to_contain_text("on")
    box.press("Tab")
    expect(page.get_by_test_id("search-type-chip")).to_have_text("Person")
    expect(box).to_have_value("")
    expect(box).to_be_focused()


def test_a_long_type_of_several_words_is_offered_and_finds_what_is_inside_documents(page: Page, data):
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
    box = page.get_by_role("searchbox", name="Search everything")
    box.press_sequentially("creation of")
    expect(page.get_by_role("option")).to_have_text(
        ["Creation of artwork", "Creation of painting", "Creation of physical object"]
    )
    expect(page.get_by_test_id("search-type-completion")).to_contain_text("artwork")
    box.press("Tab")
    chip = page.get_by_test_id("search-type-chip")
    expect(chip).to_have_attribute("data-type-info", "CreationOfArtwork")
    result = page.locator('main li a[href*="/CreationOfPainting/"]', has_text="Making the altarpiece")
    expect(result).to_be_visible()
    result.click()
    page.wait_for_url("**/CreationOfPainting/**")
    expect(page.get_by_text("Making the altarpiece").first).to_be_visible()


def test_more_of_a_type_opens_its_list_with_the_words(page: Page, data):
    page.goto("/")
    hydrated(page)
    box = page.get_by_role("searchbox", name="Search everything")
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
    box = page.get_by_role("searchbox", name="Search everything")
    box.press_sequentially("person ma")
    page.wait_for_url("**/?q=ma&type=Person")
    page.reload()
    hydrated(page)
    expect(page.get_by_test_id("search-type-chip")).to_have_text("Person")
    expect(page.get_by_role("searchbox", name="Search everything")).to_have_value("ma")
    expect(page.locator('main li a[href*="/Person/"]', has_text="Maximilian")).to_be_visible()


def test_results_are_in_the_page_the_server_sends(page: Page, data, stack):
    html = page.request.get("/?q=Maximilian").text()
    assert "Maximilian" in html


def test_select_all_and_backspace_empties_the_chip_too(page: Page, data):
    page.goto("/")
    hydrated(page)
    box = page.get_by_role("searchbox", name="Search everything")
    box.press_sequentially("person ma")
    chip = page.get_by_test_id("search-type-chip")
    expect(chip).to_be_visible()
    box.press("ControlOrMeta+a")
    box.press("Backspace")
    expect(chip).to_have_count(0)
    expect(box).to_have_value("")
    expect(page.locator("main li")).to_have_count(0)
