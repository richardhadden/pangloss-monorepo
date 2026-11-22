# Reconciliation (`pangloss-reconcile`) 🚧

Status (2026-11-22): step 10.2c of [the build plan](similarity-build-plan.md) is built: the package, its settings,
the candidates of an unknown found and scored by the parts of similarity, and the two routes; of step 10.3, the mends
of 10.2c's second reading, the reasons (`shared`) and a seeded floor of quality; step 10.4, the interface (the
candidates in review's reconcile dialog). Not built: the rest of 10.3, 10.5 and 10.6 (below). The design and its decisions are the build plan's phase 10, "Read again (2026-11-22)".

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
| `RECONCILE_WEIGHTS` | `{}` | The weight of each part in the score; a part not named has the profile's. Refused: a name that is no part, a weight that is not a number of 0 or more, and weights that leave none of the parts the profile weighs above 0 |
| `RECONCILE_MOST_UNKNOWNS` | 20 | The most unknowns asked about at once. A plan with more is refused before any part is asked (`TooManyUnknowns`; a 422 that says how many it has and the most). A whole number of 1 or more |
| `RECONCILE_REASONS` | 5 | The most entities a candidate is said to share with the payload (`shared`); 0 asks nothing. A whole number of 0 or more |

## How the candidates are found and scored ✅

`candidates_of(plan, *, see_unpublished, limit=10, only=None) -> list[Found]` (`candidates.py`, no FastAPI in it).
`Found(unknown, candidates, status)`, `Candidate(id, type, score, scores)`. For the unknowns of the plan, in its
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
2. **Scored** (`score.py`, no database in it): the vectors in use of those items, part by part (`store.read_part`,
   one read for each part for every unknown), the cosine of each with the unknown's vector of that part, 0 where the
   candidate has none; `scores` has each part the unknown has a vector of and whose weight is above 0, and
   `score = Σ w·scores[part] / Σ w` over them, `w` from `RECONCILE_WEIGHTS` or else the profile. A part a candidate
   lacks still counts below the line; one whose stored vector is of another length than the unknown's counts 0 (as
   if it had none, never an error); a part whose vector of the unknown is all zeros has said nothing (not scored,
   not below the line). By score, then id; the first `limit`.
3. An unknown no part says anything of has no candidates. A profile never built: each `Found` has `status`
   `"pending"` and no candidates (`"rebuild_due"` likewise, from the search).

What the reader may see is the search's (`see_unpublished`) and the reference views' (`fragments.listed`): an entity
merged into another is no candidate, its survivor is. A candidate is always an entity of the class the unknown names,
and an entity is never unpublished, so there is no unpublished candidate to leave out.

## Reasons ✅

For each candidate in an answer, `shared` (`reasons.py`): the entities the payload names that are also named in a
stored document together with the candidate. The entities of the payload are every reference of its plan and every
entity written in it that exists, resolved as the write would resolve them
(`pangloss_cypher.validate_write.resolved_plan`, which the graph part reads too: a URL is the node it names, an entity
merged into another is its survivor). A document shares one with a candidate when, below or in its head, one node has
a forward relation to the candidate and one a forward relation to the entity. Cut to what the reader may see: the
head a document the reader may look through (`fragments.listed`), not one whose references do not count
(`fragments.counted`: a derived document), not the plan's own head (the stored route's document is not its own
reason); the entity looked through too; forward edges of fields only (`fragments.forward`, `fragments.reference`).
A merge moves the absorbed entity's references onto its survivor, so the survivor is shared in the documents of both.

One query for every candidate of a request, in a read transaction of its own with the plan's references resolved:
at most `RECONCILE_REASONS` a candidate, those of the most documents first, then by id, each as a reference view with
`documents`, how many; `[]` when none. The score is not changed by them.

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
                     "score": 0.91, "scores": {"graph": 0.57, "name": 1.0},
                     "shared": [{"id": "…", "type": "Person", "label": "Ada", "mergedInto": null,
                                 "documents": 2}]}]}]}
```

The candidates are the reference views the similar route gives (`pangloss_vectors.views.reference_views`), as the
reader may see them, each with `score`, `scores` and `shared`. `status`: `"ok"`; `"pending"` if the profile has not been built
(every list empty) or an unknown's search said so; `"rebuild_due"` if a search said so, or the profile's status says
a rebuild is due (the candidates are then of the vectors in use).

## The interface ✅

The app's interface module (`pangloss_reconcile/interface/`, its words in `translations/ui.jsonc`) fills review's
place `reconcileCandidates` (`slots: { reconcileCandidates: { Candidates: ... } }`, nothing else): in the reconcile
dialog of a saved mention, under "Reconcile with" and above the picker, while no entity is chosen,
`ReconcileCandidates` draws "Suggested" and the mention's candidates (`GET /api/reconcile/candidates/{id}?limit=5`),
best first. Each is a row: the entity's `ReferenceChip` (a link to its page), a slate bar and the figure of its score
(as the rows of the Similar section), and Choose, which gives the entity to the panel's `onPick` (the panel then shows
it as chosen, as the picker does). The score of each part is the bar's `title` and accessible text ("Score 0.88: name
1.00, graph 0.39"). Under a candidate that shares something, quietly, "also named with" and the `shared` entities as
chips, each with a badge of its count of documents when above 1.

It reads by itself, a memo of the mention's id and the session (another mention, another request). Nothing at all is
drawn (no heading) while the answer comes, for `pending`, for no candidate to show, or when the request fails (the
place's boundary hides it, and the console says why); with `rebuild_due` the candidates are shown. A candidate is
shown only with a score of at least `LEAST_SCORE` (0.3, in the module's `candidates.ts`): the route gives the nearest
whatever they are, and the graph part alone finds the people of the mention's own document (in the e2e test, the
third witness at 0.077: name 0, graph 0.39; a same-name candidate 0.80 to 0.88). The props are declared in the module
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
  the ids of the plan (`test_the_stored_route_gives_what_the_payload_route_gives_for_the_same_document`).
- **The cost of a POST with one unknown** (measured 2026-11-22 on Memgraph, the live test's small world): 14 read
  transactions and 59 statements, held to that by a test. Four of them are the login (the API reads the token twice
  for a request that needs a user); about 33 statements are the graph part's lay-out of the neighbourhood; the
  reasons are one transaction of two statements (the plan's references resolved, and the query), which
  `RECONCILE_REASONS = 0` saves.
- **The quality, held to a floor** with no database (`tests/test_reconcile_planted.py`, the planted world of 1,500
  people, the vectors made in memory, seeds 1 to 3): with the name at 1 and the graph at 0.25, the person right first
  78% to 81.5%, among five 99.7% to 100%; of the names several people have, right first 57% to 65% with the graph,
  35% to 42% by the name alone. Main's measurement through the service at 6,000 people:
  `notes/similarity-evaluation/planted_reconcile_memgraph_small.txt`.

## Not built ⏳

- **10.3**, the rest: the weights measured (hand-set until then), how likely "someone new" is, several unknowns of
  one payload ranked jointly (main's).
- **10.5** The toolchain mode: not built until the user says what sets it off.
- **10.6** Measured on both backends at size; this page and the guide written out.
