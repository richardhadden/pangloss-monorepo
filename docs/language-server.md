# The language server

**Status: ✅ built 2026-11-08: `pangloss check`, diagnostics, fresh stubs, hover, completions, quick fixes and "did you mean", tested
over stdio. The two editor extensions are installed and work in Zed (the VS Code one compiles, and has not been run in
VS Code). Not built: the clash warning for `reverse_name`.**

It sits beside your type checker and does what a type checker cannot: it knows Pangloss's rules.

- **On save**, what `initialise()` refuses is shown at the field or class, every field at once, and the warnings too.
- **Payload keys**: in a dict that says `"type": "Person"`, the keys of that model in camelCase, and the model names
  for `"type"`.
- **`Where` keys**: in `Person.Where(`, the fields of that model that can be searched, then the `$` keys.
- **Hover on a model's name** (its `class` line, or where an annotation names it): its kind, docstring, the classes
  above it, its indexes, and the fields that can hold it.
- **Find references** on a model's name: the relation fields that can hold it.
- **Inlay hints**: after each relation field, the name of the edge back (`born_in: Place  ⇄ born_in_reverse`).
- **Changes not in a migration yet**, as warnings at the field or class that changed.
- **Quick fixes** for the refusals that have an obvious correction (below).
- **Completion** of the options of every `Meta`, of `RelationConfig` and `FieldBinding`, of the values they take, and
  of the `_x_meta` slots (below).
- **The stubs are rewritten** after each save with no errors, so `pangloss make-stubs` need not be run by hand.
- **Hover** on the name of a declared field says what it is to Pangloss (a value on the node; a relation, its reverse
  edge; its type in `Create` and whether it is required). Hover on the name of an option says what it is.

## `pangloss check`

```sh
pangloss check                  # file:line:column: error: message. Exits with 1 if there is an error
pangloss check --json           # one line of JSON: {"diagnostics": [...], "fields": {"Model.field": "..."}}
pangloss check --write-stubs    # and the stubs, if the models are sound
```

It needs no database. It runs `initialise(bind_database=False)`, by way of `pangloss_models.diagnostics.check_models`,
so it says what `initialise()` would. There are no rules of its own: under `check_models`, `reported()` notes a refusal
and initialising goes on to the next field. After the field definitions it stops, if something was refused, because the
later steps need all the fields.

In a `Diagnostic`, `line` counts from 1 and `column` from 0 (a character, not a byte). A problem with no one place has
no `file`. The report also has `schema`, which the completions are made from.

## Hover on a model

Over a model's name the hover has its kind (`abstract entity`), the first paragraph of its docstring, the project's
classes above it (parents and traits), its indexes, the number of its fields and relations, and the first six fields
that can hold it (`Statement.about (as a Agent)`). Hovering a field's own name still says what that field is, and an
option's name (`indexes=`) what the option is. The facts are in the report's `schema.models`.

## Find references

On a model's name (its `class` line, or where an annotation names it), the editor's *find references* lists the
relation fields that can hold one, each at the field's name. A type checker lists where the class is named; this lists
where it is *pointed at*, which is also by a field that goes to a class above it or a trait it has (`about: Agent`
can hold a `Person`), and by a field of reified relations or semantic spaces that take it as a parameter
(`involves: list[InRole[Person]]`). `diagnostics.relation_references` makes the list, `via` in it says which class
above the model the field goes to; the generated parametrisations (`InRole[Person]`) are not owners of fields.

## Inlay hints

A relation is two edges, and the name of the one back (`born_in_reverse`, or the `reverse_name` the field was given) is
what a query and the incoming relations of the target use, yet the source never says it. It is shown after the line of
each relation field, or after the last line of a field whose statement goes over several. The report's `hints` has the
text and a tooltip for each `Model.field` (`diagnostics.field_hints`); the server places them from the buffer, so they
are where the field is as you type. Nothing else is hinted: a type or a default is in the source already. Zed shows
inlay hints from a language server only when `"inlay_hints": {"enabled": true}` is in its settings.

## Changes not in a migration yet

When the models have changed since the last migration, each change `makemigrations` would write is a warning at the
field (an added field, a changed type) or at the class (a removed field, a changed option): "Not in a migration yet:
Add the field Person.born ... (`pangloss makemigrations`)". A model that is gone from the code has no place, so its
warning has none. It is `diff` of the migrations' state and the snapshot of the models, as `makemigrations --check`
does, and needs no database. A project with no migrations at all is told nothing (every model would be new), and a
warning does not make `pangloss check` exit with 1.

## Quick fixes

A refusal can name the correction: `PanglossModelError(..., fix="drop_optional")`, and likewise a
`PanglossModelWarning(..., model=..., member=..., fix=...)`. The names are the keys of `diagnostics.FIXES`, each of
which turns the field's source (found with `ast`) into an `Edit`: the range, the text that is there (`old_text`) and
the text to put. The server offers it as a code action, and only if the buffer still has `old_text` at that range (it
was made from the saved file).

| Refusal | Fix |
|---|---|
| `visited: list[Place] \| None` | change to `list[Place]` (a list may already be empty) |
| `tags: list[str \| None]` | remove `None` from the items, or make the whole list optional |
| a `model_config` of the class's own (warning, at the `model_config` line) | remove it |
| a name in a string that is not one (`indexes=["nmae"]`) | change to the closest names (up to three) |

**Names in strings.** A type checker cannot see `indexes=["nmae"]`, `reference_view_extra_fields`, or the names of a
`FieldBinding`. `initialise()` refuses each (the bindings' `bound_field`, `child_fields`, `allowed_type_names` and
`excluded_type_names` were not checked before: a misspelt one never applied, without a word), and the error carries the
string it is about (`PanglossModelError(..., at_string=AtString(option, value, candidates))`). The editor underlines
that string, not the class, and the message says "Did you mean 'name'?". A binding's `child_fields` must be a field of
some model, not of a particular one, since which classes it reaches depends on what the field holds. The names of a
binding's types are those of the models and of the classes above them (a trait's too).

Most of the old refusals of `docs/modelling-dx.md` §2 are not refusals now, so there are few mechanical fixes left. A
refusal that has one should name it where it is raised.

## Completion

`schema` in the report is made by `pangloss_models.editor_schema.editor_schema()` from the classes, never kept by hand:

- `calls`: each `Meta` (`DocumentMeta`, `EntityMeta`, ...), each meta slot class of the installed apps
  (`InterfaceMeta`, `DerivedMeta`, `Protection`, ...), `RelationConfig` and `FieldBinding`: for each option its type,
  default, choices and documentation. The documentation is the comment directly above the field in the class (a
  blank line between breaks it); a parenthesised comment is taken without its brackets. Choices come from a `Literal`,
  a `bool` or an `Enum`.
- `aliases`: `Document.Meta`, `Entity.Meta` and `<Model>.Meta` for each model, to the class they are.
- `slots`: the `_x_meta` names, their classes and the package to import them from.
- `models`: each model's kind and the kind of each field (`literal`, `list`, `relation`, `embedded`, `annotated`), and the keywords of its generated `Where` (read from the class, so what cannot be searched yet is left out).

A meta class can say what an option takes by an `editor_choices(option)` static method. `InterfaceMeta` does, for
`list_page`, `item_page`, `view_card` and `edit_card` (the `<app>:<Name>` of each key of `components` in the installed
interface modules) and `collapse` (`collapseRules`). Those are read from the TypeScript source of the module's
`defineModule` by `pangloss_interface.modules.keys_of`, which is a text reading, not Node's loader (that takes seconds).
It can miss a component built in a way the reading does not follow.

The server (`pangloss_lsp.context`, `completion`) reads the buffer as text, not as Python, since it rarely parses
while it is being typed. It finds the innermost call at the cursor, the argument it is in and whether that is a name,
a value, or inside a list or a string.

| At | Offered |
|---|---|
| a name in a `Meta(`, `InterfaceMeta(`, `RelationConfig(`... | the options not yet given, as `name=` |
| `indexes=[...]` | the fields of the class that hold a value (`literal`, `list`; fields typed since the last save too), and `label` |
| `view_extra_fields`, `reference_view_extra_fields`, `hide_on_forms`, `bound_field` | every field of the class |
| `allowed_type_names`, `excluded_type_names` | the models |
| `default_reified_type` | the reified relations, as a class name |
| `reverse_name` | `<field>_reverse`, the name the field would get |
| any option with choices | the choices (strings quoted, unless the string is begun) |
| the start of a line of a class body, after `_` | `_meta = <Base>.Meta(...)`, and each registered slot, with its import added |
| a key in a dict literal that has `"type": "<Model>"` | the model's keys, camelCase, as the API takes them (`label` and `id` too, for a document or entity), those not already given |
| a name in `Person.Where(` | the keywords of that model's `Where` (`label`, its searchable fields, then `all_`, `any_of_`, `not_`...), as `name=`, those not already given |
| the value of `"type"` | the models (not abstract ones, nor generated parametrisations like `InRole[Person]`) |

A dict says what it is by its `"type"`, wherever it is written (a script that uses the SDK, a test, `json=` of a
request); one that does not say is offered `type`. The keys of `Person.Create(...)` itself are the type checker's, from
the stubs. JSON files (a bulk upload) are not Python and are not offered anything.

`Where` is found by its name: `Person.Where(` is completed, but a `Where` imported on its own, or kept in a variable, is
not. The values of a keyword (the `Text(`, `Rel(` operators) are not offered. Not offered either: `_typology_meta` (it
belongs to the classes that subclass `Typology`, and is not a registered slot).

## How the server works

`pangloss-lsp` (package `pangloss-lsp`, on `pygls`) is an editor's process, and imports no project code. On the first
file opened in a project and on each save of a Python file, it runs `python -m pangloss_cli.main check --json
--write-stubs` in the project's directory and publishes what that says. So a broken model cannot take the server down,
and each run starts with nothing registered.

A project is found by the nearest `pyproject.toml` with `[tool.pangloss] settings`. A file outside one is ignored. The
server has to be installed in the project's environment, since it is that Python which imports the models. It is a
command of its own, not `pangloss lsp`, because the `pangloss` command imports the settings and each app's `cli.py`
before it starts, and anything printed then would corrupt the protocol on stdout.

Diagnostics, and the schema, only come on save, because the project's modules on disk are what is imported. A hover uses the last run
without an error, and finds the field by indentation, so it works in a buffer that does not parse.

## Installing

Add `pangloss-lsp` to the project's development dependencies; in this repository it is already installed by `uv sync
--all-packages --all-groups --all-extras`. The extensions look for `.venv/bin/pangloss-lsp` in the folder that is open,
then on the `PATH`. They are in `packages/pangloss-lsp/editors/`.

**Zed.** Needs Rust from `rustup`, with `rustup target add wasm32-wasip2`. If you have just installed it, quit Zed and open it again: Zed reads the `PATH`
when it starts. In the command palette, *zed: install dev
extension*, and choose `packages/pangloss-lsp/editors/zed`. The extension runs `.venv/bin/pangloss-lsp` of the folder that is open (Zed does not list what git ignores, so it
cannot look for it first), or a `pangloss-lsp` on the `PATH`; `"lsp": {"pangloss": {"binary": {"path": "..."}}}` in
Zed's settings names another. If Homebrew's `rust` is installed, remove it: its `cargo` comes before rustup's on Zed's
`PATH` and has no wasm target. If the `language_servers` of `Python` in your settings do
not contain `"..."`, add `"pangloss"`.

**VS Code.** In `packages/pangloss-lsp/editors/vscode`, run `npm install` and `npm run compile`. To try it, open that
folder in VS Code and press F5. To install it, run `npx @vscode/vsce package --allow-missing-repository` and choose the
`.vsix` with *Extensions: Install from VSIX*. The setting `pangloss.serverPath` names another server.

Any other editor can start `pangloss-lsp` over stdio for Python files.
