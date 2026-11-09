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
