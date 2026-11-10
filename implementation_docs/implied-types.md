# Implied types: narrowing a document by what a field holds 🚧

**Status (2026-11-05): the interface part is built: ↧ offers only narrowings that lose nothing (the others greyed,
saying why), and the properties of a relation are counted as lost when a retype drops them. The suggestion of a
narrower type without being asked, `defining` fields and a read-only check command are not built, and may not be
needed. The backend narrowing first planned was considered and not chosen (reasons below). Field bindings
now reach narrowed documents (their types include the types below; their fields, the fields that stand for them); entity class changes would
meet narrowed documents, but entities do not change class today (Zotero's excepted).**

## The problem

In the demo:

```python
class CreationOfPhysicalObject(Statement):
    created_by: Annotated[Person, RelationConfig(subclasses_parent_fields=[FieldSubclassing("involves", Statement)])]
    object_created: PhysicalObject

class CreationOfArtwork(CreationOfPhysicalObject):
    artwork_created: Annotated[Artwork, RelationConfig(subclasses_parent_fields=[
        FieldSubclassing("object_created", CreationOfPhysicalObject)])]

class CreationOfPainting(CreationOfArtwork):
    painting_created: Annotated[Painting, RelationConfig(subclasses_parent_fields=[
        FieldSubclassing("artwork_created", CreationOfArtwork)])]
```

A `CreationOfPhysicalObject` whose `object_created` is a `Painting` is valid, but whoever wrote it meant a
`CreationOfPainting`. The question was how Pangloss could know that, and what it should do about it: suggest the
narrower type in the interface, narrow by itself on the backend, check existing data with a command, and mark for
review where a narrower type needs more fields.

## What already existed

| What | Where | What it gives |
|---|---|---|
| Field subclassing | `FieldSubclassing`, `normalise_and_get_subclassed_fields` (`initialise_field_definitions.py`) | The map "field of the narrower type ↔ field of the parent it stands for" (`painting_created` → `artwork_created` → `object_created`), transitive |
| Edge pairs for subclassed fields | `edge_names` (`pangloss_cypher/write_plan.py`) | A `CreationOfPainting` is written with `painting_created`, `artwork_created` *and* `object_created` edges, and the labels of all its parents. So **narrowing never removes anything a query over the parent finds** |
| Retyping a nested document | `schema/retype.ts`, `form/Retype.tsx` (↧/↥) | Carrying values between types through `subclasses`, the "this will be lost" dialog |
| A nested document keeps its id under a new type | conformance `test_update_changes_the_type_of_a_nested_document_that_keeps_its_id` | The save of a retype |
| Class change of an **entity** in place | `changing_class_from` (`write_functions.py`, `test_change_class.py`) | Refused for documents (`test_only_an_entity_changes_class`) |

## Built: a narrowing that never loses anything ✅

The form's ↧ (narrow) offers a type below only if what is filled in fits it. `narrowingChoices(definitions, value,
options)` (`schema/retype.ts`) gives each type below that the field allows, with what `retype` would lose there. A
type with nothing to lose can be chosen; the others are in the menu greyed, with "Would lose: Object created" under
the name (`TypeMenu`'s `unavailable`: a `menuitem` with `aria-disabled`, which the arrow keys reach and a click does
not choose). With a painting chosen, both `CreationOfArtwork` and `CreationOfPainting` can be chosen; with an
artwork, only `CreationOfArtwork`; with nothing chosen yet, both (the object is chosen after). Nothing is declared
for this: the rule is only "would anything filled in be lost?".

What counts as lost:

- a thing in a field that the narrower type's field cannot hold (an artwork where only a painting can go);
- all but one of a list, where the narrower field holds one (two people at an event, one chair of a meeting);
- **the properties of a relation** (`ViaEdge[Person, Certainty]`) whose new field has another edge model, or none.
  `fitEdge` (`schema/clipboard.ts`) dropped them before, and `retype` did not count them, so ↧ and ↥ lost them
  **without saying so**. They are now a `LostField` with `edgeProperties: true` ("Present: the properties of the
  relation"), counted only where a property is filled in.

A widening (↥) can still lose something (a field only the narrower type has, the properties of a relation): it asks
first in its dialog, as before, now naming lost relation properties too. A narrowing never needs the dialog.

For the user: a narrowing cannot be made while the value contradicts the type (change the object first, then
narrow); and with a type below that cannot be chosen, ↧ is a menu saying why, even when only one other can be.

Tests: Vitest `retype.test.ts` (the choices: artwork, painting, nothing chosen, a field that does not allow the type,
list to one, relation properties to none, the same and another edge model), `TypeMenu.test.tsx` (greyed, reason,
arrow keys, not chosen, menu or button), `Retype.test.tsx` (in the form: greyed and not chosen, a painting all the
way and saved, nothing chosen, relation properties in the menu and in the widening dialog); e2e `test_retype.py`
(the e2e project's `Provenance` of `CreationOfPhysicalObject` > `CreationOfArtwork` > `CreationOfPainting`: greyed
with its reason, not chosen, the other chosen and saved as the same node; a painting narrowed all the way, then
widened back with the medium lost after the dialog); dev build `test_narrowing_and_widening_a_document_in_a_form`.

## Not built, and perhaps not needed ⏳

### A suggestion without being asked, and `defining` fields

With ↧ filtered by fit, a person who opens ↧ with a painting chosen finds `CreationOfPainting`; what they are not
given is a prompt ("This is a Creation of Painting?"). A prompt needs to know **which** narrowing carries the meaning,
because suggesting every type that fits is wrong: a `Statement` that involves a person would be offered `Activity`,
`Transfer`, `MemberOf`, which mean other things, and a `CreationByWorkshop` that narrows `created_by` would be pushed
at every creation by a workshop. Only the modeller knows, so it would be declared: `RelationConfig(defining=True)` on
the parent's field (`object_created`), inherited by the fields that subclass it.

If built: a strip under the nested document's head bar offers the most specific type among `narrowingChoices` that
narrows a defining field with the value (several where the value fits more than one, as for a union); dismissing it
is forgotten with the form. A project-wide switch and a per-class one were asked for, and would be: a setting
`IMPLIED_TYPES = "suggest" | "off"` and `Document.Meta(implied_types=...)` on the class narrowed from, inherited, the
`Meta` winning (so "only these types" is the setting off and the `Meta` on). Worked out at `initialise()` and
exported; not data, so no migration.

**Decision so far:** wait, and add the prompt only if people miss narrower types in practice.

### A read-only check of existing data

`pangloss narrow check [MODEL]`: what in the database could be narrowed with nothing lost, what by more than one
type, and what would need fields; it writes nothing. Finding them is a query per (class, field, narrower class) for
nested nodes of the class and not the narrower one whose field's edge goes to a node of the narrower field's class: a
storage operation in `pangloss-cypher` (both backends), measured on the 640,000-node database before it is relied on.
It would need `defining` too (or it reports every fitting subclass). Its findings are what the first **Review Jobs**
would be made of (below).

## Considered, and not chosen: narrowing on the backend

The first plan narrowed nested documents on every write (create and update, in the model layer, so Python, the API
and the SDK alike) where exactly one narrower class was implied and needed nothing more, with a command to apply it to
existing data. The user's answers to that plan were: nested documents only (no class change in place for documents);
create and update, with a stored `keep_type` marker set when a person widens or dismisses; narrow as far as can be
done automatically and report the rest; in the core; and a global and a per-class switch (`auto`/`suggest`/`off`).

It was dropped because nearly everything that could go wrong came from the backend changing a type by itself:

1. **Meaning.** A subclass may mean more than its field's type ("a creation of a painting" may exclude a print of a
   painting, a copy). A person shown a choice catches that; a silent rewrite does not.
2. **A deliberate broad type is undone.** A person widens a `CreationOfPainting` and saves; the backend narrows it
   back. Hence the stored `keep_type` marker: new data, and rules for when it is cleared.
3. **The reference understates the class.** A payload may say `{"type": "PhysicalObject", "id": …}` of what is a
   `Painting` (the write's check accepts it by label: `check_references_exist`), so the backend would need a lookup of
   the classes of everything referred to.
4. **Ambiguity** (two defining fields narrowed by unrelated subclasses; a list of mixed classes) can never be decided
   by the backend; a person can be offered both.
5. **Partial narrowing** (to `CreationOfArtwork` because `CreationOfPainting` needs a field) is a half-step nobody
   asked for.
6. **Clients see a type they did not send**, and the history shows changes nobody made.
7. **Two rules to keep in step** (Python on the write path, TypeScript in the form) for nothing the interface does not
   already give.

What it was for (data from the API, and existing data) is better served deliberately: the read-only check above;
for an import script, a Python `narrow(doc)` it can call before saving (its own choice, visible where it is made); and
if bulk narrowing is ever wanted, `pangloss narrow apply`, run on purpose after reading the check's report.

## Two problems narrowing brings with it (investigated 2026-11-05) ⏳

The first (class changes) is only for later: entities do not change class today, except Zotero's, which is excluded.
The second (field bindings) applies now, to ↧ as built, and to any subclass that narrows a bound field. Neither is
fixed.

### A class change refused by a narrowed document

**What happens now** (`pangloss_cypher/write_functions.py`): `check_class_change` reads what refers to the entity as
its old class (`referrers`, through `fetch_incoming_relations`). After the change, `check_references_kept` reads it
again as the new class and raises `PanglossClassChangeError` (409) for anything lost. A `CreationOfPainting` still has
its `object_created` edge, but `read_incoming` counts a relation that a subclass narrows only under the narrower name,
so read as an `Artwork` the painting's creation is lost, and the change is refused. The message names the relation,
and the type and id of the **nested** document (`painting_created (CreationOfPainting <id>)`). A nested document
cannot be opened on its own, so the user is not told which head to edit, although `head_node_id` and
`head_node_type` are on the node (`read_incoming.py` strips them as `INTERNAL_KEYS`).

**This does not happen today** (checked 2026-11-05). The only caller of `changing_class_from` is Zotero's base-on and
link (`pangloss_zotero/link.py`), which makes an item of the fallback class (`ZoteroObject`) a project class (`Book`);
it is Zotero's own concern, and excluded here. History's restore does not change a class: it refuses a version from
before a class change (`restore.py`; conformance `test_a_version_from_before_a_class_change_is_not_restored`). A
narrowing changes the type of a document, never of the entity it refers to. So what follows is **for later**: it
matters only if a general "change the class of this entity" is ever added, which would meet narrowed documents.

**Solutions, in order of cost:**

1. **Say what is in the way, by its head.** `PanglossClassChangeError` carries a list of blockers: the relation, the
   nested document's type and id, its **head**'s type, id and label, and the class it could be widened to (below).
   The API gives them in the 409's body. The interface shows them as `ReferenceChip`s to the heads, so the user can
   open each and widen with ↥. Small; worth doing first, whatever else is chosen.
2. **Widen in the same change.** The class change takes `widen_referrers=True`. For each blocker it works out the
   most specific ancestor of the nested document's class whose field can hold the new class. That is the implied
   rule run upwards: for an `Artwork`, `CreationOfArtwork`. It retypes the document to that class, with the `retype`
   carrying rules in Python. All of it happens in the class change's transaction, so either everything changes or
   nothing does. Each head gets a new version and its own history record, with a note that it was widened because
   entity X changed class. A widening that would lose something (a field only the narrower class has, holding a
   value) is refused, and that blocker is named as in 1. The interface's dialog for the 409 offers "Widen these
   documents and change the class". **Cost:** a storage operation that rewrites several heads in one transaction
   (today `replace_head_node` writes one), with a conformance test on both backends.
3. **The interface does it step by step.** It widens each head with an ordinary update, then tries the class change
   again. No new storage operation, but it is not atomic: if the class change still fails, the documents stay
   widened. Widening loses nothing, so that is not harmful, but it is a change nobody asked for. Not recommended
   over 2, except as a stopgap.

Widening a blocker is `retype` run upwards in Python: the carrying rules of `schema/retype.ts` written again in
`pangloss_models`, with one table of cases (JSON) that pytest and Vitest both run, so that the two stay in step.

### Field bindings across a narrowed document

**What happened** (before 2026-11-05). Both binders matched by **exact names**:

- Python (`pangloss_models/model_bases/binding.py`): a child was bound if `item.type` was in `allowed_type_names`
  (exactly) and not in `excluded_type_names`, and only into a field the child has **by that name**
  (`hasattr(item, child_bound_field)`).
- The interface (`schema/binding.ts`): the same, with `binding.allowedTypes.includes(type)` and
  `model.fields.some(field => field.key === key)`.
- The builder (`field_has_inherited_field_bindings`, `utils.py`) relaxes a child's field in `Create` when a binding
  will fill it, by the same exact names.

Both are fixed (2026-11-05): the type names include the types below them (solution 2), and the field names reach
the fields that stand for them (solution 1). The note at a field whose bound value does not fit (3) is built too.

A narrowed child does not have its parent's field under the old name: the narrower class has `painting_created` in
place of `object_created` (`get_fields_on_model` removes subclassed fields). So:

| Binding declares | Before narrowing | After narrowing to `CreationOfPainting` |
|---|---|---|
| `child_fields=["object_created"]` | bound | was silently not bound (no field of that name); **fixed**: `painting_created` is bound |
| `allowed_type_names=["CreationOfPhysicalObject"]` | applies | stopped applying (the name was not in the list); **fixed**: applies |
| `excluded_type_names=["CreationOfPhysicalObject"]` | does not apply | started applying; **fixed**: does not apply |

This is not new. It is already true of the ↧ button, and of any subclass that narrows a bound field: a binding into
`Statement.involves` does not reach a `CreationOfPhysicalObject` (`created_by` stands for it) or an `Activity`
(`carried_out_by`). The demo's one binding (`Order.ordered_to` into `given_by`, `ordered_by`) uses no names that a
subclass renames, so nothing shows it.

**Solutions:**

1. **Bind through subclassing.** ✅ Built 2026-11-05. A binding into field `f` gives a child's field `g` when `g` is
   `f`, or `g` subclasses `f` (transitively: the normalised `subclasses_parent_fields` in Python, `subclasses` in the
   export, looked up by name on the types above for the key). The same rule is in all three places: the binder
   (`fields_bound`), the builder's relaxation (`bound_names`: the narrower field need not be given where a binding
   fills it) and the interface's binder (`fieldsBound`). A value the narrower field cannot hold (an artwork bound to
   the painting created): on the server, the binder gives it and the field's validation refuses it, so the write fails
   with a 422 naming the field (never written empty); in the form, it is not given, and a field that was following the
   binding is emptied, so that it is filled in by hand rather than keeping a value the bound field no longer has.
   Tests: `test_binding_rules.py` (the names stood for, transitively; `Create` and `Update` into each narrower field;
   not required inside the commission, required on its own; a value given kept; an artwork refused for the painting
   created), `form.test.ts` (each narrower field given and following; one that cannot hold it not given, emptied, filled
   again; a child narrowed as ↧ does it still follows), e2e `test_retype.py` (the e2e project's `Provenance.subject`
   bound into `object_created`: a creation of a painting added in the form has the subject as its painting created and
   is saved so; the API fills it for a payload without it, and refuses an artwork with 422).
2. **Type names include their subclasses.** ✅ Built 2026-11-05 (the user's decision: they should).
   `allowed_type_names` and `excluded_type_names` match a class, anything below it, and a trait it has; one below an
   excluded type is excluded even if it is below an allowed one. In the binder, the builder's relaxation and the
   interface's binder alike (`binding_applies` and `class_names` in `model_bases/binding.py`; `applies` in
   `schema/binding.ts`, from the export's `parent` and `traits`; the library's bases, `Document`, are not names). So
   narrowing or widening a child does not change whether a binding applies, as long as it stays below what is
   allowed. Tests: `test_binding_rules.py` (the rule; `Create` and `Update` with subclasses of allowed and excluded
   types; the field relaxed or required), `form.test.ts` (the form; a child narrowed, then widened out of what is
   allowed). It changed the meaning of existing declarations: none in the repository relied on exact matching.
3. **A bound value that does not fit a narrowed child.** ✅ Built 2026-11-05. The form says so at the field, in red
   with its problems: "The thing is given to this from above, but cannot go here: choose one that can" (the problem
   code `bound_not_held`, `invalid_bound_not_held`). It is worked out from the item as it is (`bindingNotices` in
   `schema/binding.ts`, through a new `FormHook.notices`; a memo in the form's state that `problemsAt` adds to the
   problems found on save), so it is there whether the field was never given the value or was emptied when the value
   changed, and goes when the field is filled in or the bound value changes to one that fits. It is not a problem of
   the save: the save's own check says "Required" beside it. Tests: `formNotices.test.ts` (in the browser build of
   Solid: in the server's build, which `form.test.ts` uses, a memo is never worked out again), e2e
   `test_a_step_that_cannot_hold_the_subject_says_so_at_its_field`, dev build.
4. **A binding and ↧.** A bound value counts as filled in, so it decides which narrowings can be chosen exactly as a
   chosen one does (a child bound to an artwork cannot be narrowed to a creation of a painting). That is right, and
   needs nothing beyond a test. (If the unasked suggestion is ever built, a bound value prompts it the same way.)

All four are built or need nothing more.

## Open questions

- (For later, if entities can ever change class generally: widen the documents in the way in one transaction, or
  only name them.)

## Review Jobs (noted, not designed)

A later part of `pangloss-review`: jobs that find documents to look at and attach a mark to a part of one, shown in
the review panel and the queue. The first job would be the check's "could be a `<type>`" (needs fields, or
ambiguous). Not designed yet.
