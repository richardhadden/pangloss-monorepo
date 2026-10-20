# Development

## Setup

Requires Python 3.14 (`.python-version`) and [uv](https://docs.astral.sh/uv/).

```sh
uv sync            # installs all workspace packages into .venv
```

`pangloss-models` depends on `pydantic-meta-kit` straight from GitHub (`[tool.uv.sources]`).

## Tests

```sh
./run_tests.sh     # uv run pytest --dist=loadgroup -n auto
```

- `pangloss-models/tests`: model-initialisation tests. They need no database: the fixtures use `pangloss_sdk.databases.api` as `DATABASE_MODULE`.
- `pangloss-memgraph/tests`: integration tests. They need Docker or a Memgraph instance on `bolt://localhost:7687` (user/password `test`/`test`). If none is found, the fixture starts a `memgraph/memgraph-mage` container, runs `initialise_database` (indexes, constraints, the `label_text` text index) and creates a `PGUser` for the default username, and clears the data after tests that request `clear_database`. Tests run in the `db` xdist group so that they run serially.
  - `test_create.py`: writing; `test_update.py`: updating; `test_read.py`, `test_read_entity.py` and `test_list.py`: reading and listing; `test_initialise_database.py`: setting up the database. Shared helpers are in `helpers.py`.
- `pangloss-cli/tests`: the command line, using a fake database backend and fake apps in a temporary directory (no database needed); `pangloss-users/tests`: passwords and user models (the stored users are tested in `pangloss-memgraph/tests/test_users.py`).
- `pangloss-sdk/tests`: checks that the synchronous database-module binding works, using the hard-coded `get_document` stub.

Tests for known bugs and missing features are written as the behaviour we want and marked `@pytest.mark.xfail(strict=True, reason=...)`, so they pass the suite while the bug exists and fail (XPASS) once it is fixed, at which point the marker should be removed. `grep -rn "xfail" packages` lists them.

The root `pyproject.toml` sets `testpaths = ["packages"]` and the session-scoped asyncio loop.

## Repository layout

```
.
├── docs/                   this documentation
├── notes/modelling.md      design notes on modelling roles
├── packages/
│   ├── pangloss-cli/       the `pangloss` command
│   ├── pangloss-core/      settings
│   ├── pangloss-models/    model base classes and initialisation
│   ├── pangloss-memgraph/  Memgraph backend
│   ├── pangloss-sdk/       API-as-database client (stub)
│   └── pangloss-users/     users, passwords, request-user context variable
├── pyproject.toml          uv workspace + pytest config
└── run_tests.sh
```

## Tips

- Tests call `ModelRegistry._reset()` before each test, so classes defined inside a test function do not leak into others. Do the same in scratch scripts if you re-define classes.
- To set the acting user for a write, use the context variable: `current_request_username.set("john_smith")`. The `PGUser` node must exist in the database.
