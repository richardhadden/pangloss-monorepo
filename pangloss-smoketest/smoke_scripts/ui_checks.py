"""The built interface (:3010) in a browser: every main page, as `editor`, with load times, console errors and
screenshots in smoke_scripts/out/screens/

    ../.venv/bin/python smoke_scripts/ui_checks.py         # from pangloss-smoketest/
"""

import json
import random
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

HERE = Path(__file__).parent
OUT = HERE / "out"
SHOTS = OUT / "screens"
SHOTS.mkdir(parents=True, exist_ok=True)
BASE = "http://localhost:3010"
R = random.Random(3)
entities = json.loads((OUT / "entities.json").read_text())
factoids = json.loads((OUT / "factoids.json").read_text())
SUPER = json.loads((OUT / "superperson.json").read_text())["super_id"]
results = []


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1400, "height": 1000})
        console: list[str] = []
        page.on("console", lambda m: console.append(f"{m.type}: {m.text}") if m.type in ("error", "warning") else None)
        page.on("pageerror", lambda e: console.append(f"pageerror: {e}"))
        failed: list[str] = []
        page.on("response", lambda r: failed.append(f"{r.status} {r.url}") if r.status >= 500 else None)

        def visit(name, path, wait_for=None, timeout=60000):
            console.clear()
            failed.clear()
            t = time.perf_counter()
            status = None
            try:
                resp = page.goto(BASE + path, timeout=timeout, wait_until="load")
                status = resp.status if resp else None
                page.wait_for_function("window._$HY && window._$HY.done", timeout=timeout)
                if wait_for:
                    page.locator(wait_for).first.wait_for(timeout=timeout)
                ok = status is not None and status < 400
            except Exception as e:  # (recorded)
                ok = False
                console.append(f"exception: {type(e).__name__}: {str(e)[:300]}")
            ms = (time.perf_counter() - t) * 1000
            shot = SHOTS / f"{len(results):02d}-{name.replace(' ', '_').replace('/', '_')}.png"
            try:
                page.screenshot(path=str(shot), full_page=False)
            except Exception:
                pass
            errs = [c for c in console if not c.startswith("warning")]
            tag = "PASS" if ok and not errs and not failed else "FAIL"
            print(f"{tag} {name} {path} [{ms:.0f} ms] status={status} errors={errs[:3]} 5xx={failed[:3]}", flush=True)
            results.append({"name": name, "path": path, "ms": round(ms), "status": status, "console": console[:10], "5xx": failed[:10],
                            "ok": tag == "PASS", "shot": shot.name})

        # log in through the dialog
        visit("home (anonymous)", "/")
        page.locator("nav[aria-label='Main']").hover()
        page.get_by_role("button", name="Log in").click()
        dialog = page.get_by_role("dialog", name="Log in")
        dialog.get_by_label("Username").fill("editor")
        dialog.get_by_label("Password").fill("smoke-editor-pw-2026")
        dialog.get_by_role("button", name="Log in").click()
        page.get_by_role("img", name="Logged in as editor").wait_for(timeout=15000)
        print("logged in", flush=True)

        visit("home", "/")
        visit("Person list", "/Person")
        visit("Person list search", "/Person?q=Medici")
        visit("Person list far position", "/Person?at=20000")
        visit("Person page", f"/Person/{R.choice(entities['Person'])}")
        visit("SUPER person page", f"/Person/{SUPER}", timeout=120000)
        visit("SUPER person edit", f"/Person/{SUPER}/edit", timeout=120000)
        visit("Factoid list", "/Factoid")
        visit("Factoid page", f"/Factoid/{factoids[0]}")
        visit("Factoid page 2", f"/Factoid/{R.choice(factoids)}")
        visit("Factoid edit", f"/Factoid/{R.choice(factoids)}/edit")
        visit("Factoid new", "/Factoid/new")
        visit("Statement list (abstract)", "/Statement")
        visit("Group list (trait/base)", "/Group")
        visit("Settlement page", f"/Settlement/{entities['Settlement'][0]}")
        visit("Office page", f"/Office/{entities['Office'][0]}")
        visit("Book new", "/Book/new")
        visit("Feast new", "/Feast/new")
        visit("Feast page", f"/Feast/{entities['Feast'][0]}")
        visit("OccupationType tree", "/OccupationType")
        visit("ZoteroObject list", "/ZoteroObject")
        visit("calendar", "/calendar")
        visit("calendar month", "/calendar/gregorian/1500/3")
        visit("calendar day", "/calendar/gregorian/1500/3/25", timeout=120000)
        visit("review queue", "/review")
        visit("unknown page", "/this/is/not/a/page")
        visit("unknown model", "/Nonsense")
        visit("missing person", "/Person/01a1ae17-0000-7000-8000-000000000000")

        # super person: how big is the page?
        page.goto(f"{BASE}/Person/{SUPER}", timeout=120000)
        page.wait_for_function("window._$HY && window._$HY.done", timeout=120000)
        n = page.evaluate("document.querySelectorAll('*').length")
        h = page.evaluate("document.documentElement.scrollHeight")
        print(f"NOTE super person page: {n} DOM elements, {h}px tall", flush=True)
        results.append({"name": "super person DOM", "elements": n, "height": h})
        page.screenshot(path=str(SHOTS / "super-person-full.png"), full_page=False)

        (OUT / "ui_checks.json").write_text(json.dumps(results, indent=1))
        browser.close()


if __name__ == "__main__":
    main()
