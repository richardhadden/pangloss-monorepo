"""The page /admin (`pangloss_admin`): who sees it, and a dump from the button to the download"""

import gzip
import re
import time
from uuid import uuid4

from conftest import OTHER_PASSWORD, OTHER_USERNAME, USERNAME
from helpers import hydrated
from playwright.sync_api import Page, expect


def test_nothing_links_to_the_admin_page(logged_in: Page, data):
    logged_in.goto("/")
    hydrated(logged_in)
    expect(logged_in.locator('a[href="/admin"]')).to_have_count(0)


def test_someone_not_logged_in_is_asked_to(page: Page, data):
    page.goto("/admin")
    hydrated(page)
    expect(page.get_by_role("dialog")).to_be_visible()
    expect(page.get_by_test_id("admin-page")).to_have_count(0)


def test_someone_who_is_not_an_admin_finds_nothing(page: Page, data, types):
    client = types.client(OTHER_USERNAME, OTHER_PASSWORD)
    assert client.send("GET", "/api/admin/jobs")[0] == 403
    page.goto("/")
    hydrated(page)
    response = page.request.post(
        "/api/users/session", form={"username": OTHER_USERNAME, "password": OTHER_PASSWORD}
    )
    assert response.ok
    page.goto("/admin")
    hydrated(page)
    expect(page.get_by_role("heading", level=1, name="Page not found")).to_be_visible()
    expect(page.get_by_test_id("admin-page")).to_have_count(0)


def test_a_dump_from_the_button_to_the_download(logged_in: Page, data, tmp_path):
    page = logged_in
    page.goto("/admin")
    hydrated(page)
    form = page.get_by_test_id("admin-job-form-rdf_dump")
    expect(form.get_by_label("Compress (gzip)")).to_be_checked()
    form.get_by_role("button", name="Start").click()

    # (the page is not reloaded: what follows comes from the live feed)
    row = page.get_by_test_id("admin-job-row").first
    expect(row).to_have_attribute("data-state", "finished", timeout=120_000)
    expect(row.get_by_test_id("admin-job-counts")).to_contain_text(re.compile(r"\d+ items"))
    expect(form.get_by_role("button", name="Start")).to_be_enabled()

    with page.expect_download() as download:
        row.get_by_role("link", name=re.compile(r"\.nq\.gz")).click()
    saved = tmp_path / "dump.nq.gz"
    download.value.save_as(saved)
    with gzip.open(saved, "rt") as text:
        assert "<" in text.readline()

    row.get_by_role("button", name="Delete").click()
    expect(page.get_by_text("No jobs yet")).to_be_visible()


def no_jobs(api) -> None:
    """No job running and none listed, whatever a test before left (one that failed part way)"""
    deadline = time.monotonic() + 30
    while jobs := api.ok("GET", "/api/admin/jobs")["jobs"]:
        assert time.monotonic() < deadline, jobs
        for job in jobs:
            if job["state"] in ("queued", "running"):
                api.send("POST", f"/api/admin/jobs/{job['id']}/cancel")
            else:
                api.send("DELETE", f"/api/admin/jobs/{job['id']}")
        time.sleep(0.3)


def test_the_options_chosen_in_the_form_are_those_of_the_job(logged_in: Page, data, tmp_path):
    no_jobs(data.api)
    page = logged_in
    page.goto("/admin")
    hydrated(page)
    form = page.get_by_test_id("admin-job-form-rdf_dump")
    form.get_by_label("Format").select_option(label="Turtle")
    form.get_by_label("Compress (gzip)").uncheck()
    form.get_by_role("button", name="Start").click()
    row = page.get_by_test_id("admin-job-row").first
    expect(row).to_have_attribute("data-state", "finished", timeout=120_000)
    # (who started it, and the file as asked for: Turtle, not compressed)
    expect(row).to_contain_text(USERNAME)
    link = row.get_by_role("link", name=re.compile(r"\.ttl \("))
    with page.expect_download() as download:
        link.click()
    saved = tmp_path / "dump.ttl"
    download.value.save_as(saved)
    assert "@prefix" in saved.read_text()
    row.get_by_role("button", name="Delete").click()
    expect(page.get_by_text("No jobs yet")).to_be_visible()


def test_a_running_job_shows_how_far_it_is_and_is_cancelled(logged_in: Page, data):
    """(`slow` is a job of the e2e project's own, `roles/admin.py` in conftest.py: a step a second)"""
    no_jobs(data.api)
    page = logged_in
    page.goto("/admin")
    hydrated(page)
    form = page.get_by_test_id("admin-job-form-slow")
    form.get_by_role("button", name="Start").click()
    row = page.get_by_test_id("admin-job-row").first
    expect(row).to_have_attribute("data-state", "running", timeout=30_000)
    # (how far it is, from the live feed, moving on without a reload)
    expect(row).to_contain_text(re.compile(r"\d+ of 120\s+part \d+"))
    expect(row.get_by_test_id("admin-job-counts")).to_contain_text(re.compile(r"\d+ parts"))
    expect(row).to_contain_text(re.compile(r"[3-9] of 120"), timeout=20_000)
    # (one job of a kind at a time: another of it cannot be started, here or by the API; a job of another kind can;
    # and a running job is not deleted)
    expect(form.get_by_role("button", name="Start")).to_be_disabled()
    assert data.api.send("POST", "/api/admin/jobs", {"kind": "slow", "options": {}})[0] == 409
    expect(page.get_by_test_id("admin-job-form-rdf_dump").get_by_role("button", name="Start")).to_be_enabled()
    expect(row.get_by_role("button", name="Delete")).to_have_count(0)

    row.get_by_role("button", name="Cancel").click()
    expect(row).to_have_attribute("data-state", "cancelled", timeout=30_000)
    expect(row).to_contain_text("Cancelled")
    expect(row.get_by_role("button", name="Cancel")).to_have_count(0)
    expect(form.get_by_role("button", name="Start")).to_be_enabled()
    row.get_by_role("button", name="Delete").click()
    expect(page.get_by_text("No jobs yet")).to_be_visible()


def test_a_job_that_fails_says_why(logged_in: Page, data):
    no_jobs(data.api)
    page = logged_in
    page.goto("/admin")
    hydrated(page)
    form = page.get_by_test_id("admin-job-form-slow")
    form.get_by_label("steps").select_option("2")
    form.get_by_label("fail").check()
    form.get_by_role("button", name="Start").click()
    row = page.get_by_test_id("admin-job-row").first
    expect(row).to_have_attribute("data-state", "failed", timeout=30_000)
    expect(row).to_contain_text("Failed")
    expect(row).to_contain_text("The slow job was told to fail")
    # (it made no file, and another can be started)
    expect(row.get_by_role("link")).to_have_count(0)
    expect(form.get_by_role("button", name="Start")).to_be_enabled()
    row.get_by_role("button", name="Delete").click()
    expect(page.get_by_text("No jobs yet")).to_be_visible()


def test_managing_users_is_kept_up_to_date_without_reloading(logged_in: Page, data, types):
    page = logged_in
    page.goto("/admin")
    hydrated(page)
    section = page.get_by_test_id("admin-users")
    own = section.locator(f'[data-username="{USERNAME}"]')
    expect(own.get_by_role("button", name="Disable")).to_be_disabled()

    name = f"made-{uuid4().hex[:8]}"
    section.get_by_role("button", name="New user").click()
    dialog = page.get_by_role("dialog")
    dialog.get_by_label("Username").fill(name)
    dialog.get_by_label("Email").fill(f"{name}@example.com")
    dialog.get_by_label("Password", exact=True).fill("first-password")
    dialog.get_by_label("Password again").fill("first-password")
    dialog.get_by_role("button", name="Create").click()
    row = section.locator(f'[data-username="{name}"]')
    expect(row).to_be_visible()

    # (the buttons take effect at once)
    row.get_by_role("button", name="Make admin").click()
    expect(row).to_have_attribute("data-admin", "true")

    # (a change made elsewhere reaches the open page)
    types.admin().ok("PUT", f"/api/users/{name}/disabled", {"disabled": True})
    expect(row).to_have_attribute("data-disabled", "true")
    row.get_by_role("button", name="Enable").click()
    expect(row).to_have_attribute("data-disabled", "false")

    # (a field is sent when it is left: there is nothing to save)
    row.get_by_label("Full name").fill("Made Up")
    row.get_by_label("Full name").press("Tab")
    for _ in range(50):
        if types.admin().ok("GET", f"/api/users/{name}")["fullName"] == "Made Up":
            break
        page.wait_for_timeout(100)
    assert types.admin().ok("GET", f"/api/users/{name}")["fullName"] == "Made Up"

    row.get_by_role("button", name="Tokens").click()
    dialog = page.get_by_role("dialog")
    dialog.get_by_label("What is it for?").fill("script")
    dialog.get_by_role("button", name="Create").click()
    expect(dialog.get_by_test_id("users-admin-new-token")).to_contain_text("pgl_")
    expect(dialog.get_by_test_id("users-admin-token")).to_contain_text("script")
    dialog.get_by_role("button", name="Revoke").click()
    expect(dialog.get_by_test_id("users-admin-token")).to_have_count(0)
    dialog.get_by_role("button", name="Close").click()

    row.get_by_role("button", name="Password").click()
    dialog = page.get_by_role("dialog")
    dialog.get_by_label("Password", exact=True).fill("second-password")
    dialog.get_by_label("Password again").fill("second-password")
    dialog.get_by_role("button", name="Set password").click()
    expect(dialog).to_have_count(0)
    assert types.client(name, "second-password").send("GET", "/api/users/me")[0] == 200


def test_tabs_in_the_background_leave_connections_for_a_new_page(logged_in: Page, data):
    """Each open feed holds one of the browser's six connections to the host: with these tabs still connected, the
    last page would wait for one of them to close"""
    context = logged_in.context
    tabs = []
    for _ in range(4):
        tab = context.new_page()
        tab.goto("/admin")
        hydrated(tab)
        expect(tab.get_by_test_id("users-admin-row").first).to_be_visible()
        tab.evaluate(
            """() => {
                Object.defineProperty(document, "hidden", { configurable: true, get: () => true });
                document.dispatchEvent(new Event("visibilitychange"));
            }"""
        )
        tabs.append(tab)

    last = context.new_page()
    last.goto("/admin")
    expect(last.get_by_test_id("admin-job-form-rdf_dump")).to_be_visible(timeout=5_000)
    last.close()

    # (and a tab that comes back is connected again)
    tab = tabs[0]
    name = f"seen-{uuid4().hex[:8]}"
    made = context.request.post(
        "/api/users",
        data={"username": name, "email": f"{name}@example.com", "password": "a-password"},
    )
    assert made.ok, made.text()
    expect(tab.locator(f'[data-username="{name}"]')).to_have_count(0)
    tab.evaluate(
        """() => {
            Object.defineProperty(document, "hidden", { configurable: true, get: () => false });
            document.dispatchEvent(new Event("visibilitychange"));
        }"""
    )
    expect(tab.locator(f'[data-username="{name}"]')).to_be_visible()
    for open_tab in tabs:
        open_tab.close()
