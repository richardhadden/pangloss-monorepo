# Todo



- [ ] Add "subtract" type wrapper (opposite of Fulfil)

## `initialise_models/`: review (2026-10-21)

From reading all of `pangloss_models/initialise_models/` (about 4,000 lines) and running the test suite
with a line tracer (558 tests pass; **79% of the lines are reached**; the tracer is a throwaway script,
because `coverage` does not load on Python 3.15 yet: `module coverage.tracer uses unknown slot ID`).
Items marked **(confirmed)** were reproduced; **(suspected)** were found by reading only.

### Bugs

- [ ] **(confirmed) `Field(description=...)` is ignored.** `extract_field_description` only uses a bare
  `str` in the `Annotated` metadata (or `RelationConfig.description`), so `name: str = Field(description="x")`
  has no description in the field definition, in `Create`'s JSON schema, or in the OpenAPI. Use
  `field_info.description` first. Test: description from `Field(...)`, from `Annotated[str, "..."]`, from
  `RelationConfig`, and which wins.
- [ ] **(confirmed) Field names that collide with generated ones are accepted silently:** `label`, `id`,
  `type`, `urls` (only `meta` is rejected, in `initialise_field_definitions`). Decide the reserved set
  (what each `Create`/`View`/`HeadView` adds) and raise `PanglossModelError`. Test each name, per kind.
- [ ] **(confirmed) `initialise()` is not idempotent:** a second call doubled the incoming relations
  (`who_reverse`: 1 then 2), because `initialise_incoming_relation_definitions` appends. Make it
  idempotent or refuse a second call (with a clear error), and test both.
- [ ] **(suspected) `initialise_update_model.build_generic_update_model_from_type_option`** has three faults
  in one place: the result of `build_bound_field_update_model(...)` is assigned to `bound_create_model`
  (an unused name), so **field bindings are dropped** from bound `Update` models; it copies
  `generic_relation_type.Create.model_fields` (not `.Update`) onto the `Update` model; and `@cache` is on a
  function of `(type_option, field_bindings)`, so it is also a process-global cache (see below). The lines
  run in the tests (so it is covered but not asserted). Write a test with a generic relation + `bind_to_child_field`
  + `Update` and check the bound field is optional.
- [ ] **(suspected) Generic branches append the plain variant even when there is an edge model.** In every
  `build_generic_*_from_type_option` the `RelationToGeneric` case is
  `if to.edge_model: annotations.append(edge version)` followed by an unconditional
  `annotations.append(plain version)` (all the other branches use `else`). With `Field(discriminator="type")`
  (View) two members with the same `type` Literal would be an error; without it (Create) a payload without the
  edge properties is accepted. Check which is meant; add tests.
- [ ] **(suspected) `get_fields_on_model` yields a field twice** when two fulfilled classes (`Fulfils[A, B]`)
  have a field of the same name (`fulfilled_field_names` is a list, not de-duplicated), and picks
  `[...][0]` of an unordered `set` (`get_fulfiled_types` returns a `set`, so *which* class's `FieldInfo` is used
  is by hash order, so could differ between runs). Use an ordered, de-duplicated structure, and decide what happens
  when two fulfilled classes disagree about a field's type.
- [ ] **(suspected) `normalise_and_get_subclassed_fields` mutates `relation_config.subclasses_parent_fields`**
  (a list on a config shared through `FieldInfo`), and is called for the model and again for every fulfilled
  class. Result depends on call order and on how often it ran. Compute a new value, do not write back. In the string
  branch, `subclassed_fields[name]` is overwritten for each origin class, so only the last survives when a field
  is on several parents.
- [ ] **(suspected) `build_relation_options`**: the `Document` branch skips `abstract` types, the `Trait` branch
  (which also yields Documents) and the `Entity` branch do not. An abstract Document that implements a Trait may be
  offered as a target. Check against `get_concrete_types`.
- [ ] **(suspected) `check_subclass_type`** uses `assert isinstance(..., RelationFieldDefinition)`: subclassing a
  literal field gives an `AssertionError` (and nothing under `python -O`), not a `PanglossModelError`. The same
  `assert`-as-validation is in `build_list_field_definition`, which then catches `AssertionError` to turn it into a
  generic message (this would hide a real assertion error from elsewhere in the `try`).
- [ ] **(suspected) A relation field that ends with no usable types** (`get_relation_annotation_types` returns
  `None`) and is optional makes `Union[None, None]`, i.e. a field of type `None`, and it is created silently.
- [ ] **(suspected) `CreateDB` literals that are optional get `default=None` but a non-optional annotation**
  (`Create` and `View` use `X | None`). Harmless at runtime (defaults are not validated), but the schema and type
  hints disagree.
- [ ] **(suspected) The `incoming` analysis misses wrappers.** `initialise_incoming_relation_definitions` handles
  `RelationToEntity` and `ReifiedRelation[...]` only. A relation whose type is `SemanticSpace[...]` or
  `Conjunction[...]` around an entity (`RelationToSemanticSpace`, `RelationToConjunction`) is ignored, so the
  entity gets no reverse field for it. `docs/models.md` says these are included (via nesting): check which cases.

### Global state and fragile mechanisms

- [ ] **`bound_models_built` (module global, in both `initialise_create_model` and `initialise_view_model`)** is
  keyed by `hash(hash(model) + hash(frozenset(bindings)))`: a collision returns the *wrong* model, silently, and
  it is not cleared by `ModelRegistry._reset()` (check), so models from an earlier registry can be reused. Key by
  the tuple `(model, bindings)` and clear it in `_reset`. Same for the `@cache` on
  `build_generic_update_model_from_type_option`.
- [ ] **Writes to `Model.model_fields[...]` directly, then `model_rebuild(force=True)`**, everywhere (65
  places). It works with the pydantic in use but is not a public API. The comment "for some reason, we need to
  manually add all the fields from the Generic unbound type" is a sign it is being fought. At minimum put it in
  one helper (`set_field(model, name, FieldInfo)`) so a pydantic change has one place to fix; better, build the
  fields as `create_model(**field_definitions)` once.
- [ ] **`FieldInfo` objects are shared between models** (`HeadView`/`EditView` copy `View`'s `FieldInfo`s), and
  the code later sets `.default` / `.default_factory` on `FieldInfo`s it has just put in. A later mutation would
  leak between models. Copy (`copy.copy`) when sharing.
- [ ] **`initialise()` needs settings loaded** (`_bind_database_functions` reads
  `pangloss_core.settings.SETTINGS`) even to generate pure models: `AttributeError: module 'pangloss_core.settings'
  has no attribute 'SETTINGS'`. Generation should not need a database; bind lazily or split the step.
- [ ] **`initialise_reference_models`: `try: get_type_hints(...) except Exception: return`** with a
  "TODO! Remove this guard once all tests passing" (twice). It silently leaves a model with no `ReferenceSet` /
  `ReferenceView`. Remove the guard and let the error show. The models are found from the class's *type hints*
  (`get_args(get_args(hints["ReferenceSet"])[0])[0]`), a fragile way to find a base class; use an explicit
  attribute. A missing hint is a `warnings.warn`, should be an error.
- [ ] `EditView` exists only for `Entity` (`can_have_edit_view_model`), but the API has `/edit` for Documents too:
  check what the Document route returns and whether it should have the same model.

### Refactoring

- [ ] **Merge the five builders into one (deliberately left duplicated until now; revisit when ready).**
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

  Not started. The snapshot harness (step 1) needs no decisions and is the safe first piece.
- [ ] **Dead code:** `unpack_generic_fields` is defined in 4 modules and called from none;
  `check_create_and_id_present` and `get_model_validators` are defined twice (`create` and `create_db`) and
  `update` re-defines `get_model_validators`; `return None` after the base-type chain is unreachable; `else:
  annotation = annotation / edge_model = edge_model` in `build_relation_options` is a no-op; `else: continue` in
  `get_field_origin_model_and_definition`; `if definition:` guards a value that is never falsy.
- [ ] **`initialise_field_definitions` is one 150-line function** with an `if` chain whose order matters and a
  `handled_as_type_variable` flag set in four places, and which can add the same field twice (the
  generic-wrapper cases add the field and then fall through to the `elif` chain). Split by kind (one function per
  field category, returning the definition), and put the "wrapper with a TypeVar" cases in their own function.
- [ ] `build_relatable_field_definition` makes the same `RelationFieldDefinition(...)` in four branches that
  differ in three arguments. One construction, with the branches computing `type_options` and `wrapper`.
- [ ] Functions called `build_*` / `get_*` that **mutate the model** (`model._depends_on_classes.add(...)` inside
  `build_relation_options` and `build_relatable_field_definition`; docstrings say `model.depends_on_classes`, the
  attribute is `_depends_on_classes`). Return the dependencies and let the caller record them.
- [ ] Small: `initalise_incoming_relation_definitions.py` (typo in the file name); "fulfiled"/"fulfilling" spelled
  both ways (`get_fulfiled_types`, `_fulfiling_types`, a magic `"fulfiling_types"` skipped by name in
  `get_fields_on_model`); the loop variable `type_option` is shadowed inside `recurse_embedded_for_incoming` and
  the match capture `parameter_type_options` rebinds the loop variable in `recursive_get_target_of_reified`;
  `getattr(model._meta, "create_with_id", False)` / `getattr(..., "require_label", True)` hide a typo in an
  option name (the meta classes declare them); error messages print class objects (`{spf.field_on_model}`) instead
  of names; three type checkers' ignore comments (`# type: ignore`, `# pyright: ignore[...]`, `# ty:ignore[...]`)
  on the same lines; `label` is added last to `Create`/`View`, so appears last in the schema.

### Tests that are missing (from the line trace)

Everything below is code that **no test reaches**:

- [ ] **Generic relations (`ReifiedRelation[...]`, `SemanticSpace[...]`, `Conjunction[...]`) with an edge model
  (`ViaEdge`)**: in all five builders, nearly every `edge_model` branch under `build_generic_*` and
  `get_relation_annotation_types` (the `.apply_edge_model(...)` lines). One parametrised test over the five model
  kinds (`Create`, `CreateDB`, `Update`, `UpdateDB`, `View`) would cover them.
- [ ] **Generic relations whose own fields are `Entity` / `Document` relations (not a TypeVar):** the
  `RelationToEntity` / `RelationToDocument` branches after the TypeVar loop (with and without `create_inline`, with
  and without bindings) in `create`, `update`, `view`, `create_db`, `update_db`.
- [ ] **Field bindings on embedded values and annotated values** (`annotation | None` and `default = None` for
  `Embedded` and `AnnotatedValue` fields with inherited bindings): `create`, `update`, `view`.
- [ ] **Field bindings on a `Document` inside a generic (`build_bound_field_*` called from the generic builders)**,
  and the bound-model cache (a second request for the same binding returns the same class).
- [ ] **`create_with_id` validation:** `create_new=True` without an `id` (the second `raise` in
  `check_create_and_id_present`) is never exercised.
- [ ] **Reference models:** the `warnings.warn` for a missing hint, the swallowed `get_type_hints` failure, and the
  `PanglossModelError` for a bad `reference_view_extra_fields` name.
- [ ] **Field definitions:** a `Fulfils[...]` parent in `get_field_origin_model_and_definition`; the string-name
  branch of `normalise_and_get_subclassed_fields` for a field that does not exist; `RelationConfig.description`; a
  Trait with a Document implementation as a relation target; an `AnnotatedValue` with a relation (the error); an
  invalid `list[...]` literal field (the `AssertionError` path).
- [ ] **`require_label=False`** for `HeadView` (only reached in the other models).
- [ ] **Properties, not lines:** the tests assert on the shape of the generated models for chosen cases. Add
  a property test over the registry: for every model kind, `Create(...)` accepts what `View` returns for the same
  data (round trip), the JSON schema is valid, and `initialise()` of the same classes in a different declaration
  order gives the same schemas.
- [ ] A **line-coverage run in CI.** `coverage` needs a Python it supports (or the `sys.monitoring` tracer used
  here, `COVERAGE_CORE=sysmon`, once `coverage` installs on 3.15); then fail below a floor for
  `initialise_models/`.
