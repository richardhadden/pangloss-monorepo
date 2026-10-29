"""What the tests share about the pages"""

from playwright.sync_api import Page, expect


def hydrated(page: Page) -> None:
    """Wait until the page is interactive (before that the server-rendered page has no handlers, and a drag does nothing)"""
    page.wait_for_function("window._$HY && window._$HY.done")


def row(page: Page, label: str):
    """A row of the typology tree, by its link (the select of every row has the names of the other types)"""
    return page.locator("[data-type-id]").filter(
        has=page.get_by_role("link", name=label, exact=True)
    )


def drag_to_box(page: Page, label: str, target) -> None:
    """Drag a row by its edge (not by the link in it) with the mouse as a person moves it: in steps, because the browser
    starts a drag only when the mouse has moved. `target` is called when the drag has started, and gives the box to move to
    (the page may change when a drag starts)"""
    hydrated(page)
    source = row(page, label).bounding_box()
    page.mouse.move(source["x"] + 4, source["y"] + 4)
    page.mouse.down()
    page.mouse.move(source["x"] + 10, source["y"] + 10, steps=3)
    expect(page.get_by_text("Drop here for the top level")).to_be_visible()
    box = target()
    page.mouse.move(box["x"] + 4, box["y"] + 4, steps=10)
    page.mouse.up()


def drag(page: Page, label: str, onto: str) -> None:
    """Drag a row onto another"""
    drag_to_box(page, label, lambda: row(page, onto).bounding_box())


def drag_to_top(page: Page, label: str) -> None:
    """Drag a row onto the strip for the top level"""
    drag_to_box(
        page,
        label,
        lambda: page.get_by_text("Drop here for the top level").bounding_box(),
    )


def expand_nav(page: Page) -> None:
    """Open the navigation bar by moving the mouse over it, as a person does (its login button, language and model links are
    there only when it is open). The bar opens when the mouse enters and closes when it leaves; its button toggles, so a click
    on it after the mouse came over it closes it again"""
    hydrated(page)
    page.locator("nav[aria-label='Main']").hover()
    expect(
        page.get_by_role("button", name="Retract the navigation bar")
    ).to_be_visible()


def retract_nav(page: Page) -> None:
    """Close the bar by moving the mouse off it"""
    page.mouse.move(600, 400)
    expect(page.get_by_role("button", name="Expand the navigation bar")).to_be_visible()
