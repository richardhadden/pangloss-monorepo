#! /bin/sh
# Everything, in three runs (after `ruff`: the formatting, pyflakes and bugbear; and `ty`, the static types):
#
#   1. the unit and integration tests of the packages (in parallel), with the Memgraph in Docker, the conformance suite
#      (`pangloss_testing/conformance/`, the tests every backend passes) among them;
#   2. the conformance suite again, on Neo4j (`PANGLOSS_TEST_BACKEND=neo4j`); the tests of `pangloss-neo4j`, against a
#      Neo4j in Docker. (Its own run: it has its own database and its own
#      process-wide settings, so it cannot share a process with the Memgraph tests; it is serial, as they all use one database);
#      Then the live tests of the add-on packages (typology, calendar, dates, zotero), which the first run made on Memgraph,
#      again on Neo4j (`PANGLOSS_TEST_BACKEND=neo4j`, one process for each package: see `pangloss-testing`);
#   3. the end-to-end tests in a browser (e2e/, one process: they share the test Memgraph, which the first run wipes).
#
#   ./run_tests.sh                run everything
#   ./run_tests.sh --no-neo4j     skip the Neo4j tests (no Neo4j image needed)
#   ./run_tests.sh --no-e2e       skip the browser tests (no browser needed)
#   ./run_tests.sh -k typology    other arguments go to the first pytest run, which is then all of `packages/` (the
#                                 Neo4j package too) and nothing else: the second and third runs are skipped, as they
#                                 are not what was asked for; to run only one of them:
#                                     uv run pytest packages/pangloss-neo4j
#                                     uv run pytest e2e
#
# The browser tests need Chromium once: uv run playwright install chromium
# The Neo4j tests start `neo4j:2026.10.1` themselves (ports 7693 and 7694) if Docker is running; without it they are skipped.

neo4j=yes
e2e=yes
args=""
for arg in "$@"; do
    case "$arg" in
        --no-neo4j) neo4j=no ;;
        --no-e2e) e2e=no ;;
        *) args="$args $arg"; neo4j=no; e2e=no ;;
    esac
done

# Each run's output goes to the screen as it happens, and nothing more: the script fails if any run failed.
status=0

# run LABEL COMMAND...: runs the command, keeping its exit status if it failed
run() {
    label=$1
    shift
    echo
    echo "=== $label"
    "$@" || status=$?
}

if [ -z "$args" ]; then
    # (formatting, and pyflakes: unused names, undefined names, names defined twice)
    run "ruff (format, pyflakes, bugbear)" sh -c 'uv run ruff format --check packages && uv run ruff check --select F,B packages'
    # (the static types, of the whole repository: what is relaxed, and where, is in `pyproject.toml`, `[tool.ty]`)
    run "ty" uv run ty check
    # (the skill that tells an agent how Pangloss works, `.claude/skills/pangloss`: the paths, modules and packages
    # it names are still there. What it says is kept true by hand, with the change that makes it untrue)
    run "the Pangloss skill" uv run python .claude/skills/pangloss/scripts/check_skill.py
    # (everything: the Neo4j package has a run of its own)
    run "packages (Memgraph)" uv run pytest --dist=loadgroup -n auto --ignore=packages/pangloss-neo4j
else
    run "packages ($args )" uv run pytest --dist=loadgroup -n auto $args
fi

if [ "$neo4j" = yes ]; then
    run "conformance on Neo4j" env PANGLOSS_TEST_BACKEND=neo4j uv run pytest packages/pangloss-testing/src/pangloss_testing/conformance
    run "pangloss-neo4j" uv run pytest packages/pangloss-neo4j
    for package in typology calendar dates zotero; do
        run "pangloss-$package live tests on Neo4j" env PANGLOSS_TEST_BACKEND=neo4j uv run pytest "packages/pangloss-$package/tests/live"
    done
fi

if [ "$e2e" = yes ]; then
    run "e2e (browser)" uv run pytest e2e --tracing retain-on-failure --screenshot only-on-failure
fi

exit $status
