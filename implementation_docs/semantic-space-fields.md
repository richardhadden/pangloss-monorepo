# The fields of a semantic space ⏳

What each of the eight proposed fields of `SemanticSpaceMeta` would mean and how each would be used: ChatGPT's four
(`semantic_family`, `semantic_operator`, `content_status`, `operand_cardinality`, in `semantic_spaces_demo.py`) and
the four of [the report](semantic-spaces-formalisation.md) (`veridical`, `fit`, `logical`, `unary`). **Decided by
the user (2026-11-24): the report's four.** ChatGPT's are described for comparison and are not taken, alone or beside
the report's. Then how the four work with similarity, how to explain them to the people who enter and read data,
negatives that record a relation (a gradient a person can judge, and how it might be built), derived edges through
spaces (measured on the demo), and the data model of the user's project, `apis-instance-manmax` (its `model_config.json`, read on 2026-11-24), taken as
an exercise in what such fields would have to cover. **Nothing here is built**: every `SemanticSpace.Meta(...)` below
with one of these fields is a proposal, and so are `Modal`, `Holder()`, `Addressee()` and `Expectation`. What is said of the code as
it is was read in it, and one fault was found by a scratch test (below).

A summary of this page and the report is [semantic-spaces-summary.md](semantic-spaces-summary.md); how the four
would be built, [semantic-spaces-plan.md](semantic-spaces-plan.md).

Writing this revised two of the report's four: `logical` gives a negation, or a modal by its force and its flavour
(`Modal("possibility", "epistemic")`), rather than a yes or no; and `fit`'s values are `"describes"` and
`"prescribes"` rather than `"world"` and `"word"` (see each).

## Contents

- What any field of `SemanticSpaceMeta` is
- A fault in how spaces are recorded today
- ChatGPT's four (not taken): `semantic_family`, `semantic_operator`, `content_status`, `operand_cardinality`
- The report's four: `veridical`, `fit`, `logical`, `unary`
- The two sets side by side
- One example, through every reader
- How it works with similarity
- How to explain it to people
- Negatives that record a relation
- Derived edges through spaces
- The manmax model as an exercise
- What the exercise adds
- Decisions for the user

## What any field of `SemanticSpaceMeta` is

The same for all eight:

- **Declared on the class**, in `_meta = SemanticSpace.Meta(...)`, and **inherited**: the meta kit's default rule
  (`MetaRules.INHERIT_OR_OVERRIDE`, `meta_kit/meta.py`) gives a subclass every value its parent has unless it sets
  that value itself. So a family is an abstract space class that sets the values once, and a subclass changes only
  what differs (`Knowledge` below `Epistemic` sets `veridical=1` and inherits the rest). ChatGPT asked for this too.
- **Checked at `initialise()`**, as the other meta options are; a wrong combination is a `PanglossModelError`
  naming the class.
- **Not data.** Changing one changes no stored node, so it should not be in the migrations' snapshot of a class
  (which today holds `abstract`, `useInSemanticSpaceLabel` and a few others, not every option), and needs no
  migration. A reader that keeps a signature of what it was built from (the graph part's maps) has to put these in
  it, so that a change makes a rebuild due.
- **Exported** with the models (`export_models()`), with their TypeScript types, so the interface can read them.
- **Read from a node without walking the graph.** Every node inside a space carries `meta.semantic_spaces`, the
  names of the spaces around it **outermost first** (`pangloss_models/context.py` appends each space as it goes
  down), and `meta.context_labels`, the same path with the documents between the spaces, by type and id (every
  document whose class keeps the default `use_in_semantic_space_label=True`). So a reader
  goes from a statement to its path, from each name to its class, and from the class to its meta. A statement that
  *holds* a space (the `Order` round `Ordered[...]`) is the document just before the space in `context_labels`, so
  its holder can be found from the statement inside.

## A fault in how spaces are recorded today

Found while checking the last point, by a scratch test (`/tmp/space-trial/test_single_slots.py`, run against the
workspace's models; not in the repository):

```python
class Threat(Conjunction):
    cause: IfCondition[Statement]          # a single relation, each slot in a space of its own
    consequence: Committed[Statement]
```

The statement in `cause` is recorded as in `["IfCondition"]`, as it should be. **The statement in `consequence` is
recorded as in `["IfCondition", "Committed"]`**, as if it were inside the condition too, whether the `Threat` is in
a list or in a single field. The cause is in `propagate_context` (`pangloss_models/context.py`): what a *single*
relation holds is given the node's own lists, which a space below it appends to, so a later sibling sees the space
of an earlier one. Its docstring says this sharing "is kept" (so it was carried over on purpose from the code before
it), with a reason that holds for the context labels of documents and not for spaces.

It matters because every reader of the spaces would be wrong for exactly the shape a conditional needs: search's
`$spaces`, the RDF export's `pgo:inSpace`, and anything built on the fields below. A conjunction whose slots are
lists, or a space whose contents is a list, is not affected (each item gets a copy). The fix is small; stored data
has the wrong lists too, and a migration works them out with the same algorithm, so the fix needs those nodes worked
out again. **Not fixed: the user's call** (it is the first thing the manmax exercise needs, below).

**Tried further, and on the demo** (2026-11-24): the leak reaches a statement with no space of its own, and derived
edges with it; the demo's data has none of it; and a narrower fix than copying the lists mends every shape while
changing nothing stored in the demo. See [Derived edges through spaces](#derived-edges-through-spaces).

## ChatGPT's four (not taken)

### `semantic_family`

**What it says.** The general kind of interpretation a space belongs to.

**Values** (an enum in `pangloss_models`): `POLARITY`, `ALETHIC`, `EPISTEMIC`, `EVIDENTIAL`, `PREDICTIVE`,
`DESIDERATIVE`, `INTENTIONAL`, `DIRECTIVE`, `COMMISSIVE`, `CONDITIONAL`, `DEONTIC`, `TOPIC`. Default `None`.

```python
class BelievedContent[T](SemanticSpace[T]):
    _meta = SemanticSpace.Meta(semantic_family=SemanticFamily.EPISTEMIC, ...)
```

**How it would be used.**

- *The type menu*: the spaces' sections of `TypeMenu` (today one section for each space, headed with its name)
  grouped by family: "Epistemic: Known, Believed, Doubted".
- *Search*: "inside any epistemic space", compiled to the names of the spaces of the family and asked of
  `meta.semantic_spaces`, as search already expands a wrapper class into the classes below it
  (`exclude_wrappers`, `test_search_match.py`).
- *The RDF export*: a superclass for each family in the generated ontology.

**What is wrong with it.** Each use is already served by an abstract parent class
(`class Epistemic[T](SemanticSpace[T])`, abstract): the menu can group by it, search expands it, and the ontology has it as a class. As
an enum it is a closed list: a project with a family it does not name (legal procedure: `Charged`, `Sentenced`,
`Pleaded`) needs a change to the core. The file itself does not keep to it: the conversation has a `TOPIC` family,
the file puts `KnownAbout` in `EPISTEMIC` with a `TOPIC` *status*. The one thing a family carries that logic needs is
a modal's *flavour* (what its "must" or "may" is relative to), and the report's `logical` holds that, for the modal
spaces only (below).

### `semantic_operator`

**What it says.** What the space does to its contents.

**Values**: the conversation lists `NEGATION`, `POSSIBILITY`, `NECESSITY`, `HYPOTHESIS`, `KNOWLEDGE`,
`AWARENESS`, `BELIEF`, `DOUBT`, `HEARING`, `REPORTING`, `PREDICTION`, `DESIRE`, `INTENTION`; the file also uses
`DIRECTIVE`, `COMMITMENT`, `CONDITIONAL_ANTECEDENT`, `OBLIGATION`, `PERMISSION`, `PROHIBITION`, which were never
defined. Default `None`.

**How it would be used.**

- *Normalising*: to see that `Not[Possible[p]]` and `Necessary[Not[p]]` say the same thing, the code has to know
  which class is negation, which possibility and which necessity. The operator names them whatever the classes are
  called, so a table of dualities keyed by operator can rewrite one into the other. **This is the one use no other
  field gives**, and it is why the report's `logical` gives a modal's force and flavour (below).
- *Naming the operator for others*: two projects' `Negative` and `Not` are both `NEGATION`; an export or an
  import between projects could match them.

**What is wrong with it.** Outside negation and the modals it is a second name for the class: each space has one
operator, fixed by its class, and no code could act on `BELIEF` or `HEARING` without a table, kept outside the
models, of what each one does. Naming a class for others is what `pangloss-rdf`'s mapping of classes to outside
vocabularies is for (mixins, as the demo's `Statement` has `E5_Event`; whether it allows them on a space has not been
checked).

### `content_status`

**What it says** (the conversation): "how the contents relate to the source's assertion of the enclosing
statement", and explicitly **not an outcome**: `DIRECTED` says the journey was the content of an order, not that it
happened or did not.

**Values**, from the file: `DENIED`, `POSSIBLE`, `NECESSARY`, `ASSUMED`, `TOPIC`, `FACTIVE`, `BELIEVED`,
`DOUBTED`, `HEARD`, `REPORTED`, `PREDICTED`, `DESIRED`, `INTENDED`, `DIRECTED`, `COMMITTED`, `CONDITIONAL`,
`OBLIGATORY`, `PERMITTED`, `PROHIBITED` (none of them defined in the conversation). Default `None`.

**How it would be used.**

- *A word for the reader*: a badge on a statement in a list or on its page: "Directed", "Heard, not endorsed".
- *A filter*: "only what the source asserts" is "no space with a status".
- *Behaviour, through a table*: a reader that has to decide something (does a derived rule fire, do two statements
  contradict) maps each status to what it does, by a table like [the one below](#the-two-sets-side-by-side).

**What is wrong with it.** It is the same value as the operator in all but two cases (`HEARING` gives `TOPIC` or
`HEARD`; `AWARENESS` gives `TOPIC`), and the table that would make it useful is the report's four fields under
another name. As a word for the reader it is good; the class's name and docstring already give that word, and the
interface shows them.

The manmax model has the one-bit ancestor of this field: every statement has `head_statement: bool` (default
`True`), false for a statement that is only held by another. That says *that* a statement is not asserted, never
*why*.

### `operand_cardinality`

**What it says.** Whether the space applies to one proposition or to several.

**Values**: `ONE` (the default) and, presumably, one for "several" (the enum was never given).

**How it would be used.** To refuse a `Negative` with two statements in its `contents`. As the conversation says,
it is "descriptive until you implement validation": every space's `contents` is a list.

**What it should be about.** The question that matters is not how many items a list has but **what a list under the
operator means**, and logic answers it by the operator's monotonicity:

- An **upward monotone** operator (what follows from its contents also falls under it: necessary, possible,
  obligatory, permitted, ordered, promised, intended, known, believed, reported) can be read item by item: "ordered
  to go and to pay" gives "ordered to go", and a comparison can take each item alone.
- A **downward monotone** one (not, forbidden, doubted, refused) cannot: "not (went and paid)" does not give "did
  not go"; "forbidden to do both" does not give "forbidden to do each".

So the operators that need one operand are the negative ones, and the rule can be stated once: a list under an
upward operator is read item by item; a downward one takes one item (or its list is compared as a whole, never item
by item). The report's `unary` is this.

## The report's four

### `veridical`

**What it says.** Whether the space commits the source to its contents being so.

**Values**: `1`, the contents are so (knowing that, confirming that); `-1`, they are not (not, denial); `0`,
neither (believing, hearing, reporting, possibility, hypothesis, wishing, intending, ordering, promising, permitting,
a condition). Default `0`: a space nobody has described is read as "not asserted".

**What is not a space.** A statement nested in another **with no space** is asserted: the `churchservice`'s parts,
the occupation an election results in, what someone is thanked for. So `1` is rare on a space: it marks an
attitude to something the source also asserts (`Known`), not assertion itself.

**How a path composes.** From `context_labels`, which has the statements between the spaces, not from
`meta.semantic_spaces` alone. First normalise each run of spaces next to each other (the table under
[`logical`](#logical)). Then walk from the outside with a sign that starts at `1`:

- a `1` space keeps the sign, and `logical="not"` flips it;
- once the sign is `-1`, the next space or statement makes the path `0`, leaning neither way (that something is not
  so says nothing of what it holds);
- at the first `0` space the path is `0`, the source not committed, and the walk goes on only to find which way it
  **leans**, for p or against it: a `"not"` below turns the lean, and a space or statement met while it leans
  against leaves it leaning neither way.

Which way an uncommitted path leans matters to comparison: "it was reported that he did not go" is no support for
"he went".

| Path | `veridical` of p | If `0`, it leans |
|---|---|---|
| `Not[p]` | `-1` | |
| `Not[Not[p]]` | `1` | |
| `Reported[p]` | `0` | for p |
| `Reported[Not[p]]` | `0` | against p |
| `Not[Known[p]]` (it is not known that p) | `0` | neither way |
| `Not[Might[p]]` (it cannot have been so), read as `Must[Not[p]]` | `-1` where the project's `Must` commits the source (`veridical=1`), else `0` | against p |
| `Known[ChurchService(parts=[p])]` | `1` | |
| `Not[ChurchService(parts=[p])]` (there was no such service) | `0`: the flat list on p, `["Not"]`, would wrongly say `-1` | neither way |
| `Order(content=Ordered[p])`, the order asserted | `0` | for p, prescribed |
| `Order(content=Ordered[Not[p]])` | `0` | against p, prescribed |

**How it would be used.**

- *Comparison* (`pangloss-compare`, phase 12): the relation of two statements whose contents match. One `1` and one
  `-1`: they contradict; a `1` and a `0` that leans for p: support; one that leans against: tension (all of it under
  [How it works with similarity](#how-it-works-with-similarity)). Phase 12's `CompareMeta(negates=True)` is
  `veridical=-1`.
- *Derived rules* (`pangloss-derived`): today a fact found in a space is *qualified* unless the space's own
  `DerivedMeta(derivation=...)` says `block` or `transparent`. A default from `veridical`: `1` transparent, `0`
  qualify (as now), `-1` block. A rule that derives "traded with" from purchases would then derive a plain fact
  from a purchase someone is known to have made, a qualified one from a purchase that was ordered, and none from a
  purchase the source says did not happen.
- *Identity claims* (`pangloss-library`): today a `SameEntity` in any space joins nothing. With `veridical`: in a
  `1` space it joins as if bare; in a `-1` space it is a claim that the two are **different**, which the clusters
  and reconciliation could use ("not to be suggested as this one").
- *The time part* (`pangloss-dates-vectors`): a date on a statement whose path is not `1` is of something that
  did not happen or was not asserted, and would count for nothing (the open item of step 9.3, `TODO.md`).
- *The RDF export*: today nothing inside any space is asserted (`pgo:inSpace`, no direct triples). With
  `veridical`, what is inside a `1` space would get its direct triples too.
- *Search*: a proposed node condition, `"$asserted": true`, compiled from the names of the spaces by their values.
- *The interface*: a mark on a statement whose path is not `1`, in lists and on its page.

```python
class Epistemic[T](SemanticSpace[T]):
    _meta = SemanticSpace.Meta(abstract=True, veridical=0)


class Known[T](Epistemic[T]):
    _meta = SemanticSpace.Meta(veridical=1)


class Not[T](SemanticSpace[T]):
    _meta = SemanticSpace.Meta(logical="not")    # veridical=-1 and unary=True follow
```

### `fit`

**What it says.** Whether the contents describe how things are, or prescribe how they are to be made.

**Values**: `"describes"` (Searle's word-to-world fit: reports, beliefs, predictions, conditions, possibilities) and
`"prescribes"` (world-to-word: orders, requests, promises, intentions, wishes, permissions, prohibitions). Default
`"describes"`. (The report's first draft said `"world"` and `"word"`; Searle's own names are easily read the wrong
way round, so these say what they mean.)

**Why two values are enough.** Searle has two more classes, declarations (which make their content so by saying it:
appointing, excommunicating) and expressives (which presuppose it: thanking, lamenting, apologising). The content
of both is simply true, so it is nested with no space and asserted; neither needs a space.

**How it would be used.**

- *Fulfilment* (comparison): a `"prescribes"` statement against a later `"describes"` one of the same contents is a
  question of fulfilment, not of agreement: carried out (`1`), not carried out (`-1`), reportedly carried out (`0`,
  leaning for). A prescription of a "not" goes the other way round (done is a breach), and a permission, being a
  possibility, is used or not, never carried out or breached. Phase 12 leaves all of this out.
- *Time*: what is prescribed comes after the prescribing, so its date (if any) is of a plan.
- *The interface*: "Carried out by…" on an order's page, as "Similar" is on every item's.

```python
class Directive[T](SemanticSpace[T]):
    _meta = SemanticSpace.Meta(abstract=True, fit="prescribes")


class Ordered[T](Directive[T]):
    """What someone was ordered to do (and did not necessarily do)"""


class Requested[T](Directive[T]):
    """What someone was asked to do"""
```

### `logical`

**What it says.** Whether the space is an operator of standard logic, and which: a negation, or a modal. A modal is
given as formal semantics gives it (Kratzer), by two things:

- its **force**: the contents hold in every situation of some kind (*necessity*: "must") or in at least one
  (*possibility*: "may", "might");
- its **flavour**: what kind of situations those are. What is known (*epistemic*: "he must have been there", "he
  might have been there"); what a law or an authority allows (*deontic*: "he must pay", "he may leave"); what is
  possible at all (*alethic*).

The same word changes its meaning with the flavour ("must" in "must have been there" and in "must pay"), and the
rewrites that normalising uses hold only within one flavour: which is why `logical` needs both.

**Values**: `"not"`; or `Modal(force, flavour, of_not=False)`, where

- `force` is `"necessity"` or `"possibility"`;
- `flavour` is the project's own word (`"epistemic"`, `"deontic"`, `"alethic"`, or a narrower one, such as
  `"canon law"`). It is only ever compared with another space's flavour, so it is not a list the core keeps, and a
  new flavour needs no change to the core;
- `of_not=True` makes the space the modal of the *negation* of what it holds: a prohibition is a deontic necessity
  of not.

Default `None`: an attitude (belief, knowledge), a speech act (an order, a promise, a report) or a condition is not
an operator of logic. (The report's first draft had a yes or no, and then six names: `"necessary"` and `"possible"`,
which were the alethic flavour, and `"obligatory"`, `"permitted"` and `"forbidden"`, the deontic one. That left out
the flavour sources use most: the epistemic "might have" of the demo's own `Hypothetical`, "The source says it might
have been so".)

```python
class Not[T](SemanticSpace[T]):
    _meta = SemanticSpace.Meta(logical="not")


class Might[T](SemanticSpace[T]):
    """The source says it might have been so"""

    _meta = SemanticSpace.Meta(logical=Modal("possibility", "epistemic"))


class Must[T](SemanticSpace[T]):
    """The source says it must have been so"""

    # (whether "must have" commits the source to it is the project's call: below)
    _meta = SemanticSpace.Meta(logical=Modal("necessity", "epistemic"), veridical=1)


class Deontic[T](SemanticSpace[T]):
    _meta = SemanticSpace.Meta(abstract=True, fit="prescribes")


class Obligatory[T](Deontic[T]):
    _meta = SemanticSpace.Meta(logical=Modal("necessity", "deontic"))


class Permitted[T](Deontic[T]):
    _meta = SemanticSpace.Meta(logical=Modal("possibility", "deontic"))


class Forbidden[T](Deontic[T]):
    _meta = SemanticSpace.Meta(logical=Modal("necessity", "deontic", of_not=True))
```

**What follows from force and flavour**, checked at `initialise()`:

- **Veridicality.** A possibility never commits the source to its contents ("might have" is not "did", "may leave"
  is not "left"), so a possibility is always `0`, and anything else set on it is refused. A necessity commits the
  source only when its flavour is of what is actually so, what is known or what is necessarily so (a "realistic"
  flavour, in Kratzer's word); a deontic necessity never does ("must pay" is not "paid"). A flavour being only the
  project's word, the core cannot tell which flavours are realistic: the project says so by `veridical=1` on the
  class (`-1` on a necessity `of_not`, such as a `CannotHaveBeen`), and the default is `0`. `"not"` is `-1`, and
  anything else set on it is refused.
- **One operand.** `"not"` and a modal `of_not` are downward monotone, so `unary=True` follows.
- **Fit** does not follow (a flavour is only a word): it is set on the family, as on `Deontic` above.

**How it would be used: normalising**, on the comparison's copy of a path, never on what is stored. In the table,
`N_f` is a necessity of the flavour f and `P_f` a possibility of the same flavour:

| Written | Read as | For example |
|---|---|---|
| `Not[Not[p]]` | `p` | |
| `Not[N_f[p]]` | `P_f[Not[p]]` | not obliged to pay = permitted not to pay |
| `Not[P_f[p]]` | `N_f[Not[p]]` | cannot have been there (`Not[Might]`) = must not have been there (`Must[Not]`); not permitted to import = obliged not to import |
| a modal `of_not` of `p` | the same modal of `Not[p]` | forbidden to import = obliged not to import |

So "it was forbidden to import copper" and "it was obligatory not to import copper" compare as one claim, and "it
cannot have been Paul" as the claim that it was not Paul (what that does to a comparison is under
[How it works with similarity](#how-it-works-with-similarity)). Two limits:

- **Only within one flavour.** What canon law does not permit is not thereby forbidden by a city's statutes: two
  modals of different flavours are never rewritten into each other.
- **Only between spaces next to each other.** `Not[GrantingPermission(..., content=Permitted[p])]` says that a
  permission was not given, which is not that p was forbidden: the statement between them stops it.

### `unary`

**What it says.** That the space holds exactly one item.

**Values**: `True` or `False`; default `False`. Set by `logical="not"` and by a modal of a negation
(`Modal(..., of_not=True)`), and by hand on any other downward monotone space (`Doubted`, `Refused`).

**How it would be used.**

- *The models*: `Create` refuses a second item, as `Annotated[list[T], MinLen(1), MaxLen(1)]` does on the
  library's `Identification.target`, with a message that says why ("`Not` takes one statement: not (A and B) is not
  (not A) and (not B); use one `Not` for each").
- *Comparison*: the items of a space that is not unary are compared one by one; see
  [`operand_cardinality`](#operand_cardinality) for why that is sound for the others and not for these.

## The two sets side by side

Each of the file's spaces, by ChatGPT's fields and by the report's. A blank is the default.

| Space | Family | Operator | Status | `veridical` | `fit` | `logical` | `unary` |
|---|---|---|---|---|---|---|---|
| `Negative` | polarity | negation | denied | `-1` | | `"not"` | yes |
| `Possible` | alethic | possibility | possible | `0` | | possibility, alethic | |
| `Necessary` | alethic | necessity | necessary | `0` (a project may say `1`) | | necessity, alethic | |
| `Hypothetical` | alethic | hypothesis | assumed | `0` | | | |
| `KnownContent` | epistemic | knowledge | factive | `1` | | | |
| `BelievedContent` | epistemic | belief | believed | `0` | | | |
| `DoubtedContent` | epistemic | doubt | doubted | `0` | | | yes |
| `HeardContent` | evidential | hearing | heard | `0` | | | |
| `ReportedContent` | evidential | reporting | reported | `0` | | | |
| `PredictedContent` | predictive | prediction | predicted | `0` | | | |
| `DesiredContent` | desiderative | desire | desired | `0` | `"prescribes"` | | |
| `IntendedContent` | intentional | intention | intended | `0` | `"prescribes"` | | |
| `DirectiveContent` | directive | directive | directed | `0` | `"prescribes"` | | |
| `Commitment` | commissive | commitment | committed | `0` | `"prescribes"` | | |
| `IfCondition` | conditional | conditional antecedent | conditional | `0` | | | |
| `ObligatoryContent` | deontic | obligation | obligatory | `0` | `"prescribes"` | necessity, deontic | |
| `PermittedContent` | deontic | permission | permitted | `0` | `"prescribes"` | possibility, deontic | |
| `ProhibitedContent` | deontic | prohibition | prohibited | `0` | `"prescribes"` | necessity of not, deontic | yes |
| `KnownAbout`, `HeardAbout` | epistemic, evidential | awareness, hearing | topic | — | — | — | — |

The last row has no values because it holds an entity, not a proposition: as the report says, a relation. A modal
is written by force and flavour: "necessity, deontic" is `Modal("necessity", "deontic")`. The file's
`Hypothetical` is an assumption made for argument's sake, not a modal; the demo's `Hypothetical` ("might have") is
an epistemic possibility.

What the table shows:

- **ChatGPT's status is a name for the report's values.** Read across, every status is a pair of `veridical` and
  `fit` (and `logical` where there is one), plus which class it is. What a reader *acts on* is the pair; the name
  is for people.
- **Its family is the class hierarchy**, and its operator is the class, except for negation and the modals, whose
  force and flavour `logical` holds. A modal's flavour is the one part of a family that logic needs.
- **Its `operand_cardinality` is `unary`**, with the reason (monotonicity) that says which spaces need it.
- **The report's four do not say what the spaces are called**, which is why a project's `Charged` or `Feared` needs
  no change to the core: it is a class with two or three values.

| | ChatGPT's four | The report's four |
|---|---|---|
| A reader can decide by them alone | No (needs a table from operator or status to behaviour) | Yes |
| A new kind of space | A change to the core's enums | A class |
| Normalising | Yes, by the operator | Yes, by `logical` |
| A word for the reader | Yes (status) | No (the class's name and docstring) |
| Composes along a nested path | No (its own table reads `DirectiveContent[Negative[Journey]]` as "directed and denied", two labels side by side) | Yes (the walk under `veridical`) |
| Inherited, checked, exported | Yes | Yes |

**Decided** (the user, 2026-11-24): the report's four. ChatGPT's are not taken, and not beside them either: where
the two sets overlap they would have to be kept in step by hand (a status against `veridical` and `fit`, an operator
against `logical`, a cardinality whose default is the opposite of `unary`'s), for nothing a program needs.

## One example, through every reader

The manmax model's own example of an order not carried out: "Paul von Liechtenstein had been commissioned by KM to
purchase several regiments and suits of armor from the Italians, but since he was unable to receive the necessary
funds, the purchase had to be cancelled". Beside it, a second report **made up for this example**: another source
says Paul bought armour from Italian merchants later that year. The models are an illustration in Pangloss's
terms, not a design for a port.

```python
class Order(Statement):
    issuer: Annotated[Agent, Holder()]            # Holder and Addressee: proposed markers (below)
    recipient: Annotated[Agent, Addressee()]
    content: Ordered[Statement | Not[Statement]]


class Purchase(Statement):
    buyer: Agent
    sellers: list[Agent]
    things: list[PhysicalObject]
```

| Statement | Path (`meta.semantic_spaces`) | Holder (`context_labels`) | `veridical` | `fit` |
|---|---|---|---|---|
| **a** The order (factoid 1) | `[]` | — | `1` | describes |
| **b** The purchase ordered (in a) | `["Ordered"]` | a, KM; addressee Paul | `0` | prescribes |
| **c** The purchase cancelled (factoid 1): `Not[Purchase]` | `["Not"]` | — | `-1` | describes |
| **d** The purchase in the other source (factoid 2) | `[]` | — | `1` | describes |

What each reader makes of it:

- **Comparison.** b against c: prescribed and not done, **not carried out** (this is the manmax class
  `orderednotcarriedout`, worked out rather than chosen). b against d: done by the addressee, after the order,
  **carried out** (if d is the same purchase). c against d: one says it did not happen and one that it did,
  **they contradict**, which is the pair worth a scholar's look. (Phase 12's call c, "two statements of one
  factoid are never a pair", is right for duplicates and wrong for fulfilment: b and c are in one factoid.)
- **Derived rules.** A rule "buyer traded with seller": from d a plain fact; from b, by default, a qualified one
  (`0`); from c nothing (`-1`, blocked).
- **The graph part.** As now, by `FastRPMeta` on each space; the report's open question (whether `stop` on `Not`
  keeps c's people apart) is unchanged.
- **The time part.** b's date, if the order set one, is when the purchase was to be made; c's, when it did not
  happen. Neither would count for when Paul was active.
- **The RDF export.** d's triples are asserted; b and c are in their spaces, not asserted (as today).
- **Search.** "Purchases by Paul that the sources assert" (`"$asserted": true`) finds d only.
- **The interface.** b and c are marked as not asserted wherever they are listed; the order's page could have
  "Carried out?" with c and d.

## How it works with similarity

Similarity in Pangloss is two things ([the report](semantic-spaces-formalisation.md#spaces-in-statement-similarity)):
the **vectors** (`pangloss-vectors`, built: the items nearest to one, by the class, graph, name and time parts) and
**comparison** (`pangloss-compare`, phase 12, written and not built: pairs of statements that may tell of one event,
and a verdict on each pair). The four fields leave the first alone and decide most of the second.

### Contents find, spaces decide

1. **Candidates come from the contents alone.** A statement inside a space is a document with its own vector and
   its own fields, so `nearest` and phase 12's pairs by rule find it as they find any statement. Nothing in the four
   fields changes a cosine: a denial is as near to what it denies as a second report of it, and that is the pair most
   worth finding. (Phase 12's rule that two statements of one factoid are never a pair holds for one event told
   twice, not for fulfilment: an order and its failure are often told together, as b and c are
   [above](#one-example-through-every-reader).)
2. **Each statement of a pair gets a signature** from its path (`context_labels`, already on the node): the path
   normalised (the table under [`logical`](#logical)); its `veridical` and, when that is `0`, which way it leans, by
   [the walk](#veridical); the `fit` of the innermost space
   that prescribes, if there is one; the holder and the addressee of the statement holding that space; and, for a
   modal, its flavour, with the authority (the holder) for a deontic one. Nothing more is read from the database: the
   path is on the node, and the fields are on the classes, in memory.
3. **Phase 12's verdict on the contents stands as it is written**: whether the two are one event (its hand-set
   logistic of the gap between the dates, the place, the people in common), and which fields agree.
4. **The two signatures make that verdict a relation:**

| This statement | The other | Relation |
|---|---|---|
| asserts p (`1`) | asserts p | one event told twice: they agree, or disagree on the fields (phase 12 as written) |
| asserts p | denies p (`-1`) | **contradiction** |
| asserts p | not committed (`0`: a report, a belief, a "might have"), leaning for p | support |
| asserts p | not committed, leaning against p ("it was reported that he did not") | tension |
| denies p | not committed, leaning for p | tension, never a contradiction ("might have" is consistent with "did not") |
| denies p | not committed, leaning against p | support |
| not committed | not committed | compatible when they lean the same way, at odds when not (two reports that differ: where news changed as it spread) |
| prescribes p as a necessity (ordered, obliged, promised, intended) | asserts p, later, by the addressee | **carried out** (by another, or before: done, but not carried out) |
| prescribes p as a necessity | denies p | **not carried out** |
| prescribes not p (ordered not to, forbidden) | asserts p, of the one it applied to | **breach** |
| prescribes not p | denies p | complied with |
| permits p (a possibility) | asserts p | done, as allowed: a permission is used or not, never carried out or breached |
| any prescription | not committed | reportedly carried out, or reportedly not, by its lean |
| a necessity of p | a necessity or a possibility of not p, of one flavour and one authority | **conflict** (ordered and forbidden; obliged, and permitted not to). Two possibilities never conflict |
| a prescription | a prescription of another flavour or another authority | two orders at odds (a dispensation under canon law against a ruler's prohibition): shown as that, not as a conflict |
| leaning neither way | anything | nothing: it says nothing of p |

Force counts here as much as in normalising: a permission and an order of the same thing are different relations to
what happened, and only within one flavour can two prescriptions conflict at all.

5. **A strength**, so that a list can be ordered: the likelihood of one event (phase 12's) times how far each side
   commits, a weight for each space class (an order counts for more than a recommendation, a report more than a
   rumour). The weights are hand-set in compare's own slot at first, and learnt from people's judgements later
   (step 12.9), with the pair of signatures among the features.

### What each part of the vectors does

- **The class part**: nothing. A space is not a class of item.
- **The graph part**: `FastRPMeta` on each space, as now. A default weight could come from `veridical` (asserted at
  1, not asserted lower, denied: the open question of `stop`), measured before it is chosen.
- **The time part**: a date counts only on a statement whose path is `1` (the open item of step 9.3).
- **The name part**: nothing.
- **A "context" part**: not made. It would push a denial away from what it denies.

### In the interface

The "Similar" section keeps its order, by content, and each statement in it is labelled by its relation to this
one: "contradicts", "carried out", "reported", "might have". Filters: "only what the sources assert" (`veridical`
`1`) and "only contradictions". Phase 12's "Compared" section (step 12.7) shows the relations of the table, and an
order's page "Carried out?".

### An illustration

Statement d of [the example](#one-example-through-every-reader) (Paul bought armour from Italian merchants), and one
more, e, **made up** as d was: a chronicle says "it cannot have been Paul who bought it", written
`Not[Might[Purchase(buyer=Paul)]]`. The scores are invented, to show the shape.

| Similar to d | Score, by content | Path | Relation to d |
|---|---|---|---|
| c, the purchase cancelled | 0.91 | `Not` | contradicts d, if they are one event |
| b, the purchase ordered | 0.88 | `Ordered` (KM to Paul) | d carries it out |
| e, "cannot have been Paul" | 0.86 | `Not[Might]`, read as `Must[Not]` | contradicts d, if one event and the project's `Must` commits the source; otherwise tension |

e is where force and flavour count. Read without them, `Not[Might[p]]` turns the walk negative at `Not` and then
meets a space, so e would say nothing of p and be listed as merely near. Normalised within its flavour, it is
`Must[Not[p]]`: the chronicle's claim that it was not Paul. The same holds of the deontic flavour: "not permitted to
import" against "imported" is a breach, which "not obliged to import" is not.

## How to explain it to people

For the people who enter and read the data, not for those who write the models: they never meet the four fields,
or the words "semantic space".

### In a paragraph

> Everything in the database is what a source says. A statement on its own is something the source says happened.
> When the source says that someone ordered, asked for, promised, intended or allowed something, choose that kind
> of statement, and put what was ordered (asked for, promised...) inside it as a statement of its own: the database
> knows that what is inside did not necessarily happen. If the source says that something did *not* happen, mark it
> "not"; if it says that it might have happened, mark it "perhaps". How sure *you* are of your reading is something
> else, and has its own place.

And what it gives them, which is the reason to take the trouble:

> Because of this, the database can show you where two sources contradict each other, whether an order was carried
> out or a promise kept, and which reports rest only on hearsay, without your having to look for them.

### When the kind of statement decides the space

The user's question: if a statement such as an order brings its space with it, is there less for people to
understand? **Yes, nearly all of it goes.**

- **The statement type carries the space.** `Order.content` can hold only `Ordered[...]`, so there is nothing to
  choose: a person picks "Order" because the source tells of an order, and fills in "what was ordered" with another
  statement. They never pick a space, and never need to know there is one. Of the manmax model's 62 fields that
  hold statements, 41 hold something not asserted; with the space fixed by each field's type, nearly all of them ask
  nothing new. The few that can go either way (a reason asserted or only alleged, an oath that promises or one that
  affirms) offer that one choice, where it arises.
- **What is left to choose is small**: "not" inside an order or a promise (ordered *not* to, promised *not* to),
  and at the top of a factoid "not" and "perhaps" (and "reportedly", if a project wants it). Two or three choices,
  where ChatGPT's file had a vocabulary of twenty spaces.
- **The finer distinctions come from words people already use.** Whether something was known, believed or heard is
  the choice between the statement types "Knowing that", "Believing that", "Hearing that", each of which brings its
  space, and people make it by what the source says. That is easier to make the same way twice than a choice
  between abstract categories, which answers the report's worry about consistency
  ([Is it viable](semantic-spaces-formalisation.md#is-it-viable)).
- **Force and flavour stay out of sight too.** "Might have" and "must have" are two choices with plain names; that
  one is a possibility and the other a necessity, both epistemic, is the model's business.

Three things still need saying, because they are easy to get wrong:

1. "Not" is the source saying it did not happen; leaving a statement out says nothing.
2. "Perhaps" is the source hedging, not the person entering it: their own doubt goes in the certainty of a field.
3. A reason held by a punishment or an imprisonment is what was alleged, unless the source asserts it (where a model
   has `Alleged`, the form offers it there, and only there).

### What the interface would need

- **A space that is a field's only option drawn without its head bar** in the form: in a field that can hold that
  space and nothing else, one of it, and must. `InterfaceMeta(headless=True)` does this today for reified relations
  only (`schema/headless.ts`); extending it to spaces is a small change, not made.
- **"Not" as a toggle** on a statement, where a field offers `Statement | Not[Statement]`, rather than a section of
  the type menu (`TypeMenu` gives each space a section of its own today).
- **What it means stays visible**: a statement inside a space keeps its band and colour in views (as now), and its
  relation in "Similar", so that a reader sees at once that an ordered purchase is not a purchase.

## Negatives that record a relation

Added 2026-11-24 from a discussion with the user, who agreed with its conclusions. It is not a field of
`SemanticSpaceMeta`: it belongs to each negative statement, and a person judges it. **Nothing here is built**, and
the implementations at the end are options, each the user's to choose.

### The gradient

A negative statement can be anything from news to nothing:

- "Maximilian did not attend the chapter of the Golden Fleece" (the manmax model's own example for
  `absencefromevent`): he was the Order's sovereign and expected there;
- "Maximilian did not meet the pope on that day": a meeting was possible, and the negative may even come from a date
  set wrong;
- "Maximilian did not know Zarglqwargl, an alien from Mars": true, and empty.

What runs along it is how **live** the positive was: how expected, or at least possible, it was that it would
happen. ChatGPT's file had this as `NegationAssessment` (`positive_feasibility`, `opportunity`,
`expectedness_of_positive`, `confidence_in_negative`). This section keeps the idea and changes three things: where
it lives, what is asked of people (one judgement), and that much of it can be worked out from the data.

In terms of information, a negative tells as much as its positive was likely: learning "not p" when p had a
probability P is worth −log₂(1 − P) bits, nothing when P is 0 and 3.3 bits when it is 0.9.

**It is not confidence.** Whether the negative holds at all ("the date could be wrong") is a second axis: the
certainty a project records already (the manmax model has `certainty` on every statement). A negative can be both
informative and doubtful, so the two are kept apart, as ChatGPT's file kept them.

### A relation, virtual rather than actual

The user's point: a source that says "X did not meet Y" still records a relation between them, real but virtual
rather than actual (in Deleuze's sense), when it stands in a structured space in which the meeting was possible.
Zarglqwargl is not even remotely possible, and so is no relation between two persons.

Deleuze's own distinction sharpens it. The virtual is not the possible: the possible is the real less its existence,
while "the reality of the virtual is structure" (*Difference and Repetition*, chapter 4). What makes the
non-meeting a relation is not that a meeting was logically possible (a meeting with an alien is, thinly,
conceivable), but that X and Y are already joined in a structure (offices, alliances, itineraries, letters) in which
it was a live tendency. Zarglqwargl fails twice: nothing joins him to Maximilian, and there is no second person.

Three consequences:

- **Liveness, information and relation go together**: where the positive had no chance, the negative tells nothing
  and records no relation; the more live the positive, the stronger the virtual relation.
- **A source's negative is evidence that the positive was live**: people negate what is at issue (Givón, Horn on
  negation), so a source that bothers to say it shows the meeting was live for it. The empty negative hardly occurs
  in sources; it comes from a researcher's own entries.
- **It is not only negation**: an order, an intended journey, a planned marriage and a promise hold virtual relations
  too. The signature of a path says which kind (denied, prescribed, reported), liveness how strong.

### When the expectation has grounds: "X did not fight in battle Y"

The user's example, a real one. X was in the army, and the army fought at Y: X is expected to have fought; he was
nearby, so he could have; he did not.

1. **A default, defeated.** The structure implies by default (what follows unless something says otherwise) that X
   fought, and the negative defeats it. The virtual relation is the defeated default, and the gradient is how strong
   the default was. Its parts are those ChatGPT named, expected (in the army), opportunity (near the field) and
   feasible (alive, free), but here they can be read off other statements instead of judged from nothing.
2. **It works backwards.** A source says X did not fight only if he was expected to, so the negative presupposes its
   grounds: it is evidence that X was with the army and near the field, even where nothing else records it. That
   justifies suggesting those statements for a person to confirm, never asserting them.
3. **Its reach is the event's.** A battle has many participants, so a virtual relation to Y joins X, through Y, to
   everyone who fought there: his would-be comrades and his enemies. In "who belonged to the same structure" X stays
   with his army; in "who actually fought together" he drops out. Notable absences are where the two networks part.
4. **It makes X the exception**, and an exception calls for an explanation: illness, capture, disgrace, the reserve,
   treachery. Sources often give it, and a conjunction (the demo's `Causes`) joins the reason to the negative.
   Historically an expected commander's absence may matter more than one more man fighting: that is its
   significance, which is not its weight in similarity.
5. **Scope decides what is virtual.** "Did not fight in battle Y" may deny that he was there, or only that he fought.
   Negating his participation as a combatant denies the two together, not his presence. Where the source says he was
   there, that is asserted: the relation to Y is actual, and only the fighting is virtual. The manmax model has the
   grain for it: `participationinevent` has a `Role_in_event`, and `roleinevent`'s own example is serving as a
   commander in a battle.

### Live for whom

A source's denial is live in the source's world (it may be refuting a rumour); the historian may judge the positive
never possible at all. A computed expectation (below) rests on the historian's data, and so is the researcher's; the
source's own shows in its having said it, and sometimes in its words ("contrary to custom"). **Open** (decision 7):
one gradient, the researcher's, or the source's beside it.

### Possible implementations

None chosen. Three questions, each with its options and the one proposed.

**Where the judgement lives:**

| Option | What | For | Against |
|---|---|---|---|
| **A citing document** (proposed, for the researcher's) | `Expectation[T]`: `statement: Cites[T]`; `how_expected`, one of five steps: impossible, unlikely, possible, likely, expected; `grounds: list[Cites[Statement]]`, the statements it rests on; a note. Ready-made in `pangloss-library`, beside `Identification` | Several scholars, each with their own, each with its history and review; the source's factoid is not rewritten; "changed since cited" says when the statement or a ground has changed since | One more document to make; a reader that wants the value (the graph part) has to look it up |
| A field of the negative's space (for the source's own, if decision 7 wants it) | `Not(expected=...)`: what the source itself says of it, "contrary to custom" | It is what the source says, so it belongs in the factoid, read like any property | One value, and not the researcher's |
| A field of the statement, beside its certainty | As the manmax model keeps `certainty` | The simplest to enter | The researcher's judgement inside the source's factoid, which [the report](semantic-spaces-formalisation.md) argued against |

The five steps are an ordinal scale with no "unknown" (an expectation not judged is simply not there), mapped to
numbers by a setting wherever a number is needed.

**How the expectation is proposed**, so that a person confirms instead of judging from nothing:

| Option | What | For | Against |
|---|---|---|---|
| **Rules of the project** (proposed) | `pangloss-derived` rules that derive an "expected at" relation: a member of a group that fought at an event is expected at it; a knight of the Order is expected at its chapters. A derived fact keeps what it rests on (its justifications), and those are the grounds | Explicit and explained; the project's own expectations; kept current by derived's worker | A rule for each kind of expectation; nearness in time is a condition of the rule (derived has `within` and `overlaps` for dates) |
| **A guard of feasibility** (proposed, with the rules) | Impossible when a lifespan does not reach the date (from `pangloss-dates`' bounds), or when the other is no real entity (a stand-in, or a class the project marks as fictional) | Finds the empty end with nobody judging | Covers only that end |
| Features by hand | Lifespans; being in the same place within a window (the project's statements of where someone was, named by a marker); membership: a logistic set by hand, as phase 12's verdict is, then learnt | Needs no rules | Needs a marker for "where someone was"; places compare only as the same or not (no distances yet) |
| Link prediction | The cosine of X's and Y's vectors (an event has a vector too), calibrated by `pangloss-learn` against pairs that are asserted | Needs nothing declared | Opaque; circular unless the vectors come from a graph without the negatives (the actual network, below); needs data to calibrate |

The expectation is worked out when the statement is shown, offered as a suggestion, and stored only when a person
confirms it (as an `Expectation`), so nothing churns.

**How it is used:**

- **The graph part**: a negated statement's joins are weighted by its liveness, and the empty end joins nothing.
  FastRP already takes weights from the data, not only from the model (the shares of a `SumsTo`, read from each
  edge); this one comes from a citing document (looked up as the reader already reads citations) or from the space's
  field. A negative not judged: as today, or a setting (decide).
- **Two networks**: the actual one (what is asserted: a node whose path is not `1` joins nothing, which needs the walk
  of phase 3 in the graph's reader) and the structural one (virtual relations at their liveness), as two graph parts
  that profiles choose between (`who_met`, `who_belonged`). A second part costs a second rebuild and refresh.
- **Comparison**: a contradiction between a denial and an assertion weighs by the denial's liveness, and "expected,
  and did not" is a relation of its own (a notable absence).
- **Suggesting the grounds**: a negative whose expectation has no grounds in the data suggests them ("X was with the
  army that fought at Y") for a person to confirm, as Pangloss's toolchain suggests identifications. A suggestion of
  a statement is new: today only an entity can be suggested.
- **The interface**: on a negative, "How expected was it?" in five steps, with the computed reasons as chips; on an
  event's page, who was expected and was not; on a person's page, notable absences; in review, a negative judged
  impossible ("worth recording?").
- **Scope** is a rule for modellers (negate the role, not the presence, when the source says he was there), in the
  guide; in the form, "not" toggled on a participation with a role could ask "was not there" or "was there, but not
  as …".

## Derived edges through spaces

Added 2026-11-24, and measured on the demo's database (read only: the scripts are in `/tmp/space-check/`, not in the
repository). **Nothing here is built.**

### What derived does with spaces today

From `pangloss_derived/compile.py`, `store.py` and `declare.py`:

- Each match of a rule is a **justification**, which records what it passed through: the spaces stored on each node a
  pattern matched (`meta.semantic_spaces`) and the wrappers on each relation path between them.
- Each wrapper class says what it does (`DerivedMeta(derivation=...)`): a space **qualifies** by default, a reified
  relation or a conjunction is **transparent**, and any may **block** (a blocked space is tested against the stored
  list of each matched node too).
- A fact is **plain** when one of its justifications passed through nothing that qualifies; otherwise it is
  `qualified_only`, with the labels of them all.
- A **document rule** takes no qualified justification unless it allows the space; a document it makes carries
  `derived_context`, which is inherited down a chain.
- The RDF export asserts plain facts only, `graph --plain-only` exports them only, and the graph part of the vectors
  reads no derived edge at all.

So derived already keeps something like the user's virtual relations (a fact from inside a space, qualified), but it
cannot tell a denial from a report from an order: a space is "qualified" or it is not.

### The fault reaches derived

Derived reads the stored lists, so [the fault](#a-fault-in-how-spaces-are-recorded-today) changes its facts. Two more
shapes were tried (`/tmp/space-trial/test_leak_shapes.py`):

- `Causes(cause=Negative[C], result=R)`: R, which the source asserts, is recorded as inside `Negative`. A fact from R is
  qualified "Negative", and none is derived at all where a project blocks `Negative`.
- `Causes(cause=Order(thing_ordered=Wished[W]), result=R)`: the order's space, nested inside the cause, reaches R, and a
  fact from R is qualified as wished.

The graph part is not affected: it walks the edges, never the stored lists.

**On the demo**: its models have four classes with two or more single relations to nodes of their own (`Causes`,
`ChildOf`, `Order`, `Transfer`), and one shape that leaks: a `Causes[Statement, Statement]` whose cause is an `Order`,
since `thing_ordered` is a single relation holding a space. Its data has no such factoid: in the 9 documents that hold
a space, the 57 nodes are stored as the algorithm gives them, and none of their spaces would change were the fault
fixed.

**The fix can be narrower than copying the lists.** What the sharing is for showed in the demo's one `Causes`: its
result (`Transfer` "Charlemagne's gifts") has its cause (`Activity` "The people acclaim Charlemagne") in its context,
because the two share the lists a single relation is given. Copying them, as a list item's are, would take that away
(the result would have no context at all). Instead: **a space adds itself to new lists for what it holds, never to
the lists it was given.** Tried: every shape is mended (the threat's consequence is in `Committed` only, the two results
above in nothing), the result keeps its cause in its context, and on the demo every one of the 154 nested nodes of its
45 documents comes out as it is stored. So the fix changes nothing in the demo's data, and in a project's only the
nodes the fault got wrong.

### What the four fields change

1. **A default from `veridical`** (plan step 4.1): asserted spaces read through, uncommitted ones (reports, beliefs,
   orders) qualified as today, denials blocked. A space's own `DerivedMeta` still wins, and a project that sets no
   field sees no change.
2. **Decided by the path, not by each wrapper.** Each wrapper on the path is judged by itself today, which gets
   compositions wrong: `Not[Not[p]]` gives a fact qualified twice, where [the walk](#veridical) says p is asserted
   (plain); `Not[Known[p]]` ("it is not known that p") gives a qualified "p", where the walk says the source says
   nothing of p (no fact). For the walk, derived has to read the matched nodes' `context_labels`, which show where the
   statements are between the spaces, and not only the flat list.
3. **A status, not only "plain".** Each justification would say how it holds: asserted, denied, uncommitted leaning
   for or against, prescribed, or saying nothing. A fact could then say "traded with: asserted by two, denied by one",
   a contested edge: a cheap counterpart, for each relation, of comparison's contradiction. `plain` stays, meaning
   "has an asserted justification".
4. **Both cases.** A space round the matched statement (derived from a statement in a space), and a space on the
   relation path itself (`participants: list[Person | Not[Person]]`, "Y was not among them"). The second is not the
   case called a mistake in [the report](semantic-spaces-formalisation.md#faults-in-the-proposal) (an entity as the
   content of an attitude, `KnownAbout`):
   here the space qualifies the relation the path is, which can be so or not.

### Virtual relations in derived

- **A positive edge class should mean the positive**, so a denial blocks it.
- **Virtual relations are edge classes of the project's own**, derived on purpose from denied or prescribed contents
  ("expected but absent", "was ordered to give to").
- **Liveness is a value of each justification**: derived has the marker for it (`PerJustification()`), so a graph of
  virtual edges can weigh them by liveness rather than by how many justifications they have.
- **The two networks are in derived too**: who actually met (asserted edges), and who belonged to the same structure
  (asserted edges with the virtual ones, weighed).
- **The battle** as rules: "a member of an army that fought at Y is expected at Y"; the denial blocks his "fought
  alongside" edges; the expectation and the denial together are a notable absence, which a rule could derive
  (whether a rule can read another rule's edges, or needs the expectation as a derived document, is to be found
  out). Scope works the same way: denying the combatant role leaves his asserted presence deriving "was at Y".

### In the demo's data

Of the demo's 34 `GaveTo` edges (the rule `Transfer__GaveTo`): 10 are plain; 20 are qualified by `WeightedAlternative`
(an alternative, not a space: the library's `DerivedMeta` makes it qualify, and the fields leave it as it is); 3 come
from gifts that were ordered (`PositiveSubjunctive`); and 1 from a gift that was forbidden (`NegativeSubjunctive`):
"The Frankish army" gave to "The Roman Church", from the factoid "Charlemagne orders gifts, and forbids a trade".
Today all four are "gave to" edges, qualified; the last is a "gave to" made of a forbidding.

With the fields, the three ordered gifts are prescribed, leaning for: a virtual relation ("was to give to"),
qualified as now but saying why. The forbidden one is prescribed, leaning against, and leaves `GaveTo`: blocked, or a
virtual "forbidden to give to" of its own.

The demo's two subjunctives pack "prescribed" and "not" into classes of their own, and the four fields can describe
them as they are, without a migration: as the demo uses them (inside an order) they are commands,
`Modal("necessity", "command")` and `Modal("necessity", "command", of_not=True)`, each with `fit="prescribes"` and
never veridical. Splitting them into `Ordered[Statement | Not[Statement]]` (decision 8) would be a migration. Every
space of the demo holds one item, so `unary` (which follows from `of_not`) refuses nothing that is stored.

### What `pangloss-derived` would need

- The matched nodes' `context_labels` read beside their `semantic_spaces`, so that the walk sees the statements
  between the spaces (`compile.py` reads only the flat list).
- Each justification's status from the walk (`pangloss_models.spaces.signature`, phase 3 of the plan), over the
  matched node's path and the wrappers on the rule's own paths.
- The derivation from the status (asserted: through; uncommitted or prescribed: qualified; denied, or leaning
  neither way: blocked), unless a wrapper's own `DerivedMeta` says otherwise.
- The status kept on each justification and summed up on the fact (asserted, contested, reported, prescribed, denied
  only), with `plain` kept.
- A rule option to take only justifications of a status, to derive virtual edge classes from denied or prescribed
  contents.
- Liveness as a `PerJustification()` value.
- After the fault is fixed, the heads it mends marked as written, so that their facts are found again.

## The manmax model as an exercise

The file could be read (`https://raw.githubusercontent.com/acdh-oeaw/apis-instance-manmax/main/model_config.json`,
768 kB): **222 classes**, 151 statement types, 70 entity types and `unreconciled`. Of the statement types, **51 hold
other statements, in 62 fields**, and **46 of those fields accept any of the 151 types**. There are no semantic
spaces; four other things do their work:

1. **A class for each operator with its content.** `absencefromevent` and `absencefromplace` are "not" with a
   participation or a stay; `negativeorder` is an order of a "not"; `orderednotcarriedout` is an order *and* the
   assertion that it was not carried out; `apologyfornonattendance` is an apology for a "not". With a `Not` space
   each is a `Not` round the positive class, and the comparison of "absent" with "present" needs no rule of its own.
2. **Polarity in the names of fields.** `threat` has `positive_cause`, `negative_cause`, `positive_consequences` and
   `negative_consequences`, and its description says "PAY VERY CLOSE ATTENTION TO WHICH FIELDS YOU USE!". With `Not`
   it is a condition and a consequence, each `Statement | Not[Statement]`.
3. **One bit for "not asserted"**: `head_statement`, as above.
4. **The holder in a field of each class, under its own name**: `Befehlsgeber` and `Befehlsempfänger` (order),
   `Bittsteller` (request), `Versprechen_gebende_Person` (promise), `Person_die_das_Vorhaben_ausdrückt` (intention),
   `person_threatening`; and a proxy, `personwithproxy`, a reified relation.

### The 62 fields, by what they do to what they hold

| | What the field holds | Fields | `veridical` | `fit` | Examples |
|---|---|---|---|---|---|
| A | Parts or results, asserted | 4 | `1`, no space | describes | `churchservice` parts, `musicperformance` parts, the occupation an `election` or `assignmenttorole` results in |
| B | A statement presupposed, usually asserted in its own factoid | 8 | `1`, a citation | describes | `acceptanceoforder` (the order), `cancellationofdebt` (the debt), `resignationfromrole`, `settlementofdispute` (the dispute), `undo`, `confirmationbyauthority` (the action, done *before*), `churchservice` (its occasion) |
| C | What was directed | 10 | `0` | prescribes | `order`, `negativeorder` (of a "not"), `orderednotcarriedout`, `request`, `invitation`, `recommendationofaction`, `creationcommission`, `contentsofwill`, the punishment imposed, a settlement's outcome |
| D | What was undertaken | 7 | `0` | prescribes | `promise`, `contract`, `marriagebeginning` terms, `swearingofoath` (if promissory), `quidproquo`, `grantsprotection`, `refusal` (of a "not") |
| E | What was intended, a purpose | 3 | `0` | prescribes | `expressionofintention` ("does not imply that the thing happened"), a `journey`'s purpose, an endowment's purpose |
| F | What was permitted, forbidden, a right | 5 | `0` | prescribes | `grantingpermission`, `grantingofdispensation`, `prohibition`, a right a benefice or a noble position confers |
| G | A condition | 10 | `0` | describes | `eventdependenttrigger`'s condition, conditions to end an excommunication, expulsion or suspension, the conditions of a permission, an office, a transfer, a `verschreibung`, a `threat`'s causes |
| L | What follows if a condition holds | 4 | `0` | prescribes | `eventdependenttrigger`'s two results ("this should happen"), a `threat`'s consequences |
| H | What was communicated or recorded | 2 | `0` | describes | `communicateswith`'s subject, `recordinginregister` |
| I | A reason, asserted or alleged | 6 | `1` or `0` | describes | `imprisonment`, `punishment` (alleged by the punisher), `payment`, `debtowed`, `verschreibung`, a temporary transfer (mostly asserted) |
| J | What is thanked for or lamented | 2 | `1`, no space | describes | `textexpressesthanks`, `textexpresseslamentation` |
| K | A machine's suggestion | 1 | — | — | `unknownstatementtype.corrected_statements` (AutoAPIS) |

So: **41 of the 62 fields hold something not asserted** (C to H and L), **29 hold something prescribed** (C, D,
E, F, L), **14 hold something asserted** (A, B, J), six can be either (I), and one is not a matter of meaning (K).
Read as the eight fields, the model needs every value of `veridical`, both of `fit`, `logical="not"` in at least
eight places (the five classes of point 1, the two negative fields of `threat`, and `refusal` as an undertaking not
to), a deontic necessity of not for `prohibition` (`Modal("necessity", "deontic", of_not=True)`), and `unary` on
the `Not`. It never needs `semantic_family` or `semantic_operator` to decide anything (its deontic statements need a
flavour, which `logical` holds: point 11 below), and its `head_statement` is `content_status` with one value.

## What the exercise adds

Eleven things the model needs that the eight fields do not give, or that change how they should be taken. Each is
"what could be required", not a decision.

1. **Bare nesting must mean asserted**, and most `1`s need no space at all (A, J). This is the file's own principle,
   and the model bears it out: a `1` space is for an attitude to something also asserted, which is rare.
2. **Not every statement held by another is contained.** The eight fields of B name a statement that stands on its
   own, usually in another factoid (the order accepted, the debt cancelled, the dispute settled): in Pangloss a
   citation (`Cites[T]`), not nesting and not a space. Taking one up can change what it holds: accepting an order
   makes its content the recipient's undertaking.
3. **Fulfilment is wanted, not a refinement.** The model has classes for an order not carried out, for accepting an
   order or a request, and for refusing; nearly half its fields are prescribed (29 of 62). The relation between a
   prescribed content and what happened is the comparison it most needs, which settles the report's question 4 in
   favour of fulfilment, and means phase 12's call c (never two statements of one factoid) must not apply to it.
4. **A space in each of two slots**, the shape the fault above gets wrong when the slots are single relations (as a
   conjunction's usually are): `threat` (cause, consequence), `eventdependenttrigger` (condition, result, result
   otherwise), `punishment` (reason, punishment), `settlementofdispute` (dispute, outcome), `grantingpermission`
   (permission, conditions). **The fault has to be fixed before any reader of spaces can be trusted with this
   model.** The "otherwise" result of
   `eventdependenttrigger` also needs the condition's `Not` to be read off the slot (if not C then R2).
5. **Holder and addressee, by role, not by field name.** Fulfilment asks whether the *addressee* did the thing;
   "whose belief" asks for the holder. None of the eight fields can say which field of the holding statement that
   is. Proposed: markers on the holding statement's fields, `Annotated[Agent, Holder()]` and
   `Annotated[Agent, Addressee()]` (Pangloss has field markers already: `IdentityClaim()`), found through a reified
   relation such as a proxy. The content's own agent (the `buyer` of the purchase) has to be named too; phase 12's
   `CompareMeta(identifying=[...])` is the place.
6. **Strength within a family.** The model ranks its own classes: an expression of intention "implies a lesser
   commitment than a Promise"; recommendation, request, order. The report left strength out of the core; this
   suggests a rank, on the space class or as phase 12's, so that a fulfilment expected of an order outweighs one of a
   recommendation.
7. **Before or after.** `confirmationbyauthority` is "the same as granting permission, but *after* the action": two
   classes that differ only in whether the content comes before or after the statement holding it. A field for that
   (`orientation`: `"prospective"`, `"retrospective"`) would serve fulfilment (only what comes after an order
   carries it out) and the time part.
8. **Alleged reasons.** "Imprisoned for treason" asserts the imprisonment and, read as bare, the treason. A source
   usually asserts only the charge. So a reason held by a punishment needs a space of its own (`Alleged`,
   `veridical=0`, the holder the one who punishes), while the reason of a payment is mostly asserted (bare).
9. **Contents that are kinds, not events.** A prohibition of importing copper from Venice, a right to payments
   that a benefice confers, the duties of an office: the content is a kind of action, done many times or never.
   Comparison must not take it as one event; its fulfilment or breach is many to one. A mark for such contents
   (`generic`) would be needed before comparing them.
10. **Neither certainty nor a machine's guess is a space.** Every statement has `certainty` and `certainty_values`
    (JSON): how sure someone is, of the statement or a field, not what the source says of it (`Possible` is the
    source hedging). Pangloss keeps that in edge models and annotated values (the demo's `Certainty`,
    `WithCertainty`). And AutoAPIS's `unknownstatementtype` is a suggestion no person has confirmed, which Pangloss
    has a mechanism for (`hooks.unconfirmed`, the library's suggestion classes), not a space.
11. **Two normative orders.** The deontic statements come from the Church (`grantingofdispensation`,
    `grantingofindulgence`, `excommunication`) and from rulers and cities (`prohibition`, `grantingpermission`, the
    rights a benefice or a noble position confers). A dispensation is a permission against canon law, not against a
    ruler's prohibition. With the flavour in `logical` and the authority as the holder, comparison calls a conflict
    only within one order, and two orders at odds something else (the table under
    [How it works with similarity](#how-it-works-with-similarity)).

And one small one: `textannounces` ("I will write a poem about Maximilian") has no field for what is announced;
a space (`Announced`, `fit="prescribes"`, prospective) would give it one.

In passing, four slips in the file that a port would carry into its labels: `threat` has the `verbose_name`
"Provision of Accommodation"; `textexpressesthanks` has the description of `textasksforpatronage`;
`textmakesnegativestatementaboutperson` says "positive"; and `fictionalperson` and `fictionalplace` have each
other's German names.

### What the exercise says of the eight fields

| Field | Needed by the manmax model | Verdict |
|---|---|---|
| `veridical` | Every one of the 62 fields | Core |
| `fit` | 29 fields prescribed; fulfilment is three of its classes | Core |
| `logical` | `"not"` in at least eight places; deontic necessity and possibility in F, of two normative orders (point 11) | Core |
| `unary` | On `Not` | Core, or implied by `logical` |
| `semantic_family` | Never to decide, but for a modal's flavour, which `logical` holds; the model's own groups (Allgemein, Leben/Familie, Text, Musik...) are thematic and cut across it | Not taken: the class hierarchy |
| `semantic_operator` | Only for negation and the modals | Not taken: `logical` |
| `content_status` | Its `head_statement` is this field with one value | Not taken: the class's name is the word for people |
| `operand_cardinality` | Lists under one operator (a contract's terms, a will's contents, `quidproquo`) are read item by item | Not taken: `unary` |

And what none of them covers, from the list above: holder and addressee (5), before or after (7), strength (6),
alleged reasons (8), generic contents (9), citations (2), and the fault (4).

## Decisions for the user

**Decided (2026-11-24): the report's four fields**, as revised here; not ChatGPT's, and not both.

1. Whether to fix the fault in `propagate_context` (single relations sharing their spaces), with a migration that
   works the stored lists out again.
2. Whether `logical` gives a modal by force and flavour (`Modal(...)`) as proposed here, with the flavour the
   project's own word (proposed) rather than one of a list.
3. Whether `orientation` (before or after) and a strength rank belong with the four, or in phase 12's `CompareMeta`.
4. Whether `Holder()` and `Addressee()` markers on fields should be designed (they would serve comparison, the
   interface and the RDF export).
5. Whether phase 12's verdict takes in the relations of [How it works with similarity](#how-it-works-with-similarity)
   (carried out or not, tension, conflict), with its own rule for pairs in one factoid.
6. Whether forms should draw a space that is a field's only option without its head bar, and offer "not" as a
   toggle ([How to explain it to people](#how-to-explain-it-to-people)).
7. For negatives ([Negatives that record a relation](#negatives-that-record-a-relation)): one gradient, the
   researcher's, or the source's beside it.
8. Where the researcher's judgement lives (proposed: `Expectation[T]`, a citing document in `pangloss-library`), and
   how an expectation is proposed (proposed: the project's derived rules with a guard of feasibility; link prediction
   later).
9. Which uses to build: the graph part's weights, the actual network as a second graph part, comparison's weights,
   suggested grounds, the interface.
10. For derived ([Derived edges through spaces](#derived-edges-through-spaces)): the derivation decided by the walk of
    the path, with a status on each justification and fact; denials blocking positive edge classes, and virtual
    relations as classes of their own; the demo's subjunctives described as commands (no migration) or split
    (decision 8).
