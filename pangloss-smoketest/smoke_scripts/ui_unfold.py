"""Open a deeply nested factoid (view and edit) and unfold it to the bottom, one fold at a time (2026-11-07: a block
five deep starts folded), timing each unfold; a screenshot of the whole page at the end.

    ../.venv/bin/python smoke_scripts/ui_unfold.py ID      # SMOKE_UI for the server, :3010 by default
"""

import os
import sys
import time

from playwright.sync_api import sync_playwright

BASE = os.environ.get("SMOKE_UI", "http://localhost:3010")

with sync_playwright() as p:
    b = p.chromium.launch()
    page = b.new_page(viewport={"width": 1400, "height": 1000})
    errs: list[str] = []
    page.on("console", lambda m: errs.append(m.text[:300]) if m.type == "error" else None)
    page.on("pageerror", lambda e: errs.append("pageerror " + str(e)[:300]))
    page.goto(BASE + "/", timeout=180000)
    page.wait_for_function("window._$HY && window._$HY.done", timeout=180000)
    page.locator("nav[aria-label='Main']").hover()
    page.get_by_role("button", name="Log in").click()
    d = page.get_by_role("dialog", name="Log in")
    d.get_by_label("Username").fill("editor")
    d.get_by_label("Password").fill("smoke-editor-pw-2026")
    d.get_by_role("button", name="Log in").click()
    page.get_by_role("img", name="Logged in as editor").wait_for()
    item = sys.argv[1]
    for suffix in ("", "/edit"):
        errs.clear()
        page.goto(f"{BASE}/Factoid/{item}{suffix}", timeout=180000)
        page.wait_for_function("window._$HY && window._$HY.done", timeout=180000)
        page.wait_for_timeout(1000)
        clicks = []
        while True:
            folded = page.locator("button[aria-expanded='false'][aria-label^='Fold or unfold']")
            if folded.count() == 0:
                break
            before = page.evaluate("document.querySelectorAll('*').length")
            t0 = time.perf_counter()
            # (a click from the page itself: the bar is scrolled to by hand, and the browser's own click sometimes
            # found it moved by the time it looked)
            folded.first.scroll_into_view_if_needed()
            folded.first.evaluate("el => el.click()")
            # (unfolded when something new is on the page)
            page.wait_for_function(f"document.querySelectorAll('*').length > {before}", timeout=60000)
            clicks.append(time.perf_counter() - t0)
        n = page.evaluate("document.querySelectorAll('*').length")
        width = page.evaluate("document.documentElement.scrollWidth")
        name = f"{item[-6:]}{suffix.replace('/', '_')}_unfolded"
        page.screenshot(path=f"smoke_scripts/out/ui_nested_{name}.png", full_page=True)
        print(f"/Factoid/{item}{suffix}: {len(clicks)} unfolds, each {', '.join(f'{c * 1000:.0f}' for c in clicks)} ms; "
              f"{n} elements, page {width} px wide, errors: {errs[:5]}")
    b.close()
