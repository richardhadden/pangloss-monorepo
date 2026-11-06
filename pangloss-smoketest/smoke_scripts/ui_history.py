"""Open the history panel of the first factoid (edited once), restore it to version 1 in the interface, check the API"""
import json
import httpx2 as httpx
from playwright.sync_api import sync_playwright

f = json.load(open("smoke_scripts/out/factoids.json"))[0]
API = "http://localhost:8010/api"
tok = httpx.post(f"{API}/users/token", data={"username": "editor", "password": "smoke-editor-pw-2026"}).json()["access_token"]
H = {"Authorization": f"Bearer {tok}"}
before = httpx.get(f"{API}/Factoid/{f}", headers=H).json()
print("before:", before["meta"]["version"], before["label"])
with sync_playwright() as p:
    b = p.chromium.launch(); page = b.new_page(viewport={"width": 1400, "height": 1000}); errs = []
    page.on("console", lambda m: errs.append(m.text[:200]) if m.type == "error" else None)
    page.goto("http://localhost:3010/"); page.wait_for_function("window._$HY && window._$HY.done")
    page.locator("nav[aria-label='Main']").hover(); page.get_by_role("button", name="Log in").click()
    d = page.get_by_role("dialog", name="Log in"); d.get_by_label("Username").fill("editor")
    d.get_by_label("Password").fill("smoke-editor-pw-2026"); d.get_by_role("button", name="Log in").click()
    page.get_by_role("img", name="Logged in as editor").wait_for()
    page.goto(f"http://localhost:3010/Factoid/{f}"); page.wait_for_function("window._$HY && window._$HY.done")
    page.get_by_role("button", name="History").click(); page.wait_for_timeout(1500)
    page.screenshot(path="smoke_scripts/out/screens/feat-history-open.png")
    # (the oldest version: the card that says CREATED)
    entries = page.get_by_text("Factoid 0: what the source says of Dudley", exact=True)
    print("entries by importer:", entries.count())
    if entries.count():
        entries.last.click(); page.wait_for_timeout(1000)
        page.get_by_role("button", name="Restore to this point").click(); page.wait_for_timeout(1500)
        dlg = page.get_by_role("dialog")
        print("after restore click:", (dlg.all_inner_texts() or ["(no dialog)"])[0][:300].replace("\n", " | "))
        if dlg.count():
            ok = dlg.get_by_role("button").filter(has_text="Restore")
            if ok.count(): ok.last.click(); page.wait_for_timeout(2500)
        page.screenshot(path="smoke_scripts/out/screens/feat-history-restored.png")
    print("errors:", errs[:5])
    b.close()
after = httpx.get(f"{API}/Factoid/{f}", headers=H).json()
print("after:", after["meta"]["version"], after["label"])
