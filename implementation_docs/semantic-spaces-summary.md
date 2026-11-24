# Semantic spaces formalised: a summary ⏳

A short account of two longer pages, both of 2026-11-24: [the report](semantic-spaces-formalisation.md) on
ChatGPT's proposal for a typed vocabulary of semantic spaces and its use in comparing statements, and
[the fields of a semantic space](semantic-space-fields.md), which describes the fields a space would have, how they
would be used, and the user's own data model as an exercise. **Nothing in them is built.** How it would be built is
[the implementation plan](semantic-spaces-plan.md).

## Where it started

ChatGPT proposed, in `semantic_spaces_demo.py` and a conversation (`chatgpt-semantic-space-conv.md`, both at the root
of the repository and not committed), about twenty spaces in families: polarity (`Negative`), alethic (`Possible`,
`Necessary`, `Hypothetical`), epistemic (`KnownContent`, `BelievedContent`...), evidential (`HeardContent`,
`ReportedContent`), the attitudes and speech acts (`DesiredContent`, `IntendedContent`, `DirectiveContent`,
`Commitment`), conditions and the deontic three, with statements that hold them (`Order`, `Agreement`,
`KnowingThat`...). Each space was to say four things on the core's `SemanticSpaceMeta`: its family, its operator, a
"content status" and how many operands it takes. The principle it rests on is sound, and is the one Pangloss already
has: **a statement on its own is what the source asserts; what is inside a space is not thereby asserted.**

## What was decided

**The user's decision (2026-11-24): fields on `SemanticSpaceMeta`, yes; the report's four, not ChatGPT's, and not
both.** ChatGPT's four are names: a closed list of families and operators in the core (a core change for every new
kind of space), repeating what the class already says, and acting on nothing without a table kept elsewhere. The
report's four say how a space behaves, so that a program can act on them, and they compose along a nested path.

| Field | What it says | Values |
|---|---|---|
| `veridical` | Whether the space commits the source to its contents | `1` (knowing that), `-1` (not), `0` (believing, reporting, ordering, a condition...); default `0` |
| `fit` | Whether the contents describe how things are, or prescribe how they are to be made | `"describes"` (default), `"prescribes"` (orders, promises, intentions, permissions) |
| `logical` | Whether the space is an operator of logic: a negation, or a modal by its force and its flavour | `"not"`, or `Modal(force, flavour, of_not=False)`: `Modal("possibility", "epistemic")` is "might have"; default `None` |
| `unary` | That the space holds one item | follows from `"not"` and from a modal of a negation; default `False` |

Three rules go with them:

- **Nesting with no space is asserted.** The parts of a church service, what someone is thanked for: no space is
  needed, so a space with `veridical=1` is rare.
- **A path composes.** From the outside, `1` keeps the sign, `"not"` flips it, a `0` space leaves the source
  uncommitted, and the walk goes on to find which way an uncommitted path *leans*: "it was reported that he did not
  go" leans against "he went". A statement between two spaces stops the composing (that a permission was not given
  is not that the thing was forbidden).
- **Modals rewrite into each other only within one flavour**, as formal semantics has it (Kratzer: a force,
  necessity or possibility, over a flavour, what is known, what a law allows, what is possible at all). "Cannot have
  been there" is "must not have been there"; "not permitted to import" is "obliged not to import"; what canon law
  does not permit is not thereby forbidden by a city's statutes. A possibility never commits the source; a
  necessity does only when the project says its flavour is of what is so.

## Similarity: contents find, spaces decide

The spaces must not change how near two statements are: a denial is as near to what it denies as a second report of
it, and that is the pair most worth finding. So the vectors (`pangloss-vectors`, built) stay as they are, and the
spaces decide what the planned comparison (`pangloss-compare`, phase 12, on hold) says of a pair. Each statement gets
a signature from its path (already on the node), and the two signatures turn "one event?" into a relation:

- one asserts and one denies: **contradiction**; an uncommitted one **supports** an assertion or is **in tension**
  with it, by its lean;
- something prescribed and what happened: **carried out**, **not carried out**, a **breach** (of an order not to);
  a permission is used or not, never carried out or breached;
- two prescriptions of one flavour and one authority that cannot both hold: **conflict**; of different ones (canon
  law and a ruler), two orders at odds.

Of the vector parts, only the time part would change (a date on something not asserted counts for nothing), and
perhaps the graph part's default weights. The "Similar" section would keep its order and label each item by its
relation.

## Explaining it to people

The people who enter data never meet the fields or the words "semantic space". **When a kind of statement brings its
space with it** (`Order.content` can only be "ordered"), they choose "Order" because the source tells of an order,
and put what was ordered inside it; what is left to choose is "not" and "perhaps" (and "reportedly", if a project
wants it). The finer distinctions (known, believed, heard) are choices of statement type, made by what the source
says. Three things still need saying: "not" is the source saying it did not happen; "perhaps" is the source
hedging, not the person entering it; a punishment's reason is only alleged unless the source asserts it. The forms
would need a space with no choice drawn without its head bar (done today for reified relations only).

## What is wrong with ChatGPT's file

- `Negative` is both a source's denial and the logical "not" inside an order ("ordered not to go").
- Things said twice that can disagree: `NormativePosition.force` and the class of its contents; `Order.force =
  PROHIBITION` and an order of a "not"; the holder sometimes on the statement, sometimes on the space.
- Researchers' assessments (`NegationAssessment`) nested inside the source's factoid, where an assessment rewrites
  the factoid and another scholar's has nowhere to go: they belong in a document that cites the statement.
- Spaces over entities (`KnownAbout[Entity]`): nothing there is true or false; a relation does it.
- Ordinal scales with `UNKNOWN` inside them; a factoid union that lists what `Statement` already offers.
- The core change it asks for cannot run as given: two of its enums are never defined.

## What was found in Pangloss

- **A fault, tested by a scratch test**: two single relations each holding a space (a conditional's condition and
  consequence) record the second's contents as inside both spaces (`propagate_context`, `pangloss_models/context.py`).
  Every reader of the spaces would be wrong for exactly that shape. Not fixed: the user's call.
- **A question, read and not tested**: `FastRPMeta(stop=True)` on `Negative` cuts the factoid from the negated
  statement, but the statement may still be joined to its own people, so "X was not in Y" may still make X like Y.
- **Every package treats every space alike today**: derived rules qualify what they find in any space, identity
  claims in any space join nothing, the RDF export asserts nothing inside any space, the time part dates everything.
  The fields would let each tell a denial from a report from a certainty.

## The user's project as an exercise

`apis-instance-manmax` (`model_config.json`): 222 classes, 151 statement types, 62 fields that hold statements, 46 of
which take any statement; no spaces. Instead: a class for each operator with its content (`absencefromevent`,
`negativeorder`, `orderednotcarriedout`), polarity in the names of fields (`threat`'s four, "PAY VERY CLOSE ATTENTION
TO WHICH FIELDS YOU USE!"), one bit for "not asserted" (`head_statement`), and the holder under a new name in every
class. Of the 62 fields, 41 hold something not asserted and 29 something prescribed. The four fields cover the
meaning; what the model needs beyond them:

- citations, not containment, for statements that stand on their own (the order accepted, the debt cancelled);
- fulfilment as a relation of its own (the model has classes for it);
- the fault fixed (the model is full of conditionals);
- the holder and the addressee of a prescription, by role;
- before or after (a confirmation is a permission given after the act), and strength within a family (an
  intention is "a lesser commitment than a Promise");
- alleged reasons; contents that are kinds of action rather than events (a standing prohibition);
- two normative orders (the Church's and the rulers'), which is where flavour and authority count;
- and two things that are not spaces: certainty, and a machine's suggestion.

## Decisions still open

From both pages, before anything is built:

1. Fix the fault, and how stored data is mended.
2. `logical` as force and flavour, with the flavour the project's own word.
3. Whether each package follows the fields: derived rules, identity claims, the time part, the RDF export, the
   graph part's weights.
4. `Holder()` and `Addressee()` markers on fields.
5. Before or after (`orientation`) and strength: with the four, or in phase 12's `CompareMeta`.
6. Whether phase 12's verdict takes in the relations above, with its own rule for pairs in one factoid.
7. In the forms: spaces with no choice drawn without their head, "not" as a toggle.
8. In the demo: split `Negative` into a denial and a "not"; where `NegationAssessment` would go.

## Where to read more

| For | Read |
|---|---|
| The proposal, its faults, the case for fields in the core, similarity at length | [semantic-spaces-formalisation.md](semantic-spaces-formalisation.md) |
| Each of the eight fields, the walk, the normalising table, the relation table, one example through every package, explaining it to people, the manmax exercise | [semantic-space-fields.md](semantic-space-fields.md) |
| How it would be built, step by step | [semantic-spaces-plan.md](semantic-spaces-plan.md) |
| What spaces are in Pangloss today | [semantic-spaces.md](semantic-spaces.md) |
| The comparison the fields would serve | [similarity-build-plan.md](similarity-build-plan.md), "Phase 12: `pangloss-compare`" |
