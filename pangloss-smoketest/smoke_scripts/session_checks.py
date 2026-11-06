"""Sessions: a password change ends tokens; logout-all; personal tokens survive logout-all; revoke; review errors_found"""
import json, httpx2 as httpx
API = "http://localhost:8010/api"
def login(u, pw): return httpx.post(f"{API}/users/token", data={"username": u, "password": pw})
def me(t): return httpx.get(f"{API}/users/me", headers={"Authorization": f"Bearer {t}"}).status_code
pw = "smoke-reader-pw-2026"
a = login("reader", pw).json()["access_token"]; b = login("reader", pw).json()["access_token"]
pat = httpx.post(f"{API}/users/me/tokens", headers={"Authorization": f"Bearer {a}"}, json={"name": "s", "scope": "read", "expiresDays": 1}).json()
print("two sessions + a token:", me(a), me(b), me(pat["token"]))
r = httpx.post(f"{API}/users/me/logout-all", headers={"Authorization": f"Bearer {a}"}); print("logout-all:", r.status_code)
print("after logout-all, sessions:", me(a), me(b), "| personal token:", me(pat["token"]))
c = login("reader", pw).json()["access_token"]
r = httpx.put(f"{API}/users/me/password", headers={"Authorization": f"Bearer {c}"}, json={"oldPassword": pw, "newPassword": "smoke-reader-pw-2027"})
print("password change:", r.status_code, "| old session after:", me(c), "| old password:", login("reader", pw).status_code, "| new:", login("reader", "smoke-reader-pw-2027").status_code)
d = login("reader", "smoke-reader-pw-2027").json()["access_token"]
httpx.put(f"{API}/users/me/password", headers={"Authorization": f"Bearer {d}"}, json={"oldPassword": "smoke-reader-pw-2027", "newPassword": pw})
r = httpx.put(f"{API}/users/me/password", headers={"Authorization": f"Bearer {login('reader', pw).json()['access_token']}"}, json={"oldPassword": pw, "newPassword": "short"})
print("a too-short new password:", r.status_code, r.text[:150])
e = login("reader", pw).json()["access_token"]
r = httpx.delete(f"{API}/users/me/tokens/{pat['id']}", headers={"Authorization": f"Bearer {e}"}); print("revoke personal token:", r.status_code, "| it now:", me(pat["token"]))
# repeated wrong passwords: is there a limit?
codes = [login("editor", "wrong").status_code for _ in range(12)]
print("12 wrong passwords for editor:", codes, "| then the right one:", login("editor", "smoke-editor-pw-2026").status_code)
# review: errors found
rv = login("reviewer", "smoke-reviewer-pw-2026").json()["access_token"]; H = {"Authorization": f"Bearer {rv}"}
f = json.load(open("smoke_scripts/out/factoids.json"))[600]
r = httpx.post(f"{API}/review/{f}/status", headers=H, json={"status": "errors_found", "comment": "The page is wrong"})
print("errors_found:", r.status_code, json.dumps({k: r.json().get(k) for k in ("status", "published", "openComments")}))
print("anonymous read after errors_found:", httpx.get(f"{API}/Factoid/{f}").status_code)
q = httpx.get(f"{API}/review/queue", headers=H, params={"status": "errors_found"}).json()
print("queue of errors_found:", q.get("count"), [x["label"] for x in q.get("results", [])][:2])
