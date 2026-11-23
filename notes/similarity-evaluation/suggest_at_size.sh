#!/bin/bash
# Step 10.5c: `planted.py suggest` at size, tried until the database answers (a large container needs minutes
# after `docker start`). Usage: suggest_at_size.sh memgraph bolt://localhost:7706
cd "$(dirname "$0")/../.."
for i in $(seq 1 15); do
  out=$(timeout 3000 uv run python notes/similarity-evaluation/planted.py suggest "$1" "$2" --dated --sample 800 --learn-from 100 --profiles '{"who": {"name": 1, "graph": 0.25}}' 2>&1)
  if echo "$out" | grep -q "decisions kept"; then echo "$out" | tail -56; exit 0; fi
  echo "try $i: $(echo "$out" | tail -1 | cut -c1-300)"
  sleep 60
done
