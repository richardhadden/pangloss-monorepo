"""The TypeScript types of the search patterns of the models (`LetterWhere`, `SearchOf<"Letter">`): made for the
kitchen-sink models, and checked with `tsc` against a file that uses them, rightly and (`@ts-expect-error`)
wrongly. They need Node and the packages installed in `js/`, as `test_javascript.py` does."""

import shutil
import subprocess
import sys
from pathlib import Path

import pangloss_interface
import pytest
from pangloss_core import settings as core_settings
from pangloss_core.settings import ClientSettings
from pangloss_interface.meta import export_definitions
from pangloss_interface.typescript import models_module
from pangloss_models import initialise
from pangloss_models.model_registry import ModelRegistry

JS = Path(pangloss_interface.__file__).parent / "js"
SUPPORT = Path(__file__).parents[2] / "pangloss-models/tests/support"

pytestmark = [
    pytest.mark.skipif(shutil.which("npm") is None, reason="npm is not installed"),
    pytest.mark.skipif(
        not (JS / "node_modules").is_dir(),
        reason=f"the packages are not installed: npm install in {JS}",
    ),
    pytest.mark.xdist_group("javascript"),
]

USAGE = """
import { searchItems, type ApiClient } from "@pangloss/interface-core";
import type { PersonWhere, SearchOf, Wheres } from "./models";

declare const client: ApiClient;

const person: SearchOf<"Person"> = {
  type: "Person",
  where: {
    aliases: { contains: "x" },
    nickname: { starts_with: "a", exists: true },
    born: { type: "Date" },
    $any_of: [{ label: { eq: "a" } }, { note: { in: ["b"] } }],
    $not: { nickname: { eq: null } },
    $incoming: [{ type: "Factoid", field: "statements" }],
  },
  orderBy: [{ field: "nickname", direction: "desc" }, { field: "label" }],
};
void searchItems(client, person);

const source: SearchOf<"Source"> = {
  type: "Source",
  where: { written: { lt: "1600-01-01" }, edition_price: { between: [1, "2.50"] } },
};
void searchItems(client, source);

const factoid: Wheres["Factoid"] = {
  year: { gte: 800 },
  statements: { type: "Activity", where: { year: { lt: 900 } } },
  $mentions: { is: "0194a1b2-0000-7000-8000-000000000001" },
};
void factoid;

// @ts-expect-error a field that is not there
const a: PersonWhere = { nonsense: { eq: "a" } };
// @ts-expect-error an operator that the field does not take
const b: PersonWhere = { nickname: { gt: "a" } };
// @ts-expect-error a value of the wrong type
const c: Wheres["Source"] = { written: { lt: 1600 } };
// @ts-expect-error not a field to order by
const d: SearchOf<"Person"> = { type: "Person", orderBy: [{ field: "aliases" }] };
// @ts-expect-error a relation to a class it cannot point at
const e: Wheres["Factoid"] = { statements: { type: "Person" } };
// @ts-expect-error the combinators are of the same model
const f: PersonWhere = { $any_of: [{ year: { eq: 1 } }] };
void [a, b, c, d, e, f];
"""


@pytest.fixture
def exported():
    saved = core_settings.__dict__.get("SETTINGS")
    ClientSettings(INSTALLED_APPS=[], STORAGE="pangloss_sdk.storage:api")
    ModelRegistry._reset()
    sys.path.insert(0, str(SUPPORT))
    try:
        import kitchen_sink

        kitchen_sink.declare()
        initialise()
        yield export_definitions()
    finally:
        sys.path.remove(str(SUPPORT))
        sys.modules.pop("kitchen_sink", None)
        ModelRegistry._reset()
        if saved is None:
            core_settings.__dict__.pop("SETTINGS", None)
        else:
            core_settings.SETTINGS = saved


def test_the_search_patterns_of_the_models_are_exported(exported):
    patterns = exported["searchPatterns"]
    person = patterns["Person"]
    assert person["kind"] == "entity"
    assert person["fields"]["aliases"] == {
        "operators": "items",
        "value": {"type": "str"},
    }
    assert person["fields"]["born"]["operators"] == "relation"
    assert "Date" in person["fields"]["born"]["targets"]
    assert person["orderBy"][0] == "label"
    assert patterns["Date"]["kind"] == "embedded" and patterns["Date"]["orderBy"] == []
    assert patterns["Source"]["fields"]["edition_price"]["value"] == {"type": "decimal"}


def test_the_types_of_the_patterns_type_check_and_refuse_what_is_wrong(
    exported, tmp_path
):
    # (in the workspace, so that `@pangloss/interface-core` is found; removed after)
    directory = JS / f".search-types-check-{tmp_path.name}"
    directory.mkdir()
    try:
        (directory / "models.ts").write_text(models_module(exported))
        (directory / "usage.ts").write_text(USAGE)
        (directory / "tsconfig.json").write_text(
            '{"extends": "../tsconfig.base.json", "include": ["*.ts"]}\n'
        )
        result = subprocess.run(
            [str(JS / "node_modules/.bin/tsc"), "-p", str(directory)],
            capture_output=True,
            text=True,
            timeout=300,
        )
        assert result.returncode == 0, (result.stdout + result.stderr)[-3000:]
    finally:
        shutil.rmtree(directory)
