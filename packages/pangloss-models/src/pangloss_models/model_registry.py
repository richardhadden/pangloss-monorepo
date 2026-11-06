import functools
import heapq
from collections.abc import Callable
import logging
from itertools import chain
from typing import ClassVar, get_args, get_origin

from pydantic import BaseModel
from pydantic.alias_generators import to_camel
lazy from pangloss_core import storage_of

from pangloss_models.exceptions import (
    PanglossImportError,
    PanglossInitialisationError,
    PanglossModelError,
)
lazy from pangloss_models.initialise_models.initialise_create_db_model import (
    add_fields_to_create_db_model,
    initialise_create_db_model,
)
lazy from pangloss_models.initialise_models.initialise_create_model import (
    add_fields_to_create_model,
    can_have_create_model,
    initialise_create_model,
)
lazy from pangloss_models.initialise_models.initialise_edit_view_model import (
    can_have_edit_view_model,
    initialise_edit_view_model,
)
lazy from pangloss_models.initialise_models.check_relation_targets import (
    check_relation_targets,
)
lazy from pangloss_models.initialise_models.initialise_field_definitions import (
    initialise_field_definitions,
)
lazy from pangloss_models.initialise_models.initialise_head_view_model import (
    can_have_head_view_model,
    initialise_head_view_model,
)
lazy from pangloss_models.initialise_models.initialise_incoming_relation_definitions import (
    initialise_incoming_relation_definitions,
)
lazy from pangloss_models.initialise_models.initialise_reference_models import (
    initialise_reference_set_model,
    initialise_reference_view_model,
)
lazy from pangloss_models.initialise_models.initialise_update_db_model import (
    add_fields_to_update_db_model,
    initialise_update_db_model,
)
lazy from pangloss_models.initialise_models.initialise_update_model import (
    add_fields_to_update_model,
    can_have_update_model,
    initialise_update_model,
)
lazy from pangloss_models.search_where import initialise_where_models
lazy from pangloss_models.initialise_models.initialise_view_model import (
    add_fields_to_view_model,
    can_have_view_model,
    initialise_view_model,
)
lazy from pangloss_models.model_bases.base_models import (
    _ActionClass,
    _DeclaredClass,
)
lazy from pangloss_models.model_bases.document import (
    Document,
    _DocumentCreateBase,
    _DocumentUpdateBase,
    refuse_unless_created_directly,
)
lazy from pangloss_models.model_bases.entity import (
    Entity,
    _EntityCreateBase,
    _EntityUpdateBase,
)
lazy from pangloss_models.model_bases.model_tools import (
    forget_schema,
    inherit_fields,
    rebuilds_put_off,
)


def apply_camel_case_aliases(model: type[BaseModel]) -> None:
    """Give each field of the model its camelCase alias, for input and output (in
    the JSON of the API: `born_in` is `bornIn`). The name itself is still accepted.

    Fields that were given a (validation) alias already are completed with the
    others; fields with an alias of their own that is not the camelCase one are left
    as they are."""
    for name, field in model.model_fields.items():
        alias = to_camel(name)
        if alias == name:
            continue
        # (`alias_priority` 2 is "set explicitly": the generator will not replace it)
        if field.alias is None:
            field.alias = alias
        if field.validation_alias is None:
            field.validation_alias = alias
        if field.serialization_alias is None:
            field.serialization_alias = alias
        field.alias_priority = 2


logger = logging.getLogger("pangloss.models.registry")


# Properties that the database keeps on the node of a head document or entity (the search, the lists and the
# review read them): not names for a field
RESERVED_PROPERTIES = frozenset(
    {
        "deleted",
        "published",
        "review_status",
        "reviewed_by",
        "reviewed_at",
        "marked_for_deletion",
    }
)


def refusing_unless_created_directly(create: Callable) -> Callable:
    """`create` (sync or async), refusing first a document that cannot be made on its own"""

    @functools.wraps(create)
    def save(instance, *args, **kwargs):
        refuse_unless_created_directly(instance._owner)
        return create(instance, *args, **kwargs)

    return save


class ModelRegistry:
    """
    Deterministic model registry + dependency resolver.

    Responsibilities:
    - Register models
    - Build dependency graph
    - Provide stable topological ordering
    - Finalise models (pydantic rebuild + model initialisation procedure)
    """

    def __init__(self):
        raise PanglossInitialisationError(
            "ModelRegistry cannot be initialised or subclassed"
        )

    def __init_subclass__(cls) -> None:
        raise PanglossInitialisationError(
            "ModelRegistry cannot be initialised or subclassed"
        )

    @classmethod
    def _reset(cls):

        cls._models = []
        cls._model_set = set()
        cls._model_dict = {}
        cls._action_classes = []
        for reset in cls.on_reset:
            reset()

        # (the models made for bindings and generics refer to the classes that were registered)
        from pangloss_models.initialise_models.builder import clear_caches

        clear_caches()

    _models: ClassVar[list[type[_DeclaredClass]]] = []
    _model_set: ClassVar[set[type[_DeclaredClass]]] = set()
    _model_dict: ClassVar[dict[str, type[_DeclaredClass]]] = {}

    _action_classes: ClassVar[list[type[_ActionClass]]] = []

    before_finalise: ClassVar[list[Callable[[], None]]] = []
    """Functions an optional package adds, called at the start of `finalise` (the settings are loaded and the models
    are declared, but nothing is initialised): to complete the models it made (`pangloss-typology` adds the label
    fields of the languages). Not cleared by `_reset`."""

    on_reset: ClassVar[list[Callable[[], None]]] = []
    """Functions an optional package adds, called by `_reset` (the tests' fresh start), to forget what it keeps of the
    models (`pangloss-derived`: the classes and rules declared). Not cleared by `_reset`."""

    after_finalise: ClassVar[list[Callable[[], None]]] = []
    """Functions an optional package adds, called at the end of `finalise`, when every model and its classes are made
    (`pangloss-derived` loads the `derived.py` of the apps, and checks the rules against the models). Not cleared by
    `_reset`."""

    # ----------------------------
    # Registration
    # ----------------------------

    @classmethod
    def register(cls, model: type[_DeclaredClass]) -> None:

        if model not in cls._model_set:
            cls._models.append(model)
            cls._model_set.add(model)
            cls._model_dict[model.__name__] = model

    @classmethod
    def all_models(cls) -> dict[str, type[_DeclaredClass]]:
        return {m.__name__: m for m in cls._models}

    # ----------------------------
    # Dependency extraction
    # ----------------------------

    @classmethod
    def _explicit_deps(cls, model: type[_DeclaredClass]) -> set[type[_DeclaredClass]]:
        return set(getattr(model, "__depends_on__", []))

    @classmethod
    def _generic_deps(cls, model: type[_DeclaredClass]) -> set[type[_DeclaredClass]]:
        from pangloss_models.utils import get_parent_class

        deps: set[type[_DeclaredClass]] = set()

        if parent_class := get_parent_class(model):
            deps.add(parent_class)
        meta = getattr(model, "__pydantic_generic_metadata__", None)
        if meta:
            for arg in meta.get("args", ()):
                if (
                    isinstance(arg, type)
                    and issubclass(arg, _DeclaredClass)
                    and issubclass(arg, BaseModel)
                ):
                    deps.add(arg)

        return deps

    @classmethod
    def _annotation_deps(cls, model: type[_DeclaredClass]) -> set[type[_DeclaredClass]]:
        """
        Optional light inference:
        Extract BaseModel types from annotations.
        """
        from pangloss_models.model_bases.embedded import Embedded
        from pangloss_models.utils import generic_get_subclasses

        deps = set()

        for field in getattr(model, "model_fields", {}).values():
            ann = field.annotation

            stack = [ann]
            while stack:
                tp = stack.pop()

                if isinstance(tp, type) and issubclass(tp, BaseModel):
                    deps.add(tp)
                    # (a field of an embedded type takes any of its subclasses, as their own `Create` and the rest: so
                    # those are made first. Otherwise a model whose name sorts before theirs, `chronicle.models.Journey`
                    # before `pangloss_dates.models.ExactDate`, finds the `Create` each inherits from the base, and takes
                    # only the base)
                    if issubclass(tp, Embedded):
                        deps |= generic_get_subclasses(tp, include_abstract=True)
                    continue

                origin = get_origin(tp)
                if origin:
                    stack.extend(get_args(tp))

        return deps

    @classmethod
    def _model_dependencies(
        cls, model: type[_DeclaredClass]
    ) -> list[type[_DeclaredClass]]:
        deps = set()

        deps |= cls._explicit_deps(model)
        deps |= cls._generic_deps(model)
        deps |= cls._annotation_deps(model)

        model_set = set(cls._models)
        # Only keep registered models and avoid self-dependency
        deps = {d for d in deps if d in model_set and d is not model}

        return sorted(deps, key=cls._model_key)

    # ----------------------------
    # Graph
    # ----------------------------

    @classmethod
    def _model_key(cls, model: type[_DeclaredClass]) -> str:
        return f"{model.__module__}.{model.__qualname__}"

    @classmethod
    def _build_graph(cls) -> dict[type[_DeclaredClass], list[type[_DeclaredClass]]]:
        graph = {}

        for model in sorted(cls._models, key=cls._model_key):
            graph[model] = cls._model_dependencies(model)

        return graph

    # ----------------------------
    # Topological sort (stable)
    # ----------------------------

    @classmethod
    def _toposort(cls, graph):
        indegree = {n: 0 for n in graph}

        for node, deps in graph.items():
            indegree[node] += len(deps)

        heap = []
        for node, deg in indegree.items():
            if deg == 0:
                heapq.heappush(heap, (cls._model_key(node), id(node), node))

        ordered = []

        while heap:
            _, _, node = heapq.heappop(heap)
            ordered.append(node)

            for other, deps in graph.items():
                if node in deps:
                    indegree[other] -= 1
                    if indegree[other] == 0:
                        heapq.heappush(heap, (cls._model_key(other), id(other), other))

        left = {n for n in graph if indegree[n] > 0}
        del heap
        return ordered, cls._order_cyclic(graph, left)

    @classmethod
    def _order_cyclic(cls, graph, left: set) -> list:
        """What the sort could not order (the models in a cycle, and those that depend on one), each after what it
        depends on, except within a cycle: the cycles (strongly connected components, by Tarjan's algorithm, which
        gives each only after those it depends on), and in each, by name. (A model that only depends on a cycle, an
        `Appointment` of a `Person` whose typology refers back to it, comes after it, and after the dates it embeds.)"""
        index: dict = {}
        low: dict = {}
        stack: list = []
        on_stack: set = set()
        ordered: list = []

        def visit(node) -> None:
            index[node] = low[node] = len(index)
            stack.append(node)
            on_stack.add(node)
            for dep in graph[node]:
                if dep not in left:
                    continue
                if dep not in index:
                    visit(dep)
                    low[node] = min(low[node], low[dep])
                elif dep in on_stack:
                    low[node] = min(low[node], index[dep])
            if low[node] == index[node]:
                component = []
                while True:
                    member = stack.pop()
                    on_stack.discard(member)
                    component.append(member)
                    if member is node:
                        break
                ordered.extend(sorted(component, key=cls._model_key))

        for node in sorted(left, key=cls._model_key):
            if node not in index:
                visit(node)
        return ordered

    # ----------------------------
    # Finalisation
    # ----------------------------

    @classmethod
    def _check_field_names(cls, model) -> None:
        """A field cannot be named as a property that the database keeps on the node of a head document or entity
        for its own use: its value would hide the node (`deleted`, `published`) or be taken for the state of
        its review"""
        clash = sorted(RESERVED_PROPERTIES & set(model.model_fields))
        if clash:
            raise PanglossModelError(
                f"{model.__name__} has a field named {', '.join(repr(n) for n in clash)}, which Pangloss keeps on "
                "every head node for itself (see docs/review.md): call it something else"
            )

    @classmethod
    def finalise(cls, *, allow_cycles: bool = True, bind_database: bool = True):
        """
        1. Resolve Pydantic types
        2. Run topo-ordered initialisation
        3. Attach the database functions (`get`, `save`, ...), which needs the settings to be loaded;
           `bind_database=False` makes the models alone, without them
        """

        for before in cls.before_finalise:
            before()

        # --- Phase 1: Pydantic rebuild ---
        namespace = cls.all_models()
        logger.debug(
            "Initialising %s models (bind database: %s): %s",
            len(namespace),
            bind_database,
            ", ".join(namespace),
        )

        for model in cls._models:
            model.model_rebuild(force=True, _types_namespace=namespace)

        cls._initialise_models()
        logger.debug("Models initialised")
        if bind_database:
            cls._bind_database_functions()
            logger.debug("Database functions bound to the models")

        for after in cls.after_finalise:
            after()

    # ----------------------------
    # Model initialisation
    # ----------------------------

    @classmethod
    def _initialise_models(cls):
        """Generate all action classes (Create, View, etc.) for the registered models."""

        # (a model is to be rebuilt each time it is given fields: that is put off, to be done once, below)
        with rebuilds_put_off() as put_off:
            graph = cls._build_graph()
            order, cyclic = cls._toposort(graph)

            # To initialise field definitions, we need to initialise in
            # declaration order
            for model in cls._model_dict.values():
                initialise_field_definitions(model)

            check_relation_targets(list(cls._model_dict.values()))

            from pangloss_models.indexes import check_indexes

            for model in cls._model_dict.values():
                if hasattr(model, "__metatype__") and model.__metatype__ in [
                    "Document",
                    "Entity",
                    "Embedded",
                ]:
                    check_indexes(model)

            for model in cls._model_dict.values():
                if hasattr(model, "__metatype__") and model.__metatype__ in [
                    "Document",
                    "Entity",
                ]:
                    cls._check_field_names(model)

            # (the incoming relations are worked out from all the models, so start again if this is not the first time)
            for model in cls._model_dict.values():
                model._meta.field_definitions.incoming_fields.clear()

            for model in cls._model_dict.values():
                if hasattr(model, "__metatype__") and model.__metatype__ in [
                    "Document",
                    "Entity",
                    "ReifiedRelationDocument",
                ]:
                    initialise_incoming_relation_definitions(model)

            for model in chain(order, cyclic):
                initialise_reference_set_model(model)
                initialise_reference_view_model(model)

            # (what the sort ordered first: none of it depends on what it could not, which is ordered as well as it can be)
            for model in chain(order, cyclic):
                if can_have_create_model(model):
                    initialise_create_model(model)
                    add_fields_to_create_model(model.Create, frozenset())

                initialise_create_db_model(model)

                add_fields_to_create_db_model(model)

            for model in chain(order, cyclic):
                if can_have_update_model(model):
                    initialise_update_model(model=model)
                    add_fields_to_update_model(model.Update, frozenset())

                initialise_update_db_model(model)

                add_fields_to_update_db_model(model)

            for model in chain(order, cyclic):
                if can_have_view_model(model):
                    initialise_view_model(model=model)
                    add_fields_to_view_model(model.View, frozenset())

            for model in chain(order, cyclic):
                if can_have_head_view_model(model):
                    initialise_head_view_model(model)
                if can_have_edit_view_model(model):
                    initialise_edit_view_model(model)

            # The variants with an edge model were made when their base had the fields it had then:
            # give them the ones it was given since
            for action_class in list(cls._action_classes):
                for variant in action_class._via.values():
                    inherit_fields(variant, action_class)

            # The fields added to the models above have to be given their camelCase
            # aliases (the `alias_generator` of the models only sees the fields they are
            # created with)
            for action_class in cls._action_classes:
                apply_camel_case_aliases(action_class)

            # The search patterns of the models (`Person.Where`; see docs/search-where-implementation.md)
            initialise_where_models(cls._model_dict.values())

        # A model embeds the schema of the models it refers to as they were when it was last rebuilt, so
        # models that refer to each other (an `Order` that orders a `Statement`, which may be an `Order`)
        # kept the half-made schema of the one that came first, and could be nested only so deep. Forget all
        # the schemas, then make them again: pydantic then meets the cycle while it makes a schema, and
        # makes it recursive, so there is no limit to the depth. (All of them: the classes made for the
        # models, and whatever else was to be rebuilt on the way, such as the search patterns. One that kept
        # its schema would be embedded as it was.)
        everything = list(dict.fromkeys([*cls._action_classes, *put_off]))
        for made in everything:
            forget_schema(made)
        for made in everything:
            made.model_rebuild(force=True)

    # ----------------------------
    # Database bindings
    # ----------------------------

    @classmethod
    def _bind_database_functions(cls):
        """Attach the storage backend's operations (`exposed_functions`) to the model base classes.

        The functions are assigned directly: sync and async functions both work as
        methods, so no wrapping is needed. They must take the class (or instance,
        for `save`) as their first argument. (The one exception: `save` of a document's
        `Create` first refuses a class with `create_directly=False`, for every backend.)"""

        # (read when used: the settings are set when a project makes them)
        storage = storage_of()
        try:
            exposed_functions = storage.operations
        except ImportError as error:
            raise PanglossImportError(
                f"Failed to find the functions of the storage backend '{storage.name}' "
                f"(in '{storage.package}')"
            ) from error

        Document.get = classmethod(exposed_functions.get_document)  # type: ignore
        Entity.get = classmethod(exposed_functions.get_entity)  # type: ignore
        Entity.get_for_edit = classmethod(exposed_functions.get_entity_for_edit)  # type: ignore
        Document.delete = classmethod(exposed_functions.delete_document)  # type: ignore
        Entity.delete = classmethod(exposed_functions.delete_entity)  # type: ignore
        Document.undelete = classmethod(exposed_functions.undelete_document)  # type: ignore
        Entity.undelete = classmethod(exposed_functions.undelete_entity)  # type: ignore
        Document.list = classmethod(exposed_functions.list_items)  # type: ignore
        Entity.list = classmethod(exposed_functions.list_items)  # type: ignore
        Entity.autocomplete = classmethod(exposed_functions.autocomplete)  # type: ignore
        Entity.references = classmethod(exposed_functions.references)  # type: ignore
        Document.search = classmethod(exposed_functions.search)  # type: ignore
        Entity.search = classmethod(exposed_functions.search)  # type: ignore

        _DocumentCreateBase.save = refusing_unless_created_directly(  # ty: ignore[invalid-assignment]
            exposed_functions.create_head_node
        )
        _EntityCreateBase.save = exposed_functions.create_head_node
        _DocumentUpdateBase.save = exposed_functions.update_head_node
        _EntityUpdateBase.save = exposed_functions.update_head_node
