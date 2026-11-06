"""Script in a label (rendered by the interface on :3011), and Cypher-looking keys in a structured search"""
import httpx2 as httpx
from playwright.sync_api import sync_playwright
API = "http://localhost:8010/api"
tok = httpx.post(f"{API}/users/token", data={"username": "editor", "password": "smoke-editor-pw-2026"}).json()["access_token"]
H = {"Authorization": f"Bearer {tok}"}
evil = '<img src=x onerror="window.__pwned=1"><script>window.__pwned=2</script>"\'><svg onload="window.__pwned=3">'
r = httpx.post(f"{API}/Commodity", headers=H, json={"label": evil}); cid = r.json()["id"]; print("made:", r.status_code)
with sync_playwright() as p:
    b = p.chromium.launch(); page = b.new_page(); dialogs = []
    page.on("dialog", lambda d: (dialogs.append(d.message), d.dismiss()))
    for path in (f"/Commodity/{cid}", "/Commodity", f"/Commodity?q=onerror"):
        page.goto("http://localhost:3011" + path); page.wait_for_function("window._$HY && window._$HY.done"); page.wait_for_timeout(500)
        print(path[:40], "| __pwned:", page.evaluate("window.__pwned ?? null"), "| label text shown:", evil[:20] in page.content().replace("&lt;", "<"))
    b.close()
for key in ["label`) DETACH DELETE n //", "label) RETURN 1 //", "$where", "__proto__", "label.`x`"]:
    r = httpx.post(f"{API}/search", json={"type": "Person", "where": {key: {"eq": "x"}}})
    print(f"search key {key!r}: {r.status_code} {r.text[:120]}")
r = httpx.post(f"{API}/search", json={"type": "Person) DETACH DELETE n //", "where": {}}); print("search type injection:", r.status_code, r.text[:100])
r = httpx.get(f"{API}/Person", params={"order_by": "label; MATCH (n) DETACH DELETE n"}); print("odd order_by on list:", r.status_code)
r = httpx.post(f"{API}/search", json={"type": "Person", "where": {}, "order_by": [{"field": "label` DESC, n.x //"}]}); print("order_by field injection:", r.status_code, r.text[:120])
print("persons still there:", httpx.get(f"{API}/Person", params={"page_size": 1}).json()["count"])
