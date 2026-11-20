# A relation through several wrappers as one edge: the plan

⏳ Planned 2026-11-20, nothing built. Branch `relation-steps`. This is option A of
[edge-models-unified.md](edge-models-unified.md): the storage and the declarations stay as they are; the search and
the reverse read stop caring which of the two a value on the way is stored as.

## What is to be true at the end

For `person_involved: list[EdgeA[EdgeB[EdgeC[Person]]]]`, and for any mix of reified relations, semantic spaces,
conjunctions and `ViaEdge` on the way:

1. `Person.get` reads every such relation back (two shapes fail today).
2. One condition asks about any step of the way, whether its values are on an edge or on a node:

   ```python
   Doc.Where(person_involved=Rel(is_=john, via=[Certainty.Where(value=Compare[int](gte=8)), InRole.Where(role=baker)]))
   ```

   ```json
   {"person_involved": {"is": "0194…", "via": [
     {"type": "Certainty", "where": {"value": {"gte": 8}}},
     {"type": "InRole", "where": {"role": {"is": "0195…"}}}
   ]}}
   ```

3. A wrapper's own relations can be asked ("in the role of baker", the role an entity).
4. `$incoming` takes the same.

`through`, `edge` and `exclude_wrappers` keep their meaning; stored patterns that use them are untouched.

## What `via` means

- **An item** is `{"type": <class>, "where": {...}}`; `where` may be left out. The class is an edge model, or a
  wrapper (a reified relation, a semantic space, a conjunction).
- **The way** of a relation is `node -e0-> w1 -e1-> … wk -ek-> target`: the field's own edge, the wrappers, the edge
  out of each. A relation with no wrapper is the one edge `e0`.
- **An edge-model item** is met by an edge of the way whose properties fit `where`. **A wrapper item** is met by a
  wrapper of the way of that class (or one below it) that fits `where`.
- **In order.** The items are met by different places of the way, in the order given, as the annotation nests:
  `Certainty[InRole[Person]]` is `via=[Certainty…, InRole…]`. Other steps may lie between. (Rough edge 5 of the report. `through` stays
  unordered.)
- **A wrapper's `where`** takes its values and its own relations by `is`, `is_any` and `exists`, not what it holds
  (`target`, `contents`, a conjunction's slots: that is the relation's own business). The same is allowed in a
  `Through` step's `where`.
- **With the rest:** `is`, `is_any`, a pattern, `exists`, `through` and `edge` all hold of the same way. Alone, `via`
  means "has a relation by such a way"; with `exists: false`, has none.
- **Checked:** an edge model must be one an edge of the relation can have (`Reach.edges`, as `edge` is checked); a
  wrapper item on a field with no wrapper in its type is refused, as is one the search leaves out
  (`exclude_wrappers`); at most `MAX_VALUES` items, each counted against `MAX_PATTERNS`.
- **Where:** a relation field, `$any`, `$mentions`, `$incoming`. Refused in the body of a `pangloss-derived` rule
  for now, with a message (rules have `through` with variables; `via` with variables is a later question).
- **An edge still does not record its edge model.** `via=[Certainty.Where()]` with nothing asked is therefore
  refused for an edge model ("ask something of it"), until edges say what they are (see "Later").

## Steps

Each step ends with its tests green on both backends and an "As built" section here.

### 0. The behaviour wanted, as tests

A conformance file `test_relation_steps_live.py`, from the scratch test described in the report: the models
(`chain`, `twice`, `edge_in`, `edge_out`, `both`, `role`, `plain`), the documents, and one test for each thing in
"What is to be true", each marked `xfail(strict=True)` with the step that lifts it. The cases that pass today
(`is`, `exists`, `$mentions`, `through` with a `where`) are plain tests in the same file, so nothing regresses.

**As built (2026-11-20).** ✅ `conformance/test_relation_steps_live.py`: 8 plain tests and 17 `xfail(strict=True)`, the
same on Memgraph and Neo4j, each seen to fail for the reason it gives. All seven fields were accepted by
`initialise()` as written. In the JSON form only (typed forms are step 6).

- The refusals of `via` are one test, lifted by **step 3** (the check), not 4. The `xfail`s have no `raises=`: after
  step 3 the tests of steps 4 and 5 fail in another way (an answer, not "extra inputs are not permitted").
- A person for each shape whose reverse read fails (Ann, Bea, Dan, Cat), so the reads that work are not failed by
  them.
- What the tests take `via` to mean where the text above did not say:
  - the edges and wrappers of the way are **one sequence**: on `edge_in`, `[EdgeA, Certainty]` finds nothing (the
    certainty is on the edge into the wrapper), and on `both`, `[Certainty 9, EdgeA]` and `[EdgeA, Certainty 9]`
    find different documents;
  - a wrapper item with no `where` is allowed, as a place in the order;
  - `exists: false` with `via` also finds what has no such relation at all;
  - `$incoming` with `via` is tested with `field` given only; `$mentions` only for relations of the document itself.
- The answers of the step 4 and 5 tests that have a `through` or `edge` form today were checked against it; those
  that depend on the order could not be, until step 4.
- `InRole.role` is required, so `exists` on it is true of every role: a weak test, kept.

### 1. The reverse read

In `pangloss_cypher.read_incoming` and `read_query.build_incoming_query`:

- `wrapper_view` gives a wrapper only the fields that hold what it is made for. It is to give its other relations
  too (`InRole.role`), from the same `held` rows, which already have every forward edge of every wrapper of the
  chain.
- The query returns the types of the edges of the ascent and not their properties. It is to return the properties,
  and each wrapper on the way down is given the `edge_properties` of the edge into it, the field's own edge
  included.

The budgets of `test_query_costs.py` must hold: no new round trip.

### 2. A wrapper's own relations in a `where`

`search.check_values_only` refuses whatever is not a literal. It is to let through a relation of the wrapper that
is not one of its held fields, by `is`, `is_any`, `exists`. `WrapperWhere` (typed) gains those fields; the stubs
follow.

Not known: whether an `EXISTS { MATCH (nd)-[…]->(…) }` is accepted inside the `any(nd IN [nodes(p)[i]] WHERE …)`
that names a wrapper of a path, on Memgraph and on Neo4j. Tried first, on both. If not, the wrapper is bound by a
`MATCH` inside the relation's `EXISTS` instead.

### 3. `via`: the check

In `pangloss_models.search`: `Condition.via`, a `ViaItem` model, `CheckedVia` on `CheckedCondition`, `check_via`
with the refusals above, `conditions_of` walking it, and `check_match` refusing an excluded wrapper. No database:
tests in `pangloss-models`.

### 4. `via`: the compilers

`Compiler.path_tests` gains the ordered test: nested `any(i IN range(…))`, each inside the one before with its
lower bound, over positions of the way (edge `j` at `2j`, wrapper `i` at `2i - 1`), an edge item reading
`relationships(p)[j]`, a wrapper item `nodes(p)[i]`. `relation_of` and `reaching`: the direct branch stands only if
every item is an edge model and there is one of them; otherwise the way through wrappers. Neo4j's own
(`related_to_targets`, `mentioned_in_document`) take it written from the target (`backwards=True`).

Measured before it is kept, on the scratch database of current demo models (the stopped container on `:7690`), and
on Neo4j: a `via` against the `through` step that says the same.

### 5. `$incoming` with `via`

`Incoming.via`, `check_incoming`, and `Compiler.incoming` with the same path test, written backwards. `through`
by name stays.

### 6. Everywhere a pattern is read or written

| Where | What |
|---|---|
| `search_where` | `Rel(via=[…])`, `IncomingFrom(via=[…])`; an `EdgeWhere` or `WrapperWhere` given as an item; `to_json` |
| Stubs | `pangloss make-stubs`, `pangloss_testing.framework_stubs` |
| `migrations/patterns.py` | the walk over a stored pattern: `via` items renamed, rewritten or marked broken as `through` steps and `edge` are |
| `pangloss-criteria` | `analysis.py`: a wrapper item with a relation adds what it reaches to `depends_on`; `describeCriteria`: says a `via` in the summary |
| `pangloss-derived` | the refusal in a rule's body, with its test |
| Interface | `api/types.ts` (`ViaItem`, on `RelationCondition` and the incoming condition); `whereToForm` gives `null` for a pattern with `via`, as for `edge` |
| SDK | the contract test sends one |

### 7. Docs

`structured-search.md` (a section, and the "Not done" lists), `search-where-implementation.md`,
`guide/search/README.md`, `models.md` ("Reading an entity"), `status.md`, the skill's `references/modelling.md`,
`TODO.md`, and "As built" in the report.

## Who builds each step

The agents of `.claude/agents/`: **`builder`** (builds decided work from a brief, with tests, does not commit),
**`test-runner`** (runs and reports), and **`Explore`** for "where is this read". **Main** is this session: it
settles what is open, makes the changes to the core read path and the compilers, measures, writes the briefs, reads
each diff, writes "As built", and commits and pushes after each step.

| Step | Mostly | Main keeps | To `builder` | Runs (`test-runner`) |
|---|---|---|---|---|
| 0. Tests | `builder` | The list of cases and which step lifts each | The whole file, from a brief with the models and results of the scratch test | The file on Memgraph and Neo4j: every `xfail` fails for the reason given |
| 1. Reverse read | Main | All of it: a core read path with cost budgets, and small | — | The file, `test_query_costs.py`, then the conformance suite on both |
| 2. Wrapper relations | Main, then `builder` | The Cypher tried on both backends, and the fallback if it is refused | `check_values_only`, `WrapperWhere`, stubs, the unit tests, once the form of the Cypher is known | Models, then conformance on both |
| 3. `via`, the check | `builder` | The meaning above; reading the refusals' wording | All of it, from "What `via` means" | `packages/pangloss-models` |
| 4. `via`, the compilers | Main | All of it, and the measurement | — | Conformance on both; `test_query_costs.py` |
| 5. `$incoming` | Main | The path test backwards | The typed `IncomingFrom` and its tests, with step 6 | Conformance on both |
| 6. Everywhere else | `Explore`, then `builder` in two briefs | The list of readers checked against what `Explore` finds; `analysis.py`'s reach, which decides whether the criteria worker is exact | Python (typed classes, stubs, `patterns.py`, criteria, derived's refusal, SDK test); interface (types, `whereToForm`, `describeCriteria`, translations) | Each package touched; the criteria live tests; the interface's unit tests |
| 7. Docs | `builder` | A reading of the docs against the code | All of it | `./run_tests.sh`, whole, before the last commit |

Steps 3 and 0 do not depend on each other or on 1, and can be given to `builder` at once while main does step 1.
A report from an agent is a claim: each is checked against the diff and a run.

## Not yet known

- Step 2's Cypher (above).
- What an ordered `via` costs on a long way. A step of `through` is tested once for each path; nested `any` is the
  product of the positions, small for ways of two or three wrappers, unmeasured.
- Whether Memgraph accepts `relationships(p)[j]` with a computed index inside nested list predicates as it does
  the one level `step_at` uses now.

## Later, not in this plan

- **Edges record their edge model** (a property written with the edge, and a migration for those that exist). It
  would let `via=[Certainty.Where()]` mean "by a `Certainty`", and end the "has no `note`" surprise. To decide once
  `via` is in use.
- **The search form offers `via`** (and so `whereToForm` reads it back).
- The reverse read of a direct `ViaEdge` gives a reference to the document without the edge's values, where a
  wrapped one gives them: left as it is.

## Decided (2026-11-20)

1. `via` is ordered.
2. `via` is the name.
3. A commit and a push after each step, as for matches criteria.
