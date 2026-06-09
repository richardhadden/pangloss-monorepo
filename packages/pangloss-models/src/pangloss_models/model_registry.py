import heapq
import importlib
from inspect import iscoroutinefunction
from itertools import chain
from typing import TYPE_CHECKING, ClassVar, get_args, get_origin
from uuid import UUID

from pydantic import AnyHttpUrl, BaseModel

from pangloss_models.exceptions import (
    PanglossImportError,
    PanglossInitialisationError,
    PanglossModelError,
)

if TYPE_CHECKING:
    from pangloss_models.model_bases.base_models import _DeclaredClass


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

    _models: ClassVar[list[type[_DeclaredClass]]] = []
    _model_set: ClassVar[set[type[_DeclaredClass]]] = set()
    _model_dict: ClassVar[dict[str, type[_DeclaredClass]]] = dict()

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

        deps = set()

        deps.add(get_parent_class(model))
        meta = getattr(model, "__pydantic_generic_metadata__", None)
        if meta:
            for arg in meta.get("args", ()):
                if isinstance(arg, type) and issubclass(arg, BaseModel):
                    deps.add(arg)

        return deps

    @classmethod
    def _annotation_deps(cls, model: type[_DeclaredClass]) -> set[type[_DeclaredClass]]:
        """
        Optional light inference:
        Extract BaseModel types from annotations.
        """
        deps = set()

        for field in getattr(model, "model_fields", {}).values():
            ann = field.annotation

            stack = [ann]
            while stack:
                tp = stack.pop()

                if isinstance(tp, type) and issubclass(tp, BaseModel):
                    deps.add(tp)
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
            for dep in deps:
                indegree[node] += 1

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

        cyclic = {n for n in graph if indegree[n] > 0}
        del heap
        return ordered, cyclic

    # ----------------------------
    # Finalisation
    # ----------------------------

    @classmethod
    def finalise(cls, *, allow_cycles: bool = True):
        """
        1. Resolve Pydantic types
        2. Run topo-ordered initialisation
        """

        # --- Phase 1: Pydantic rebuild ---
        namespace = cls.all_models()

        for model in cls._models:
            model.model_rebuild(force=True, _types_namespace=namespace)

        cls._initialise_models()

    # ----------------------------
    # Hook for your system
    # ----------------------------

    @classmethod
    def _initialise_models(cls, db_module: str | None = None):
        """
        Override or monkey-patch this.
        """

        from pangloss_models.initialise_models.initalise_incoming_relation_definitions import (
            initialise_incoming_relation_definitions,
        )
        from pangloss_models.initialise_models.initialise_create_db_model import (
            add_fields_to_create_db_model,
            initialise_create_db_model,
        )
        from pangloss_models.initialise_models.initialise_create_model import (
            add_fields_to_create_model,
            can_have_create_model,
            initialise_create_model,
        )
        from pangloss_models.initialise_models.initialise_field_definitions import (
            initialise_field_definitions,
        )
        from pangloss_models.initialise_models.initialise_head_view_model import (
            can_have_head_view_model,
            initialise_head_view_model,
        )
        from pangloss_models.initialise_models.initialise_reference_models import (
            initialise_reference_set_model,
            initialise_reference_view_model,
        )
        from pangloss_models.initialise_models.initialise_update_db_model import (
            add_fields_to_update_db_model,
            initialise_update_db_model,
        )
        from pangloss_models.initialise_models.initialise_update_model import (
            add_fields_to_update_model,
            can_have_update_model,
            initialise_update_model,
        )
        from pangloss_models.initialise_models.initialise_view_model import (
            add_fields_to_view_model,
            can_have_view_model,
            initialise_view_model,
        )
        from pangloss_models.model_bases.document import Document, _DocumentCreateBase

        graph = cls._build_graph()
        order, cyclic = cls._toposort(graph)

        # To initialise field definitions, we need to initialise in
        # declaration order
        for model in cls._model_dict.values():
            try:
                initialise_field_definitions(model)
            except PanglossModelError as e:
                raise PanglossModelError(e)
            except Exception as e:
                print(f"Exception on init fields of model {model.__name__}", e)

        for model in cls._model_dict.values():
            if hasattr(model, "__metatype__") and model.__metatype__ in [
                "Document",
                "Entity",
                "ReifiedRelationDocument",
            ]:
                try:
                    initialise_incoming_relation_definitions(model)
                except PanglossModelError as e:
                    raise e
                except Exception as e:
                    print(f"Exception on init fields of model {model.__name__}", e)

        for model in chain(order, cyclic):
            initialise_reference_set_model(model)
            initialise_reference_view_model(model)

        for model in chain(cyclic, order):
            if can_have_create_model(model):
                initialise_create_model(model)
                add_fields_to_create_model(model.Create, frozenset())

            initialise_create_db_model(model)

            add_fields_to_create_db_model(model)

        for model in chain(cyclic, order):
            if can_have_update_model(model):
                initialise_update_model(model=model)
                add_fields_to_update_model(model.Update, frozenset())

            initialise_update_db_model(model)

            add_fields_to_update_db_model(model)

        for model in chain(cyclic, order):
            if can_have_view_model(model):
                initialise_view_model(model=model)
                add_fields_to_view_model(model.View, frozenset())

        for model in chain(cyclic, order):
            if can_have_head_view_model(model):
                initialise_head_view_model(model)

        from pangloss_core.settings import SETTINGS

        database = SETTINGS.DATABASE_MODULE
        print(database)
        try:
            database_exposed_functions_module = importlib.import_module(
                f"{database}.exposed_functions"
            )
        except ImportError:
            raise PanglossImportError(
                f"Failed to find database functions in given module '{database}'"
            )

        is_async = iscoroutinefunction(database_exposed_functions_module.get_document)
        if is_async:

            async def get_document_function_async(cls: Document, id: UUID | AnyHttpUrl):
                return await database_exposed_functions_module.get_document(cls, id)

            Document.get = classmethod(get_document_function_async)  # type: ignore
        else:

            def get_document_function_sync(cls: Document, id: UUID | AnyHttpUrl):
                return database_exposed_functions_module.get_document(cls, id)

            Document.get = classmethod(get_document_function_sync)  # type: ignore

        is_async = iscoroutinefunction(
            database_exposed_functions_module.create_document
        )
        if is_async:

            async def create_document_function_async(self: _DocumentCreateBase):
                return await database_exposed_functions_module.create_document(self)

            _DocumentCreateBase.save = create_document_function_async  # type: ignore
        else:

            def create_document_function_sync(self: _DocumentCreateBase):
                return database_exposed_functions_module.create_document(self)

            _DocumentCreateBase.save = create_document_function_sync  # type: ignore
        """
        def save_func_for_create(self):
            print(f"Using database {database}")
            db_instance = self._to_db_model()
            database_exposed_functions_module.save(db_instance)


        _DocumentCreateBase.save = save_func_for_create  # ty:ignore[invalid-assignment]
        _EntityCreateBase.save = save_func_for_create  # ty:ignore[invalid-assignment]
        """
