# Label templates ⏳

**Status: plan, 2026-11-11. Nothing is built.**

Each nested document now needs a label typed by hand, and the label usually just repeats what the document holds. A
label template says how to build the label from the fields. The label is worked out on the client as the user types
and again on the server when the document is saved; the stored label is the server's. A user can unlock the label and
write their own.

## Decisions taken (2026-11-11)

1. **A derived label is stored as it was when it was made.** If an entity it names is renamed later, the label stays
   as it was. A background job that updates derived labels when something they name changes is for later (`TODO.md`).
2. **A small template language**, not named functions, interpreted in Python and in TypeScript.
3. **Entities can have templates too** (`"{surname}, {forename}"`), by the same mechanism.
4. **One language.** A template's fixed text is stored as written. Labels in several languages are for later
   (`TODO.md`).
5. **Which kinds store a label:** a `ReifiedRelation` never has a label. A `ReifiedRelationDocument` always does (it
   acts as a document at times), and in a folded block it shows its label, derived or written.

## Declaring

```python
class Birth(Document):
    person: Person
    place: Place | None
    date: Date | None

    _meta = Document.Meta(label_template="Birth of {person}[ at {place}][, {date}]")


class Will(Document):
    testator: Person
    bequests: list[Bequest]          # nested documents

    _meta = Document.Meta(
        label_template='Will of {testator}[: {bequests|each("{item} to {recipient}")|join("; ")}]'
    )
```

`label_template` is a `Meta` option on every kind of model, and subclasses inherit it. `LabelTemplate("…", "…")` gives
alternatives, tried in order. What happens to the result depends on the kind:

| Kind | What the template is for |
|---|---|
| `Document`, `ReifiedRelationDocument`, `Entity` | Stored as the node's label, unless a user wrote their own |
| `ReifiedRelation`, `Conjunction`, `SemanticSpace`, `Embedded` | Not stored: only how it reads inside another's template |

## The language

```
template    := (text | placeholder | group)*
placeholder := "{" path ("|" filter)* "}"
path        := name ("." name)*                    # Python field names: bequests.recipient
group       := "[" template "]"                    # left out if any placeholder in it is empty
filter      := join("sep") | first | last | count | default("text") | each("template")
escapes     := \{ \} \[ \] \\
```

- **Optional parts are groups.** `[ at {place}]` is left out when there is no place, so a model with optional fields
  needs one template, not one for each combination. The alternatives of `LabelTemplate(a, b, …)` are for different
  wording: the first is taken that has no empty placeholder outside a group.
- **A required template that gives nothing** (an empty string after the groups are dropped) is refused on save with a
  `PanglossWriteError`, unless a label was written by hand.

### How a value becomes text

This is your question 2: what happens when a placeholder points at nested documents. There are three ways in, from
least to most explicit:

| `{x}` is | Its text |
|---|---|
| a literal | the value (`str`; numbers as written; an enum by its value; a `date` as ISO). A `bool` is refused at `initialise()` |
| a reference to an entity or document | its label (on the client from the chip; on the server read from the database, see below) |
| a nested document, entity or `ReifiedRelationDocument` | **its label**, derived (worked out first, from the innermost outwards) or written by hand |
| a `ReifiedRelation`, `Conjunction` or `SemanticSpace` | its own template if it has one; if not, what it holds, by the rule of the folded bar (`labelledContents` in `collapse.ts`: a reified relation's `target`, a conjunction's relations), joined with `", "` |
| an `Embedded` object | its template, or a **formatter** named by its app (`pangloss_dates:date`, see below). Neither: refused at `initialise()` |
| a list | its items, each as above, joined with `", "`, unless a filter says otherwise |

So the contents of a nested document reach the outer label in one of three ways:

1. **`{bequests}`**: each bequest by its own label (which its own template may derive).
2. **`{bequests.recipient}`**: a path into the nested documents. Through a list, this gives one value for each item.
3. **`{bequests|each("{item} to {recipient}")}`**: an inline template run on each item, with paths starting from that
   item.

What sets the nested contents apart is the template's own fixed text. Brackets and separators are written into the
template, for example `[ ({witnesses|join("; ")})]`. There is no built-in quoting.

`initialise()` checks every path against each model it applies to, including every member of a union and every
subclass, and checks that every value can become text. A mistake is a `PanglossModelError` naming the template and the
path, so `pangloss check` and the language server show it at the line with no extra work.

Edge properties (`ViaEdge`: `{person@role}`) are left for later.

### Formatters

A date reads well only through `pangloss-dates`' `formatDate`, which exists only in TypeScript (`format.ts`) for now.
Hence a general hook, with no knowledge of `pangloss-dates` in the core:

- **Python:** an app's `labels.py` registers `{"date": format_date}`. Its embedded class says
  `Embedded.Meta(label_template=Formatter("pangloss_dates:date"))`.
- **TypeScript:** the app's interface module exports the same name in its manifest.
- **One file of cases for each formatter** (input JSON, expected text), run by pytest and vitest alike, keeps the two
  copies in step. The same goes for the core's template interpreter (`label_cases.json`).
- **The language** of a formatter's words is the project's default language (a setting), on both sides. The interface
  must not use the reader's language here, or the preview would not match what is saved.

`pangloss-dates` needs a Python port of `format.ts`. That is the largest single piece of work in this plan.

## Storing it and the server

- **The flag:** each node that has a label and whose class has a template gets a property `label_auto` (`labelAuto`
  in JSON). It is on `Create`, `Update`, `View` and `HeadView`, so that a read sent back as it is keeps it. A node with
  no property counts as **written by hand**, so existing data is left alone, and adding a template is not a migration.
- **On a write**, for each such node:
  - `label_auto` true, or no label given: the label is worked out, and anything sent as the label is replaced;
  - a label given and `label_auto` not said: the label is the user's (an SDK script that writes
    `label="…"` means it);
  - `label` on `Create` becomes `str | None` for a class with a template.

  The interface always sends `labelAuto`.
- **Where it is worked out:** in the write path after the pydantic checks and before the write plan, in the same way
  for create, update, `create_inline` batches and `bulk-load`.
- **Labels of references.** A `ReferenceSet` sends `{type, id}`; its `label` is dropped (`remove_label`). The server
  therefore reads the labels of every entity and document the template names, in **one query per write**: a new
  backend operation `labels_of(ids)` in `pangloss-cypher`, with a conformance test on both backends. A `create_new`
  entity in the same payload supplies its own label. This has to be measured on 640k nodes for a single write and for a
  `bulk-load` batch. A template that names no references needs no read.
- **History, search, autocomplete and RDF** all use the stored label, so they need no changes.
- **Export:** each model gets `labelTemplate` (the strings as written; the TypeScript interpreter parses them, and the
  shared cases check both parsers) and the names of its formatters. `pangloss interface check` refuses a formatter
  that no installed module provides.

## The interface

- **A form hook** (`FormHook`, as for field bindings in `schema/binding.ts`) works out every automatic label again
  after each change, innermost first.
- **The label field** of an automatic node is greyed out and shows the label as it is now. It has square icon buttons
  in its bar:
  - a **pencil** unlocks it (`labelAuto: false`), keeping the text so it can be edited;
  - a **↺** on a field written by hand makes it automatic again.

  These follow the rules in `interface-styling-rules` and use `t()` slots with translations.
- **Validation:** an automatic label is not "required" in the valibot checks. If the template gives nothing for a node
  whose label is required, the field turns red, as on the server.
- **Unsaved changes:** labels are worked out only after a change by the user, not on opening the document. So an old
  document whose template changed does not count as changed just by being opened, and opening it shows the stored
  label until something is edited.
- **The server's label is the one kept.** If the two differ (for example, an entity was renamed since its chip was
  loaded), the form shows the server's label after saving.
- **Folded blocks:** a `ReifiedRelationDocument` inside a folded wrapper already shows its label (`labelledContents`).
  With a template, that label changes as the user types.
- `e2e/COVERAGE.md` rows, a browser test (type into a nested document, watch the outer label; unlock, edit, save,
  reload; ↺), and the dev build (`e2e/test_dev_mode.py`).

## Steps

| # | What | Where |
|---|---|---|
| 0 | The language written down, and `label_cases.json` (template, data, expected) | `pangloss-models` |
| 1 | Parser and interpreter in Python; `label_template` on every `Meta`; the checks at `initialise()` | `pangloss-models` |
| 2 | The formatter hook; `format_date` ported, with shared cases | `pangloss-models`, `pangloss-dates` |
| 3 | `label_auto`, the optional `label`, the labels worked out on write, `labels_of`, conformance tests, measured on 640k | `pangloss-models`, `pangloss-cypher`, `pangloss-testing` |
| 4 | Export; the TypeScript parser and interpreter on the same cases | `pangloss-models`, `interface-core` |
| 5 | The form hook, the locked label field, validation, strings, e2e | `interface-core`, `e2e/` |
| 6 | Templates on two or three nested models of the demo; stubs | `pangloss-demo/` |
| 7 | Docs: `models.md` (the `Meta` option), `relations.md`, the guide, `status.md`, the skill | |

## For later

- Derived labels updated when something they name changes (a background job on write events; decision 1).
- Labels in several languages (decision 4).
- `pangloss labels rederive <Model>`: work out the labels of existing data again, for automatic nodes only, or for all
  of them with a flag.
- Edge properties in paths.

## Open: my defaults, to confirm or change

- **A label given with `label_auto` not said counts as written by hand** (the SDK case above).
- **Opening a document does not work out its labels again** (the unsaved-changes case above).
- **"Show when collapsed":** I took this to mean that a `ReifiedRelationDocument` shows its label inside a folded
  wrapper, as it does now. If you meant that a `ReifiedRelationDocument` itself folds down to its label, that is a
  separate addition to `collapse.ts`, which today folds only `ReifiedRelation` and `Conjunction`.
