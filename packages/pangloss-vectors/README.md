# pangloss-vectors

Similarity: a vector for each document and entity, made by **parts** that other packages give (`"class"`, here,
from the hierarchy of classes; `"graph"`, from `pangloss-fastrp`), stored on nodes of their own, kept current after
writes and searched through the backend's vector index ("documents like this one").

Built (`implementation_docs/similarity-build-plan.md`, phases 2, 5 and 6): the `Part` protocol that every part is
built against, `register_part`, profiles (a weight for each part), the settings, the store of the vectors
(`store.py`: generations and the switch to a new one, in Cypher both backends run), the class part (`class_part.py`:
the hierarchy of the models as a vector, `VECTORS_CLASS_DECAY`), search (`nearest`, `search.py`), a rebuild under a
lease and the status of what is built (`rebuild.py`, `status.py`), the commands, an admin job, the routes, the worker
that keeps vectors current after writes (`worker.py`) and an interface module (the section "Similar", the part of
`/admin`). Not built: a model method and the SDK's side. How to use it is `guide/vectors/`; the whole is described in
[vectors](../../implementation_docs/vectors.md).

```python
from pangloss_vectors import nearest

found = await nearest(str(person.id), group="Person", k=10)
found.status  # "ok", "pending" (no vector yet), "rebuild_due"
found.hits  # [Hit(id, type, score), ...], nearest first
```

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

```sh
pangloss vectors rebuild [--part class]     # every vector made again; searches meanwhile read the old ones
pangloss vectors status                     # what is in use, and whether a rebuild is due, and why
pangloss vectors weights                    # the profiles' weights; each part's dimension and signature
```

`GET /api/Person/{id}/similar?type=Person&limit=10` gives `{"status": "ok", "results": [{...reference view...,
"similarity": 0.93}, ...]}`; `GET /api/vectors/status` (logged in) the status.

A part is an object with `name`, `local`, `requires`, `weight`, `dimension()`, `signature()`, `rebuild()`,
`refresh()` and `overlay()` (`pangloss_vectors.Part`), given to `register_part` when its package is imported.

Needs a backend with Cypher and a vector index (`requires = {"cypher", "vector_index"}`). See
[the build plan](../../implementation_docs/similarity-build-plan.md).
