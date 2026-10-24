# Semantic spaces and context labels

## Semantic spaces

A `SemanticSpace[T]` subclass wraps content in a named context that changes how the content should be read, for example `Negative[Statement]` ("it is *not* the case that...").

```python
class Negative[T](SemanticSpace[T]): ...


class Hypothetical[T](SemanticSpace[T]): ...


class Factoid(Document):
    has_statement: list[Statement | Negative[Statement]]
```

A payload looks like:

```python
Factoid(
    label="F",
    has_statement=[
        {
            "type": "Negative",
            "contents": [{"type": "Statement", "label": "S", "text": "..."}],
        },
    ],
)
```

The space is stored as a node of its own (type `Negative`), connected to its contents through the `contents` relation, and read back the same way (`factoid.statements[0].type == "Negative"`, `.contents[0].type == "Order"`). In addition, when an object is converted to its `CreateDB` form, `recursively_propagate_context_types` walks the tree and annotates **every contained object** with the spaces it sits inside, so a node can be filtered by context without traversing up.

## What gets recorded

Each node written to the database has `meta.semantic_spaces` and `meta.context_labels`:

- **`semantic_spaces`** is a flat list of the space type names enclosing the node (e.g. `["Negative"]`).
- **`context_labels`** is a nested structure (`ContextLabel = {type, id?, contents?}`) recording the path of spaces and documents:
  - A semantic space adds `{"type": "<SpaceName>"}`.
  - A nested `Document` (with `use_in_semantic_space_label=True`) is appended to the `contents` of the innermost space, as `{"type": <DocType>, "id": <id>}`.
  - A nested Document outside any space starts a root entry `{"type": "#rootcontext", "contents": [...]}`.
  - List items each receive their own deep copy so siblings do not share state.

The space node itself does not get `semantic_spaces`/`context_labels`; only the objects inside it do.

Both fields appear on `View`/`HeadView`/`ReferenceView` metas (as `meta.semantic_spaces`, `meta.context_labels`) so clients can display or filter by context. The most recent commits (`restructure context labels of objects`, `update memgraph context_label test`) reworked the shape of `context_labels`.

Tests: `pangloss-memgraph/tests/test_create.py::test_write_semantic_spaces`; model-level tests in `test_create_model.py` and `test_create_db_model.py`.

## Status

- ✅ Declaring spaces, generating `Create`/`CreateDB`/`View` models, propagating labels on create, writing to Memgraph.
- ✅ Semantic spaces are propagated through updates too: updating a document rewrites `semantic_spaces` and `context_labels` on its nodes (tested). The matching item in `pangloss-models/todo.md` is still unticked.
- ⏳ Querying by semantic space is not implemented.

## Conjunctions

`Conjunction` subclasses work similarly as generic wrappers (`Causes[Statement, Statement]` has `cause` and `result` slots) and are likewise stored as nodes (with their slots such as `cause` and `result` as relations), but, unlike spaces, are not involved in context-label propagation (the propagation code only treats `SemanticSpace` specially). They are declared and generate models; see [Defining models](models.md#conjunction).
