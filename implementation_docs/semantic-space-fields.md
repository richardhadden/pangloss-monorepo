# The fields of a semantic space ⏳

What each of the eight proposed fields of `SemanticSpaceMeta` would mean and how each would be used: ChatGPT's four
(`semantic_family`, `semantic_operator`, `content_status`, `operand_cardinality`, in `semantic_spaces_demo.py`) and
the four of [the report](semantic-spaces-formalisation.md) (`veridical`, `fit`, `logical`, `unary`), side by side.
Then the data model of the user's project, `apis-instance-manmax` (its `model_config.json`, read on 2026-11-24), taken
as an exercise in what such fields would have to cover. **Nothing here is built**: every `SemanticSpace.Meta(...)`
below with one of these fields is a proposal, and so are `Holder()` and `Addressee()`. What is said of the code as it
is was read in it, and one fault was found by a scratch test (below).

Writing this changed two of the report's four: `logical` names its operator rather than being a yes or no, and
`fit`'s values are `"describes"` and `"prescribes"` rather than `"world"` and `"word"` (see each).

## Contents

- What any field of `SemanticSpaceMeta` is
- A fault in how spaces are recorded today
- ChatGPT's four: `semantic_family`, `semantic_operator`, `content_status`, `operand_cardinality`
- The report's four: `veridical`, `fit`, `logical`, `unary`
- The two sets side by side
- One example, through every reader
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

## ChatGPT's four

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

**What is wrong with it.** Each use is already served by an abstract parent class (`class Epistemic[T]
(SemanticSpace[T])`, abstract): the menu can group by it, search expands it, and the ontology has it as a class. As
an enum it is a closed list: a project with a family it does not name (legal procedure: `Charged`, `Sentenced`,
`Pleaded`) needs a change to the core. The file itself does not keep to it: the conversation has a `TOPIC` family,
the file puts `KnownAbout` in `EPISTEMIC` with a `TOPIC` *status*.

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
  field gives**, and it is why the report's `logical` now names an operator (below).
- *Naming the operator for others*: two projects' `Negative` and `Not` are both `NEGATION`; an export or an
  import between projects could match them.

**What is wrong with it.** Outside the six logical operators it is a second name for the class: each space has one
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
[`logical`](#logical)). Then walk from the outside with a sign that starts at `1`: a `1` space keeps it;
`logical="not"` flips it; a `0` space makes it `0`; once it is `-1`, the next space or statement makes it `0` (that
something is not so says nothing of what it holds); `0` stays `0`. So:

| Path | `veridical` of p |
|---|---|
| `Not[p]` | `-1` |
| `Not[Not[p]]` | `1` |
| `Not[Known[p]]` (it is not known that p) | `0` |
| `Not[Possible[p]]`, read as `Necessary[Not[p]]` | `0`, or `-1` where the project says its `Necessary` is `1` |
| `Known[ChurchService(parts=[p])]` | `1` |
| `Not[ChurchService(parts=[p])]` (there was no such service) | `0`: the flat list on p, `["Not"]`, would wrongly say `-1` |
| `Order(content=Ordered[p])`, the order asserted | `0` |

**How it would be used.**

- *Comparison* (`pangloss-compare`, phase 12): the relation of two statements whose contents match. One `1` and one
  `-1`: they contradict; `1` and `0`: weak support; `-1` and `0`: tension. Phase 12's `CompareMeta(negates=True)`
  is `veridical=-1`.
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
    _meta = SemanticSpace.Meta(logical="not", unary=True)    # veridical -1 follows from logical="not"
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
  question of fulfilment, not of agreement: carried out (`1`), not carried out (`-1`), reported carried out (`0`).
  This is the column of the report's table that phase 12 leaves out.
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

**What it says.** Which operator of standard logic the space is, if it is one: the operators whose logic is fixed
and shared, so that the code may rewrite one into another.

**Values**: `"not"`, `"possible"`, `"necessary"`, `"obligatory"`, `"permitted"`, `"forbidden"`; default `None`. A
closed list is right here, where it was wrong for families: these six are the whole of the logic, and a project's own
kinds of space are not among them. (The report's first draft had a yes or no; that cannot say *which* operator, and
rewriting needs to know.)

**What it implies.** `"not"`: `veridical=-1` and `unary=True`. `"obligatory"`, `"permitted"`, `"forbidden"`:
`fit="prescribes"`; `"forbidden"`: `unary=True`. Each can still be set otherwise, and a contradiction (`"not"` with
`veridical=1`) is refused at `initialise()`.

**How it would be used: normalising**, on the comparison's copy of a path, never on what is stored:

| Written | Read as |
|---|---|
| `Not[Not[p]]` | `p` |
| `Not[Possible[p]]` | `Necessary[Not[p]]` |
| `Not[Necessary[p]]` | `Possible[Not[p]]` |
| `Forbidden[p]` | `Obligatory[Not[p]]` |
| `Not[Permitted[p]]` | `Obligatory[Not[p]]` |
| `Not[Obligatory[p]]` | `Permitted[Not[p]]` |

so that "it was forbidden to import copper" and "it was obligatory not to import copper" compare as one claim. A
rewrite applies **only between spaces next to each other**: `Not[GrantingPermission(..., content=Permitted[p])]`
says that a permission was not given, which is not that p was forbidden, and the statement between them stops it.

### `unary`

**What it says.** That the space holds exactly one item.

**Values**: `True` or `False`; default `False`. Set by `logical="not"` and `"forbidden"`, and by hand on any other
downward monotone space (`Doubted`, `Refused`).

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
| `Possible` | alethic | possibility | possible | `0` | | `"possible"` | |
| `Necessary` | alethic | necessity | necessary | `0` (a project may say `1`) | | `"necessary"` | |
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
| `ObligatoryContent` | deontic | obligation | obligatory | `0` | `"prescribes"` | `"obligatory"` | |
| `PermittedContent` | deontic | permission | permitted | `0` | `"prescribes"` | `"permitted"` | |
| `ProhibitedContent` | deontic | prohibition | prohibited | `0` | `"prescribes"` | `"forbidden"` | yes |
| `KnownAbout`, `HeardAbout` | epistemic, evidential | awareness, hearing | topic | — | — | — | — |

The last row has no values because it holds an entity, not a proposition: as the report says, a relation.

What the table shows:

- **ChatGPT's status is a name for the report's values.** Read across, every status is a pair of `veridical` and
  `fit` (and `logical` where there is one), plus which class it is. What a reader *acts on* is the pair; the name
  is for people.
- **Its family is the class hierarchy**, its operator is the class, except for the six operators of standard
  logic, which `logical` names.
- **Its `operand_cardinality` is `unary`**, with the reason (monotonicity) that says which spaces need it.
- **The report's four do not say what the spaces are called**, which is why a project's `Charged` or `Feared` needs
  no change to the core: it is a class with two or three values.

| | ChatGPT's four | The report's four |
|---|---|---|
| A reader can decide by them alone | No (needs a table from operator or status to behaviour) | Yes |
| A new kind of space | A change to the core's enums | A class |
| Normalising | Yes, by the operator | Yes, by `logical` |
| A word for the reader | Yes (status) | No (the class's name and docstring) |
| Inherited, checked, exported | Yes | Yes |

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
to), `logical="forbidden"` for `prohibition`, and `unary` on the `Not`. It never needs `semantic_family` or `semantic_operator` to decide anything, and its `head_statement` is
`content_status` with one value.

## What the exercise adds

Ten things the model needs that the eight fields do not give, or that change how they should be taken. Each is
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
| `logical` | `"not"` in at least eight places; `"permitted"` and `"forbidden"` in F | Core |
| `unary` | On `Not` | Core, or implied by `logical` |
| `semantic_family` | Never to decide; the model's own groups (Allgemein, Leben/Familie, Text, Musik...) are thematic and cut across it | Class hierarchy |
| `semantic_operator` | Only for the six of `logical` | Folded into `logical` |
| `content_status` | Its `head_statement` is this field with one value | A word for people: the class's name |
| `operand_cardinality` | Lists under one operator (a contract's terms, a will's contents, `quidproquo`) are read item by item | Folded into `unary` |

And what none of them covers, from the list above: holder and addressee (5), before or after (7), strength (6),
alleged reasons (8), generic contents (9), citations (2), and the fault (4).

## Decisions for the user

1. Whether to fix the fault in `propagate_context` (single relations sharing their spaces), with a migration that
   works the stored lists out again.
2. Which fields go in the core: the report's four as revised here (`logical` naming one of six operators, `fit`
   as `"describes"`/`"prescribes"`), ChatGPT's, or both.
3. Whether `orientation` (before or after) and a strength rank belong with them, or in phase 12's `CompareMeta`.
4. Whether `Holder()` and `Addressee()` markers on fields should be designed (they would serve comparison, the
   interface and the RDF export).
5. Whether phase 12's verdict takes fulfilment in, with its own rule for pairs in one factoid.
