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

**As built (2026-11-20).** ✅ Both faults fixed, with no new query: the three `xfail`s of step 0 are plain tests.

- `read_query.build_fetch_incoming_query` returns `chain_edge_properties` beside `chain_edge_types`: the properties of
  the reverse edges of the ascent. A reverse edge is written with the values of its forward edge, so
  `chain_edge_properties[i]` is the edge *into* `chain[i]`, the field's own edge for the topmost wrapper.
- `read_incoming.wrapper_view` gives each wrapper `edge_properties` from it (without `reverse`, `pg_position`,
  `computed`, `seen_by`, and only when something is left, as `build_tree` does in the forward read), and
  `own_relations(wrapper)`: every relation field that is not a held one, from the same `held` rows, a list or one or
  `None` as the field is declared.
- One more test than planned: a list and an optional relation of its own on the outer of two wrappers, and an edge
  model on the edge between the two (`InRoles[ViaEdge[Inner[Person], Weight]]`).
- **Left as it was:** what a wrapper's own relation points at is given as the node's own properties. That is right
  for an entity (a reference); an embedded object or a nested document of a wrapper's own, with relations of its
  own below it, is not read deeper here. Before this step such a wrapper could not be read from the entity at all.

### 2. A wrapper's own relations in a `where`

`search.check_values_only` refuses whatever is not a literal. It is to let through a relation of the wrapper that
is not one of its held fields, by `is`, `is_any`, `exists`. `WrapperWhere` (typed) gains those fields; the stubs
follow.

Not known: whether an `EXISTS { MATCH (nd)-[…]->(…) }` is accepted inside the `any(nd IN [nodes(p)[i]] WHERE …)`
that names a wrapper of a path, on Memgraph and on Neo4j. Tried first, on both. If not, the wrapper is bound by a
`MATCH` inside the relation's `EXISTS` instead.

**As built (2026-11-20).** ✅ A step of `through` (and so an item of `via`, once compiled) asks a wrapper's own
relation by `is`, `is_any` and `exists`; the two `xfail`s are plain tests, with one more (a wrapper in the middle of
the way, an optional relation, `$any_of`, `$not`, the edge that leaves it, another step beside it, `$any`,
`$mentions`).

- **The Cypher, tried on both.** Memgraph 3.14 accepts an `EXISTS { MATCH (nd)-[…]->(…) }` inside
  `any(nd IN [nodes(p)[i]] WHERE …)` and **gives the wrong answer**: it held for a wrapper it does not hold of (the
  miller's document for the baker). The same with a pattern comprehension and with `exists(pattern)`; a pattern from
  a name bound by a list predicate is not tested of that node. An `EXISTS` that uses the *index* of a list predicate
  is an error ("Expected to generate all filters"). What is right on both: a subquery that names the wrapper by
  `UNWIND`:

  ```cypher
  EXISTS { UNWIND range(1, size(nodes(p)) - 2) AS i
           WITH nodes(p)[i] AS nd, relationships(p)[i] AS ed
           WHERE $label IN labels(nd) AND EXISTS { MATCH (nd)-[e:role]->(w) WHERE w.id IN $ids } …
           RETURN 1 AS found }
  ```

  `Compiler.step_with_relations`, used only for a step that asks a relation (`has_relation`); every other step keeps
  the list predicate of `step_at`, and its measured plan. **Step 4 has to be written with this in mind:** an item of
  `via` with a relation cannot sit inside nested `any(i IN …)`.
- **Neo4j** finds what is related to given ids once, before the `MATCH` (a prelude). That is of the nodes of the
  search, not of a wrapper named inside a test, and the list was not in scope there: `Compiler.local` is set while a
  wrapper's own tests are compiled (`own_tests`), and `Neo4jCompiler.reaching` then gives the plain pattern.
- **The check** (`check_values_only`): a relation field of the wrapper that is not a held one
  (`held_field_names`: a type variable in the class or one above it). A pattern, `through`, `edge` or `via` on it is
  refused: "a relation of a wrapper is tested here by 'is', 'is_any' and 'exists' only".
- **Typed:** the `Where` of a wrapper has a field for each relation of its own, a `Rel`; an id or anything with one is
  `Rel(is_=…)`: `Through(InRole, where=InRole.Where(role=baker))`. Stubs: only `MatchesCriteria.Where` changed among
  the framework's (`description`); the demo's did not (its `InRole.role` is an enum).
- `conditions_of` now walks the items of the steps of `through` (it did not).
- **`pangloss-derived` refuses it** in the body of a rule ("a relation of a wrapper is not tested in the body of a
  rule yet"): a rule's compiler places a step with `step_at` in a list comprehension, the form that is wrong above.
- **Not measured yet:** the `UNWIND` subquery on large data. With step 4, which uses the same form.
- **For step 6 (criteria):** such a condition is by id, so it adds no class to `classes_touched`; `analysis.analyse`
  reads neither `steps` nor `via`, so it is no anchor and no reason for `far`.
- **Found, not fixed:** a generic reified relation with a relation of its own *through a wrapper*
  (`office: Negative[RoleType] | None`) fails `initialise()` with `TypeError: Cannot take a Union of no types`
  (`builder.wrap_in_union`). And a field of a non-generic class below a wrapper (`list[JohnRole]`,
  `class JohnRole(InRole[Person])`) "cannot be searched yet". Both in `TODO.md`.

### 3. `via`: the check

In `pangloss_models.search`: `Condition.via`, a `ViaItem` model, `CheckedVia` on `CheckedCondition`, `check_via`
with the refusals above, `conditions_of` walking it, and `check_match` refusing an excluded wrapper. No database:
tests in `pangloss-models`.

**As built (2026-11-20).** ✅ `ViaItem`, `Condition.via`, `CheckedVia(kind, model, items)` on `CheckedCondition`,
`check_via`, `conditions_of`, `check_match`; 20 tests in `pangloss-models/tests/test_search_via_check.py`, and the
refusals' conformance test is a plain test. `ViaItem` is a public name.

- `CheckedVia.items` is in the form of a `CheckedEdge`'s and a `CheckedStep`'s (`Compiler.all_of` compiles it);
  `kind` is `"edge"` or `"wrapper"`; a wrapper is to be matched by its label (the class or one below it).
- **`Reach.edges` is narrower, and so `edge` is too.** `chain: EdgeA[EdgeB[EdgeC[Person]]]` was said to have
  `Certainty` edges, because another field uses `EdgeA[ViaEdge[Person, Certainty]]`: the edge models of a wrapper
  were collected from every use of the generic. The way of one relation now takes only its own (through the options
  of its parameters). `{"chain": {"edge": Certainty…}}` was accepted and found nothing; it is now refused ("an edge
  of this relation is never a Certainty"). The edge onwards of a `through` step is as before.
- `Reach.wrappers` (new): the wrapper classes a relation's type names on its way. A wrapper item is accepted if its
  class is one of them, or above or below one. `through` checks no such thing, and was left alone.
- Each item counts once against `MAX_PATTERNS`, a wrapper item with no `where` too. `via: []` is refused.
- `exclude_wrappers` refuses an item by the names it leaves out (those below each included): an item of a class
  *above* an excluded one is allowed.
- `$any`, `$mentions`: any edge model and any wrapper (there is no reach). `exists` is not an operator of either, so
  `exists: false` with `via` is for a relation field only.
- No part of a pattern takes camelCase names, and `via` does not either.
- **Until step 4**, `Compiler.condition` refuses a condition with a `via` ("checked, but not compiled yet"), so no
  search runs without it. A wrapper item with a relation (`InRole.role`) is refused by `check_values_only` until
  step 2.
- Brought forward from step 6: the body of a `pangloss-derived` rule refuses a `via` (its own compiler would have
  left it out). It cannot be written there until the typed `Rel(via=…)` exists, so its test stays in step 6.
- Still to follow in step 6: `pangloss_criteria.models.classes_touched` and `analysis.py` (a wrapper item's class
  is not yet in what a pattern depends on), `migrations/patterns.py`.

### 4. `via`: the compilers

`Compiler.path_tests` gains the ordered test: nested `any(i IN range(…))`, each inside the one before with its
lower bound, over positions of the way (edge `j` at `2j`, wrapper `i` at `2i - 1`), an edge item reading
`relationships(p)[j]`, a wrapper item `nodes(p)[i]`. `relation_of` and `reaching`: the direct branch stands only if
every item is an edge model and there is one of them; otherwise the way through wrappers. Neo4j's own
(`related_to_targets`, `mentioned_in_document`) take it written from the target (`backwards=True`).

Measured before it is kept, on the scratch database of current demo models (the stopped container on `:7690`), and
on Neo4j: a `via` against the `through` step that says the same.

**As built (2026-11-20).** ✅ `Compiler.way_test`, called by `path_tests`, so every path of a relation takes it
(Neo4j's `related_to_targets` and `mentioned_in_document`, `backwards`, too). The guard of step 3 is gone; the ten
conformance tests are plain tests, on both backends.

- **Two forms.** Where no item asks a relation of a wrapper, list predicates inside one another, as planned. Where
  one does (`InRole.role`), the places are named by `UNWIND` in one subquery (`UNWIND range(…) AS i1 UNWIND
  range(i1 + 1, …) AS i2 WITH nodes(p)[i1] AS nd, … WHERE … RETURN 1 AS found`), for the reason found in step 2:
  on Memgraph 3.14 a pattern from a node named by a list predicate is not tested of that node.
- **The places are counted by their own numbers**, not by positions `2j` and `2i - 1`: edge `j` is
  `relationships(p)[j]`, wrapper `i` is `nodes(p)[i]`, and both end at `size(nodes(p)) - 2`. An item after edge `j`
  starts at `j + 1` (an edge or a wrapper); one after wrapper `i` at edge `i` or wrapper `i + 1`. `backwards`, the
  same numbers are read from the other end of the path.
- **A relation with no wrapper** is one edge: its branch stands if `via` is one edge-model item
  (`Compiler.never_direct`, `way_of_one_edge`), and is `false` otherwise (`true` under `exists: false`). With a
  `via`, as with `edge`, the direct branch is not of an edge to a wrapper.
- **Measured** (the shortest of 5; a search of factoids that gives ids). `via` costs what the `through` or `edge`
  that says the same costs, and finds the same number, on both:

  | Search | Memgraph, 75,556 factoids: `via` | `through` / `edge` | Neo4j, 6,006: `via` | `through` / `edge` |
  |---|---|---|---|---|
  | `source` at a page (`AtPage.page`) | 125 ms | 144 ms | 28 ms | 24 ms |
  | `source` is one, at a page | 67 ms | 66 ms | 2.9 ms | 3.2 ms |
  | no `source` at the page (`exists: false`) | 133 ms | 151 ms | 26 ms | 27 ms |
  | `$mentions` a person in a role | 334 ms | 332 ms | 2.9 ms | 2.7 ms |
  | `$mentions` by a sure edge (`edge`) | 494 ms | 487 ms | 2.8 ms | 2.6 ms |
  | `$mentions`, two items in order | 334 ms | | 2.3 ms | |

  With every item named by `UNWIND` (forced, as an item that asks a relation is) the same searches took the same
  (125 → 130 ms, 334 → 340 ms; on Neo4j 28 → 22 ms). The demo has no wrapper with a relation of its own, so the
  relation itself was not measured on large data: only the form that names the places.
- Tests: the conformance file (the test of a wrapper's relation also asks it by `via`, in order among edges and
  another wrapper, with `exists: false`, `$any` and `$mentions`), and the text of both forms in
  `pangloss-cypher/tests/test_step_with_relations_text.py`.

### 5. `$incoming` with `via`

`Incoming.via`, `check_incoming`, and `Compiler.incoming` with the same path test, written backwards. `through`
by name stays.

**As built (2026-11-20).** ✅ `Incoming.via` (a list of `ViaItem`), checked by `check_via` and carried on the
condition as a relation's is (`CheckedCondition.via`), so `conditions_of` and the refusal of a wrapper the search
leaves out (`check_match`) take it with no change. The conformance test is a plain test on both backends, with
more cases than it had; five tests of the check in `pangloss-models/tests/test_search_via_check.py`.

- **The way is from the node that refers to the entity**, in the order of that node's field: `via` reads the same
  in `{"chain": {"via": […]}}` of a document and in `$incoming` of a person. The path of the query is written from
  the entity, so `Compiler.way_test` counts from its other end (`backwards`).
- **What an item may be** is taken from the relations that can point at the entity: the one named by `field`, or,
  with no `field`, all of them together (an edge model or a wrapper that any of them can have). So with no `field`
  an item is refused only if no relation of the class could meet it.
- **A relation with no wrapper** is met by one edge-model item, as in step 4: the direct branch tests it of its one
  edge, and is left out where the `via` asks for a wrapper or for more than one place.
- A wrapper's own relation (`InRole.role`) is asked here too, by the `UNWIND` form.
- Not measured on large data on its own: the test of the path is step 4's, and the path it is put in is the one
  `$incoming` with `through` already had.
- Still to follow in step 6: the typed `IncomingFrom(via=…)`, the stubs and the interface's types.

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
