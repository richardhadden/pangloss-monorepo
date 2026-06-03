#! sh

uv run --package pangloss-memgraph pytest packages/pangloss-memgraph
uv run --package pangloss-models pytest -n auto packages/pangloss-models
