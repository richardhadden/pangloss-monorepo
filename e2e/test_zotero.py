"""Zotero in the interface (the module of `pangloss_zotero`): a new Book based on an item of the library (*From Zotero*
on its form), the Book unlinked from the item again, and a Book made by hand linked to an item (the two nodes become
one). The items are written as the sync writes them, through Python: there is no Zotero here."""

import json
import re
import subprocess
import textwrap
from types import SimpleNamespace

import pytest
import neo4j
from conftest import (
    BIN,
    MEMGRAPH_AUTH,
    MEMGRAPH_URI,
    USERNAME,
    Stack,
    environment,
    forget,
)
from helpers import hydrated
from playwright.sync_api import Page, expect

# (written into the project and run there: the API will not let a person set the fields the sync owns)
SEED = textwrap.dedent(
    """
    import asyncio, json, sys

    from pangloss_cli.project import load_project
    from pangloss_models import initialise
    from pangloss_users import current_request_username
    from pydantic import AnyHttpUrl


    async def main():
        project = load_project()
        backend = project.require_database()
        project.import_models()
        initialise()
        from pangloss_zotero import ZoteroObject

        current_request_username.set(sys.argv[1])
        await backend.connect()
        made = {}
        try:
            for key in sys.argv[2:]:
                url = f"https://www.zotero.org/groups/1/items/{key}"
                await ZoteroObject.Create(
                    id=AnyHttpUrl(url),
                    create_new=True,
                    label=f"(Smith, {key})",
                    zotero_url=url,
                    zotero_library="groups/1",
                    zotero_key=key,
                    zotero_version=1,
                    zotero_synced_entity_version=1,
                    item_type="book",
                    title=f"The book {key}",
                    citation=f"(Smith, {key})",
                ).save()
                made[key] = str((await ZoteroObject.get(AnyHttpUrl(url))).id)
        finally:
            await backend.disconnect()
        print(json.dumps(made))


    asyncio.run(main())
    """
)


def seed(stack: Stack, *keys: str) -> dict[str, str]:
    script = stack.project / "seed_zotero.py"
    script.write_text(SEED)
    done = subprocess.run(
        [str(BIN / "python"), str(script), USERNAME, *keys],
        cwd=stack.project,
        env=environment(),
        capture_output=True,
        text=True,
        check=False,
        timeout=120,
    )
    assert done.returncode == 0, done.stderr
    return json.loads(done.stdout.strip().splitlines()[-1])


def forget_items() -> None:
    """The items of an earlier test, and their addresses (which a node that is gone would still hold)"""
    forget("Citation", "Book", "ZoteroObject")
    driver = neo4j.GraphDatabase.driver(MEMGRAPH_URI, auth=MEMGRAPH_AUTH)
    try:
        driver.execute_query(
            "MATCH (u:PGUrl) WHERE u.url STARTS WITH 'https://www.zotero.org/groups/1/' DETACH DELETE u",
            database_="memgraph",
        )
    finally:
        driver.close()


@pytest.fixture
def items(types: Stack) -> SimpleNamespace:
    forget_items()
    api = types.admin()
    keys = ["E2EONE", "E2ETWO"]
    made = seed(types, *keys)
    # (the first is cited: what refers to it stays when it becomes a Book)
    citation = api.ok(
        "POST",
        "/api/Citation",
        {
            "label": "Cites one",
            "source": {"type": "ZoteroObject", "id": made["E2EONE"]},
        },
    )["id"]
    return SimpleNamespace(api=api, ids=made, citation=citation, stack=types)


def pick(page: Page, label: str) -> None:
    """Find an item in the picker of the library, and choose it"""
    picker = page.get_by_test_id("zotero-picker")
    picker.get_by_role("combobox").fill(label)
    picker.get_by_role("option", name=re.compile(re.escape(label))).first.click()


def test_a_new_book_is_based_on_an_item_and_unlinked_again(logged_in: Page, items):
    page = logged_in
    page.goto("/Book/new")
    hydrated(page)
    page.get_by_role("button", name="From Zotero").click()
    pick(page, "Smith, E2EONE")
    based = page.get_by_test_id("zotero-based-on")
    expect(based).to_contain_text("Smith, E2EONE")
    expect(page.get_by_label("Label", exact=True)).to_have_value("(Smith, E2EONE)")
    page.get_by_role("spinbutton", name="Pages").fill("120")
    page.get_by_role("button", name="Save").click()

    # the item is the Book now: the same node, so its page is at the item's id
    page.wait_for_url(re.compile(rf"/Book/{items.ids['E2EONE']}$"))
    expect(page.locator("main")).to_contain_text("The book E2EONE")
    expect(page.locator("main")).to_contain_text("120")
    citation = items.api.ok("GET", f"/api/Citation/{items.citation}")
    assert citation["source"]["type"] == "Book"

    # unlinked, it keeps its own fields and what cites it; the item is an entry of its own again
    page.get_by_role("button", name="Unlink from Zotero").click()
    dialog = page.get_by_test_id("zotero-unlink-dialog")
    dialog.get_by_role("button", name="Unlink from Zotero").click()
    expect(
        page.get_by_text("Unlinked: the Zotero item is “(Smith, E2EONE)” again")
    ).to_be_visible()
    expect(page.get_by_role("button", name="Link to Zotero")).to_be_visible()
    book = items.api.ok("GET", f"/api/Book/{items.ids['E2EONE']}")
    assert book["zoteroUrl"] is None and book["pages"] == 120
    again = items.api.ok("GET", "/api/ZoteroObject", None)
    assert any(r["label"] == "(Smith, E2EONE)" for r in again["results"])


def test_a_book_made_by_hand_is_linked_to_an_item(logged_in: Page, items):
    page = logged_in
    book = items.api.ok("POST", "/api/Book", {"label": "My own book", "pages": 9})["id"]
    page.goto(f"/Book/{book}")
    hydrated(page)
    page.get_by_role("button", name="Link to Zotero").click()
    pick(page, "Smith, E2ETWO")
    expect(page.get_by_text("Linked to the Zotero item")).to_be_visible()
    # (nothing referred to the item: the Book made by hand is kept, with the item's fields)
    expect(page.locator("main")).to_contain_text("The book E2ETWO")
    expect(page.get_by_role("button", name="Unlink from Zotero")).to_be_visible()
    assert items.api.send("GET", f"/api/ZoteroObject/{items.ids['E2ETWO']}")[0] == 404


def test_from_zotero_is_only_on_the_classes_an_item_can_be_made_into(
    logged_in: Page, items
):
    page = logged_in
    page.goto("/Statement/new")
    hydrated(page)
    expect(page.get_by_label("Label", exact=True)).to_be_visible()
    expect(page.get_by_role("button", name="From Zotero")).to_have_count(0)
