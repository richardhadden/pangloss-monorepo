# 3. What happens for each kind of change

This is the reference for "I changed my model like *this*: what will Pangloss do to my data, and what will it ask?"

Each table gives the change, what happens to existing data, and its safety (see [chapter 1](01-ideas.md#how-safe-is-a-change)). **Asked** means `makemigrations` prompts you; **in the file** means there is an option you can set by editing the migration (see the end of this chapter).

Everything here is applied in a **single transaction per migration** (with the exception of indexes and constraints), so a migration that fails part way leaves the data as it was.

## Models

| You change | What happens | Safety |
|------------|--------------|--------|
| Add a model | Nothing to the data | safe |
| Remove a model | All its nodes are deleted, with everything they own (nested documents, embedded objects) and their creation/update records | **lossy** |
| Rename a model | **Asked** if it is a rename. Nodes are relabelled and their `type` updated (as is the `head_node_type` of what a renamed document holds) | transforming |
| Add or remove a parent class or trait | The matching label is added to, or taken off, the model's nodes | transforming |
| Change the kind (an `Entity` becomes a `Document`, or the reverse) | **Not allowed**: `makemigrations` refuses. They are stored differently. Keep the kind, or make a new model and move the data | not allowed |

Subclasses carry their parents' labels, so a change made to a model applies wherever it is used, including to subclasses and to documents nested inside other documents.

## Plain fields (strings, numbers, dates, enums, lists of these)

| You change | What happens | Safety |
|------------|--------------|--------|
| Add an optional field (`str \| None`), or a list | Nothing: existing records have no value | safe |
| Add a **required** field | **Asked** for a value; every existing record gets it | additive |
| Remove a field | The property is removed from every node | **lossy** |
| Rename a field | **Asked** if it is a rename. The values move across | transforming |
| Make a field optional | Nothing | safe |
| Make an optional field required | **Asked** for a value; records with no value get it | additive |
| Change its type | Each value is converted (see below) | transforming |
| Change the type of a list's items | As above, for every item | transforming |

### Converting a type

These conversions are understood:

| From | To |
|------|----|
| `str` | `int`, `float`, `bool` (`true` / `false`), `Decimal`, `date` (ISO text), an enum (the text must be the value of a member) |
| `int` | `float`, `str`, `Decimal`, `bool` (non-zero is true) |
| `float` | `int`, `str`, `Decimal` |
| `bool` | `str`, `int` |
| `Decimal` | `str`, `float`, `int` |
| `date` | `str` |
| an enum | `str` (the member's value as text), another enum (by member name, or by `mapping` of member names) |

Any other pair (for example `datetime`, or an enum to `int`) is refused: write it by hand ([chapter 6](06-by-hand.md)). A conversion can be lossy in practice (`float` to `int` drops the fraction), so the migration is marked as one that may not be undone exactly.

By default, if *any* value cannot be converted the migration **fails before changing anything**, and tells you how many, so nothing is half-done. To say what to do with values that do not convert, edit the migration and set `on_failure`:

```python
{'change': 'AlterLiteralType', 'model': 'Person', 'name': 'born', ...,
 'on_failure': 'null'}       # such values become empty (the field must be optional)
 # or 'default', together with  'default': 0
```

For an enum that changes to another enum, say which new member each old value becomes with `mapping`:

```python
 'mapping': {'DRAFT': 'PENDING', 'FINAL': 'DONE'}
```

### Enums

An enum field is stored as the **value** of the member (`Colour.RED = "red"` is stored as `"red"`; a number if the value is one), as an ordinary property. Nothing is made in the database for the enum, and its *name* and its members' *names* are not stored at all. So:

| You change | What happens |
|------------|--------------|
| Add an enum, or a member | Nothing to the data |
| Rename a member (same value) | Nothing to the data, and **not asked**: a removed member and an added one with the same value are taken for a rename |
| Change a member's **value** (`GREEN = "green"` becomes `"verde"`) | Every stored `"green"` of that enum becomes `"verde"`, wherever it is kept: a field, a list, inside a `TypedDict`, an annotated value, or on an edge. The text `"green"` in a plain `str` field is not touched |
| Rename a member *and* change its value | **Asked** if it is a rename; if so, both of the above |
| Remove a member | **Asked** which member the values that had it become (or nothing: then it fails, saying where, if any do) |
| Rename an enum | **Asked** if it is a rename. Nothing to the data |
| Remove an enum | Nothing to the data |

The values of an enum must be strings or numbers (Pangloss checks this when the models start). Because an enum is only its values, all enum changes are ordinary updates: they run in the migration's transaction, can be tried by `--dry-run`, and can be undone.

### Annotated values

An *annotated value* is a value with extra fields of its own (for example a colour with a `certainty`).

| You change | What happens | Safety |
|------------|--------------|--------|
| A plain field becomes an annotated value | The value is wrapped. **Asked** for the extra required fields, for the values that exist | transforming |
| An annotated value becomes a plain field | The value is taken out; the extra fields are dropped | **lossy** |

## Relations

A relation to an entity is a pair of edges (forward and reverse). Relations to documents, reified relations and semantic spaces own the nodes they point to. Pangloss keeps both edges and any derived data consistent.

| You change | What happens | Safety |
|------------|--------------|--------|
| Add a relation | Nothing. Existing records have no target. If the relation is required, records without one cannot be read: `check-data` will list them | safe |
| Remove a relation | Its edges (forward and reverse) are deleted. For a relation to **documents**, the nodes it owned are deleted too. **Entities are kept**: only the link goes | **lossy** |
| Rename a relation | **Asked** if it is a rename. Both edge types are renamed, keeping their properties | transforming |
| Change its reverse name | Reverse edges are renamed | transforming |
| Widen what it may point to | Nothing | safe |
| Narrow what it may point to | Fails if any edge points to what is no longer allowed. **In the file**: `on_narrowing: 'remove'` deletes those edges instead | **lossy** |
| List becomes a single value | Fails if any node has several. **In the file**: `keep: 'first'` keeps the first edge and removes the others | **lossy** |
| Single value becomes a list | Nothing | safe |
| Add properties to the edges (an edge model) | **Asked** for values for the required ones, for the edges that exist | additive |
| Remove them | The properties are removed | **lossy** |

A relation that **narrows a field of a parent class** is stored as two edge pairs. Adding, removing or changing this is handled for you.

### Wrapping a relation

You can wrap what a relation points to, for example `person: Person` becomes `person: IdentifiedAs[Person]`, where `IdentifiedAs` is a *reified relation* (a relation with data of its own, such as `certainty`).

| You change | What happens | Safety |
|------------|--------------|--------|
| Wrap in a **reified relation** | A new node is inserted on every existing edge. **Asked** for the wrapper's required fields, for the relations that exist. The result is exactly what the new model would have written (labels, `head_node_id`, creator and times, context labels) | transforming |
| Unwrap it | The nodes are removed and the edges join up again. The wrapper's own fields are lost | **lossy** |
| Wrap in a **semantic space** | A node for the space is inserted, and the semantic spaces and context labels of everything inside are recomputed | transforming |
| One reified relation or space for another | Nodes are relabelled; new fields get **asked** values; fields the new one lacks are dropped | transforming |
| Wrap in a **conjunction** | **Refused when applied, always.** A conjunction has several slots, and nothing says which one an existing relation should fill. Write it by hand ([chapter 6](06-by-hand.md)) | needs code |

### Embedded objects

| You change | What happens | Safety |
|------------|--------------|--------|
| Some literal fields become an embedded object | A node is made for each owner, the values moved into it. **Asked** for the embedded object's other required fields | transforming |
| An embedded object becomes plain fields | The values are copied out and the node deleted; its other fields are lost | **lossy** |
| Add an embedded object (not made of fields that were there) | A node of it is made for each owner that exists. **Asked** for the values of its required fields. Refused when it could be any of several kinds (which one is not known) | additive |

## `Fulfils`

A class declared `Fulfils[X]` supplies what `X` requires, and a node of it that holds everything `X` needs also carries `X`'s labels. If you add or remove `Fulfils[X]`, or change what `X` requires (or its labels), the labels of the existing nodes are worked out again: a node gets the labels of the classes it fulfils now, and loses those of the classes it no longer does. Nothing is asked, nothing is lost, and the migration can be undone. A node counts as fulfilling `X` if it has a value for each field `X` requires (a property that is set, an edge that is there); a Python validator on one of `X`'s fields is not checked.

## Indexes and constraints

Pangloss itself needs some indexes and uniqueness constraints (on ids, on user names, the text index used for searching labels). They are migrations like any other, shipped by the `pangloss_memgraph` package in its own `migrations/` folder, so a project does not write them. If a newer Pangloss needs another, you get it as a normal pending migration: `pangloss migrate` makes it.

## What is not handled automatically

**Not allowed** (`makemigrations` refuses, and says what):

- changing the **kind** of a model (an `Entity` that is a `Document`, or the reverse) or of a field (a plain value that is a relation, and so on). They are stored differently. Keep the kind, or make a new model or field, move the data to it by hand, and remove the old one.

**Found, but refused when applied** (`migrate` stops before changing anything, `--plan` shows them and `--dry-run` says `WOULD FAIL`), so you write them by hand ([chapter 6](06-by-hand.md)):

- wrapping in a **conjunction**;
- adding an **embedded object** that could be of several kinds (which one to make is not known);
- a **type conversion** Pangloss does not know (see the table above).

## Editing the answers in the file

The questions `makemigrations` asks are answered in the file for you. The other options are fields on the change, left empty (`None`) until you set them. Open the migration and add them to the change's dictionary:

| Field | On | Values |
|-------|----|--------|
| `default` | add a required field; make a field required; convert with `on_failure: 'default'` | a value of the field's type |
| `defaults` | wrapping; changing a wrapper; annotated values; edge models; embedded objects | `{'field_name': value, ...}` |
| `on_failure` | change of type | `'fail'` (the default), `'null'`, `'default'` |
| `mapping` | enum to enum | `{'OLD': 'NEW', ...}` |
| `keep` | list to single value | `'first'` or `'fail'` |
| `on_narrowing` | a relation that may point to less | `'fail'` or `'remove'` |
| `replacement` | removing an enum member | the member name to give the values |

Dates are written as ISO text (`'2024-05-01'`), and decimals as text (`'3.14'`).

A change that needs an answer and has none *cannot be applied*: `migrate` stops, before changing anything, and says which answer is missing.
