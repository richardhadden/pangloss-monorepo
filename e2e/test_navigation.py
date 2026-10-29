"""The home page, the navigation bar, pages that are not there"""

from helpers import expand_nav, hydrated, retract_nav
from playwright.sync_api import Page, expect


def test_home_lists_the_models_of_the_project(page: Page, types):
    page.goto("/")
    for model in ("Person", "Role", "RoleType"):
        expect(page.get_by_role("link", name=model, exact=True)).to_be_visible()


def test_a_link_on_the_home_page_opens_the_list(page: Page, data):
    page.goto("/")
    page.get_by_role("link", name="Person", exact=True).click()
    page.wait_for_url("**/Person")
    expect(page.get_by_role("link", name="Maximilian")).to_be_visible()


def test_the_navigation_bar_opens_and_closes(page: Page, types):
    page.goto("/")
    hydrated(page)
    expect(page.get_by_role("button", name="Log in")).to_have_count(0)
    expand_nav(page)
    expect(page.get_by_role("button", name="Log in")).to_be_visible()
    retract_nav(page)
    expect(page.get_by_role("button", name="Log in")).to_have_count(0)


def test_the_navigation_bar_links_to_the_lists(page: Page, data):
    page.goto("/")
    expand_nav(page)
    entities = page.get_by_role("region", name="Entities")
    expect(entities.get_by_role("link", name="Person")).to_be_visible()
    # (a type that is a subclass of another is listed after it, indented)
    expect(entities.get_by_role("link", name="RoleType")).to_be_visible()
    entities.get_by_role("link", name="Person").click()
    page.wait_for_url("**/Person")
    expect(page.get_by_role("link", name="Marie of Burgundy")).to_be_visible()


def test_the_console_names_the_type_of_the_page(page: Page, data):
    page.goto("/Person")
    expect(page.get_by_role("banner", name="Console")).to_contain_text("Persons")
    page.get_by_role("link", name="Maximilian").click()
    page.wait_for_url(f"**/Person/{data.maximilian}")
    expect(page.get_by_role("banner", name="Console")).to_contain_text("Person")
    expect(page.get_by_role("banner", name="Console")).to_contain_text("Maximilian")


def test_a_page_that_is_not_there_is_a_404(page: Page, types):
    response = page.goto("/this/is/not/a/page")
    assert response is not None and response.status == 404
    expect(page.get_by_role("heading", name="Page not found")).to_be_visible()


def test_an_item_that_is_not_there_is_explained(page: Page, types):
    page.goto("/Person/00000000-0000-0000-0000-000000000000")
    expect(page.get_by_role("alert")).to_be_visible()


def test_a_type_that_is_not_a_model_is_explained(page: Page, types):
    page.goto("/Nonsense")
    expect(
        page.get_by_role("alert").or_(page.get_by_text("No results")).first
    ).to_be_visible()


def test_the_server_sends_the_data_in_the_page(page: Page, data):
    # (server-side rendering: the first response has what is shown, streamed in; a browser without scripts only gets
    # the placeholders until a script puts the streamed parts in place, which is how Solid streams)
    for path, texts in {
        "/Person": ["Maximilian", "Marie of Burgundy", "Charles the Bold"],
        f"/Person/{data.maximilian}": ["Maximilian", "Maximilian&#39;s secretary"],
    }.items():
        body = page.request.get(path).text()
        for text in texts:
            assert text in body or text.replace("&#39;", "'") in body, (path, text)


def test_clicking_the_button_of_the_bar_while_the_mouse_is_over_it_closes_it(
    page: Page, types
):
    # (the bar opens when the mouse comes over it, so someone who clicks it to open it closes it again: how it is now,
    # recorded here so that a change to it is seen)
    page.goto("/")
    hydrated(page)
    page.get_by_role("button", name="Expand the navigation bar").click()
    expect(page.get_by_role("button", name="Expand the navigation bar")).to_be_visible()
