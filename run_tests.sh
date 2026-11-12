#! /bin/sh
# Everything, in three runs (after `ruff`: the formatting, pyflakes and bugbear; and `ty`, the static types):
#
#   1. the unit and integration tests of the packages, the conformance suite (`pangloss_testing/conformance/`, the
#      tests every backend passes) among them, on Memgraph. In two parts, at the same time: the tests that need no
#      database, on every core; and those that use the test database (marked `database`), on four xdist workers, each
#      with a Memgraph of its own (7687, 7711, 7712, 7713: `pangloss_testing.backends`, started in Docker if they are not
#      there, and stopped after). Beside them, the tests of `pangloss-neo4j`, against a Neo4j in Docker (a run of its own:
#      it has its own database and its own process-wide settings, so it cannot share a process with the Memgraph tests);
#   2. the conformance suite and the live tests of the add-on packages (typology, calendar, dates, zotero, rdf) again,
#      on Neo4j (`PANGLOSS_TEST_BACKEND=neo4j`), on two workers with a Neo4j each (7693, 7721). (Not at the same time
#      as the Memgraph ones: Docker's memory would not hold them all);
#   3. the end-to-end tests in a browser (e2e/), on four workers, each with its own project, servers and Memgraph (as the
#      first run has them: they are wiped); `test_changed_project.py`, on the test Neo4j, and `test_dev_mode.py`, with
#      the development server, each on one worker.
#
#   ./run_tests.sh                run everything
#   ./run_tests.sh --no-neo4j     skip the Neo4j tests (no Neo4j image needed)
#   ./run_tests.sh --no-e2e       skip the browser tests (no browser needed)
#   ./run_tests.sh -k typology    other arguments go to one pytest run of all of `packages/` (the Neo4j package too),
#                                 on the one test database, its tests one after the other (as `uv run pytest -n auto`
#                                 runs them by hand), and nothing else: the second and third runs are skipped, as they
#                                 are not what was asked for; to run only one of them:
#                                     uv run pytest packages/pangloss-neo4j
#                                     uv run pytest e2e
#
# The browser tests need Chromium once: uv run playwright install chromium
# The Neo4j tests start `neo4j:2026.10.1` themselves (ports 7693, 7694 and 7721) if Docker is running; without it they are skipped.
# A run that was killed can leave the databases it started: `docker rm -f $(docker ps -q --filter name=pangloss-test-)`.

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

# beside LABEL COMMAND...: starts the command in the background, its output kept for `shown`
outputs=$(mktemp -d)
trap 'rm -rf "$outputs"' EXIT
beside() {
    label=$1
    shift
    file="$outputs/$(printf '%s' "$label" | tr -c 'A-Za-z0-9' _)"
    printf '%s\n' "$label" > "$file.label"
    "$@" > "$file.out" 2>&1 &
    echo $! > "$file.pid"
}

# shown: waits for what `beside` started, and shows each one's output after the other
shown() {
    for pidfile in "$outputs"/*.pid; do
        [ -e "$pidfile" ] || continue
        file=${pidfile%.pid}
        wait "$(cat "$pidfile")" || status=$?
        echo
        echo "=== $(cat "$file.label")"
        cat "$file.out"
        rm -f "$pidfile"
    done
}

if [ -z "$args" ]; then
    # (formatting, and pyflakes: unused names, undefined names, names defined twice)
    run "ruff (format, pyflakes, bugbear)" sh -c 'uv run ruff format --check packages && uv run ruff check --select F,B packages'
    # (the static types, of the whole repository: what is relaxed, and where, is in `pyproject.toml`, `[tool.ty]`)
    run "ty" uv run ty check
    # (the skill that tells an agent how Pangloss works, `.claude/skills/pangloss`: the paths, modules and packages
    # it names are still there. What it says is kept true by hand, with the change that makes it untrue)
    run "the Pangloss skill" uv run python .claude/skills/pangloss/scripts/check_skill.py
    # (the type stubs that the packages ship of their own models, `pangloss_dates/models.pyi`: they are what would
    # be written now. After changing a model of a package: uv run python -m pangloss_testing.framework_stubs)
    run "the stubs of the packages' models" uv run python -m pangloss_testing.framework_stubs --check
    # (everything but the Neo4j package, which has a run of its own: what needs no database on every core, at the
    # same time as what does, a Memgraph for each worker)
    beside "packages, without a database" uv run pytest --dist=loadgroup -n auto --ignore=packages/pangloss-neo4j -m "not database"
    if [ "$neo4j" = yes ]; then
        beside "pangloss-neo4j" uv run pytest packages/pangloss-neo4j
    fi
    run "packages, on Memgraph (four workers, a database each)" env PANGLOSS_TEST_DATABASE_PER_WORKER=1 \
        uv run pytest --dist=loadgroup -n 4 --ignore=packages/pangloss-neo4j -m database
    shown
else
    run "packages ($args )" uv run pytest --dist=loadgroup -n auto $args
fi

if [ "$neo4j" = yes ]; then
    run "conformance and the add-ons' live tests on Neo4j (two workers, a database each)" \
        env PANGLOSS_TEST_BACKEND=neo4j PANGLOSS_TEST_DATABASE_PER_WORKER=1 uv run pytest --dist=loadgroup -n 2 \
        packages/pangloss-testing/src/pangloss_testing/conformance \
        packages/pangloss-typology/tests/live packages/pangloss-calendar/tests/live packages/pangloss-dates/tests/live \
        packages/pangloss-zotero/tests/live packages/pangloss-rdf/tests/live
fi

if [ "$e2e" = yes ]; then
    run "e2e (browser, four workers)" env PANGLOSS_TEST_DATABASE_PER_WORKER=1 uv run pytest e2e -n 4 --dist=loadgroup \
        --tracing retain-on-failure --screenshot only-on-failure
fi

exit $status
