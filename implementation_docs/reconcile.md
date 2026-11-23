# Reconciliation (`pangloss-reconcile`) 🚧

Status (2026-11-23): phase 10 of [the build plan](similarity-build-plan.md) is built but for its toolchain mode:
the package and its settings, the candidates of an unknown found and scored by the parts of similarity, the
reasons (`shared`), the two routes, the candidates in review's reconcile dialog, a seeded floor of quality, and
the measurements at size on both backends. Step 11.2 is built: the entities shared are in the score, counted for
every candidate found, and the least score of a candidate is a setting, cut at the server. How to use it: [the guide](../guide/vectors/reconcile.md). The design
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

`requires = {"cypher", "vector_index"}`. It depends on `pangloss-vectors`, `pangloss-cypher`, `pangloss-models`,
`pangloss-core` and `pangloss-api`.

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

## How the candidates are found and scored ✅

`candidates_of(plan, *, see_unpublished, limit=10, only=None) -> list[Found]` (`candidates.py`, no FastAPI in it).
`Found(unknown, candidates, status)`, `Candidate(id, type, score, scores, shared)`. For the unknowns of the plan, in its
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
   By score, then id; those under `RECONCILE_LEAST_SCORE` left out; the first `limit`.
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

`GET /api/reconcile/candidates/{id}?limit=10`: `id` is a stored stand-in, a node below a head. Its head is read as
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

The candidates are the reference views the similar route gives (`pangloss_vectors.views.reference_views`), as the
reader may see them, none scoring under `RECONCILE_LEAST_SCORE`, each with `score`, `scores` and `shared`. `status`: `"ok"`; `"pending"` if the profile has not been built
(every list empty) or an unknown's search said so; `"rebuild_due"` if a search said so, or the profile's status says
a rebuild is due (the candidates are then of the vectors in use).

## The interface ✅

The app's interface module (`pangloss_reconcile/interface/`, its words in `translations/ui.jsonc`) fills review's
place `reconcileCandidates` (`slots: { reconcileCandidates: { Candidates: ... } }`, nothing else): in the reconcile
dialog of a saved mention, under "Reconcile with" and above the picker, while no entity is chosen,
`ReconcileCandidates` draws "Suggested" and the mention's candidates (`GET /api/reconcile/candidates/{id}?limit=5`),
best first. Each is a row: the entity's `ReferenceChip` (a link to its page), a slate bar and the figure of its score
(as the rows of the Similar section), and Choose, which gives the entity to the panel's `onPick` (the panel then shows
it as chosen, as the picker does). The score of each part, and of the entities shared under a translated name ("named
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
company first, chosen and reconciled; a mention like nobody shows nothing); the development build in
`e2e/test_dev_mode.py::test_the_tasks_of_review`.

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
  no likelihood of "someone new" is answered.
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

## Not built ⏳

- How likely "someone new" is, and several unknowns of one payload ranked jointly (step 10.3: measured too weak,
  and not measurable on the planted world).
- **10.5** The toolchain mode (an `IdentificationByToolchain` written above a threshold for a person to confirm):
  not built until the user says what sets it off.
- Suggestions as a name is typed in a form's field (a search by a name, which has no route yet).
- Dates in the score (an entity has no time vector).
