"""The typology tree in a browser: what only a real browser shows (drag and drop, the built chunks, the live feed from
the interface's server, the API behind the proxy)"""

import subprocess
import time

from conftest import environment
from helpers import drag, hydrated, row
from playwright.sync_api import Page, expect


def labels(nodes) -> list[str]:
    return [n["label"] for n in nodes]


def children(nodes, label: str) -> list[str]:
    return labels(next(t for t in nodes if t["label"] == label)["children"])


def server_has(types, check) -> None:
    """Wait until the API's tree passes `check`: the page shows a change before the API has made it"""
    deadline = time.monotonic() + 5
    while True:
        nodes = types.tree()
        if check(nodes):
            return
        assert time.monotonic() < deadline, nodes
        time.sleep(0.1)


def test_the_tree_lists_the_types_nested(page: Page, types):
    page.goto("/RoleType")
    for label in ("Clerk", "Secretary", "Advisor"):
        expect(row(page, label)).to_be_visible()
    # (the subtype is below its supertype, further in)
    expect(row(page, "Secretary")).to_have_attribute("data-depth", "1")
    expect(row(page, "Clerk")).to_have_attribute("data-depth", "0")
    assert (
        row(page, "Secretary").bounding_box()["x"]
        > row(page, "Clerk").bounding_box()["x"]
    )


def test_not_logged_in_a_type_can_be_neither_moved_nor_renamed(page: Page, types):
    page.goto("/RoleType")
    hydrated(page)
    expect(row(page, "Advisor")).to_have_attribute("draggable", "false")
    expect(page.get_by_role("combobox")).to_have_count(0)
    expect(page.get_by_role("button", name="Edit the label of Advisor")).to_have_count(
        0
    )


def test_dragging_a_type_onto_another_moves_it_below_that_one(logged_in: Page, types):
    page = logged_in
    page.goto("/RoleType")
    drag(page, "Advisor", "Clerk")
    # (the API has it, and so does the page after it is read again)
    expect(row(page, "Advisor")).to_have_attribute("data-depth", "1")
    server_has(
        types, lambda nodes: children(nodes, "Clerk") == ["Advisor", "Secretary"]
    )
    page.reload()
    expect(row(page, "Advisor")).to_have_attribute("data-depth", "1")


def test_dragging_a_type_to_the_edge_of_another_puts_it_beside_that_one(
    logged_in: Page, types
):
    page = logged_in
    page.goto("/RoleType")
    # (beside a top-level type is the top level)
    drag(page, "Secretary", "Advisor", "top")
    expect(row(page, "Secretary")).to_have_attribute("data-depth", "0")
    server_has(types, lambda nodes: labels(nodes) == ["Advisor", "Clerk", "Secretary"])
    # (and beside a subtype is below its supertype)
    drag(page, "Advisor", "Clerk", "middle")
    expect(row(page, "Advisor")).to_have_attribute("data-depth", "1")
    drag(page, "Secretary", "Advisor", "bottom")
    expect(row(page, "Secretary")).to_have_attribute("data-depth", "1")
    server_has(
        types, lambda nodes: children(nodes, "Clerk") == ["Advisor", "Secretary"]
    )


def test_where_a_drop_would_put_a_type_is_marked_and_the_rows_stay_still(
    logged_in: Page, types
):
    page = logged_in
    page.goto("/RoleType")
    hydrated(page)
    before = row(page, "Clerk").bounding_box()
    source = row(page, "Advisor").bounding_box()
    page.mouse.move(source["x"] + 40, source["y"] + 4)
    page.mouse.down()
    page.mouse.move(source["x"] + 46, source["y"] + 10, steps=3)
    assert row(page, "Clerk").bounding_box() == before
    target = row(page, "Secretary").bounding_box()
    page.mouse.move(target["x"] + 60, target["y"] + target["height"] / 2, steps=5)
    expect(row(page, "Secretary")).to_have_attribute("data-drop", "into")
    page.mouse.move(target["x"] + 60, target["y"] + 2, steps=3)
    expect(row(page, "Secretary")).to_have_attribute("data-drop", "above")
    # (beside Clerk is the top level, where Advisor is: nothing is marked)
    page.mouse.move(before["x"] + 60, before["y"] + 2, steps=3)
    expect(page.locator("[data-drop]")).to_have_count(0)
    page.mouse.up()
    expect(page.locator("[data-drop]")).to_have_count(0)


def test_a_type_cannot_be_dropped_below_its_own_subtype(logged_in: Page, types):
    page = logged_in
    page.goto("/RoleType")
    drag(page, "Clerk", "Secretary")
    # (the page does not even accept the drop, so nothing moves)
    assert labels(types.tree()) == ["Advisor", "Clerk"]
    expect(page.get_by_role("alert")).to_have_count(0)


def test_a_move_by_someone_else_is_shown_without_reading_the_page_again(
    page: Page, types
):
    page.goto("/RoleType")
    hydrated(page)
    expect(row(page, "Advisor")).to_have_attribute("data-depth", "0")
    types.admin().ok(
        "POST",
        f"/api/typology/RoleType/{types.type_id('Advisor')}/move",
        {"to": types.type_id("Clerk")},
    )
    expect(row(page, "Advisor")).to_have_attribute("data-depth", "1")


def test_what_the_server_refuses_is_shown_and_undone(logged_in: Page, types):
    page = logged_in
    page.route(
        "**/api/typology/RoleType/*/move",
        lambda route: route.fulfill(
            status=409, json={"detail": "Refused by the server"}
        ),
    )
    page.goto("/RoleType")
    drag(page, "Advisor", "Clerk")
    expect(page.get_by_role("alert")).to_contain_text("Refused by the server")
    expect(row(page, "Advisor")).to_have_attribute("data-depth", "0")
    assert labels(types.tree()) == ["Advisor", "Clerk"]


def test_the_pencil_renames_a_type_in_place(logged_in: Page, types):
    page = logged_in
    page.goto("/RoleType")
    hydrated(page)
    row(page, "Advisor").hover()
    page.get_by_role("button", name="Edit the label of Advisor").click()
    field = page.get_by_role("textbox", name="Label of Advisor")
    expect(field).to_be_focused()
    field.fill("Counsellor")
    field.press("Enter")
    expect(row(page, "Counsellor")).to_be_visible()
    expect(page.get_by_role("textbox")).to_have_count(0)
    server_has(types, lambda nodes: labels(nodes) == ["Clerk", "Counsellor"])
    page.reload()
    expect(row(page, "Counsellor")).to_be_visible()


def test_escape_leaves_the_label_as_it_was(logged_in: Page, types):
    page = logged_in
    page.goto("/RoleType")
    hydrated(page)
    row(page, "Secretary").hover()
    page.get_by_role("button", name="Edit the label of Secretary").click()
    field = page.get_by_role("textbox", name="Label of Secretary")
    field.fill("Scribe")
    field.press("Escape")
    expect(row(page, "Secretary")).to_be_visible()
    assert children(types.tree(), "Clerk") == ["Secretary"]


def test_a_subtype_is_added_in_a_dialog(logged_in: Page, types):
    page = logged_in
    page.goto("/RoleType")
    hydrated(page)
    row(page, "Advisor").get_by_role("button", name="Add a subtype of Advisor").click()
    dialog = page.get_by_role("dialog", name="New subtype of Advisor")
    expect(dialog.get_by_label("default")).to_be_focused()
    dialog.get_by_label("default").fill("Privy councillor")
    dialog.get_by_label("de", exact=True).fill("Geheimrat")
    dialog.get_by_role("button", name="Add").click()
    expect(dialog).to_have_count(0)
    expect(row(page, "Privy councillor")).to_have_attribute("data-depth", "1")
    server_has(types, lambda nodes: children(nodes, "Advisor") == ["Privy councillor"])
    # (still the page it was: no new page was opened)
    assert page.url.endswith("/RoleType")


def test_a_top_level_type_is_added_from_the_console_and_from_the_tree(
    logged_in: Page, types
):
    page = logged_in
    page.goto("/RoleType")
    hydrated(page)
    expect(page.get_by_role("button", name="Add a top-level type")).to_have_count(2)
    page.get_by_role("banner", name="Console").get_by_role(
        "button", name="New Role type"
    ).click()
    dialog = page.get_by_role("dialog")
    expect(dialog).to_contain_text("New top-level")
    dialog.get_by_label("default").fill("Herald")
    dialog.get_by_label("default").press("Enter")
    expect(row(page, "Herald")).to_have_attribute("data-depth", "0")
    page.get_by_role("button", name="Add a top-level type").last.click()
    page.get_by_role("dialog").get_by_label("default").fill("Almoner")
    page.get_by_role("dialog").get_by_role("button", name="Add").click()
    expect(row(page, "Almoner")).to_have_attribute("data-depth", "0")
    server_has(
        types,
        lambda nodes: labels(nodes) == ["Advisor", "Almoner", "Clerk", "Herald"],
    )


def test_a_type_can_be_collapsed_and_expanded(page: Page, types):
    page.goto("/RoleType")
    hydrated(page)
    clerk = row(page, "Clerk")
    clerk.get_by_role("button", name="Collapse").click()
    expect(row(page, "Secretary")).to_have_count(0)
    clerk.get_by_role("button", name="Expand").click()
    expect(row(page, "Secretary")).to_be_visible()
    # (a type with no subtypes has nothing to collapse)
    expect(row(page, "Advisor").get_by_role("button", name="Collapse")).to_have_count(0)


def test_a_type_links_to_its_page(page: Page, types):
    page.goto("/RoleType")
    row(page, "Secretary").get_by_role("link", name="Secretary").click()
    page.wait_for_url(f"**/RoleType/{types.type_id('Secretary')}")
    expect(page.get_by_role("navigation", name="Path")).to_contain_text("Secretary")


def test_the_module_tests_pass_in_the_built_project(stack):
    """The typology module's own vitest tests and type-check, run where a project builds it (a module has no
    node_modules of its own)"""
    interface = stack.project / ".pangloss" / "interface"
    for command in (
        ["npx", "vitest", "run", "--root", "modules/pangloss_typology"],
        ["npx", "tsc", "--noEmit", "-p", "modules/pangloss_typology/tsconfig.json"],
    ):
        done = subprocess.run(
            command,
            cwd=interface,
            env=environment(),
            capture_output=True,
            text=True,
            timeout=300,
            check=False,
        )
        assert done.returncode == 0, (done.stdout + done.stderr)[-3000:]
