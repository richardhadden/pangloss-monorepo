# A field takes the classes below a wrapper it names: the task

✅ Built 2026-11-20 ("As built", below; what the reference says is in [models.md](models.md), "Classes below a
wrapper"). Branch `reified-relation-inheritance` (from dev, which has
[relation-steps-plan.md](relation-steps-plan.md) and the edge-model types).

## What is wanted

```python
class InRole[T](ReifiedRelation[T]):
    role: str | None = None

class Finer[T](InRole[T]):
    fine: int = 0

class Doc(Document):
    who: list[InRole[Person]]
```

`who` should take a `Finer` (`{"type": "Finer", "fine": 2, "target": [...]}`), as a field that declares `Person`
takes a `Saint`. Today it is refused (`who.0.type: Input should be 'InRole'`), and a field takes only the wrappers
it names: `InRole[Person] | Finer[Person]`. The user (2026-11-20): reified relation inheritance was left out "mostly
because I was struggling with the implementation", and "it would be ideal if it worked, if that's not too
difficult". So the first thing to find out is whether it is; if it turns out large, stop and say so.

The same for a semantic space and a conjunction, so that the three stay alike.

## What is known

- **Where the types of a field are made:** `build_relation_options`
  (`pangloss_models/initialise_models/initialise_field_definitions.py`). A reified relation gives one option, of
  the class named (`base_type=origin`). A semantic space and a conjunction loop over `get_concrete_types(origin)`,
  but that finds no generic class below: `utils.generic_get_subclasses` skips every parameterised generic, and
  `class Finer[T](InRole[T])` is below `InRole[T]`, a parameterised class. So none of the three takes a class below
  today.
- **The parameters.** `Finer[T](InRole[T])` passes its own `T` to `InRole`'s. An option for `Finer` in a field that
  declares `InRole[Person]` needs `Finer`'s parameters worked out from `InRole`'s (`T -> Person`): read the
  parameterised base in `Finer.__mro__` (`__pydantic_generic_metadata__`: `origin`, `args`). A class below may
  rename, reorder or add parameters (`class Both[A, B](InRole[A])`): what cannot be worked out from the use should
  not be offered, or should be refused with a message: to decide.
- **A class with no parameters below a use** (`class JohnRole(InRole[Person])`) already works as a field's type
  (`closed_wrapper_use`, same file). Whether `InRole[Person]` should also take a `JohnRole` follows the same
  question (it is below that very use).
- **What already copes** (not to rebuild, but to test): a node has the label of its own class only
  (`labels.labels_for_model`), and a search that names a wrapper looks for the classes below it
  (`search.wrapper_labels`, `Compiler.is_wrapper`, `passes_through`); `exclude_wrappers` likewise. The reverse read
  goes by the node's `type`.
- **A type is among the types of a field once** (`check_one_option_for_each_type`): `InRole[Person] | Finer[Person]`
  written out must still be allowed once `InRole[Person]` alone gives both (the same option twice is one).
- **`default_reified_type`, `collapse`, `headless`** (`InterfaceMeta`, `check_default_reified_type`) assume the
  options of a field: check each against a field that now has more.

## What follows from it (the cost)

- **Migrations.** The options of every field that names a wrapper with classes below it change, so
  `makemigrations` finds an `AlterRelationTarget` (added options) for each: for the demo, and for any project.
  Additive, no data changes. The demo needs its migration and its stubs made again.
- **The interface.** A form offers the classes below wherever the parent is declared (the retype buttons ↧/↥ for
  nested documents are the model: `schema/retype.ts`). `default_reified_type` decides what a new value is.
- **Exports, stubs, the SDK, the snapshot of generated models** (`test_generated_models_snapshot.py`,
  `UPDATE_SNAPSHOTS=1`) change.
- **`pangloss-derived`, `pangloss-criteria`, `pangloss-rdf`, history upgrades**: each reads a field's options
  somewhere; find them (an `Explore` pass: "where are `type_options` / `parameter_type_options` read").

## Steps

1. **Find out the size.** A scratch test with no database (`initialise(bind_database=False)`): make
   `build_relation_options` give an option for each generic class below, with its parameters worked out, and see
   what `initialise()`, a `Create`, and the non-database suite say. Report to the user before going on if it is
   more than the option expansion and its followers above.
2. **Decide with the user:** opt-out (a wrapper whose classes below are not to be offered), what a class below
   with other parameters does, and whether the interface offers them at once.
3. **Build**, with tests first in the conformance suite (written, read, read from the entity, updated, searched, on
   both backends), then the model tests, the demo's migration, the interface.
4. **Docs:** `models.md` ("Classes below a wrapper", which says today that a field takes only what it names),
   `relations.md`, `TODO.md` (the item under "A relation through several wrappers as one edge"), the guide, the
   skill's `references/modelling.md`, `status.md`.

## As built: step 1 (2026-11-20)

**The size: small.** It is the option expansion and nothing else in the Python code.

- `wrapper_uses_below(use)` (`initialise_field_definitions.py`): the classes declared directly below a use of a
  generic wrapper, each as the use that the field's use makes of it (`Finer[Person]` for `InRole[Person]`), by the
  parameterised base in between (`InRole[T]`: `__pydantic_generic_metadata__`). `build_relation_options` calls
  itself for each, so an option for a class below is the option the written-out union gave before, and classes
  further down (`Finest[T](Finer[T])`) follow. The same code serves the three kinds of wrapper.
- Taken: a generic class that passes its parameters on (`Finer[T](InRole[T])`), at any depth, and a class with no
  parameters below the very use (`JohnRole(InRole[Person])` in a field of `InRole[Person]`).
- Not taken (the payload is refused as before, no error at `initialise()`): a class with a parameter the use does
  not settle (`Both[A, B](InRole[A])`), a class below another use (`GroupRole(InRole[Group])`; also `JohnRole` in a
  field of `InRole[Person | Group]`), and a class below a class with no parameters (`class Sub(JohnRole)`).
- `InRole[Person] | Finer[Person]` written out gives the same options as `InRole[Person]` alone
  (`check_one_option_for_each_type` has nothing to say: the same option twice is one in the set).

**What the suites said**, with the expansion in and nothing else changed: without a database 2 failures of 3,543,
both expectations in `test_search_via_check.py` (a field of `EdgeA[...]` now passes through `Finer` too); on
Memgraph all 1,582 pass. The new `conformance/test_wrapper_classes_below_live.py` (written, read, read from the
entity, updated, searched, for the three kinds) passes on Memgraph and Neo4j: writes, reads, the reverse read, the
search and `exclude_wrappers` needed no change.

**What did not need building:**

- The interface: a form already offers every option of a field, so the classes below appear as the buttons a
  written-out union gave (not run in a browser for this).
- `default_reified_type`: passes as it is. `collapse` goes by the value. `headless` (`schema/headless.ts`) is for a
  field with one option, so a headless wrapper that has a class below it is no longer headless in such a field.
- The demo: `makemigrations --dry-run` finds no changes, because it writes
  `Identification[...] | IdentificationByToolchain[...]` out wherever it uses one. A project that names only
  `Identification[X]` and has `pangloss_library` installed gets `IdentificationByToolchain` in that field now, and
  an `AlterRelationTarget` for it.

## As built: steps 2 to 4 (2026-11-20)

**Decided by the user** (step 2, as recommended):

1. No opt-out. A class below goes where the class above is named, as a `Saint` goes where a `Person` is.
2. A class the use does not settle is quietly not taken (no error at `initialise()`: such a class is valid where a
   field names it).
3. `headless` is left as it is: a wrapper with a class below it has its head bar in a field that names it.

Not asked for, so not built: a class below a class with no parameters (`class Sub(JohnRole)`) in a field of the use
above.

**Step 3.** Beside the live test of step 1: `tests/test_wrapper_classes_below.py` (which classes are taken, at any
depth; which are not; that the options and the export of the field are those of the union written out;
`default_reified_type` of the class above or one below) and one in `tests/migrations/test_migration_diff.py` (a new
class below is an `AlterRelationTarget` for the field). No interface code changed. In a browser (asked for by the user afterwards): the e2e project has
`class InOffice[T](InRole[T])`, and `test_fields_and_wrappers.py` adds one in `Dossier.witnesses`
(`list[InRole[Person]]`): "Add Witnesses" offers In role and In office, the one below has its own field beside
the one it inherits, and it is saved and shown as an `InOffice`. The demo needs no migration.

**Step 4.** `models.md`, `relations.md`, `status.md`, `TODO.md`, the guide (the tutorial's statements page, the
interface page on `headless`), the skill's `references/modelling.md`.

## How to work

- Read the `pangloss` skill first. Commit and push after each step, and pause for the user after each.
- Tests: one database run at a time (`PANGLOSS_TEST_DATABASE_PER_WORKER=1` still puts a worker on `:7687`); long
  runs under `caffeinate -is`; not the Neo4j conformance run straight after the `pangloss-neo4j` package run.
  The commands are in `run_tests.sh`.
- One browser test fails in every full e2e run and passes alone
  (`e2e/test_admin.py::test_a_toolchain_made_on_the_admin_page_has_nothing_to_log_in_with`): a race in the test, not
  this work.
- The demo database (`:7688`) is never touched by tests; it needs `pangloss migrate` for the edge-model types
  (`pangloss_memgraph.0009`).
