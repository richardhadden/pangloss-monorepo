# pangloss-vectors

Similarity: a vector for each document and entity, made by **parts** that other packages give (`"class"`, here,
from the hierarchy of classes; `"graph"`, from `pangloss-fastrp`), stored on nodes of their own, kept current after
writes and searched through the backend's vector index ("documents like this one").

Being built (`implementation_docs/similarity-build-plan.md`, phase 2). So far: the `Part` protocol that every part is
built against, `register_part`, profiles (a weight for each part) and the settings.

```python
# settings.py
INSTALLED_APPS = [..., "pangloss_vectors"]
VECTORS_PROFILES = {"default": {"graph": 1, "class": 0.1}}
```

A part is an object with `name`, `local`, `requires`, `weight`, `dimension()`, `signature()`, `rebuild()`,
`refresh()` and `overlay()` (`pangloss_vectors.Part`), given to `register_part` when its package is imported.

Needs a backend with Cypher and a vector index (`requires = {"cypher", "vector_index"}`). See
[the build plan](../../implementation_docs/similarity-build-plan.md).
