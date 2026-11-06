"""Load one page of the interface (:3010) and list its API requests with times: `ui_probe.py /path [login]`"""
import sys, time
from playwright.sync_api import sync_playwright
path = sys.argv[1]
with sync_playwright() as p:
    b = p.chromium.launch(); page = b.new_page(viewport={"width": 1400, "height": 1000})
    if len(sys.argv) > 2:
        page.goto("http://localhost:3010/"); page.wait_for_function("window._$HY && window._$HY.done")
        page.locator("nav[aria-label='Main']").hover(); page.get_by_role("button", name="Log in").click()
        d = page.get_by_role("dialog", name="Log in"); d.get_by_label("Username").fill("editor")
        d.get_by_label("Password").fill("smoke-editor-pw-2026"); d.get_by_role("button", name="Log in").click()
        page.get_by_role("img", name="Logged in as editor").wait_for()
    t0 = time.perf_counter(); reqs = []; errs = []
    page.on("console", lambda m: errs.append(m.text[:400]) if m.type == "error" else None)
    page.on("pageerror", lambda e: errs.append("pageerror " + str(e)[:400]))
    page.on("requestfinished", lambda r: reqs.append((time.perf_counter() - t0, r.method, r.url, r.response().status if r.response() else None)) if "/api/" in r.url or "_server" in r.url else None)
    page.on("requestfailed", lambda r: reqs.append((time.perf_counter() - t0, r.method, r.url, "FAILED")))
    page.goto("http://localhost:3010" + path, timeout=120000); page.wait_for_function("window._$HY && window._$HY.done", timeout=120000)
    print(f"hydrated at {time.perf_counter() - t0:.2f}s")
    page.wait_for_timeout(3000)
    print("ERRORS:", errs)
    for t, m, u, s in reqs: print(f"{t:6.2f}s {s} {m} {u[:160]}")
    b.close()
