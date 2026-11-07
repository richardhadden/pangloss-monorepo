"""Any pages of the interface, logged in as editor: time, elements, errors, screenshot

    ../.venv/bin/python smoke_scripts/ui_pages.py /PATH [/PATH ...]

For each page: time to hydrate, DOM elements, console errors and page errors, a screenshot in out/ui_nested_*.png.
"""

import sys
import time

from playwright.sync_api import sync_playwright

import os

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
    for path in sys.argv[1:]:
        for suffix in ("",):
            errs.clear()
            t0 = time.perf_counter()
            page.goto(f"{BASE}{path}", timeout=180000)
            page.wait_for_function("window._$HY && window._$HY.done", timeout=180000)
            page.wait_for_timeout(2000)  # (the edit page keeps a live feed open: never "networkidle")
            took = time.perf_counter() - t0 - 2
            n = page.evaluate("document.querySelectorAll('*').length")
            name = path.strip("/").replace("/", "_")[-40:]
            page.screenshot(path=f"smoke_scripts/out/ui_pages_{name}.png")  # (the viewport: a virtual list is very tall)
            print(f"{path}: {took:.2f}s, {n} elements, errors: {errs[:5]}")
    b.close()
