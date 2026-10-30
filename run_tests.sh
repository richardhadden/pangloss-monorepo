#! /bin/sh
# Everything, in three runs:
#
#   1. the unit and integration tests of the packages (in parallel), with the Memgraph in Docker;
#   2. the tests of `pangloss-neo4j`, against a Neo4j in Docker. (Its own run: it has its own database and its own
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

if [ -z "$args" ]; then
    # (everything: the Neo4j package has a run of its own)
    uv run pytest --dist=loadgroup -n auto --ignore=packages/pangloss-neo4j
else
    uv run pytest --dist=loadgroup -n auto $args
fi
status=$?

if [ "$neo4j" = yes ]; then
    uv run pytest packages/pangloss-neo4j || status=$?
    for package in typology calendar dates zotero; do
        PANGLOSS_TEST_BACKEND=neo4j uv run pytest "packages/pangloss-$package/tests/live" || status=$?
    done
fi

if [ "$e2e" = yes ]; then
    uv run pytest e2e --tracing retain-on-failure --screenshot only-on-failure || status=$?
fi
exit $status
