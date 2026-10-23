# Todo



- [ ] Add "subtract" type wrapper (opposite of Fulfil)

## `initialise_models/`: review (2026-10-21)

From reading all of `pangloss_models/initialise_models/` (about 4,000 lines) and running the test suite
with a line tracer (558 tests pass; **79% of the lines are reached**; the tracer is a throwaway script,
because `coverage` does not load on Python 3.15 yet: `module coverage.tracer uses unknown slot ID`).
Items marked **(confirmed)** were reproduced; **(suspected)** were found by reading only.

**Status 2026-10-22: the cleanup is done; see [docs/initialise-models-cleanup.md](../../docs/initialise-models-cleanup.md).**
Items below marked `[x]` are fixed (with a test); `[x] not a bug` were suspected and found not to be; the rest remain
(also listed in "Not done" and "Decisions needed" there).


### Bugs

- [x] **(confirmed) `Field(description=...)` is ignored.** `extract_field_description` only uses a bare
  `str` in the `Annotated` metadata (or `RelationConfig.description`), so `name: str = Field(description="x")`
  has no description in the field definition, in `Create`'s JSON schema, or in the OpenAPI. Use
  `field_info.description` first. Test: description from `Field(...)`, from `Annotated[str, "..."]`, from
  `RelationConfig`, and which wins. **Fixed.**
- [x] **(confirmed) Field names that collide with generated ones are accepted silently:** `label`, `id`,
  `type`, `urls` (only `meta` is rejected, in `initialise_field_definitions`). Decide the reserved set
  (what each `Create`/`View`/`HeadView` adds) and raise `PanglossModelError`. Test each name, per kind. **Fixed (all but `label`, which a model may declare).**
- [x] **(confirmed) `initialise()` is not idempotent:** a second call doubled the incoming relations
  (`who_reverse`: 1 then 2), because `initialise_incoming_relation_definitions` appends. Make it
  idempotent or refuse a second call (with a clear error), and test both. **Fixed.**
- [x] **(suspected) `initialise_update_model.build_generic_update_model_from_type_option`** has three faults
  in one place: the result of `build_bound_field_update_model(...)` is assigned to `bound_create_model`
  (an unused name), so **field bindings are dropped** from bound `Update` models; it copies
  `generic_relation_type.Create.model_fields` (not `.Update`) onto the `Update` model; and `@cache` is on a
  function of `(type_option, field_bindings)`, so it is also a process-global cache (see below). The lines
  run in the tests (so it is covered but not asserted). Write a test with a generic relation + `bind_to_child_field`
  + `Update` and check the bound field is optional. **Not a bug that a test could find: the discarded assignment was dead code and is removed; the `Create` fields copied onto the `Update` model were an accident, and are now the `Update` fields (decided 2026-10-22, with the other `Update` quirks: see "Decisions made" in docs/initialise-models-cleanup.md).**
- [x] **(suspected) Generic branches append the plain variant even when there is an edge model.** In every
  `build_generic_*_from_type_option` the `RelationToGeneric` case is
  `if to.edge_model: annotations.append(edge version)` followed by an unconditional
  `annotations.append(plain version)` (all the other branches use `else`). With `Field(discriminator="type")`
  (View) two members with the same `type` Literal would be an error; without it (Create) a payload without the
  edge properties is accepted. Check which is meant; add tests. **Confirmed (initialise() crashed) and fixed.**
- [x] **(suspected) `get_fields_on_model` yields a field twice** when two fulfilled classes (`Fulfils[A, B]`)
  have a field of the same name (`fulfilled_field_names` is a list, not de-duplicated), and picks
  `[...][0]` of an unordered `set` (`get_fulfiled_types` returns a `set`, so *which* class's `FieldInfo` is used
  is by hash order, so could differ between runs). Use an ordered, de-duplicated structure, and decide what happens
  when two fulfilled classes disagree about a field's type. **Fixed (ordered, each once). What happens when two fulfilled classes disagree about a type is not decided.**
- [x] **(fixed 2026-10-22) `normalise_and_get_subclassed_fields` mutated `relation_config.subclasses_parent_fields`**
  (a list on a config shared through `FieldInfo`), and is called for the model and again for every fulfilled
  class. Result depends on call order and on how often it ran. Compute a new value, do not write back. In the string
  branch, `subclassed_fields[name]` is overwritten for each origin class, so only the last survives when a field
  is on several parents.
- [x] **(suspected) `build_relation_options`**: the `Document` branch skips `abstract` types, the `Trait` branch
  (which also yields Documents) and the `Entity` branch do not. An abstract Document that implements a Trait may be
  offered as a target. Check against `get_concrete_types`. **Not a bug: abstract documents implementing a trait are excluded.**
- [x] **(suspected) `check_subclass_type`** uses `assert isinstance(..., RelationFieldDefinition)`: subclassing a
  literal field gives an `AssertionError` (and nothing under `python -O`), not a `PanglossModelError`. The same
  `assert`-as-validation is in `build_list_field_definition`, which then catches `AssertionError` to turn it into a
  generic message (this would hide a real assertion error from elsewhere in the `try`). **Fixed.**
- [x] **(checked 2026-10-22) A relation field that ends with no usable types** is left out of the model (`builder.py`, `if annotation is None: continue`), not made a field of type `None`. Whether it should be an error is open.
- [x] **(decided and done 2026-10-23: `X | None`) `CreateDB` literals that are optional get `default=None` but a non-optional annotation**
  (`Create` and `View` use `X | None`). Harmless at runtime, but the schema and type hints disagree. Listed under "Decisions needed" in `docs/initialise-models-cleanup.md`.
- [x] **(confirmed 2026-10-22) An entity reached only through a `SemanticSpace` or `Conjunction` has no reverse relation.**
  Tested on the real database, with `Plain.direct: Person`, `ViaReified.reified: InRole[Person]`,
  `ViaSpace.spaced: Negative[Person]` and `ViaSpaceReified.both: Negative[InRole[Person]]`: all four documents are
  **written** without error, and the graph holds the reverse edges (`contents_reverse` from the person to the
  `Negative` node, `target_reverse` to the `InRole`), but `Person.get(...)` has only `direct_reverse` and
  `reified_reverse`. The entity has no `spaced_reverse` or `both_reverse` field, so the relation is accepted, stored, and
  invisible from the entity. Two places leave it out: `initialise_incoming_relation_definitions` handles
  `RelationToEntity` and `RelationToReifiedRelation[Document]` only (not `RelationToSemanticSpace` /
  `RelationToConjunction`), and the read in `pangloss-memgraph` (`build_fetch_incoming_query`, `read_incoming.py`)
  climbs only reified relations and embedded objects (`CHAIN_LABELS`), so the `Negative` node ends the climb and is dropped
  as an unknown holder. A document that refers to the entity directly, nested inside a semantic space
  (`Negative[Statement]` where `Statement.by: Person`), is not affected. **Decide: support it** (both packages: the
  analysis, the climb, and a view that shows the chain of wrappers) **or refuse it** at `initialise()` with a clear error
  (currently the data is written and cannot be seen from the entity). No test yet; if it is to be supported, write the
  `pangloss-memgraph` test first. **Fixed 2026-10-22, supported in both packages** (model analysis, the incoming read and its view assembly; tests in `test_read_entity.py` and `test_initialisation_gaps.py`). A conjunction above the wrapper next to the entity whose other part is not an entity is left out of the entity's view, with a log warning.
### Global state and fragile mechanisms

- [x] **`bound_models_built` (module global, in both `initialise_create_model` and `initialise_view_model`)** is
  keyed by `hash(hash(model) + hash(frozenset(bindings)))`: a collision returns the *wrong* model, silently, and
  it is not cleared by `ModelRegistry._reset()` (check), so models from an earlier registry can be reused. Key by
  the tuple `(model, bindings)` and clear it in `_reset`. Same for the `@cache` on
  `build_generic_update_model_from_type_option`. **Fixed.**
- [x] **Writes to `Model.model_fields[...]` directly** now go through `set_field` (`builder.py`): one place to change if pydantic does.
- [x] **`FieldInfo` objects are shared between models** (`HeadView`/`EditView` copy `View`'s `FieldInfo`s), and
  the code later sets `.default` / `.default_factory` on `FieldInfo`s it has just put in. A later mutation would
  leak between models. **Fixed (2026-10-23): `copy` when sharing; the incoming-relation field goes through `set_field`.**
- [x] **(fixed: `initialise(bind_database=False)`) `initialise()` needs settings loaded** (`_bind_database_functions` reads
  `pangloss_core.settings.SETTINGS`) even to generate pure models: `AttributeError: module 'pangloss_core.settings'
  has no attribute 'SETTINGS'`. Generation should not need a database; bind lazily or split the step.
- [x] **`initialise_reference_models`: `try: get_type_hints(...) except Exception: return`** with a
  "TODO! Remove this guard once all tests passing" (twice). It silently leaves a model with no `ReferenceSet` /
  `ReferenceView`. Remove the guard and let the error show. The models are found from the class's *type hints*
  (`get_args(get_args(hints["ReferenceSet"])[0])[0]`), a fragile way to find a base class; use an explicit
  attribute. A missing hint is a `warnings.warn`, should be an error. **Fixed.**
- [x] `EditView` exists only for `Entity` (`can_have_edit_view_model`), but the API has `/edit` for Documents too:
  **Checked 2026-10-23: no `EditView` is needed.** It is the `HeadView` without the incoming relations, and a document has none, so its
  `HeadView` is what is edited (the API says so; `test_head_view_model.py` pins that a document's `HeadView` has the fields of its `View`).

### Refactoring

- [x] **Merge the five builders into one (deliberately left duplicated until now; revisit when ready).**
  `create`, `create_db`, `update`, `update_db` and `view` in `initialise_models/` were kept as separate copies
  on purpose, until it was clear how far they would diverge and which differences are real. The review above
  suggests that is now clear enough to decide (51-76% of lines identical pairwise, measured with `difflib`; each
  has its own `can_have_*`, `get_*_base_model_type` (a seven-way `if/elif` over the kinds),
  `recursively_get_generic_naming` (verbatim x5), `build_generic_*_from_type_option` (about 190 lines each),
  `get_relation_annotation_types` and `add_fields_to_*`). A fix has to be made five times, and the copies have
  already drifted (see "Bugs"). Aim: one builder, parameterised by a small `ModelKind` description (the name of the
  generated model, its base class per declared kind, how an entity reference / document / generic is spelled in
  it, whether unions are discriminated, whether field bindings apply).

  *Differences that look real (the single builder must keep them):*
  - which model is made (`Create`, `CreateDB`, `Update`, `UpdateDB`, `View`) and its base class;
  - how a reference to an entity is spelled: `ReferenceSet` (+ the inline `Create` if `create_inline`) in
    `Create`/`Update`; `ReferenceSet` + `CreateDB` in `CreateDB`/`UpdateDB`; `ReferenceView` in `View`;
  - a nested document in `Update` may be new or existing, so the union holds both `Create` and `Update`
    members; the others hold one;
  - `View` unions are discriminated on `type` (`Field(discriminator="type")`); `Create`'s is commented out;
  - field bindings apply to `Create`, `Update` and `View`, never to the DB models;
  - in `View`, a relation list with no items defaults to an empty list (nothing stored means nothing read back).

  *Differences that look accidental (decide each, with a test, before merging):*
  - `Update` bound generics: bindings dropped (result assigned to an unused name) and `Create`'s fields copied
    onto the `Update` model (see "Bugs");
  - the `RelationToGeneric` case adds the plain variant even when there is an edge model (all five);
  - order of `ReferenceSet` and the inline `Create` in a union differs between branches, and pydantic's smart
    union can choose differently by order;
  - `CreateDB` optional literals: `default=None` with a non-optional annotation (the others use `X | None`);
  - `View` does not add the inline `View` for a `create_inline` entity in the non-edge branch, but does in the
    edge-model branch;
  - `getattr(model._meta, "create_with_id", False)`-style lookups that hide a mistyped option.

  *Order of work:*
  1. **Characterisation tests first (a snapshot harness).** For every model in the test models (and the demo's),
     generate all five model kinds and record their JSON schemas, field annotations and union members (in a
     stable order). The merge must reproduce them exactly, except where a difference is decided to be a bug.
     This also covers most of "Tests that are missing" below, because it exercises each generic / edge-model /
     binding combination.
  2. **Settle the accidental differences**: one test each saying which behaviour is intended, so each is a
     decision and not a side effect of the merge. Fix the confirmed and suspected bugs above first or as part of
     this step.
  3. **Introduce `ModelKind`** and move one builder over at a time, `View` first (fewest special cases), running
     the snapshots after each. Delete the old copy (and the dead code listed below) as each one goes.
  4. Remove the module-level caches and direct `model_fields` writes as part of it (see "Global state and
     fragile mechanisms").

  Not started. The snapshot harness (step 1) needs no decisions and is the safe first piece. **Done.**
- [x] **Dead code:** `unpack_generic_fields` is defined in 4 modules and called from none;
  `check_create_and_id_present` and `get_model_validators` are defined twice (`create` and `create_db`) and
  `update` re-defines `get_model_validators`; `return None` after the base-type chain is unreachable; `else:
  annotation = annotation / edge_model = edge_model` in `build_relation_options` is a no-op; `else: continue` in
  `get_field_origin_model_and_definition`; `if definition:` guards a value that is never falsy. **Done.**
- [x] **`initialise_field_definitions` is one 150-line function** with an `if` chain whose order matters and a
  `handled_as_type_variable` flag set in four places, and which can add the same field twice (the
  generic-wrapper cases add the field and then fall through to the `elif` chain). Split by kind (one function per
  field category, returning the definition), and put the "wrapper with a TypeVar" cases in their own function. **Done.**
- [x] `build_relatable_field_definition` makes the same `RelationFieldDefinition(...)` in four branches that
  differ in three arguments. One construction, with the branches computing `type_options` and `wrapper`. **Done.**
- [x] `build_relation_options` no longer takes the model: it adds to the set it is given (`depends_on`), and says so. (`build_relatable_field_definition` still records into `model._depends_on_classes`.)
- [x] Small, done 2026-10-22: "fulfiled"/"fulfiling" spelled one way (`fulfilled`, `fulfilling`), and the dead `"fulfiling_types"` field name no longer skipped by name; the `initalise_` file name and the shadowed loop variables had been fixed already; the error for a subclassed field that does not exist names `Class.field`. Left: the `getattr(model._meta, "create_with_id" / "require_label", ...)` calls are needed, as not every meta class declares them; three type checkers' ignore comments on the same lines; `label` is added last to `Create`/`View`, so appears last in the schema.

### Tests that are missing (from the line trace)

These were code that **no test reached**. Done ones are marked; the snapshot (`test_generated_models_snapshot.py`) now also covers each generic / edge-model / binding combination of the kitchen sink.

- [x] **Generic relations (`ReifiedRelation[...]`, `SemanticSpace[...]`, `Conjunction[...]`) with an edge model
  (`ViaEdge`)**: in all five builders, nearly every `edge_model` branch under `build_generic_*` and
  `get_relation_annotation_types` (the `.apply_edge_model(...)` lines). One parametrised test over the five model
  kinds (`Create`, `CreateDB`, `Update`, `UpdateDB`, `View`) would cover them. **Done (`test_initialisation_gaps.py`, all five models).**
- [x] **Generic relations whose own fields are `Entity` / `Document` relations (not a TypeVar):** the
  `RelationToEntity` / `RelationToDocument` branches after the TypeVar loop (with and without `create_inline`, with
  and without bindings) in `create`, `update`, `view`, `create_db`, `update_db`. **Done.**
- [x] **Field bindings on embedded values and annotated values** (`annotation | None` and `default = None` for
  `Embedded` and `AnnotatedValue` fields with inherited bindings): `create`, `update`, `view`. **Done.**
- [x] **Field bindings on a `Document` inside a generic (`build_bound_field_*` called from the generic builders)**,
  and the bound-model cache (a second request for the same binding returns the same class). **Done (and the cache is cleared with the registry).**
- [x] **`create_with_id` validation:** `create_new=True` without an `id` (the second `raise` in
  `check_create_and_id_present`) is never exercised. **Done: for `Create`; for `CreateDB` the branch was unreachable (it makes an id), and is removed.**
- [x] **Reference models:** the `warnings.warn` for a missing hint, the swallowed `get_type_hints` failure, and the
  `PanglossModelError` for a bad `reference_view_extra_fields` name. **Done (the guard is gone; a bad `reference_view_extra_fields` and a model that refers to itself are tested).**
- [x] **Field definitions:** a `Fulfils[...]` parent in `get_field_origin_model_and_definition`; the string-name
  branch of `normalise_and_get_subclassed_fields` for a field that does not exist; `RelationConfig.description`; a
  Trait with a Document implementation as a relation target; an `AnnotatedValue` with a relation (the error); an
  invalid `list[...]` literal field (the `AssertionError` path). **Done.**
- [x] **`require_label=False`** for `HeadView` (only reached in the other models). **Done.**
- [x] **Properties, not lines:** the tests assert on the shape of the generated models for chosen cases. Add
  a property test over the registry: for every model kind, `Create(...)` accepts what `View` returns for the same
  data (round trip), the JSON schema is valid, and `initialise()` of the same classes in a different declaration
  order gives the same schemas.  **Done, in part (2026-10-22):** `test_cross_kind_properties.py` (samples from the field definitions; Create, Update, conversions for writing, aliases, field agreement, nothing lost). It found three older bugs (see docs/initialise-models-cleanup.md). The read-edit-send-back and write/read cycle through the real database is `pangloss-memgraph/tests/test_edit_cycle.py`.
- [ ] A **line-coverage run in CI.** `coverage` needs a Python it supports (or the `sys.monitoring` tracer used
  here, `COVERAGE_CORE=sysmon`, once `coverage` installs on 3.15); then fail below a floor for
  `initialise_models/`. **Not done.**
## Tidying done 2026-10-23, and what is left

- Done: the `# pyright: ignore` comments are gone (`ty` is the checker); `_fulfils_classes` is worked out once per instance;
  `allow_bind_on_this_item` is "allowed (if any) and not excluded" (it was an OR; tested in `test_binding_rules.py`); the ~25
  type-only `@overload`s in `utils.py` are three generic signatures.
- [x] **Reorganise the tests.** Done: `tests/initialisation/`, `generated_models/` (with `snapshots/`), `migrations/`, `export/`, helpers in `support/` (put on the path by `tests/conftest.py`).
- [x] (done: `check_enum_values_in`, called when the field definition is made; tested for lists, optionals and `TypedDict`s) `is_literal` calls `check_enum_values` (a check with a side effect inside a predicate): move the check to where the field
  definition is made (it must also cover `list[Enum]`, `Enum | None` and the values of a `TypedDict`).
- [x] `get_top_level_classes` is `@cache`d: kept (it is read in loops over every class's MRO), and says in its docstring that it reads the library's own classes, which exist once the package is imported.
