"""Fill in a new factoid through the interface's form, step by step, with screenshots (out/screens/form-*.png)"""
import sys, time
from playwright.sync_api import sync_playwright

SHOT = "smoke_scripts/out/screens/form-{}.png"


def login(page):
    page.goto("http://localhost:3010/"); page.wait_for_function("window._$HY && window._$HY.done")
    page.locator("nav[aria-label='Main']").hover(); page.get_by_role("button", name="Log in").click()
    d = page.get_by_role("dialog", name="Log in"); d.get_by_label("Username").fill("editor")
    d.get_by_label("Password").fill("smoke-editor-pw-2026"); d.get_by_role("button", name="Log in").click()
    page.get_by_role("img", name="Logged in as editor").wait_for()


with sync_playwright() as p:
    b = p.chromium.launch(); page = b.new_page(viewport={"width": 1400, "height": 1100}); errs = []
    page.on("console", lambda m: errs.append(m.text[:300]) if m.type == "error" else None)
    page.on("pageerror", lambda e: errs.append("pageerror " + str(e)[:300]))
    login(page)
    page.goto("http://localhost:3010/Factoid/new"); page.wait_for_function("window._$HY && window._$HY.done")
    page.get_by_placeholder("Label").fill("Made through the form")
    src = page.get_by_placeholder("Find Book, Zotero object…")
    src.click(); src.fill("Maximilian")
    t = time.perf_counter(); page.get_by_role("option").first.wait_for(timeout=10000)
    print(f"source options after {time.perf_counter() - t:.2f}s: {page.get_by_role('option').count()}")
    page.screenshot(path=SHOT.format("1-source"))
    page.get_by_role("option").first.click()
    page.locator("input").filter(has_not=page.locator("[placeholder]")).nth(0)
    page.get_by_label("Page").fill("12") if page.get_by_label("Page").count() else None
    page.get_by_role("button", name="Add statements").click()
    page.wait_for_timeout(500)
    page.screenshot(path=SHOT.format("2-add-menu"))
    page.get_by_role("button", name="Death", exact=True).first.click()
    page.wait_for_timeout(500)
    page.screenshot(path=SHOT.format("3-death"), full_page=True)
    st = page.locator("[aria-label='Label']").nth(1)
    st.fill("He died at last")
    page.get_by_label("Text", exact=True).fill("The source says he died, finally.")
    who = page.get_by_placeholder("Find Person…"); who.click(); who.fill("Bartolomeo")
    t = time.perf_counter(); page.get_by_role("option").first.wait_for(timeout=10000)
    print(f"person options after {time.perf_counter() - t:.2f}s:", page.get_by_role("option").all_inner_texts()[:3])
    page.get_by_role("option").first.click()
    page.get_by_role("button", name="Add date").click(); page.wait_for_timeout(300)
    page.screenshot(path=SHOT.format("4-date-menu"))
    print("date choices:", [x for x in page.get_by_role("button").all_inner_texts() if x.strip()][:40])
    page.get_by_role("button", name="Exact date").click(); page.wait_for_timeout(300)
    page.screenshot(path=SHOT.format("5-exact-date"), full_page=True)
    print("after exact date, inputs:", [(i.get_attribute("aria-label"), i.get_attribute("type")) for i in page.locator("input, select").all()])
    yr = page.get_by_label("Year")
    if yr.count(): yr.first.fill("1520")
    page.get_by_role("button", name="Save").click()
    page.wait_for_timeout(3000)
    print("url after save:", page.url)
    print("alerts:", page.get_by_role("alert").all_inner_texts()[:5], page.locator("[role=status]").all_inner_texts()[:5])
    page.screenshot(path=SHOT.format("6-after-save"), full_page=True)
    print("inputs:", [(i.get_attribute("placeholder"), i.get_attribute("aria-label"), i.get_attribute("type")) for i in page.locator("input, textarea, select").all()][:30])
    print("errors:", errs)
    b.close()
