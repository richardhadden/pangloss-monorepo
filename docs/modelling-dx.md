# Modelling DX: footguns, pydantic's types, and editor tooling

**Status: a review and two proposals, written 2026-11-08. Nothing here is built.** The facts about the current
behaviour were checked by running a probe script against `initialise(bind_database=False)` on this day (the table in
§2 is its output); everything marked *to check* was not.

## 0. The question

Declaring a Pangloss model looks like writing a pydantic model, and that is the point: no new language to learn. But
Pangloss reads the class and makes other classes from it, and so it has rules pydantic does not have, and it ignores
things pydantic would honour. The worry is that a user writes what pydantic would accept, and gets something else,
sometimes without a word said.

The constraint this review is written under: the factoid model (`pangloss-demo`) is the **far** limit of what Pangloss
must support. The near limit is a plain research database: entities with literal fields and relations to each other
(`Person.spouse`, `Person.born_in: Place`), with few or no documents. The DX has to be good at the near limit first,
because that is what a new user writes in their first hour, and the far limit must not make the near one worse.

Three sources of trouble, in order of how much harm they do:

1. **Pydantic features that are read and silently dropped.** The class is valid pydantic, `initialise()` accepts it,
   and the generated models do something other than what was written. (§2, "silent")
2. **Rules that cannot be derived from pydantic**: which types are literals, which shapes of relation exist, what
   `Create` demands. These raise at `initialise()`, so they are loud, but to the user they look arbitrary. (§2,
   "loud but arbitrary")
3. **Generation at run time, invisible to editors and type checkers**: `Person.Create` does not exist until
   `initialise()` has run, so an editor cannot complete it and `ty`/`pyrefly` cannot check it without stubs. (§5)

§3 answers whether the built-in primitives are too many; §4 is proposal (a), storing pydantic's standard types;
§5 is proposal (b), a language server; §6 is the recommended order.

## 1. How a field is understood today

For the proposals it matters where the knowledge of "what a literal is" lives. It is in **seven places**, each with
its own list:

| Place | What it knows | File |
|---|---|---|
| `is_literal` / `LITERAL_TYPES` | Which annotations are literals: `str int float bool Decimal date datetime`, `Enum`, `TypedDict` of these | `pangloss_models/utils.py` |
| `map_validators_to_kwargs` | Which `annotated_types` constraints are carried: `Gt Ge Lt Le MultipleOf MinLen MaxLen` | `pangloss_models/utils.py` |
| `convert_type_for_writing` | How a value is written: `Decimal` and `UUID` and `AnyUrl` as `str`, an enum as its value, containers recursively | `pangloss_cypher/values.py` |
| `Exporter.SCALAR_TYPES` / `describe_type` | How a type is told to the interface: `bool int float str decimal datetime date uuid`, `enum`, `typedDict`, `list`, `literal` | `pangloss_models/export.py` |
| `kind_of` / `checked_value` | How a type is compared in a search: `text number decimal temporal simple` | `pangloss_models/search.py`, `pangloss_cypher/search_query.py` (`toFloat` for a decimal) |
| `LiteralEditor.tsx`, `searchForm.ts` | Which widget edits it | `interface-core/src/components/form/`, `schema/` |
| The migration snapshot and `AlterLiteralType` | What a change of type means to stored data | `pangloss_models/migrations/` |

They agree today because the list is short. The export knows `uuid` and `literal`, which `is_literal` refuses, so they
have already begun to drift. Any new type must be added to all seven (and to the stubs, which render whatever
pydantic has).

## 2. The footguns

Each row of the first table was run on 2026-11-08 (`/tmp` probe: a `Document` with one field, `initialise(bind_database=False)`,
then the field's definition and its `Create` field). "Silent" means the class is accepted and the result differs from
what pydantic would do with the same class.

### 2.1 Silent

| You write | What pydantic would do | What Pangloss does | Harm |
|---|---|---|---|
| `n: int = 0` | Optional, default 0 | `Create.n` **required**, no default | A user adds a field with a default to a model that has data, and every existing client breaks. The migration planner also sees a required field with no default (it asks) |
| `n: int \| None = 5` | Default 5 | Default **`None`** | Data silently differs from what the class says |
| `tags: list[str] = []` or `Field(default_factory=list)` | Optional, `[]` | Required | Same as the first row |
| `@field_validator("s")` | Runs on every parse | **Not copied** to any generated model | Normalisation and checks the author believes in never run. Only `@model_validator(mode="after")` is copied |
| `@computed_field` | In the serialised output | Dropped | |
| `def full_name(self): ...` on the class | A method of every instance | Not on `Create`, `View` or `HeadView` (they do not subclass the declared class) | The most "pure pydantic" expectation there is, and the one most quietly broken |
| `model_config = ConfigDict(extra="forbid", frozen=True, ...)` | Honoured | Ignored; the generated models have their own config | See the next row |
| `Person.Create(label="x", txet="typo")` | `extra="ignore"` default too, so dropped | Dropped. Over the API, a misspelled camelCase key in a payload is **silently discarded** and the document saved without it | A typo in a client script or in a bulk upload loses data without an error. Pydantic's default is the same, so this is "inherited", but the API's payloads are where it hurts |
| `Field(pattern=r"...")`, `constr(max_length=3)`, `conint(ge=0)`, `conlist(str, max_length=2)`, `StrictStr` | Constraints enforced | Constraints **lost** (they are not `annotated_types.BaseMetadata`, or the mapping does not know them); the schema shows none | Looks like validation, is not |
| `Field(alias="Foo")` | The alias is the key | Ignored; the alias is always camelCase | |
| `f: SomeIntFlag` | Members and their combinations | Accepted as an enum; a combination (`A \| B` = 3) is a value no member has, which the enum migrations (`RemoveEnumMember`, `AlterEnumMemberValue`) cannot see | Minor, but a trap |
| `d: datetime.datetime` with a timezone | Kept | *To check*: no handling of zoned datetimes was found in `pangloss_cypher` (Memgraph has `ZonedDateTime`, Neo4j `DateTime`); whether the offset survives the round trip, and whether the two backends agree, is not tested | |
| `price: Decimal` | Exact | Stored as a string "to keep its exact value", but **compared as `toFloat()`** in a search and ordered as a string by any plain `ORDER BY` | Half a promise. Either is defensible; the doc should say which |

The first group (defaults, validators, methods, config) is the one that makes the "looks like pydantic" worry real.
A user who knows pydantic will write every one of these in their first model.

### 2.2 Loud, but the rule is not pydantic's

All of these raise `PanglossModelError` at `initialise()`, which is right. The question is whether the rule is one a
user can predict.

| You write | Result | Why it feels arbitrary |
|---|---|---|
| `spouse: Person \| None` | Refused: "use `list[Person]`" | The most natural relation at the near limit. `list[Person]` for 0..1 says nothing about the cardinality, and the interface shows an "Add" button where a picker was wanted. The machinery exists: `AtPage.target: Annotated[list[T], MinLen(1), MaxLen(1)]` is a 1..1 relation today |
| `spouse: Person` (required, one) | Accepted | So one is fine, zero-or-one is not |
| `date: Date \| None`, `dates: list[Date]` (Embedded) | Refused | Same pattern |
| `names: list[WithCertainty[str]]` | Refused: annotate the list instead | The workaround (`WithCertainty[list[str]]`) says something different (one certainty for all names) |
| `tags: list[str] \| None` | Refused | but `tags: list[str \| None]` is **accepted**, and `None`s go into the stored list. The other way round would be the sensible one |
| `kind: Literal["a", "b"]` | Refused: "use an Enum" | The export and the interface already have a `literal` type (for the `type` field); a `Literal` is the lightest fixed list there is |
| `id_in_other_db: uuid.UUID`, `homepage: HttpUrl`, `email: EmailStr`, `when: datetime.time`, `lasted: timedelta`, `path: Path`, `ip: IPv4Address` | Refused | All are strings or numbers in the database, and `convert_type_for_writing` already knows how to write a `UUID` and an `AnyUrl`. §4 |
| `coords: tuple[float, float]`, `tags: set[str]`, `d: dict[str, str]` | Refused | A tuple and a set are lists with a rule; `dict` is refused because migrations cannot see inside it (a good reason that the message does not give) |
| `extra: SomeBaseModel`, a dataclass | Refused | Right (use `Embedded` or a `TypedDict`), but the message lists the literal types, not the two choices |
| `x: int \| str` | Refused | Right; a union of literals has no storage type |
| a field called `id`, `type`, `meta`, `urls`, `create_new`, `db_labels`, `context_labels`, `semantic_spaces`, `edge_properties` | Refused | Right, and the message says why. `label` is allowed and means the label |

### 2.3 The contract of the generated models

Not errors: things the user has to learn, which the class does not say.

- **`Create` wants everything that is not `X | None`**: every list (`[]`), every relation, every embedded object. A
  model with ten relations needs ten keys in every payload. There is no "default empty" for a list, which is what
  the silent-default rows above would have given.
- `Person(...)` is `Person.Create(...)`; `save()` gives a `ReferenceView` unless `detail=True`; `get()` gives a
  `HeadView` whose relations are `ReferenceView`s (not the thing). Reasonable, but each is a surprise once.
- JSON is camelCase, Python is snake_case; every model has `type`. An entity is referred to as `{"type", "id"}`.
- An enum is stored as its **value**; renaming a member is free, changing a value is a migration. A `Decimal` is a
  string. These are good decisions that a user discovers from a query, not from the class.
- `initialise()` must run after every class and needs settings to exist (or `bind_database=False`). A module that
  calls it at import time breaks the second importer. Tests must `ModelRegistry._reset()`.
- The stubs: `make-stubs` must be rerun by hand after each change, and a reverse relation through a wrapper is
  `typing.Any` in the stub (`Person.HeadView.participants_reverse` in the demo), so the completion a user most
  wants on an entity's page is the one that is missing.

## 3. Are the built-in primitives sufficient, or too many?

The structural primitives are `Document`, `Entity`, `Embedded`, `Trait`/`NonHeritableTrait`, `EdgeModel`,
`AnnotatedValue`, `ReifiedRelation` (and 🚧 `ReifiedRelationDocument`), `SemanticSpace`, `Conjunction`, with
`ViaEdge`, `Fulfils`, `RelationConfig`, `FieldBinding`, `DBField` and the markers as modifiers.

**Sufficient:** yes, for the far limit, as the demo shows, and nothing in it is unused. **Too many:** not in number;
each has a different storage shape and a different rendering, as you say. The problem is which question the user has
to answer to choose one. Today it is "how should this be stored?" (a map property, a node, an edge, a node with a
label), which is the one question a user of a "declare once" framework should never be asked. Set side by side:

| I want to say... | Use | Stored as |
|---|---|---|
| A value, with extra facts about the value (a name, and how sure) | `AnnotatedValue` | a map property |
| Structured data with no identity (a date) | `Embedded` | a node |
| A relation, with a fact or two about the relation (certainty) | `ViaEdge[T, EdgeModel]` | edge properties |
| A relation with fields and perhaps several targets (a person in a role) | `ReifiedRelation[T]` | a node |
| A relation that is itself a document (has a label, is read on its own) | `ReifiedRelationDocument[T]` 🚧 | a head node |
| A context that changes how the contents are read (negation) | `SemanticSpace[T]` | a node, plus `meta` on everything inside |
| A join of several things in slots (cause and effect) | `Conjunction` | a node |
| "Any of these classes" | `Trait` | a label |

The first two rows and the next three are the pairs that will be confused: *AnnotatedValue vs Embedded* and *EdgeModel
vs ReifiedRelation* each differ by storage and by what else you can do (an `Embedded` can be searched into and indexed;
an `AnnotatedValue` cannot be listed; an `EdgeModel` has literals only; a `ReifiedRelation` can be the target of a
derived rule). The rules of thumb in the skill ("a value or two → edge; needs fields and a target → reified") are the
right answer; they live in the skill and in `notes/`, not in the error messages or the docs' first page.

Recommendation: **keep the set, and make the choice teachable rather than smaller.** Concretely:

1. A decision table like the one above at the top of `docs/models.md` and in the tutorial, by the question the user
   has, not by the class.
2. Every refusal names the primitive to use: "a list of `Embedded` is not supported; if each date is a thing of its
   own, make it a `Document`; if you want one date with several readings, make the field `Date` and use a
   `DateRange`".
3. Merge nothing. `AnnotatedValue` is the one candidate (an `Embedded` with `Meta(store="property")` would do the
   same work), but it is used by the library and the demo, it reads well, and the gain is one fewer name.

What does reduce arbitrariness at the near limit is the **not-supported list**, not the primitive count. `X | None`
for a relation and for an embedded object, and `list[Embedded]`, are the three that a plain entity model hits at once.
Supporting the optional ones as a list of at most one in storage (the cardinality mechanism exists) and `list[Embedded]`
as several nodes with an order property would remove most of §2.2 for the near limit. This is already in `TODO.md`
("Model layer"); this review puts it first.

## 4. Proposal (a): storing pydantic's standard types

### 4.1 What is being asked

Pydantic's [standard library types](https://pydantic.dev/docs/validation/latest/api/pydantic/standard_library_types/)
and [pydantic types](https://pydantic.dev/docs/validation/latest/api/pydantic/types/) are, for storage, a short list
of shapes. A graph property can be a string, an integer, a float, a boolean, a date, a datetime, a duration, a list of
these, and (Memgraph only; Neo4j's dialect flattens) a map. So every type is one of: *native*, *a string with a
format*, *a number*, *a list with a rule*, *a map*, or *refuse*.

| Shape | Types | Stored as | Export | Search kind |
|---|---|---|---|---|
| Native | `str int float bool date datetime` (done) | as is | as now | as now |
| String with a format | `UUID`, `AnyUrl`/`HttpUrl`/`AnyHttpUrl`/`FileUrl`, `EmailStr`, `NameEmail`, `IPv4Address`/`IPv6Address`/`IPvAnyAddress`/`...Network`/`...Interface`, `Path`/`PurePath`, `datetime.time` (ISO), `Pattern`, `Color`, `Base64Str`, `PaymentCardNumber` | `str` | `{"type": "str", "format": "uuid" \| "url" \| "email" \| "ip" \| "path" \| "time" \| ...}` | `text` (`eq`, `in`, `starts_with`; no ranges) |
| Number with a meaning | `ByteSize`, `PositiveInt` & co (done: `Annotated`), `Fraction` (as `str` or two ints) | `int`/`float`/`str` | `int`/`float`/`str` + `format` | `number` |
| Exact decimal | `Decimal` | today `str`; see 4.3 | `decimal` | `decimal` |
| Duration | `timedelta` | Cypher `Duration` (both databases have it) or ISO 8601 string | `{"type": "duration"}` (new widget) | `number` on total seconds, or `temporal` |
| Zoned datetime | `datetime` with tzinfo, `AwareDatetime`, `NaiveDatetime`, `PastDatetime`... | *to check* what the drivers do today | `datetime` | `temporal` |
| Fixed list | `Literal["a", "b"]`, `Literal[1, 2]` | the value | `literal` (exists) | `simple` |
| List with a rule | `set[X]`/`frozenset[X]` (no order, no repeats), `tuple[X, Y]` (fixed length), `Sequence[X]`, `deque[X]` | a list; the rule is a validator on read and write | `list` (+ `unique: true` / `length: n`) | `list` |
| Enum variants | `Enum` (done), `IntEnum`, `StrEnum`, `IntFlag`/`Flag` (store the int; refuse or warn: migrations cannot follow combinations) | the value | `enum` | `simple` |
| Map | `TypedDict` (done), `NamedTuple`, a pydantic `BaseModel` or dataclass **with literal fields only** | a map property (Memgraph) or flattened (Neo4j dialect does this for `meta` already) | `typedDict` | fields by dot path |
| Refuse, and say why | `dict[K, V]` (open keys: migrations and search cannot see inside), `Json` (a string that is parsed: store the `str`), `Any`/`object`, `bytes` (Memgraph has no bytes; base64 `str` if wanted), `complex`, `SecretStr`/`SecretBytes` (a research database is not where a secret goes; and serialising hides the value), `ImportString`, `Callable`, `type` | | | |

So "all or most" is realistic: everything but the last row reduces to a shape that already exists in every one of
the seven places of §1. The work is not in the backends; it is in saying it **once**.

### 4.2 Design: a literal codec registry

One object per storage shape, registered once, that every place in §1 asks:

```python
@dataclass(frozen=True)
class LiteralCodec:
    matches: Callable[[Any], bool]        # is this annotation (after Annotated/Optional stripping) mine?
    storage: Literal["str", "int", "float", "bool", "date", "datetime", "duration", "list", "map"]
    export: Callable[[Any], dict]         # {"type": "str", "format": "uuid"}
    search_kind: Kind                     # text | number | decimal | temporal | simple | list
    to_db: Callable[[Any], Any] = identity
    from_db: Callable[[Any], Any] = identity
    constraints: Callable[[Any], list[BaseMetadata]] = lambda tp: []   # what the type itself implies (PositiveInt → Gt(0))
```

- `is_literal` becomes "some codec matches"; `LITERAL_TYPES` is the set of codecs for the natives.
- `convert_type_for_writing` and the `from_database` hook ask the codec of the field (today they switch on the
  *value*, which is why a `UUID` can be written but not declared).
- `Exporter.describe_type` asks `codec.export`. The interface needs one new widget for `duration`, and `format` on a
  `str` becomes an HTML `type=` or `inputmode`; nothing else changes in `LiteralEditor.tsx`.
- `kind_of` asks `codec.search_kind`.
- The migration snapshot records `storage` and the type's name; a change of type between two codecs of the same
  `storage` is `StateOnly`, between different storages `AlterLiteralType` (as now).
- A package may register a codec (`pangloss_dates` could register `JulianDay` as an `int` codec). This is the same
  shape as `hooks` and the meta slots: the core knows the shapes, the packages the types.

Constraints are the second half: `map_validators_to_kwargs` should carry every `annotated_types` member it can
express (`Predicate` cannot be exported; carry it and mark the field "checked on the server only"), and
`pydantic.StringConstraints` (`pattern`, `strip_whitespace`, `to_lower`, `min_length`, `max_length`), which is what
`constr` and `Field(pattern=...)` become. Anything in `Annotated` that is neither a known constraint nor a
`FieldMarker` nor a `RelationConfig` should be an **error**, not dropped (`Strict()` included, until strictness is
decided).

### 4.3 Decisions this needs

- **`Decimal`.** Keep the string and the `toFloat()` comparison (exact at rest, approximate to search), or store a
  float beside it for ordering and indexes. Recommendation: keep the string, state the comparison rule in
  `docs/relations.md`, and refuse `Meta(indexes=[a decimal])` with a message, since a string index does not order
  numbers.
- **Zoned datetimes.** Check the round trip on both backends first (`conformance/`). Then either store UTC and the
  offset in two properties, or require naive datetimes and say so.
- **`IntFlag`.** Refuse, or store as an int with no enum migrations. Refuse is simpler.
- **A pydantic `BaseModel` as a map.** It is a `TypedDict` with methods, and the methods will be lost like a declared
  class's. Allow only if §2.1's method problem has an answer; otherwise refuse with "use a TypedDict or an Embedded".
- **Order.** `Literal`, `UUID`, the URL family, `time`, `set`/`tuple`, `StringConstraints` carry the most value for
  the least decision; `timedelta` and zoned datetimes need the backend checks; the rest can wait for a request.

Cost, as a guess: the registry and the refit of the seven places, with conformance tests for the round trip of each
shape on both backends, is a few days; the optional-relation work of §3 is separate and larger.

## 5. Proposal (b): a language server

### 5.1 What the tools you have can and cannot do

- **`ty` and `pyrefly`** are whole-program type checkers in Rust with built-in LSP servers. Neither has a plugin
  API (as of this writing; *to check* against their current releases), so neither can be taught Pangloss's rules.
  `mypy` has plugins (pydantic ships one), but it is the slow one and is not what you use.
- **`ruff`** has no third-party rule plugins either (long requested; *to check* whether the plugin system that has
  been discussed has shipped). Its rules are syntactic, and most of §2 needs the resolved model (is this annotation
  an `Entity`? is this class a `Document`?), which is only known after import.
- **Stubs are still needed.** A type checker only knows `Person.Create` from a `.pyi`. A language server can give
  completions and diagnostics, but it cannot feed *types* into `pyrefly`'s checking of `await Person.get(id)`. So
  the goal is not "instead of stubs" but "stubs that are never stale, plus the checks a type checker cannot make".

A second LSP beside `pyrefly` is normal: VS Code, Neovim, Zed and Helix all run several servers for one language and
merge their diagnostics and completions.

### 5.2 What a `pangloss-lsp` would do

Built on `pygls` (Python), as a `pangloss lsp` command, so it runs in the project's own virtual environment and can
import its models.

1. **Diagnostics from the real analysis.** On open and on save of a module in an installed app: in a subprocess (so a
   broken model cannot take the server down, and so `ModelRegistry` is fresh), import the apps, run
   `initialise(bind_database=False)`, and collect every `PanglossModelError` and the new warnings of §5.3. Map each to a
   range: `inspect.getsourcelines(cls)` gives the class; an `ast` walk finds the `AnnAssign` of the field. Pydantic's
   `FieldInfo` has no source position, so this mapping is the one piece of plumbing to write; it belongs in
   `pangloss_models` as a function (`source_range(model, field)`), because the CLI wants it too (next point).
2. **`pangloss check --json`** first, with the same diagnostics as `file:line:col: message`, for CI and pre-commit.
   The LSP is then a thin wrapper that watches files and publishes what `check` returns. This is the part worth
   building even if the LSP is never built.
3. **Stubs kept fresh.** After a successful analysis, rewrite the `.pyi` (`write_stubs`), so `pyrefly` sees the new
   `Create` a second later. This alone removes "run `make-stubs` again" from the tutorial.
4. **Completions `pyrefly` cannot give**, because they are strings or come from the registry, not from types:
   `Document.Meta(` and `Entity.Meta(` options with their docs; `RelationConfig(reverse_name=` (suggest `<field>_reverse`
   and warn on a clash); the `_x_meta` slot names and their classes; `InterfaceMeta(view_card="app:Component")` from the
   manifests; `Meta(indexes=[...])` from the model's own literal fields; `Where` keys; the model names allowed in a
   `FieldBinding`'s `allowed_type_names`.
5. **Hover** on a field: what it is to Pangloss ("relation to Person or Group, one edge pair per item, reverse
   `involves_reverse`; in `Create`: `list[Person.ReferenceSet | Group.ReferenceSet]`, required"). This is the single
   most useful thing for the "looks like pydantic" worry: the hover says what the line *means*.
6. **Code actions** for the common refusals: "make this a `list[Person]`", "wrap the list: `WithCertainty[list[str]]`",
   "move the default to `X | None = None`", "regenerate stubs".

Not in scope: anything a type checker does (types of expressions, unresolved names), or Cypher.

### 5.3 The checks, and where they should live

Most of §2.1 should be **errors or warnings at `initialise()`**, not editor features, under "fail early and loudly".
The LSP then only shows them at the line. Proposed, in `initialise_field_definitions` and `builder`:

| Case | Proposed behaviour |
|---|---|
| A default other than `None` on a literal or list field | **Decide**: honour it (carry `default`/`default_factory` to `Create` and `Update`; the migration planner then has a value to fill existing nodes with, which is the harder change), or refuse with "Pangloss does not carry defaults; write `X \| None = None`". Refusing is one line and removes the worst silent row; honouring is better DX and is what pydantic users expect |
| `@field_validator`, `@computed_field`, a `@property`, a method on a declared class | Warn at `initialise()` (`PanglossModelWarning`, shown by the CLI and the LSP), saying that generated models do not have them. Or: copy `field_validator`s to the written models as `model_validator`s are; methods cannot be copied sensibly |
| `model_config` on a declared class | Warn, unless it is exactly the base's |
| Unknown `Annotated` metadata (`Field(pattern=)`, `StringConstraints`, `Strict`, anything not a known constraint, marker or config) | Error: "not carried; supported constraints are ..." (until §4.2 carries them) |
| Unknown keys in a `Create`/`Update` payload | **Decide** whether `extra="forbid"` on the generated write models is wanted. The API would then 422 a misspelled key instead of dropping it. The cost is that a client built against a newer model cannot talk to an older server; the SDK pins the model version, so that cost is small |
| `list[X \| None]` | Refuse (and allow `list[X] \| None` as "no list" if there is a meaning for it; otherwise refuse both, with the same message) |

With these in `initialise()`, `pangloss check` and the server, pre-commit and the LSP all say the same thing from one
source, which is the only way the rules stay in step.

### 5.4 Cost and order

`check --json` with ranges: a day or two (the range mapping, the warnings of §5.3, the CLI output). The LSP with
diagnostics and stub refresh: two or three days on top, with `pygls`; completions and hover a few more, each
independent. The e2e of it is an editor; a test can drive the server over stdio with `pytest-lsp`.

## 6. Recommendations, in order

1. **Make the silent rows loud** (§5.3): defaults, validators, methods, config, unknown `Annotated` metadata. A day,
   mostly messages and tests, and the biggest gain per hour on the "looks like pydantic" worry.
2. **Decide `extra="forbid"`** for `Create` and `Update`. It is a one-line change with an API consequence; it needs
   your call, not building.
3. **Optional relations and optional embedded objects** as 0..1 (§3), since they are the first thing a plain entity
   model writes. `list[Embedded]` after, if wanted.
4. **The codec registry** (§4.2), starting with `Literal`, `UUID`, the URL family, `time`, `set`/`tuple`, and
   `StringConstraints`; the Decimal and zoned-datetime decisions written down in `docs/relations.md` whichever way.
5. **The decision table** of §3 at the top of `docs/models.md` and in the tutorial; every refusal names the
   alternative.
6. **`pangloss check --json`** with source ranges, then the LSP on top of it with stub refresh first, hover and
   completions after.

The probe script that produced §2.1 should become a test in `packages/pangloss-models/tests/` so that the table
stays true: one case per type, asserting either the definition kind and the `Create` field or the error message.
