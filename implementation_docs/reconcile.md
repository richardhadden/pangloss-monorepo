# Reconciliation (`pangloss-reconcile`) 🚧

Status (2026-11-23): phase 10 of [the build plan](similarity-build-plan.md) is built but for its toolchain mode:
the package and its settings, the candidates of an unknown found and scored by the parts of similarity, the
reasons (`shared`), the two routes, the candidates in review's reconcile dialog, a seeded floor of quality, and
the measurements at size on both backends. Step 11.2 is built: the entities shared are in the score, counted for
every candidate found, and the least score of a candidate is a setting, cut at the server. Step 11.4 is built: what
the stored route offered, and what a person chose of it, are kept ("Decisions kept", below), for 11.5 to learn
from. Step 11.5 is built: the decisions are fitted, compared and written as a fit, put in use past a check
("Learning from decisions"). Step 11.6 is built: the stored route says, from the fit in use, how likely the one meant is
none of those offered ("None of these"); the ranking stays the hand-set score's. Step 10.5c is built: what to
suggest for an unknown, and its settings ("What to suggest", 🚧 until the worker that writes it, 10.5d), and a
toolchain's suggestion that no person has confirmed is no evidence ("Reasons"). Step 10.5d is built: the worker that
writes suggestions in the place of stand-ins ("The worker that suggests", 🚧 until what sets it off, learning from
confirmations and the measurements, 10.5e to 10.5g). How to use it: [the guide](../guide/vectors/reconcile.md). The design
and its decisions are the build plan's phase 10, "Read again (2026-11-22)"; several are not yet confirmed by the
user.

## What it does ✅

A document may name someone it has not identified: a **stand-in** in the place of an entity (review's
`Unreconciled`, with its label and the class it would be, `unreconciled_type`). Such a node of a write plan is an
**unknown** (`pangloss_vectors.unknowns_of`: a node whose class is the document of a `hooks.StandIn` with a
`named_type`). For each unknown, this package gives the entities it may be, best first, each with a score and the
score of each part, and writes nothing. It knows the parts only through `pangloss_vectors.parts` and the stand-ins
only through `unknowns_of`: it imports no part's package and not `pangloss-review`.

```python
INSTALLED_APPS = [..., "pangloss_vectors", "pangloss_fastrp", "pangloss_names", "pangloss_reconcile"]
VECTORS_PROFILES = {"who": {"name": 1, "graph": 0.25}}
RECONCILE_PROFILE = "who"
```

`requires = {"cypher", "vector_index"}`. It depends on `pangloss-vectors`, `pangloss-learn`, `pangloss-cypher`,
`pangloss-models`, `pangloss-core` and `pangloss-api`.

## Settings ✅

Checked at `initialise()` when the app is installed (`settings.py`), each refusal saying what to set:

| Setting | Default | |
|---|---|---|
| `RECONCILE_PROFILE` | None | The profile candidates are found and scored by. None: the profile that weighs the most parts that have `unknown` (at least one). Refused: a name that is no profile, one that weighs no such part, no profile that does, or, without a name, several that weigh as many (with `pangloss-fastrp` installed, `default` weighs the class and the graph, as many as a `who` of the name and the graph: such a project names `who`) |
| `RECONCILE_FETCH` | 50 | How many candidates each part is asked for. A whole number from 1 to 1,000 |
| `RECONCILE_WEIGHTS` | `{}` | The weight of each part in the score; a part not named has the profile's. `shared` may be named beside the parts (the entities shared, below): 1.5 unless given; `{"shared": 0}` is phase 10's score exactly. Refused: a name that is no part and not `shared`, a weight that is not a number of 0 or more, and weights that leave none of the parts the profile weighs above 0 (`shared` alone is not enough: with no part nothing is found) |
| `RECONCILE_MOST_UNKNOWNS` | 20 | The most unknowns asked about at once. A plan with more is refused before any part is asked (`TooManyUnknowns`; a 422 that says how many it has and the most). A whole number of 1 or more |
| `RECONCILE_REASONS` | 5 | The most entities a candidate is said to share with the payload (`shared`); 0 shows none. It does not decide whether they are counted (the score counts them while the weight of `shared` is above 0). A whole number of 0 or more |
| `RECONCILE_LEAST_SCORE` | 0.15 | The least score of a candidate either route gives: those under it are left out, after ranking and before the cut to `limit`. A number from 0 to 1. Not a query parameter |
| `RECONCILE_KEEP_DECISIONS` | True | Whether the stored route keeps what it offered and a reconciliation made of it is kept as an example ("Decisions kept"). False: nothing is written, the listener does nothing. True or False |
| `RECONCILE_SHOWN_FOR` | 30 | In minutes, how long what was offered can make an example: a reconciliation later than that makes none, and `pangloss reconcile sweep` removes what is older. A finite number above 0 |
| `RECONCILE_LEARN_FROM` | 100 | The fewest decisions a fit is made of for it to be put in use ("Learning from decisions"). A whole number of 1 or more |
| `RECONCILE_NEW_ABOVE` | 0.5 | The stored route says an unknown is probably none of those offered (`probablyNew`) when the fit in use gives a likelihood of that above it ("None of these"). A number from 0 to 1 |
| `RECONCILE_SUGGEST_ABOVE` | 0.6 | The least score of the best candidate for a suggestion to be made ("What to suggest", 🚧). A number from 0 to 1 |
| `RECONCILE_SUGGEST_MOST` | 3 | The most alternatives of a suggestion (🚧). A whole number from 1 to 10 (no more than the dialog's five are ever offered) |
| `RECONCILE_SUGGEST_WITHIN` | 0.7 | An alternative of a suggestion scores at least this share of the best one's score (🚧). A number from 0 to 1 |
| `RECONCILE_SUGGEST_ON_SAVE` | False | Whether a save of a document that may hold a stand-in leaves it for the worker when the write does not say (`suggest=true\|false` says it either way; "The worker that suggests", 🚧). True or False |
| `RECONCILE_SUGGEST_AS` | `"IdentificationByToolchainFromText"` | The class the worker writes in a stand-in's place (🚧). A name, always; a model with `text`, `uris`, `identified_by`, `toolchain_version` and `target`, checked at `initialise()` only when `RECONCILE_SUGGEST_ON_SAVE` is True, and by the worker when it has something to write (a project without `pangloss-library` and with the setting off is not refused) |
| `RECONCILE_TOOLCHAIN` | `"pangloss-reconcile"` | The user the worker writes as, of kind `toolchain` (made when it is not there; the worker refuses, and stops, if it is a person or disabled) (🚧). A username |
| `RECONCILE_WORKER_IN_SERVER` | True | Whether the server runs the worker as a background task; False to run it apart, `pangloss reconcile worker` (🚧). True or False |

## How the candidates are found and scored ✅

`candidates_of(plan, *, see_unpublished, limit=10, only=None) -> list[Found]` (`candidates.py`, no FastAPI in it).
`Found(unknown, candidates, status, best)`, `Candidate(id, type, score, scores, shared)`. For the unknowns of the plan, in its
order (`only`: those of these ids), with what each part says the unknown would be (`unknown_vectors`). Every part is
asked of all the plan's unknowns, so that each is laid out among the others as in the whole document; but a plan
with more unknowns than `RECONCILE_MOST_UNKNOWNS` has the parts asked of those of `only` alone (the stored route
answers for one stand-in of a document with many at the cost of one). More asked about than the cap is refused
(`TooManyUnknowns`) before any part is asked.

1. **Found**: for each part that gave the unknown a vector and that the profile weighs, the `RECONCILE_FETCH`
   nearest by that part alone: `nearest(vector={part: vector}, profile=..., types=classes_of(unknown.type),
   asked=[unknown.type], exact=True, see_unpublished=...)`. Exact, because the vector index of Memgraph does not
   find items whose vectors repeat, and namesakes share a name vector. The union of their ids. A hit's score from
   these searches is not used: with one part in the query it lifts hits that lack the other parts.
2. **Counted** (step 11.2): what every item found, of every unknown asked about, shares with the document (the
   reasons, below), in one query for the request, before any cut and uncut. Each `Candidate.shared` is every pair
   `(entity id, documents)`, most documents first, then by id. Not asked only when the weight of `shared` is 0 and
   `RECONCILE_REASONS` is 0, or nothing was found.
3. **Scored** (`score.py`, no database in it): the vectors in use of those items, part by part (`store.read_part`,
   one read for each part for every unknown), the cosine of each with the unknown's vector of that part, 0 where the
   candidate has none; `scores` has each part the unknown has a vector of and whose weight is above 0, and, while
   the weight of `shared` is above 0, `shared = lead × n / (n + 2)` of the n entities the candidate shares, `lead`
   being the candidate's cosine of the part the weights weigh most among those scored for the unknown (of several
   alike, the first by name; with `who`, the name; none scored, 0). What is shared tells namesakes apart; it does
   not make someone of another name a candidate. It is 0 for one that shares nothing, and for every candidate of a
   document that names no entity, so that it is always below the line and a score means the same from one document
   to the next. `score = Σ w·scores[key] / Σ w` over them, `w` from `RECONCILE_WEIGHTS` or else the profile (and
   1.5 for `shared`). `scores.shared` in the answer is that product; the count is what the list `shared` shows. A part a candidate lacks still
   counts below the line; one whose stored vector is of another length than the unknown's counts 0 (as if it had
   none, never an error); a part whose vector of the unknown is all zeros has said nothing (not scored, not below the
   line). `shared` is not a part: it has no vector, and is a count asked of the database for the candidates found.
   By score, then id; those under `RECONCILE_LEAST_SCORE` left out; the first `limit` (`Found.candidates`). Of the
   same order, before either cut, the first ten (`KEPT`) are `Found.best` (step 11.4): what the stored route keeps of
   what it offered. One function makes both (`candidates.ranked`, no database in it), so the candidates are always a
   head of that order.
4. An unknown no part says anything of has no candidates. A profile never built: each `Found` has `status`
   `"pending"` and no candidates (`"rebuild_due"` likewise, from the search).

What the reader may see is the search's (`see_unpublished`) and the reference views' (`fragments.listed`): an entity
merged into another is no candidate, its survivor is. A candidate is always an entity of the class the unknown names,
and an entity is never unpublished, so there is no unpublished candidate to leave out.

## Reasons ✅

For each candidate found, `shared` (`reasons.py`): the entities the payload names that are also named in a
stored document together with the candidate. The entities of the payload are every reference of its plan and every
entity written in it that exists, resolved as the write would resolve them
(`pangloss_cypher.validate_write.resolved_plan`, which the graph part reads too: a URL is the node it names, an entity
merged into another is its survivor). A document shares one with a candidate when, below or in its head, one node has
a forward relation to the candidate and one a forward relation to the entity. Cut to what the reader may see: the
head a document the reader may look through (`fragments.listed`), not one whose references do not count
(`fragments.counted`: a derived document), not the plan's own head (the stored route's document is not its own
reason); the entity looked through too; forward edges of fields only (`fragments.forward`, `fragments.reference`).
A merge moves the absorbed entity's references onto its survivor, so the survivor is shared in the documents of both.

**A guess no person has confirmed is no evidence** ✅ (step 10.5c; the user's answer to row 16 of the 10.5
challenger). A forward edge to a candidate, or to an entity of the payload, does not count when the node it starts
from is of a class `hooks.unconfirmed` names (with `pangloss-library`, every class of suggestion:
`IdentificationByToolchain` and below, an outside toolchain's too), or is below one through the wrappers that hold it
(a `WeightedAlternative` in the suggestion, the suggestion in an `InRole`). In the query (`reasons.unconfirmed`), for
each of the two edges, from a node below a head only (a head document or an entity is below nothing, and the edges
into an entity come from every document that names it): `AND (n1.head_node_id IS NULL OR NOT EXISTS { MATCH
(n1)<walk>(n1_held) WHERE any(label IN labels(n1_held) WHERE label IN [...]) })`, the walk up the forward edges into
the node through wrappers, none too (`Dialect.through_wrappers(..., backwards=True)`: Memgraph's lambda, Neo4j's
quantified path).

The same of the plan asked about (`reasons.guessed`): what its own suggestions name is not among its entities. With
no class named the query is the text it was (no cost to a project without the library). A document below a
suggestion is not climbed through (its own edges count, as the graph part joins them). Once a person confirms the
suggestion (an `Identification` of the same id) it counts. Nothing else changes what "uses" an entity. The graph part
leaves the same out ([fastrp.md](fastrp.md), "The joined graph"), so a stored suggestion changes no candidate's score
for a later mention. **Not measured at size** (the shapes considered: `notes/similarity-evaluation/briefs/10.5c-report.md`).

One query for every candidate found of a request (about 95 at size, at the median), before the cut to `limit`, in a
read transaction of its own with the plan's references resolved, every shared entity with its count. Their number is
in the score (above). The answer shows at most `RECONCILE_REASONS` a candidate, those of the most documents first,
then by id, each as a reference view with `documents`, how many; `[]` when none; nothing is asked again for them.

## The routes ✅

Both need a login (`get_current_user`, as the vectors' status route): reconciling is the work of people logged in,
and neither is cheap. A reader who is not logged in gets a 401 and nothing is computed. The rule that a stand-in of a
document the reader may not see is not answered for is kept below the routes too (`stored_plan` gives None), should a
route be opened later.

`POST /api/reconcile/candidates?limit=10`: the body a `Create` payload whose `type` is a class with
a create route (another is a 422 that names it). It is a create that stops before it writes: the body is validated
as that create route validates it (the same 422), refused as it refuses (401 not logged in, 403 a read-only field or
creators named by someone not an admin), checked by `checked_create` with the creators the route names
(`?created_by=`, `?toolchain=`, `?toolchain_version=`, `?toolchain_date=`, an admin's) and the request's user, and
review's `?review_status=` read by its middleware as for a create. A refusal of `checked_create` is answered by the
API's own handlers, as the create's is.

`GET /api/reconcile/candidates/{id}?limit=10`: `id` is a stored stand-in, a node below a head. Since step 11.4 it
writes one thing, after its answer is made: what it offered the user (below, "Decisions kept"). Since step 11.6 it reads
the fit in use and says what it finds of the list ("None of these"): its answer has `model`, and an unknown may have
`new` and `probablyNew`; the payload route's has neither. Its head is read as
the reader, as `GET /api/NAME/{head}` reads it, made an `Update` as review's `rewrite_part` makes one
(`editable(view.model_dump())`), and planned as an update of it would be, nothing written (`stored.py`): of what
`update_head_node` does before its transaction, `citations.resolve`, `to_db_model` and `fill_labels`; of what it
does inside it, `plan_update` alone (without the meta of the old nodes, which no part reads). The `@before_update`s
and the checks of the transaction are not run: the document is stored, and nothing is changed. The plan keeps the
stored ids. A head that is an entity is read as it is edited (`get_for_edit`). 404 if the node is not there, is no
unknown of that plan, or the reader may not see its head. A stored document is not refused: one that cannot be
planned so (the `Update` does not take its view, a validator or label template refuses the database model, a
reference cannot be resolved) is a 404 too, "The document of the stand-in {id} cannot be planned as it is stored",
and the reason is logged as a warning (`pangloss.reconcile`).

Both answer, camelCase:

```json
{"status": "ok", "profile": "who", "unknowns": [
    {"id": "…", "type": "Person", "label": "Jon Smyth",
     "candidates": [{"id": "…", "type": "Person", "label": "Jon Smyth", "mergedInto": null,
                     "score": 0.74, "scores": {"graph": 0.57, "name": 1.0, "shared": 0.6},
                     "shared": [{"id": "…", "type": "Person", "label": "Ada", "mergedInto": null,
                                 "documents": 2}]}]}]}
```

The stored route's answer has `model` too, at the top (`null`, or `{"id", "at", "decisions", "used"}` of the fit in
use), and an unknown of it, when the fit is used and its list is not empty, `"new": 0.82, "probablyNew": true` ("None of
these", below).

The candidates are the reference views the similar route gives (`pangloss_vectors.views.reference_views`), as the
reader may see them, none scoring under `RECONCILE_LEAST_SCORE`, each with `score`, `scores` and `shared`. `status`: `"ok"`; `"pending"` if the profile has not been built
(every list empty) or an unknown's search said so; `"rebuild_due"` if a search said so, or the profile's status says
a rebuild is due (the candidates are then of the vectors in use).

## Decisions kept ✅

Once a mention is reconciled, the person chosen is named by its document, and their graph vector and what they are
named with hold the answer: the features of a decision cannot be worked out afterwards. So what was offered is kept
when it is offered, and joined to what was chosen when the choice reaches the database (`decisions.py`; the build
plan's step 11.4, faults 1, 2, 6, 10, 11, 13, 16 and 18 of its challenger). Two kinds of plain node, not models: in
no list, search, RDF or vectors.

**What was offered**, `PGReconcileShown`, one for each stand-in and user:

| Property | |
|---|---|
| `stand_in` | The stand-in's id |
| `user` | The username of the reader it was shown to (the key only) |
| `at` | When (a datetime, UTC) |
| `rows` | JSON: `Found.best`, the ten best of the items found by the hand-set score (as many as the `limit` asked, if that is more than ten: a candidate displayed is always among the rows kept), before the cut by the least score and `limit`, whatever was asked (and whoever ranks the list later: a model in use must not choose its own examples). Each `{id, type, scores, shared, score, displayed}`: `scores` each part's cosine and `shared`'s score while its weight is above 0, `shared` the count of the document's entities it is named with (a whole number), `score` the hand-set score, `displayed` whether it was in the answer given (among `candidates`, and left in by the reference views). By score, then id |
| `profile` | The profile's name |
| `signature` | The profile's signature, of the vectors in use (`store.states()`) |
| `parts` | JSON: each part the weights weigh above 0 (but `shared`) that has been built, with its stored signature |
| `weights` | JSON: the weights in use (`settings.weights()`, `shared` among them) |
| `features` | `decisions.FEATURES` (1): the version of what a row holds and how its numbers are made, raised when that changes |
| `least` | `RECONCILE_LEAST_SCORE` (a number): which rows are `displayed`, and so the head of a list a "none of these" model reads, depends on it |

The last six are what makes the numbers of the rows comparable (`decisions.SIGNATURES`), and one function says what
they are today, `decisions.today(states)`: the stored route writes it, and the retraining (and step 11.6) take an
example or a fit to be of today when its six are those values and the profile has been built (`decisions.of_today`).
A known limit: the `limit` a request asks for also changes what is displayed, and is not among them (the dialog
always asks for five).

Written by the stored route after its answer is made, only when the answer's `status` is `"ok"` (not `pending`, not
`rebuild_due`), in one write transaction: a `MERGE` by stand-in and user, so a second request of that user for that
stand-in replaces the first's (new `at`, new rows). Two requests at once leave one: the unique key, and a write that
meets it (Memgraph refuses the commit, Neo4j's `ConstraintError`) is tried again and finds the other's. A failure to
write is logged (`logger.exception`, `pangloss.reconcile`) and the answer still given; while the database is being
migrated nothing is written and nothing is logged. The payload route writes nothing.

**What was chosen**, `PGReconcileExample`, one for each stand-in: `stand_in`, `at` (when it was decided), `rows`,
`profile`, `signature`, `parts`, `weights`, `features`, `least` as they were shown, and `taken`, the id of the row that is the
entity put in the stand-in's place, among all the rows kept (displayed or not), or null when it is none of them
(someone else, or an entity just made). **Who decided is not kept**, and there is no label anywhere: ids and numbers.
Made by `decisions.heard`, a listener of `hooks.resolved` (appended when the app is imported; it does nothing unless
the app is installed and `RECONCILE_KEEP_DECISIONS` is true), in one write transaction that reads the shown records
of the stand-in (of every user), writes the example when the resolution is `direct`, by the user of one of them, and
within `RECONCILE_SHOWN_FOR` minutes of it and not before it (a `MERGE` by stand-in: a later decision replaces an
earlier one), otherwise removes an earlier example of the stand-in (resolved before and there again, it was put
back, by a restore say: that decision was undone and is not learnt from), and in every case removes every shown
record of the stand-in (it is gone from its document). The driver may run the
transaction again: it does only what can be done twice. "None of those offered" is `taken` null or a row not
displayed: worked out by 11.5, not stored.

**What is no example, and why**: a stand-in never shown (a mention reconciled by a URI it names: no list was asked);
shown to one person and reconciled by another (not what the decider saw); the `also` mentions reconciled with it in
the background (`direct` false: nobody looked at their list); shown longer ago than `RECONCILE_SHOWN_FOR` (the list
may not be what was seen when deciding); a list dated after the decision (the request was still on its way when the
person decided: they did not see it); a reconciliation in a form (`in_form`: review writes nothing then, and raises
no event, so the decision may never reach the database; the shown record stays until the sweep); a resolution that
raises no event (a form's edit, a restore, the SDK, a toolchain).

**The sweep**: `decisions.sweep() -> int`, `pangloss reconcile sweep`: removes the shown records older than
`RECONCILE_SHOWN_FOR` and those whose stand-in is no longer a node of a document (gone with a rewrite of its
document), in pages of 1,000. Nothing else removes a record never decided; the retraining runs it first
(`decisions.sweepable()`, the same query counting, in a dry run). The sweep also removes, not counted, the
**examples** whose stand-in is a node of a document again: the decision was undone by something that raises no
event (a restore from history, an edit), and is not learnt from.

**The migration**: `migrations/0001_initial.py` makes what `structure.py` says: unique `PGReconcileShown(stand_in,
user)` (a composite key, made by both backends) and an index of `PGReconcileShown(stand_in)`; unique
`PGReconcileExample(stand_in)` and an index of it (Memgraph's unique constraints make no index; on Neo4j the
constraint's serves). Reading every example is a scan of the label. A project needs `pangloss migrate`.

**The cost** (measured 2026-11-23 on Memgraph, the live tests' small world): a GET of a stored stand-in runs 15
transactions and 49 statements with nothing kept, and one write transaction of two statements more with what was
offered kept (the migration lock every write looks for, and the `MERGE`), held by a test. The listener is one write
transaction for each resolution.

Tests: `tests/live/test_reconcile_decisions_live.py` (each path above by name, both backends),
`tests/live/test_reconcile_sweep_command_live.py`, `tests/test_reconcile_best.py`, `tests/test_reconcile_structure.py`.

## Learning from decisions ✅

The build plan's step 11.5 (faults 8 to 12 of its challenger). The examples are `learning.py`'s (no database in it),
the maths [`pangloss-learn`](learn.md)'s, the reading and writing `fits.py`'s. What uses a fit is the stored route's "none of
these" (below, step 11.6), and only its "none of these" model: the ranking model is fitted, compared and recorded, and
used by nothing.

**Two models, from the same decisions**, both by `pangloss_learn.fit` (ridge 1.0):

| | An example | Its features | `yes` | Compared with |
|---|---|---|---|---|
| The **ranking** model | Each row kept in a decision (the ten, displayed or not), `group` the stand-in | `learning.ranking_features(weights)`: each part weighed above 0, by name, then `shared` (its score as kept) while its weight is above 0: `graph, name, shared` | The row taken | The hand-set score (`score.score(features, weights)`), by `compare` |
| The **"none of these"** model | Each decision with a row displayed | `learning.head_features(rows)`, over the rows **displayed**, ranked by the hand-set score: `best` (the best one's score), `gap` (to the next one's; with one row, `best` itself), the best one's features as `best_graph`, `best_name`, `best_shared`, and `rows` (`log(1 + n)` of how many were displayed) | None of those displayed was taken (`taken` null, or a row kept and not displayed) | Always answering the commoner of the two, by `compare_calls` |

Both comparisons are over five folds dealt by the seed 0. `head_features` takes rows as plain data (`score`,
`scores`, `displayed`): step 11.6 calls it on a live answer. A decision with no row displayed has no "none of these"
example (no figure of an empty list): it is counted.

**Which examples**: those of today (`decisions.of_today`: the profile, its signature and its parts', the weights,
`FEATURES`, the least score); the others are left out and counted ("of other vectors or weights"). Then those in which a row lacks a
feature (the unknown had no vector of a part: fault 11) are left out and counted.

**The fit**, `PGReconcileModel`, a plain node, one for each fit written, **none ever deleted**:

| Property | |
|---|---|
| `id` | A UUID |
| `at` | When it was fitted (a datetime, UTC) |
| `profile`, `signature`, `parts`, `weights`, `features`, `least` | Today's, as an example holds them |
| `decisions` | How many decisions went into it (the ranking model's; the "none of these" model's are its `examples`) |
| `latest` | The newest of their `at` |
| `ranking`, `none` | Each `Model.to_json()`, or null when it could not be fitted |
| `ranking_why`, `none_why` | Why that model could not be fitted (the `Unfittable`'s message), or, fitted, why its comparison could not be made; null otherwise |
| `compared` | JSON: `{"ranking": {decisions, model, baseline} \| null, "none": … \| null}` (null: not fitted, or the comparison could not be made) |
| `in_use` | **At most one fit is in use**: set and unset in one write transaction |

**The check** (the build plan's call e), `fits.why_not`: a fit is put in use only when (1) its "none of these" model
is of `RECONCILE_LEARN_FROM` decisions or more (the decisions it was fitted on, those with a row displayed: it is the
model the check guards; in `use`, the stored model's `examples`, 0 when it is null), and (2) that model was fitted,
compared, and no worse than always answering the commoner. The ranking model's comparison is **recorded and used by nothing** (the ranking stays
hand-set: "None of these", below): a ranking model that is worse, or could not be fitted, does not
keep a fit out of use; its line ends "(recorded: nothing uses the ranking model)". A fit that fails the check is
written, not in use, and the fit in use before **stays in use**; what failed is said.

Two known limits, not mended. Two runs at the same instant (the command beside the admin job) can each write a fit in
use: there is no lock; `fits.in_use()` gives the newest, and the next fit put in use, or any `--use`, leaves one.
And `in_use` on the node does not mean usable today: after the weights, the vectors or the least score change, the
fit in use is of other signatures, and the service does not use it until a new fit (the stored route checks
`of_today` on the fit, and says `used: false`: "None of these").

**`pangloss reconcile learn`** (`fits.learn(dry_run=False) -> Learnt`; the command prints `Learnt.lines()`):

1. `decisions.sweep()`;
2. the examples read; those not of today, and those lacking a part, left out and counted;
3. no decision: nothing fitted or written. The newest fit of today of as many decisions and the same `latest`:
   "Nothing new since the fit of DATE (ID): nothing written", and, when that fit is not in use, "; it is not in use
   (`pangloss reconcile learn --use ID` puts it in use, through the check)";
4. both fitted and compared, the fit written, put in use or not.

What it prints, line by line (here of 50 made-up decisions, the live tests' generator, with one more line for each
reason an example was left out when there is one):

```
0 records of what was offered removed
50 examples read
50 decisions to learn from
2 decisions with no suggestion displayed: left out of the "none of these" model
The ranking model: fitted on 500 rows; the one taken was first in 26 of 36 by the model, 26 by the score set by hand (recorded: nothing uses the ranking model)
The "none of these" model: fitted on 48 decisions; called rightly in 48 of 48 by the model, 26 by always answering the commoner
Written: the fit 6f1c…, not in use: its "none of these" model is of 48 decisions, fewer than RECONCILE_LEARN_FROM (100)
No fit is in use
```

`--dry-run`: all of it but nothing written; the shown records that would be swept are counted, not removed
(`decisions.sweepable`). `--use ID`: nothing fitted; the earlier fit is put in use through the same check (its
stored "none of these" model and comparison) and only if its signatures are today's; refused otherwise, with why (exit code
1), and nothing changes. `--use none`: no fit in use. In Python: `fits.use(id | None)`, `fits.Refused`.

**The admin job** (`admin.py`, found by `pangloss-admin`, which this package does not depend on):
`reconcile_learn`, with the choice `dry_run` (`no`, `yes`). Its counts (`Learnt.counts()`: `swept`, `read`, `other`,
`lacking`, `decisions`, `undisplayed`) are the job's; the printed lines are its report, `learnt.txt`.

**The migration**: `migrations/0002_models.py`, unique `PGReconcileModel(id)` and an index of it. A project needs
`pangloss migrate`. Finding the fit in use (`fits.in_use()`: the newest of those marked, one node read), or the
newest, is a scan of the label: a few nodes, one for each run of the command that had something new. No index of
`in_use` is made (step 11.6 reads it on every request of the stored route; a scan of so few is what an index would
save).

Tests: `tests/test_reconcile_learning.py` (pure: the examples, the head, the rows lacking a part),
`tests/live/test_reconcile_learn_live.py` (both backends: none, too few, a fit in use, nothing new, a second fit, a
worse one kept out of use, what is left out and counted, `use`, a dry run, a model that cannot be fitted, the admin
job), `tests/live/test_reconcile_learn_command_live.py` (the command's lines, `--use`).

## "None of these" ✅

The build plan's step 11.6 (faults 10, 11, 12 and 17 of its challenger). The stored route reads the fit in use
(`fits.in_use()`) and, through `api.none_of_these` (no database in it), adds to its answer:

- **`model`**, at the top: `null` when no fit is in use; otherwise `{"id", "at", "decisions", "used"}` of the fit in
  use (`at` ISO 8601, UTC; `decisions` how many it was fitted on). `used` is `fits.usable(fit, decisions.today(states))`
  with the states the answer was made with: false when the fit is **not of today** (its profile, signature, parts'
  signatures, weights, `FEATURES` or least score differ from what this request's rows are made with:
  `decisions.of_today`) or it has **no "none of these" model**. `in_use` on the node alone does not mean usable.
- On each unknown, when `model.used`, its candidates **as answered** are not empty, and every feature the model weighs
  can be made of them: **`new`**, the likelihood from 0 to 1 that the one meant is **none of those offered**
  (`learning.none_likelihood`: `Model.score` of `learning.head_features` of the rows answered, the function the fit was
  made with), and **`probablyNew`**, whether `new` is above `RECONCILE_NEW_ABOVE` (0.5). The rows are exactly the
  candidates the answer gives, after the least score, `limit` and the reader's views, in the answer's order: what the
  person sees is what the figure is about (so `limit=1` and `limit=5` give different figures).
- **Absent, both keys** (not null, not 0): no fit in use, or one not used; an empty list (there is no figure of none);
  a row lacking a part the model weighs as `best_PART` (the unknown had no vector of it: fault 11), or a feature the
  model weighs that the head does not make.

"None of these" means none of those offered (fault 12): the one meant may be in the database and not among them.

**The ranking is not by a model.** The candidates and their order are the hand-set score's, whatever fit is in use;
no `likelihood` is on a candidate. The trial (the build plan, "What was found before the steps", point 3) found a
fitted ranking no better at size and much worse on few decisions or on the five the dialog shows; 11.5's small planted
world said the same (noise). The ranking model 11.5 fits is recorded and used by nothing.

**The payload route's answer is unchanged** (no `model`, no `new`): its features differ a little from the stored
route's (fault 17), and a model fitted on lists the stored route offered would be read off other numbers.

**Nothing is written by it.** What 11.4 keeps (`PGReconcileShown`) is unchanged and holds no figure. **The cost**: one
read transaction of one statement more on every request of the stored route (`MATCH (m:PGReconcileModel) WHERE
m.in_use = true ... LIMIT 1`; the route's other transactions are those of other packages): 16 transactions and 50
statements with nothing kept, 17 and 52 with what was offered kept (15 and 49, 16 and 51, before), the same with a fit
in use as with none.

Tests: `tests/test_reconcile_none_of_these.py` (pure: `usable` of each signature, `none_of_these`),
`tests/test_reconcile_learning.py` (`none_likelihood`: no rows, a row lacking a part), `tests/test_reconcile_settings.py`
(the setting), `tests/live/test_reconcile_new_live.py` (both backends: no fit; a fit of today, the figure to 1e-9 and
`probablyNew` each side of the setting; a fit of another signature, parts, weights, features or least score, and one
with no "none of these" model, said and not used; two marked, the newest; an empty list; `limit`; the payload route;
the candidates the same with and without a fit; nothing written but 11.4's record; the budget).

## What to suggest 🚧

The decision of the worker that suggests (10.5d, below), built and tested alone (`suggest.py`, no database in it): from the
candidates of an unknown **as the dialog is answered** (the first `candidates.DISPLAYED`, five: what the interface
asks for, `LIMIT` of its `api.ts`, held equal by a test; so the list "none of these" was fitted on), `decide`
suggests **nothing** when there is no candidate (`none`), when the best scores under `RECONCILE_SUGGEST_ABOVE`
(`low`), or when the fit in use says the one meant is probably none of them (`new`: `learning.probably_new` above
`RECONCILE_NEW_ABOVE`, the one function the stored route's `probablyNew` is made by); otherwise the best
`RECONCILE_SUGGEST_MOST` that score at least `RECONCILE_SUGGEST_WITHIN` of the best's (the best always kept), each
with whole percentages of at least 1 that sum to 100, in proportion to the scores, the largest remainders taking what
rounding leaves (the earlier of equal ones; at most 100 alternatives). `decide_for(found, fit)` gives `decide` its
arguments from the settings and the "none of these" model of the fit in use (or None).

The defaults are main's call from the measurement at size (the build plan, "10.5c measured"; not yet confirmed by
the user): at 0.6 a third of the mentions of known people get a suggestion, which holds the person 98 times in 100,
and about one mention in six of someone new gets one. The seeded floor (`tests/test_reconcile_suggest_planted.py`,
the planted world in memory): of suggestions made, 99 to 100% hold the person; 16 to 21% of the mentions whose
person was taken out get one. Tests: `tests/test_reconcile_suggest.py`.

## The worker that suggests 🚧

Pangloss's own toolchain (step 10.5d; 🚧 until 10.5e, what sets it off over the API and the admin page, 10.5f, learning
from a person's confirmation, and 10.5g, the measurements): a document saved with a stand-in in it is left for a
worker in the background, which writes, in the stand-in's place, a suggestion of who it is for a person to confirm
(`RECONCILE_SUGGEST_AS`, the library's `IdentificationByToolchainFromText`), as review lists any toolchain's.
`marking.py` (what leaves a document for it) and `suggesting.py` (the worker); the decision is `suggest.py`'s. It
still imports neither review nor the library: it finds stand-ins by `unknowns_of` and writes the class a setting
names (and the library's `WeightedAlternative`, by its name, for alternatives).

**What leaves a document for it.** A mark of the kind `reconcile` (`pangloss_cypher.pending`), in the write's own
transaction, only on a create or an update of a head of a class **that people write and that can hold a stand-in**
(worked out once after `initialise()`: it has an `Update`, is not abstract, `hooks.written_by_people` says people
write it, so not a derived document, and some relation field of it, at any depth through nested documents, reified
relations, conjunctions and semantic spaces, takes a document of `hooks.stand_ins` that names what it stands for).
The write's instruction `suggest` (`save(instructions={"suggest": True})`, `?suggest=true` on the API's create and
update routes; `hooks.declare_write_instruction`) says it either way, for that write only:

| The write says | `RECONCILE_SUGGEST_ON_SAVE` | The mark |
|---|---|---|
| `suggest=true` | either | made |
| `suggest=false` | either | **taken off**, if one stands (a pipeline that identifies for itself) |
| nothing | True | made |
| nothing | False | as it was: one a trigger left stays |

With the setting off and nothing said a write costs what it did without the app (a test, `test_reconcile_worker_live.py`);
a marked write runs one statement more (the mark's `MERGE`).

**What it does with a marked head**, cheapest first. Each head is read once (`rewriting.read_head`), planned once
(`stored.plan_of_view`), and as the toolchain sees it (everything unpublished):

| | Left alone, and why | Its mark |
|---|---|---|
| 1 | The head is gone or deleted | completed, logged at info |
| 1 | It is **published** (the user: only unpublished documents) | completed, logged |
| 1 | Its class is not one people write (a derived document), or holds no stand-in | completed, logged |
| 1 | Its stored form cannot be planned (`stored.Unplannable`) | completed, logged |
| 2 | A stand-in **tried with today's digest** (`PGReconcileTried`: today's signatures, `decisions.today`; the settings of the decision, `RECONCILE_SUGGEST_*`, `RECONCILE_NEW_ABOVE`, the fit in use when used, `DISPLAYED`; and the stand-in's own label, class and URIs): skipped | as the rest decides |
| 3 | A stand-in whose place takes no suggestion, found **by trial** (the head's `Update` validated with it replaced by a suggestion of a placeholder: one `WeightedAlternative` at 100 per cent, then one entity; nothing written, nothing looked up): left, noted as tried | as the rest decides |
| 4 | **A part it would change is cited** (by any document not deleted, published or not: a citation of the stand-in, of a node above it, of the head, or of any part of a head whose `cited_with` names the field it is in), asked by a read before any candidate: **the head is left whole** | completed, logged |
| 5 | A stand-in whose candidates are not `ok` (the profile not built, a rebuild due): left, not noted as tried | as the rest decides |
| 5 | A stand-in decided against (`suggest.decide_for`: no candidate, the best under `RECONCILE_SUGGEST_ABOVE`, or "probably new"): left, noted as tried | as the rest decides |

The candidates are asked **as the stored route asks them** (`candidates_of(plan, see_unpublished=True,
limit=candidates.DISPLAYED, only=...)`), in groups of at most `RECONCILE_MOST_UNKNOWNS` (a document with 30
mentions is asked in two groups, not refused), with the fit in use read once for the batch. Between the decision and
the write, `judged` returns it unchanged: the place of a project's judge (10.5c').

**The update**, if anything was decided: **one** for the document (`rewriting.rewrite`), based on the version read,
written **as the toolchain** (`RECONCILE_TOOLCHAIN`, the user of the write; history records the version as its), with
`instructions={"suggest": False}`, which **takes the head's mark off in the update's own transaction** and leaves no
new one (the vectors' and criteria's marks are left as by any update: the worker's update is one). Each stand-in
decided becomes a suggestion with **a new id**: `text` the stand-in's label, `uris` its URIs, `identified_by` the
toolchain, `toolchain_version` what was used (`"profile who"`, `"profile who, fit <id>"` when a fit in use was used),
the target in the shape the trial found (alternatives in the order decided with their per cent, or the best alone),
the relation's own properties kept (as review's reconciliation keeps them). A stand-in not decided stays as it was,
with its id.

| The update | What happens |
|---|---|
| Written | the mark gone with it; what it saw kept (below) |
| `PanglossVersionConflictError` (a person saved meanwhile) | nothing written; the claim given back, the mark kept: done again at the next turn if it is still marked (a save that said `suggest=false` took it off) |
| Any other refusal (the whole update not valid, a citation, a `@before_update`, a reference gone) | logged with the head; the mark completed; the stand-ins asked noted as tried |
| A failure that is not a refusal (the database, a migration under way, the toolchain gone or disabled meanwhile, a bug) | the claims given back, the marks kept, the error raised (the worker backs off) |
| Nothing decided | the mark completed by its token; the stand-ins noted as tried |

**What it keeps** (`structure.py`, `migrations/0003_suggested.py`), in the update's own transaction (`hooks.in_write`,
only while the worker writes that head): one `PGReconcileSuggested` for each suggestion, by its id (the head, the
stand-in, when, the rows of `Found.best` as the stored route's record keeps them with `displayed` the list decided
on, the alternatives written and their shape, today's signatures; no user), for learning from a person's
confirmation (10.5f); one `PGReconcileTried` for each stand-in left (its id, its head, the digest). The sweep
(`pangloss reconcile sweep`) removes the first only when the suggestion is no longer a node of a class of suggestion
(confirmed, or gone), never by age, and the second when its stand-in is gone; `suggesting.forget_tried(heads)` forgets
those tried (for 10.5e's `--again`).

**When it waits.** Nothing is claimed while a rebuild of the vectors holds its lease; and only marks made before the
oldest mark of the vectors' kind are claimed, the oldest first (the writes that left its work have reached the
vectors; its own updates' vector marks are newer, and are not waited for). With `pangloss_vectors` installed and its
worker not running, nothing is claimed, and `pending_status()` says so (`waiting_for_vectors`).

**One worker at a time** (a lease on the `PGReconcileWorker` node), few heads claimed at once (5), the lease and the
claims renewed every quarter of 30 s while it works (a mention asked takes 1 to 2.5 s at size). In the server
(`RECONCILE_WORKER_IN_SERVER`, a background task woken by the writes of the classes it marks) or apart: `pangloss
reconcile worker [--batch N] [--once]` (`--once`: what can be done now, and stop). Before it writes it checks the class
it writes and the toolchain (`ready`): made if absent, kind `toolchain`; **a person or a disabled user is refused, and
the worker stops**, saying why. `drain()` for tests and scripts; `pending_status()` (marked, claimed, waiting for the
vectors, a rebuild in hand, who holds the lease).

**The head's label.** A head whose label template names the field a mention was in keeps the name the source wrote:
the library's `IdentificationByToolchainFromText` has the template `{text}`, which is how a reified relation reads in
the label of what holds it ("Ada gave to Jon Smith", not the candidates' labels). Confirmed, it is an
`IdentificationFromText`, which reads as who was identified.

**Not built with it** (the user's word): anything against the worker changing a document a person has open. Until the
live view ([live-editing.md](live-editing.md)), such a person is refused on saving, as for any stale version.

Tests: `tests/test_reconcile_suggesting.py` (the settings, what can be marked, the shapes, the digest, what is cited);
live on both backends `tests/live/test_reconcile_worker_live.py` and `test_reconcile_worker_command_live.py`.

## The interface ✅

The app's interface module (`pangloss_reconcile/interface/`, its words in `translations/ui.jsonc`) fills review's
place `reconcileCandidates` (`slots: { reconcileCandidates: { Candidates: ... } }`, nothing else): in the reconcile
dialog of a saved mention, under "Reconcile with" and above the picker, while no entity is chosen,
`ReconcileCandidates` draws "Suggested" and the mention's candidates (`GET /api/reconcile/candidates/{id}?limit=5`),
best first. Each is a row: the entity's `ReferenceChip` (a link to its page), a slate bar and the figure of its score
(as the rows of the Similar section), and Choose, which gives the entity to the panel's `onPick` (the panel then shows
it as chosen, as the picker does). When the answer says the mention is `probablyNew` ("None of these") and there are
rows, one quiet line between "Suggested" and the rows, "Probably not in the database yet" (slate, `text-xs`, as "also
named with"; `data-testid="reconcile-probably-new"`), its `title` the likelihood as a percentage ("82% likely to be none
of these"; `candidates.probablyNewText`). Nothing is hidden or reordered by it. The score of each part, and of the entities shared under a translated name ("named
with"), is the bar's `title` and accessible text ("Score 0.73: name 1.00, named with 0.60, graph 0.39"). Under a candidate that shares something, quietly, "also named with" and the `shared` entities as
chips, each with a badge of its count of documents when above 1.

It reads by itself, a memo of the mention's id and the session (another mention, another request). Nothing at all is
drawn (no heading) while the answer comes, for `pending`, for no candidate to show, or when the request fails (the
place's boundary hides it, and the console says why); with `rebuild_due` the candidates are shown. Every candidate
the route gives is shown: the server leaves out those under `RECONCILE_LEAST_SCORE` (until step 11.2 the module cut
at 0.3 itself; the graph part alone finds the people of the mention's own document, in the e2e test the third
witness, name 0, under the least score). The props are declared in the module
(`{ mention: { id }, onPick }`: a module cannot import review's files). Nothing is offered for a mention not yet saved
(review's dialog says to save first), nor as a name is typed in a form.

Tests: Vitest (`candidates.test.ts`, the helpers; `ReconcileCandidates.test.tsx`, the component), run in a built
project by `e2e/test_module_unit_tests.py`; `e2e/test_reconcile_candidates.py` (the namesake who keeps the mention's
company first, chosen and reconciled; a mention like nobody shows nothing; with a fit in use, planted by
`helpers.fit_in_use`, the line and its title, the suggestion still there); the development build in
`e2e/test_dev_mode.py::test_the_tasks_of_review` (with a fit in use: the line).

## What "refused as the create is" does not cover

`checked_create` runs what a create runs before its statements (step 10.2a, "As built"). It does not refuse what a
create checks only after it has written: a citation of a part of the document itself (`citations.record`), cited
bases given in the payload (`citations.check_bases`), what the apps run in the write's transaction (`hooks.in_write`:
`pangloss-derived` refuses there a derived document made by anyone but its worker), and a uniqueness constraint broken
by another write at the same moment. A project's `@before_create` is run, as it is before a create.

## What is known of it

- **The two routes agree for the same ids only, and that is accepted** (main, 2026-11-22). The graph part starts each
  stop from a vector made from its id (`pangloss_fastrp.maths.seeds`), so a payload, whose nested nodes are given new
  ids each time it is planned, and the same document once written, whose ids were made again, give an unknown
  different graph vectors, and its candidates somewhat different graph scores (in the live test, 0.875 against 0.907
  for the first candidate, the order the same). With the same ids they are equal to 10⁻⁵: the test gives the write
  the ids of the plan (`test_the_stored_route_gives_what_the_payload_route_gives_for_the_same_document`). The
  entities shared are the same on both routes (the stored route does not count its own document), so this is still
  all that differs.
- **The cost of a POST with one unknown** (measured 2026-11-22 on Memgraph, the live test's small world): 14 read
  transactions and 59 statements, held to that by a test. Four of them are the login (the API reads the token twice
  for a request that needs a user); about 33 statements are the graph part's lay-out of the neighbourhood; the
  reasons are one transaction of two statements (the plan's references resolved, and the query). Since step 11.2
  they are asked once for every candidate found, where they were asked once for those returned: the same 14 and 59;
  only `RECONCILE_REASONS = 0` with `shared` at 0 saves them (13 and 57).
- **The quality, held to a floor** with no database (`tests/test_reconcile_planted.py`, the planted world of 1,500
  people, the vectors made in memory, seeds 1 to 3): with the name at 1 and the graph at 0.25, the person right first
  78% to 81.5%, among five 99.7% to 100%; of the names several people have, right first 57% to 65% with the graph,
  35% to 42% by the name alone. With `shared` at 1.5 too, the name's cosine × n / (n + 2) (the shared entities
  worked out in memory as the service counts them, 2026-11-23): right first 89.2% to 90.7% (8.6 to 11.7 points
  more, held to 8), among five 100%; of the names several people have, 77.9% to 81.9%. (The first form, n / (n + 2)
  at 0.75 for everyone: 85.7% to 86.6%.) Main's measurement through the service at 6,000 people:
  `notes/similarity-evaluation/planted_reconcile_memgraph_small.txt`.

## Measured at size ✅

The dated planted world of 32,137 people and 6,427 mentions (253,400 vectors in the profile `who`, the table of
variants), 200 mentions each posed again as a payload with a stand-in and not written
(`notes/similarity-evaluation/planted.py reconcile`; the output beside it, `planted_reconcile_memgraph.txt`,
`planted_reconcile_neo4j.txt`; at 5,986 people, `planted_reconcile_memgraph_small.txt`: 78.0% right first, 99.7%
among five, a request 1.3 s). These are of phase 10's score, the parts alone (2026-11-22); with the entities shared
in it (step 11.2), below:

| | Memgraph (`:7706`) | Neo4j (`:7707`) |
|---|---|---|
| Right first / among five, name alone | 58.0% / 91.5% | 58.0% / 91.5% |
| name 1, graph 0.1 | 69.5% / 94.5% | 70.0% / 94.0% |
| **name 1, graph 0.25** (the profile's) | **65.0% / 96.5%** | **66.5% / 95.0%** |
| name 1, graph 0.5 | 46.5% / 95.5% | 50.0% / 95.5% |
| name 1, graph 1 | 16.0% / 89.0% | 17.0% / 90.5% |
| graph alone | 0.0% / 23.0% | 0.0% / 21.5% |
| Of the 115 whose name several have, at the profile's weights | 52.2% / 95.7% | 53.0% / 93.9% |
| "Someone new", AUC by the best score | 0.62 | 0.62 |
| The person among those found, by either part | 99.5% | 99.5% |
| **A request, at the median (slowest)** | **2.21 s** (3.41 s) | **1.30 s** (2.72 s) |
| the graph part's `unknown` | 505 ms | 528 ms |
| each exact scan (two a request) | 679 ms | 350 to 369 ms |
| `store.read_part` (two a request) | 117 ms | 18 ms |
| the name part's `unknown` | 110 ms | 3 ms |
| The reasons of ten candidates (slowest) | 3 ms (9 ms) | 3 ms (119 ms) |
| The rebuild before it (every part, two profiles) | 565 s | 274 s |

- The quality is that of a search by the stored vectors at this size (step 8.6: 63.6% and 97.2%); it falls with
  size because there are more namesakes.
- A request reads every vector of the unknown's classes twice (once by each part), on purpose: Memgraph's vector
  index does not find vectors that repeat, and people of one name and nothing else have one name vector. That,
  and the graph part's reading of the neighbourhood (half a second on both backends), is the cost. What would
  lessen it is in `TODO.md`; none of it is built.
- The best score does not tell a mention whose person is in the database from one whose person is not (AUC 0.62):
  no likelihood of "someone new" is answered from it. Since step 11.6 a fitted model over the head of the list gives
  one ("None of these"), once enough decisions have been kept and learnt from.
- The reasons cost 3 ms here; an entity named in very many documents (which this world has not) is not measured.

### The entities shared in the score (step 11.2) ✅

**The form built**: `shared` = the name's cosine (the lead part's) × n / (n + 2), at 1.5. Measured by main through
the service on the same world (Memgraph, 200 mentions; `notes/similarity-evaluation/planted_reconcile_byname_memgraph.txt`):

| | Right first | Among five | Of names several people have, first |
|---|---|---|---|
| name 1, graph 0.25 | 66.5% | 95.5% | 53.9% |
| + shared at 0.75 (the first form, n / (n + 2) for everyone alike) | 82.0% | 99.5% | 76.5% |
| + name's cosine × n/(n+2) at 1 | 85.5% | 99.5% | 79.1% |
| **the same at 1.5** (the default) | **86.5%** | 99.5% | 82.6% |
| at 2 / 3 / 4 | 86.5% / 86.0% / 85.0% | 99.5% | 82.6% / 81.7% / 80.9% |

**What was tried first**, and built first, then changed: n / (n + 2) alone, the same for every candidate, beside
name 1 and graph 0.25 (both backends; `planted_reconcile_shared_memgraph.txt`, `planted_reconcile_shared_neo4j.txt`).
It lifted the people the document itself names, of no name like the unknown's, by what they share with each other
(to about 0.26 with a name of 0 in the live test's world):

| Weight of `shared` | Right first (Memgraph / Neo4j) | Among five | Of names several people have, first |
|---|---|---|---|
| 0 (phase 10) | 65.5% / 67.5% | 95.5% / 96.0% | 50.4% / 54.8% |
| 0.25 | 75.0% / 73.5% | 99.5% | 62.6% / 61.7% |
| 0.5 | 79.5% / 79.5% | 99.5% | 71.3% / 68.7% |
| **0.75** | **80.5% / 80.5%** | 99.5% / 99.0% | 73.9% / 73.0% |
| 1 | 78.5% / 79.0% | 99.5% / 99.0% | 72.2% / 71.3% |
| 2 | 72.0% / 73.5% | 99.5% / 99.0% | 70.4% |

A name's cosine is not always 0 between unlike names: in the live test's world Ada has 0.24 with "Jon Smyth" (the
names' hashing), and with what she shares comes up at about 0.2, over the least score. The reasons query asked for
**every** candidate found (95 at the median) takes 10 ms at the median on Memgraph
(slowest 20 ms) and 8 ms on Neo4j (slowest 166 ms): the same query, asked once a request, earlier.

### Learning from decisions (step 11.7) ✅

Through the package's own code on the planted world at size (32,137 people; `planted.py learn`,
`learn_at_size.sh`, `notes/similarity-evaluation/planted_learn_{memgraph,neo4j}.txt`; 2026-11-23): 800 mentions,
each posed again as a payload with a stand-in and asked of the service as it is set (name 1, graph 0.25, shared
1.5, least score 0.15, five displayed); of every second the person is taken out of what was found. Half are kept
as decisions made with the truth (`decisions.write_example`) and learnt from (`fits.learn`: 400 decisions, the
fit put in use); the other half is asked of the fit.

| At size, 400 lists held out | Memgraph | Neo4j |
|---|---|---|
| "None of these" called rightly by the fit (at a half) | 66.8% | 68.2% |
| by always answering the commoner | 52.0% | 52.0% |
| "None of these", AUC by the fit / by the best score alone | 0.74 / 0.65 | 0.73 / 0.65 |
| Right first by the score set by hand (the lists whose person is among the rows) | 77.6% | 79.0% |
| Right first by the fitted ranking model | 75.5% | 71.3% |

- **"None of these" is what learning buys, and it is modest**: about two lists in three called rightly where the
  commoner answer is right for half (the trial in memory said three in four; the seeded pure test at 1,500
  people, `tests/test_reconcile_learning_planted.py`, has 78 to 82%).
- **The fitted ranking is no better than the score set by hand, and worse on Neo4j's run** (in the fit's own
  comparison too: 145 against 149 of 197 on Memgraph, 142 against 147 of 198 on Neo4j). The ranking stays
  hand-set; the fit's ranking model is recorded and used by nothing.
- A caution, as before: these decisions are the truth. Real ones are fewer, chosen by whoever reviews, and
  sometimes wrong.

## Not built ⏳

- "None of these" on the payload route (fault 17), and a ranking by a fitted model (not taken: "None of these").
- Several unknowns of one payload ranked jointly (step 10.3: measured too weak,
  and not measurable on the planted world).
- **10.5** The toolchain mode: the decision, the classes and the worker are built (10.5a, 10.5c, 10.5d); what sets
  it off over the API and on the admin page (`POST /api/reconcile/suggest`, the job, `pangloss reconcile suggest |
  status`), a project's judge, learning from confirmations and the measurements are not (10.5e, 10.5c', 10.5f,
  10.5g).
- Suggestions as a name is typed in a form's field (a search by a name, which has no route yet).
- Dates in the score (an entity has no time vector).
