# Merging duplicate entities

Sooner or later someone cannot find "John Smith", makes a second one, and documents come to refer to both. A
**merge** makes them one again: everything that referred to the second refers to the first. The second is kept,
marked as merged, so a merge can be **undone**.

This guide covers merging in the web interface, from Python, from the command line and over the API. The design,
and what is built, is in [Duplicate entities](../../implementation_docs/entity-identity.md).

A database made before merging existed needs `pangloss migrate` once (it adds indexes).

## What a merge does

Merging B (the *absorbed* entity) into A (the *survivor*):

- Every relation that pointed at B points at A, with its place in its list and its edge properties. A document
  that named both in one list names A once; the result lists such documents for you to look at.
- A has the fields you choose. If you choose nothing: A's own values, B's where A has none, and both of every list.
  A has the URLs of both.
- B is not changed, only marked. Its id still works: reading it gives A, and a write that names it is made with A.
  A write *addressed to* B (an update, a delete) is refused, naming A.
- Each document that changed has a new version, as after an edit, and history records it.

A `Person` can be merged with a `Poet(Person)`; the survivor is then a `Poet`, unless you say otherwise. A `Person`
and a `Place` cannot be merged.

## In the web interface

The pages come with `pangloss_interface`; they are for someone logged in.

1. Open the page of the entity that should **stay**, and choose **Merge with…** in the bar at the top (the icon of
   two lines joining). Find the duplicate in the box.
2. The two are shown side by side, a row for each field. For each row choose whose value the survivor has: **Stays**,
   **Absorbed**, or for a list **Both**. The label can also be typed. **Swap the two** turns them round.
3. Under the rows the page says how much refers to each, which documents name both (they will name the survivor
   once: look at them afterwards), and how many documents the merge writes.
4. **Merge** asks once more, and then says what it did. If you may not merge alone (see "Who may merge"), write why
   the two are one and choose **Propose the merge**: someone else opens it from **Merges** in the navigation bar, or
   from the notice on either entity's page, and verifies or rejects it.

The address of the absorbed entity now shows the survivor, with a notice that says so and leads to the merge.

**To undo**, open the merge (from that notice, from **Merges**, or from **Merge with…** on the survivor, which lists
its merges). The page says what would go back, what cannot, and what was written to the survivor since the merge,
which stays on it. **Undo the merge** asks once more. Someone who may not undo alone proposes it, and someone else
undoes it or leaves it merged.

An admin sees the merges made lately on `/admin`, and can run **Check references to merged entities** there.

## In Python

```python
preview = await Person.merge_preview(absorb=b_id, into=a_id)
if preview.possible:
    result = await Person.merge(absorb=b_id, into=a_id)
    print(result.merge.id, result.merge.moved, [head.label for head in result.collapsed])
else:
    print(preview.refused)
```

`merge_preview` writes nothing. It says whether the merge can be made (and if not, why), how many documents it
would write, and the fields the survivor would have (`preview.values`). To choose the fields yourself, change them
and pass them back:

```python
values = {**preview.values, "label": "John Smith of Leith"}
await Person.merge(absorb=b_id, into=a_id, values=values)
```

To undo, with the id of the merge:

```python
undone = await Person.unmerge(result.merge.id)
```

The references the merge moved go back to B, where the document that held each is still there and still points at
A. What could not be put back is in `undone.unmatched`. What was written to A *since* the merge stays on A, and is
listed in `undone.made_since`: some of it may have been meant for B, and only a person can tell. A's own fields are
put back if A has not changed since the merge; otherwise they are given in `undone.draft` for you to reconcile.

`await Person.merges(id)` lists the merges an entity is part of.

The same functions work in a script that uses [the SDK](../sdk/README.md), if the server lets your user merge.

## From the command line

```sh
pangloss merge Person <survivor id> <absorbed id> --user ann --dry-run
pangloss merge Person <survivor id> <absorbed id> --user ann
pangloss merges
pangloss unmerge <merge id> --user ann
```

For a clean-up, put the pairs in a file, a line each (the survivor's id, then the absorbed entity's), and run
`pangloss merge Person --pairs pairs.txt --user ann`. The first pair that cannot be merged stops the rest.

## Who may merge

The setting `MERGE_DIRECTLY` says who merges, and undoes a merge, without anyone else:

| Value | Who |
|---|---|
| `"admin"` (the default) | Admins |
| `"any"` | Every logged-in user |
| `"none"` | Nobody |

Everyone else **proposes** a merge, and a **different** user verifies it, which carries it out (or rejects it,
with a reason). Undoing follows the same rule. The commands above are not subject to the setting: whoever can run
`pangloss` on the server can merge.

A merge that would write more than `MERGE_LIMIT` documents (1,000) is made only by an admin over the API, or with
`pangloss merge --large`. Up to the limit a merge is one transaction: it happens completely or not at all.

## Over the API

All of these need a login.

| | |
|---|---|
| `POST /api/Person/{survivor}/merge/preview` | What it would do. Body: `{"absorb": "<id>"}` |
| `POST /api/Person/{survivor}/merge` | Merge. Body: `{"absorb", "values"?, "asClass"?, "versionInto"?, "versionAbsorb"?}` |
| `POST /api/Person/{survivor}/merge/propose` | Propose it (`"note"` says why) |
| `GET /api/merges?open=true` | Proposals waiting for someone |
| `POST /api/merges/{merge}/verify`, `/reject` | Carry out a proposal, or reject it |
| `POST /api/merges/{merge}/undo` | Undo (`{"dryRun": true}` says what would be undone) |
| `POST /api/merges/{merge}/undo/propose`, `/undo/reject` | Propose an undo; reject that |

`versionInto` and `versionAbsorb` are the versions of the two entities you looked at: if either has changed, the
merge is refused with 412, as an update is.

## Relations a merge should leave alone

A statement that says "A is the same person as B" must still say so after B is merged into A, not "A is the same
as A". Mark such a relation with `KeepOnMerge()` (or `IdentityClaim()` from `pangloss-library`), and a merge leaves
it pointing at B:

```python
class SameAs(Document):
    entities: Annotated[list[Person], MinLen(2), MaxLen(2), KeepOnMerge()]
```

## Saying two are the same without merging them

A merge is a decision. Before it, a source (or you) may only *say* that two people are one, and another source may
say they are not. `SameEntity` from `pangloss-library` is a statement for that:

```python
from pangloss_library import SameEntity


class Factoid(Document):
    statements: list[Statement | SameEntity[Person] | Negative[Statement | SameEntity[Person]]]
```

```python
{"type": "SameEntity", "label": "The John of both charters", "target": [a, b], "argument": "The same seal"}
```

The page of each person then lists, above everything else, who they are **said to be the same as**, with the
statements that say so; those inside a semantic space are listed under its name ("in Negative"). Someone logged in
has **Compare, or merge** beside each. After a merge the statements still name both, the absorbed one as "merged
into this".

Your own statement class works the same way if its relation is marked `IdentityClaim()`.

## Keeping the absorbed entity's name

B's label still finds A in the autocomplete. To have it shown on A as well, name a list field for it to go into by
default:

```python
class Person(Entity):
    _meta = Entity.Meta(merge=MergeRules(label_into="aliases"))
    aliases: list[str] = []
```

## If something looks wrong

`pangloss check-data` reports references that are still on a merged entity (something wrote them without going
through the models) and merges that stopped part of the way. `pangloss check-data --move-merged --user ann` moves
the first to the entities they belong to.

Typology types that have subtypes are merged in the typology (`pangloss typology merge`), which keeps the hierarchy.
An item of a Zotero library is never the one absorbed: merge the other entity into it.
