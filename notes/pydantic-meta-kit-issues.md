# `pydantic-meta-kit`: the issues found so far

Summary of what is in `TODO.md` ("Decisions and planning"), found by reading the code and by probes in earlier sessions. Not rechecked
against the version you are working on now.

## Bugs

1. **A grandchild loses its parent's meta values.** The merge reads `parents_metas[-1]`, which is the *farthest* ancestor, not the
   nearest, so a three-level hierarchy (`A` > `B` > `C`) gives `C` the values of `A` and drops what `B` set.
2. **`ACCUMULATE` of a `dict` raises on a repeated key**, instead of merging by the rule the field asks for.
3. **`_meta_class` is global to `WithMeta`.** A second kind of meta (two meta types in one process) breaks a subclass that has its
   own `_meta`, because the class that builds the meta is shared, not kept per base.
4. **Aliased fields never count as set**, so a value given under its alias is treated as not given and is overwritten by the
   parent's.
5. **Its own docstring example does not run.**

## Tests to add

Three-level hierarchies, and two meta types in one process (these are what found 1 and 3).

## Decisions that are yours

- Release it with a version and pin Pangloss to it?
- Does it stay a separate repository? (It is closely tied to pydantic internals, so each pydantic release is a risk either way.)

## What Pangloss does that depends on it

- Every declared kind (`Document`, `Entity`, `Embedded`, `ReifiedRelation`, `SemanticSpace`, `Conjunction`, `Trait`, `EdgeModel`,
  `AnnotatedValue`) repeats a `__pydantic_init_subclass__` hook, `cls._meta = cls.__dict__.get("_meta", XMeta())`, and a
  `_meta: ClassVar[XMeta] = XMeta()` override that needs a `# type: ignore`. Once the merge is right these should become one
  shared mechanism (`packages/pangloss-models/src/pangloss_models/model_bases/`; item "model_bases hooks" in
  `packages/pangloss-models/todo.md`).
- It blocks **meta slots** (`docs/meta-slots.md`) and any use of its merge rules by an optional package.
