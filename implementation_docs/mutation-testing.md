# Mutation testing 🚧

Written 2026-11-18. What mutation testing has been run on, what it found, what was done about it, how to run it
again, and what to check next. The work is on branch `mutmut-test` (commits `23140bd4`, `e96d0240`, `c565fd10`).

## Contents

- In short
- What it is, and what the numbers mean
- How to run it
- pangloss-dates
- pangloss-models: search checking and label templates
- Traps
- What is left in the two modules
- What to check next

## In short

| Module | Mutants | Survived before | Survived after | Score after | Run time |
|---|---|---|---|---|---|
| pangloss-dates (pure modules) | 1626 | 125 | 26 | 98.4% | ~1 min |
| pangloss-models `search.py`, `search_where.py`, `label_templates.py` | 3427 | 789 | 507 | ~84% | ~7 min |

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

Each package has an untracked `setup.cfg` with its configuration. Run from the package's directory:

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

## Traps

- **Code run when a module is imported** is invisible to mutmut, which switches a mutant on after the tests are
  collected. `RULES` in `test_dates_recurrence.py` is a list built at import, so the check of `nth=5` it made was
  never counted. Build the values at the edges inside a test.
- **The number of survivors varies by one or two between runs.**
- **A refusal test without `match=` proves only that something refused.** Match the whole message (`^...$`).
- **mutmut's state is reset by a run that fails at once.** A run given absolute test paths reset every result to
  "not checked". Keep a copy of the survivors' diffs before trying anything new.
- **`run_tests.sh` sees `mutants/`.** Delete it first, or pass `--exclude` to ruff.
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

In order of what I expect them to find against what they cost. The times are for the module's own tests.

| Module | Size | Its tests | Why |
|---|---|---|---|
| `pangloss_cypher/write_plan.py` | 606 lines | `test_write_plan.py`, 0.4 s | how a write is planned before any Cypher is run; pure; a mistake writes the wrong thing |
| `pangloss_models/literals.py` | 482 lines | the initialisation tests | the codec registry: how each literal type is stored, read and compared; search and the RDF export use it |
| `pangloss_models/merging.py` | 490 lines | `test_merging.py`, 1.3 s | the merge of two entities that can be undone; a mistake loses data |
| `pangloss_models/write_checks.py`, `citations.py` | 176 and 383 lines | 0.3 s and 0.6 s | what a write is refused for; what a citation protects |
| `pangloss_cypher/fragments.py`, `build_tree.py` | 225 and 103 lines | 0.3 s and 0.2 s | the pieces of Cypher and the tree a read is made into |
| `pangloss_dates/rules.py`, `query.py` | 147 and 121 lines | the live tests of dates | needs the database: one mutant at a time |
| the rest of `search.py` and `search_where.py` | | | the 258 above |
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
