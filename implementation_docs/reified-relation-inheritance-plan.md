# A field takes the classes below a wrapper it names: the task

⏳ Planned 2026-11-20, nothing built. Branch `reified-relation-inheritance` (from dev, which has
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
