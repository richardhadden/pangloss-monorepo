# Translations for the interface 🚧

**Status: built, and the nav bar, the console and the login form are connected.**
`pangloss interface translations generate | gather | check` make the files, and `gather` (run whenever the interface is
prepared) writes `interface-app/src/generated/translations.json` with every language. The interface reads it
**on the server only**: `loadTranslations(language?)` in `interface-app/src/translations.ts` is a `"use server"` function
(the Vite plugin's `serverFunctions: true`), so the browser has only the texts of the languages chosen. The default
language is read when the page is rendered and comes with it; another is fetched the first time it is chosen in
the nav bar (one call to `/_server`), and kept. While it loads the page sets `data-translating` on `<html>` and
`styles.css` fades the body out and back in with the new words. The choice is kept in `localStorage`
(`pangloss.language`) and followed at the next load (the server renders the default language first, so there is a
change after a reload). `<html lang>` follows the language. The pages not yet connected are listed in
[interface-strings.md](interface-strings.md). The API is not multilingual (see the last section).

**In components:** `const { t, modelName, fieldName, incomingName, enumName, memberName, language, setLanguage } = useTranslations()`
(`interface-core/src/context/translations.tsx`). `t("new_item", "New {type}", { type })` takes the slot and the English
to use when there is none; with no `TranslationsProvider` above (a component on its own, a test) the English is what shows.
`modelName(type, true)` is the plural. A missing text falls back to the default language, then to the name in the code.

The interface shows the names of models and fields, and some fixed text of its own (the title, "Log in").
Both need translating. The API stays in one language (see [The API and languages](#the-api-and-languages)).

Settings that already exist (`pangloss_core.settings.BaseSettings`):

```python
INTERFACE_LANGUAGES: list[str] = []        # e.g. ["en", "de"]
DEFAULT_INTERFACE_LANGUAGE: str = "en"
```

## The format

**JSONC (JSON with comments) for the files people edit; plain JSON for what the site loads.** The alternatives, and why not:

| Format | For | Against |
|--------|-----|---------|
| **JSON / JSONC** | the site needs JSON anyway; every editor reads it (VS Code treats `.jsonc` as JSON with comments); comments are allowed in JSONC | JSONC needs a reader that skips comments (see below); long strings are one line |
| YAML | comments, multi-line text, friendlier to edit | a dependency; the "Norway problem" (`no` is read as `false`, which is awkward for a language list with `no`); indentation errors are silent |
| TOML | comments, in the standard library to read | nesting three levels deep (model → language → fields) is clumsy; the standard library cannot write it |
| gettext `.po` | the standard for translators; tools like Weblate; plurals | keyed by the source text, not by structured keys; one flat catalogue per language; needs a compile step |
| XLIFF / ICU / Fluent | rich (plurals, gender, context) | heavy, for names of models and fields that are nouns |

### Comments (JSONC)

Comments are what a translator needs: the **English text beside the German one**, and a note that a text
**needs review**. The generator writes them, so each run writes them again from the current state:

```jsonc
"birth_place": {
  // English: Place of birth
  "name": "Geburtsort",
  "plural": "Geburtsorte",
  "help": "" // NEEDS REVIEW: the English has changed since this was translated
}
```

Two things to know:

- **A comment a person adds is lost the next time `generate` rewrites the file.** Reading JSONC is easy;
  *writing* it with the comments of the person kept needs a patcher that edits the text instead of
  rewriting it, which is a lot of code for little. Comments that are the generator's are always right
  because they are made again. If notes from people are wanted, they go in a `"note"` field, which is a
  value and so is kept like any other.
- **Reading is our own comment stripper** (`i18n/jsonc.py`, string-aware: a `//` inside a string is text;
  newlines are kept so an error says the right line). The `jsonc-parser` package only reads too (no
  writer), so it would not have saved anything. Trailing commas are not part of JSONC, so they are not
  accepted.

`.state.json` stays plain JSON, as does the output of `gather`: the site loads ordinary JSON.

Files are written the same way every time (indented by 2, keys in order, `ensure_ascii=False` so that `ö`
is not `\u00f6`), so that a diff in git shows only what changed.

## Where the files are

```
demo_app/translations/models.jsonc      the models of the app, all languages: the file a translator edits
demo_app/translations/.state.json       what the generator last wrote (see below): commit it, do not edit it
translations/models.jsonc               the project's overrides (same shape; may hold only what is changed)
pangloss_interface/translations/ui.jsonc the fixed text of the interface (same shape idea; see below)
.pangloss/interface/.../translations.json   the result of `gather`: what the frontend loads (generated)
```

An app's folder is `translations/` next to its `models.py`. The app a model belongs to is found as the
migrations find it (`app_of_module`, `pangloss_models/migrations/planner.py`), so the same rule decides
where a model's entry is written.

### `models.jsonc`

One file per app, holding every language. The shape you described: model name, then language, then the texts.
A translator opens one file and sees English beside German; the cost is that a file grows with
models × languages, and two people translating different languages in it can conflict in git (the keys
are sorted and a text is on its own lines, so a conflict is small).

```jsonc
{
  "models": {
    "Person": {
      "en": {
        "name": "Person",
        "plural": "People",
        "description": "A person who appears in the sources.",
        "help": "",
        "fields": {
          "birth_place": { "name": "Place of birth", "plural": "", "help": "Where the person was born." }
        },
        "incoming": {
          "carried_out": { "name": "Carried out", "plural": "", "help": "" }
        }
      },
      "de": {
        // en: Person
        "name": "Person",
        "plural": "Personen",
        "description": "",
        "help": "",
        "fields": {
          "birth_place": { "name": "Geburtsort", "plural": "Geburtsorte", "help": "" }
        },
        "incoming": { }
      }
    }
  },
  "enums": {
    "Colour": {
      "en": {
        "name": "Colour", "plural": "Colours", "description": "The colours of ink", "help": "",
        "members": { "RED_WINE": { "name": "Red wine" } }
      },
      "de": { "...": "the same, empty" }
    }
  },
  "_obsolete": { }
}
```

The top has a section for `models` and one for `enums` (enums are not models, and a name could be
both), then the entity, then the language, then the texts. `incoming` are the relations that *other*
models make to this one, named by the reverse name they have in the models; `members` are the values of
an enum, by the name in code (what is stored is the value, which is not translated).

- The languages are `INTERFACE_LANGUAGES` (the default language is always included).
- `en` (the default language) is filled from the models. The others are filled with `""`, which means
  *not translated*.
- **`plural`** is optional everywhere: `""` means *use the singular* (for a field such as `label`, or a
  language where it makes no sense). It is never reported as missing. `help` is likewise optional, but
  once the default language has a help text, an empty one in another language *is* reported as missing.
- A model's `name` may be longer than the class name or have characters that Python does not allow
  ("Person or group"). Editing it in the file is how to do that: no new option on the model is needed,
  and the edit is kept (see the next section).
- Only the fields a model **declares** are listed: a field is translated on the base-most class of the
  app that has it, and `gather` gives a subclass (`Student`) the texts of the class that declared it
  (`Person`'s `birth_place`).
- A class that **redeclares** a field (to narrow it) gets an entry of its own for it, with empty texts. While
  they are empty the base's are used; fill one in (`name`, `plural`, `help`, in any language) and the
  narrowing class has its own. In a language, the order is: the class's own text, then the base's, and only
  then the default language's.
- The generator's comments are the default language's text above each translation and
  `NEEDS REVIEW` marks; they are written again each run. **A comment of your own, on a line of its
  own above a key, is kept** (at the top of the file too), as long as it does not begin like the
  generator's (`en: `, `de: `, ..., `NEEDS REVIEW: `). A comment at the end of a line or in `/* */` is not kept,
  and one above something that has moved to `_obsolete` is dropped with it.

### Where the default text comes from

| Text | Source, in order |
|------|------------------|
| model `name` | the class name, written as words (`BirthRecord` → "Birth record") |
| model `plural` | `""` (the singular is used) |
| model `description` | the docstring of the class (`inspect.cleandoc`, as `export_model` does), else `""` |
| field `name` | `Field(title=...)` if there is one (the verbose name), else the field name as words (`birth_place` → "Birth place") |
| field `help` | `Field(description=...)` if there is one, else `""` |
| model `help` | `""` (a short line for a tooltip; `description` is the docstring) |
| incoming relation `name` | its reverse name as words |
| enum `name`, `description` | the class name as words; the docstring |
| enum member `name` | the member name as words (`RED_WINE` → "Red wine") |

There is no verbose-name option on models today. When the [meta slots](meta-slots.md) exist the natural
place for one is `InterfaceMeta(verbose_name=..., verbose_name_plural=...)`, which the generator would then
read before the class name. Not needed to start.

## Keeping manual edits: a three-way merge, not a replay

You suggested dated snapshots of the user's edits and of the model changes, replayed in order. There is a
simpler thing that gives the same result, and it needs no history that does not exist (the changes to a
model are not recorded anywhere except the migrations' snapshots, and not every change is migrated).

Remember, for each text, **what the generator wrote last time** (the *base*). Then at the next
`generate`, for each text there are three values:

- `base`: what the generator wrote last time (from `.state.json`)
- `current`: what is in the file now (maybe edited by a person)
- `new`: what the models give now

| `current` vs `base` | `new` vs `base` | Result |
|---------------------|-----------------|--------|
| same (not edited) | same | nothing changes |
| same (not edited) | changed | take `new` (the file follows the model) |
| **edited** | same | keep `current` (the person's edit) |
| **edited** | changed | keep `current`, and mark it **needs review** |
| key is new | | write `new` (`""` for languages that are not the default) |
| key has gone | | see renames |

"Edited" is simply `current != base`, so no timestamps are needed. For a translation (say German) the
`new` and `base` that matter are those of the **default language** text it was made from: so
`.state.json` also keeps, for each text, the default-language `source` it was translated from. When that
source changes and the German has been edited, the German is kept and marked *needs review*: it may now
be wrong, but a person decides.

```json
{
  "Person": {
    "de": {
      "name":        { "base": "", "source": "Person" },
      "description": { "base": "", "source": "A person who appears in the sources.", "review": true },
      "fields": { "birth_place": { "base": "", "source": "Place of birth" } }
    }
  }
}
```

If a timeline of edits is wanted later (who changed what, when), git has it; the state file does not
need to repeat it.

### Renames and removals

A key that is renamed (a model, or a field) is a **new key**, so the new one starts fresh and the old one
has no model. What is done with the old:

1. If the migrations record a rename (`RenameModel`, `RenameField`, `RenameEnum`, `RenameEnumMember`,
   which `makemigrations` asks about and stores; and `AlterReverseName` for an incoming relation, which
   is on whichever models the field points to, so it applies to all of them: if another relation still
   uses the old reverse name, its text is not touched), the entry is **moved** to the new key, with its edits and its review mark. That is the one case
   where the generator knows it is the same thing.
2. Otherwise the old entry is moved to a top-level `"_obsolete"` section of the file, not deleted: a
   person's translation is not lost to a typo in a class name, and it can be copied back. `generate
   --prune` removes it.

The translations of a renamed thing are "reset" (the new key starts with defaults) unless the migrations
say it is a rename. `_obsolete` entries keep the key they had, so a rename recorded **later** moves them
back (see the next section).

## What needs the migrations

Only **rename detection** does, and only `generate`. `gather` and `check` read the translation files and
the settings and never need the migrations or even the models. `generate` does not need the migrations
to be up to date either, but there is a catch:

- A model or field renamed in the code, with **no migration yet**, looks like a removal plus an addition.
  The old entry goes to `_obsolete` and the new one starts empty.
- That is safe, and it is recoverable: `_obsolete` keeps the old key, so when `makemigrations` records the
  rename (you answer its question) and `generate` runs again, the entry is moved to the new key, with its
  edits.
- So the advice is *run `makemigrations` first*, and `generate` **warns** when the models differ from the
  migrations ("the models have changes with no migration; a rename will not be carried over until there
  is one"). It does not refuse: someone translating needs not be blocked on a migration. `--strict` makes
  the warning an error, for CI.

## Overrides

`<project>/translations/models.jsonc` has the same shape and holds only what the project wants different
from the apps (including for models of installed packages). `generate` creates it empty (`{}`) if it is
not there and never rewrites its contents. Precedence when gathering, highest first:

1. the project's `translations/models.jsonc`
2. the app's `translations/models.jsonc`
3. the generated default (what the app file would have said had it not been edited)

Within each, a text that is `""` is *not there*, and the next level down is used. For a language other than
the default, a text that nothing gives falls back to the default language at run time, and `check` reports
it.

## The fixed text of the interface

`pangloss-interface` has its own file, `src/pangloss_interface/translations/ui.jsonc`, with the slots the
pages use (a flat map of key → language → text, not tied to a model):

```json
{
  "title":   { "en": "Pangloss", "de": "Pangloss" },
  "log_in":  { "en": "Log in",   "de": "Anmelden" },
  "log_out": { "en": "Log out",  "de": "Abmelden" }
}
```

It also has the words for the **kinds of model** (`kind_entity`, `kind_entity_plural`, `kind_edge_model`, ...:
one pair for each kind there is, and a test fails if a kind is added without them). A model in the gathered
file has its `kind` ("Entity"), and the page looks the words up in `ui`. (Edge models are models, with
texts for themselves and their fields like the others.)

It is **written by hand** (there is nothing to generate it from, and it is in the installed package, which
`generate` never writes to). It has English and German for the three slots now. Every installed app can
have a `translations/ui.jsonc` of its own slots; the interface's is always read, whether or not
`pangloss_interface` is in `INSTALLED_APPS`. A project adds or changes slots and languages in
`<project>/translations/ui.jsonc` (made empty by `generate`), which wins. `check` reports a slot with no
text in a language.

## The commands

All under `pangloss interface translations`, and all need the project's models:

| Command | Does |
|---------|------|
| `generate [--app APP] [--prune] [--dry-run] [--strict]` | writes or updates `<app>/translations/models.jsonc` and `.state.json` for each installed app that is part of the project (an app inside `site-packages` is skipped: use the project's overrides), and makes the project's `translations/models.jsonc` and `ui.jsonc` (empty) if they are not there. Prints, per app, how many texts were added, followed the models, were moved to a new name, put in `_obsolete`, and need review. Warns if the models have changes with no migration (`--strict` stops there) |
| `gather [--out FILE]` | merges every layer into one JSON file for the frontend; default `.pangloss/interface/translations.json` |
| `check [--lang L] [--strict]` | prints what is missing (`missing`), what needs review (`review`) and what points at nothing (`unknown`: a name in the project's overrides, or in `_obsolete`, that no model has), then the counts. Exit code 1 if anything is missing; `--strict` also fails on the other two |

The shape of what `gather` writes (by language first, with the fallback to the default language already
applied, plurals filled in, and each model with all of its fields, inherited ones too):

```json
{
  "default": "en",
  "languages": ["en", "de"],
  "ui":     { "en": { "title": "Pangloss", "log_in": "Log in", "log_out": "Log out" }, "de": { } },
  "models": { "en": { "Person": { "name": "", "plural": "", "description": "", "help": "", "kind": "Entity",
                                  "fields": { "birth_place": { "name": "", "plural": "", "help": "" } },
                                  "incoming": { } } }, "de": { } },
  "enums":  { "en": { "Colour": { "name": "", "plural": "", "description": "", "help": "",
                                  "members": { "RED_WINE": { "name": "" } } } }, "de": { } }
}
```

A plural that is not there is the singular *in that language* (a German name with no German plural is the
German name, not the English plural); a name with nothing in the language falls back to the default's.

## How it is built

In `pangloss-interface`, the package `pangloss_interface.i18n` (and `translations_cli.py` for the
commands). The comments in the files are the generator's: **the comment stripper is our own**
(`jsonc.strip_comments`, string-aware, 25 lines; no dependency).

| File | Is | Needs models? |
|------|----|---------------|
| `jsonc.py` | read JSONC; write a nested dict in one form with comments above keys | no |
| `paths.py` | a text is a tuple `(section, entity, language, *rest)`; helpers | no |
| `extract.py` | the default texts from the exported models, the registry, `Field(title/description)`, docstrings | yes |
| `merge.py` | the three-way merge, renames and `_obsolete`, as pure functions on flat maps | no |
| `files.py` | read and write `models.jsonc`, `.state.json`, `ui.jsonc`; find an app's folder; never write outside the project | no |
| `renames.py` | the renames the migrations record; the models' changes that have no migration | migrations |
| `generate.py`, `resolve.py`, `gather.py`, `check.py` | the commands' work | no (given what `extract` made) |

Tests: `test_i18n_jsonc.py`, `test_i18n_merge.py` (each row of the table above, renames, `_obsolete`,
checked by mutation), `test_i18n_project.py` (an app made in a temporary directory: extract, generate
twice, edits kept, gather, check, the commands, renames from migrations).

### Decided

1. One file per app, all languages in it.
2. A field has `name` and `help`.
3. Models and fields have `name` and `plural`; an empty `plural` uses the singular.
4. An unmatched rename goes to `_obsolete`.
5. Enum members and incoming relations have names; models have a `help`.
6. JSONC, with our own comment stripper.

### Still open

- If `.state.json` is lost the next `generate` has no memory, so it takes any text that differs from the
  models for an edit: nothing is lost, but nothing follows the models until it is reset. Commit it.
- Comments of your own are kept only above keys (see above).
- No page reads `translations.json`; adding `title`, `log in` and `log out` to the pages is for when the
  interface is built.
- A reverse name that two relations share is renamed for neither unless both use the new one: only
  text that has lost its name is moved.

## The API and languages

Not to be decided now. Notes on whether it could be done with pydantic aliases:

- **Pydantic aliases** give a field one name for validation (`validation_alias`, or several with
  `AliasChoices`) and one for output (`serialization_alias`). They are fixed on the class, not chosen per
  request. A different language is therefore a different class, or a custom serializer that renames keys
  using `SerializationInfo.context` (which can be set per request). Either is possible, but:
- The generated models are already five kinds per model (`Create`, `CreateDB`, `Update`, ...), and an alias
  generator is already used for camelCase (`apply_camel_case_aliases`). A per-language variant multiplies
  the classes and has to work with that alias.
- The OpenAPI schema (and so the SDK and the TypeScript export) would be per language, or would lie.
- Property names in the database and in Cypher must stay the English field names, so every request and
  response would be translated at the edge; queries on a field (filters, sorting) would have to translate
  the other way.
- It does not help with what is likely wanted more: **values** in several languages (a label in German
  and English), which is a question for the data model, not for field names.

The view taken for now: the API uses the model's identifiers, and the interface translates names for
display from the files above. That costs nothing in the API and can be revisited if someone needs to
send `Geburtsort` to the API itself.
