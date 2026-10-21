# Meta slots: extra metas on a model class ⏳

**Status: a design, not built.** Parts of it were tried in throwaway scripts (marked *tried*); the rest
is untested.

An optional package (the interface, a search package, ...) should be able to keep its own settings for a
model class **on the class**, next to `_meta`, without `pangloss_models` knowing about it:

```python
from pangloss_interface import InterfaceMeta
from pangloss_models.model_bases.entity import Entity


class Person(Entity):
    name: str
    _interface_meta = InterfaceMeta(card="PersonCard")


class Student(Person):  # inherits Person's
    pass
```

and read it as `Person._interface_meta` (the object, typed, inherited).

## Why this is not just "patch it onto `_DeclaredClass`"

*Tried*, and it does not work from outside:

1. **Pydantic makes `_interface_meta = X` a private attribute.** An unannotated name with a leading
   underscore goes into `__private_attributes__` and is removed from the class namespace. Reading
   `Person._interface_meta` gives the `ModelPrivateAttr` wrapper, not `X`. (The `ClassVar` check for names a
   base declares comes *after* the private-name check in `inspect_namespace`, so adding the name to
   `__class_vars__` of the bases does not help.) The value is at
   `Person.__private_attributes__["_interface_meta"].default`.
2. **Each model kind defines its own `__pydantic_init_subclass__`** (`Entity`, `Document`, `Conjunction`,
   `Trait`, `EmbeddedDocument`, `EdgeModel`, `AnnotatedValue`, `SemanticSpace`, `ReifiedRelation`, and
   `_BaseObject`), and most do not call `super()`. A hook patched onto `_DeclaredClass` is never reached.

So the hook has to be in `pangloss_models`, called from each kind. The *content* of a slot belongs to the
optional package.

## Design

### The registry (`pangloss_models/meta_slots.py`)

```python
def register_meta_slot(name: str, meta_class: type) -> None:
    """An optional package says: `name` (a leading-underscore name, ending `_meta`) on a model class
    holds an instance of `meta_class`."""

def apply_meta_slots(cls) -> None:
    """For each registered slot: find the value, check it, and set it on `cls` as a plain class
    attribute."""

def meta_slots() -> dict[str, type]: ...
```

`apply_meta_slots(cls)`, for each registered `(name, meta_class)`:

1. **Own value**: `cls.__private_attributes__.get(name)`; its `.default`, if the class set one in its own
   body (not inherited: compare with the parent's private attribute, as `__private_attributes__` is
   merged from the bases).
2. **Check**: if the own value is not an instance of `meta_class`, raise `PanglossMetaError` naming the
   class and the slot (at class creation, so the mistake is at the line that made it).
3. **Inherit**: if there is no own value, use the value the nearest parent has (`cls.__mro__[1:]`, the
   first with `name` in its `__dict__`), else `None`.
4. **Set**: `setattr(cls, name, value)`. This is what `Entity` already does with `cls._meta`. The result is
   a real class attribute, so `Person._interface_meta` is the object (and shadows the private-attribute
   wrapper, which is why the value is also set when it is `None`).

It has no merge rules: a subclass's value **replaces** its parent's. That is the right thing for "which
component", and enough for settings that are one object. A slot that wants fields to accumulate through
the hierarchy can make its meta a `BaseMeta` of `pydantic_meta_kit` and merge in its own accessor (see
"Later").

### Calling it

Core calls `apply_meta_slots(cls)` from the one place each kind finishes setting up a class: at the end of
each `__pydantic_init_subclass__` (or, if the kinds can be made to share a base hook, once). The kinds that
need it are those a user subclasses to make a model: `Document`, `Entity`, `Conjunction`, `Trait`,
`EmbeddedDocument`, `EdgeModel`, `AnnotatedValue`, `SemanticSpace`, `ReifiedRelation`.

`_BaseObject.__pydantic_init_subclass__` (which does call `super()`) is the natural single place **if** every
kind's hook calls up to it. Today most do not; changing them to `return super()...(**kwargs)` at the end is
a small edit per file, but check the ones that return early (`ReifiedRelation`).

Registering a slot after models exist: `register_meta_slot` also applies the slot to every class already
registered (`ModelRegistry._models`), so import order does not matter; for the classes that were declared
before it, the value is whatever their own private attribute holds.

### The optional package

`pangloss_interface` (light module, no heavy imports, so `models.py` can import it cheaply):

```python
# pangloss_interface/meta.py
@dataclass(frozen=True)
class InterfaceMeta:
    card: str | None = None      # name of a component, see the component map
    view: str | None = None
    edit: str | None = None


# pangloss_interface/__init__.py   (runs when the package is imported)
register_meta_slot("_interface_meta", InterfaceMeta)
```

A project that never imports `pangloss_interface` never registers the slot. A model that sets
`_interface_meta` without it being registered is, as now, an ordinary private attribute that nothing reads
(see "Open questions": should core warn?).

Reading: `Person._interface_meta`, or `getattr(cls, "_interface_meta", None)` for a class from before the
package was imported. The exporter (`typescript.py`) writes each model's slot into the generated
definitions (`generated/models.ts`), where the JavaScript lookup (model → component, with fallback up the
model's parents) uses it.

### Typing and stubs

A type checker does not know `_interface_meta` exists on `Entity`. Two ways, both small:

- the user annotates in the class: `_interface_meta: ClassVar[InterfaceMeta] = InterfaceMeta(...)`
  (this also keeps pydantic from treating it as private, so step 1 of "Design" would then find it as a
  plain class attribute: handle both);
- `pangloss make-stubs` (`typestubs.py`) writes `_interface_meta: ClassVar[InterfaceMeta | None]` for
  each registered slot into the stubs.

### Tests

1. A slot set on a class is the object on the class (`Person._interface_meta is the_instance`).
2. A subclass without one inherits the nearest parent's; one with one replaces it; a class with none
   anywhere has `None`.
3. A wrong type raises `PanglossMetaError` at class creation.
4. A slot registered *after* some models were declared is applied to them.
5. An unregistered `_something_meta` is left alone.
6. Each kind (the list above) gets a test: one per kind catches a hook that was not changed.
7. `ModelRegistry._reset()` keeps registered slots (they belong to the process, not the models).

### Order of work

1. Fix `pydantic_meta_kit` first (a grandchild loses its parent's meta values, and `_meta_class` is global),
   since the hooks in the kinds read `_meta` and a slot may later want its merge rules.
2. `meta_slots.py` with the registry and `apply_meta_slots`, plus its tests on a stand-in class.
3. Call it from each kind; run the whole suite.
4. `pangloss_interface`: `InterfaceMeta`, the registration, the exporter, the stubs.

## Open questions

- **Warn on an unregistered slot?** Core cannot tell `_interface_meta` from any private attribute, but
  names ending `_meta` that are not registered could be reported by `initialise()` (a typo, or a missing
  import).
- **Slot names**: a convention (`_<package>_meta`) is enough; nothing stops two packages claiming one name.
  `register_meta_slot` should refuse a name that is taken by another class.
- **Accumulating slots**: if a slot needs `ACCUMULATE` rules, its meta is a `BaseMeta` and `apply_meta_slots`
  would merge with `parent & child` rather than replace. Do this once `pydantic_meta_kit`'s inheritance is fixed.
- **Generic classes** (`Foo[int]`): treated by pydantic as a new subclass, so the value is inherited from
  `Foo` by step 3, which is what is wanted; check it with the kinds that already special-case generics.
- **Instances**: `__private_attributes__` are copied to instances; the class attribute set in step 4 does not
  show on `instance._interface_meta` the same way. Nothing needs it, but a test should say which.
