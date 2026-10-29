"""The typology tree in a browser: what only a real browser shows (drag and drop, the built chunks, the API behind the proxy)"""

from playwright.sync_api import Page, expect


def row(page: Page, label: str):
    # (by its link: the select of every row has the names of the other types)
    return page.locator("[data-type-id]").filter(
        has=page.get_by_role("link", name=label, exact=True)
    )


def hydrated(page: Page) -> None:
    """Wait until the page is interactive (before that the server-rendered page has no handlers, and a drag does nothing)"""
    page.wait_for_function("window._$HY && window._$HY.done")


def drag(page: Page, label: str, onto: str):
    """Drag a row by its edge (not by the link in it) onto another, with the mouse as a person moves it (in steps: the
    browser starts a drag only when the mouse has moved)"""
    hydrated(page)
    source = row(page, label).bounding_box()
    page.mouse.move(source["x"] + 4, source["y"] + 4)
    page.mouse.down()
    page.mouse.move(source["x"] + 10, source["y"] + 10, steps=3)
    expect(page.get_by_text("Drop here for the top level")).to_be_visible()
    target = (
        row(page, onto).bounding_box()
    )  # (the rows did not move when the strip showed: that was a bug this test found)
    page.mouse.move(target["x"] + 4, target["y"] + 4, steps=10)
    page.mouse.up()


def test_the_tree_lists_the_types(page: Page, types):
    page.goto("/RoleType")
    for label in ("Clerk", "Secretary", "Advisor"):
        expect(row(page, label)).to_be_visible()


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


def test_a_type_cannot_be_dropped_below_its_own_subtype(logged_in: Page, types):
    page = logged_in
    page.goto("/RoleType")
    drag(page, "Clerk", "Secretary")
    # (the page does not even accept the drop, so nothing moves)
    assert [t["label"] for t in types.tree()] == ["Advisor", "Clerk"]
