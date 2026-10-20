# Database migrations ⏳

**Status: a specification. Nothing here is implemented.** It describes how changes to the models could be applied to data that is already in the database, and what that needs. (Progress so far: see [Progress](#12-progress).)

## 1. The problem

The models are Python classes; the data is a graph that was written *by an earlier version of them*. When a model changes, three things can stop agreeing:

1. **The data and the new models.** A field was renamed, a type narrowed, a relation wrapped in a new object. The old data can no longer be read (`HeadView(**data)` fails), or can be read but is wrong.
2. **The database's own structure**: indexes, uniqueness constraints, the text index and the Memgraph enums that `initialise_database()` makes (`memgraph.md`). It only *adds* (it cannot remove an enum member, or drop what is no longer used).
3. **Derived data** that is stored, not computed: `head_node_id`/`head_node_type`, `meta.semantic_spaces`/`context_labels`, the `PGUrl` nodes, the reverse edges. A structural change has to keep these true.

A migration is a recorded, ordered, repeatable change that takes the database from one version of the models to the next.

**Goals**

- Most changes are *detected* from the models and written as a reviewable migration file, as in Django.
- Changes that are not safe or not obvious (a rename, a lossy conversion, a new required value) ask a person, and the answer is kept in the file.
- A migration is **code in version control**, run in order, once, and recorded in the database.
- It works on the graph as a graph: whole-database, set-based Cypher, not a load-and-resave of every document through the models.
- Large databases: resumable, batched, with a dry run and a backup.

**Non-goals (for a first version)**: zero downtime (the API is stopped, or put into read-only, while a migration runs); migrating *between* database backends; an "undo" for lossy changes (only what can be reversed is reversible).

## 2. What is stored, and so what a change touches

A change to a model is a change to one of these. (From `memgraph.md`, confirmed against the demo database.)

| In the model | In the graph |
|--------------|--------------|
| A class | Labels on its nodes: its name, every parent class and trait name, its kind (`Document`, `Entity`, `Embedded`, `ReifiedRelation`, ...), `PGIndexableNode`; `HeadNode` on top-level nodes. Property `type` is the class name |
| A `str`/`int`/`float`/`bool`/`date`/`datetime`/list literal | A node property of the field's name (absent when `None`) |
| `Decimal` | A string property |
| An `Enum` | A native Memgraph enum value (`ActivityType::MEETING`), and a database-level enum that must exist |
| A `TypedDict` | A map property |
| An `AnnotatedValue[T]` | A map property `{value: ..., <extra fields>}` on the node |
| A relation to an Entity | A forward edge `(a)-[:field]->(b)` and a reverse edge `(b)-[:field_reverse {reverse: true}]->(a)`; the reverse name is `RelationConfig.reverse_name` or derived |
| A relation to a Document | The same pair of edges, to a node that is part of the same document: it has `head_node_id`/`head_node_type` |
| An `Embedded` field | A node (`Date`, labels `Embedded`, ...) joined by the same edge pair, with its literals as properties |
| A `ReifiedRelation[T]` field | A node of the relation class (`AtPage`, labels `ReifiedRelation`) with its own literals; edges `(a)-[:field]->(r)` (and `field_reverse` back) and `(r)-[:target]->(b)` (and `(b)-[:target_reverse]->(r)`) |
| A `SemanticSpace[T]` / `Conjunction` | A node, joined to its contents by `contents` (or the slots `cause`, `result`...). Everything inside it has `meta.semantic_spaces` and `meta.context_labels` |
| `ViaEdge[T, Edge]` | The edge model's fields as properties of **both** edges of the pair |
| A field that narrows a parent's field (`subclasses_parent_fields`) | The edge pair is written **again for each parent field**: `carried_out_by` and `involves` both exist, with the same properties |
| `create_with_id` + `accept_url_as_id` | `PGUrl {url}` nodes, linked by `has_url`, with a uniqueness constraint |
| `Fulfils[...]`, traits | Extra labels on the node |
| `label` | A property, and the text index `label_text` on `PGIndexableNode(label)` |

Not changed by a model change, and so never migrated: `PGCreation`, `PGUpdate`, `PGDeletion` and `PGUndeletion` (they record who and when, not the content), `PGUser`. There is **no stored history of the content of a document** (`PGUpdate` is an audit record, not a version), so a migration does not have older versions to rewrite.

Two consequences shape everything below:

- **A model is identified by its class name.** Labels and `type` are the class name, and the registry is keyed by name. A renamed class is a different class unless a migration says it is the same; two apps may not have models of the same name.
- **A field is a name in a model, and the name is the edge type or property key.** A rename is a rename of data, and cannot be told from "remove one, add another" by looking at the models alone.

## 3. Keeping track of the previous state

A migration compares *what the models were* with *what they are*. The old Python classes are gone, so the old state has to be kept as data.

### 3.1 The schema snapshot

A **schema snapshot** is a plain, JSON-serialisable description of the models, as they are stored. `pangloss_models.export.export_models()` (made for the interface, and described in `interface.md`) is the start of it: every model, its kind, parent, concrete subtypes, fields with their kind, types, validators, the types a relation can be to (through reified relations, semantic spaces and conjunctions), the reverse names, and the enums.

It has to hold *what is needed to write migrations*, which is more than what the interface needs. Add:

| Add to the export | Why |
|-------------------|-----|
| **Labels** of each model (class, parents, traits, `Fulfils`, kind) | to find its nodes, and to see that a label changed |
| **Storage** of each field: `property`, `map_property`, `edge`, `embedded_node`, `reified_node`, ... | what to rewrite |
| **Edge type names**: the forward name, the reverse name, and the extra edges of a narrowed parent field (`subclasses_parent_fields`) | edges are renamed, and removed, by name |
| The **edge model** and its fields | properties on edges |
| **`create_with_id`, `accept_url_as_id`** | `PGUrl` nodes |
| **Declaration order** (it is used to resolve generics) | to compare like with like |
| **Resolved generics**: the concrete type options of each parameter (`IdentifiedAs[Person]` is `IdentifiedAs` with `Target = {Person, Student}`) | a change of `Person` to `Person | Group` changes what edges may point at |
| A stable **model identity** and **field identity** (see 5.3) | renames |
| A **hash** of the whole snapshot | cheap "has anything changed" |

Not stored: validators that do not change data (`Ge(0)`, `MaxLen`) are kept for reporting, but are not in the hash that decides whether a migration is needed (changing them is a *check*, see 4.4).

### 3.2 Where it lives

**In the repository, per app**, as migration files, like Django: the state is not a file of its own, it is the result of replaying the migrations.

```
demo_app/
  models.py
  migrations/
    __init__.py
    0001_initial.py          # creates every model as they were
    0002_identified_as.py    # WrapInReified(...)
    0003_...py
```

Each migration file has:

```python
class Migration(MigrationBase):
    dependencies = [("demo_app", "0001_initial")]       # also other apps' migrations
    operations = [
        operations.WrapInReified(
            model="Statement", field="person", wrapper="IdentifiedAs",
            defaults={"certainty": 3},
        ),
    ]
```

Each **operation** describes a change in *both* worlds: `state_forwards(state)` changes the snapshot, and `database_forwards(tx, state)` changes the data. So replaying the operations from `0001` gives the snapshot as it was after any migration, without the old classes. A migration also stores the **hash of the snapshot it leaves**, as a check that replay and the operations agree.

> Why not store a full snapshot per migration? It is simpler to read and to diff, but a second source of truth that can disagree with the operations. The hash gives most of its checking for none of the duplication. A tool may *also* write `0002.snapshot.json` for review.

### 3.3 What the database records

The graph says which migrations have been applied, and guards against two running at once:

| Node | Properties |
|------|------------|
| `(:PGMigration)` | `app`, `name`, `applied_when`, `applied_by`, `checksum` (of the operations as written), `schema_hash` (the snapshot after it), `status` (`running`, `applied`, `failed`), `cursor` (for a resumable one), `duration` |
| `(:PGMigrationLock)` | one; created with a uniqueness constraint, so a second `migrate` fails at once |

At start-up `pangloss run`/`dev` compare, for each app, **the hash of the current models' snapshot** with the `schema_hash` of the last applied migration. If they differ the server **refuses to start** (or starts read-only, a setting): either a migration is pending or the models have changed without one. This is the safety that stops a new model reading old data.

## 4. Finding what changed

`pangloss makemigrations` loads the current models (`initialise()`, no database), builds the snapshot, replays the existing migrations to get the old one, and **diffs** them into a list of operations.

### 4.1 The diff

Nodes of the comparison are models and fields, matched by their identity (5.3). For each pair:

1. **Models** only in the new: `CreateModel`. Only in the old: `DeleteModel`. In both: compare kind, parents, traits, abstract.
2. **Fields** of a model, matched by name: only in the new, `AddField`; only in the old, `RemoveField`; in both, compare storage, type and options, and emit the operation for what differs.
3. **Database structure** (indexes, constraints, enums, text index) is derived from the snapshot, and diffed the same way, so `initialise_database()` and a migration cannot disagree.

Then the operations are **ordered** (create models and enums before fields that use them; add before wrapping; remove last) and **merged** where one change is several differences (a rename seen as a removal and an addition, 4.2; a parent field and the field that narrows it, 5.4).

### 4.2 What cannot be known from the models

| Ambiguity | Why | Resolved by |
|-----------|-----|-------------|
| Renamed, or removed and added? | the names differ; so may be nothing else | **Always asked, on the command line.** `makemigrations` never infers a rename. When a field (or model) disappears and one of a compatible type appears in the same model, it asks `Was 'born' renamed to 'birth_date'? [y/N]`; a *no* is a removal and an addition (which loses the data). An explicit hint in the models, `Annotated[int, RenamedFrom("born")]` or `Entity.Meta(renamed_from="Human")`, is also an answer, and is also confirmed on the command line. In a non-interactive run a possible rename is an error (`--rename old=new` gives the answer) |
| A class moved to another module or app | identity is the name | none needed if the name is kept; a rename needs the hint |
| What value to give existing nodes for a new required field | the model has no default for the *old* data | **Ask**, or `Field(migration_default=...)`; written into the migration |
| How to convert a changed type | `str` to `int` may not parse | **Ask** for the conversion, or choose "fail on a value that does not convert" / "set to null" / "drop" |
| What a new object wrapping a relation should contain | `IdentifiedAs.certainty` has no value for old edges | **Ask** for the `defaults` |
| Which one to keep when a list becomes a single value | there may be several | **Ask**: first by creation order, or fail |

`makemigrations` is interactive in a terminal, takes answers on the command line, and refuses to guess in a non-interactive run. Nothing is written until the person has seen the operations.

### 4.3 Operations are written for the model, not for one place

A field is declared once, but used wherever its model is: a field of `Statement` is on `Activity` and `Transfer` too (they are `Statement`s, and so have the label `Statement`); a field of an `Embedded` `Date` is on every node of that class, wherever it hangs. So operations address **a model and a field** (`Statement.person`) and select by **label** (`MATCH (n:Statement)`), not by path through a document. That keeps one operation for one declaration, however deep or often it is nested, and it keeps the operation independent of which classes exist now.

The current classes **are not imported by a migration.** It is run against the snapshot (`state`) as it was at that point: `state.model("Statement").labels`, `.field("person").edge_type`. This is what lets old migrations keep working after the models have moved on.

### 4.4 Changes that need no data change, but a check

A change of **validators** (`Ge(0)`, `MaxLen(10)`, `Annotated[str, MinLen(5)]`), of `require_label`, or of a description changes no data but may make existing data invalid. These produce no operation. `pangloss check-data` (a new command; also run by `migrate`) reads every head node through its current `HeadView`, and reports each document that fails and why. It is the verification step after every migration, too.

## 5. The kinds of change

For each: how it is **detected** (from the diff), what it does to **data**, and how safe it is.

| Safety | Meaning |
|--------|---------|
| **S** safe | no data change; or only structure (an index) |
| **A** additive | data is added; needs a value |
| **T** transforming | data is rewritten; reversible if the information is kept |
| **L** lossy | data is removed, or cannot be converted back |
| **M** manual | needs a decision, or hand-written code (`RunCypher`/`RunPython`) |

### 5.1 Models

| Change | Detected as | Data | |
|--------|-------------|------|---|
| Add a model | in new only | none (maybe indexes, enums) | S |
| Remove a model | in old only | `DETACH DELETE` its nodes, and the reverse edges that point at them; every field that referred to it must be gone first (the diff orders this). Documents hold the nodes of their tree, so removing a *nested* model changes the documents that contain it | L |
| Rename a model | hint, or asked | change the label and `type` on every node; relabel in `context_labels` of nodes in semantic spaces; edge types are unchanged | T |
| Add or remove a **parent class** or **trait** | parents/traits differ | add or remove the label on every node of the model (and so what a query for the parent finds) | T |
| Change the **kind** (Document to Entity, Embedded to Document...) | kind differs | **M**. A Document is nested in its head and an Entity is not: the node gains or loses `head_node_id`, `HeadNode`, its own `PGCreation`, and a parent that held it by edge keeps it by reference. Written by hand | M |
| `abstract` on or off | meta differs | none (it decides what can be written, and what a relation to the parent allows) | S |
| `create_with_id`, `accept_url_as_id`, `create_inline` | meta differs | removing `accept_url_as_id` leaves `PGUrl` nodes (kept, or dropped by choice) | S |
| `require_label` on | meta differs | existing nodes with no label need one: **ask** (a default, or a field to copy) | A |
| Add/remove the **text index** or an index | derived | DDL | S |

### 5.2 Literal fields

| Change | Data |
|--------|------|
| **Add**, optional | none: an absent property is `None` | S |
| **Add**, required | set the property on every node of the model (and its subtypes) to the given default. Batched | A |
| **Remove** | `REMOVE n.field`. Reversible only if the values are saved | L |
| **Rename** | `SET n.new = n.old REMOVE n.old` | T |
| **Optional to required** | ask for a default for nodes without it, then as "add, required" | A |
| **Required to optional** | none | S |
| **Move up** to a parent class | none (the label of the parent is already on the nodes) | S |
| **Type**, widening (`int` to `float`, `str` to `list[str]`) | convert in place: `SET n.f = toFloat(n.f)`; `[n.f]` | T |
| **Type**, narrowing or incompatible (`str` to `int`, `float` to `int`, to a `date`) | per node conversion with `toInteger`, `date(...)`; a value that does not convert fails the migration, or is set to null/default (a choice, written in the migration) | T / L |
| **To or from `Decimal`** | stored as a string: convert to `toString(...)` / `toFloat(...)` | T |
| **To an `Enum`** | create the Memgraph enum (a database-level step, 5.6), then `SET n.f = ToEnum('Name', 'MEMBER')` using a mapping of old values to members. Tested (see 11) | T |
| **From an `Enum`** | the reverse: `split(toString(n.f), '::')[1]` is the member name, mapped to the new value | T |
| **List item type** | as above, applied with `[x IN n.f | convert(x)]` | T |
| **`TypedDict` shape** | rewrite the map: add keys (default), remove keys, rename keys | T / L |
| **Add a member to an `Enum`** | `ALTER ENUM Name ADD VALUE MEMBER`. Tested | S |
| **Rename a member** | `ALTER ENUM Name UPDATE VALUE OLD TO NEW`: **in place, and the stored values follow** (a node that had `OLD` now has `NEW`; tested). No data rewrite | S |
| **Remove a member** | **Not possible** (`Not yet implemented: Alter enum remove value`, Memgraph 3.13.1). Move the data off it (a mapping to another member, asked), and **leave the member in the database enum**, which is then a superset of the model's. See 5.6 | T / L |
| **Rename an enum class**, or replace one | There is no `RENAME ENUM` or `DROP ENUM` (not implemented). Create the new enum, convert every property that used the old (`ToEnum` per value, also inside lists, maps and annotated values), and leave the old enum **orphaned** in the database | T |
| **Plain literal to annotated value** (`name: str` to `name: WithCertainty[str]`) | `SET n.name = {value: n.name, certainty: $default}` | T |
| **Annotated value to plain** | `SET n.name = n.name.value` | L (the extra fields) |
| **Add or remove a field of an annotated value** | rewrite the map property on every node that has it | A / L |

### 5.3 Identity (the rename problem)

Every model and field has a **stable identity**, which starts as its name and is kept in the snapshot. A rename is an operation that says "the field that was called `a` is now `b`", and from then on identity follows the name `b`. `makemigrations` resolves the ambiguity of 4.2 by **always asking on the command line** (a hint in the models is only a suggestion that is confirmed there); it never infers a rename silently.

The identity of a *relation* is the pair `(model, field)` and so also names its two edge types. A change of `reverse_name` alone renames the reverse edge type and nothing else.

### 5.4 Relations

| Change | Data |
|--------|------|
| **Add**, a list or otherwise optional | none | S |
| **Add**, a required single relation | there is nothing to point at: **ask** for an entity (by id/URL) or fail; usually the field should be made a list or declared in two steps | A / M |
| **Remove** | delete the forward and reverse edges named for it, and the **nodes it owned** when it is a relation to a Document (they are part of the tree): a delete of a subtree. Entities are only referred to, so are kept | L |
| **Rename** | rename the forward edge type and the reverse edge type (`field` and `field_reverse`), and the edges of every parent field it narrows. There is no in-place rename of an edge type in Memgraph; it is a replacement, either `refactor.rename_type` (MAGE) or plain Cypher (5.8), and both **keep the properties** (including `reverse: true`) and run in a transaction | T |
| **Change `reverse_name`** | as a rename, for the reverse edges only | T |
| **Target widened** (`Person` to `Person | Group`, a new subclass, a trait gaining an implementer) | none | S |
| **Target narrowed** (`Person | Group` to `Person`, `Agent` to `Person`) | **check** the edges: those that point at a label that is no longer allowed make the migration fail, or are removed (a choice) | L |
| **Single to list** | none: one edge is a list of one | S |
| **List to single** | nodes with more than one edge need a choice: keep the first by edge creation order, keep by a property, or fail. Others' edges are removed | L |
| **Entity target to Document target** (or the reverse) | **M**: the target stops being a thing that is referred to and becomes part of the document (or the reverse); the node needs `head_node_id`, and entities have an identity of their own. Written by hand | M |
| **Relation to an embedded object, or to literals** | **M** (see 5.5) | M |
| **Add or remove `ViaEdge[T, Edge]`** | set `Edge`'s fields on both edges of every pair (defaults, asked); or remove those properties | A / L |
| **Edge model field changed** | as for literal fields, on edges: `SET e.f = ...` | T |
| **Narrow a parent field** (`subclasses_parent_fields` added) | write the second edge pair for the parent field beside each existing one (copying properties); removed: delete the extra pair | A / L |
| **Wrap in a reified relation** (`person: Person` to `person: IdentifiedAs[Person]`) | **insert a node**: see section 6 | T |
| **Unwrap** | the reverse: rewire edges to the target and **drop the relation node and its fields** | L |
| **Change a reified relation's fields** | literal-field rules, on the relation's nodes (by its label) | A / L / T |
| **Change what a reified relation's parameter allows** (`IdentifiedAs[Person]` to `IdentifiedAs[Person | Group]`) | as widening or narrowing, on the `target` edges | S / L |
| **Wrap or unwrap in a semantic space** (`Statement` to `Negative[Statement]`) | insert (or remove) the space node between the parent and the contents, **and recompute** `meta.semantic_spaces` and `meta.context_labels` for everything below it | T |
| **Conjunction**: add, remove, or change a slot | as a reified relation: a node with one edge per slot | T |

### 5.5 Embedded objects

| Change | Data |
|--------|------|
| **Literals to an embedded object** (`when: date; precision: str` to `date: Date`) | create one `Date` node per owner with the old properties moved into it; remove them from the owner. The edge pair is `date` / `date_reverse` | T |
| **Embedded to literals** | copy the properties back, delete the node | T / L |
| **Field of an embedded model** | literal-field rules, on nodes **by the embedded label**: they are wherever it is used | any |
| **Embedded subtype added** | none | S |
| **Embedded to a reified relation, or to a Document** | **M** | M |

### 5.6 Database structure

Indexes, constraints, the text index and enums are derived from the snapshot and diffed like fields; the operations are `AddIndex`, `RemoveIndex`, `AddConstraint`, `RemoveConstraint`, `AddEnum` and `AlterEnum`. After this is done, `setup-database` is only for a database that has no migrations yet.

**DDL is not transactional.** Memgraph refuses index, constraint and enum changes inside an explicit transaction (`Creating or modifying enums is not allowed in multicommand transactions`), so each runs on its own, in an auto-commit session, and is idempotent (`IF NOT EXISTS`, "already there" is ignored). Do not use `execute_query` or a transaction function for them: the driver treats Memgraph's *Not yet implemented* as a transient error and **retries it with backoff for minutes** (this hung an experiment); DDL has to be run without retries.

**Enums are append-only** (Memgraph 3.13.1, tested; see 11):

| | |
|---|---|
| `CREATE ENUM`, `ALTER ENUM ... ADD VALUE`, `ALTER ENUM ... UPDATE VALUE a TO b` | work. `UPDATE VALUE` renames a member and the stored values follow |
| `ALTER ENUM ... REMOVE VALUE`, `DROP ENUM` | *Not yet implemented* |
| rename an enum | no such statement |

So the database's enums are always a **superset** of the models': a removed member stays; a replaced enum stays as an orphan. Consequences for the design: the drift check compares "every enum and member of the models exists in the database", not equality; `initialise_database()` already only adds; the migration of a removed member is a *data* migration (nothing has that member any more); and an orphan is harmless but never goes away (a wiped and recreated database does not have it). A `pangloss migrate --plan` lists enums that would be orphaned.


### 5.7 Derived data a structural change must keep true

Any operation that adds, removes or moves nodes must also keep:

- `head_node_id` and `head_node_type` on every new node: the head of the node it is inserted beside (`coalesce(s.head_node_id, s.id)`);
- `meta` of a new node: `created_by`, `created_when` copied from its neighbour (a migration is not a user's edit), `semantic_spaces` and `context_labels` the same as that neighbour's, which **must be recomputed** under a changed semantic space;
- the **reverse** edge of every forward edge, with `reverse: true`;
- the labels (class, parents, traits, kind, `PGIndexableNode`);
- the extra edge pairs of narrowed parent fields;
- `PGUrl` nodes and their uniqueness;
- soft-deleted nodes: **they are migrated too** (they can be undeleted).

A shared set of helpers (`insert_between(...)`, `copy_meta(...)`, `add_reverse(...)`, `relabel(...)`) implements these once, and operations are written with them.

### 5.8 Renaming edge types

There is no in-place rename: an edge's type is fixed when it is created, and `refactor.set_type` does not exist. What was tested (Memgraph 3.13.1 with MAGE; see 11):

| | |
|---|---|
| `CALL refactor.rename_type(old, new, rels)` (MAGE) | works on a list of edges, in either direction (so for `field` and `field_reverse` alike); **keeps all properties**, including `reverse: true` and a `ViaEdge`'s fields; the edges get **new ids** (it is a replacement); it works inside an explicit transaction, and a rollback undoes it |
| Plain Cypher `MATCH (a)-[e:old]->(b) CREATE (a)-[n:new]->(b) SET n = properties(e) DELETE e` | the same result, and the same speed (50,000 edges: 0.11 s either way) |

So "replace all of them" is what happens either way; the procedure only saves writing it. **The plain Cypher is the default**, because it needs no MAGE (the backend is plain Memgraph), is as fast, and is one code path; `rename_type` could be an optimisation. For a large graph it is run in batches (`WITH a, e, b LIMIT $batch`; the next batch finds only what is left), each its own transaction, the old type being the cursor.

`refactor.extract_node` and `refactor.collapse_node` (MAGE) were looked at for wrapping and unwrapping a relation (section 6) and **not used**: `extract_node` makes the node from the edge and gives it the *edge's properties as its own*, cannot be followed by a `SET` in the same statement (*Update clause can't be put after calling a writeable procedure*), and does not make the reverse edges, ids, `head_node_id` or `meta`; `collapse_node` needs exactly one edge in and one out, and the real node has the reverse edges too. Plain Cypher does all of it in one statement.

## 6. Worked example: wrapping a relation in a reified relation

```python
# before
class Statement(Document):
    person: Person

# after
class IdentifiedAs[T](ReifiedRelation[T]):
    certainty: int

class Statement(Document):
    person: IdentifiedAs[Person]
```

### Detection

The snapshots differ in two places: a **new model** `IdentifiedAs` (kind `ReifiedRelation`, field `certainty: int`, parameter `T`), and **the type of `Statement.person`** changed from `entity: Person` to `reified: IdentifiedAs{T: Person}`. `makemigrations`:

1. emits `CreateModel("IdentifiedAs")` first (a model, so a new label; no data);
2. notices that the old target set (`{Person}`) equals the new parameter's, and the field name is the same, and proposes **`WrapInReified`** instead of "remove the field, add a field" (which would lose every edge);
3. needs a value for `certainty`, which old edges have no equivalent of: **asks** (`IdentifiedAs.certainty has no value for existing relations. Value (or Enter to fail):`), and writes the answer in the operation.

```python
operations = [
    CreateModel("IdentifiedAs", kind="ReifiedRelation", parameters=["T"], fields=[("certainty", "int")]),
    WrapInReified(model="Statement", field="person", wrapper="IdentifiedAs",
                  defaults={"certainty": 3}),
]
```

### The data

Before, for one `Statement` (a nested node of some head document, or a head itself):

```
(s:Statement)-[:person]->(p:Person)
(p)-[:person_reverse {reverse: true}]->(s)
```

After (as `AtPage` is stored in the demo database):

```
(s)-[:person]->(r:IdentifiedAs:ReifiedRelation:PGIndexableNode {certainty: 3, ...})
(r)-[:person_reverse {reverse: true}]->(s)
(r)-[:target]->(p)
(p)-[:target_reverse {reverse: true}]->(r)
```

and the old `(p)-[:person_reverse]->(s)` is gone: the reverse of the entity now leads to the relation node, and the document is found from there (that is how `Person.get` reads `person_reverse` through reified relations). In Cypher, run in batches (a page of `$ids` of new nodes, made in Python: UUIDs are `uuid7`, as elsewhere):

```cypher
MATCH (s:Statement)-[old:person]->(p)
WHERE NOT p:IdentifiedAs                        // idempotent: skip what is done
WITH s, old, p ORDER BY s.id, p.id LIMIT $batch // one batch
OPTIONAL MATCH (p)-[old_reverse:person_reverse]->(s)
WITH collect({s: s, old: old, p: p, old_reverse: old_reverse}) AS rows
UNWIND range(0, size(rows) - 1) AS i
WITH rows[i].s AS s, rows[i].old AS old, rows[i].p AS p,
     rows[i].old_reverse AS old_reverse, $new_ids[i] AS new_id   // uuid7s, made in Python
CREATE (r:PGIndexableNode:ReifiedRelation:IdentifiedAs {
    id: new_id, type: 'IdentifiedAs', certainty: $certainty,
    head_node_id: coalesce(s.head_node_id, s.id),
    head_node_type: coalesce(s.head_node_type, s.type),
    meta: s.meta })        // creator, times, semantic_spaces and context_labels of its neighbour
CREATE (s)-[:person]->(r)
CREATE (r)-[:person_reverse {reverse: true}]->(s)
CREATE (r)-[:target]->(p)
CREATE (p)-[:target_reverse {reverse: true}]->(r)
DELETE old, old_reverse
```

The ids of the new nodes are given as a parameter, so that they are `uuid7` as everywhere else. The statement is repeated until the `WHERE` finds nothing. (This is a sketch of the shape; the real one is checked against Memgraph in the operation's tests.)

### What the complexity of the model adds

The same operation has to cope with:

- **Subclasses.** `MATCH (s:Statement)` finds `Activity` and `Transfer` too, as they carry the label. Nothing per subclass is written.
- **Narrowed parent fields.** If `Activity.carried_out_by` narrows `Statement.person`, the graph has *two* edge pairs (`carried_out_by` and `person`) to the same entity. The operation is **expanded** to every field in the chain, and the wrapper node is shared: one relation node, with *both* names for the edge to the statement. (The diff reports this as one change and the generator does the expansion from the snapshot's `edge_types`.) A narrowed field must itself become `IdentifiedAs[...]`, as the model validation requires: if only the parent changed, the models would not initialise.
- **Edge properties.** If the old relation was `ViaEdge[Person, Certainty]`, its properties are on the old edges: they are **moved** to the new relation node (if the wrapper has fields of those names) or fail, or are dropped by choice.
- **Where it is.** `s` may be a head, nested in another document, inside an `Embedded`, under a `Negative[...]` or a `Causes` slot. `head_node_id` is copied from `s`, and `meta.semantic_spaces`/`context_labels` too, so the new node is in the same context.
- **Deleted documents.** Soft-deleted nodes match too, and are migrated.
- **A union.** `person: Person | Group` to `IdentifiedAs[Person | Group]`: the same operation; the `WHERE` just does not name the target label. If the target set changed as well, the target-narrowing check (5.4) runs.
- **Volume.** Repeated batches, each its own transaction, with the `WHERE NOT p:IdentifiedAs` as the cursor, so the operation can be **stopped and restarted**.

### Reversing

`UnwrapReified` runs the same in the other direction (`MATCH (s)-[:person]->(r:IdentifiedAs)-[:target]->(p)`), re-creates the direct edges and **deletes `r` and its `certainty`**. It is reversible as a graph but not as data: `certainty` is lost, so the migration is marked **lossy** and `migrate --backwards` asks for confirmation (or saves the lost values, if the migration was written with `keep=True`).

## 7. How operations are run

### 7.1 Operations

```python
class Operation:
    reversible: bool
    lossy: bool
    def state_forwards(self, state): ...             # change the snapshot
    def database_forwards(self, tx, state): ...      # change the data; state is *before*
    def database_backwards(self, tx, state): ...     # optional
    def describe(self) -> str: ...                   # for --plan
```

| Operation | |
|-----------|--|
| `CreateModel`, `DeleteModel`, `RenameModel`, `AlterModelLabels` (parents/traits) | 5.1 |
| `AddField`, `RemoveField`, `RenameField`, `AlterField` (type, nullability, default) | 5.2, with `convert=` for a changed type |
| `AddEnum`, `AlterEnum`, `RemoveEnum`, `AddIndex`, `RemoveIndex`, `AddConstraint`, `RemoveConstraint` | 5.6 |
| `AddRelation`, `RemoveRelation`, `RenameRelation`, `AlterRelationTarget`, `AlterCardinality`, `AlterEdgeModel` | 5.4 |
| `WrapInReified`, `UnwrapReified`, `WrapInSemanticSpace`, `UnwrapSemanticSpace` | 5.4, 6 |
| `LiteralsToEmbedded`, `EmbeddedToLiterals` | 5.5 |
| `RunCypher(forwards, backwards)`, `RunPython(forwards, backwards)` | the escape hatch (below) |

A migration is a list of operations; `RunCypher` and `RunPython` (which gets the `state`, a transaction and the helpers of 5.7, **not** the model classes) are for what the generator cannot do, such as a change of kind. Hand-written ones are reviewed like any code, and `makemigrations --empty` makes a file to put them in.

### 7.2 The commands

| Command | |
|---------|--|
| `pangloss makemigrations [app] [--name N] [--empty] [--dry-run] [--check]` | detect, ask, write `migrations/NNNN_name.py`. `--check` exits non-zero if the models and the migrations disagree (for CI) |
| `pangloss migrate [app] [target] [--plan] [--dry-run] [--backup] [--fake]` | apply what is pending, in dependency order. `--plan` lists operations and what they would match (counts); `--dry-run` runs them in a transaction and rolls back; `--backup` takes a snapshot of the database first; `--fake` records one as applied without running it (for a database that was changed by hand) |
| `pangloss migrate [app] <earlier>` | go backwards, where the operations are reversible |
| `pangloss showmigrations` | applied and pending, per app |
| `pangloss check-data` | read every head node through the current models and report failures (4.4) |
| `pangloss squashmigrations app 0001 0007` | replace a run of migrations by one that has the same effect on the snapshot, for a new database (old databases keep the history) |

### 7.3 Running one

1. Take the **lock** (`PGMigrationLock`); fail if someone has it.
2. Check the applied migrations match the files (`checksum`); refuse if an applied migration was edited.
3. For each pending migration in order, with the snapshot *before* it:
   - write `(:PGMigration {status: 'running'})`;
   - run the operations. **Default: one transaction** for the migration, so it either happens or does not. For a large database `atomic = False` runs each operation in batches, each its own transaction, using the operation's *own idempotent condition* as the cursor (as the `WHERE NOT p:IdentifiedAs` above), and saves progress in `cursor`;
   - DDL runs outside transactions, in its own steps;
   - set `status: 'applied'` and `schema_hash`.
4. Run `check-data` unless told not to. Release the lock.

A failed non-atomic migration is `failed`, and the next `migrate` **resumes** it. An atomic one has changed nothing.

While it runs, the API is not to be used: `pangloss run` refuses to start with pending migrations (3.3), and a running migration holds the lock; there is a setting to put the API in read-only. Anything that writes during a structural change would write nodes in the old shape.

### 7.4 Safety

- **Always** a dry run first in CI, on a copy.
- A **backup** (`--backup`) before applying; Memgraph's snapshot is the unit. Lossy operations require it (or `--no-backup`).
- A lossy operation prints what it will lose (a count) and needs `--yes` or an interactive confirmation.
- Migrations never import the current models, so an old migration still runs when the models have changed since.
- The checksum stops an applied migration being edited; a fix is a new migration.

## 8. Other parts that depend on the models

- **The interface** gets its definitions from the snapshot export, built from the current models at build time. A migration changes data only; nothing there changes except that the interface and the data have to be of the same version (the same hash check, in `pangloss interface build`).
- **The REST API**: `ETag`/`If-Match` is the count of `PGUpdate` nodes. A migration adds none (it is not a user's edit), so a page that was loaded before a migration and sent after it would be accepted by the version check; it is rejected by validation as its shape is the old one. Stopping the API (7.3) makes this moot.
- **Apps and the dependency graph.** Models in one app refer to another's. A migration may depend on another app's (`dependencies = [("people", "0003")]`), and an operation that changes a model used by other apps (a rename) is the one to carry the change into theirs, with the others' dependent migrations written after it. Cycles between apps' models need the models of an app to be in one initial migration with later ones split.
- **Installed library apps** (`pangloss_users`, `pangloss_memgraph`): their data (`PGUser` and the like) is migrated by their own migrations, with the same machinery, so a Pangloss upgrade can bring migrations.

## 9. A way to build it

Each phase is usable by itself.

1. **Snapshot and drift check.** Extend `export_models()` to the storage-aware snapshot (3.1); store its hash and `PGMigration`/`PGMigrationLock`; `pangloss run` refuses to start if the models differ from the applied hash. No operations yet: this alone prevents a silent mismatch.
2. **Migration files and DDL.** `Operation`, the file format, `migrate`, `showmigrations`, `makemigrations` for adding and removing models, indexes, constraints and enums (`initialise_database()` becomes "the operations that make the initial state").
3. **Literal fields.** Add, remove, rename, nullability, type and enum conversions, with the ask-for-a-value flow and `check-data`.
4. **Relations.** Rename, cardinality, target narrowing with checks, reverse names, edge models, narrowed parent fields (the edge-pair expansion).
5. **Structural operations.** `WrapInReified`/`Unwrap`, embedded to and from literals, semantic space wrapping with recomputed context labels, parents/traits, on the shared helpers of 5.7. Resumable batches.
6. **Detection polish.** Rename hints, the interactive questions, `squashmigrations`, `--backwards`, `--plan` with counts.

### Testing

- **Operation tests** against a real Memgraph, as the backend's tests are: build a graph in the *old* shape with the old models, run the operation, then read it with the *new* models (`HeadView`) and compare with data written the new way. This "old graph, new models, same result" is the main property.
- **Round trips** where an operation is reversible.
- **Detection tests**: pairs of snapshots to the operations expected (no database).
- **Idempotency**: running an operation twice, and after an interruption, changes nothing the second time.
- A **property test** over the demo models: every field kind, in every position (a head, a nested document, an embedded object, a semantic space).

## 10. Open questions

- ~~**Rename detection**~~ Decided: always asked on the command line, never inferred (4.2).
- **Field identity beyond the name**: a stable id in the declaration (`Field(id="...")`) would make renames exact, at the cost of noise in the models.
- **How lossy is allowed by default**: `--yes` per operation, or one flag per run?
- **Read-only mode** while migrating: needed, or is stopping the API enough?
- **Multiple databases / environments** whose migrations diverge (a branch that migrates the demo database differently): Django's merge migrations, or a linear history only?
- **Memgraph limits** — now tested (11): enums are append-only, edge types are replaced (not altered), DDL is outside transactions. Still to check: the size of a transaction on large graphs, and whether a snapshot (`--backup`) can be taken from a client.
- **History**: `PGUpdate` records say who and when but not what. If a content history is ever kept, migrations would have to rewrite it too.

## 11. What was tested

Run against the demo database (Memgraph **3.13.1**, `memgraph/memgraph-mage`) on scratch labels and enums, to see what is possible before specifying it.

| Tried | Result |
|-------|--------|
| `CREATE ENUM`; store a member in a property and in a list | works; `toString(n.f)` gives `Enum::MEMBER` for a single value (it does not accept a list) |
| `ALTER ENUM E ADD VALUE X` | works |
| `ALTER ENUM E UPDATE VALUE OLD TO NEW` | works; **a node that had `OLD` now compares equal to `E::NEW`** |
| `ALTER ENUM E REMOVE VALUE X` | `Not yet implemented: Alter enum remove value` |
| `DROP ENUM E` (unused, and in use) | `Not yet implemented: Drop enum` |
| `ALTER ENUM ... RENAME`, `RENAME ENUM` | syntax errors: do not exist |
| Convert to another enum | `SET n.c2 = ToEnum('E2', split(toString(n.c), '::')[1])`, and `[x IN n.c | ToEnum(...)]` for lists: works |
| Enum DDL in an explicit transaction | refused: *not allowed in multicommand transactions* |
| The driver, with a *Not yet implemented* error | treated as transient and retried with growing waits (~1 minute and more): use auto-commit sessions for DDL |
| `refactor.rename_type` | keeps properties, new edge ids, works in both directions and in a transaction, undone by a rollback |
| `refactor.set_type` | does not exist |
| `refactor.extract_node`, `collapse_node` | work, but not suited (5.8) |
| 50,000 edges renamed | 0.11 s by `rename_type`, 0.11 s by `CREATE`+`DELETE`; a batch of 10,000 by `LIMIT` works |

> The experiment left two **scratch enums, `ScratchColour` and `ScratchColour2`, in the demo database**. Because enums cannot be dropped, they stay until the demo database is recreated. They are not used by anything.

## 12. Progress

Where the work stands, so that it can be picked up.

**Done: the specification and the Memgraph facts it rests on**

- This specification (sections 1 to 10), and the Memgraph behaviour it depends on, tested (section 11).
- Decisions: a rename is **always asked on the command line**, never inferred (4.2); enums are append-only (5.6); edge types are renamed with plain Cypher (5.8).

**Done: finding what changed** (`pangloss_models.migrations`; no database, no files)

| Module | |
|--------|-|
| `snapshot.py` | `build_snapshot()`: `export_models()` plus each model's `labels` (`labels_for_model` in `base_models.py`, the one function the write path uses too) and each field's `storage` (`property`, `map_property`, `embedded_node`, `edge`, with the edge types, including the extra pair for each parent field a relation narrows). `snapshot_hash()` is of what is *stored* (`data_view()` leaves out descriptions, validators, whether a field has a default, derived data, and the order of fields, labels and enum members) |
| `changes.py` | 30 changes, immutable records with a `safety`, a `describe()`, a `phase` that orders them (renames first, then what others need, alterations, fields added, fields removed, what is gone), and `to_dict()` / `change_from_dict()`. Each carries what is needed to apply it to a snapshot (a model or field definition, the options a relation has now), and, for some, fields for an **answer** that only a person can give (`default`, `defaults`, `on_failure`, `mapping`, `keep`, `on_narrowing`, `replacement`): `None` as `diff` finds it; the change cannot be applied to a database until it is filled in |
| `diff.py` | `diff(old, new, confirmed=(), declined=())` returns `changes` and `questions` (`PossibleRename`s, each with a `question()` for the command line). A field that another narrows is "absorbed" (`RemoveField.absorbed`, `AddField.from_narrowing`): it is no longer a field of the model but its edges are still written |
| `state.py` | `replay(old, changes)`: the snapshot after the changes, with a handler for every kind of change (a test fails if one is added without it) |

The property that makes it complete is tested on every case in the diff tests: **`replay(old, diff(old, new).changes) == data_view(new)`**.

**Done: applying changes to Memgraph** (`pangloss_memgraph.databases.memgraph.migrations`)

`apply_change(tx, change, state)` for a change to the data, in a transaction; `run_ddl(database, change, state)` for enums, outside one and safe to repeat; `apply_changes(database, state, changes)` runs a list in order (the data changes that come together in one transaction, enum changes on their own between them, the snapshot followed through so each change is given the state before it). `state` is the snapshot: nothing needs the classes of the models.

| Change | Data |
|--------|------|
| `CreateEnum`, `AddEnumMember`, `RenameEnumMember` (`UPDATE VALUE`, in place), `RenameEnum` (a new enum, the values converted) | DDL; the old enum or member stays |
| `RemoveEnumMember` | the values are moved to `replacement` (an answer; fails if some have it and there is none); the member stays in the database enum |
| `AddField` | a required literal gets `default` on the nodes that exist; optional fields and relations need nothing |
| `RemoveField` | the property, or the edges of the relation and the nodes it owned (the subtree below, not entering entities) |
| `RenameField` | the property moved, or the edge types (forward and reverse) replaced |
| `AlterNullability` | to non-null: `default` where there is none |
| `AlterLiteralType`, `AlterListItemType` | converted in place (`str`, `int`, `float`, `bool`, `decimal`, `date`, enums by value or `mapping`); what does not convert fails unless `on_failure` is `null` or `default` |
| `LiteralToAnnotatedValue`, `AnnotatedValueToLiteral` | the value wrapped in (with `defaults` for the extra fields) or taken out of the map |
| `AlterCardinality` | list to one: `keep: "first"` or it fails when a node has several |
| `AlterRelationTarget` | narrowing: the edges to what is no longer allowed fail, or are removed (`on_narrowing: "remove"`) |
| `AlterReverseName`, `AlterParentFields`, `AlterEdgeModel` | reverse edges replaced; the edge pair of a parent field written or deleted; properties (with `defaults`) set on, or removed from, both edges of each pair |
| `WrapRelation`, `UnwrapRelation` (reified relations) | a node inserted on each edge (labels, `head_node_id`, and the `meta` the models would give: creator and times, the semantic spaces, the context labels with the holding statement in them), with `defaults` for its fields; a field that narrows the wrapped one shares the one node; unwrapping removes the node. Tested to give **the same graph the new models write** |
| `WrapRelation`, `UnwrapRelation` (semantic spaces) | a node for the space on each edge, between the node and what it holds (`contents`); then the **semantic spaces and context labels of every node of the document are written again** (`recompute_contexts`), following the models' own propagation, including that what a single relation holds shares the lists of the node and a list's items are given copies, and that an embedded object is not followed. Tested equal to a document written natively, for a statement that holds a nested document |
| `ChangeWrapper` | a relation to one reified relation that is now to another: the nodes relabelled and given the new `type`; the fields the new has not are given `defaults`, those the old had and the new has not are removed |
| `LiteralsToEmbedded`, `EmbeddedToLiterals` | the literal fields of a model become the fields of an embedded object (a node for each node that has them, the values moved into it, `defaults` for what else it needs) and back (the values copied out, the node deleted; its other fields are lost) |
| `AlterModelLabels`, `RenameModel`, `DeleteModel` | labels added or removed; relabelled (and `type`, `head_node_type`, and the context labels of what a renamed document holds); the nodes, what they own, and their creation and update records |
| `CreateModel`, `AlterModelOption`, `AlterAnnotatedValue`, `AlterEmbedded`, `RemoveEnum` | nothing to do to the data |
| `AlterModelKind`, `ChangeFieldKind`, `AddField` of an embedded object that is not made of literals that were there, wrapping in a conjunction (it has several slots to fill) | refused with `PanglossMigrationNotSupported`: to be written by hand |

Tested in `pangloss-memgraph/tests/test_migrations_literals.py` and `test_migrations_relations.py`: data written with the old models, migrated, and read with the new ones. Memgraph found three things the specification had not:

- **The read lost one of two edges to a node.** A field that narrows another is stored as two edges to the same node (`carried_out_by` and `person`); the read finds each node once, along one edge, so which it read depended on the order they were stored in, and a narrowed relation to a node (a reified relation, a document) could not be read. `build_read_query.py` now adds the other edges between the same two nodes.
- **The first label of a node is its class** (the reader takes `labels[0]`): a node that is inserted has its own label first and `PGIndexableNode` last.
- **A head node has no `meta`**, and the context labels of what a nested document holds have the document in them; so the `meta` of an inserted node is built from the creation record, or the neighbour's (`INSERTED_NODE_META`).

**Done: migration files, planning and the commands**

| Piece | |
|-------|-|
| `migrations/files.py` | A migration is a Python module in the app's `migrations/` package (`dependencies`, `schema_hash`, `changes = changes_from_data([...])`), written by `write()` and read by `load()` / `discover()`. `checksum` is of the changes as written. `MigrationGraph` orders migrations (each app's in order, and what they depend on), finds the leaf of an app, replays them to the **state** without the classes of the models, and says which app made each model (`owners()`) |
| `migrations/planner.py` | `plan(graph, snapshot, apps, confirmed, declined, answer)`: the changes since the migrations, shared among the apps (a model or enum belongs to the app its class is in, or that made it), each migration depending on those of the other apps whose models it mentions; it checks that applying the migrations in that order gives the models, and refuses to write them if models of two apps need each other |
| `migrations/questions.py` | What is asked: `answers_needed(change, state)` (a value for a new required field, for a field that may no longer be null, the fields of a wrapper, the extra fields of an annotated value, edge model fields, the member to give the values of a member that goes), `with_answer`, `parse_value` (typed answers, kept as data: a date as ISO text, a decimal as text) |
| `migrations/history.py` | `pending(graph, applied)` and `problems(graph, applied)`: an applied migration that was edited, one that is not there, one applied before what it follows |
| `pangloss_memgraph.databases.memgraph.migration_backend` | What the commands need of a backend: `ensure_ready` (the record's constraints, and the indexes; not enums), `applied`, `lock` / `unlock` (a `PGMigrationLock` node with a uniqueness constraint), and `apply`, which records each migration as `running`, then `applied` (with its checksum, schema hash, who and how long) or `failed` (with the error), and stops at a failure |
| `pangloss makemigrations` | Compares the models with the migrations, asks each possible rename (`Was the field 'born' renamed to 'birth_year'? [y/N]`) and the answers the changes need, shows what each migration does (marking `[LOSES DATA]` and `[NEEDS CODE]`), and writes them. `--dry-run`, `--check` (exit 1 if the models have changed), `--noinput` (never guess: fail if it has to ask), `--name` |
| `pangloss migrate` | Applies what the database has not had, in order, under the lock. `--plan`, `--dry-run` (see below), `--check`, `--fake` (record as applied without running: for a database that is already as they say), `--yes` (do not ask before changes that lose data), `--unlock` (after a stopped run), `--no-check`, `--check-all`, `--batch-size N`. Refuses if the record and the files disagree. Warns if the models have changed since the migrations. **After applying it reads the data of the models the migrations could have made unreadable** (below), and exits with an error, saying what, if any cannot be read; `--check-all` reads everything, `--no-check` nothing |
| `pangloss migrate --dry-run` | Tries the changes in **one transaction that is rolled back**, and says for each what it did: `3 properties set`, `2 nodes made, 4 edges deleted`, or `WOULD FAIL: <why>` (a value that is needed and was not given, data that does not convert). After a failure the rest are `not tried`, as the transaction cannot go on. A change to the enums cannot be tried (`changes the database's enums (not tried)`), and one that needs an enum that the migration would make fails for want of it. Changes nothing, and needs no lock. The counts are the statements' own, from the database |
| `pangloss check-data [--type T] [--limit N]` | Reads each Document and Entity (not deleted; a nested document is read on its own as well as in its head) with the model of its own `type` and reports what cannot be read, with the first errors (`Person 01a1… (Ann): born: Field required`). Exit 1 if any. `pangloss_models.migrations.check.check_data` |
| `pangloss showmigrations` | `[X]` applied, `[ ]` not, `[!]` failed, `[~]` running, `(faked)` |

Tried for real against Memgraph (a project of its own): `makemigrations` writes `0001_initial`, `migrate` applies it; a model gets a required field, `makemigrations` asks `A value for MigPerson.born on the nodes that exist`, writes `0002_addfield_migperson_born` with `'default': 1900`, and `migrate` gives the existing node the value. The demo project has its `0001_initial`, recorded with `migrate --fake` as its database was made before there were migrations.

**Not done**

- `--backup`, squashing, and going backwards. Batches (below) do not cover relations that are removed or renamed, wrapping in a semantic space, or a change of enum; those are made at once, in a transaction of their own.
- Wrapping in a conjunction (a relation to one thing cannot become one to a join of several; it is a change of the model to write by hand); `Fulfils` (the labels a node gets for the classes it fulfils are decided when it is written, and are not in the snapshot); a node whose enum values are inside a `TypedDict`, an annotated value or an edge model when an enum member is removed or an enum renamed; the `contents` order of a context label, which depends on the order the edges were made in.
- Indexes and constraints are made by `migrate` (`ensure_ready`) as `setup-database` makes them, and are not yet changes of their own (`AddIndex`).
- The tests make enums that stay in the test database (Memgraph cannot drop one): `MigrationHue` and one with a new name for each run of the member test.

**Also done: the start-up check** (`migrations/startup.py`, called from the lifespan of `pangloss-api`). If a project has migrations, the server does not start (`MIGRATION_CHECK = "error"`; `"warn"` starts and warns, `"off"` does not look) when migrations have not been applied, one was changed or lost after it was applied, or the models are not what the migrations come to. Tried on the demo: it starts; with its migration marked not applied it refuses and says `pangloss migrate`.

**Also done: `migrate --dry-run` and `check-data`.** On the demo's data, with a required field added to `Place` (and then undone): `makemigrations` asked for a value, `migrate --dry-run` said `3 properties set` (its three places) and changed nothing, and `check-data` read all 20 nodes.

**How long `check-data` takes.** It reads one node at a time (a page of the list, then a `get` for each). Measured on a local Memgraph: **about 1.5 ms a node** for simple nodes (1000 nodes in 1.5 s), and about 7 ms a node for the demo's documents, which have ~15 nodes each. So 100,000 nodes of that size is roughly 3 to 12 minutes, and it scales with the size of each document's tree; `--type` and `--limit` read part. It is sequential; reading several at once is the obvious way to make it faster. Finding this showed two faults in reads, fixed:

- **A read planned its query afresh each time** (~118 ms): the query text had parameter names made for each call, and Memgraph keeps the plan of a query by its text. With fixed names a read is 1 to 2 ms (the same `get`, 118 ms before). Writes still build their queries with made-up names, so each is planned each time (a create is ~10 ms).
- **`list` returned one row for a page of documents that refer to entities**: the facets were worked out for each document, so such a page came back as many rows and only the first was read (`count` 40, `results` 1). `check-data` had been skipping those nodes.

**Also done: the check after `migrate` reads only what could be affected** (`migrations/affected.py`, `affected_models(changes, snapshot)`). Adding a model, an enum, an enum member or an optional field (or a list) changes nothing that exists, so nothing is read. Otherwise the models read are: those a change names (and their subclasses); those that **hold** them (a Document is read with the Documents nested in it, its embedded objects, reified relations and semantic spaces); the **entities** on the other end of a relation that changed (an entity is read with the documents that refer to it); and the models that use an enum that changed. Adding a single required relation reads the model that has it, but not the entity it is to (it only gets an empty reverse relation). `pangloss check-data` on its own still reads everything.

**Also done: resumable batches.** `pangloss migrate --batch-size N`, or `atomic = False` in a migration file (batches of 5000), makes a migration in batches, each its own transaction (`apply_changes_in_batches`):

- a change to a literal field (add, remove, rename, make not null, change the type or the items' type, wrap in or take out of an annotated value) and a change of labels are made **`N` nodes at a time, in the order of their ids**, and a wrapped relation (a reified relation) **`N` relations at a time** (those done are no longer there to be wrapped, so the next batch finds the next); everything else is made at once, in a transaction of its own, and enum changes on their own as before;
- **how far it has got is saved in the same transaction as each batch** (`cursor` on the `PGMigration` record: the changes before `change` are done, and `change` is done for ids up to `after`); a run that stops or fails leaves the record `running` or `failed` with it, and the next `migrate` goes on from there (`going on from change 3`), after `--unlock` if the lock was left;
- what must hold before anything is changed is checked **once, before the first batch**: that every value converts (or `on_failure` says what to do), that the answers a change needs are given;
- the result is the same as for the whole migration (the tests run the same changes both ways, and a wrapped relation is what the new models write, and wrapped once, even when stopped half way through).

A batch that is retried by the driver after a transient error runs again, so a change in batches should be one that can be run twice over the same nodes: the keyset (`id` after the last) means it normally is not.

**Next**

Everything that is left is listed in [`TODO.md`](../TODO.md), under "Database migrations" (commands and safety, changes that cannot be applied yet, batches and speed, code to tidy). In order of use:

1. `RunCypher` / `RunPython`, so that a change that is `[NEEDS CODE]` can be written by hand.
2. `--backup`.
3. Going backwards, and squashing.
3. Unwrapping into and out of conjunctions, if a use for it turns up.
