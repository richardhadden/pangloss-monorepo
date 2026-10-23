#!/usr/bin/env bash
# Run sdk_demo.py as a client: a new environment with only the SDK in it.
#
#   PANGLOSS_URL=http://127.0.0.1:8765 PANGLOSS_USERNAME=admin PANGLOSS_PASSWORD=... ./run.sh [--keep]
#
# The server (`pangloss run` in pangloss-demo) must be running, and the user an admin
# (the SDK is for admins unless SDK_ACCESS says otherwise).
set -euo pipefail

here="$(cd "$(dirname "$0")" && pwd)"
root="$(cd "$here/.." && pwd)"
url="${PANGLOSS_URL:-http://127.0.0.1:8765}"
: "${PANGLOSS_USERNAME:?set PANGLOSS_USERNAME (an admin)}"
: "${PANGLOSS_PASSWORD:?set PANGLOSS_PASSWORD}"

work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT

echo "== a new environment: pangloss-sdk and what it needs, nothing else"
uv venv --quiet --python 3.15 "$work/venv"
python="$work/venv/bin/python"
uv pip install --quiet --python "$python" \
    "$root/packages/pangloss-core" "$root/packages/pangloss-models" "$root/packages/pangloss-sdk"

echo "== the SDK: git clone from the server, then install the clone"
# (git asks for the username and password: they are answered from the environment, by a
# helper, so that neither is in the URL or in the process list. A personal access token does
# as the password too.)
cat > "$work/askpass" <<'ASK'
#!/usr/bin/env bash
case "$1" in
    Username*) printf '%s\n' "$PANGLOSS_USERNAME" ;;
    *) printf '%s\n' "$PANGLOSS_PASSWORD" ;;
esac
ASK
chmod +x "$work/askpass"
GIT_ASKPASS="$work/askpass" GIT_TERMINAL_PROMPT=0 git -c credential.helper= clone --quiet "$url/api/sdk/git" "$work/sdk"
git -C "$work/sdk" log --oneline --decorate | head -3
uv pip install --quiet --python "$python" "$work/sdk"

echo "== what is installed here"
uv pip list --python "$python" 2>/dev/null | grep -i -E "pangloss|demo|neo4j|fastapi" || true

echo "== the demo"
PANGLOSS_URL="$url" "$python" "$here/sdk_demo.py" "$@"
