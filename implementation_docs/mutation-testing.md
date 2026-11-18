# Mutation testing 🚧

Written 2026-11-18. What mutation testing has been run on, what it found, what was done about it, how to run it
again, and what to check next. The work is on branch `mutmut-test`.

## Contents

- In short
- What it is, and what the numbers mean
- How to run it
- pangloss-dates
- pangloss-models: search checking and label templates
- pangloss-cypher: the write plan, build_tree, fragments
- pangloss-models: literals, merging, write checks, citations
- pangloss-models: migrations
- pangloss-models: search checking, second round
- pangloss-history
- pangloss-derived: checking rules
- pangloss-rdf
- Traps
- What is left in the two modules
- What to check next

## In short

| Module | Mutants | Survived before | Survived after | Score after | Run time |
|---|---|---|---|---|---|
| pangloss-dates (pure modules) | 1626 | 125 | 26 | 98.4% | ~1 min |
| pangloss-models `search.py`, `search_where.py`, `label_templates.py` | 3427 | 789 | 507 | ~84% | ~7 min |
| pangloss-cypher `write_plan.py`, `build_tree.py`, `fragments.py` | 651 | 194 | 20 | 97% | ~10 s |
| pangloss-models `literals.py`, `merging.py`, `write_checks.py`, `citations.py` | 1283 | 229 (+413 with no test) | 132 (+36) | 87% | ~4 min |
| pangloss-models `migrations/` (diff, changes, planner, reverse, affected, state) | 3972 | 926 | 565 | 85% | ~5 min |
| pangloss-models search, second round | 3410 | 500 | 412 | 87% | ~8 min |
| pangloss-history `upgrade`, `diff`, `draft`, `summary`, `view`, `restore`, `store` | 1689 | 312 | 242 | 84% | ~1 min |
| pangloss-derived `check`, `compile`, `declare` | 2431 | 883 | 431 | 80% | ~3 h (with the documents tests) |
| pangloss-rdf `convert`, `uris`, `literals`, `ontology`, `resolve`, `negotiate`, `terms`, `fields` | 2009 | 74 | (tests added after) | 96% | ~40 min |

- In **pangloss-dates** the arithmetic was mostly well tested, but by samples. Two slips that are wrong in only a
  few years or days would have passed: one in Gregorian Easter (9 years in 14,800) and one in `from_jdn` (37 days,
  28 February in century years before 1 AD). Every year is now checked. A wrong plural ("Easter + 1 days") was
  found and fixed.
- In **pangloss-models** the checking of search patterns had real gaps:
  - None of the limits that keep a search of a client small was tested at its edge. A mutant that reset the
    count of conditions survived.
  - A field after `$all`, `$any_of` or `$not` could be skipped without a test failing.
  - `$incoming` had no unit test, and has no conformance test against a database.

  Running the live conformance tests of search as well killed only about 13 more mutants, so these gaps are not
  covered elsewhere.
- In the **later modules** (all with no database):
  - **A bug in pangloss-history:** the upgrade of a stored version compared each value's class with
    `AlterRelationTarget.removed`, which the planner writes as option keys (`entity:Person`). Nothing ever matched:
    a version referring to a class a relation can no longer be to was restored with no problem reported. Its unit
    tests built the change by hand, with plain class names. Fixed (commit `c60530bc`).
  - **A bug:** `WithCertainty[str] | None` crashed `initialise()` with a `TypeError` (`AnnotatedValueFieldDefinition`
    has no `optional`). It is now refused with a `PanglossModelError` that says what to write instead.
  - **A wrong message:** `list[str | None]` was told to write `` `list | None` ``. It now says `` `list[str] | None` ``.
  - **A reversal was checked only on the models' state**, which ignores much of what the data operations use. The
    migration tests now check that undoing the undoing gives back the changes found.
  - **Duplicated code:** the export described literal types itself, in parallel with `literals.export_type`. It now
    calls it, and the demo's export is unchanged byte for byte.
  - **Dead code:** a parameter that was always `True`, a field always `False`, an unused argument passed through
    three functions, a list computed and thrown away.
  - The write plan, the JSON of merges, `@before_create`/`@before_update`, the ownership of a migration's changes
    and what is read after one had no unit tests. They were reached only through the live tests, or not at all.
- **Refusal tests that do not match the message hide missing checks.** Several cases were refused by an earlier
  check, not the one they were meant to test. The refusal tests of both modules now match the message.

## What it is, and what the numbers mean

A tool makes many small changes to the code (a *mutant* each: `>` to `>=`, `and` to `or`, `+ 1` to `+ 2`, a
`continue` to a `break`, an argument to `None`) and runs the tests against each.

- **Killed:** a test failed. The tests would notice that mistake.
- **Survived:** every test passed. No test checks that behaviour.
- **No tests:** no test that was run reaches the code. Here that is usually code tested by another package's tests,
  which were not in the run.

A survivor is one of three things:

- **A real gap:** worth a test.
- **Equivalent:** the change makes no difference to any input (`(x - 15) % 30` and `(x + 15) % 30`). Nothing to do.
- **Wording only:** the text of an error message. Worth catching only where the message is what a user reads, or
  where matching it is what proves the right check refused.

Line coverage says the code ran. Mutation testing says whether a test would notice it being wrong.

## How to run it

The tool is **mutmut 3.8.1**, installed into `.venv` only (`uv pip install --python .venv/bin/python mutmut`). It is
not in any `pyproject.toml`, so `uv sync` removes it. It runs on Python 3.15 (it needs `libcst`, which has wheels).

Each package mutated has an untracked `setup.cfg` with its configuration (pangloss-dates, pangloss-models,
pangloss-cypher). The one of pangloss-models is changed for each group of modules: the groups are below. Run from the package's directory:

```
rm -rf mutants
../../.venv/bin/mutmut run --max-children 8
../../.venv/bin/mutmut results          # the mutants and what became of each
../../.venv/bin/mutmut show <name>      # the change a mutant made
../../.venv/bin/mutmut browse           # all of it, interactively
```

mutmut copies the package into `mutants/`, changes the copy, and runs pytest there. **Delete `mutants/` before
running `run_tests.sh`.** ruff and ty would check the mutated copy and fail.

The configuration of pangloss-dates:

```ini
[mutmut]
paths_to_mutate=
    src/pangloss_dates/julian.py
    src/pangloss_dates/gregorian.py
    src/pangloss_dates/easter.py
    src/pangloss_dates/bounds.py
    src/pangloss_dates/calendar.py
    src/pangloss_dates/recurrence.py
    src/pangloss_dates/edtf.py
    src/pangloss_dates/labels.py
tests_dir=tests
pytest_add_cli_args=--ignore=tests/live -p no:cacheprovider -q
also_copy=
    src
```

The configuration of pangloss-models:

```ini
[mutmut]
paths_to_mutate=
    src/pangloss_models/search.py
    src/pangloss_models/search_where.py
    src/pangloss_models/label_templates.py
tests_dir=
    tests/test_search_match.py
    tests/test_search_through.py
    tests/test_search_where.py
    tests/test_search_where_models.py
    tests/test_label_templates.py
    tests/test_search_incoming.py
pytest_add_cli_args=-p no:cacheprovider -q
also_copy=
    src
```

**With tests that need a database.** mutmut does not take a test file by its absolute path (the test ids come out
as `::test_...` and the run stops at once). To run conformance tests, re-export them from a folder in the package.
The scratch folder `packages/pangloss-models/mm_live/` (untracked) has a `conftest.py` with
`from pangloss_testing.conformance.conftest import *` and, for each test file, a `test_mm_<name>.py` with
`from pangloss_testing.conformance.test_<name> import *`. Add `mm_live` to `also_copy` and the files to `tests_dir`.

All mutants then share the one test database, so they must run one at a time (`--max-children 1`). That took an hour
for the 3427 mutants of pangloss-models. Nothing else may use `:7687` meanwhile: no database tests and no e2e.

**The TypeScript side.** The tests of an interface module (`pangloss_dates/interface`) have no `node_modules` of their
own. Copy the module to a scratch folder, symlink `node_modules` to `pangloss-demo/.pangloss/interface/node_modules`,
and run `./node_modules/.bin/vitest run` and `./node_modules/.bin/tsc --noEmit -p tsconfig.json` there. Stryker,
the mutation tool for TypeScript, has not been tried.

**Sorting the survivors.** Hundreds of survivors cannot be read one by one. A short script (it was in `/tmp`, not
kept) dumped `mutmut show` for each survivor and sorted them into wording-only changes (only a string literal
differs) and changes of logic, counted by function. That gives the list to work through.

## pangloss-dates

Mutated: `julian`, `gregorian`, `easter`, `bounds`, `calendar`, `recurrence`, `edtf`, `labels`, against the 219 tests
that need no database (under a second). Left out: `models`, `dateable`, `rules`, `query` (slow, or need the database).

Found, and now tested:

- **Gregorian Easter** (`easter.py`): `// 451` → `// 452` is wrong in 9 years of the range (−3770, −3743, …, 3165).
  Now checked against Knuth's method (*The Art of Computer Programming*, 1.3.2, exercise 14) in every year from
  −4799 to 9999. The two are worked out differently and agree in every year.
- **`from_jdn`** (`calendar.py`): `274277` → `274278` is wrong on 37 days (28 February read as 29 in century years
  such as −4700). The round trip was sampled every 997 days. Now 1 January, 28 February, the last day of February,
  1 March and 31 December of every year are checked, in both calendars, in under a second.
- **`Bounds.contains`**: neither end was tested as inside.
- **Recurrence:**
  - Every test used `interval=2`, which cannot tell `year - anchor` from `year + anchor`. Now intervals of 3 and 5.
  - The anchor's year and month are read in the rule's calendar (1 January 1501 Gregorian is still 1500 in the
    Julian).
  - The weeks counted from the end of a month count in its own calendar (Julian February 1500 has 29 days).
  - The ends of the accepted ranges (`month=12`, `nth=±5`, `leap_shift` on the 28th).
  - A rule on Easter with weekdays was never refused for that reason.
- **EDTF:**
  - What is not read: negative years with unspecified digits, open-ended sets, Level 2 seasons.
  - Level 2 intervals.
  - The precision of unspecified digits and of sets, and `uncertain` on a set.
  - Padding carried into the members of a set and the ends of an interval.
  - The error for an interval with a day its calendar does not have.
- **Labels:**
  - Plurals ("every 2 weeks"), negative Easter offsets, lists of weekdays.
  - A month alone, values out of range, a recurrence that names no day.
  - The same cases are in `interface/src/format.test.ts` (the two are kept in step by hand), and both give the
    same.
- **Fixed:** "Easter + 1 days" is now "Easter + 1 day", in Python and in the interface. There is a new key,
  `date_from_easter_one_day`, in en/de/fr, as `date_unit_week`/`date_unit_weeks` are kept apart.

The 26 left:

- About 10 are wording only.
- About 8 are equivalent. For example `n >= 0` in `nth_weekday`, where 0 is refused first; `(b + 9) // 25` in
  Easter, which gives the same Easter in every year of the range; `getattr(x, "negative", True)` where the
  attribute is always there.
- About 8 are code that cannot be reached. python-edtf 5 parses `15XX-03` and `1500-XX-03` as
  `PartialUnspecified`, so two branches of `_unspecified` and the empty-set check never run. They are kept, in case
  a later python-edtf parses these forms differently.

## pangloss-models: search checking and label templates

Mutated: `search.py` (the checking of a search pattern against the models: what keeps names that are not fields
of the models out of the Cypher text), `search_where.py` (the `Where` classes and what the interface is told of
patterns), `label_templates.py`. They were run against the five search and label test files, which take under 5
seconds together.

| Run | Tests | Killed | Survived | No tests |
|---|---|---|---|---|
| 1 | the unit tests | 2409 | 789 | 224 |
| 2 | and the live conformance tests of search and label templates | 2434 | 776 | 212 |
| 4 | the unit tests, with the new tests | 2696 | 507 | 217 |

767 of the 776 survivors of run 2 had survived run 1. The live tests do not cover these gaps.

Found, and now tested (commit `c565fd10`):

- **The limits, on both sides of each:**
  - nesting depth (`MAX_DEPTH` 50, counted through `$not`, `$all` and `$any_of`);
  - the lists of `$all`, `$any_of`, `$somewhere` and `$incoming` (one to `MAX_VALUES` 100);
  - `$spaces`;
  - fields in one pattern (`MAX_CONDITIONS` 20);
  - conditions in a whole search (`MAX_EXPRESSIONS` 500);
  - patterns for what a relation points at (`MAX_PATTERNS` 50).

  The conditions of a step of `through` count as conditions; only an edge counts as a pattern.
- **Fields after a combinator:** `continue` → `break` after `$all`, `$any_of` or `$not` survived. Such a field would
  have been left out of the search. Now each combinator is followed by a field that must be checked.
- **Where a field is named:** a field inside `$all`, `$any_of` or `$not` is named as it is in the error. The head
  properties (`published`, `review_status`) can be asked inside a combinator.
- **`$incoming`** (new file `tests/test_search_incoming.py`):
  - what it is checked to;
  - by any relation that can point at the entity, or by one;
  - an abstract class by the relations of its kinds;
  - wrapped or not, and `through`;
  - each refusal, with its message;
  - the limit.
- **Values:**
  - `starts_with` is lowercased (`.lower()` → `.upper()` survived);
  - `contains` needs text;
  - a bad value, or an empty or too long list, is named where it is (`pages.in`, `sender.is_any`);
  - the items of a `list[Decimal]` are compared as floats.
- **Relations:** every checked condition of a relation names its field and carries `through` and the steps;
  `$any` can pass through wrappers.
- **`export_search_patterns`** (what the interface makes its TypeScript types of patterns from) is compared exactly
  for a small set of models, and the yes-or-no keys an app adds (`flag`, `offered_for`) are named for the right
  classes.
- **Label templates:**
  - each filter, and each on nothing;
  - values as text (whole floats as JavaScript writes them, true/false, an annotated `{value, certainty}`);
  - a written label before what a thing holds;
  - a reified relation without a template as what it holds;
  - formatters (registered, missing, giving nothing);
  - escapes, inside and outside the text of a filter;
  - more templates that cannot be read;
  - `LabelTemplate()` and `Formatter("bad")` refused;
  - a root that looks like a reference is still worked out;
  - the schema made again for other models and kept for the same;
  - the path of a nested label that its template gives nothing for.

## pangloss-cypher: the write plan, build_tree, fragments

Mutated: `write_plan.py`, `build_tree.py`, `fragments.py`, against their three test files (0.5 s). Commit `6d5f18b2`.

Found, and now tested:

- **The write plan:**
  - embedded objects;
  - annotated values (one, and a list);
  - generic wrappers whose type variable the field gives (`Proxy[Place] | Identification[Person]`);
  - `KeepOnMerge` on a reference and on an entity written in a document;
  - the `meta` of a nested node (who made it, who updated it, when, kept on an update);
  - what installed apps put on a new head node, with the review status the document asks for;
  - an entity's URLs, in order;
  - a reference matched once but checked each time;
  - an entity's own tree, written only where it is new.
- **`build_tree`:** the order of a list by `pg_position`, and `GraphFragment`.
- **`fragments`:** the conditions that installed apps add (`counted`, `counted_edge`), `listed` and `only_used`.

Removed, as dead code: the `is_new` parameter (always true), `NodeToWrite.is_entity` (always false), and the edge
properties of an embedded object (it has no edge model).

The 20 left: `getattr` defaults, `typing.cast`, and one that depends on the order of a set (`resolve_type_var_options`).
The Cypher text of `fragments` is checked only by the live tests.

## pangloss-models: literals, merging, write checks, citations

Mutated: `literals.py`, `merging.py`, `write_checks.py`, `citations.py`, against `tests/initialisation`,
`tests/migrations`, `tests/export` and the files of the three others. Commits `f5be137b`, `aad02278`, `bff823ae`.

- **Literals:**
  - `codec_for_value` is exact for the natives (a `ByteSize` is stored as an `int`; a date is not taken by the
    decimal's codec);
  - a package's codec is asked first;
  - the refusals of `Literal[...]`;
  - `storage_descriptor` and `python_type_of_storage`.

  `Exporter.describe_type` was a second copy of `export_type`. It is now one function, given a callback for the
  enums it meets.
- **Merging:**
  - `to_wire` and `from_wire` had no test. They now go round for every result, with payloads in camelCase, payloads
    no longer of their class, and a wire without a field.
  - The label and lists of one side only, `DBField`s, what makes two items of a list the same (bare references,
    maps, wrappers, `meta`), abstract survivors, the order of the classes that are both.
  - `related` in `survivor_class` could not change the result, and is removed.
- **Write checks:** `nodes_of`, `check_before_create` and `check_before_update` with no database: the order, the
  previous version, where a refusal is, one read of the head.
- **Citations:** generic documents cited by their base, a citation with `protect = False`.

Left: mostly `getattr` defaults, and the field defaults of the citation node classes, which the live tests use.

## pangloss-models: migrations

Mutated: `diff`, `changes`, `planner`, `reverse`, `affected`, `state`, against `tests/migrations` (4 s). Commit
`0900eb35`.

- **The biggest gain was one check, not many tests.** `changes()` in `tests/support/migration_support.py` replays
  each change found, and its reversal, on the snapshot. The snapshot ignores much of what the database operations
  use, such as the labels an `AlterModelLabels` adds and removes, or the edges of an `AlterParentFields`. A reversal
  could get those wrong and pass. Now **undoing the undoing must give the changes found**, except for the answers a
  person gives (`default`, `keep`, `on_narrowing`), which a reversal fills with the careful choice.
- **Changes of a field:**
  - one annotated value or a list of them;
  - a list's items;
  - an embedded field's union and its `| None`;
  - literals moved into an embedded object only if they keep their type, and only from the same model.
- **Renames:** confirmed renames that no longer fit the models are left out (each kind).
- **Narrowed fields:** a field that another comes to narrow is absorbed; one no longer narrowed comes back.
- **What is read after a migration:** what holds an annotated value, a union of embedded objects or a wrapped
  document; the entities of each changed relation; hand-written steps that say what they touch.
- **The app a change belongs to:** `owner_of`, `structure_owner`, `app_of_module`.
- **Indexes and constraints in the state:** the snapshots of the tests have none.
- **Removed:** `uncovered_required` (computed and discarded), and an argument passed through three functions and
  never used.

Left, 565 (406 change logic):

- `_replace_back`, `_add_structure` and `_remove_structure` (52) are made when `INVERSES` and `HANDLERS` are built at
  import, so their mutants never take effect (see Traps).
- `planner.split_app` (22) and `split` (9): the two-step migrations of apps whose new models need each other.
- `affected_models` (24): mostly defaults of `.get`, and `continue` → `break` where only one change is given.
- The inverses of `RunCypher`, `RunPython` and `ChangeWrapper` (25): changes made by hand, which `changes()` never
  finds.
- The rest are wording, and `.get` defaults.

## pangloss-models: search checking, second round

Commit `a49052d6`. The `continue` → `break` gap of the first round was also after `$any`, `$mentions`, `$somewhere`,
`$incoming` and an app's key: a field after one of them is now checked in a test. Also: an app's key is given where
it is and refused for other kinds; `$spaces` accepted; the depth limit through `$all` and `$any_of` at its edge; the
fields an app adds to the `Where` classes; the message for a class that is never searched. New shared label cases
(Python and the interface's Vitest, which agree): paths through a reified relation and a semantic space, annotated
values. `parse_where` checked `isinstance(value, Condition)` before `Condition.model_validate`, which returns an
instance as it is: removed.

Left: mostly rule variables (`Var`, `$is`), tested in pangloss-derived.

## pangloss-history

Mutated: `upgrade`, `diff`, `draft`, `summary`, `view`, `restore`, `store`, against the tests that need no database
(0.1 s). Commits `c60530bc`, `6da6f032`.

- **The bug above** (narrowed relations). The upgrade now decides as the database's migration does: a value stays if
  one of its class's labels is among the classes the change's `options` allow.
- **The problems an upgrade reports were checked by kind and path only, on one node.** New tests use a document with
  nested nodes and a reference, and compare each problem whole (model, field, path, old value, message), for added,
  removed and narrowed fields, removed enum members, cardinality and type changes.
- `restore.merged_problems` and `migrations_after` with a squashed migration had no unit test.

Left: `view` (24), and the log lines of `apply_migrations`.

## pangloss-derived: checking rules

Mutated: `check.py`, `compile.py`, `declare.py`, against the tests that need no database. Commit `ceb8ec0f`.

- Without `test_derived_documents.py` (23 s, which makes the run take hours) 883 survived. With it, and the new
  tests, 431: the documents tests cover the sources and cycles of derived documents.
- **Each refusal of a rule now has a test with its whole message**: no head and body, an abstract class, no pattern,
  a variable not of the rule, a value of the wrong class in the head, a pattern that is no model's `Where` or cannot
  be read, a variable in no pattern, `unordered` of values or of one variable. Also the warning for a variable used
  once, and a body that is not the same swapped because of a filter on one end.
- **Dead code:** the refusal of a head relation given no variable could not be reached (`Derive` refuses it first, as
  "the head is not right"). Removed.

Left: `compile.py` (the Cypher of a rule, tested by the live tests) and wording.

## pangloss-rdf

Mutated: `convert`, `uris`, `literals`, `ontology`, `resolve`, `negotiate`, `terms`, `fields` (1.4 s of tests). Only 74
survived. The gaps were in the ontology: the properties of embedded objects, annotated values and maps (`TypedDict`,
and one inside another), a property's comment, and the ontology's own `versionInfo`; and a browser sent to the text
of the ontology and the dataset. Tests added.

## Traps

- **Code run when a module is imported** is invisible to mutmut, which switches a mutant on after the tests are
  collected. `RULES` in `test_dates_recurrence.py` is a list built at import, so the check of `nth=5` it made was
  never counted. Build the values at the edges inside a test.
- **The number of survivors varies by one or two between runs.**
- **A refusal test without `match=` proves only that something refused.** Match the whole message (`^...$`).
- **mutmut's state is reset by a run that fails at once.** A run given absolute test paths reset every result to
  "not checked". Keep a copy of the survivors' diffs before trying anything new.
- **`run_tests.sh` sees `mutants/`.** Delete it first, or pass `--exclude` to ruff.
- **A function that makes a function, called at import** (`_replace_back(kind)` in the table `INVERSES`): the
  closure is made before mutmut switches the mutant on, so every mutant of it survives. Such factories have to be
  checked by reading them, or made plain functions.
- **The test database is shared.** A run with database tests and `--max-children` above 1, or any other database
  test or e2e run at the same time, clears the database under the run.

## What is left in the two modules

pangloss-dates: nothing worth a test (see above).

pangloss-models: 507 survivors. 186 are wording only and 321 change logic. About 63 of those 321 are rule variables,
extensions and `$is`, which are tested in pangloss-derived and pangloss-library, outside this run. That leaves about
258. By function:

| Function | Logic | Wording | What it is |
|---|---|---|---|
| `search.check_where` | 29 | 1 | most pass `path` or `top` on to `$somewhere`, `$any`, `$spaces` and the rule keys |
| `search.check_relation` | 29 | 11 | mostly the variable of a rule; `steps` and `through` of a `match` |
| `search_where.initialise_where_models` | 26 | 22 | making the `Where` classes; their errors |
| `search.parse_where` | 15 | 9 | taking `Condition` and `Incoming` objects as they are; the depth of nested `$all` |
| `search.check_incoming` | 15 | 1 | through wrappers on the way; the subclasses' relations |
| `search_where.variable_classes` | 14 | 5 | the classes a `Var` can stand for |
| `search.never_a_head_message` | 11 | 6 | the message for a class that can never be searched |
| `search.check_spaces` | 11 | 13 | `$spaces` |
| `search_where.aliased` | 11 | 0 | the JSON keys of a field as well as its Python name (`AliasChoices`) |
| `label_templates.fill_labels` | 11 | 19 | what is read, and what is put back, on a write |
| `label_templates._step`, `text_of` | 20 | 0 | paths through wrappers and annotated values |

217 mutants have no test in this run. They are in code that other packages' tests reach:

- `check_field_types`, through the list query in pangloss-cypher;
- `check_extension` and `register_extension`, through `$same_as` in pangloss-library and the dates query;
- the comparisons of `Var`, through pangloss-derived.

A run with those packages' tests would show whether they are really covered.

**A gap in the conformance suite:** no test searches with `$incoming` against a database. Only one live test of
pangloss-derived uses it. A conformance test (it would run on Memgraph and Neo4j) would cover the Cypher that
`search_query.py` makes of it.

## What to check next

In order of what I expect them to find against what they cost. The times are for the module's own tests. (The
write plan, `fragments`, `build_tree`, literals, merging, write checks, citations and the migrations are done: see
above.)

| Module | Size | Its tests | Why |
|---|---|---|---|
| `pangloss_dates/rules.py`, `query.py` | 147 and 121 lines | the live tests of dates | needs the database: one mutant at a time |
| the rest of `search.py` and `search_where.py` | | | the 258 above |
| the rest of the migrations | | `tests/migrations`, 4 s | `split_app`, and the inverses of the changes made by hand (above) |
| `pangloss_cypher/search_query.py` | 412 lines | only through the live tests | see below |
| the interface, with Stryker | | Vitest | `interface-core/src/schema/` (`labelTemplate.ts`, `collapse.ts`, `clipboard.ts`, `fillEmbedded.ts`), the valibot form checks, `pangloss_dates/interface/src/format.ts` and `dating.ts` |

**`search_query.py`** turns a checked search into Cypher. It is only tested through the live tests, so each mutant
needs the database. Ways to make that cheaper:

- **Run it on the ~400 mutants that matter.** Leave out the wording and run the rest at `--max-children 1`
  overnight.
- **A database per worker.** `PANGLOSS_TEST_DATABASE_PER_WORKER` gives each xdist worker one, but a mutmut child is
  not an xdist worker. Something would have to give each child a database (a port by child), and that is not built.
- **Check the Cypher text against fixed expectations.** These would break with every harmless change to the query,
  and need updating each time.

**Stryker** (TypeScript) needs `@stryker-mutator/core` and `@stryker-mutator/vitest-runner` in the interface's
`package.json`. That is a change to the interface's dependencies, and has not been made. The interface keeps its
logic out of components in `schema/` and the modules' `src/`. That is what can be tested this way; the components
are tested by e2e.

**Whether to run it regularly.** It is too slow for every commit. On the pure modules it is fast enough to run by
hand after a change to them (1 to 7 minutes). Two things would make it routine:

- Add `mutmut` to the dev dependencies.
- Keep the two `setup.cfg` files, or `[tool.mutmut]` sections in the packages' `pyproject.toml`.

Both change what is committed, so they are for the user to decide.
