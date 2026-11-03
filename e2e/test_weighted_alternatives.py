"""Alternatives weighted by how likely each is (`pangloss_library`'s `WeightedAlternative`): sliders that give way to
each other, so the percentages add up to 100"""

from helpers import hydrated
from playwright.sync_api import Page, expect


def test_the_shares_of_alternatives_give_way_to_each_other(logged_in: Page, data):
    page = logged_in
    page.goto("/Suspicion/new")
    hydrated(page)
    page.get_by_label("Label", exact=True).fill("Who was it")
    sliders = page.locator('input[type="range"]')

    def shares() -> list[str]:
        return [sliders.nth(i).input_value() for i in range(sliders.count())]

    def choose(search: str, name: str, count: int) -> None:
        box = page.get_by_label("Find Person…").last
        box.click()
        box.press_sequentially(search)
        page.get_by_role("option", name=name).click()
        expect(sliders).to_have_count(count)
        # (the cursor goes to the share of the one chosen)
        expect(sliders.last).to_be_focused()

    # (the first is the whole; a second is given an even share)
    choose("Marie", "Marie of Burgundy", 1)
    expect(sliders.first).to_have_value("100")
    choose("Charles", "Charles the Bold", 2)
    assert shares() == ["50", "50"]

    # (dragged, here by the keys: the other gives way)
    sliders.first.focus()
    for _ in range(20):
        page.keyboard.press("ArrowRight")
    expect(sliders.first).to_have_value("70")
    assert shares() == ["70", "30"]

    # (a third is given an even share, and the others give way in proportion)
    choose("Max", "Maximilian", 3)
    assert shares() == ["47", "20", "33"]

    # (one taken away: the others share the whole)
    page.get_by_role("button", name="Remove Charles the Bold").click()
    expect(sliders).to_have_count(2)
    assert shares() == ["59", "41"]

    with page.expect_response(
        lambda response: response.request.method == "POST"
        and response.url.endswith("/api/Suspicion")
    ) as answer:
        page.get_by_role("button", name="Save").click()
    made = answer.value.json()
    saved = data.api.ok("GET", f"/api/Suspicion/{made['id']}")
    assert [
        (alternative["label"], alternative["edgeProperties"]["percent"])
        for alternative in saved["suspects"]["alternatives"]
    ] == [("Marie of Burgundy", 59), ("Maximilian", 41)]
