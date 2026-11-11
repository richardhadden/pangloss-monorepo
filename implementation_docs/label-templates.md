# Label templates 🚧

**Status: plan of 2026-11-11, built as a trial the same day on `implement-autolabels`. The plan below is as written;
what differs is in "As built", and what the trial showed about readable English and German in "The trial".**

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

## As built (2026-11-11)

Where the code is:

| What | Where |
|---|---|
| The language: parser, interpreter, `fill_labels`, the schema made from the export | `pangloss_models/label_templates.py` |
| The checks at `initialise()` | `pangloss_models/initialise_models/check_label_templates.py` |
| `label` optional and `label_auto` on the generated models | `add_label_field` in `initialise_models/builder.py`, `initialise_head_view_model.py` |
| On a write: `fill_labels(db_instance, read_labels)` before `check_before_create`/`check_before_update` | `pangloss_cypher/write_functions.py`; `label_auto` written in `write_plan.py` |
| The same in TypeScript, and the form hook | `interface-core/src/schema/labelTemplate.ts`; `createFormHooks(definitions, formatter)` |
| The locked label: `LabelLock` (pencil, ↺) beside the row or the title box | `components/form/ModelFields.tsx` |
| A date in a label | `pangloss_dates/labels.py` (`format_date`), `labelFormatters.date` of its module |
| Tests | `pangloss-models/tests/test_label_templates.py` and `label_cases.json` (run by Vitest too); `test_dates_labels.py`; conformance `test_label_templates_live.py`; `e2e/test_label_templates.py`; dev build in `test_dev_mode.py` |

Where it differs from the plan, or what the plan did not say:

- **Public names:** `LabelTemplate`, `Formatter`, `register_label_formatter` (from `pangloss_models`). A formatter is
  registered where its models are (`pangloss_dates/models.py`), not in a `labels.py` an app is searched for.
  `Conjunction.Meta` and `SemanticSpace.Meta` were added (the other kinds had their `.Meta` already).
- **Filters:** `join` takes a second text, the separator before the last (`join(", ", " and ")`); `lower` and
  `capitalise` were added. `count` of nothing is empty (so `[: {bequests|count} bequests]` drops out).
- **A wrapper without a template of its own gives up what it holds at the end of a path** (to `join`, `count` and the
  text), so `{witnesses|join(", ", " and ")}` joins the members of a conjunction. `each`, `first` and `last` take the
  wrappers themselves, so `{participants|each("{target} ({role})")}` reaches a reified relation's own fields. A path
  goes through a wrapper that has no field of that name to what it holds (`{owner.forename}` through an
  `Identification`).
- **The interpreter works on the client's JSON** (camelCase; references `{type, id, label}`) on both sides, with a
  schema made from the export: so the Python and TypeScript copies are given the same input, and the shared cases are
  the same file. `contextLabels` and `semanticSpaces` are not walked into (`contextLabels` hold `{type, id}` of the items
  round a node, which looked like references).
- **The labels of references** are read by a plain function in `pangloss_cypher.write_functions` (`read_labels`, one
  `UNWIND` query), not a new backend operation; references by URL get no label. **Not measured** on 640k nodes.
- **`labelTemplate` is not data:** it is in the migration planner's `NOT_DATA_KEYS`. (Without that, the `Formatter` on
  `Date` broke `makemigrations` of a project with the Julian calendar.) The export leaves the key out for a model
  without a template, so no export snapshot changed; `test_models_match_typescript.py` now lets optional keys of a
  model be left out, as it already did for fields.
- **Validation is unchanged:** an automatic label that is empty is "required", red, as the server would refuse it.
- **Formatters are English only**, on both sides (the Python port has no translations; the module's `formatDate` is
  called with its English default). No setting chooses the language.
- **The cursor:** a new nested document puts the cursor in its first field that can be typed in
  (`reveal.ts` skips `[readonly]`), not in the locked label.
- **The guide** is [guide/labels](../guide/labels/README.md); its examples were run through the interpreter.
- **Not built:** `pangloss interface check` of formatter names; templates in the demo; `pangloss labels rederive`.

## The trial: readable English, and German (2026-11-11)

Models shaped like the demo's (a `Factoid` of `Statement`s: `Transfer`, `MemberOf`, a `Meeting` with `InRole`
participants, an `Order` whose `thing_ordered` is a statement in a `PositiveSubjunctive`, a `Negative` space, `Causes`;
`Identification[WeightedAlternative[Person]]` for an uncertain giver), filled in, the labels worked out by
`derive_labels`. The scripts were scratch (`/tmp/autolabels`), not kept.

### English: readable, with one template a model

```
Transfer:   "{given_by} gave {quantity} {item} to {given_to}[ at {places|join(", ", " and ")}][, {date}]"
            → Agnes Hathaway gave 2 silver cups to Judith Quiney at Stratford, 4 March 1601
uncertain:  WeightedAlternative "{alternatives|join(", ", " or ")}"
            → Agnes Hathaway or Anne Whateley gave 1 silver cup to Judith Quiney
Meeting:    "{participants|each("{target} ({role})")|join(", ", " and ")} met[ at {places}][, {date}]"
            → Francis Collins (witness), Julyne Shaw (witness) and Hamnet Sadler (messenger) met at Stratford
Negative:   "it is not the case that {contents}"
            → it is not the case that Hamnet Sadler was a member of the King's Men, 1603
```

What works: nested documents first, groups for what is optional, `join` with "and"/"or", `each` for a reified
relation's own fields, a date said as a person would. What does not, each with what would fix it:

1. **A nested statement in another's sentence needs a different form of it.** `"{ordered_by} ordered {ordered_to}:
   {thing_ordered}"` gives *William Shakespeare ordered Agnes Hathaway: Agnes Hathaway gave 1 silver cup to Judith
   Quiney*. An inline template for the one kind it holds reads well, *William Shakespeare ordered Agnes Hathaway to give
   1 silver cup to Judith Quiney*, but the outer template then knows each kind of statement
   (`{thing_ordered.contents|each("to give {quantity} {item} to {given_to}")}`, and another alternative for the rest).
   **Named forms** would fix it: a model gives several templates by name (`LabelTemplate(..., infinitive="to give
   {quantity} {item} to {given_to}")`), and a placeholder asks for one (`{thing_ordered|form("infinitive")}`), falling
   back to the label.
2. **Numbers and plurals:** *1 statements*, *1 bequests*, *1 silver cup* (where English says *a*). A `plural("bequest",
   "bequests")` filter, and perhaps a way to say *a* for 1, would do for English.
3. **Free text does not agree with numbers:** `quantity` 1 and `item` "silver cups" gives *1 silver cups*. Nothing a
   template can do; the data has to be entered to fit it.
4. **Long labels:** a factoid of four statements is a paragraph. `first` with `count` helps (*…, 4 March 1601 (and 4
   statements in all)*), but "N more" needs the count less one: a `rest` or `more` filter.
5. **Commas inside commas:** a nested label with its own commas (a date, a list, a name written "Hathaway, Anne") in a
   list joined by commas is hard to read. Brackets round nested parts help (`(because {cause})`).
6. **Enum values are not words:** `{role}` gives the stored value (*witness*), not a translated name, and cannot be
   grouped (*witnessed by A and B*): a `where(role="witness")` filter would be needed.
7. **`[` and `]` are groups**, so a literal bracket, common in editions (*[?]*), must be written `\[`. Easy to trip on.
8. **Percentages of a `WeightedAlternative`** are edge properties, which paths cannot reach (planned for later).

With named forms and `plural`, every English label in the trial reads as a person would write it.

### German: prose is much harder; a catalogue style works

The same data, the item and group names in German, templates written as a German speaker would:

```
Transfer:  "{given_by} gab {given_to} {quantity} {item}[ in {places}][, {date}]"
           → Agnes Hathaway gab Judith Quiney 2 silberne Becher in Stratford, 4 March 1601
MemberOf:  "{member} war Mitglied von {group}"
           → Hamnet Sadler war Mitglied von die King's Men, 1603
Order:     "{ordered_by} befahl {ordered_to}, dass {thing_ordered}"
           → William Shakespeare befahl Agnes Hathaway, dass Agnes Hathaway gab Judith Quiney 1 silberner Becher
Negative:  "es ist nicht der Fall, dass {contents}"
           → es ist nicht der Fall, dass Hamnet Sadler war Mitglied von die King's Men, 1603
```

What goes wrong, beyond the English list:

1. **Word order.** After *dass* or *weil* the verb goes last (*dass Agnes Hathaway Judith Quiney einen silbernen Becher
   gab*). A nested statement's label is a main clause, so it cannot be put after *dass*, *weil* or *es ist nicht der
   Fall, dass* as it is. English got away with this (*it is not the case that* takes a main clause); German does not.
   Named forms fix it too, but each kind of statement then needs a subordinate form as well as its main one.
2. **Case and articles.** A label is in one case. *die King's Men* stored with its article becomes *von die King's
   Men* (*der King's Men*, genitive, is right; *den*, dative, after *mit*). Names of people mostly survive (*gab Judith
   Quiney*: a dative with no article), but anything with an article (a group, a type from a typology, *der Knecht*) needs
   its forms by case, which are not in the data. Either an entity keeps its forms (nominative, genitive, dative,
   accusative: a field a typology could have), or templates avoid putting such labels where a case shows.
3. **Adjectives agree with case and number:** free text *silberner Becher* is nominative singular; after *gab … 1* it
   must be *einen silbernen Becher*. Not something a template can change.
4. **Gender:** *Zeuge* or *Zeugin* depends on the person; enum values cannot follow it.
5. **The date formatter is English** (*4 March 1601*): a formatter needs the language of the labels (*4. März 1601*).

A **catalogue style**, a noun for the kind of statement and its parts after labels, avoids almost all of it, and reads
well enough for a list:

```
Übergabe: 2 × silberne Becher; von Agnes Hathaway; an Judith Quiney; Ort: Stratford; 4 March 1601
Übergabe: 1 × silberner Becher; von Agnes Hathaway / Anne Whateley; an Judith Quiney
Mitgliedschaft: Hamnet Sadler — die King's Men; 1603
Treffen: Francis Collins (witness), Julyne Shaw (witness), Hamnet Sadler (messenger); Ort: Stratford
Befehl: William Shakespeare an Agnes Hathaway; 25 March 1616 — Befohlen: Übergabe: 1 × silberner Becher; …
```

Only the enum values (*witness*) and the date are still English. The same style works in English, and is what a
template that has to serve several languages should use.

### What the trial suggests

- The mechanism (paths, groups, nested first, `join`/`each`) is enough for labels that are lists of facts, in any
  language.
- Prose labels need, in order of need: `plural` (English), **named forms** (English for nested statements; German for
  every subordinate clause), translated enum names, a formatter in the labels' language, and for German, entity labels
  by case. The last is a modelling question (where the forms of a name are kept), not one of templates.
- If labels are later kept in several languages (decision 4), each language needs its own templates, since word order
  differs, not just its own words.
