"""Alternatives weighted by how likely each is (`pangloss_library`'s `WeightedAlternative`): sliders that give way to
each other, so the percentages add up to 100"""

import re

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


def suspicion(data, *suspects: tuple[str, int]) -> str:
    return data.api.ok(
        "POST",
        "/api/Suspicion",
        {
            "label": "Who was it",
            "suspects": {
                "type": "WeightedAlternative",
                "alternatives": [
                    {"type": "Person", "id": person, "edge_properties": {"percent": percent}}
                    for person, percent in suspects
                ],
            },
        },
    )["id"]


def test_on_its_page_each_alternative_has_its_share_at_the_end_of_its_chip(page: Page, data):
    """`pangloss_library:WeightedAlternativeCard`: no head for the conjunction, the alternatives under their name"""
    made = suspicion(data, (data.marie, 60), (data.charles, 40))
    page.goto(f"/Suspicion/{made}")
    hydrated(page)
    main = page.locator("main")
    expect(main.locator("dt")).to_have_text(["Suspects", "Alternatives"])
    # (the conjunction itself is not named: no "Weighted alternative" head)
    expect(main).not_to_contain_text("Weighted alternative")
    for name, id, share in (("Marie of Burgundy", data.marie, "60%"), ("Charles the Bold", data.charles, "40%")):
        link = main.get_by_role("link", name=f"Person {name}")
        expect(link).to_have_attribute("href", f"/Person/{id}")
        # (the share is the end of the chip: in its frame, straight after the link)
        chip = link.locator("xpath=..")
        expect(chip).to_have_text(re.compile(rf"{name}\s*{share}$"))
    # (and from the person, the suspicion refers to them)
    page.goto(f"/Person/{data.marie}")
    hydrated(page)
    expect(page.get_by_test_id("incoming-by-field").get_by_role("link", name=re.compile("Who was it"))).to_be_visible()


def test_one_alternative_alone_is_only_itself(page: Page, data):
    made = suspicion(data, (data.marie, 100))
    page.goto(f"/Suspicion/{made}")
    hydrated(page)
    main = page.locator("main")
    expect(main.locator("dt")).to_have_text(["Suspects"])
    expect(main.get_by_role("link", name="Person Marie of Burgundy")).to_be_visible()
    expect(main).to_contain_text("100%")


def test_shares_that_do_not_add_up_are_refused_at_the_field(logged_in: Page, data):
    """The server refuses what does not add up to 100 (`SumsTo`); so does the form, for an item made elsewhere"""
    status, result = data.api.send(
        "POST",
        "/api/Suspicion",
        {
            "label": "Badly weighed",
            "suspects": {
                "type": "WeightedAlternative",
                "alternatives": [
                    {"type": "Person", "id": data.marie, "edge_properties": {"percent": 60}},
                    {"type": "Person", "id": data.charles, "edge_properties": {"percent": 60}},
                ],
            },
        },
    )
    assert status == 422, result
