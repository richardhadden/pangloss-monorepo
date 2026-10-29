#! /bin/sh
# Everything: the unit and integration tests (in parallel), then the end-to-end tests in a browser (e2e/, one process:
# they share the test Memgraph, which the first run wipes, so they cannot run at the same time).
#
#   ./run_tests.sh                run everything
#   ./run_tests.sh --no-e2e       skip the browser tests (no browser needed)
#   ./run_tests.sh -k typology    other arguments go to the first pytest run (and the e2e run is skipped, as it is not
#                                 what was asked for); to run only the browser tests: uv run pytest e2e
#
# The browser tests need Chromium once: uv run playwright install chromium

e2e=yes
args=""
for arg in "$@"; do
    if [ "$arg" = "--no-e2e" ]; then
        e2e=no
    else
        args="$args $arg"
        e2e=no
    fi
done
# (--no-e2e alone, or nothing, is the only case that asks for everything)
if [ "$#" -eq 0 ]; then e2e=yes; fi

uv run pytest --dist=loadgroup -n auto $args
status=$?

if [ "$e2e" = yes ]; then
    uv run pytest e2e || status=$?
fi
exit $status
