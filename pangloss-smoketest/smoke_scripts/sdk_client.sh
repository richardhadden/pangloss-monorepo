#!/usr/bin/env bash
# The project's SDK as a client has it: a new environment with `pangloss-sdk`, the packages the models import (without
# what those need on a server) and the SDK cloned from the running API; then `sdk_client.py`.
#
#   ../.venv/bin/pangloss sdk build && ../.venv/bin/pangloss run --port 8010 &
#   smoke_scripts/sdk_client.sh
set -euo pipefail

here="$(cd "$(dirname "$0")" && pwd)"
root="$(cd "$here/../.." && pwd)"
url="${PANGLOSS_URL:-http://localhost:8010}"
# shellcheck disable=SC1091
source "$here/.secrets"

work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT

uv venv --quiet --python 3.15 "$work/venv"
python="$work/venv/bin/python"
uv pip install --quiet --python "$python" \
    "$root/packages/pangloss-core" "$root/packages/pangloss-models" "$root/packages/pangloss-sdk"
# (the packages whose models the project's are built on. Their distributions also name what they need on a server,
# FastAPI and the API: a client needs none of it, so they are installed alone)
uv pip install --quiet --python "$python" --no-deps \
    "$root/packages/pangloss-dates" "$root/packages/pangloss-calendar" "$root/packages/pangloss-typology" \
    "$root/packages/pangloss-review" "$root/packages/pangloss-derived" "$root/packages/pangloss-library" \
    "$root/packages/pangloss-zotero"

cat > "$work/askpass" <<'ASK'
#!/usr/bin/env bash
case "$1" in
    Username*) printf 'importer\n' ;;
    *) printf '%s\n' "$PANGLOSS_TOKEN" ;;
esac
ASK
chmod +x "$work/askpass"
PANGLOSS_TOKEN="$PANGLOSS_TOKEN" GIT_ASKPASS="$work/askpass" GIT_TERMINAL_PROMPT=0 \
    git -c credential.helper= clone --quiet "$url/api/sdk/git" "$work/sdk"
git -C "$work/sdk" log --oneline --decorate | head -2
uv pip install --quiet --python "$python" "$work/sdk"

uv pip list --python "$python" 2>/dev/null | grep -i -E "pangloss|smoke|neo4j|fastapi|typer|starlette" || true
cd "$work" && PANGLOSS_URL="$url" PANGLOSS_TOKEN="$PANGLOSS_TOKEN" "$python" "$here/sdk_client.py"
