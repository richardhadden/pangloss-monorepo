# Form validation in the interface

Written 2026-11-02. An edit form (`ItemForm`, and the dialog that makes an entity from inside a form) is checked in
the browser when Save is pressed, before anything is sent. What is wrong is shown where it is: the name of the field
turns red, with what is wrong under it. A red toast says that the item was not saved. The API's own answer (a 422)
is shown the same way, so the box of problems at the top of the form is gone.

## Plan

1. **Schemas from the exported definitions** (`interface-core/src/schema/validation.ts`). The interface has no
   Pydantic: it has what `pangloss_models.export` writes (`ModelDefinitions`). From it, a
   [valibot](https://valibot.dev) schema is made for a model, as the form holds it:

   | Definition | Schema |
   |---|---|
   | `str` | `string`, with `MinLen`, `MaxLen`, `pattern` |
   | `int` / `float` | `number` (`integer` for an int), with `Ge`, `Gt`, `Le`, `Lt`, `MultipleOf` |
   | `decimal` | a number, or a text that is one (the form keeps a decimal as text) |
   | `date` / `datetime` / `uuid` | ISO date / date and time / UUID text |
   | `enum` / `literal` | `picklist` of the values (and their text: the pills write text) |
   | `typedDict` | an object of its keys, each required |
   | `list` | `array` of the item (with `itemValidators`), the length checks on the list |
   | annotated value | its model's fields, with `value` of the field's `valueType` |
   | embedded | by its `type`, one of the field's `types`, then that model's fields |
   | relation | each item by its `type`, one of the field's options (type variables bound as in the form): an entity is a reference with an `id` (and its edge model's properties); a document, reified relation, conjunction or semantic space its model's fields |
   | label | required on a Document or Entity with `requireLabel` |
   | anything unknown (`unknown`, a type variable of a literal) | accepted |

   Schemas are made lazily (`v.lazy`) and kept per model and binding of type variables, so a model that contains
   itself (a statement in a statement) is no problem. Objects are loose: the form holds keys the API only reads.

2. **What counts as empty** is what `cleanForSave` leaves out: nothing, null, `""`, `{}`, and an entity not yet
   chosen (`{ type }` without an `id`). An empty field is fine if it is not `required` (or is `nullable`); a required
   one says "required". Empty items of a list are left out when saved, so they are not checked and not counted.
   The form, not the cleaned body, is checked, so that the path of a problem is the path of the form.

3. **Problems** (`FieldProblem`: a path of the form, a code, and its numbers) are made from valibot's issues
   (`problemsOf` reads `type`, `requirement`, `expected`, `received`). The codes are few (`required`, `too_short`,
   `too_long`, `too_few`, `too_many`, `too_small` (`Ge`), `must_exceed` (`Gt`), `too_large` (`Le`), `must_be_under` (`Lt`), `not_whole`, `not_multiple`, `not_number`,
   `not_date`, `not_datetime`, `not_uuid`, `not_choice`, `wrong_type`, `type_not_allowed`, `invalid`, `server`),
   each a UI string (`invalid_<code>`), so they can be translated. A 422 of the API is read the same way
   (`serverProblems`): `body` and the names of models in its `loc` are left out.

3a. **Language** (valibot's [i18n](https://valibot.dev/guides/internationalization/)). The texts are the
   `invalid_<code>` slots of `ui.jsonc` (English and German; a project adds languages in its own `ui.jsonc`).
   Before each check, `useSaveChecks` gives valibot the messages of the page's language
   (`setValidationMessages(lang, say)`: one `setGlobalMessage(fn, lang)`, whose function says an issue by its
   code), and checks with `{ lang }`, so each problem's `message` is valibot's, in that language. If the
   language is changed while problems are shown, they are checked again and said in the new one. The codes do
   not depend on the messages: "required" is the only `custom` check, a type not allowed is `never`, and the
   patterns of a decimal and of a date and time are told apart by which `RegExp` they are. `@valibot/i18n` is
   not used: its texts are valibot's own ("Invalid length: Expected >=5 but received 2"), not the interface's,
   and they would be a second place to translate.

4. **Where they are shown.** Each row of a form (a field's name and editor; the title box) registers its path with
   the form's state. A problem belongs to the row with the longest path that it is under: a problem inside a part
   that has no rows of its own (a date in its own editor, a typed dict, an item of a list of texts) is shown at the
   field it is in, with the names of the keys between. The name of the row turns red, and the problems are listed
   under it. Changing a field takes its problems away. A problem that has no row is said in the toast.

5. **Save**: when the form has problems nothing is sent; a red toast says how many, and the first field with a
   problem is scrolled into view. The answer of the API is shown in the same way (a 422 by field; anything else in
   the toast). The amber notice of a 412 (someone saved meanwhile) stays where it is, since it has a button.

## Tests

- `schema/validation.test.ts`: each row of the table above, the empty rules, lists (blank items, lengths), nested
  paths through relations, semantic spaces, type variables, embedded types, edge properties, recursion, and that the
  issue paths are the form's paths; `serverProblems` with the `loc` of a discriminated union.
- `context/form.test.tsx`: problems belong to the nearest row, clear on change.
- `components/form/ItemForm.test.tsx`: Save with a missing required field sends nothing, shows a red toast, marks the
  field red and says why; fixing it and saving sends; a 422 is shown at the field; no box of problems.

## Limits

- Only what the export says is checked. A Pydantic validator written in Python (a `field_validator`, a
  `model_validator`) is not exported, so it is still only the API that says so (and that is shown at the field, too).
- `required` is the base model's. If the `Create` or `Edit` model of a type differs, the API's answer is the truth.
