"""Interface features, as `editor`: history panel, delete, list search form, by-date view, review panel, a stale edit.
Screenshots in out/screens/feat-*.png

    ../.venv/bin/python smoke_scripts/ui_features.py        # from pangloss-smoketest/
"""

import json
import time
from pathlib import Path

import httpx2 as httpx
from playwright.sync_api import sync_playwright

OUT = Path("smoke_scripts/out")
BASE = "http://localhost:3010"
API = "http://localhost:8010/api"
factoids = json.loads((OUT / "factoids.json").read_text())
entities = json.loads((OUT / "entities.json").read_text())
SUPER = json.loads((OUT / "superperson.json").read_text())["super_id"]
log = []


def say(*a):
    line = " ".join(str(x) for x in a)
    print(line, flush=True)
    log.append(line)


def shot(page, name):
    page.screenshot(path=str(OUT / "screens" / f"feat-{name}.png"))


def hydrated(page):
    page.wait_for_function("window._$HY && window._$HY.done", timeout=120000)


def buttons(page):
    return [b.get_attribute("aria-label") or b.inner_text().strip() for b in page.get_by_role("button").all()][:40]


with sync_playwright() as p:
    b = p.chromium.launch()
    page = b.new_page(viewport={"width": 1400, "height": 1000})
    errs = []
    page.on("console", lambda m: errs.append(m.text[:300]) if m.type == "error" else None)
    page.on("pageerror", lambda e: errs.append("pageerror " + str(e)[:300]))
    page.goto(BASE + "/"); hydrated(page)
    page.locator("nav[aria-label='Main']").hover(); page.get_by_role("button", name="Log in").click()
    d = page.get_by_role("dialog", name="Log in"); d.get_by_label("Username").fill("editor")
    d.get_by_label("Password").fill("smoke-editor-pw-2026"); d.get_by_role("button", name="Log in").click()
    page.get_by_role("img", name="Logged in as editor").wait_for()

    # --- history of the factoid edited earlier
    page.goto(f"{BASE}/Factoid/{factoids[0]}"); hydrated(page)
    say("factoid page buttons:", buttons(page))
    h = page.get_by_role("button", name="History")
    if h.count():
        h.first.click(); page.wait_for_timeout(1500); shot(page, "history")
        say("history panel text:", page.locator("aside, [role=complementary], [role=dialog]").all_inner_texts()[:2])
    else:
        say("no History button found")

    # --- delete an unused settlement through the button
    page.goto(f"{BASE}/Settlement/{entities['Settlement'][-1]}"); hydrated(page)
    dl = page.get_by_role("button", name="Delete")
    if dl.count():
        dl.first.click(); page.wait_for_timeout(1000); shot(page, "delete-ask")
        say("delete dialog:", page.get_by_role("dialog").all_inner_texts()[:1], page.get_by_role("alertdialog").all_inner_texts()[:1])
    # --- delete a referred-to person: what does it say?
    page.goto(f"{BASE}/Person/{SUPER}"); hydrated(page)
    dl = page.get_by_role("button", name="Delete")
    if dl.count():
        t = time.perf_counter(); dl.first.click(); page.wait_for_timeout(2000); shot(page, "delete-super")
        say(f"delete super person ({time.perf_counter() - t:.1f}s):", (page.get_by_role("dialog").all_inner_texts() + page.get_by_role("alertdialog").all_inner_texts())[:1])
        page.keyboard.press("Escape")

    # --- by-date view on the super person
    bd = page.get_by_role("button", name="By date").or_(page.get_by_role("radio", name="By date")).or_(page.get_by_role("tab", name="By date"))
    say("super person buttons:", buttons(page)[:20])
    if bd.count():
        t = time.perf_counter(); bd.first.click(); page.wait_for_timeout(3000)
        say(f"by date: {time.perf_counter() - t:.1f}s, DOM {page.evaluate('document.querySelectorAll(\"*\").length')}")
        shot(page, "by-date")

    # --- list search form
    page.goto(f"{BASE}/Person"); hydrated(page)
    say("person list buttons:", buttons(page)[:20])
    sf = page.get_by_role("button", name="Search form").or_(page.get_by_role("button", name="Structured search"))
    if sf.count():
        sf.first.click(); page.wait_for_timeout(1000); shot(page, "search-form")
    page.get_by_placeholder("Search").first.fill("Medici")
    page.keyboard.press("Enter"); page.wait_for_timeout(1500); shot(page, "list-medici")
    say("list after Medici:", page.locator("main").inner_text()[:300].replace("\n", " | "))

    # --- review panel on an unchecked factoid
    page.goto(f"{BASE}/Factoid/{factoids[-1]}"); hydrated(page)
    rv = page.get_by_role("button", name="Review")
    if rv.count():
        rv.first.click(); page.wait_for_timeout(1000); shot(page, "review")
        say("review panel:", page.locator("aside, [role=complementary]").all_inner_texts()[:1])

    # --- a stale edit: open the edit form, change the factoid over the API, then save in the form
    fid = factoids[10]
    page.goto(f"{BASE}/Factoid/{fid}/edit"); hydrated(page)
    tok = httpx.post(f"{API}/users/token", data={"username": "reviewer", "password": "smoke-reviewer-pw-2026"}).json()["access_token"]
    H = {"Authorization": f"Bearer {tok}"}
    r = httpx.get(f"{API}/Factoid/{fid}/edit", headers=H); body = r.json(); body["label"] += " (changed meanwhile)"
    r2 = httpx.put(f"{API}/Factoid/{fid}", headers={**H, "If-Match": r.headers["etag"]}, json=body)
    say("changed meanwhile over the API:", r2.status_code)
    lbl = page.get_by_placeholder("Label").or_(page.get_by_label("Label")).first
    lbl.fill("Edited in the form after someone else")
    page.get_by_role("button", name="Save").click(); page.wait_for_timeout(2500); shot(page, "stale-save")
    say("stale save: url", page.url, "| alerts:", page.get_by_role("alert").all_inner_texts()[:3], "| status:", page.locator("[role=status]").all_inner_texts()[:3])

    say("console errors:", errs[:8])
    (OUT / "ui_features.log").write_text("\n".join(log))
    b.close()
