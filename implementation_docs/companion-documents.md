# Companion documents ✅

**Status: plan of 2026-11-12, built the same day on `reverse-bind-on-create`.** The six questions at the end were
answered by the user the same day: the recommended answer, (a), to each. The places they decide are marked *(decided:
Qn)*. The plan is as written; where the code differs, and what the plan did not say, is in "As built" at the end.

## The problem

A person writing a `Factoid` needs a `Person` who is not in the database yet, and makes one in the dialog that the `+`
of a relation opens. That is the moment to ask for the person's structured name and their gender. These cannot be
fields of `Person`: a name and a gender are *claims made by a source*, so they are statements (`Naming`, `Gendering`)
in a factoid of their own, with its own source, which can be reviewed and disagreed with like any other.

So the dialog that makes the person should also offer a second document, a *companion*: a new `Factoid` holding a
`Naming` and a `Gendering` about the person being made. Its source is taken from the factoid behind the dialog. If the
person fills in anything of it, Save makes the person and the companion factoid, with the new person put in the right
field of each statement, and the factoid labelled by its template. If they fill in nothing, only the person is made, as
now. The same companion is offered when a person is made on their own (the `/Person/new` page), where the source has to
be given by hand.

This has to be generic: any entity, any companion document, any parts, any fields; declared in the models, as field
bindings and label templates are.

## Words

| Word | Meaning |
|---|---|
| **the entity** | What is being made (the `Person`) |
| **the companion** | A new head document offered with it (the `Factoid`) |
| **a part** | A document the companion holds in one of its list fields, prefilled (`Naming`, `Gendering` in `statements`) |
| **the entity's slot** | The relation of a part (or of the companion itself) that the new entity is put in (`Naming.named`) |
| **the outer document** | The document whose form the dialog was opened from (the factoid being written). Absent when the entity is made on its own |
| **a copy** | A value taken from the outer document into the companion (`source`) |

## What is true already, and what this builds on

- **The entity dialog** (`EntityCreateDialog` / `EntityCreateForm` in `interface-core/src/components/form/ModelFields.tsx`)
  makes the entity at its own Save, in a fresh form state (`createItemFormState`), and hands the summary back to the
  field. It knows nothing of the outer document: its `ItemFormProvider` shadows the outer one.
- **Field bindings** copy a parent's value into a child, following until the child's field is changed, and copy a
  relation as a value of its own (a new reified relation): the same rules are wanted for a copy here.
- **Label templates** (`label-templates.md`) already label a `Factoid` from its source and statements, on the client
  as it is typed and on the server on save. A companion needs no template of its own.
- **One transaction can write several heads.** `write_head_node` checks the references of a plan *inside* the
  transaction (`checked_plan`), so a second plan written in the same transaction after a first sees the entity the
  first wrote. What is missing is an operation that does this, and labels for references to something not yet
  committed (`read_labels` reads the database before the transaction).
- **`create_inline`** writes an entity named in a document's payload in the same transaction. It could carry this
  feature (post the companion with the person as `create_new`), but only for entities with `create_with_id` and
  `create_inline`, which most should not need. Not used: *(decided: Q3)*.
- **`newItemFields`** lets an interface module add rows to the new-item form, in the dialog too. It is the wrong hook
  for this (a companion is declared in the models, not by a module), but the dialog already draws module rows, so the
  companion section goes beside them.

## 1. The declaration

On the entity's `Meta`, since the question asked is "when a Person is made, what else is offered?" *(decided: Q1)*.
Names are strings, because the entity is usually declared before the documents that refer to it; they are checked at
`initialise()`.

```python
from pangloss_models import Companion, CompanionPart, CopyFromOuter, Standalone, Within


class Person(Entity, Agent):
    _meta = Entity.Meta(
        create_with_id=True,
        companions=[
            Companion(
                name="naming_and_gender",            # unique among the entity's companions; the key in the API
                document="Factoid",                  # a Document that can be made on its own
                field="statements",                  # its list relation that holds the parts
                parts=[
                    CompanionPart("Naming", entity_field="named"),
                    CompanionPart("Gendering", entity_field="gendered"),
                ],
                copies=[CopyFromOuter("source")],     # outer document's `source` -> the companion's `source`
                offered=[Within("Factoid"), Standalone()],
            )
        ],
    )
```

| Piece | Meaning |
|---|---|
| `Companion.document` | The type of the companion. Must be a concrete `Document` that can be made directly (not `create_directly=False`, not abstract) |
| `Companion.field` + `parts` | The list relation of the companion that holds the parts, and the parts, in order. Each part's type must be one the field can hold (with semantic spaces and conjunctions: not in v1, only a direct member). Without `field`, the companion itself is the one part, and `entity_field` is on the `Companion` |
| `CompanionPart.entity_field` | The relation of the part that the new entity is put in. It must accept the entity's type directly (`Person`, or a trait/parent of it such as `Agent`). Through a wrapper (`InRole[Agent]`, `Identification[...]`): not in v1 |
| `CopyFromOuter(from_field, to_field=from_field)` | A field of the outer document's head, copied into a field of the companion when there is an outer document. A relation is copied as a value of its own, as a binding copies (a new `AtPage` with the same target and page). A dotted path (`"source.target"`) is allowed on both sides |
| `offered` | When the companion is offered (any of them). `Within(*head_types, fields=..., holders=...)`: the outer document's head is one of `head_types` (with the types below them, as `allowed_type_names` of a binding), and optionally the relation the entity is made from is one of `fields` (`"Statement.involves"`, matched with the fields that subclass it) on a document of one of `holders`. `Standalone()`: there is no outer document (the entity's own new page; a module's `NewEntityDialog` with no outer form). Also `Not(Within(...))` to exclude. With no `offered`, both `Within` anything and `Standalone` |

The declaration **is not data**: it goes into `NOT_DATA_KEYS`, so changing it is not a migration. Subclasses of the
entity inherit it (a companion declared on `Agent`'s implementors is declared on each; a subclass may set
`companions=[]` to have none).

**Checks at `initialise()`**, each a `PanglossModelError` naming the entity, the companion and the alternative, with
"Did you mean …?" (as for `FieldBinding`), and the language server underlining the string:

- the document, field, part types and fields exist, and are of the kinds above;
- each `entity_field` accepts the entity's type, and is a single relation, or a list (then the entity is its one
  member);
- each copy's two fields exist, and the value of the one can be validated as the other (checked by type: same field
  type, or the target types of the relation include the source's);
- every `Within` type name is a model or a class above one;
- names are unique among the entity's companions.

## 2. What counts as filled in

The point is that the person need not fill in the companion. So:

- A part is **touched** when the user has changed any of its fields. What the declaration put there (the entity in its
  slot, the copies, the part's own blank defaults) does not count.
- The companion is **written** when at least one part is touched (or, without `field`, the companion itself is
  touched). The parts that are not touched are left out of what is sent. A companion that is written is validated as
  a whole, as any document: a touched `Naming` with a required field left empty is red, and so is an empty `source`
  (when it could not be copied).
- What is not touched is not validated: an untouched `Gendering` with its required `gender` empty does not stop Save.
- Touched-ness is the client's: the server only sees what is sent, and writes a companion with no parts only if the
  model allows an empty list there (`statements: []`), which the client never sends.

## 3. The backend: several heads in one transaction

A new storage operation, used by this and available to others (an import that must be all-or-nothing):

```python
await storage.create_heads([person_create, factoid_create])   # pangloss_core's Storage: the operation, for any backend
```

- **One transaction**: each item's plan is written in order, checked against what is before it in the transaction, so
  a later item may refer to an earlier one by its id. Any failure rolls everything back. (`write_with_retries` around
  the whole.)
- **Ids**: the entity's id is given by the server before the companion's payload is completed (the API does this), so
  this needs no `create_with_id` on the entity.
- **Labels**: `fill_labels` of a later item is given the labels of the earlier ones (their `CreateDB`s), as a
  `create_new` entity supplies its own, before `read_labels` is asked for the rest.
- **Checks**: `check_before_create` of each, in order, before the transaction. A `@before_create` that reads the
  database does not see the earlier items (they are not written yet): said in the docs, not worked round.
- **After commit**: one `announce("create", …)` per head, in order, so history records each as created at version 1,
  and review makes the companion `unchecked` (a `Factoid` is reviewable) as it would any new one. Creators
  (`created_by`, `toolchain`) apply to all.
- **Where**: `pangloss-cypher` (`write_heads`, sharing `checked_plan`, `render`, `pending.mark_written`), so both
  backends have it; the SDK's storage sends it to the API (section 4).
- **Conformance tests** (`pangloss_testing/conformance/`): two heads, the second referring to the first; a failure of
  the second leaves neither; the label of the second names the first; one event each, in order; a review status per
  class.

## 4. The API and Python

**Route** *(decided: Q3)*: `POST /api/NAME/with-companions`, logged in, for an entity class with companions:

```json
{
  "item": { "label": "John of Gaunt", "knownAs": { ... }, ... },
  "companions": [
    { "name": "naming_and_gender",
      "document": { "source": { "type": "AtPage", "page": "12", "target": [ ... ] },
                    "statements": [ { "type": "Naming", "firstName": "John", "familyName": "of Gaunt", "title": "Duke of Lancaster", ... } ] } }
  ]
}
```

The server:

1. finds each companion by `name` among those the class declares (422 naming it, and those there are, if not);
2. checks each part is of a declared part type, each at most once (422 otherwise; *(decided: Q5)*);
3. gives the entity its id, and puts `{"type": NAME, "id": …}` in each part's slot, refusing a slot the client filled
   with anything else (422: the slot is the server's to fill);
4. validates `item` as `NAME.Create` and each companion as its `Create` (a 422's `loc` starts `["body", "item", …]` or
   `["body", "companions", i, "document", …]`, so the form finds the field);
5. writes them together (section 3), and answers 201 with `{"item": ReferenceView, "companions": [ReferenceView]}`.

The server does **not** check `offered`: that says where the interface offers a companion, not what may be written. Any
declared companion may be sent (an SDK script making people with their namings).

`POST /api/NAME` is unchanged; the interface uses it when no companion is filled in.

**Python and the SDK**: `await Person.Create(...).save_with_companions({"naming_and_gender": {...}})`, taking the
companions as dicts (the slot cannot be filled before the id exists, so a `Factoid.Create` cannot be built first),
giving `(person, [factoid])`. Run over HTTP in the SDK by the route above. `create_heads` is public as well, for writes
that give their own ids.

**Export**: each entity's definition gets `companions` (name, document, field, parts with their slots, copies,
offered, as resolved names), typed in `interface-core/src/types/models.ts` and guarded by
`test_models_match_typescript.py`. Left out for a model without companions.

## 5. The interface

### Where the dialog was opened from

`PickOrCreate` (and so the dialog) learns its **creation context** from the form it is in: the outer form's state (to
read the copies from), the head's type, the relation's field and the type of the document holding it. A small context,
`CreationContext`, given by `ItemForm` and read by `PickOrCreate` *before* the dialog's own `ItemFormProvider`
shadows the outer one. On the entity's own new page there is none (`Standalone`).

### Pure functions (`schema/companions.ts`, Vitest without a DOM)

- `offeredCompanions(definitions, entityType, context)`: which companions to offer, by `offered`, with the types below
  (sharing `classNames` / `applies` with `schema/binding.ts`, so a binding and a companion match types the same way).
- `startCompanion(definitions, companion, context)`: the blank companion, with its parts (blank items of their types),
  the copies made from the outer state (a relation as a value of its own), and the slots marked.
- `companionsToSend(state)`: the touched parts only, the slots left for the server, the untouched companions dropped.

### The dialog

`EntityCreateForm` shows, under the entity's fields, a **section for each companion offered**:

- its head bar: the companion's type chip (`Factoid`, in its colour, with `data-type-info`) and, as joined chips, the
  part types; a short line from the companion's translation slot (below) saying what it is for ("Optional: what the
  source says of the person's name and gender").
- its own form state (one per companion: so the companion has its own binder, its own labels worked out by template,
  its own validation), drawn with `ModelFields`: the companion's fields (`source`, copied and editable *(decided: Q4)*),
  then each part as a nested block, as in the factoid's own form.
- **the slot** in each part is not a picker but a `ReferenceChip` of the entity being made, without a link, its label
  following what is typed in the entity's label box (and its label template, if the entity has one), marked as new.
  It cannot be removed or changed.
- the companion's label is the automatic one, worked out as the parts are typed, with the new entity's label in it.
- a part cannot be removed or added (the declared ones, once each) *(decided: Q5)*; an untouched part is drawn quieter
  (its hairline dashed, as a block not yet filled is elsewhere) so it reads as optional.

**Save**: the entity's checks, then each touched companion's. No companion touched: `POST /api/NAME` as now. Otherwise
`POST /api/NAME/with-companions`; a 422 is shown in the form it belongs to (the `loc` prefix decides). The toast names
both: `Person “John of Gaunt” created, with Factoid “Chronicle, p. 12: John of Gaunt named …”`, each a chip. The entity
is handed back to the field as now; the companion is not part of the outer document and nothing of it goes there.

**Unsaved changes**: a touched companion is a change of the dialog's form (the dialog's Cancel asks, as the form does).
Entities are not stashed, so the stash is not touched.

**Nested**: a picker inside the companion (another person in a `Naming`) can make an entity of its own, with the
companion as its outer document. Nothing stops this, and nothing special is needed.

### On the entity's own page

`/Person/new` shows the same sections after the fields (context `Standalone`), with nothing copied: the source has to
be given if the companion is filled in. The same `schema/companions.ts` and the same section component, so the page and
the dialog cannot drift. The edit page of an existing person shows none *(decided: Q6)*.

### Text

The section's line is a slot per companion in `models.jsonc` (`companions.Person.naming_and_gender`), which
`pangloss interface translations generate` adds; its fixed words (`companion_optional`, the toast) are `t()` slots in
`ui.jsonc` with English, German and French.

## 6. The demo

- `Naming(Statement)`: `named: Person` (subclassing `involves`) and the three fields the user chose (2026-11-12):
  `first_name`, `family_name` and `title`, each `str | None = None` (a source may give only one of
  them). A label template such as
  `"{named}: [{title} ][{first_name}][ {family_name}]"`. `Gendering(Statement)`: `gendered: Person`, `gender: Gender` (an
  enum). Both added to what `Factoid.statements` holds (through `Statement`, they already are).
- `Statement.text` is required with `MinLen(5)`, so a touched `Naming` would need its text typed. At build time, see
  whether a subclass may give it a default; if not, say so to the user rather than loosen `Statement`.
- `Person._meta` gets the companion above. Migration (the new classes), stubs again.

## Steps

| # | What | Where | Tests |
|---|---|---|---|
| 0 | Demo models `Naming`, `Gendering`; migration; stubs | `pangloss-demo/` | `pangloss check` |
| 1 | `Companion`, `CompanionPart`, `CopyFromOuter`, `Within`, `Standalone`, `Not`; `Entity.Meta(companions=)`; checks at `initialise()`; `NOT_DATA_KEYS`; LSP diagnostics for the names | `pangloss-models`, `pangloss-lsp` | `test_companions.py` (each refusal), LSP case |
| 2 | Export of `companions`; TS types | `pangloss-models`, `interface-core/types` | `test_models_match_typescript.py`, export snapshot |
| 3 | `create_heads` / `write_heads`: one transaction, labels of the earlier items, events in order | `pangloss-core` (Storage), `pangloss-cypher` | conformance, both backends |
| 4 | The route; slots filled by the server; 422 locations; `save_with_companions`; SDK | `pangloss-api`, `pangloss-models`, `pangloss-sdk` | API tests; SDK test; history and review see two creates |
| 5 | `schema/companions.ts` | `interface-core` | Vitest |
| 6 | `CreationContext`; the companion section; the slot chip; Save, errors, toast; the dialog | `interface-core` | Vitest (`ItemForm.test.tsx`, a new `Companions.test.tsx`) |
| 7 | The new-entity page | `interface-app`, `interface-core` | Vitest |
| 8 | Strings; screenshots on the demo (dialog, 4x of the slot chip and the part blocks); dev build | translations, `e2e/` | `e2e/test_companions.py` (fill a naming in the dialog from a factoid, save, see both; leave it empty, only the person), `test_dev_mode.py`, `e2e/COVERAGE.md` |
| 9 | Docs: this page's "As built", `models.md` (the `Meta` option), `api.md` (the route), `relations.md` (beside field binding), the guide, `status.md`, `TODO.md`, the skill | | `check_skill.py` |

Steps 1–4 can be finished, tested and committed before any interface work; 5–7 depend on 2 and 4.

## Not in this plan (for later)

- Parts reached through wrappers: the entity's slot inside `InRole[...]` or `Identification[...]`, a part inside a
  `Negative[...]`.
- A companion for an existing entity: on the person's page, "New Factoid: naming and gender" opening the factoid's new
  form with the parts and the person filled in. (Cheap once `startCompanion` exists: a console action.)
- Companions of a document made in a dialog (`createTypes` of `PickOrCreate`), not only of entities.
- Writing the companion when the outer document is saved instead of with the entity (Q2, if the answer changes).
- Bulk-load and `create_inline` do not offer companions: they write what the file says.

## Decisions (2026-11-12)

The user chose (a) for every question: declared on the entity's `Meta`; written with the entity at the
dialog's Save, in one transaction; by a new several-heads operation and route; the copied source shown, filled in and
editable; exactly the declared parts, once each; not offered when editing an existing entity (later, as a console
action). The questions as they were asked:

1. **Where it is declared.** (a) On the entity's `Meta`, names as strings; (b) on the companion document's `Meta`
   (`companion_of="Person"`); (c) in a project file of their own (`companions.py`), outside both.
2. **When the companion is written.** (a) With the entity, at the dialog's Save, in one transaction; (b) held in the
   outer form and written when the outer document is saved (its source then final; but held state, stash and a
   person made without their naming if the outer one is abandoned).
3. **How it is written.** (a) A new operation for several heads in one transaction, and the route above; (b) no new
   backend operation: the interface posts the companion with the entity in it as `create_new` (atomic, but only for
   entities with `create_with_id` and `create_inline`); (c) two requests, the entity and then the companion (not
   atomic: a failed second leaves a person without their naming).
4. **The copied values (the source) in the dialog.** (a) Shown, filled in, editable; (b) shown, locked; (c) not shown.
5. **The parts.** (a) Exactly the declared ones, once each; (b) the declared ones to start with, and the user may add
   more (a second naming) or other types the field holds.
6. **Offered when editing an existing entity.** (a) Not now (the "for later" console action); (b) yes, as a section of
   the edit page, writing a new companion on save.


## As built (2026-11-12)

Where the code is:

| What | Where |
|---|---|
| The declaration (`Companion`, `CompanionPart`, `CopyFromOuter`, `Within`, `Standalone`), `companions_of`, `companion_create`, `save_with_companions` | `pangloss_models/companions.py` |
| `Entity.Meta(companions=[...])` | `pangloss_models/model_bases/entity.py` |
| The checks at `initialise()` | `pangloss_models/initialise_models/check_companions.py` |
| The export (`companions` of an entity) | `export_companion` in `pangloss_models/export.py`; `CompanionDefinition` in `interface-core/src/types/models.ts` |
| Several heads in one transaction | `pangloss_models.create_heads` (`together.py`, bound at initialise) → `create_heads`, `write_head_nodes` in `pangloss_cypher/write_functions.py` |
| The route | `add_with_companions_route` in `pangloss_api/routes/models.py` |
| The SDK | `save_with_companions` in `pangloss_sdk/databases/api*/exposed_functions.py`, `protocol.create_with_companions` |
| What is offered, started, changed and sent | `interface-core/src/schema/companions.ts` |
| The dialog, the page, the sections | `useCompanions`, `CompanionSections`, `EntityCreateForm` in `components/form/ModelFields.tsx`; `ItemForm.tsx` |
| Tests | `pangloss-models/tests/initialisation/test_companion_declarations.py`, `tests/test_companion_payloads.py`, `test_export_models.py`; conformance `test_create_heads.py`, `test_companions_live.py`, `test_query_costs.py`, `test_sdk_contract.py`, `test_review_live.py`; `pangloss-cli/tests/test_check_command.py` (the underline); Vitest `companions.test.ts`, `Companions.test.tsx`; `e2e/test_companions.py`, `test_dev_mode.py` |

Where it differs from the plan, or what the plan did not say:

- **Every argument is a keyword**: `CompanionPart(type="Naming", entity_field="named")`, `CopyFromOuter(field="source")`,
  `Within(heads=["Factoid"], fields=["Statement.involves"], holders=["Statement"])`. The language server finds the
  string a refusal is about by the keyword it is given to; a positional string it cannot find.
- **No `Not(...)`**: `Not` is already a public name (a search condition), and nothing needed it. A copy names one field
  each side, **not a dotted path**.
- **`create_heads` is a function of `pangloss_models`** (`from pangloss_models import create_heads`), bound to the
  storage's operation when the models are initialised, not a method of `Storage`. The SDK has no `create_heads` (it
  would need a route of its own); it has `save_with_companions`, which goes through the companions' route.
- **A refusal says which head it was about**: `create_heads` marks a `PanglossWriteRefused` of a label template or a
  `@before_create` with `item_index`, so that the route can place it under `item` or `companions[i].document`.
- **The server checks** that a part is declared and given once, and that the entity's field was left to it (one given
  that is not the new entity is refused; its own reference may be sent). A companion with no parts is refused: the
  interface does not send it.
- **What counts as changed** leaves out, besides the entity and the copies, every `label`, `labelAuto`, `id` and `meta`
  (a label its template works out again as the entity's name is typed is not a change of the user's). A part typed in
  and emptied again is changed, and checked as a whole.
- **The form**: `ItemFormOptions.fixed(path)` says which relations hold what the form was given. The new entity in a
  part is a `ReferenceChip` with no link and no buttons, "The new Person" until a label is typed; the parts of a
  companion cannot be added to, removed, cut or retyped (↧/↥). The companion is checked as it is sent, with the entity
  kept in so that a required place for it is met (`useSaveChecks` takes the item to check and where its problems go).
- **The section's line is one text slot** (`companion_offered`, "Also made with the Person, if anything in it is filled
  in"), not a slot per companion in `models.jsonc`. A text of each companion's own is for later.
- **A module that sends a new entity its own way** (`NewItemForm.sendBy`) cannot take companions with it: Save says so
  (`companion_not_sent`) and sends nothing, rather than making the entity without them.
- **The demo** needed two things the plan had foreseen as possible: `Naming` and `Gendering` make the inherited `text`
  and `date` of a `Statement` optional (a subclass may), and `pangloss-dates` now lets a class below a `Dateable` one
  have no date (the copies of the date are then empty). The demo's database is not migrated (migration 0017).
- **Not measured** on a large database: `create_heads` is one transaction of the statements of each head (the cost
  test holds it to that), and the route adds nothing that reads.

Not done:

- The demo's `models.jsonc` has no names for `Naming`, `Gendering` and their fields: `pangloss interface translations
  generate` would also rewrite much else that has drifted in that file, which is left for the user to run.
- What is in "Not in this plan (for later)" above.
