# SDK demo

A script that uses the models of `pangloss-demo` **from outside it**, through the SDK the demo server
builds. See [the SDK](../docs/sdk.md).

```bash
# 1. The demo server (see docs/demo-setup.md), and an admin for the SDK (admins only, by default)
cd pangloss-demo
pangloss users create --username me --email me@example.org --admin
pangloss run --port 8765

# 2. In another terminal: a new environment with only the SDK in it, the clone, and the script
cd sdk-demo
PANGLOSS_USERNAME=me PANGLOSS_PASSWORD=... ./run.sh          # --keep leaves what it made
```

`run.sh` does, in order:

1. `uv venv`, and installs `pangloss-core`, `pangloss-models` and `pangloss-sdk` (the client side; no `neo4j`, no FastAPI);
2. `git clone http://127.0.0.1:8765/api/sdk/git` (read-only; git is answered from the environment by a
   `GIT_ASKPASS` helper), and installs the clone: that is `pangloss-demo-sdk`, the models of `demo_app` with their stubs;
3. runs `sdk_demo.py`: connect, check the SDK is the server's, list, create (a login is asked for here if the
   environment has none), a factoid that refers to what was created, read back, update with `expected_version`
   and a stale update refused, iterate, and remove what it made.

To keep the server's SDK up to date later: `pangloss-sdk update` (or `git pull` in the clone). To keep a login
between runs: `pangloss-sdk login http://127.0.0.1:8765`.

What it removes is only **marked** as deleted (as everything is): to leave the database as it was, remove the nodes
labelled `(SDK demo)` and their records with Cypher.
