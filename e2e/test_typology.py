"""The typology tree in a browser: what only a real browser shows (drag and drop, the built chunks, the API behind the proxy)"""

from helpers import drag, drag_to_top, hydrated, row
from playwright.sync_api import Page, expect


def labels(nodes) -> list[str]:
    return [n["label"] for n in nodes]


def test_the_tree_lists_the_types_nested(page: Page, types):
    page.goto("/RoleType")
    for label in ("Clerk", "Secretary", "Advisor"):
        expect(row(page, label)).to_be_visible()
    # (the subtype is indented below its supertype)
    expect(row(page, "Secretary")).to_have_css("margin-left", "24px")
    expect(row(page, "Clerk")).to_have_css("margin-left", "0px")


def test_not_logged_in_a_type_cannot_be_moved(page: Page, types):
    page.goto("/RoleType")
    hydrated(page)
    expect(row(page, "Advisor")).to_have_attribute("draggable", "false")
    expect(page.get_by_role("combobox")).to_have_count(0)


def test_dragging_a_type_onto_another_moves_it(logged_in: Page, types):
    page = logged_in
    page.goto("/RoleType")
    drag(page, "Advisor", "Clerk")
    # (the API has it, and so does the page after it is read again)
    expect(row(page, "Advisor")).to_have_css("margin-left", "24px")
    clerk = next(t for t in types.tree() if t["label"] == "Clerk")
    assert {c["label"] for c in clerk["children"]} == {"Secretary", "Advisor"}
    page.reload()
    expect(row(page, "Advisor")).to_have_css("margin-left", "24px")


def test_the_rows_do_not_move_when_a_drag_starts(logged_in: Page, types):
    # (the strip for the top level was inserted at dragstart, and the rows jumped from under the pointer)
    page = logged_in
    page.goto("/RoleType")
    hydrated(page)
    before = row(page, "Clerk").bounding_box()
    source = row(page, "Advisor").bounding_box()
    page.mouse.move(source["x"] + 4, source["y"] + 4)
    page.mouse.down()
    page.mouse.move(source["x"] + 10, source["y"] + 10, steps=3)
    expect(page.get_by_text("Drop here for the top level")).to_be_visible()
    assert row(page, "Clerk").bounding_box() == before
    page.mouse.up()


def test_dragging_to_the_strip_makes_a_type_a_top_level_type(logged_in: Page, types):
    page = logged_in
    page.goto("/RoleType")
    drag_to_top(page, "Secretary")
    expect(row(page, "Secretary")).to_have_css("margin-left", "0px")
    assert labels(types.tree()) == ["Advisor", "Clerk", "Secretary"]


def test_a_type_cannot_be_dropped_below_its_own_subtype(logged_in: Page, types):
    page = logged_in
    page.goto("/RoleType")
    drag(page, "Clerk", "Secretary")
    # (the page does not even accept the drop, so nothing moves)
    assert labels(types.tree()) == ["Advisor", "Clerk"]
    expect(page.get_by_role("alert")).to_have_count(0)


def test_what_the_server_refuses_is_shown(logged_in: Page, types):
    page = logged_in
    page.goto("/RoleType")
    hydrated(page)
    # (someone else moved Advisor below Clerk after this page was read: it still thinks they are both at the top)
    types.admin().ok(
        "POST",
        f"/api/typology/RoleType/{types.type_id('Advisor')}/move",
        {"to": types.type_id("Clerk")},
    )
    drag(page, "Clerk", "Advisor")
    expect(page.get_by_role("alert")).to_contain_text("below")
    # (and the tree is as the server has it)
    assert labels(types.tree()) == ["Clerk"]


def test_the_select_moves_a_type_and_offers_only_places_that_are_allowed(
    logged_in: Page, types
):
    page = logged_in
    page.goto("/RoleType")
    hydrated(page)
    clerk_places = row(page, "Clerk").get_by_role("combobox")
    options = [o.strip("– ") for o in clerk_places.locator("option").all_inner_texts()]
    # (not itself, nor its own subtype; it is at the top already)
    assert options == ["Move to…", "Advisor"]
    row(page, "Advisor").get_by_role("combobox").select_option(label="Clerk")
    expect(row(page, "Advisor")).to_have_css("margin-left", "24px")
    assert labels(types.tree()) == ["Clerk"]
    # (and to the top again)
    row(page, "Advisor").get_by_role("combobox").select_option(label="(top level)")
    expect(row(page, "Advisor")).to_have_css("margin-left", "0px")
    assert labels(types.tree()) == ["Advisor", "Clerk"]


def test_a_type_can_be_collapsed_and_expanded(page: Page, types):
    page.goto("/RoleType")
    hydrated(page)
    clerk = row(page, "Clerk")
    clerk.get_by_role("button", name="Collapse").click()
    expect(row(page, "Secretary")).to_have_count(0)
    clerk.get_by_role("button", name="Expand").click()
    expect(row(page, "Secretary")).to_be_visible()
    # (a type with no subtypes has nothing to collapse)
    expect(row(page, "Advisor").get_by_role("button", name="Collapse")).to_be_disabled()


def test_a_type_links_to_its_page(page: Page, types):
    page.goto("/RoleType")
    row(page, "Secretary").get_by_role("link", name="Secretary").click()
    page.wait_for_url(f"**/RoleType/{types.type_id('Secretary')}")
    expect(page.get_by_role("navigation", name="Path")).to_contain_text("Secretary")
