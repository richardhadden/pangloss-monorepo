"""The page /admin (`pangloss_admin`): who sees it, and a dump from the button to the download"""

import gzip
import re
import time
from uuid import uuid4

from conftest import OTHER_PASSWORD, OTHER_USERNAME, USERNAME, Client
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


def new_user(page: Page, name: str, password: str = "a-password", again: str | None = None):
    """The New user dialog, filled in and sent; the dialog"""
    page.get_by_test_id("admin-users").get_by_role("button", name="New user").click()
    dialog = page.get_by_role("dialog")
    dialog.get_by_label("Username").fill(name)
    dialog.get_by_label("Email").fill(f"{name}@example.com")
    dialog.get_by_label("Password", exact=True).fill(password)
    dialog.get_by_label("Password again").fill(again if again is not None else password)
    dialog.get_by_role("button", name="Create").click()
    return dialog


def test_a_toolchain_made_on_the_admin_page_has_nothing_to_log_in_with(logged_in: Page, data, types):
    page = logged_in
    page.goto("/admin")
    hydrated(page)
    section = page.get_by_test_id("admin-users")
    name = f"tool-{uuid4().hex[:8]}"
    section.get_by_test_id("users-admin-new-toolchain").click()
    dialog = page.get_by_role("dialog")
    expect(dialog).to_contain_text("It cannot log in.")
    dialog.get_by_label("Name", exact=True).fill(name)
    dialog.get_by_label("Full name").fill("The OCR")
    dialog.get_by_role("button", name="Create").click()
    expect(dialog).to_have_count(0)

    row = section.locator(f'[data-username="{name}"]')
    expect(row).to_have_attribute("data-kind", "toolchain")
    expect(row.get_by_text("Toolchain", exact=True)).to_be_visible()
    expect(row.get_by_label("Full name")).to_have_value("The OCR")
    # (no password, sessions, tokens or admin: it may only be disabled)
    for absent in ("Make admin", "Password", "End sessions", "Tokens"):
        expect(row.get_by_role("button", name=absent)).to_have_count(0)
    row.get_by_role("button", name="Disable").click()
    expect(row).to_have_attribute("data-disabled", "true")
    made = types.admin().ok("GET", f"/api/users/{name}")
    assert (made["kind"], made["fullName"], made["disabled"]) == ("toolchain", "The OCR", True)


def test_what_the_admin_page_refuses_it_says_and_puts_back(logged_in: Page, data, types):
    page = logged_in
    page.goto("/admin")
    hydrated(page)
    section = page.get_by_test_id("admin-users")
    name = f"refused-{uuid4().hex[:8]}"

    # (two passwords that differ are not sent)
    dialog = new_user(page, name, "first-password", "other-password")
    expect(dialog.get_by_role("alert")).to_have_text("The two passwords are not the same")
    expect(section.locator(f'[data-username="{name}"]')).to_have_count(0)
    assert types.admin().send("GET", f"/api/users/{name}")[0] == 404
    dialog.get_by_role("button", name="Cancel").click()

    # (a username that is taken is the API's to refuse: the dialog stays, saying why, and the row shown at once goes)
    dialog = new_user(page, USERNAME)
    expect(dialog.get_by_role("alert")).to_contain_text("already in use")
    expect(section.locator(f'[data-username="{USERNAME}"]')).to_have_count(1)
    dialog.get_by_role("button", name="Cancel").click()

    # (an email the API will not take is put back as it was)
    expect(new_user(page, name)).to_have_count(0)
    row = section.locator(f'[data-username="{name}"]')
    email = row.get_by_label("Email")
    expect(email).to_have_value(f"{name}@example.com")
    email.fill("not an address")
    email.press("Enter")
    expect(section.get_by_role("alert")).to_be_visible()
    expect(email).to_have_value(f"{name}@example.com")
    assert types.admin().ok("GET", f"/api/users/{name}")["email"] == f"{name}@example.com"

    # (and an admin can be made one and not again)
    row.get_by_role("button", name="Make admin").click()
    expect(row).to_have_attribute("data-admin", "true")
    row.get_by_role("button", name="Remove admin").click()
    expect(row).to_have_attribute("data-admin", "false")
    assert types.admin().ok("GET", f"/api/users/{name}")["admin"] is False


def test_a_token_that_only_reads_and_ending_a_users_sessions(logged_in: Page, data, types):
    page = logged_in
    page.goto("/admin")
    hydrated(page)
    section = page.get_by_test_id("admin-users")
    name = f"reader-{uuid4().hex[:8]}"
    expect(new_user(page, name)).to_have_count(0)
    row = section.locator(f'[data-username="{name}"]')

    row.get_by_role("button", name="Tokens").click()
    dialog = page.get_by_role("dialog")
    expect(dialog).to_contain_text("No tokens")
    dialog.get_by_label("What is it for?").fill("a report")
    dialog.get_by_label("Scope").select_option("read")
    dialog.get_by_label("Days").fill("30")
    dialog.get_by_role("button", name="Create").click()
    token = dialog.get_by_test_id("users-admin-new-token")
    expect(token).to_contain_text("pgl_")
    listed = dialog.get_by_test_id("users-admin-token")
    expect(listed).to_contain_text("a report")
    expect(listed).to_contain_text("Read")
    expect(listed).to_contain_text("Expires")
    expect(listed).to_contain_text("Never used")

    # (the token reads, and is refused a write)
    bearer = {"Authorization": f"Bearer {token.inner_text().strip()}"}
    reader = Client(types.api)
    status, me = reader.send("GET", "/api/users/me", headers=bearer)
    assert status == 200 and isinstance(me, dict) and me["username"] == name
    status, _ = reader.send("POST", "/api/Person", {"label": "Not made", "hasRole": []}, headers=bearer)
    assert status == 403
    dialog.get_by_role("button", name="Close").click()

    # (End sessions: a session the user had elsewhere no longer works)
    elsewhere = types.client(name, "a-password")
    assert elsewhere.send("GET", "/api/users/me")[0] == 200
    row.get_by_role("button", name="End sessions").click()
    for _ in range(50):
        if elsewhere.send("GET", "/api/users/me")[0] == 401:
            break
        page.wait_for_timeout(100)
    assert elsewhere.send("GET", "/api/users/me")[0] == 401
    # (and the admin who ended them is still logged in)
    expect(page.get_by_test_id("admin-users")).to_be_visible()
    assert page.request.get("/api/users/me").ok


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
