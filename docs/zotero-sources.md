# Zotero items as sources and as subjects ⏳

**Status: a design, not built.** Nothing here exists yet. It is the modelling question that [the Zotero
package](zotero.md) depends on, and it is written first because it decides what that package's model is.

## The problem

A Zotero item (a book, a letter, a charter) has to do two jobs:

- **Be the source of a factoid.** `Factoid.source` points at it, with the page (`AtPage[Source]`).
- **Be the subject of a factoid.** "This letter was sent from X to Y", "it was signed by Z", "it was written
  in 1342": the letter is what the statements are *about*, and a statement refers to an entity.

The old plugin made every `Factoid.source` point to a `ZoteroEntry` and nothing else. The strategy so far for the
second job is a separate `TextObject` entity with a link to the Zotero object. That works, but there are then two
nodes for one letter, and the question is whether they can be one.

Constraints from how Pangloss stores things (all checked in the code and docs, not assumed):

1. **A node has one class.** Its labels are its class, all its parent classes, its traits and its kind
   (`labels_for_model`), and the reader takes the first label as the class. The class is fixed when the node is
   created; the only way to change it afterwards is a migration (`RenameModel`, `AlterModelLabels`), which
   changes every node of a model, not one.
2. **A relation to a class accepts its subclasses**, and a relation to a trait accepts any class that has it.
3. **An entity can be given a URL as its id**, which is a node (`PGUrl`) with a uniqueness constraint, and a
   document's payload can *name* an entity by that URL and have it created if it does not exist yet
   (`create_inline` with `create_new`: a convenience for uploading data in batches; the entity is still its own
   head node, not part of the document). So an entity can exist before its data does.
4. **An update replaces the whole tree under the head node** and writes a new version. Anything written to an
   entity by something other than the user is overwritten by the user's next update unless it is in what they
   send back, and the sync would overwrite the user's relations if it used `Update` carelessly.
5. **`Fulfils` does not help.** It lets a class supply what another requires, so a payload can be written as
   both; it is decided by the content of one write, not a way of joining two existing nodes.

## The options

### A. Two nodes, linked (the current strategy)

```python
class ZoteroObject(Entity): ...            # plugin-controlled
class TextObject(Entity):
    zotero: ZoteroObject | None = None     # the link
class Factoid(Document):
    source: AtPage[ZoteroObject | TextObject]
```

- ➕ Nothing new to build; the plugin owns `ZoteroObject` completely.
- ➖ One letter is two nodes. A factoid whose source is the `ZoteroObject` and a statement about the `TextObject`
  refer to different nodes, so "everything about this letter" needs a query that follows the link both ways.
- ➖ Nothing stops two `TextObject`s pointing at one `ZoteroObject`, or none at all being made for a letter that
  needs one.
- ➖ The interface has to explain the pair to the user.

### B. Two nodes, one trait

Both carry a trait `Citable`, and `Factoid.source` is `AtPage[Citable]`. This lets the source be either, without a
union that lists them. It is A with a nicer type: it removes the union and none of the other costs.

### C. One class: the Zotero fields are on the project's own class (recommended)

The package does not own a class that projects link to. It gives an **abstract base with the Zotero fields**,
and the project's text class is built on it:

```python
from pangloss_zotero.models import ZoteroBacked

class TextObject(ZoteroBacked):
    """Anything that is a text: a letter, a chronicle, a charter"""
    # (project fields: language, repository, shelfmark ...)
```

`ZoteroBacked` is an abstract `Entity` with `zotero_url`, `zotero_key`, the library, the version, `item_type`,
`citation`, `bibliography`, `csl_json`, and so on; **all optional**, so a `TextObject` made by hand has none of
them. The sync writes items as the class named by a setting (`ZOTERO_MODEL`, default `"ZoteroObject"`, a concrete
class the package ships for projects that want nothing else).

Then:

- **Source and subject are the same node.** `Factoid.source: AtPage[TextObject]`; a statement about the letter
  refers to the same `TextObject`.
- **Not every `TextObject` is from Zotero.** Those made by hand have no key. The interface shows the citation
  where there is one.
- **What differs between kinds of text goes in statements, not in subclasses.** "Sent from X to Y" and "signed by
  Z" are factoids about the one `TextObject`; so no per-type `Letter` subclass is needed to hold a sender field,
  and nothing needs to change class when Zotero's item type is changed.
- **The entity id is the Zotero URL** (`https://www.zotero.org/groups/<id>/items/<key>`). Uniqueness is then
  guaranteed by the existing constraint, and a factoid uploaded before the sync has run can name the source by
  that URL: the stub is created, and the sync fills it in later. (This is what batch uploads of data from other
  places already do for people and places.)

The cases the question raised:

| Situation | What happens |
|-----------|--------------|
| A Zotero item is synced, and nobody has used it yet | A `TextObject` is created from it |
| A factoid names the item by its URL before it is synced | A stub `TextObject` (URL id, a label) is created from the payload; the sync finds it by the URL and fills in the Zotero fields |
| A user makes a `TextObject` by hand, and later wants it to be a Zotero item | They give it the item's `zotero_url` (the interface offers a search of the library). If the sync has not seen the item, it adopts the node; if the sync **has** already made a node for it, there are two nodes for one thing (below) |
| A text that is not in Zotero | A `TextObject` without Zotero fields |
| The Zotero item is deleted | The node is kept, flagged `removed_from_zotero`; it is not deleted (it is probably cited) |

**The one hard case is two nodes that turn out to be one**: a hand-made `TextObject` whose Zotero item the sync had
already created. Pangloss has no *merge entities* (re-point every incoming relation, the `PGUrl`s and the history
of one to the other, and delete it). Avoiding the case is cheap: the interface lets the user *pick* an imported
item to link to, instead of asking them to type a URL, and the sync report lists likely duplicates (the same
title). A general merge is worth building, but it is a feature of its own (it would serve people and places too),
so it is not a part of this design. See the open questions.

- ➕ One node; no link to maintain; the id is the same URL everywhere; works with batch uploads.
- ➕ Needs nothing from the model system that does not exist.
- ➖ The Zotero fields sit on the user's class, so they are editable in a form unless something stops it
  (see "Fields the sync owns", in [the package plan](zotero.md)).
- ➖ The project must name its class in a setting, and changing the class later is a migration (`RenameModel` and
  `AddField`: which is available, and does the whole set at once, which is what is wanted here).

### D. One node, promoted in place

Keep a package-owned `ZoteroObject`, and let a user turn a given one into a `TextObject` by adding labels and
changing its `type`: `pangloss zotero promote <key> --as TextObject`.

- ➕ Exactly what the question asked for ("make my TextObject also be the ZoteroObject, the latter already
  existing").
- ➖ Nothing in the models supports a node changing class. It would be a new operation in the write path (labels,
  `type`, `head_node_type` of what it owns, the history's idea of what it was), the node's views would have to be
  those of the new class, and the sync would have to keep to its own properties for ever after. It is the most
  invasive option, for a case that C removes by not having two classes.

## Recommendation

**C**, with the sync writing a class the project chooses, and the entity id being the Zotero URL.

It answers "one and the same object" without a new operation in the models, "not all text objects are Zotero
objects" with optional fields, and "the Zotero object has already been created" by never having two classes to
begin with. The cost is a field-protection question (below) and the unmerged-duplicate case.

If a project would rather keep the plugin's class apart (it does not want Zotero fields on its own classes), the
package's concrete `ZoteroObject` is option B: leave `ZOTERO_MODEL` at its default, give `TextObject` an optional
`zotero: ZoteroObject`, and use a trait if the source relation should accept both. Nothing in C stops that.

## Decided

### Subclasses of the text class

A project may have `Letter(TextObject)`, `Book(TextObject)` and so on. They inherit the Zotero fields and their
protection, a relation to `TextObject` accepts them, and they can have fields only a person fills in. What Zotero
knows of the item stays in `zotero_data`, not in typed properties on the subclasses.

- `ZOTERO_MODEL` is a mapping from item type to class, with `"*"` for the rest:
  `{"letter": "Letter", "book": "Book", "*": "TextObject"}`. A string is the same as `{"*": that}`. Startup checks
  that each class is a concrete `ZoteroBacked` subclass. A type Zotero adds later is imported as the `"*"` class.
- **The class is fixed when the node is created** (decided; it is how Pangloss stores nodes). So a node whose
  item type later changes in Zotero keeps its class and takes the new `item_type`; a node first made from a
  factoid's payload keeps the class that payload gave it. The sync fills in either and never changes a class.
  `pangloss zotero check` reports a node whose class is not the one the mapping gives now. Such a node still works
  (it is a `TextObject`). A way to change one node's class (option D) is not needed for a first version.

### Fields the sync owns are read-only

`ZoteroBacked` lists them in a meta option that accumulates (so every subclass has it), and the **API** refuses a
create or an update that changes their stored values. The form sends back what it was given, so it still works; the
exported models carry the flag, so the interface shows them read-only; the SDK goes through the API and is covered.
The sync writes through Python and is not stopped. Code that writes through Python is trusted. This is a small
feature of the models and the API, and it is not specific to Zotero.

### Deletion

Deleting in Pangloss never removes anything: the node is flagged, its id and URL stay taken, and it can be
undeleted. An entity that something refers to is not deleted, only marked. The rules follow from that, and **do not
depend on the class** (a bare `ZoteroObject` and a `Letter` are treated alike); what matters is whether the item is
used.

| Event | What happens |
|-------|--------------|
| The item is **in Zotero's trash** | Flagged `removed_from_zotero`, nothing else. It can come back, and then the flag is cleared |
| The item is **deleted for good** in Zotero, and nothing refers to it, and no person has edited it | Deleted (flagged deleted, hidden everywhere) |
| The same, but something refers to it, **or a person has edited it** (added fields or relations of their own) | Kept, flagged `removed_from_zotero`. The citation stays, so what cites it still reads |
| An item that was deleted by the sync **appears again** (restored in Zotero, or the key reused) | Undeleted, and its fields written again. (It has to be: the id is still taken, so a new node cannot be made.) |
| A **user deletes** a Zotero-backed node | Refused by the API, unless `removed_from_zotero` is set. It would only be made again, or undeleted, by the next sync. A user who wants it gone removes the item in Zotero |
| A user deletes a text object that has **no Zotero fields** | As for any entity |

"Edited by a person" is read from the node's records (the sync is the user `zotero_sync`; any other user's update
counts). The refusal of a delete is a guard that the API runs for a model; it goes with the read-only option as
the second thing a model may ask the API for.

## Open questions

1. **A merge of two entities** (re-point relations, URLs, history; delete the second). Needed for the duplicate
   case; wanted generally. Decide whether to build it before or after the package.
2. **The meta option for read-only fields, and the delete guard** (see "Decided"): their names, whether the option
   is per field or a list on the class, and what the API answers (an error, or the stored value put back). Check how
   a list-valued meta option accumulates before relying on it, and that `get` on a base class returns the
   subclass's own view.
3. **Existing nodes with the wrong class** (the mapping changed, or the item type did): only reported for now. A
   way to change one node's class would be a new operation in the write path; wait to see how often it is wanted.
4. **Should `Factoid.source` point at the text object or at a Zotero item?** With C these are the same, but the
   demo's `Source` entity is already that class: the demo's `Source` becomes the `ZoteroBacked` one, or stays and
   the demo gains a `TextObject`. Decide when the demo is brought along.
5. **Several libraries** (a personal one and a group). The key is only unique in a library, which is why the id is
   a URL that has the library in it; `zotero_library` is a field of the item. Whether they can share a class is
   fine; whether a project can have items from two libraries with different classes needs `ZOTERO_MODEL` per
   library.
