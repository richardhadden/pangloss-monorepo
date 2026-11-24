# Semantic spaces: the implementation plan ⏳

Written 2026-11-24. **Nothing here is built, and nothing is to be built without the user's word.** The design is in
[the fields of a semantic space](semantic-space-fields.md) (and [the report](semantic-spaces-formalisation.md);
[a summary](semantic-spaces-summary.md) of both). This page is how it would be built: in what order, what each step
changes and where, the tests that say it is done, and who builds it. Where the code differs from a step once it is
built, the step gets an "As built" section and keeps its text.

## Contents

- What is taken as settled
- How the work is run
- Who builds each step
- Phase 0: the ground
- Phase 1: the fault in recording spaces
- Phase 2: the four fields in the core
- Phase 3: the walk
- Phase 4: the packages that read spaces
- Phase 5: the interface
- Phase 6: comparison (amendments to phase 12)
- Phase 7: the demo, the guide and the skill
- Calls taken
- Not in this plan
- What can go wrong
- Where the work stands

## What is taken as settled

| | Settled | Where |
|---|---|---|
| The fields | `veridical`, `fit`, `logical`, `unary` on `SemanticSpaceMeta`; not ChatGPT's four, and not both (the user, 2026-11-24) | [semantic-space-fields.md](semantic-space-fields.md), "Decided" |
| A statement on its own, or nested with no space, is asserted | The principle Pangloss already has | [semantic-space-fields.md](semantic-space-fields.md#veridical) |
| The spaces decide relations, never distances | No "context" part of the vectors | [semantic-space-fields.md](semantic-space-fields.md#how-it-works-with-similarity) |
| The core knows no package | Each package reads the fields through the core; nothing of a package is named in the core | the skill, "Design principles" |

Everything else is either a call of this page (below, none confirmed) or a decision marked **decide** in its step.

## How the work is run

As in [the similarity build plan](similarity-build-plan.md#how-the-work-is-run):

- **Branches**: one for each phase, from `dev` (`spaces-1-fault`, `spaces-2-fields`, …), merged into `dev` when its
  last step is green.
- **Commits**: one for each step, pushed. **A pause for the user's word after each phase**, and inside a phase
  wherever a step says **decide**.
- **A session can stop at any moment**: a step is committed and pushed as soon as it is green, and "Where the work
  stands" at the foot of this page is brought up to date in the same commit, with the memory note.
- **Three kinds of test**, named in every step: *pure* (no database), *live* (on Memgraph and on Neo4j, with the
  fixtures of `pangloss_testing.live`), *conformance* (`pangloss_testing/conformance/`, for what storage does).
- **Docs with the code**: a step that changes what a modeller or a package author types updates its page in the same
  commit ([semantic-spaces.md](semantic-spaces.md) is the reference page for spaces), and the skill when it would
  otherwise be wrong.
- **Never `:7687` (the tests) or `:7688` (the demo) for scratch work**; a migration of the demo is written and read,
  not applied, unless the user says.

## Who builds each step

The agents of `.claude/agents/`: **`builder`** builds decided work from a written brief, with its tests, and does
not commit; **`test-runner`** runs tests and reports. **Main** is the session holding this plan. Main settles what a
step leaves open, makes every change to a core write or read path (here: `context.py`, the meta and its checks, the
walk), writes the briefs, reads each diff, writes "As built", and commits. `builder` builds the packages' readers,
the interface, the demo's changes and the docs from briefs. `test-runner` makes every run.

## Phase 0: the ground

Small, by main, before any brief, because the briefs quote what it finds.

| Step | What | Tests | Who | State |
|---|---|---|---|---|
| **0.1 Why single relations share their lists** | `propagate_context` (`pangloss_models/context.py`) gives what a single relation holds the node's own lists, and its docstring says this "is kept". The file's history has only `2a11400f` ("finished migrations") and a formatting commit. Find whether anything depends on it: the context labels of a document in a single relation seen by its later siblings (label templates, the interface's bands, history's diffs), by running the models', Cypher's and the interface's tests with the sharing removed, on a scratch checkout | None committed: a written finding in 1.1's brief | Main | To do |
| **0.2 What `stop` does, as a test** | Whether a statement inside `Negative` (`FastRPMeta(stop=True)`) is still joined to its own people, on a graph in memory (`pangloss_fastrp.maths.joins`): factoid → `Negative` → statement → person. Read so far: it is | Pure, in `pangloss-fastrp`'s unit tests, kept as a test of what the code does | Main | To do |
| **0.3 Who reads the spaces** | Every reader of `meta.semantic_spaces` and `meta.context_labels`, by file and line: search's `$spaces` and `through`, the RDF export (`convert.py`, `pgo:inSpace`), derived justifications, the library's clusters (`clusters.py`, `in_spaces`), label templates, the interface's bands, history. What each would see change in phase 1 | None: a list in 1.1's brief | `Explore`, read by main | To do |

## Phase 1: the fault in recording spaces

**Decide first** (the user): fix it, and how stored data is mended (1.2).

| Step | What | Tests | Who | State |
|---|---|---|---|---|
| **1.1 Each relation's contents get their own lists** | In `propagate_context`, what a single relation holds is given copies of the lists, as each item of a list already is (`copy`, `deepcopy`); or, if 0.1 finds that a document's context entries are meant to be seen by later siblings, copies of the spaces only. `_InstanceContext.children` (`model_bases/instance_context.py`) and the migrations' `StoredContext` (`pangloss_cypher/migrations/operations.py`) share the one algorithm, so both follow | Pure: the scratch trial's case (`/tmp/space-trial/test_single_slots.py`: a conjunction with two single slots each in a space, in a list and in a single field) made a test in `pangloss-models`; a document in a single relation and a sibling after it; the existing context tests unchanged. Conformance: written and read back, on both backends (beside the tests that check `semantic_spaces` now) | Main | To do |
| **1.2 Stored data mended** (**decide**: a command or a migration) | Nodes written before the fix have the wrong lists. `recompute_contexts` (`pangloss_cypher/migrations/operations.py`) already works them out again from what is stored. Proposed: `pangloss contexts check` (the heads whose stored lists differ from a recomputation, by class) and `pangloss contexts fix` (recompute those), run once by a project after upgrading; the classes to look at are those with two single relations that can each hold a space, found from the models. The other way: a migration operation that `makemigrations` writes once for such classes | Live, both backends: a document written in the old shape (by hand, in the test), `check` finds it, `fix` mends it, `check` is clean, nothing else changes (nodes, edges, versions) | `builder` from main's brief | To do |
| **1.3 Docs** | [semantic-spaces.md](semantic-spaces.md): what is recorded, the rule for single relations, the command; `status.md`; `TODO.md`; the migrations guide if 1.2 is a migration | — | `builder` | To do |

## Phase 2: the four fields in the core

| Step | What | Tests | Who | State |
|---|---|---|---|---|
| **2.1 The fields and `Modal`** | On `SemanticSpaceMeta` (`pangloss_models/model_bases/semantic_space.py`): `veridical: Literal[1, 0, -1] = 0`, `fit: Literal["describes", "prescribes"] = "describes"`, `logical: Literal["not"] \| Modal \| None = None`, `unary: bool \| None = None` (`None`: what `logical` implies, else `False`). Inherited by the meta kit's default rule. `Modal(force, flavour, of_not=False)`: frozen, `force` one of `"necessity"` and `"possibility"`, `flavour` a non-empty word; exported from `pangloss_models` (and `implementation_docs/imports.md`). **Decide** with 2.2: `logical` as force and flavour (decision 2 of the fields page) | Pure: defaults; a family class sets values once and a subclass changes one and inherits the rest; `Modal`'s validation | Main | To do |
| **2.2 The checks at `initialise()`** | A module `initialise_models/check_semantic_spaces.py`, called where `check_label_templates` is (`model_registry.py`). Refused, by the class's name, each as a `PanglossModelError` with `fix=` (so that the language server offers it): `"not"` with `veridical` other than `-1`; a possibility with `veridical` other than `0`; `veridical=-1` on a modal that is not a necessity `of_not`; `veridical=1` on a necessity `of_not`; `unary=False` on `"not"` or a modal `of_not` | Pure: every refusal by its message and its `fix` | `builder` from main's brief | To do |
| **2.3 `unary` enforced** | A unary space's `contents` gets a length of at most one in its field definition, so `Create` and `Update` refuse a second item with a message that says why ("`Not` takes one statement: not (A and B) is not (not A) and (not B); use one `Not` for each"), and the interface's handling of `MaxLen` (no "Add" past the last) follows. Main first finds where a space's `contents` is made a field definition (`initialise_models/initialise_field_definitions.py`) | Pure: two items refused, one taken, the message; the export says the length | `builder` | To do |
| **2.4 Exported, not migrated** | `export.py` (the model's export, beside `useInSemanticSpaceLabel`) gives a space's `veridical`, `fit`, `logical` (`{"not": true}` or `{"force", "flavour", "ofNot"}`) and `unary`; `interface-core/src/types/models.ts` has them. The migration snapshot (`migrations/diff.py`, its list of keys) is left as it is: the fields are not data | Pure: the export; `packages/pangloss-interface/tests/test_models_match_typescript.py` passes; changing a space's `veridical` in a project makes no migration (`makemigrations` finds nothing) | `builder` | To do |
| **2.5 The markers of who** (**decide**: decision 4) | `Holder()` and `Addressee()`, field markers (`pangloss_models/markers.py`, `FieldMarker`) on a relation of a statement class: who holds the attitude or gives the order, and to whom. At most one of each on a class, on a relation to agents; found through a reified relation (a proxy). On a relation a marker is kept on the field's definition and not exported today: exporting them (for the interface and the RDF export) is part of the step | Pure: the checks; reading the marked fields of a class; the export | `builder` | Decide |
| **2.6 Docs and the skill** | [semantic-spaces.md](semantic-spaces.md) (the fields, ✅), [models.md](models.md) (the meta options), `imports.md`, the guide's statements page (`guide/tutorial/04-statements.md`), `status.md`; the skill's `references/modelling.md` (a new `Meta` option is one a newcomer needs), and `check_skill.py` | The skill's check | `builder`, read by main | To do |

## Phase 3: the walk

The one piece of semantics every reader shares, so in the core, pure, and by main.

| Step | What | Tests | Who | State |
|---|---|---|---|---|
| **3.1 `pangloss_models.spaces`** | `signature(context_labels) -> Signature`: the path read from a node's `context_labels` (spaces and the documents between them), each run of spaces next to each other normalised (the table under [`logical`](semantic-space-fields.md#logical): within one flavour; `of_not`; a double "not"), then [the walk](semantic-space-fields.md#veridical): `veridical`, the lean when it is `0`, the `fit` of the innermost space that prescribes, the id of the statement holding it, and the force and flavour of the innermost modal. Reads the classes' meta from the registry; no database | Pure: every row of the walk's table and the normalising table, the two limits (two flavours never rewritten; a statement between stops it), the case the old flat list gets wrong (`Not[ChurchService(parts=[p])]`). The cases are written once, as data (`space_cases.json`, beside the models' `label_cases.json`), for the interface's port (5.3) to pass too | Main | To do |
| **3.2 Read from what is stored** | Every reader gets a node's `context_labels` already (`View`, `HeadView`, the rows of the packages' own queries). Where a package's query reads only `semantic_spaces` (the library's claims, the time part's rows), it reads `context_labels` too: listed for phase 4 | Pure: `signature` of a node read back (the conformance write of 1.1) | Main | To do |
| **3.3 Docs** | [semantic-spaces.md](semantic-spaces.md): `signature`, what it gives, with three examples | — | Main | To do |

**Computed when read, never stored** (call c): a change to a space's fields then changes nothing stored and needs no
migration. What waits on that is search: a `$asserted` condition would need the value on the node, or a filter
after the query (4.6).

## Phase 4: the packages that read spaces

Each step is one package, backend-neutral, with its own tests on both backends. **Each changes behaviour, so each is
decided by the user before it is built** (decision 3). Each is written so that **a project that sets no field sees
no change** (call e), except where the step says.

| Step | What | Tests | Who | State |
|---|---|---|---|---|
| **4.1 Derived rules** | A space whose `DerivedMeta` gives no `derivation` takes it from `veridical`: `1` transparent, `0` qualify (today's default), `-1` block. Where: the default (`pangloss_derived/declare.py`) and its use (`check.py`). A `DerivedMeta` that says one still wins | Live, both backends: a rule over a purchase in a `1`, a `0` and a `-1` space, and with `DerivedMeta` set; the demo's rules unchanged | `builder` | Decide |
| **4.2 Identity claims** | A `SameEntity` whose path is `1` joins as if it were in no space; one whose path is `-1` is a claim that the two are different, given in the cluster apart ("said to be different"), not joining. Where: `pangloss_library/clusters.py` (its query reads `semantic_spaces`; it reads `context_labels` too, for the walk). Whether reconciliation should then leave such a candidate out is later | Live, both backends: each case; a claim in a `0` space as today | `builder` | Decide |
| **4.3 The time part** | A date counts for nothing when its statement's path is `-1`; **decide** whether `0` too (that changes every project with statements in spaces, and answers the open item of step 9.3 of the similarity plan). Where: `counts_for` (`pangloss_dates_vectors/part.py`), whose rows read `context_labels`. The part's signature takes in the fields, so a rebuild is due | Pure (`counts_for`); the part's suite (`PartSuite`, `dated=True`); a statement in `Not` has no time vector | `builder` | Decide |
| **4.4 The RDF export** | What is inside a space whose path is `1` has its direct triples (today nothing inside any space does); `0` and `-1` as today | The RDF package's tests: a `Known[...]` statement asserted; a `Not[...]` not | `builder` | Decide |
| **4.5 The graph part** | From 0.2: if a negated statement is still joined to its people, **decide** what `stop` should do (end the statement's own joins too, or a new option); and whether a space with no `FastRPMeta` takes a default weight from `veridical`. Measured first on the planted world (`pangloss_testing.planted`) with spaces in it, against the same world without: which people come out alike | Pure (the maps and the joins); the part's suite; the measurement written into this step | Main measures, `builder` builds | Decide |
| **4.6 Search** (outline) | `"$asserted": true` on a pattern for a document: needs the value on the node (stored at write, and then a migration whenever a space's fields change) or a filter after the query (slow on large results). Not built until a page needs it | — | — | Later |

## Phase 5: the interface

**Decide first** (decision 7): which of these, and whether a headless space is the default or asked for by
`InterfaceMeta(headless=True)` on the space, as on a reified relation.

| Step | What | Tests | Who | State |
|---|---|---|---|---|
| **5.1 A space with no choice, drawn without its head** | `headlessIn` (`interface-core/src/schema/headless.ts`) takes a semantic space too: in a field that can hold that space and nothing else, one of it, and must (`Order.content: Ordered[...]`). The form (`components/form/ModelFields.tsx`) draws its contents with no head bar; the view (`ItemContents.tsx`) keeps the band and colour | Vitest (`headless.test.ts`); e2e on the e2e project's models; a row of `e2e/COVERAGE.md`; the dev build (`e2e/test_dev_mode.py`) | `builder`; `solidjs-v2-reviewer` (main) | Decide |
| **5.2 "Not" as a toggle** | Where a field or a space's contents offers `X \| Not[X]` (a space with `logical="not"`), the form shows a "not" toggle on the item, which wraps it in the space or takes it out, client-side (as the retyping of nested documents does), in place of the space's section of the type menu (`TypeMenu`). Its text as `t()` slots with translations | Vitest; e2e: toggle on, save, read back inside `Not`; toggle off | `builder`; `solidjs-v2-reviewer` (main) | Decide |
| **5.3 What is not asserted, marked** | The walk ported to TypeScript (`interface-core`, pure), passing the same `space_cases.json` as 3.1. A statement whose path is not `1` is marked where it is listed without its band (search results, a person's statements); its relation shown in "Similar" waits for phase 6 | Vitest on the shared cases; e2e: a statement in `Not` marked in a list | `builder`; `solidjs-v2-reviewer` (main) | Decide |

## Phase 6: comparison (amendments to phase 12)

Phase 12 of [the similarity build plan](similarity-build-plan.md) (`pangloss-compare`) is written and **on hold at
the user's word** (`TODO.md`). Nothing here is built before it is; these are the changes its steps would take, to be
copied into its steps when it is taken up. **Decide** (decision 6) whether its verdict takes in the relations of
[How it works with similarity](semantic-space-fields.md#how-it-works-with-similarity).

| Phase 12 step | The change |
|---|---|
| 12.1 Planted comparisons | Beside its `Negative` and `Hypothetical` reports: reports in `Reported` and `Believed` leaning each way; orders with and without their carrying out; orders not to, kept and broken; permissions used; "cannot have been" (`Not[Might[...]]`); two normative orders. The truth (`world.verdicts`) gains the relations |
| 12.2 `CompareMeta` | `negates=True` goes (it is `veridical=-1`); `compared=False` stays, compare's own choice; a weight for each space class (strength), hand-set (**decide** with decision 5: there, or `orientation` and strength in the core) |
| 12.3 The verdict | After the contents' verdict, the two signatures (3.1) give the relation, by the table. Fulfilment asks for the addressee (2.5) and for what came after (`orientation`, decision 5) |
| 12.4 Pairs by rule | Two statements of one factoid may be a pair when one prescribes what the other tells (an order and its failure); never for one event told twice (call c of phase 12 as it is) |
| 12.6 `EventJudgement` | Its verdicts gain "carried out", "not carried out" and "breach" (**decide**) |
| 12.7 The section | "Compared" and "Similar" label each statement by its relation; an order's page has "Carried out?" |
| 12.9 Learning | The pair of signatures is among the features |

## Phase 7: the demo, the guide and the skill

| Step | What | Tests | Who | State |
|---|---|---|---|---|
| **7.1 The demo's spaces** | The fields on the demo's spaces, which is no data change and no migration: `Negative` (`logical="not"`), `Hypothetical` (`Modal("possibility", "epistemic")`), `PositiveSubjunctive` and `NegativeSubjunctive` (`fit="prescribes"`). **Decide** (decision 8): whether to go further, which is a migration each (the wrapping and unwrapping operations exist): `Negative` split into a denial and a "not"; `Order.thing_ordered` as `Ordered[Statement \| Not[Statement]]` in place of the two subjunctives. The demo's stubs made again (`../.venv/bin/pangloss make-stubs`, from `pangloss-demo/`) | The demo's tests; `pangloss check` clean on the demo | `builder` | Decide |
| **7.2 The guide** | For modellers: a page on spaces (what to declare, the four fields, a family class, the walk in two examples). For the people who enter data: the paragraph of [How to explain it to people](semantic-space-fields.md#how-to-explain-it-to-people), as a page a project can hand on | — | `builder`, read by main | To do |
| **7.3 Finished** | "As built" on each step; [semantic-space-fields.md](semantic-space-fields.md) and [the summary](semantic-spaces-summary.md) say what is built; `status.md`; `TODO.md`; the skill; `./run_tests.sh` whole; `/code-review` on the work's diff | The whole suite | Main, `test-runner` | To do |

**What runs side by side**: 0.1, 0.2 and 0.3 together; phase 2 after phase 1 (the readers' tests need right paths),
with 2.5 beside 2.2 to 2.4; 3.1 by main while `builder` does 2.3 and 2.4; the steps of phase 4 one after another (they
share the conformance fixtures), in any order the user decides; phase 5 after 3.1; phase 6 only with phase 12.

## Calls taken

None confirmed by the user.

| | Call | Instead of |
|---|---|---|
| a | The fault is fixed first (phase 1), since every reader depends on right paths | The fields first |
| b | The walk lives in the core (`pangloss_models.spaces`), pure, because several packages read it | In `pangloss-compare` |
| c | The signature is worked out when read, never stored, so the fields stay "not data" | A value stored on each node (search would be quicker; every change to a space's fields would be a migration) |
| d | `unary` is a length of one on the `contents` field, so the interface's handling of a length follows | A validator of its own |
| e | Every package's new behaviour starts from the fields, so a project that sets none sees no change; the one exception, a date in a `0` space counting for nothing (4.3), is asked | Changing what every space does at once |
| f | The walk's cases are data shared by the Python and the TypeScript tests | Two sets of tests that can drift |
| g | Mending stored data is a command run once (`pangloss contexts check \| fix`) | A migration that `makemigrations` writes |

## Not in this plan

- **ChatGPT's four fields** (decided against).
- **Researchers' assessments** (`NegationAssessment`): a document citing the statement, as `EventJudgement` is;
  whose class it is, compare's or a project's, is the report's open question 5.
- **Spaces over entities**: a rule for modellers (use a relation), in the guide of 7.2, not a check.
- **`orientation`, strength, `generic` contents, an `Alleged` space**: what the manmax exercise asks for beyond the
  four. `orientation` and strength are decision 5 and land with phase 6 if taken; `Alleged` is a project's space
  with `veridical=0`, needing nothing of the core; `generic` waits for phase 12.
- **Search by assertedness** (4.6, outline only).
- **The manmax port.**

## What can go wrong

- **The fix of 1.1 changes what other readers see.** Search, the RDF export, derived justifications and the
  interface all read the lists; 0.3 lists them, and their tests run in 1.1.
- **A project mends its data late.** Until `pangloss contexts fix` is run, stored paths of the affected shape are
  wrong and the walk gives wrong answers for them; `pangloss contexts check` says how many. (`pangloss check` reads
  no database, so it cannot say it.)
- **Too many spaces.** The fields make any number of spaces cheap to declare, and a project may declare more than its
  editors can tell apart. The guide (7.2) says to start from families and statement types that bring their spaces.
- **Flavours spelt two ways** (`"deontic"`, `"Deontic"`): two flavours, never rewritten into each other. `initialise()`
  could warn of two flavours that differ only in case.
- **The walk in two languages.** Kept equal by the shared cases (call f).

## Where the work stands

2026-11-24: **the plan is written; nothing is built.** Waiting for the user: the decisions of
[semantic-space-fields.md](semantic-space-fields.md#decisions-for-the-user), and the word to start phase 0.
