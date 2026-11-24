#!/bin/bash
# Step 10.5g: the worker that suggests at size. `planted.py rebuild --worker-models` (the vectors made again for the
# models the worker is measured on), then `planted.py worker`, as the figures of planted_worker_{memgraph,neo4j}.txt
# were made. Each waits while a test run is going (another builder's tests skew every time), and the rebuild is tried
# until the database answers (a large container needs minutes after `docker start`).
# Usage: worker_at_size.sh memgraph bolt://localhost:7706     (or neo4j bolt://localhost:7707)
#   RESUME=1 worker_at_size.sh ...   no rebuild, and `worker --resume`: goes on after the last phase kept
cd "$(dirname "$0")/../.."
PROFILES='{"who": {"name": 1, "graph": 0.25}}'
STATE="${STATE:-/tmp/planted_worker_$1.json}"
quiet() {
  while pgrep -f "[b]in/pytest" > /dev/null; do echo "(a test run is going: waiting)"; sleep 60; done
}
if [ -z "$RESUME" ]; then
  rm -f "$STATE"
  for i in $(seq 1 15); do
    quiet
    out=$(uv run python notes/similarity-evaluation/planted.py rebuild "$1" "$2" --dated --worker-models --profiles "$PROFILES" 2>&1)
    if echo "$out" | grep -q "rebuild:"; then echo "$out" | grep -v "^\s*$"; break; fi
    echo "try $i: $(echo "$out" | tail -1 | cut -c1-300)"
    sleep 60
  done
fi
uv run python notes/similarity-evaluation/planted.py worker "$1" "$2" --dated --profiles "$PROFILES" --state "$STATE" ${RESUME:+--resume} 2>&1
