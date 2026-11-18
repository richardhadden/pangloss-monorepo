"""What has been declared (`DerivedEdge` classes, rules, types of rules), and what `initialise` made of it"""

from typing import TYPE_CHECKING, Any, ClassVar

if TYPE_CHECKING:
    from pangloss_derived.declare import DerivedEdge


class PanglossDerivedError(Exception):
    """A `DerivedEdge` class or a rule is not right: the message names it, and what is wrong"""


class DerivedRegistry:
    classes: ClassVar[dict[str, type["DerivedEdge"]]] = {}
    rules: ClassVar[dict[str, Any]] = {}
    types: ClassVar[dict[str, Any]] = {}

    # (made by `initialise`)
    checked: ClassVar[dict[str, Any]] = {}
    """The checked rules (`CheckedRule`), by name"""
    documents: ClassVar[dict[str, Any]] = {}
    """The checked rules that derive documents (`CheckedRule`, with a `template`), by name. Not in `checked`: the
    worker of facts does not run them"""
    order: ClassVar[list[str]] = []
    """Every rule, those that read derived documents after the rules that write them"""
    readers: ClassVar[dict[str, list[str]]] = {}
    """For each rule that derives documents: the rules whose patterns can match what it writes"""
    triggers: ClassVar[dict[str, list[Any]]] = {}
    """For each class of head node (by name): the places (`Seed`) of the rules its nodes can be at"""
    initialised: ClassVar[bool] = False

    @classmethod
    def add_class(cls, model: type["DerivedEdge"]) -> None:
        name = model.__name__
        known = cls.classes.get(name)
        if (
            known is not None
            and known is not model
            and known.__module__ != model.__module__
        ):
            raise PanglossDerivedError(
                f"There are two DerivedEdge classes called {name} ({known.__module__} and {model.__module__})"
            )
        cls.classes[name] = model
        cls.initialised = False

    @classmethod
    def add_rule(cls, rule: Any) -> None:
        known = cls.rules.get(rule.name)
        if known is not None and known.function.__module__ != rule.function.__module__:
            raise PanglossDerivedError(
                f"There are two rules called {rule.name} ({known.function.__module__} and "
                f"{rule.function.__module__}): give one a `name=`"
            )
        cls.rules[rule.name] = rule
        cls.initialised = False

    @classmethod
    def add_type(cls, rule_type: Any) -> None:
        known = cls.types.get(rule_type.name)
        if known is not None and known != rule_type:
            raise PanglossDerivedError(
                f"There are two RuleTypes called {rule_type.name}, with different descriptions"
            )
        cls.types[rule_type.name] = rule_type

    @classmethod
    def reset(cls) -> None:
        cls.classes = {}
        cls.rules = {}
        cls.types = {}
        cls.checked = {}
        cls.documents = {}
        cls.order = []
        cls.readers = {}
        cls.triggers = {}
        cls.initialised = False

    @classmethod
    def all_checked(cls) -> dict[str, Any]:
        """The checked rules of both kinds: those that derive edges, and those that derive documents"""
        return {**cls.checked, **cls.documents}

    @classmethod
    def concrete_classes(cls) -> dict[str, type["DerivedEdge"]]:
        return {
            name: model
            for name, model in cls.classes.items()
            if not model._meta.abstract
        }
