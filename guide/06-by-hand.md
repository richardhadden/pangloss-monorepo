# 6. Writing a migration by hand

Most migrations are written for you. You need to write one yourself when:

- `migrate` refuses a change, because Pangloss cannot do it (wrapping in a conjunction, a type conversion it does not know, and the others listed at the end of [chapter 3](03-changes.md)); `--plan` shows it and `--dry-run` says `WOULD FAIL`;
- you want to **change the data itself**: fill in a value computed from other values, split a field in two, clean up records, load some reference data.

You get three building blocks, all in `pangloss_models.migrations.changes`:

| | What it does |
|-|--------------|
| `RunCypher(query, parameters=...)` | Runs a Cypher query against the database |
| `RunPython(function=...)` | Calls a Python function you wrote, which gets a database transaction |
| `StateOnly(changes=(...))` | Tells Pangloss the *models* changed, without touching the data. It is the other half of a refused change |

They are changes like any other: they sit in a migration's list, run in order, in the migration's transaction, and are recorded, dry-run, backed up and (if you say how) undone with everything else.

## Starting a file

```bash
pangloss makemigrations --empty library --name backfill_nicknames
```

writes `library/migrations/0007_backfill_nicknames.py` with no changes and a comment showing the three building blocks. (The app must already have a first migration.) You can also edit a migration that `makemigrations` just wrote and you have not applied.

A migration with a hand-written change looks like this; the list may mix dictionaries and the changes themselves:

```python
from pangloss_models.migrations.changes import RunCypher, RunPython, StateOnly
from pangloss_models.migrations.files import changes_from_data

dependencies = []
schema_hash = '...'          # leave what makemigrations wrote

changes = changes_from_data([
    RunCypher(
        query="MATCH (p:Person) WHERE p.nickname IS NULL SET p.nickname = p.name",
        note="give everyone a nickname",
    ),
])
```

## `RunCypher`

```python
RunCypher(
    query="MATCH (p:Person) WHERE p.born < $year SET p.era = $era",
    parameters={"year": 1800, "era": "early"},
    note="mark the early people",          # shown in the plan
    lossy=False,                           # True if it destroys information
    affects=["Person"],                    # models to read afterwards
    reverse_query=None,                    # how to undo it (see below)
    reverse_parameters=None,
)
```

How the data is stored, since you are writing Cypher against it (the full account is in `docs/migrations.md`):

- A node of a model has the model's **name as a label** (`:Person`), as well as its parents', its kind (`:Entity`, `:Document`...) and `:PGIndexableNode`. Match on the model's label and you also get its subclasses.
- Literal fields are **properties** of the node. Dates are dates; decimals are strings; an enum is the **value** of its member (a string or a number).
- A relation `home: Place` is two edges: `(person)-[:home]->(place)` and `(place)-[:home_reverse {reverse: true}]->(person)`. Always write both (the reverse edge is called `<field>_reverse` unless the field sets another `reverse_name`).
- Every node has an `id` (a UUID string) and a `label`. Nodes inside a document have a `head_node_id` pointing to the document at the top.
- Use **parameters** (`$year`), not string building.

Limits: **no DDL.** Memgraph will not create or change an index or constraint inside a transaction. Those are made by Pangloss's own migrations.

## `RunPython`

For anything that needs a loop, or a computation Cypher is bad at:

```python
# library/migrations/helpers.py
async def split_names(tx, state):
    result = await tx.run("MATCH (p:Person) RETURN p.id AS id, p.full_name AS name")
    for row in await result.data():
        first, _, last = row["name"].partition(" ")
        await tx.run(
            "MATCH (p:Person {id: $id}) SET p.first = $first, p.last = $last",
            id=row["id"], first=first, last=last,
        )
```

```python
changes = changes_from_data([
    RunPython(function="library.migrations.helpers:split_names", note="split full names"),
])
```

- The function takes `(tx, state)`; it may be `async` or plain. `tx.run(...)` makes a query. `state` is the description of the models **as they were before this change** (a plain dictionary), if you need to look something up.
- `function` is a `"package.module:name"` string, or the function itself (which is kept as its name).
- **Do not import your current models** in it. The migration has to keep working when the models have changed, years from now. Use `tx` and Cypher, and `state`.
- A change to the function's body is **not noticed** by the checksum (only its name is). If you must fix one that has been applied, make a new migration.
- Put functions in a module of the app (`migrations/helpers.py` works), not in the migration file itself unless it is short.

## Going back: `reverse_query`, `reverse_function`

If you give none, the migration **cannot be undone** and `migrate app <earlier>` says so, before touching anything. To make it reversible say how:

```python
RunCypher(
    query="MATCH (p:Person) SET p.era = 'early'",
    reverse_query="MATCH (p:Person) REMOVE p.era",
)
RunPython(function="library.migrations.helpers:split_names",
          reverse_function="library.migrations.helpers:join_names")
```

## Refused changes: `RunCypher` plus `StateOnly`

When `makemigrations` finds a change that `migrate` will not apply, it still writes it into the migration, so that the *models* are accounted for. `migrate` stops when it reaches it. To finish the job you do two things:

1. **Move the data** yourself, with `RunCypher` / `RunPython`, placed *before* the refused change;
2. **Tell Pangloss the models changed**, by wrapping the refused change in `StateOnly`, so that it updates the record of the models without trying to touch the data.

(Changing the *kind* of a model or a field is different: it is not allowed at all, and `makemigrations` refuses it before anything is written. Make a new model or field, and move the data to it with a migration like the one below.)

Here `Event.when` was a `datetime` and is now a `str`. Pangloss does not convert a datetime to text, so `makemigrations` wrote an `AlterLiteralType` entry that `migrate` refuses. The edited migration:

```python
changes = changes_from_data([
    # 1. turn the datetime into text
    {'change': 'RunCypher',
     'note': 'store Event.when as ISO text',
     'query': "MATCH (e:Event) WHERE e.when IS NOT NULL SET e.when = toString(e.when)",
    },

    # 2. the entry makemigrations wrote, now wrapped so that it changes the models only
    {'change': 'StateOnly',
     'changes': [
         {'change': 'AlterLiteralType', 'model': 'Event', 'name': 'when',
          'old': {'type': 'datetime'}, 'new': {'type': 'str'}},
     ]},
])
```

(This example is illustrative. Check how your own values are stored, and try it on a copy.) The pattern is always the same: **data first, then `StateOnly` of the refused change**. If you forget the second part, `makemigrations` will notice that the migrations no longer come to the models and offer the change again.

## Testing hand-written changes

- `pangloss migrate --plan` shows them (`Run a query: <your note>`, with `[LOSES DATA]` if you said `lossy=True`).
- `pangloss migrate --dry-run` runs them for real in a transaction that is rolled back, and tells you how many properties were set and nodes or edges made or deleted. If your Cypher is wrong, it says so here.
- After applying, Pangloss reads the data back with the models you named in `affects` (all of them, if you gave none). Name the models you changed, so a large database is not read for nothing.
- `pangloss check-data` reads everything.

## Advice

- **Keep them small and single-purpose.** One `RunCypher` per idea; a note on each.
- **Make them safe to run on an empty database** (a `MATCH` that finds nothing does nothing), since a new developer applies the whole history to an empty one.
- **Say `lossy=True` honestly.** It is what makes `migrate` ask for a backup.
- **Do not call your application's own code** from a `RunPython`. A migration is a record of the past; the application is in the present.
- **Don't edit them after they have run anywhere that matters.** Write another.
