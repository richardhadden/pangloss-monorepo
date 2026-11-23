# Editing together ⏳

*An initial specification, written 2026-11-23 at the user's request. **Nothing here is built**, and nothing is
decided beyond the first section. It is a later feature: it is written down now because Pangloss's own toolchain
(the build plan's [step 10.5](similarity-build-plan.md)) makes the case for it sharper.*

## What the user asked for

Two people can edit the same document at once and each sees what the other does, as it is done. The same view
serves a document that something in the background changes while a person has it open in a form: a worker that
puts a suggested identification in the place of an unidentified mention, a criteria or derived worker, a
toolchain's update over the API.

## What happens today

- Every head has a version, and an update says which version it is based on (`If-Match`). A form that saves over a
  version that has moved on is refused (412) and nothing is written: the person reloads and makes their changes
  again. Nothing is lost quietly, and nothing is merged.
- A form does not know that its document has changed until it saves.
- Pages already follow the server through `live()` feeds (the review panel, the criteria card, the admin page, the
  typology tree): a page learns of a change of its head without asking again. A form does not use one.
- Unsaved changes are warned about on leaving, and a new document's unsaved state can be stashed.

## The feature, in three sizes

Each is useful without the next, and each is the ground the next stands on.

1. **A form knows.** An open form follows a feed of its document. When the version changes underneath it, the
   form says so (who, when, and which parts changed), before the person saves. This is a notice only.
2. **A form can take the change.** The person takes the new version into the form: parts they have not touched
   become the new version's; parts they have changed stay theirs, and are marked where the other version changed
   them too. Saving is then based on the new version. This is what a background worker needs: its change is
   nearly always to a part the person is not editing.
3. **Editing together.** Each person's changes reach the other as they are made, before either saves, with
   something to show who is where (a cursor, a mark on the field being edited). Saving is no longer one person's
   act on a private copy.

## Questions the design has to answer

- **What a part is.** An update replaces the whole document below its head, and nested nodes are written again.
  Taking a change part by part needs parts that can be told apart across versions: by the ids of nested nodes
  (which an update keeps when they are sent back), by field, or both. What does the history's diff already give?
- **Where an unsaved edit lives** in size 3: in each browser and relayed, or on the server as a draft of the
  document that several people write to. A draft on the server is a new kind of stored thing, with its own rules
  for who may see it, how long it lasts, and what review and publishing mean for it.
- **How changes are joined.** Field by field with the last writer winning; by operations that can be replayed in
  any order; or by a library made for it. Long text fields are the hard case; references and lists of nested
  documents are the common one.
- **The transport.** The `live()` feeds are the server telling the page. Size 3 needs the page telling the server
  as often, and telling the other pages.
- **Validation.** A document that is half edited by two people is often not valid. When is it checked, and whose
  error is it?
- **History and versions.** Is every relayed change a version, or only a save? Whose name is on a version two
  people made?
- **Permissions and review.** Protected fields, a document under review, a reader who may see a draft of something
  not published.
- **What else writes.** The workers (criteria, derived, vectors' marks, the toolchain of 10.5) and API clients:
  are they participants like a person, or do they wait while a document is being edited?
- **Both backends, and the SDK.** Nothing here should need one database's features; and what does a client of the
  SDK see of a document being edited?

## What it would touch

`pangloss-interface` (the form's state, the feeds), `pangloss-api` (a feed for a document's versions; for size 3
a channel in both directions), `pangloss-history` (the diff between versions, the record of who changed what),
and possibly the core's write path (a draft). The optional packages' form parts (review, criteria, dates) would
have to behave when the value under them changes.

## A first step, when this is taken up

Read how the history's compare page tells two versions apart, and whether that diff can be laid over a form's
unsaved state: sizes 1 and 2 depend on it and need nothing new stored. Then decide between a draft on the server
and relayed edits, which is the decision everything in size 3 follows from.
