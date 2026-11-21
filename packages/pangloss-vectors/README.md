# pangloss-vectors

Similarity: a vector for each document and entity, made by **parts** that other packages give (`"class"`, here,
from the hierarchy of classes; `"graph"`, from `pangloss-fastrp`), stored on nodes of their own, kept current after
writes and searched through the backend's vector index ("documents like this one").

Being built (`implementation_docs/similarity-build-plan.md`, phase 2). So far: the `Part` protocol that every part is
built against, `register_part`, profiles (a weight for each part), the settings, and the store of the vectors
(`store.py`: generations and the switch to a new one, in Cypher both backends run).

```python
# settings.py
INSTALLED_APPS = [..., "pangloss_vectors"]
VECTORS_PROFILES = {"default": {"graph": 1, "class": 0.1}}
```

```python
# models.py
from pangloss_vectors import VectorsMeta


# ("people like this one": an index of its own)
class Person(Entity):
    _vectors_meta = VectorsMeta(searchable=True)


# (no vectors at all)
class Note(Document):
    _vectors_meta = VectorsMeta(include=False)
```

The vector indexes follow the models, and `makemigrations` writes them in the project's migrations.

A part is an object with `name`, `local`, `requires`, `weight`, `dimension()`, `signature()`, `rebuild()`,
`refresh()` and `overlay()` (`pangloss_vectors.Part`), given to `register_part` when its package is imported.

Needs a backend with Cypher and a vector index (`requires = {"cypher", "vector_index"}`). See
[the build plan](../../implementation_docs/similarity-build-plan.md).
