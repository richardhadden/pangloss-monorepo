# Reconciliation (`pangloss-reconcile`) 🚧

Status (2026-11-22): step 10.2c of [the build plan](similarity-build-plan.md) is built: the package, its settings,
the candidates of an unknown found and scored by the parts of similarity, and the two routes. Not built: what steps
10.3 to 10.6 add (below). The design and its decisions are the build plan's phase 10, "Read again (2026-11-22)".

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
| `RECONCILE_FETCH` | 50 | How many candidates each part is asked for. A whole number of 1 or more |
| `RECONCILE_WEIGHTS` | `{}` | The weight of each part in the score; a part not named has the profile's. Refused: a name that is no part, a weight that is not a number of 0 or more |

## How the candidates are found and scored ✅

`candidates_of(plan, *, see_unpublished, limit=10, only=None) -> list[Found]` (`candidates.py`, no FastAPI in it).
`Found(unknown, candidates, status)`, `Candidate(id, type, score, scores)`. For the unknowns of the plan, in its
order (`only`: those of these ids; every part is still asked of them all, so that each is laid out among the others
as in the whole document), with what each part says the unknown would be (`unknown_vectors`):

1. **Found**: for each part that gave the unknown a vector and that the profile weighs, the `RECONCILE_FETCH`
   nearest by that part alone: `nearest(vector={part: vector}, profile=..., types=classes_of(unknown.type),
   asked=[unknown.type], exact=True, see_unpublished=...)`. Exact, because the vector index of Memgraph does not
   find items whose vectors repeat, and namesakes share a name vector. The union of their ids. A hit's score from
   these searches is not used: with one part in the query it lifts hits that lack the other parts.
2. **Scored** (`score.py`, no database in it): the vectors in use of those items, part by part (`store.read_part`,
   one read for each part for every unknown), the cosine of each with the unknown's vector of that part, 0 where the
   candidate has none; `scores` has each part the unknown has a vector of and whose weight is above 0, and
   `score = Σ w·scores[part] / Σ w` over them, `w` from `RECONCILE_WEIGHTS` or else the profile. A part a candidate
   lacks still counts below the line. By score, then id; the first `limit`.
3. An unknown no part says anything of has no candidates. A profile never built: each `Found` has `status`
   `"pending"` and no candidates (`"rebuild_due"` likewise, from the search).

What the reader may see is the search's (`see_unpublished`) and the reference views' (`fragments.listed`): an entity
merged into another is no candidate, its survivor is. A candidate is always an entity of the class the unknown names,
and an entity is never unpublished, so there is no unpublished candidate to leave out.

## The routes ✅

`POST /api/reconcile/candidates?limit=10` (login required): the body a `Create` payload whose `type` is a class with
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
stored ids. 404 if the node is not there, is no unknown of that plan, or the reader may not see its head.

Both answer, camelCase:

```json
{"status": "ok", "profile": "who", "unknowns": [
    {"id": "…", "type": "Person", "label": "Jon Smyth",
     "candidates": [{"id": "…", "type": "Person", "label": "Jon Smyth", "mergedInto": null,
                     "score": 0.91, "scores": {"graph": 0.57, "name": 1.0}}]}]}
```

The candidates are the reference views the similar route gives (`pangloss_vectors.views.reference_views`), as the
reader may see them, each with `score` and `scores`. `status`: `"ok"`; `"pending"` if the profile has not been built
(every list empty) or an unknown's search said so; `"rebuild_due"` if a search said so, or the profile's status says
a rebuild is due (the candidates are then of the vectors in use).

## What "refused as the create is" does not cover

`checked_create` runs what a create runs before its statements (step 10.2a, "As built"). It does not refuse what a
create checks only after it has written: a citation of a part of the document itself (`citations.record`), cited
bases given in the payload (`citations.check_bases`), what the apps run in the write's transaction (`hooks.in_write`:
`pangloss-derived` refuses there a derived document made by anyone but its worker), and a uniqueness constraint broken
by another write at the same moment. A project's `@before_create` is run, as it is before a create.

## What is known of it

- **The two routes agree for the same ids only.** The graph part starts each stop from a vector made from its id
  (`pangloss_fastrp.maths.seeds`), so a payload, whose nested nodes are given new ids each time it is planned, and the
  same document once written, whose ids were made again, give an unknown different graph vectors, and its candidates
  somewhat different graph scores (in the live test, 0.875 against 0.907 for the first candidate, the order the
  same). With the same ids they are equal to 10⁻⁵ (`test_the_stored_route_gives_what_the_payload_route_gives_for_the_same_document`).
- **The cost of a POST with one unknown** (measured 2026-11-22 on Memgraph, the live test's small world): 13 read
  transactions and 57 statements, held to that by a test. Four of them are the login (the API reads the token twice
  for a request that needs a user); 33 statements are the graph part's lay-out of the neighbourhood.

## Not built ⏳

- **10.3** The second stage: the weights measured (hand-set until then), reasons (the neighbours an unknown and a
  candidate share), how likely "someone new" is, several unknowns of one payload ranked jointly.
- **10.4** The interface module that fills review's `reconcileCandidates`.
- **10.5** The toolchain mode: not built until the user says what sets it off.
- **10.6** Measured on both backends at size; this page and the guide written out.
