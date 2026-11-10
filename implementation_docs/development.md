# Development

## Setup

Requires Python 3.15 (`.python-version`; the models use `lazy import`, PEP 810) and [uv](https://docs.astral.sh/uv/).

```sh
uv sync            # installs all workspace packages into .venv
```

`pangloss-models` contains its own copy of `pydantic-meta-kit` (`pangloss_models.meta_kit`, with its tests in `tests/meta_kit`); the separate clone in `packages/pydantic-meta-kit` is no longer used.

## Tests

```sh
./run_tests.sh     # uv run pytest --dist=loadgroup -n auto
```

- `pangloss-models/tests`: model-initialisation tests. They need no database: the fixtures use the SDK's `pangloss_sdk.storage:api` as `STORAGE`.
- `pangloss-memgraph/tests`: integration tests. They need Docker or a Memgraph instance on `bolt://localhost:7687` (user/password `test`/`test`). If none is found, the fixture starts a `memgraph/memgraph-mage:3.14.0` container (with `--experimental-enabled=commit-lock-narrowing`), runs `initialise_database` (indexes, constraints, the `label_text` text index) and creates a `PGUser` for the default username, and clears the data after tests that request `clear_database`. Tests run in the `db` xdist group so that they run serially. **The tests empty that database.** As a guard, a run stops (exit code 3) if the database has more than 20,000 nodes, more than a test run ever leaves: it looks like a project's data (`pangloss_testing.live.refuse_to_empty_real_data`). `PANGLOSS_TEST_WIPE=1` goes ahead. A small project database on the same port is not told from test data, so give a project its own port.
  - `test_create.py`: writing; `test_update.py`: updating; `test_read.py`, `test_read_entity.py` and `test_list.py`: reading and listing; `test_initialise_database.py`: setting up the database. Shared helpers are in `helpers.py`.
- `pangloss-api/tests`: the user endpoints and tokens, with users kept in memory by a fake backend; `pangloss-memgraph/tests/test_api.py` runs them against Memgraph.
- `pangloss-cli/tests`: the command line, using a fake database backend and fake apps in a temporary directory (no database needed); `pangloss-users/tests`: passwords and user models (the stored users are tested in `pangloss-memgraph/tests/test_users.py`).
- `pangloss-sdk/tests`: checks that the synchronous database-module binding works, using the hard-coded `get_document` stub.

Tests for known bugs and missing features are written as the behaviour we want and marked `@pytest.mark.xfail(strict=True, reason=...)`, so they pass the suite while the bug exists and fail (XPASS) once it is fixed, at which point the marker should be removed. `grep -rn "xfail" packages` lists them.

The root `pyproject.toml` sets `testpaths = ["packages"]` and the session-scoped asyncio loop.

Line coverage of `pangloss_models` (the Python must be one `coverage` supports: 3.15.1 or later):

```bash
uv run coverage run -m pytest packages && uv run coverage report    # fails below 94% (pyproject.toml)
```

Every package at once, over the xdist workers and the Neo4j runs: `.coveragerc-all`, with the commands in the
[README](../README.md#test-coverage).

The tests of `pangloss-models` are in `tests/initialisation/` (declaring and initialising models), `tests/generated_models/` (the models made, with the snapshot), `tests/migrations/`, `tests/export/` and `tests/typestubs/`; the helpers they share (`kitchen_sink`, `sample_data`, ...) are in `tests/support/`.

## Repository layout

```
.
├── implementation_docs/                   this documentation
├── notes/modelling.md      design notes on modelling roles
├── packages/
│   ├── pangloss-api/       the REST API
│   ├── pangloss-cli/       the `pangloss` command
│   ├── pangloss-core/      settings
│   ├── pangloss-models/    model base classes and initialisation
│   ├── pangloss-memgraph/  Memgraph backend
│   ├── pangloss-sdk/       API-as-database client (stub)
│   └── pangloss-users/     users, passwords, request-user context variable
├── pyproject.toml          uv workspace + pytest config
└── run_tests.sh
```

## For agents: the Pangloss skill

`.claude/skills/pangloss/` is a skill for Claude (an "Agent skill"): what Pangloss is, the design principles, a map of
the repository, and references on modelling, the architecture, the interface and working here. Claude Code finds it
by itself in this repository. It is kept as the code is: **a change that makes it wrong corrects it in the same
commit** (its last section says when, and what not to put in it). `./run_tests.sh` runs
`.claude/skills/pangloss/scripts/check_skill.py`, which fails if the skill names a path, module or name that is no
longer there, or does not mention a package of `packages/`.

## Tips

- Tests call `ModelRegistry._reset()` before each test, so classes defined inside a test function do not leak into others. Do the same in scratch scripts if you re-define classes.
- To set the acting user for a write, use the context variable: `current_request_username.set("john_smith")`. The `PGUser` node must exist in the database.
