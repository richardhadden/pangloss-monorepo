# Descriptions instead of N.N.: a discussion record

**Preliminary. A record of a discussion on 2026-10-21/22, not a specification.** Nothing here is built, decided
or checked against a larger data set; "to check" marks facts about the code that were not verified. It should be
read with [modelling.md](modelling.md) (roles, "multi-tenant" roles such as "Maximilian's secretary"),
[../docs/dates.md](../docs/dates.md) and [../docs/history.md](../docs/history.md).

## The problem

Sources list people as "N.N., Maximilian's secretary" (N.N. for *nomen nescio*, "no name"). Modelled as one
Person entity per mention, they make a great many **singletons**: nodes with one document, no other links,
useless for network analysis, and misleading in counts.

What the source actually says is a **description** ("the secretary of Maximilian", perhaps within a period) that
some person, not named, satisfies. The wish: store the description, as something that can be matched against the
people known from other sources, instead of an invented person.

## A second example: a set, not a person

A pope retrospectively allows Maximilian to appoint bishops (he has done so already). The object of the act is not
a person but **a set defined by a description**: "the bishops that Maximilian previously appointed", which is
the answer to a query over other assertions (the appointments).

So the same device is wanted twice: a *description* of persons (N.N.), and a *description of things* (the
appointments that are ratified). Both are **intensional**: defined by criteria, not by a list; the members are
whatever satisfies them, now or later.

## The context: factoids, and nobody in charge

The project follows the Factoid Prosopography model (John Bradley; see
<https://www.kcl.ac.uk/factoid-prosopography/about>). What that page says, in brief:

- "A factoid is a spot in a source that says something about a person or persons." It is a **hub** linking
  sources, persons (and assemblages acting as persons), places, possessions, and classification schemes such as
  relationships, titles and offices. It started (mid-1990s) when the *Prosopography of the Byzantine Empire* was
  rebuilt as a structured database; Bradley and Short (2005) describe the model; an OWL/RDFS ontology, the
  Factoid Prosopography Ontology (FPO), is on GitHub.
- **Interpretation is not built into the factoids.** It "happens at the level of the individual assertions made by
  the historical sources", and the user receives "a collection of factoid-assertions that the user must assemble
  into her own story". The output of the research is structured assertions, not authored narratives.
- The page does **not** say how persons are constructed or linked, how disagreement or uncertainty is handled, or what
  fields a factoid has (date, place, role), nor how it separates inference from assertion.

So some of what follows is this project's own choice, **not inherited from the model**. Two statements of the
project, as given in the discussion, go beyond the page: that each "fact" is in practice **a researcher's
interpretation** of a source and its contents (the page puts the interpretation with the *user* of the database,
who assembles the assertions); and the three rules below. They fit the model (assertions anchored in sources, a
reader who assembles them) but are stated here as the project's requirements.

- Data may be entered **by anyone, in any order**. A description may be entered before the people who match it,
  or after.
- There is **no central figure** who decides what is correct. Assertions must be **addressable** (can be pointed
  at, compared, agreed with, disputed), not adjudicated.
- Structurally: **nothing can be said directly about an entity unless it is definitional.** Anything else (that this
  description is that person, that a person held an office, that a set was ratified) is made by a Pangloss
  **document asserting it**, which has an author, a time and, usually, a source.

How this maps: a Pangloss **Document** is the factoid-like hub (it points at a source, and at the entities it
speaks about); the **user who assembles** the assertions into a story is what the **lens** below stands for.
Where the model is silent (the construction of persons, disagreement, uncertainty) the design here is Pangloss's own.

*Lead to follow:* the FPO may show how it treats unidentified or collective persons, and how a person is linked
across factoids. Not read yet.

That last rule changes the first sketch of this idea.

## Pangloss and the factoid model: generic classes, nothing built in

Pangloss is not a factoid system and should not become one: no class, field or rule in core is specific to the
factoid model. The requirement is only that its **generic built-in classes can express factoid-style data**. The
demo project (`pangloss-demo/`, whose models file describes itself as a factoid database) is evidence that they
can; it maps like this:

| Factoid-model idea | Generic Pangloss class that carries it (in the demo) |
|---|---|
| The factoid: a spot in a source saying something about persons | A head `Document` (`Factoid`) that holds nested `Document`s (`Statement`, abstract, with `Activity` and `Transfer`) |
| The source, and where in it | An `Entity` (`Source`, with a URL as its id) and a reified relation with fields (`AtPage[Source]`) |
| Persons, and groups acting as persons | `Entity` classes (`Person`, `Group`) under a `Trait` (`Agent`) so that a relation can take either |
| Roles, titles, offices held in a factoid | A reified relation (`InRole[Agent]`), so a relation can carry fields |
| How sure the source or researcher is | `ViaEdge[Agent, Certainty]` (fields on the edge), and an `AnnotatedValue` (`WithCertainty[str]`) |
| Dates | An `Embedded` object (`Date`) |
| "Not so" and "perhaps" | `SemanticSpace` wrappers (`Negative`, `Hypothetical`); a `Conjunction` (`Causes`) |
| Who recorded it and when | Kept for every head node (`meta.created_by`, `created_when`, and the version) |

So the factoid structure itself needs nothing new. What the **descriptions idea** asks beyond that, and so what the
generic classes would have to be able to express (none of it factoid-specific):

- A **description** as an `Entity` that implements the same `Trait` as `Person` (works today).
- An **identification** as an ordinary `Document` relating a description to a person, with a certainty (works today).
- That **"only documents assert"** is a discipline of the project's models (an entity class has only definitional
  fields), which the generic classes allow but do not enforce.
- **Criteria** that name other models' fields, a **set as the object of an act**, and a **lens** (reading under a
  chosen set of authors, sources and thresholds) are **not** expressible today. They are generic features
  (stored searches, and a reader-side filter on who and what), to be built once for any project, not for factoids.

The test of the design is therefore: could a project with a different model of evidence (not factoids) use the same
features? If not, they are in the wrong place.

## First sketch, and what the rule changes

First sketch: a `PersonDescription` entity; candidate matches as edges
`(description)-[:CANDIDATE {score, basis}]->(Person)`; an identification as an edge `RESOLVED_AS`.

Under the rule above, a bare edge between entities is **not allowed to carry a claim**. So:

| | Sketch | Under "only documents assert" |
|---|---|---|
| The description | An entity | Still an entity, if it is **definitional**: the thing *is* its wording and criteria. It makes no claim about anyone |
| "This description is that person" | A `RESOLVED_AS` edge | A **document** (an identification): `describes: PersonDescription`, `is: Person`, with the certainty, the basis, a source, and (by the existing record) who and when. Several, conflicting, can coexist |
| Candidate matches | `CANDIDATE` edges | **Computed, never asserted**: the result of evaluating the description's criteria against the assertions in view. They may be materialised as derived edges for speed, and are always recomputable |
| "Which one is right?" | A flag | Nobody decides. A reader chooses a **lens** (below) |

## The pieces, as far as discussed

**Descriptions are entities defined by criteria.** One per distinct description, not per mention, so that many
sources point at one node (a hub, not a singleton). Sharing one is a claim only about the *slot*; it does not say the
same individual is meant (Maximilian had several secretaries). A deterministic URL from the normalised wording lets a batch upload
name it from a document's payload (the existing way of creating an entity by UUID or URL there, which is for batch
uploads; the entity is not part of the document).

**The criteria are a structured specification, not stored Cypher.** A small, validated, versioned JSON
specification ("holds office X for employer Y, overlapping this period") compiled to Cypher from a whitelist.
Stored text that is executed would be an injection risk, and a specification can be shown, edited and compared.
In Memgraph it would be kept as a string property (whether maps can be properties was not checked). It should be the
**same structure the search layer uses**, so the two are designed together (search is to come later).

**Intensional by default; freezing on request.** "The bishops Maximilian appointed" changes as appointments are
entered. A reference by criteria follows that. A researcher may also **freeze** the current result into an explicit
list of links in an assertion, when they mean *these*. Both are needed; they say different things.

**Evaluated against assertions, so against a lens.** "Bishops appointed by Maximilian" depends on which appointment
documents are believed: by whom, from which sources, above which certainty. So a query runs under a **lens**: a
chosen set of authors, sources and thresholds (and so for the candidates of a description). There is no default
truth; a lens may be shared and named ("the project's working view", "Researcher R"). This is the main new idea in
the record, and the least worked out.

**Retroactive approval, worked through.** A document records the pope's act: `grants: right to appoint bishops`,
with scope given as a description whose criteria are "appointments of bishops by Maximilian, before this date".
Entering it changes nothing about the appointments. Asking "what was retroactively approved?" evaluates the criteria
under a lens; entering a further appointment document later changes the answer. A researcher who wants to say
"these specific six" freezes the list.

**Evaluation is derived data.** Matches change when anything relevant is entered, in any order, so they are
evaluated on demand, or materialised in the background and recomputed when a hash of the criteria, or of what they
depend on, changes. The "pending derivation" mechanism proposed in [dates.md](../docs/dates.md) is the same need.
Asserted documents are data; computed candidates are a cache.

**Network analysis, three views of a description**: left out (identified people only); kept as an office or slot
node (often analytically useful: the secretariat); or replaced by its candidates with weights (`score / sum of scores`,
or `1/k`), so a candidate gets a fractional edge. Each is under a lens.

## What it needs from Pangloss

- **Nothing in core for a manual version.** A description entity that implements a trait with `Person` (as the demo's
  `Agent` does) can be the target of ordinary relations; an identification is an ordinary document with a
  relation to each, and an edge model or annotated value for the certainty. The record of who and when is already kept.
- **Later:** the search layer (to evaluate criteria), the pending-derivation mechanism, and a place for a lens
  (query parameters on reads, and perhaps a stored lens as a small entity or document of its own).
- **A relation whose target is a description of things** (the pope's act refers to "the appointments that
  match"): not supported as such; it would be a relation to a description entity whose criteria name another model.
  To check how far Pangloss's relations and traits allow it, or whether it needs its own kind.
- A watch-point: the head view of an entity lists every incoming relation, unpaged; a popular description lists every
  mention.

## Risks and cautions

- **Over-linking and false confidence**: a score that looks precise. Show the basis, not just a number.
- **Splitting**: if "the secretary" turns out to be two people, mentions that point at the description cannot be moved
  without editing the documents. Perhaps descriptions should be narrow (with period and employer) from the start.
- **Time-varying roles**: criteria must carry a period, or a description will match everyone who ever held the office.
- **Cost of lenses**: every read and every derived edge is relative to one; materialising for many lenses may not be
  affordable (to measure).
- **Circularity**: a description's criteria may depend on assertions that themselves mention descriptions.
- **What counts as definitional** is a modelling decision per class, and the rule ("nothing else on an entity")
  would need to be stated and, perhaps, enforced by the model layer (an entity with fields a reader may mistake for
  claims).

## Open questions

1. Are descriptions made freely from the wording of each source, or curated from a controlled list? (This decides how much
   deduplication matters.)
2. What exactly is a **lens**, and who may define one? Is one global default allowed, even though no one is in charge?
3. Is an identification one document kind, or a general "assertion about a description"? How does a *denial*
   ("this is not that person") appear?
4. Should the criteria language be the search language? If so, this waits for it.
5. What is definitional for a Person (an id, a label, a URL)? Are names claims?
6. How are sets referred to by a document (the pope's act) stored, if not as a relation to entities?
7. How do identifications interact with [history](../docs/history.md) (each is a document with versions) and
   with migrations (criteria written in a model's field names break when the model changes; they need migrating
   like any stored query).
