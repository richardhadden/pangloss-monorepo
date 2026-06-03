#! sh
uv run --package pangloss-models pytest -n auto packages/pangloss-models
uv run --package pangloss-memgraph pytest packages/pangloss-memgraph
