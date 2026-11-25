# Formalising semantic spaces, and using them in statement similarity ⏳

**2026-11-25:** the lists this page speaks of (`meta.context_labels`, shared between nodes) were replaced by `meta.path`; what is recorded now is in [semantic spaces](semantic-spaces.md).

A report, 2026-11-24, on the proposal in `semantic_spaces_demo.py` and the end of the ChatGPT conversation that made it
(`chatgpt-semantic-space-conv.md`: the user's note that extra fields on `SemanticSpaceMeta` are fine, ChatGPT's
answer, and the request for one file), and on whether its types can serve the similarity of statements: the vectors
([vectors.md](vectors.md)) and the comparison of phase 12 ([similarity-build-plan.md](similarity-build-plan.md),
"Phase 12: `pangloss-compare`", not built). **Nothing here is built.** What the code does today was read in the code;
where a claim rests on reading and not on a test, it says so.

A summary of this report and of [semantic-space-fields.md](semantic-space-fields.md) is
[semantic-spaces-summary.md](semantic-spaces-summary.md); how it would be built,
[the build plan of semantic spaces and comparison](spaces-and-comparison-plan.md).

## In short

- **The formal idea is sound, and Pangloss can already hold almost all of it.** Spaces with fields of their own,
  spaces holding entities, spaces below spaces (`Strongly[T](Negative[T])`), abstract spaces and meta slots on
  spaces all exist and are tested. Only the fields on `SemanticSpaceMeta` need the core. The user has said fields
  there are fine, and there is a good case for them (several packages would read them), but **not these four**: a
  closed list of families and operators in the core means a core change for every new kind of space, and they
  repeat what the class says. The core should hold the few *properties* generic code acts on (veridicality,
  direction of fit, whether it is a negation or a modal by its force and flavour, one operand), and the families
  stay a class hierarchy (below). **Decided by the user (2026-11-24): these four**, as revised in
  [semantic-space-fields.md](semantic-space-fields.md); not ChatGPT's, and not both.
- **For similarity the types are worth a great deal, but not as a distance.** What a space changes is the
  *relation* between two statements (one says the other is wrong, one carries out what the other ordered), not how
  near they are. The right use is: find the pairs by their contents, as now; then work out the relation from the
  spaces each statement is in, by a small algebra. Folding the spaces into the vectors would hide exactly the pairs
  most worth finding: a statement and its denial.
- **What a comparison needs of a space is four or five features, not twenty classes.** Whether it commits to the
  contents being so (veridicality), its polarity, its direction of fit (a report of the world, or an order, wish or
  promise about it), whose attitude it is, and how strong. Phase 12's call b, `CompareMeta(negates=True)` or
  `CompareMeta(compared=False)` on a project's spaces, is the first two of these. Put on `SemanticSpaceMeta`
  instead, they are the whole of the hook needed, and compare, derived rules, identity claims, the time part and
  the RDF export can all read the same declaration.
- **The proposal has faults to mend first**: `Negative` means both a source's denial and the logical "not";
  several things are said twice and can disagree; researchers' assessments are nested in the source's data; spaces
  over entities have no truth to qualify; the ordinal scales hold `UNKNOWN`.
- **The taxonomy is larger than people will enter consistently.** Belief, knowledge, hearing and report will be
  confused in practice, and a metric built on fine distinctions inherits that noise. Families first, fine classes as
  optional subclasses.

## What the proposal is

The file declares a researcher's vocabulary of contexts for statements, each a `SemanticSpace[T]`:

| Family | Spaces | Features the file gives them |
|---|---|---|
| Polarity | `Negative` (with `mode` and nested `NegationAssessment`s) | denied |
| Alethic | `Possible`, `Necessary` (with a `ModalBasis`), `Hypothetical` | possible, necessary, assumed |
| Epistemic | `KnownAbout` (an entity), `KnownContent`, `BelievedContent`, `DoubtedContent` | topic, factive, believed, doubted |
| Evidential | `HeardAbout` (an entity), `HeardContent`, `ReportedContent` (channel, mode, informant) | topic, heard, reported |
| Predictive, desiderative, intentional | `PredictedContent`, `DesiredContent`, `IntendedContent` | predicted, desired, intended |
| Directive, commissive, conditional | `DirectiveContent`, `Commitment` (promisor, beneficiary, kind, due by), `IfCondition` | directed, committed, conditional |
| Deontic | `ObligatoryContent`, `PermittedContent`, `ProhibitedContent` | obligatory, permitted, prohibited |

And statements that hold them: `Order.content: DirectiveContent[Proposition]`, `KnowingThat.content:
KnownContent[Proposition]`, `Agreement.terms`, `NormativePosition`, and so on, where `Proposition = Statement |
Negative[Statement]`. An unwrapped statement in a factoid means "the source says this was so"; the contents of a
space are not thereby said to have happened. That is the right reading, and it is how the demo's
`Order.thing_ordered` already works.

Underneath, this is a standard and well-founded picture: an operator applied to a proposition, sometimes with a
holder (whose belief, whose order) and a basis (Kratzer's modal bases, which `ModalBasis` names). The families are
those of the literature: alethic and deontic modality, propositional attitudes, evidentiality, Searle's classes of
speech acts (directive, commissive). The one property that matters most for comparison, and that the file never
names, is **veridicality** (Giannakidou): whether `O(p)` entails `p` (knowing that), entails `not p` (denying), or
neither (believing, hearing, wishing, ordering).

## How it fits Pangloss as it is

What works today, without any change (each is in the models' tests: `test_search_match.py`,
`test_search_wrapper_relations.py`, `test_computed_fields.py`, `test_meta_slots.py`):

- A space with fields of its own (`mode`, `basis`, `informant`, `promisor`).
- A space below another, so families can be abstract classes and the operators their subclasses; search matches a
  subclass under its parent.
- A space over an entity (`Doubtful[Person]`).
- Meta slots of an app's on a space, inherited (`FastRPMeta(stop=True)` on the demo's `Negative`).
- Every node inside a space carries `meta.semantic_spaces` (the names of the enclosing spaces) and
  `meta.context_labels` (the path, with ids): **a statement's operators can be read off the statement itself,
  without walking up**. Nothing in similarity reads them yet (`pangloss-vectors` only passes them to the view,
  `views.py:98`).
- One operand: the library's idiom, `Annotated[list[T], MinLen(1), MaxLen(1)]` (`Identification.target`). Whether
  a space may narrow its `contents` that way has not been tried.

### Fields on `SemanticSpaceMeta`: yes, but not these four

The file needs `semantic_family`, `semantic_operator`, `content_status` and `operand_cardinality` on the core's
`SemanticSpaceMeta`, with their enums in `pangloss_models`. The user told ChatGPT that extra fields there are fine,
and the case for the core is better than this report first allowed: a space's formal meaning is a property of a core
kind (the core already treats spaces apart, propagating `semantic_spaces`), and **several packages already make
decisions about every space alike that such fields would let them make by its meaning**:

- `pangloss-derived`: a rule finds what is inside every space and *qualifies* the fact by it unless the space
  says otherwise (`DerivedMeta(derivation="qualify" | "block" | "transparent")`, a slot of its own on each space,
  [derived.md](derived.md)), so a project says by hand, space by space, what `veridical` would say once (worked
  out, and measured on the demo, in [Derived edges through spaces](semantic-space-fields.md#derived-edges-through-spaces));
- `pangloss-library`'s identity claims: a claim in any space joins nothing ([entity-identity.md](entity-identity.md),
  "What joins"), so "the source knew that A was B" is treated as "perhaps A was B";
- `pangloss-dates-vectors`: a statement in `Negative` or `Hypothetical`, or ordered, keeps the date of what did not
  happen (step 9.3, `TODO.md`);
- `pangloss-fastrp`: `stop` and `weight` by hand on each space;
- `pangloss-compare` (planned): `negates` and `compared` on each space;
- `pangloss-rdf`: the generated ontology could say what a space means.

One declaration on the space, read by each, is better than a slot for each package. So: fields in the core, yes.
But the four proposed are the wrong ones:

1. **Closed lists of a theory in the core.** `SemanticFamily` and `SemanticOperator` are enums in `pangloss_models`:
   a project that wants a space they do not name (`Rumoured`, `Forged`, `Feared`, `Claimed under oath`) needs a
   change to the core, or has to call it something it is not. The core should hold what generic code *acts on*, and
   leave the naming of kinds to the project.
2. **They say what the class already says.** Each space has exactly one operator and one status, fixed by its class,
   so the enums are a second name for the class. `content_status` is one-to-one with `semantic_operator` in every
   case but `HEARING`, where it is the topic/content distinction that the class pair already makes.
3. **No code could act on them as they are.** To decide anything (whether a rule fires, whether two statements
   contradict) a reader would need a table from each operator to its behaviour, kept outside the models, in every
   package. The behaviour itself is what should be declared.
4. **The hierarchy is the Pangloss way to say a family.** `class Epistemic[T](SemanticSpace[T])`, abstract, with
   `Belief`, `Knowledge` and `Doubt` below it: inheritance carries meta (as ChatGPT wanted for its enums), the class
   part of the vectors already turns a hierarchy into a vector, search already matches by it, and the interface
   already groups by it.

What to put there instead is in [What the hook should be](#what-the-hook-should-be): veridicality, direction of fit,
whether the space is a negation or a modal (by its force and its flavour), and one operand enforced (not only
described).

### What the conversation adds

- **ChatGPT's own caveats agree with this report**: `ContentStatus` "is not an outcome" (`DIRECTED` says nothing of
  whether the journey happened: veridicality `0`); negation assessments "should remain instance-specific" and get
  "a separate, attributable assessment model" eventually (fault 3 below: the file nests them anyway);
  `operand_cardinality` "is descriptive until you implement validation".
- **The core change as given is incomplete.** The conversation's `SemanticOperator` ends at `INTENTION` and
  `ContentStatus` and `OperandCardinality` are never defined, while the file uses `DIRECTIVE`, `COMMITMENT`,
  `CONDITIONAL_ANTECEDENT`, `OBLIGATION`, `PERMISSION`, `PROHIBITION` and every `ContentStatus` value. The file
  cannot initialise with what was given; it was syntax-checked under Python 3.13 and never run.
- **The vocabulary is not consistent with itself.** The conversation has a `TOPIC` family; the file puts
  `KnownAbout` in `EPISTEMIC` and `HeardAbout` in `EVIDENTIAL` with a `TOPIC` status instead. `HEARING` is the
  operator of both `HeardAbout` and `HeardContent`.
- **Its own table shows the conflation of fault 1**: "The king ordered X not to travel" is
  `DirectiveContent[Negative[Journey]]`, read as "Directed and denied". Nothing was denied: a "not" was ordered.

### Faults in the proposal

1. **`Negative` is two things.** As a top-level statement it is a *source's denial* (with `NegationMode` and a
   researcher's `NegationAssessment` of how telling the denial is). As `Proposition` inside `DirectiveContent`,
   `Commitment` or `ObligatoryContent` it is the *logical "not"* of the contents ("ordered not to go"), where a
   denial mode and an argument from silence make no sense. For comparison these behave differently: a denial is a
   source's claim against another's; a "not" inside an order is part of what was ordered. Split them: a `Not[T]`
   with no fields for the contents' polarity, and `Denial[T]` (or keep the name `Negative`) for the source's speech
   act. The demo already has this split in its own way: `NegativeSubjunctive` is "ordered that not".
2. **Things said twice, that can disagree.**
   - `NormativePosition.force` and the class of its `content` (`ObligatoryContent | PermittedContent |
     ProhibitedContent`): both are chosen by hand. Drop `force`.
   - `Order.force = PROHIBITION` and `DirectiveContent[Negative[...]]` say the same thing two ways. A prohibition is
     an order of a "not"; `force` should be how strong (suggestion to command), not its polarity.
   - `ProhibitedContent[p]` is `ObligatoryContent[Not[p]]`, and `PermittedContent[Not[p]]` is the negation of
     `ObligatoryContent[p]`. The same claim then has several encodings, and a comparison has to normalise them
     (below) or it will call two equal claims different.
   - `Reporting.reporter` and `ReportedContent.reporter`; `HearingThat.hearer`, `HeardContent.informant` and
     `Reporting`: the holder of an attitude is sometimes on the statement and sometimes on the space. Choose one.
     The statement is the better place (it is the event of hearing or ordering, with its date and people); the
     space then marks only what is inside, which is what `meta.semantic_spaces` propagates. A comparison reads the
     holder from the statement that holds the space, which `context_labels` names by id.
3. **Researchers' assessments are nested in the source's data.** `Negative.assessments: list[NegationAssessment]`
   puts a scholar's judgement inside the factoid. An update replaces the whole document, so assessing a denial
   rewrites the factoid, gives it a new version, may send it back through review, and puts the assessment in the
   source's history. Another scholar's different judgement has nowhere to go. A judgement about data is a document
   of its own that cites it (`Cites[T]`), as phase 12's `EventJudgement` does; `NegationAssessment` is the same kind
   of thing and should be built the same way.
4. **Spaces over entities.** `KnownAbout[Entity]` and `HeardAbout[Entity]` have no proposition: there is nothing
   whose truth they qualify, and since an entity is never part of a document, nothing inside them gets
   `meta.semantic_spaces`. "A knew of B" is a plain relation (`knows_of: list[Entity]`), or a reified relation if it
   needs fields.
5. **Ordinal scales with `UNKNOWN` and `NOT_APPLICABLE` in them.** `Feasibility`, `Opportunity`, `Expectedness`
   and `Confidence` are orders, and a metric will want them as numbers; `UNKNOWN` has no place in the order. Make the
   field `X | None` and keep the enum to its ranks. `Confidence` also overlaps the library's `Likelihood` and the
   demo's `Certainty`; one scale of certainty in a project is better than three.
6. **The factoid's union is redundant and uneven.** `Statement` is abstract, so it already offers `Order`,
   `Agreement`, `KnowingThat` and the rest; listing them again changes nothing. At the top level it offers
   `Negative`, `Possible` and `Hypothetical` but not `Necessary`, `Reported` or `Believed`; inside an order it offers
   only `Negative`. A rule for which spaces may wrap what (below) is better than unions written out by hand.

## Spaces in statement similarity

### Two things called similarity

Pangloss has, or plans, two:

- **"Items like this one"** (`pangloss-vectors`, built): a vector for each document and entity from parts (class,
  graph, name, time), and the nearest by cosine. Statements have vectors (nested documents get them).
- **"Is this the same event, and do they agree?"** (`pangloss-compare`, phase 12, written, not built): pairs of
  statements naming the same entity in an identifying field, found by rule and by vectors; a verdict, `agree`,
  `disagree` (with the fields) or `two` events, worked out at lookup; people's judgements override it.

Spaces matter for both, in different ways.

### What the vectors do with spaces today

- **The class part ignores them.** "A went to Rome", "A did not go to Rome" and "A wished to go to Rome" are all
  `Journey`, with the same class vector.
- **The graph part passes through every space but one with `FastRPMeta(stop=True)`** (the demo's `Negative`). A
  stop ends the chain that reaches it, so the factoid is not joined to the statement inside. But the statement
  inside is a stop itself, and its own fields are walked from it (`maps.py`, `maths.py`): as I read the code, a
  negated `Journey` is still joined to its traveller and its destination, so the traveller and the place are two
  joins apart through it, and with `FASTRP_STEPS = [0, 1, 1]` that counts. If the intent is that "X was not in Y"
  does not make X like Y ([graph-embeddings.md](graph-embeddings.md), the table of controls), `stop` on the space
  does not do it. **This should be checked by a test before anything is built on it**; it is a question about the
  graph part today, whatever comes of this proposal.
- **The time part dates what did not happen**: a negated, hypothetical or ordered statement keeps its date (left as
  it is in step 9.3, `TODO.md`).

### Why the spaces should not go into the distance

One could add a part, "context", a vector of the spaces a statement is in (a dimension for each space class, decayed
up the hierarchy as the class part does, with signed dimensions for polarity), and weigh it in a profile. It would be
cheap: the spaces are on the node. But it would do the wrong thing for the use that matters most. A profile's cosine
is a weighted mean of its parts' cosines; a "not" would push a denial *away* from what it denies, and the most
interesting pair in a prosopography, one source saying it happened and another saying it did not, would drop out of
the candidates. The same holds for an order and its carrying out, a prediction and the event.

So: **find candidates by content, decide the relation by the spaces.** Spaces as a part of the vectors is worth
having only as an opt-in profile for browsing ("show me other asserted journeys"), never in the profile that
comparison draws its pairs from.

What the spaces can do for the vectors without harm is **weigh the graph**: a wish, a report or a hypothesis is
weaker evidence that its people were together than an asserted meeting. `FastRPMeta(weight=...)` on a space already
multiplies every chain through it, and on an abstract family class it is inherited. That can be done in a project now.

### The features a comparison needs

For each space class, a handful of values (on a slot, set once on the family and changed on a subclass where it
differs):

| Feature | Values | Examples |
|---|---|---|
| Veridicality | `+1` the contents are so; `-1` they are not; `0` neither | Knowledge `+1`; Denial, Not `-1`; Belief, Report, Hearing, Possible, Hypothetical, Desire, Order `0` |
| Direction of fit | describes (how things are), prescribes (how they are to be made) | Belief, Report, Prediction: describes; Desire, Intention, Order, Commitment, Obligation: prescribes |
| Holder | the source (no space), or an agent named on the holding statement | Order: the issuer; Belief: the believer |
| Strength | a rank on the family's scale (Horn scales) | Possible < Necessary; Doubt < Belief < Knowledge; Permitted < Obligatory; suggestion < command |
| Prospective | whether the contents come after the attitude | Prediction, Intention, Order, Commitment |

The path of a statement is the list of its spaces, outermost first (`meta.semantic_spaces`), each with its holder
(the statement that holds it, from `context_labels`). From the path:

- **Normalise** what has two encodings, for negation and the modals only, and only within one flavour of modality
  (what is known, what a law allows, what is possible at all): `Not[Possible[p]] = Necessary[Not[p]]`,
  `Prohibited[p] = Obligatory[Not[p]]`, `Not[Not[p]] = p`, and "cannot have been" is "must not have been". A denial
  is a speech act and does not take part; neither do the attitudes (not believing that p is not believing that not
  p). Each modal's force and flavour are in `logical` ([semantic-space-fields.md](semantic-space-fields.md#logical)).
- **Compose veridicality**, after normalising, from the outside: a `+1` space keeps the sign, a "not" flips it, a
  `0` space makes it `0`, and once the sign is `-1` the next space or statement makes it `0` (`Not[Known[p]]`, it
  is not known that p, says nothing of p). A path that is `0` still leans for p or against it (`Reported[Not[p]]`
  leans against). The rule, with its cases, is in
  [semantic-space-fields.md](semantic-space-fields.md#veridical); it reads `context_labels`, since the flat list of
  spaces on a node does not say where the statements between them are.
- **The relation** of two statements whose contents match (by phase 12's rules, on the contents) follows from the
  two paths: one that asserts p and one that denies it contradict; an uncommitted one (a report, a belief, a "might
  have") supports an assertion or is in tension with it, by which way it leans ("it was reported that he did not
  go" is no support for "he went"); a prescription is carried out, not carried out, or breached, by what happened;
  two prescriptions of one flavour and one authority can conflict. The table, with what force changes (a permission
  is used or not, never carried out or breached), is in
  [semantic-space-fields.md](semantic-space-fields.md#how-it-works-with-similarity).

Phase 12 as written covers only the first of these (`agree`, `disagree`, and `negates` as a disagreement on the
whole) and leaves the rest out (`compared=False`). They are not noise: **fulfilment** (was the order carried out,
the promise kept, the prediction right) and **tension between reports** are relations a historian asks for, and
they come from the same pairs at no extra cost of finding.

- **Weight.** The strength of a corroboration or a contradiction can be the product of how far each side commits:
  `+1`/`-1` at their certainty, a report or a hearing lower, a hypothesis near nothing. This is where
  `NegationAssessment` earns its place: a denial is good evidence only when the thing denied was feasible and
  expected (an argument from silence is weak, an explicit correction strong). As a citing document, its values can be
  read when the verdict is worked out and change its weight, as an `EventJudgement` changes the verdict. (Worked
  out since, with the user: [Negatives that record a relation](semantic-space-fields.md#negatives-that-record-a-relation).)

All of this is a function of two statements as plain data, with no database, which is the shape of step 12.3
(`maths.py`, `verdict(a, b, meta)`). The weights are hand-set first and can be learnt from judgements, as step 12.9
plans for "one event or two".

### What the hook should be

A few fields on `SemanticSpaceMeta`, inherited as the rest of `_meta` is, set on the project's spaces (most often on
an abstract family class):

| Field | Values | Default | Read by |
|---|---|---|---|
| `veridical` | `1` (the contents are so), `-1` (they are not), `0` (neither) | `0` | compare, derived, identity claims, the time part, RDF |
| `fit` | `"describes"` (how things are), `"prescribes"` (how they are to be made) | `"describes"` | compare (fulfilment), the time part |
| `logical` | a negation (`"not"`), or a modal by its force and its flavour (`Modal("possibility", "epistemic")`), so that normalising knows which spaces are duals | `None` | compare, search |
| `unary` | one item in `contents`, refused at `Create` otherwise | `False` (as now) | the models |

```python
class Epistemic[T](SemanticSpace[T]):
    _meta = SemanticSpace.Meta(abstract=True, veridical=0)


class Knowledge[T](Epistemic[T]):
    _meta = SemanticSpace.Meta(veridical=1)            # the rest inherited


class Not[T](SemanticSpace[T]):
    _meta = SemanticSpace.Meta(logical="not")         # implies veridical=-1 and unary=True


class Ordered[T](SemanticSpace[T]):
    _meta = SemanticSpace.Meta(fit="prescribes")
```

These are theory-light: they say how a space behaves, not what it is called, so a project's own `Rumoured` needs no
core change, and another project may hold that a report commits its source (`veridical=1`) without anyone else's
code changing. The default, `veridical=0`, is the cautious one: a space nobody has described is read as "not
asserted", which is what derived rules already do by default (a fact found in a space is qualified, not plain) and
identity claims do more bluntly (a claim in any space joins nothing). Letting `veridical` decide them (a `+1` space
transparent to both, a `-1` space blocking) is a change of behaviour for existing projects, and should be its own
decision.

What stays a package's own choice stays in its slot: whether compare leaves a space out altogether
(`CompareMeta(compared=False)` on `Hypothetical`), how much a space weighs in the graph (`FastRPMeta`). Strength
(Horn scales) and the holder are left out of the core: the first is a project's ranking within a family, the second
is on the holding statement already.

Unlike the four enums, each of these is something a package listed above decides today by hand or not at all, and
each can be checked at `initialise()` (`unary` against a `contents` narrowed by hand; `logical="not"` against a
`veridical` set otherwise). Normalising rewrites only the comparison's copy of a path, never what is stored, so a
logical space may have fields of its own. Each field is described at length, with ChatGPT's four beside them and
the user's project as an exercise, in [semantic-space-fields.md](semantic-space-fields.md); writing that page
revised `logical` (a negation, or a modal by force and flavour) and `fit` (`"describes"`/`"prescribes"`). How the
four work with similarity, and how to explain them to the people who enter data, are there too.

## Is it viable

**As an ontology in a project: yes, with the mends above,** and with fewer classes to start. A useful first set,
which the demo nearly has: `Denial` and `Not`; `Hypothetical`; `Reported` (with the channel and mode, which are
good); `Believed`; `Ordered`/`Intended`/`Promised` as the prescribing family; the deontic three only if a project
has norms in its sources. Each with a family above it, so the finer classes can come later without a migration of
meaning. The cost of a large set is in the data, not the code: people entering factoids will not tell knowledge from
belief from hearing consistently, and every distinction a metric relies on must be one they make the same way.
A trial of agreement between two people entering the same passages would say which distinctions survive.

**For similarity: yes, and it is the part of the proposal with most to give,** provided the spaces decide the
relation and not the distance. The minimal path:

1. Add `veridical`, `fit`, `logical` and `unary` to `SemanticSpaceMeta` (a small core change, with tests of
   inheritance and of the checks; the export carries them so the interface could show them).
2. Keep phase 12 as written; when its steps are taken up, its verdict reads those fields in place of
   `CompareMeta(negates=True)`, keeps `CompareMeta(compared=False)` as its own choice, and follows the table above,
   the cells outside phase 12 answering "not compared" at first.
3. Add to 12.1's planted world reports inside `Reported` and `Believed`, and orders with and without their carrying
   out, so the extra cells have a truth to be measured against.
4. Test the graph part's `stop` (above) and decide what a negated statement should be joined to.
5. Leave a "context" vector part for later, as an opt-in browsing profile, if anyone asks for it.

**Not to do**: closed enums of families and operators in the core; spaces over entities; researchers' assessments
nested in factoids.

## Open questions for the user

**Decided (2026-11-24)**: the core fields are the report's four, as revised in
[semantic-space-fields.md](semantic-space-fields.md); ChatGPT's four are not taken, and not beside them.

1. Whether derived rules and identity claims should then follow `veridical` (a change of behaviour for existing
   projects: today a rule qualifies what it finds in any space unless its `DerivedMeta` says otherwise, and a claim
   in any space joins nothing).
2. Whether to split `Negative` into a denial and a logical "not" in the demo (it has `NegativeSubjunctive`, which is
   the "not" inside an order).
3. Whether fulfilment ("the order was carried out") belongs in phase 12's verdict, or is a relation of its own later.
4. Whether a negated statement should be joined to its people in the graph part at all (the `stop` question).
5. Where the researcher's judgement of a negative goes: proposed since as `Expectation[T]`, a citing document in
   `pangloss-library` ([semantic-space-fields.md](semantic-space-fields.md#negatives-that-record-a-relation),
   decision 8 there).
