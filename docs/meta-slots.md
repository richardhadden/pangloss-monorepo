# Meta slots: extra metas on a model class 🚧

**Status: built in `pangloss_models` (`meta_slots.py`, 21 tests). `pangloss_interface` uses it: `InterfaceMeta(colour=...)` (see [below](#interfacemeta-built)); `card`, `view` and `edit` are not built.**
The first users are `pangloss-zotero` (`_zotero_meta`, see [Zotero](zotero.md)) and the models' own
`_protect_meta` ([Protection](#protection-a-slot-of-the-models-own)). What is below is the design; where the build
differs, it says so ("Built:").

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

**Built:** there is one hook, not one per kind: `_DeclaredClass.__pydantic_init_subclass__` calls
`apply_meta_slots(cls)` (all the kinds end up there; the "most do not call `super()`" below was true of an
earlier version). The rest of this section is the design as first written.

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
    card: str | None = None  # name of a component, see the component map
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

## What was built

`pangloss_models/meta_slots.py`:

- `register_meta_slot(name, meta_class)`: the name must start with `_`, end with `_meta`, and not be `_meta`; a
  name used for another class is refused (the same class again is fine). It applies the slot to the models that
  exist already.
- `apply_meta_slots(cls)`: on every declared class (traits and generic parametrisations too): the class's own
  value is checked to be an instance (`PanglossMetaError` at the line that made the class); with none of its own,
  the nearest parent's is used; with none anywhere, `None`. It is set as a plain class attribute.
- `declared_slots(cls)`: **which slots the class set in its own body**. A subclass that only inherits is not in
  it. This is the answer to "a subclass's value replaces its parent's": it does, but a package can ask who *said*
  it (`pangloss-zotero` takes only a class's own `_zotero_meta` as a claim on a Zotero type).
- Slots belong to the process: `ModelRegistry._reset()` keeps them.
- Not built: a warning for an unregistered `_x_meta`; accumulating slots; stubs (`make-stubs`) for slots; the
  exporter writing a slot into `models.ts`. Instances do not see the slot differently from the class (tested: they
  read the class attribute).

### Protection: a slot of the models' own

`pangloss_models/protection.py` registers `_protect_meta = Protection(read_only=(...), delete_only_if="...")`.
It is for fields that something other than a person keeps up to date (the Zotero fields).

- The **API** refuses a create that sets a `read_only` field, an update that changes one (it reads the stored
  value; leaving a field out counts as changing it), and a delete of a model whose `delete_only_if` field is not
  true: all `403`, saying which. Code that writes through Python is not stopped (trusted), so the sync can write the
  fields. The remote SDK goes through the API and is covered.
- A subclass **adds** to its parents' protection (`protection_of` puts the declared values together: the fields are
  the union, the nearest `delete_only_if` wins), where a slot would otherwise replace it.
- Not built: the flag in `export_models()` and the generated TypeScript (so a form could show the fields
  read-only); it is a change to the exporter, its TypeScript type and the guard test that holds the two together.

## InterfaceMeta (built)

`pangloss_interface.InterfaceMeta` (`meta.py`, registered when `pangloss_interface` is imported) has one field so far:

- `colour`: one of Tailwind's base colours except black and white (`slate`, `gray`, `zinc`, `neutral`, `stone`, `mauve`,
  `olive`, `mist`, `taupe`, `red`, `orange`, `amber`, `yellow`, `lime`, `green`, `emerald`, `teal`, `cyan`, `sky`, `blue`,
  `indigo`, `violet`, `purple`, `fuchsia`, `pink`, `rose`); anything else is a `PanglossMetaError` where the class is made.

```python
class Negative[T](SemanticSpace[T]):
    _interface_meta = InterfaceMeta(colour="rose")
```

A subclass without its own has its parent's. `export_definitions()` (what the interface builds from) adds
`interfaceMeta: {"colour": ...} | null` to each model in `generated/models.ts`; `test_models_match_typescript.py`
holds the keys and the list of colours to the TypeScript types. The interface uses the colour for the **type block**
of a model (results, console), and for the **band** of a semantic space round an item in a list. Without one:
blue for entities, green for documents, and a colour by depth for a space.

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
