# One kind of edge model: what collapsing `ViaEdge`/`EdgeModel` and `ReifiedRelation` would take

⏳ An investigation (2026-11-20), nothing built. The question: replace the two ways of putting values on a relation
with one `EdgeModel`, stored as a node only when it has to be, and otherwise as properties of the edge; and, above
all, have a relation through any number of edge models behave as **one edge** in a search.

## Summary

- **The search already treats a chain as one edge in the main case.** `EdgeA[EdgeB[EdgeC[Person]]]` is found by
  `Rel(is_=john)`, `exists` and `$mentions`, and each wrapper's own values can be asked with `through`. Checked live.
- **There are seven rough edges, two of them faults** (a read of an entity fails outright). They are listed below. All
  are in the search and the reverse read; none needs the storage changed.
- **Collapsing the storage is a large change with a small gain.** It touches the payload shape, so the API, the SDK,
  the interface, stored history versions, stored search patterns, RDF and every project's data. And the cases it
  would improve are few: of the reified relations declared in the repository, only the demo's `InRole` and `AtPage`
  could be stored on an edge; everything in `pangloss-library` and `pangloss-criteria` needs its node.
- **Recommendation:** fix the rough edges and give the search one way to ask about any step of a relation (option A,
  about 8 steps). Consider one declaration over the two storages afterwards (option B). Do not move the storage
  (option C) unless a measurement on large data shows it is worth it.

## What there is now

| | `ViaEdge[T, Certainty]` | `InRole[T]` (`ReifiedRelation`) |
|---|---|---|
| Fields | literals only | anything: literals, relations, embedded, annotated values |
| Payload | the reference plus `edge_properties` | `{"type": "InRole", ..., "target": [...]}` |
| Stored | properties on the forward and the reverse edge | a node with an id, `head_node_id`, labels; `target` edges |
| Target | one per edge | a list: one node can hold several |
| Has an id, a label template, subclasses, validators, hooks | no | yes |
| Records what it is | no: an edge does not say its edge model | yes: the node's labels |

They are not alternatives in the code: any relation option can carry an edge model, a reified relation included
(`ViaEdge[InRole[Person], Certainty]`, and `InRole[ViaEdge[Person, Certainty]]`). The library's own
`Identification[WeightedAlternative[T]]` is a reified relation holding a conjunction whose edges carry `Likelihood`.

## The rough edges, checked live

A scratch test on Memgraph (since deleted) with `chain: list[EdgeA[EdgeB[EdgeC[Person]]]]` and the mixed shapes.
What works: `Rel(is_=john)`, `exists`, `$mentions`, `through` with a `where` of each of the three wrappers, `$incoming`
with wrapper names, and the reverse read of the chain from the person.

| # | What | Seen |
|---|---|---|
| 1 | **Fault.** Reading an entity referred to through a reified relation that has a relation of its own (`InRole.role: RoleType`) | `Person.get` raises a `ValidationError`: `role_reverse.0.role.0.InRole.role: Field required`. The reverse read gives a wrapper its values and what it holds, not its other relations (`read_incoming.wrapper_view`). The forward read is right |
| 2 | **Fault.** Reading an entity referred to through a wrapper that is itself reached by an edge model (`ViaEdge[EdgeA[Person], Certainty]`) | `Person.get` raises: `edge_in_reverse.0.edge_in.0.EdgeA.edgeProperties: Field required`. The properties of the edge *into* a wrapper are not read back |
| 3 | The edge into a wrapper cannot be searched | `Rel(is_=john, edge=Certainty.Where(...))` on that field finds nothing: `edge` is only the last edge. With an edge model on both sides (`ViaEdge[EdgeA[ViaEdge[Person, C]], C]`) it silently tests the inner one |
| 4 | A wrapper's own relations cannot be asked | `Through(InRole, where={"role": ...})` is refused: "only the values of a wrapper can be tested here". "John, in the role of baker" cannot be searched when the role is an entity |
| 5 | Steps are not placed | In `EdgeA[EdgeA[Person]]`, `Through(EdgeA, a=1)` finds the document whether the outer or the inner has it. Steps are "some wrapper of the path", in no order |
| 6 | `$incoming` is behind | It takes wrapper names only: a step with a `where` and an `edge` are both refused (a 422) |
| 7 | Two vocabularies for one idea | A value on the way is `edge=` if it is stored on an edge and `through=[Through(...)]` if on a node, and `through` is refused on a field with no wrapper. The user has to know the storage, which is the thing the idea wants to hide |

Smaller: an edge does not record its edge model, so "has no `note`" is true of an edge of any other kind (documented);
the search form offers neither `edge` nor steps; and the reverse read gives a different shape for a direct `ViaEdge`
(a reference to the document, without the edge's properties) than for a wrapped one (the chain, with them).

## What the collapse would be

```python
class Certainty[T](EdgeModel[T]):      # literals only: properties of the edge
    value: int

class InRole[T](EdgeModel[T]):         # points at an entity: a node
    role: RoleType

person_involved: list[Certainty[InRole[Person]]]
```

One declaration and one payload shape; `initialise()` decides the storage of each class.

### What decides that a node is needed

More than "points at an entity". From what the code uses a reified node for:

- a relation, an embedded object or a list of annotated values of its own;
- **a target of more than one** (`target` is a list: two people in one role are one node; on edges the grouping is
  lost unless a shared key is written);
- an id that something keeps: review's parts and suggestions (`IdentificationByToolchain` is listed by its label
  index and confirmed in place, keeping its id), criteria's `MatchesCriteria` (a computed `target`, `same_one`, a
  worker that matches on the node), history's diff (lists are compared by id), the interface's scroll-to and reveal;
- `label_index`, a label template that is stored, a `DerivedMeta`, hooks that write.

So the rule cannot be inferred from the fields alone: a class would also need to be able to say `node=True`, and
`MatchesCriteria` and `Identification` would say it.

### Consequences

1. **The payload changes, and that reaches everywhere.** Whichever single shape is chosen, one of today's two goes:
   the API, the SDK and the generated stubs, the interface (about 26 source files branch on `edgeProperties`, about
   18 on a reified kind, with 29 and 23 unit test files), `populate.py`, every conformance model (49 reified
   declarations, about 25 edge models).
2. **Stored history versions are in the old shape.** A version is the complete write payload. `pangloss-history` has
   no handler for `AlterEdgeModel`, `WrapRelation`, `UnwrapRelation` or `ChangeWrapper` today (it reports
   "unsupported change"), so this needs building before any project with history could be moved.
3. **Storage flips under a model change.** Adding `role: RoleType` to an edge-stored class makes it a node: every
   edge of every field that uses it is rewritten. The migrations have `WrapRelation` and `UnwrapRelation`, but
   neither carries values across: wrapping takes the new node's literals from defaults, unwrapping drops them. Two
   new operations (edge properties to a node, and back) are needed, batched as `wrap_reified` is.
4. **Several edge-stored models on one edge need names and a record.** `EdgeA[EdgeB[Person]]`, both literal-only,
   is one edge with both sets of values: the properties have to be prefixed (Neo4j has no map properties), the same
   class twice needs a position, and a union (`EdgeA[Person] | EdgeB[Person] | Person`) needs the edge to say which
   it is. Today's edges say nothing, so existing edges need a migration too.
5. **A mixed chain leans on the weakest path.** `Certainty[InRole[Person]]` is an edge with properties *into* a
   node: exactly the shape of faults 2 and 3 above.
6. **Things that only one of the two has must exist for both, or be tied to the storage again.** Collapse, headless,
   `default_reified_type`, label templates, part ids on one side; `SumsTo` sliders, the chip's suffix, the paste
   rule on the other. A label template or a hook on an edge-stored class is either refused (and the user is back to
   knowing the storage) or forces a node.
7. **Stored search patterns** (criteria) name wrappers in `through` and edge models in `edge`; `migrating.py` would
   have to rewrite them. **RDF** writes a reified relation as a node with a URI and edge properties as quads on an
   edge URI: the output changes for whatever moves.
8. **The gain.** A literal-only chain becomes one hop: fewer nodes, and a search with no variable-length path. Not
   measured. In the repository's own models it would apply to `InRole` and `AtPage` only.

## Three options

### A. One edge in the search and the read; storage and declarations as they are

Fix the faults and close the gaps, and add one way to ask about any step of the way that does not depend on storage:

```python
Doc.Where(person_involved=Rel(is_=john, via=[Certainty.Where(value=Compare(gte=8)), InRole.Where(role=baker)]))
```

Each item names a class and is met by a node of it on the path or by an edge of it on the path. `through` and
`edge` stay as the exact forms.

| Step | Size |
|---|---|
| 1. Reverse read gives a wrapper its own relations (fault 1) | small |
| 2. Reverse read gives the properties of the edge into a wrapper (fault 2) | small |
| 3. An edge condition holds of any edge of the path, not only the last; a step can say the edge into it (3) | medium, both compilers |
| 4. A wrapper's relations in a step's `where`, by id (4) | medium |
| 5. Steps in order, optional (`Through(..., at=)` or the order given) (5) | small to medium |
| 6. `$incoming` with steps and `edge` (6) | medium |
| 7. `via`, with `Where` classes, the TypeScript types, `patterns.py` for criteria (7) | medium |
| 8. Edges record their edge model, with a migration, so `via` can tell them apart | medium; optional |
| 9. The search form offers it | medium; separate |

About 8 steps, each with conformance tests on both backends; roughly one to two weeks at the pace of the recent
plans. Steps 1 and 2 are worth doing whatever is decided. No data changes except step 8.

### B. One declaration, two storages kept

On top of A: `class Certainty[T](EdgeModel[T])` as the one way to write both, with `ViaEdge` and `ReifiedRelation`
kept as the storage underneath (a literal-only class with one target compiles to today's edge properties, anything
else to today's node), and one payload shape accepted for both with the old shapes still read. No data migration; the
stored shapes, history versions and RDF do not change.

The cost is in the model layer (the analysis of annotations, the builder, the stubs, the language server), a
translation at the edge of the write and the read, and the interface's export. Roughly another two weeks. The hard
part is consequence 6: deciding what an edge-stored class may not have, and saying so at `initialise()`.

### C. The storage follows the fields

A, B, and then the storage rule, the two migrations of values between an edge and a node, prefixed properties and
the record on each edge, history upgrade handlers, the criteria and review Cypher that match nodes, RDF, and a
migration of every project's data. I count 25 to 30 steps across about 150 source files and 120 test files; at a
guess four to six weeks, and the riskiest part is the data migration, which cannot be tested on anything but a copy
of a real database.

## Recommendation

Do **A** now, steps 1 and 2 first: they are faults whoever reads this. A gives what was asked for as the overriding
thing (one edge to the user, filters in between) without touching data.

Hold **B** until A is in use: if `via` makes the two feel like one in a search, the remaining difference is only in
how a class is declared, and it may not be worth a second syntax beside two that work.

Not **C**, unless a measurement on the large database shows that searches through literal-only wrappers are a real
cost. The storage difference is real, not an accident: a node has an identity and can hold several targets, and most
reified relations in use rely on one or the other.

## To decide

1. Whether A is the scope, and whether step 8 (edges record their edge model) is in it.
2. `via` as the name and shape of the storage-neutral condition, or `through` widened to take edge models.
3. Whether steps should be ordered by default (5).
4. Whether the two faults should become `xfail(strict=True)` conformance tests now, ahead of the fix.

## What this rests on

Read: the search checks and both compilers, the write plan, the reads, `relations.md`, `structured-search.md`. Run:
the scratch test above, on Memgraph only. From two surveys by sub-agents, not re-read by me: the file counts, the
interface branches, and the migration operations. One of those is inferred and unverified: that a rename or a change
of type of an edge model's own field runs the node path and so does not touch the edges. Worth a test of its own.
