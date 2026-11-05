"""Leaving a form with changes in it, and stashing a new item to finish later (docs/unsaved-changes-and-stash.md)"""

import json
import re

from conftest import USERNAME
from helpers import hydrated
from playwright.sync_api import Page, expect


def test_a_new_item_left_with_changes_is_stashed_and_taken_up_again_from_its_list(logged_in: Page, data):
    page = logged_in
    page.goto("/Statement/new")
    hydrated(page)
    save = page.get_by_role("button", name="Save")
    # (nothing to save yet)
    expect(save).to_be_disabled()
    page.get_by_label("Text", exact=True).fill("Half done")
    expect(save).to_be_enabled()
    # (Cancel would leave the page: the form asks first)
    page.get_by_role("button", name="Cancel").click()
    dialog = page.get_by_role("dialog", name="Leave without saving?")
    expect(dialog).to_be_visible()
    stash = dialog.get_by_role("button", name="Stash and leave")
    # (it has no label yet: one is asked for)
    expect(stash).to_be_disabled()
    dialog.get_by_label("A label, to know it by").fill("Half a statement")
    stash.click()
    page.wait_for_url(re.compile(r"/Statement$"))
    expect(page.get_by_role("status", name="Notifications")).to_contain_text("Statement “Half a statement” stashed")
    stashed = page.get_by_role("region", name="Stashed")
    expect(stashed).to_contain_text("Half a statement")

    stashed.get_by_role("link", name="Go on with Half a statement").click()
    page.wait_for_url(re.compile(r"/Statement/new\?stash="))
    expect(page.get_by_label("Text", exact=True)).to_have_value("Half done")
    expect(page.get_by_label("Label", exact=True)).to_have_value("Half a statement")
    # (it can be saved at once, and nothing is asked if it is left as it was)
    expect(save).to_be_enabled()
    page.get_by_label("Find Person…").fill("Marie")
    page.get_by_role("option", name="Marie of Burgundy").click()
    save.click()
    expect(page.get_by_role("heading", name="Half a statement")).to_be_visible()
    # (saved, it is no longer stashed)
    page.goto("/Statement")
    hydrated(page)
    expect(page.get_by_role("link", name="Half a statement")).to_be_visible()
    expect(page.get_by_role("region", name="Stashed")).to_have_count(0)


def test_the_stash_button_stashes_a_labelled_item_and_goes_to_the_list(logged_in: Page, data):
    page = logged_in
    page.goto("/Statement/new")
    hydrated(page)
    page.get_by_label("Label", exact=True).fill("Stashed by the button")
    page.get_by_role("button", name="Stash this").click()
    page.wait_for_url(re.compile(r"/Statement$"))
    expect(page.get_by_role("region", name="Stashed")).to_contain_text("Stashed by the button")


def test_an_edit_left_with_changes_asks_and_can_be_left_without_saving(logged_in: Page, data):
    page = logged_in
    page.goto(f"/Statement/{data.statement}/edit")
    hydrated(page)
    expect(page.get_by_role("button", name="Save")).to_be_disabled()
    expect(page.get_by_role("button", name="Stash this")).to_have_count(0)
    page.get_by_label("Label", exact=True).fill("Court somewhere else")
    page.get_by_role("button", name="Cancel").click()
    dialog = page.get_by_role("dialog", name="Leave without saving?")
    expect(dialog).to_contain_text("they will be lost")
    expect(dialog.get_by_role("button", name="Stash and leave")).to_have_count(0)
    dialog.get_by_role("button", name="Stay").click()
    expect(page.get_by_label("Label", exact=True)).to_have_value("Court somewhere else")
    page.get_by_role("button", name="Cancel").click()
    page.get_by_role("dialog", name="Leave without saving?").get_by_role("button", name="Leave without saving").click()
    page.wait_for_url(f"**/Statement/{data.statement}")
    expect(page.get_by_role("heading", name="Court at Ghent")).to_be_visible()


def test_a_stashed_item_is_checked_against_the_database_when_it_is_taken_up(logged_in: Page, data):
    page = logged_in
    page.goto("/")
    hydrated(page)

    def entry(key: str, person: str, label: str) -> dict:
        return {
            "key": key,
            "type": "Statement",
            "label": f"About {label}",
            "value": {
                "type": "Statement",
                "label": f"About {label}",
                "text": "Kept a while",
                "about": {"type": "Person", "id": person, "label": label},
            },
            "when": "2026-11-05T10:00:00.000Z",
        }

    # (Charles is deleted while the item is stashed; Maximilian was stashed under the name he had then)
    stash = [entry("gone", data.charles, "Charles the Bold"), entry("renamed", data.maximilian, "Max")]
    page.evaluate(
        "([key, value]) => localStorage.setItem(key, value)",
        [f"pangloss.stash.{USERNAME}", json.dumps(stash)],
    )
    data.api.ok("DELETE", f"/api/Person/{data.charles}")

    page.goto("/Statement/new?stash=gone")
    hydrated(page)
    notice = page.get_by_role("alert").filter(has_text="no longer there")
    expect(notice).to_contain_text("Charles the Bold")
    expect(page.get_by_label("Text", exact=True)).to_have_value("Kept a while")
    expect(page.get_by_label("Find Person…")).to_be_visible()

    page.goto("/Statement/new?stash=renamed")
    hydrated(page)
    expect(page.locator("form").get_by_text("Maximilian", exact=True)).to_be_visible()
    expect(page.locator("form").get_by_text("Max", exact=True)).to_have_count(0)
