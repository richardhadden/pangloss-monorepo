# Working in the repository

Setting up, running things, the databases, the traps that have cost time, and how docs, code and commits are written.
The reference is `implementation_docs/development.md`, `run_tests.sh` (its header says what each run is), `e2e/README.md` and
`implementation_docs/demo-setup.md`.

## Contents

- Setting up
- Tests
- Databases and ports
- Linting and types
- Traps
- Running a project from here
- How the docs are written
- How the code is written
- Commits

## Setting up

Python 3.15 (`.python-version`), [uv](https://docs.astral.sh/uv/), Docker for the databases, Node 22.12 or later for
the interface.

```sh
uv sync --all-packages --all-groups --all-extras
uv run playwright install chromium        # once, for e2e
```

All three flags, every time. Without `--all-packages` uv removes the other workspace members from `.venv`; without
the groups and extras it removes what `pangloss-dates` and the e2e tests need.

## Tests

```sh
./run_tests.sh                 # everything: ruff, ty, packages on Memgraph, Neo4j, e2e
./run_tests.sh --no-neo4j      # skip the Neo4j runs
./run_tests.sh --no-e2e        # skip the browser tests
./run_tests.sh -k typology     # other arguments go to pytest over packages/, and the later runs are skipped
uv run pytest packages/pangloss-models             # one package
uv run pytest packages/pangloss-neo4j              # the Neo4j package has a run of its own
PANGLOSS_TEST_BACKEND=neo4j uv run pytest packages/pangloss-typology/tests/live
uv run pytest e2e
```

- `packages/pangloss-models/tests` need no database (they use the SDK's storage). Anything that touches a database
  is marked `database` (a conftest's `pytest_itemcollected` calls `pangloss_testing.live.mark_database_tests`) and
  is in the xdist group `db`, run serially; `run_tests.sh` sets `PANGLOSS_TEST_DATABASE_PER_WORKER=1` instead, and
  each worker has a database of its own (`pangloss_testing.backends`; `implementation_docs/development.md`). A new
  test that uses a database outside these conftests must be marked too, or it runs beside the others on theirs.
- `conformance/test_query_costs.py` holds the transactions, statements and `PROFILE` work of the common operations
  to budgets: a change that adds a round trip or makes a read scan fails there. Raise a budget only on purpose.
- The fixtures start a Memgraph (and, for the Neo4j runs, a Neo4j) in Docker if none is reachable, and **empty the
  database** between tests. A run stops (exit 3) if that database has more than 20,000 nodes, which a test run never
  leaves: it looks like a project's data (`refuse_to_empty_real_data`; `PANGLOSS_TEST_WIPE=1` goes ahead). A small
  project on the port is not protected by this.
- Storage behaviour is tested in the conformance suite
  (`packages/pangloss-testing/src/pangloss_testing/conformance/`), which runs on both backends. An add-on's tests
  that need a database are in its `tests/live/`, with fixtures from `pangloss_testing.live`, and run on both too.
- **A known bug or a missing feature is a test of the behaviour wanted**, marked
  `@pytest.mark.xfail(strict=True, reason=...)`: it passes the suite while the bug exists and fails when it is fixed,
  which is when the marker comes off.
- **Never run tests that use the database while the browser tests run**: both use the Memgraph on 7687, and the
  package tests empty it under the e2e project (errors such as "There is no user called 'e2e'").
- `run_tests.sh` runs the browser tests on four xdist workers, each with its own project, servers and Memgraph, the
  tests dealt out one at a time: a browser test must not rely on what an earlier test left, and a module that must
  stay on one worker says so with `pytestmark = pytest.mark.xdist_group(...)` (`e2e/README.md`).
- The browser tests build one project for the session; what needs the models changed under data, or other settings,
  is in `e2e/test_changed_project.py`, which builds a second, small one on the test Neo4j. A fixture that rewrites a
  `models.py` must change its length: Python takes a file of the same size written in the same second for the one
  it has compiled.
- Test names are sentences: `test_a_deleted_factoid_hides_only_what_it_justifies`.
- Test file names must be unique across packages (`test_sync.py` in two packages clashes). If two packages'
  `conftest`s clash in one invocation, run the packages separately.
- Do not pass `-p no:logging` to quiet pytest: it removes `caplog`, which some tests use.
- Coverage of `pangloss_models` has a floor (`uv run coverage run -m pytest packages && uv run coverage report`).

## Databases and ports

| Port | What | Rule |
|---|---|---|
| 7687 | The test Memgraph (user and password `test`) | Wiped by the tests. Never keep anything here |
| 7688 | The demo's Memgraph (`pangloss-demo/`) | The user's data. Do not run tests, experiments or migrations you were not asked for against it |
| 7689 | A scratch Memgraph for large-data work, when one is running (`implementation_docs/large-data.md` has the command) | Yours to use; start one if you need a database to break |
| 7690 | The tutorial's own Memgraph (`guide/tutorial/`) | Only when replaying the tutorial |
| 7693, 7694 | The test Neo4j, started by its fixtures | Wiped by the tests |
| 7711-7713, 7721 | The other workers' test Memgraphs and Neo4j (`run_tests.sh`), started and stopped by the fixtures | Wiped by the tests |
| 8000, 3000 | `pangloss dev` (API) and `pangloss interface dev` | Often the user's own servers |

Do not guess credentials: they are in the docs or the container's environment, or you do not have them. To try
something on real-looking data, copy `pangloss-demo` to a temporary directory and point its settings at a scratch
database.

## Linting and types

`run_tests.sh` checks all of these, and the whole repository must be clean:

```sh
uv run ruff format --check packages
uv run ruff check --select F,B packages
uv run ty check
```

- Format and lint `packages/` only. `ruff format pangloss-demo` moves the `# type: ignore` comments of its generated
  stubs and rewrites its migrations; `e2e/` is not formatted either (it rewrites every file there).
- `ruff check --fix` with a wider rule set than `F,B` removes `noqa`s that the project's own check needs.
- The generated classes (`Person.Create`, `Person.get`) are invisible to a type checker, so `pyproject.toml` turns
  some `ty` rules off for tests, the demo and the code that makes the models. Elsewhere they are on: fix the type,
  do not widen the overrides without a reason written beside them.

## Traps

- `uv run` can rewrite `uv.lock` (when a package is new, say). Do not stash or check out around it; regenerate with
  `uv lock`.
- Stop a server by the process on its port (`lsof -tiTCP:<port>`), never `pkill -f "pangloss run"` or the like.
  `uv run python e2e/cleanup.py` lists servers an interrupted e2e run left behind.
- `pangloss users create` asks "Make admin?" unless given `--admin` or `--no-admin`; with no terminal, also give it
  `< /dev/null`.
- `packages/pydantic-meta-kit` is not the code in use. Change `pangloss_models.meta_kit`.
- Restart `pangloss interface dev` after changing models; they are exported when it starts.
- A scratch script that declares models needs a settings object first, and `ModelRegistry._reset()` if it declares
  the same classes twice.

## Running a project from here

`pangloss-demo/` has its own `pyproject.toml`, so `uv run pangloss …` fails there. From inside it use the workspace's
environment:

```sh
cd pangloss-demo
../.venv/bin/pangloss showmigrations
../.venv/bin/pangloss make-stubs          # after changing its models
```

A change to the demo's models needs a migration (`makemigrations`), and the user decides when the demo's database is
migrated. `implementation_docs/demo-setup.md` describes the demo; `populate.py` fills it.

## How the docs are written

- **`implementation_docs/` is the reference** (design, what is built, measurements); **`guide/` is for people using Pangloss**
  (tutorials and how-tos). A change to what a user types or sees updates the guide; a change to how something works
  updates the reference. `implementation_docs/README.md` and `guide/README.md` are the indexes: a new page gets a row.
- **Status markers**: ✅ built and tested, 🚧 partly (the gaps are said), ⏳ planned. A page with a status line at
  its top keeps it true.
- **A plan is not rewritten into a description.** It stays as written, with "As built" sections where the code
  differs, and its decisions recorded with their dates. Open questions are listed as such.
- **A plan whose work is long finished may be condensed** (the user asked for this, 2026-11-10) to what still
  matters: the decisions and who made them, the traps, the measurements, what is open. Say at its top where the full
  text is in the history of the repository. A plan of one package's interface is a section of that package's page,
  not a page of its own; small features of the interface are sections of `implementation_docs/interface-features.md`.
- **No screenshots or other images in `implementation_docs/` or the root.** Screenshots made for a review are scratch: describe
  what was decided in words, and delete them.
- **`guide/cli.md` lists every command, grouped by package.** A new or changed command, or option, is a change to
  it (`implementation_docs/cli.md` is how the command line works, and has no list).
  `packages/pangloss-cli/tests/test_cli_guide.py` fails if a command or an option is not named there.
- `implementation_docs/status.md` (what works), `TODO.md` (what is outstanding), `e2e/COVERAGE.md` (what the browser tests cover) and
  `implementation_docs/interface-to-document.md` are kept current as part of the change.
- Say what was measured and what was only read from the code. Numbers come with the size of the database and the date.
- The tutorial (`guide/tutorial/`) was checked by running every command in it; a change to what it shows means
  running it again.
- **Plain English.** Short sentences and ordinary words; say what a thing does rather than naming a pattern. British
  spelling (`initialise`, `colour`, `licence`). Dates as `2026-11-05`.

## How the code is written

- Match the file you are in. Comments say *why*, often as a parenthesised aside above the line:
  `# (one worker: the scripts share the workspace's caches)`. Docstrings are a plain sentence, usually without a
  final full stop, and name the hook or caller a function exists for.
- **Import public names from a package's root** (`from pangloss_models import Document, initialise`,
  `from pangloss_dates import Dateable`, `from pangloss_core import BaseSettings`), outside that package: the roots
  list them in `__all__` with `lazy from` imports, so a root costs nothing until a name is used and makes no cycles.
  Inside a package, its modules import from each other's files. A new public name goes into the root's `__all__`; it
  must not be the name of a submodule (the module replaces a lazy name when imported first). A test that reloads a
  module to declare its models again also reloads the roots that re-export from it (`implementation_docs/imports.md`). Migration
  files import from `pangloss_models.migrations`.
- Errors are specific exception classes with a message that names the model, field or setting at fault
  (exported by `pangloss_models`). A command shows a message and exits with a status, not a traceback, for a mistake
  the user can fix.
- No new dependency, setting, shared component or public name without a reason the user would recognise; ask when in
  doubt.
- When a design choice is the user's (a name in the public API, what a page should show, a permission rule), give a
  recommendation and ask, rather than deciding quietly. Record the answer where the feature is documented.

## Commits

Commit only when asked, and not on `main`. The form in use:

```
area: what changed, in a clause

A paragraph or two in plain sentences: what was wrong or wanted, what the
change does, what was found on the way (a bug, a trap), and how it is tested.
```

`area` is a package or part: `interface`, `dates`, `history`, `e2e`, `models`, `migrations`, `docs`. Include the
skill in the same commit when the change makes it wrong.
