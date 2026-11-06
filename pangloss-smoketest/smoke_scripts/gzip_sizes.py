"""Sizes and times of big answers, plain and gzipped: the API (:8010) and, if given, an interface server (`gzip_sizes.py http://localhost:3011`)"""
import sys, time, json
import httpx2 as httpx
API = "http://localhost:8010"
SUPER = json.load(open("smoke_scripts/out/superperson.json"))["super_id"]
tok = httpx.post(f"{API}/api/users/token", data={"username": "editor", "password": "smoke-editor-pw-2026"}).json()["access_token"]
def measure(base, paths, headers):
    rows = []
    for p in paths:
        out = []
        for enc in ("identity", "gzip"):
            t = time.perf_counter()
            with httpx.stream("GET", base + p, headers={**headers, "Accept-Encoding": enc}, timeout=300) as r:
                raw = sum(len(c) for c in r.iter_raw()); enc_got = r.headers.get("content-encoding", "-"); status = r.status_code
            out.append((raw, time.perf_counter() - t, enc_got, status))
        (a, ta, _, s), (b, tb, e, _) = out
        rows.append(f"{p[:58]:58} {s} {a:>11,} -> {b:>10,} ({b / a * 100:5.1f}%, {e:4})  {ta:6.2f}s -> {tb:6.2f}s")
        print(rows[-1], flush=True)
    return rows
H = {"Authorization": f"Bearer {tok}"}
rows = measure(API, ["/api/calendar/day/G1500-03-25", "/api/calendar/month/gregorian/1500/3", "/openapi.json", f"/api/Person/{SUPER}",
                     "/api/Person?page_size=500", "/api/Factoid?page_size=500", "/api/Settlement?page_size=50"], H)
if len(sys.argv) > 1:
    ui = sys.argv[1]
    print("-- interface", ui)
    rows += measure(ui, ["/", "/Person", f"/Person/{SUPER}", "/calendar/gregorian/1500/3", "/calendar/gregorian/1500/3/25", "/Factoid/new"],
                    {"Cookie": f"pangloss_access={tok}"})
with open("smoke_scripts/out/gzip_sizes.txt", "a") as f: f.write("\n".join(rows) + "\n\n")
