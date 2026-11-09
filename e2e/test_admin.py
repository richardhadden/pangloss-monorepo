"""The page /admin (`pangloss_admin`): who sees it, and a dump from the button to the download"""

import gzip
import re

from conftest import OTHER_PASSWORD, OTHER_USERNAME
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
