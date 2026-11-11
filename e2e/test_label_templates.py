"""Labels worked out from what an item holds (implementation_docs/label-templates.md): locked while they are, worked
out as the form is filled in, nested documents first; the pencil to write one by hand, ↺ to have it worked out again;
the server keeps the same label"""

from helpers import hydrated
from playwright.sync_api import Page, expect


def test_a_label_is_worked_out_as_the_form_is_filled_in_and_can_be_written_by_hand(logged_in: Page, data):
    page = logged_in
    page.goto("/Will/new")
    hydrated(page)
    title = page.get_by_label("Label", exact=True).first
    expect(title).to_have_attribute("readonly", "")
    expect(title).to_have_attribute("placeholder", "Worked out from what is filled in")
    expect(page.get_by_role("button", name="Write the label by hand")).to_have_count(1)

    page.get_by_label("Find Person…").first.fill("Marie")
    page.get_by_role("option", name="Marie of Burgundy").click()
    expect(title).to_have_value("Will of Marie of Burgundy")

    page.get_by_role("button", name="Add Bequests").click()
    # (the cursor goes to the first field that can be typed in: not the label, which is worked out)
    expect(page.get_by_label("Item", exact=True)).to_be_focused()
    page.get_by_label("Item", exact=True).fill("a book of hours")
    nested = page.get_by_label("Label", exact=True).nth(1)
    expect(nested).to_have_value("")
    page.get_by_label("Find Person…").last.fill("Marie")
    page.get_by_role("option", name="Marie of Burgundy").click()
    expect(nested).to_have_value("a book of hours to Marie of Burgundy")
    expect(title).to_have_value("Will of Marie of Burgundy: a book of hours to Marie of Burgundy")

    # (the bequest's label by hand: it is kept, and the will's follows it)
    page.get_by_role("button", name="Write the label by hand").nth(1).click()
    expect(nested).not_to_have_attribute("readonly", "")
    nested.fill("The Hours, by hand")
    expect(title).to_have_value("Will of Marie of Burgundy: The Hours, by hand")
    page.get_by_label("Item", exact=True).fill("a psalter")
    expect(nested).to_have_value("The Hours, by hand")

    page.get_by_role("button", name="Save").click()
    expect(page.get_by_role("heading", name="Will of Marie of Burgundy: The Hours, by hand")).to_be_visible()
    will = page.url.rstrip("/").split("/")[-1]
    stored = data.api.ok("GET", f"/api/Will/{will}")
    assert (stored["label"], stored["labelAuto"]) == ("Will of Marie of Burgundy: The Hours, by hand", True)
    assert [(b["label"], b["labelAuto"]) for b in stored["bequests"]] == [("The Hours, by hand", False)]

    # (↺ has it worked out again)
    page.goto(f"/Will/{will}/edit")
    hydrated(page)
    nested = page.get_by_label("Label", exact=True).nth(1)
    expect(nested).to_have_value("The Hours, by hand")
    page.get_by_role("button", name="Work the label out from what is filled in").click()
    expect(nested).to_have_value("a psalter to Marie of Burgundy")
    expect(page.get_by_label("Label", exact=True).first).to_have_value("Will of Marie of Burgundy: a psalter to Marie of Burgundy")
