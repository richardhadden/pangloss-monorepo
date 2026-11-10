Document written by RHadden, 2026-11-10 12:01CET

# Update to pangloss-review

The review package requires numerous updates to reflect real-world workflow.

# User package change, requiring probably widespread remodelling

- An item should be allowed to be created by multiple users, in particular:
- a human user, who was responsible for creating the data in some form, and a transformation by a new user type, ToolChain (in our workflow, we have a small LLM-based workflow for transforming text into structured data to be uploaded with the SDK)
- A ToolChain "user" should have a version and date, held separately, e.g. MyFancyToolchain is a user; a creation can be carried out by particular version and date of this.
- the SDK should allow an item to be created by an admin user using another user's username (or multiple) and a toolchain.
- It should also (I think in pangloss-review) be allowed to assign a person to review a document (also via SDK with create) when pushing as an admin. Probably, this is best done as a ReviewTask — see below later for other kinds of ReviewTask that are not just "review the whole document". ReviewTasks, even if assigned to someone, can be picked up by someone else. The Review page should have a "my tasks" filter (and allow viewing the tasks of everyone else if an admin)

- It should be possible, from the SDK, to push an object as already checked (i.e. published). Maybe change name from "Checked" to "Published"

# Unreconciled entities

- our LLM-based toolchain (via dumped data at the moment, but will work on database read solutions later) is able to suggest matching entities from candidates (via some clever string matching and structural lookups); but sometimes this fails for two reasons: a) there is no existing match; b) there are too many existing candidates and not one with a high enough probability.

- I would like to have an Unreconciled type, which creates a singleton object for something that cannot be identified. It has an "unreconciled_type" field, which is an actual Entity type allowed for that field. e.g. task_carried_out_by --> Unreconciled(type="Unreconciled", unreconciled_type="Person", label="John Smith"). This could maybe be implemented as a generic class, but would be annoying to have to type Person | Unreconciled[Person] everywhere; maybe some flag that turns on this option?

- The existence of an Unreconciled object in a head document should be a ReviewTask, even if the document is published

- An Unreconciled object (usual chip, with Unreconciled to the left) should also have a "reconcile" button to the right (use a spanner icon). When this is clicked, it opens a popup. This allows the user to select an existing person or create a new person, which will replace the Unreconciled object.

- It should, before reconciling just this object, provide a list (still in the popup, which should resize appropriately) of other unreconciled objects with the same label (or high similarity, if suitable efficient algorithms exist for memgraph and neo4j); this should be displayed as a table, e.g. if reconciling John Smith: [Person John Smith] in [Activity John Smith eats lunch] [CHECKBOX]. The user will then select which other unreconciled entities to also automatically reconcile in the background (a basic sense check). It should be possible in the model code to write a rule limiting which other unreconciled objects to suggest for reconciling in one go, e.g. they must be part of a Factoid with the same source.

- An unreconciled object can hold external URIs, and, when reconciled with an entity, they are copied (but not duplicated!) to that entity's URIs.

the process above can be carried out in a pop up from the edit page of a document. Maybe the review page could also have a "reconciliations" page, which does the same but not in a pop-up?

# Identifications as review tasks

Currently, in pangloss-demo, we have this:

class Identification[T](ReifiedRelation[T]):
    """A name in the source that has been identified: the source says "Smith", and
    this says which people that could be. The target is one `WeightedAlternative`."""

    # (on the item page, one person is shown as their chip, then `identified by`)
    _interface_meta = InterfaceMeta(collapse=True)

    identified_by: str
    target: Annotated[list[T], MinLen(1), MaxLen(1)]

(probably move Identification into pangloss-library, so it's shared more easily across packages; Identifications should also have the username of the person who identified it)

What I'd like is to have an "IdentificationByToolchain" subclass, which would function in exactly the same way as Identification (the toolchain is the user who did the identification), but additionally:

- be marked as a ReviewTask: the idea being, a toolchain (linked!) can suggest probabilities for candidates, and instead of not being able to distinguish, offer these probabilities as a preliminary suggestion, to be reviewed.
- when editing its containing document, there should be a user button to confirm that it's correct (before or after they have corrected it)
- an IdentificationByToolchain should optionally hold external URIs to be applied to a single candidate once a person has reviewed it (can't add it to multiple options as a) would be wrong and b) impossible to use same uri for multiple entities). Therefore, once a user has confirmed the IdentificationByToolchain *and* there is only one candidate, that URI can be copied to the actual candidate.

- Similar to the Unreconciled workflow, it would be useful to be given options of where similar IdentificationByToolchain objects occur: same suggestions, more or less equal probabilities — thus can be all changed en masse to the human-verified identification — and offer these in a pop-up or Review page workflow task.
