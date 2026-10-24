"""The models that `initialise()` makes, compared with a stored snapshot.

This is a characterisation test: `kitchen_sink.declare()` makes models of every kind, the
initialisation is run, and everything it made (the fields of each generated model with their
annotations, defaults, aliases and discriminators; the field definitions they were made from; the
incoming relations) is described as data (`snapshot_support.py`) and compared with
`snapshots/generated_models.json`.

It does not say the snapshot is *right*, only that it has not changed. So it is what allows the
code that makes the models to be restructured: if the snapshot is the same, the same models are made.
When a change is meant, look at the difference it reports, then write the new snapshot:

    UPDATE_SNAPSHOTS=1 uv run pytest packages/pangloss-models/tests/generated_models/test_generated_models_snapshot.py

and commit it with the reason. (The snapshot is the same whatever `PYTHONHASHSEED` is: unions, sets and
the names of generated classes are put in order. If it is ever not, that is a bug in the describing.)
"""

import difflib
import json
import os
from pathlib import Path

import kitchen_sink
import pytest
import snapshot_support
from pangloss_models import initialise
from pangloss_models.model_registry import ModelRegistry

SNAPSHOT = Path(__file__).parent / "snapshots" / "generated_models.json"


def make_snapshot() -> dict:
    kitchen_sink.declare()
    initialise()
    return snapshot_support.snapshot_registry()


def report(expected: dict, actual: dict) -> str:
    lines = []
    for section in ("declared", "generated"):
        old, new = expected[section], actual[section]
        for name in sorted(set(old) - set(new)):
            lines.append(f"{section}: missing now: {name}")
        for name in sorted(set(new) - set(old)):
            lines.append(f"{section}: new: {name}")
        for name in sorted(set(old) & set(new)):
            if old[name] != new[name]:
                before = json.dumps(old[name], indent=1, sort_keys=True).splitlines()
                after = json.dumps(new[name], indent=1, sort_keys=True).splitlines()
                diff = list(
                    difflib.unified_diff(
                        before, after, "stored", "now", lineterm="", n=1
                    )
                )
                lines.append(f"{section}: changed: {name}")
                lines.extend("    " + line for line in diff[2:22])
                if len(diff) > 22:
                    lines.append(f"    ... {len(diff) - 22} more lines")
    return "\n".join(lines[:200])


def test_generated_models_match_the_snapshot():
    actual = json.loads(snapshot_support.dumps(make_snapshot()))

    if os.environ.get("UPDATE_SNAPSHOTS"):
        SNAPSHOT.write_text(snapshot_support.dumps(actual))
        pytest.skip(f"snapshot written to {SNAPSHOT}")

    assert SNAPSHOT.exists(), (
        f"no snapshot: run once with UPDATE_SNAPSHOTS=1 to write {SNAPSHOT}"
    )
    expected = json.loads(SNAPSHOT.read_text())
    if expected != actual:
        pytest.fail(
            "the generated models have changed:\n" + report(expected, actual),
            pytrace=False,
        )


def test_the_snapshot_covers_every_kind_of_model():
    """The snapshot is only as good as what is in it: every kind of model, and every generated model,
    must be there"""
    actual = snapshot_support.dumps(make_snapshot())
    snapshot = json.loads(actual)
    kinds = [d["kind"] for d in snapshot["declared"].values()]
    assert {
        "AnnotatedValue",
        "Conjunction",
        "Document",
        "EdgeModel",
        "Embedded",
        "Entity",
        "ReifiedRelation",
        "ReifiedRelationDocument",
        "SemanticSpace",
    } <= set(kinds)
    assert None in kinds  # (a Trait has no kind of its own)

    owned = {key.split(".")[-1] for key in snapshot["generated"] if "." in key}
    assert set(snapshot_support.GENERATED) <= owned


def test_initialising_twice_in_one_process_gives_the_same_snapshot():
    """State must not leak from one registry to the next (the models are re-made for every test)"""
    first = snapshot_support.dumps(make_snapshot())
    ModelRegistry._reset()
    second = snapshot_support.dumps(make_snapshot())
    assert first == second
