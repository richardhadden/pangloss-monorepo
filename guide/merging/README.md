# Merging duplicate entities

Sooner or later someone cannot find "John Smith", makes a second one, and documents come to refer to both. A
**merge** makes them one again: everything that referred to the second refers to the first. The second is kept,
marked as merged, so a merge can be **undone**.

This guide covers merging from Python, from the command line and over the API. The pages for it in the web
interface are not built yet 🚧. The design, and what is built, is in
[Duplicate entities](../../implementation_docs/entity-identity.md).

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
