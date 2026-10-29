"""The page of one type: where it is, its labels, its switch, and what has it"""

from helpers import hydrated
from playwright.sync_api import Page, expect

PATH = "RoleType"


def open_type(page: Page, stack, label: str) -> None:
    page.goto(f"/{PATH}/{stack.type_id(label)}")
    hydrated(page)


def test_the_path_leads_up_the_hierarchy(page: Page, types):
    open_type(page, types, "Secretary")
    path = page.get_by_role("navigation", name="Path")
    expect(path).to_have_text("All›Clerk›Secretary")
    path.get_by_role("link", name="Clerk").click()
    page.wait_for_url(f"**/{PATH}/{types.type_id('Clerk')}")
    expect(page.get_by_role("navigation", name="Path")).to_have_text("All›Clerk")


def test_the_subtypes_are_listed_with_what_is_below_them(page: Page, data):
    open_type(page, data, "Clerk")
    subtypes = page.locator("section").filter(has_text="Subtypes").first
    expect(subtypes.get_by_role("listitem")).to_contain_text("0 subtypes · 1 entities")
    subtypes.get_by_role("link", name="Secretary", exact=True).click()
    page.wait_for_url(f"**/{PATH}/{data.type_id('Secretary')}")


def test_the_entities_of_a_type_include_those_of_its_subtypes(page: Page, data):
    open_type(page, data, "Clerk")
    expect(
        page.get_by_role("heading", name="Entities with this type (1)")
    ).to_be_visible()
    expect(page.get_by_role("link", name="Maximilian's secretary")).to_be_visible()
    page.get_by_label("including subtypes").uncheck()
    expect(
        page.get_by_role("heading", name="Entities with this type (0)")
    ).to_be_visible()
    expect(page.get_by_role("link", name="Maximilian's secretary")).to_have_count(0)
    page.get_by_label("including subtypes").check()
    expect(page.get_by_role("link", name="Maximilian's secretary")).to_be_visible()


def test_an_entity_links_to_its_page(page: Page, data):
    open_type(page, data, "Secretary")
    page.get_by_role("link", name="Maximilian's secretary").click()
    page.wait_for_url(f"**/Role/{data.secretary_role}")


def test_more_entities_are_shown_a_page_at_a_time(page: Page, data):
    advisor = data.type_id("Advisor")
    for n in range(52):
        data.api.ok(
            "POST",
            "/api/Role",
            {
                "label": f"Advisor {n:02}",
                "has_type": [{"type": "RoleType", "id": advisor}],
            },
        )
    open_type(page, data, "Advisor")
    expect(
        page.get_by_role("heading", name="Entities with this type (53)")
    ).to_be_visible()
    items = (
        page.locator("section")
        .filter(has_text="Entities with this type")
        .get_by_role("listitem")
    )
    expect(items).to_have_count(50)
    page.get_by_role("button", name="Show more").click()
    expect(items).to_have_count(53)
    expect(page.get_by_role("button", name="Show more")).to_have_count(0)


def test_not_logged_in_nothing_can_be_changed(page: Page, types):
    open_type(page, types, "Secretary")
    expect(page.get_by_role("button", name="Edit labels")).to_have_count(0)
    expect(
        page.get_by_role("checkbox", name="Also a concrete entity", exact=False)
    ).to_be_disabled()


def test_the_labels_are_edited_in_each_language(logged_in: Page, types):
    page = logged_in
    open_type(page, types, "Secretary")
    labels = page.locator("section").filter(has_text="Labels")
    expect(labels).to_contain_text("(not translated: the default is shown)")
    page.get_by_role("button", name="Edit labels").click()
    page.get_by_label("default").fill("Chief secretary")
    page.get_by_label("de", exact=True).fill("Sekretär")
    page.get_by_label("description").fill("Writes the letters")
    page.get_by_role("button", name="Save").click()
    expect(labels.get_by_text("Sekretär")).to_be_visible()
    expect(labels).to_contain_text("Chief secretary")
    expect(labels).to_contain_text("Writes the letters")
    # (the API has it: and the tree, which is by label, shows it)
    secretary = types.admin().ok(
        "GET", f"/api/typology/RoleType/{types.type_id('Chief secretary')}"
    )
    assert secretary["labels"] == {"de": "Sekretär"}
    expect(page.get_by_role("navigation", name="Path")).to_contain_text(
        "Chief secretary"
    )


def test_cancelling_an_edit_changes_nothing(logged_in: Page, types):
    page = logged_in
    open_type(page, types, "Secretary")
    page.get_by_role("button", name="Edit labels").click()
    page.get_by_label("default").fill("Something else")
    page.get_by_role("button", name="Cancel").click()
    expect(page.get_by_role("button", name="Edit labels")).to_be_visible()
    assert types.type_id("Secretary")


def test_switching_a_type_on_makes_it_usable_as_the_other_class(logged_in: Page, data):
    page = logged_in
    secretary = data.type_id("Secretary")
    maximilian = {"label": "Test", "has_role": [{"type": "Role", "id": secretary}]}
    status, _ = data.api.send("POST", "/api/Person", maximilian)
    assert status >= 400  # (not yet a Role)
    open_type(page, data, "Secretary")
    switch = page.get_by_role("checkbox", name="Also a concrete entity", exact=False)
    expect(switch).not_to_be_checked()
    switch.click()  # (the page sets it from what the server says, so a check does not stay at once)
    expect(switch).to_be_checked()
    status, _ = data.api.send("POST", "/api/Person", maximilian)
    assert status < 300
    # (as a Role it has a page of its own, which is its page as a type)
    page.goto(f"/Role/{secretary}")
    expect(page.get_by_role("navigation", name="Path")).to_have_text(
        "All›Clerk›Secretary"
    )


def test_a_type_that_is_used_as_the_other_class_cannot_be_switched_off(
    logged_in: Page, data
):
    page = logged_in
    secretary = data.type_id("Secretary")
    data.api.ok("PUT", f"/api/typology/RoleType/{secretary}/concrete", {"on": True})
    data.api.ok(
        "POST",
        "/api/Person",
        {"label": "Test", "has_role": [{"type": "Role", "id": secretary}]},
    )
    open_type(page, data, "Secretary")
    switch = page.get_by_role("checkbox", name="Also a concrete entity", exact=False)
    expect(switch).to_be_checked()
    switch.click()
    expect(page.get_by_role("alert")).to_contain_text("Test")
    expect(switch).to_be_checked()
