"""What the tests share about the pages"""

from playwright.sync_api import Page, expect


def hydrated(page: Page) -> None:
    """Wait until the page is interactive (before that the server-rendered page has no handlers, and a drag does nothing)"""
    page.wait_for_function("window._$HY && window._$HY.done")


def box(locator) -> dict:
    """Where an element is on the page (`bounding_box()` is `None` for one that is not visible)"""
    found = locator.bounding_box()
    assert found is not None
    return found


def row(page: Page, label: str):
    """A row of the typology tree, by its link"""
    return page.locator("[data-type-id]").filter(
        has=page.get_by_role("link", name=label, exact=True)
    )


def drag(page: Page, label: str, onto: str, where: str = "middle") -> None:
    """Drag a row onto another with the mouse as a person moves it: in steps, because the browser starts a drag only
    when the mouse has moved. `where` on the other row: its `middle` (below that type), or its `top` or `bottom` edge
    (beside it)"""
    hydrated(page)
    source = row(page, label).bounding_box()
    page.mouse.move(source["x"] + 40, source["y"] + 4)
    page.mouse.down()
    page.mouse.move(source["x"] + 46, source["y"] + 10, steps=3)
    box = row(page, onto).bounding_box()
    y = {
        "middle": box["height"] / 2,
        "top": 2,
        "bottom": box["height"] - 2,
    }[where]
    page.mouse.move(box["x"] + 60, box["y"] + y, steps=10)
    page.mouse.up()


def expand_nav(page: Page) -> None:
    """Open the navigation bar by moving the mouse over it, as a person does (its login button, language and model links are
    there only when it is open). The bar opens when the mouse enters and closes when it leaves; its button toggles, so a click
    on it after the mouse came over it closes it again"""
    hydrated(page)
    page.locator("nav[aria-label='Main']").hover()
    expect(
        page.get_by_role("button", name="Pin the navigation bar open")
    ).to_be_visible()


def retract_nav(page: Page) -> None:
    """Close the bar by moving the mouse off it"""
    page.mouse.move(600, 400)
    expect(page.get_by_role("button", name="Expand the navigation bar")).to_be_visible()
