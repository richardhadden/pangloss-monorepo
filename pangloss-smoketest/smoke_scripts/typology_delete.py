"""Problem 29: the delete every entity has, on a type of a typology that is in use, and the names a typology has.

    ../.venv/bin/python smoke_scripts/typology_delete.py
"""

import httpx2 as httpx

API = "http://localhost:8010/api"

with httpx.Client(timeout=60) as c:
    token = c.post(
        f"{API}/users/token", data={"username": "editor", "password": "smoke-editor-pw-2026"}
    ).json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    tree = c.get(f"{API}/typology/OccupationType/tree").json()
    print("roots:", [n["label"] for n in tree])

    def find(nodes, label):
        for node in nodes:
            if node["label"] == label:
                return node
            found = find(node.get("children", []), label)
            if found:
                return found
        return None

    for label in ("Merchant", "Banker"):
        node = find(tree, label)
        if node is None:
            print(label, "not in the tree")
            continue
        before = c.get(f"{API}/OccupationType/{node['id']}").json()["meta"].get("markedForDeletion")
        asked = c.get(f"{API}/OccupationType/{node['id']}/deletable", headers=headers).json()
        deleted = c.delete(f"{API}/OccupationType/{node['id']}", headers=headers)
        after = c.get(f"{API}/OccupationType/{node['id']}").json()["meta"].get("markedForDeletion")
        print(f"{label}: marked before {before}; deletable {asked['deletable']}: {asked['reason']}")
        print(f"   DELETE -> {deleted.status_code} {deleted.json().get('detail')}; marked after {after}")

    # a second type of a name beside the first
    again = c.post(f"{API}/typology/OccupationType", json={"label": "Merchant"}, headers=headers)
    print("a second root Merchant:", again.status_code, again.json().get("detail"))
    # the typology by its own name
    for name in ("OccupationTypology", "OccupationType", "Occupation"):
        got = c.get(f"{API}/typology/{name}/tree")
        print(name, got.status_code, got.json().get("detail") if got.status_code != 200 else "")
