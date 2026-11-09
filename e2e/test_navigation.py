"""The home page, the navigation bar, pages that are not there"""

import re

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
    # (the types of a typology are under a heading of their own, not Entities)
    expect(entities.get_by_role("link", name="Role type")).to_have_count(0)
    typologies = page.get_by_role("region", name="Typologies")
    expect(typologies.get_by_role("link", name="Role type")).to_be_visible()
    entities.get_by_role("link", name="Person").click()
    page.wait_for_url("**/Person")
    expect(page.get_by_role("link", name="Marie of Burgundy")).to_be_visible()


def test_the_shortcut_opens_the_navigation_bar_with_the_cursor_in_the_filter(page: Page, data):
    page.goto("/Person")
    hydrated(page)
    box = page.get_by_role("searchbox", name="Search")
    box.fill("Mar")
    filter_box = page.get_by_label("Filter types")
    expect(filter_box).to_have_count(0)
    page.keyboard.press("ControlOrMeta+k")
    expect(filter_box).to_be_focused()
    page.keyboard.type("stat")
    expect(filter_box).to_have_value("stat")
    expect(
        page.get_by_role("navigation", name="Main").get_by_role("link", name="Person")
    ).to_have_count(0)
    # (Escape clears it, then closes the bar and gives the focus back)
    page.keyboard.press("Escape")
    expect(filter_box).to_have_value("")
    page.keyboard.press("Escape")
    expect(filter_box).to_have_count(0)
    expect(box).to_be_focused()


def test_the_filter_of_the_types_chooses_with_the_arrows_and_enter_opens_the_list(page: Page, data):
    page.goto("/")
    hydrated(page)
    page.keyboard.press("ControlOrMeta+k")
    page.keyboard.type("r")
    nav = page.get_by_role("navigation", name="Main")
    selected = nav.locator("a[aria-current='true']")
    first = selected.get_attribute("href")
    page.keyboard.press("ArrowDown")
    expect(selected).not_to_have_attribute("href", first or "")
    page.keyboard.press("ArrowUp")
    expect(selected).to_have_attribute("href", first or "")
    # (a new item is for someone logged in: nothing happens)
    page.get_by_label("Filter types").fill("Person")
    expect(selected).to_have_attribute("href", "/Person")
    page.keyboard.press("ControlOrMeta+Enter")
    assert not page.url.endswith("/new")
    page.keyboard.press("Enter")
    page.wait_for_url("**/Person")
    expect(page.get_by_label("Filter types")).to_have_count(0)


def test_the_filter_of_the_types_makes_a_new_item_for_someone_logged_in(page: Page, data, logged_in):
    page.goto("/")
    hydrated(page)
    page.keyboard.press("ControlOrMeta+k")
    page.keyboard.type("Person")
    expect(page.get_by_role("navigation", name="Main").locator("a[aria-current='true']")).to_have_attribute(
        "href", "/Person"
    )
    page.keyboard.press("ControlOrMeta+Enter")
    page.wait_for_url("**/Person/new")
    expect(page.get_by_role("button", name="Save")).to_be_visible()


def test_the_types_in_the_navigation_bar_are_filtered(page: Page, data):
    page.goto("/")
    expand_nav(page)
    nav = page.get_by_role("navigation", name="Main")
    nav.get_by_label("Filter types").fill("ERSO")
    expect(nav.get_by_role("link", name="Person")).to_be_visible()
    expect(nav.get_by_role("link", name="Statement")).to_have_count(0)
    nav.get_by_label("Filter types").fill("nothing like this")
    expect(nav).to_contain_text("No types match")
    nav.get_by_role("button", name="Clear the filter").click()
    expect(nav.get_by_label("Filter types")).to_have_value("")
    expect(nav.get_by_role("link", name="Statement")).to_be_visible()
    # (Escape clears it too)
    nav.get_by_label("Filter types").fill("stat")
    expect(nav.get_by_role("link", name="Person")).to_have_count(0)
    nav.get_by_label("Filter types").press("Escape")
    expect(nav.get_by_role("link", name="Person")).to_be_visible()


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
    # (rendered on the server: the built server puts "Internal Server Error" in place of an error it is not told is
    # safe to show, and this page said that, where the development server said what it should)
    page.goto("/Person/00000000-0000-0000-0000-000000000000")
    # (in the server's language first, then in the one this browser has chosen)
    not_found = re.compile("Page not found|Seite nicht gefunden")
    expect(page.get_by_role("heading", name=not_found)).to_be_visible()
    expect(page.get_by_role("alert")).to_contain_text(
        re.compile("There is nothing here|Hier ist nichts")
    )
    expect(page.locator("main")).not_to_contain_text("Internal Server Error")
    hydrated(page)
    expect(page.get_by_role("heading", name=not_found)).to_be_visible()


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


def test_clicking_the_button_of_the_bar_while_the_mouse_is_over_it_pins_it(
    page: Page, types
):
    # (the bar opens when the mouse comes over it, and its button is then a pin)
    page.goto("/")
    expand_nav(page)
    page.get_by_role("button", name="Pin the navigation bar open").click()
    expect(page.get_by_role("button", name="Unpin the navigation bar")).to_be_visible()


def pin_nav(page: Page) -> None:
    expand_nav(page)
    page.get_by_role("button", name="Pin the navigation bar open").click()
    expect(page.get_by_role("button", name="Unpin the navigation bar")).to_be_visible()


def test_a_pinned_bar_stays_open_when_the_mouse_leaves(page: Page, types):
    page.goto("/")
    pin_nav(page)
    page.mouse.move(600, 400)
    expect(page.get_by_role("button", name="Log in")).to_be_visible()
    expect(page.get_by_role("button", name="Unpin the navigation bar")).to_be_visible()


def test_unpinning_lets_the_bar_close_again(page: Page, types):
    page.goto("/")
    pin_nav(page)
    page.get_by_role("button", name="Unpin the navigation bar").click()
    retract_nav(page)
    expect(page.get_by_role("button", name="Log in")).to_have_count(0)


def test_a_pinned_bar_stays_open_when_a_link_is_followed(page: Page, data):
    page.goto("/")
    pin_nav(page)
    page.get_by_role("region", name="Entities").get_by_role(
        "link", name="Person"
    ).click()
    page.wait_for_url("**/Person")
    page.mouse.move(900, 400)
    expect(page.get_by_role("button", name="Unpin the navigation bar")).to_be_visible()


def test_the_page_and_the_console_move_across_for_a_pinned_bar(page: Page, data):
    page.goto("/Person")
    hydrated(page)
    console = page.get_by_role("banner", name="Console")
    expect(console).to_be_visible()
    assert page.viewport_size is not None
    width = page.viewport_size["width"]
    before = console.bounding_box()
    assert before is not None
    assert before["x"] < 288  # (it is under where the pinned bar will be)
    pin_nav(page)
    page.mouse.move(width - 20, 400)
    bar = page.locator("nav[aria-label='Main']").bounding_box()
    expect(console).to_have_js_property("offsetLeft", 320)
    after = console.bounding_box()
    assert bar is not None and after is not None
    assert after["x"] >= bar["x"] + bar["width"]
    # (the padding of the page is transitioned: wait for it)
    page.wait_for_function(
        "([text, edge]) => [...document.querySelectorAll('a')]"
        ".find((a) => a.textContent.includes(text)).getBoundingClientRect().x >= edge",
        arg=["Maximilian", bar["x"] + bar["width"]],
    )
    # still centred on the page beside the bar: the same space on each side
    left = after["x"] - (bar["x"] + bar["width"])
    right = width - (after["x"] + after["width"])
    assert abs(left - right) <= 1


def test_the_pin_is_remembered(page: Page, types):
    page.goto("/")
    pin_nav(page)
    page.reload()
    hydrated(page)
    expect(page.get_by_role("button", name="Unpin the navigation bar")).to_be_visible()
    page.get_by_role("button", name="Unpin the navigation bar").click()
    page.reload()
    hydrated(page)
    page.mouse.move(600, 400)
    expect(page.get_by_role("button", name="Expand the navigation bar")).to_be_visible()


def translation_requests(page: Page) -> list[str]:
    requests: list[str] = []
    page.on(
        "request",
        lambda request: requests.append(request.url)
        if "loadTranslations" in request.url
        else None,
    )
    return requests


def test_another_language_is_fetched_only_when_it_is_chosen(page: Page, types):
    requests = translation_requests(page)
    page.goto("/")
    expand_nav(page)
    # (English comes with the page: nothing was asked for)
    expect(page.get_by_role("button", name="Log in")).to_be_visible()
    assert requests == []
    page.get_by_role("button", name="Deutsch").click()
    expect(page.locator("html")).to_have_attribute("lang", "de")
    expect(page.get_by_role("button", name="Anmelden")).to_be_visible()
    assert len(requests) == 1
    # back and forth: the German is kept, not fetched again
    page.get_by_role("button", name="English").click()
    expect(page.get_by_role("button", name="Log in")).to_be_visible()
    page.get_by_role("button", name="Deutsch").click()
    expect(page.get_by_role("button", name="Anmelden")).to_be_visible()
    assert len(requests) == 1


def test_the_language_chosen_is_kept_over_a_reload(page: Page, types):
    page.goto("/")
    expand_nav(page)
    page.get_by_role("button", name="Deutsch").click()
    expect(page.locator("html")).to_have_attribute("lang", "de")
    page.reload()
    hydrated(page)
    expect(page.locator("html")).to_have_attribute("lang", "de")
    # (the labels of the bar are German now, so it is found by its tag)
    page.locator("nav").hover()
    expect(page.get_by_role("button", name="Anmelden")).to_be_visible()


def test_the_names_of_models_follow_the_language(page: Page, data):
    page.goto("/Person")
    expand_nav(page)
    page.get_by_role("button", name="Deutsch").click()
    # (the console names the page in the plural of the language; the e2e project has no German
    # model texts, so the names stay: the words of the interface itself are what change, the console's own name too)
    expect(page.get_by_role("button", name="Anmelden")).to_be_visible()
    expect(page.get_by_role("banner", name="Konsole")).to_contain_text("Persons")


def test_an_item_that_disappears_on_logging_out_is_a_404_and_leaves_no_label(
    logged_in: Page, data
):
    # (an unpublished document is seen only when logged in: the API's answer for it is then a 404; it is simulated here
    # because the e2e project has no review of documents)
    from conftest import USERNAME

    page = logged_in
    page.goto(f"/Person/{data.maximilian}")
    hydrated(page)
    console = page.get_by_role("banner", name="Console")
    expect(console).to_contain_text("Maximilian")
    page.route(
        f"**/api/Person/{data.maximilian}*",
        lambda route: route.fulfill(
            status=404,
            content_type="application/json",
            body='{"detail":"There is no Person with id X"}',
        ),
    )
    expand_nav(page)
    page.get_by_role("button", name=f"Log out {USERNAME}").click()
    expect(page.get_by_role("heading", name="Page not found")).to_be_visible()
    expect(page.get_by_role("alert")).to_contain_text("may not exist, or you may need to log in")
    expect(page.get_by_role("alert")).not_to_contain_text("There is no Person with id")
    expect(console).not_to_contain_text("Maximilian")


def test_following_a_link_to_an_item_that_is_gone_is_a_404(page: Page, data):
    # (a list read before the item was deleted: its page is asked for in the browser, not rendered on the server)
    page.goto("/Person")
    hydrated(page)
    data.api.ok("DELETE", f"/api/Person/{data.charles}")
    errors: list[str] = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.get_by_role("link", name="Charles the Bold").click()
    page.wait_for_url(f"**/Person/{data.charles}")
    expect(page.get_by_role("heading", name="Page not found")).to_be_visible()
    assert errors == []
    # (the interface still works)
    page.go_back()
    expect(page.get_by_role("link", name="Maximilian")).to_be_visible()


def test_going_to_a_type_empties_the_filter(page: Page, data):
    page.goto("/")
    hydrated(page)
    expand_nav(page)
    box = page.get_by_label("Filter types")
    box.fill("person")
    box.press("Enter")
    page.wait_for_url("**/Person")
    # (the mouse is still over the bar, so it does not open by hovering: the shortcut opens it)
    page.keyboard.press("ControlOrMeta+k")
    expect(page.get_by_label("Filter types")).to_have_value("")


def describe_person(page: Page):
    """Holds Alt over Person in the navigation bar; the popup that appears"""
    hydrated(page)
    expand_nav(page)
    page.get_by_role("navigation", name="Main").get_by_role(
        "link", name="Person", exact=True
    ).hover()
    page.keyboard.down("Alt")
    return page.get_by_role("tooltip")


def test_alt_over_a_type_describes_it_and_letting_go_hides_it(page: Page, data):
    page.goto("/")
    popup = describe_person(page)
    expect(popup).to_contain_text("Person")
    # (the fields are for someone logged in)
    expect(popup).not_to_contain_text("has role", ignore_case=True)
    page.keyboard.up("Alt")
    expect(popup).to_have_count(0)


def test_alt_over_a_type_lists_its_fields_for_someone_logged_in(page: Page, data, logged_in):
    page.goto("/")
    popup = describe_person(page)
    expect(popup).to_contain_text("has role", ignore_case=True)
    expect(popup).to_contain_text("Role")
    page.keyboard.up("Alt")


def test_the_title_of_the_window_says_where_it_is(logged_in: Page, data):
    page = logged_in
    page.goto("/Person")
    expect(page).to_have_title("Persons | e2e project")
    page.goto("/Person/new")
    expect(page).to_have_title("New | Person | e2e project")
    page.goto(f"/Person/{data.charles}")
    expect(page).to_have_title("Charles the Bold | Person | e2e project")
    page.goto(f"/Person/{data.charles}/edit")
    expect(page).to_have_title("Edit | Charles the Bold | Person | e2e project")
    page.goto("/")
    expect(page).to_have_title("e2e project")
