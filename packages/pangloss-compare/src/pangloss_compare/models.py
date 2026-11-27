"""The models of comparison (implementation_docs/compare.md, "A person's judgement"; the plan's step 6.5).

`EventJudgement` is what a person says of two statements: one event told twice (`agree`, `disagree`), two events
(`two_events`), or of a prescription and what came of it (`carried_out`, `carried_out_otherwise`,
`not_carried_out`, `breach`). It is abstract and names no statement class: the package does not know the project's.
The project declares the two citing fields, with these names, the prescription first where there is one:

    class StatementJudgement(EventJudgement):
        statement: Cites[Statement]
        other: Cites[Statement]

(A base with a type parameter, `EventJudgement[T]`, cannot be initialised as a top-level document: the plan's
"Phase 0 as found", 0.5.) Each class below `EventJudgement` that is not abstract is checked at `initialise()`
(`check_judgement_classes`): `statement` and `other` are each a single `Cites[...]` that protects what it cites, of
documents. A judgement is written by the ordinary `POST /api/NAME` of the project's class; the comparison of a
statement reads them (`judgements.py`), and the newest of a pair overrides what is worked out (`compare.py`)."""

from typing import Any, Literal

from pangloss_models import Document, ModelRegistry, PanglossModelError

# (D7: what a person may say of a pair)
VERDICTS = (
    "agree",
    "disagree",
    "two_events",
    "carried_out",
    "carried_out_otherwise",
    "not_carried_out",
    "breach",
)

# The two citing fields a project's class declares, in this order (the prescription first where there is one)
CITING = ("statement", "other")

BASE = "EventJudgement"


class EventJudgement(Document):
    """What a person says of two statements (a pair the comparison found). The project's class below it cites the
    two (`statement` and `other`: the module's docstring)"""

    _meta = Document.Meta(abstract=True)

    verdict: Literal[
        "agree",
        "disagree",
        "two_events",
        "carried_out",
        "carried_out_otherwise",
        "not_carried_out",
        "breach",
    ]
    fields: list[str] = []
    """The fields the two disagree on, or of what was carried out otherwise the targets missed"""
    note: str = ""


def _why_not(definition: Any) -> str | None:
    """Why a field is not a single citation that protects what it cites, of documents; None if it is"""
    from pangloss_models.field_definitions import (
        RelationFieldDefinition,
        RelationToCitation,
    )

    if not isinstance(definition, RelationFieldDefinition):
        return "is not a citation"
    if definition.wrapper is not None:
        return "is a list: a judgement is of one pair"
    if definition.optional:
        return "may be None: a judgement is of a pair, both there"
    from pangloss_models.citations import BASIS

    # (beside a citation, a cited basis: an installed app's way of citing what cannot itself be cited, which a
    # statement can; never the one option)
    options = [
        o
        for o in definition.type_options
        if getattr(o.annotated_type, "__name__", None) != BASIS
    ]
    if not options or not all(isinstance(o, RelationToCitation) for o in options):
        return "is not a citation"
    if not all(o.protect for o in options if isinstance(o, RelationToCitation)):
        return (
            "is a citation that does not protect what it cites: a judgement has to know when a statement it judges "
            "has changed"
        )
    return None


def check_judgement_classes() -> None:
    """(`ModelRegistry.after_finalise`) Every class below `EventJudgement` that is not abstract has the fields
    `statement` and `other`, each a single `Cites[...]` (one that protects what it cites). A `PanglossModelError`
    naming the class and what to write"""
    models = ModelRegistry._model_dict
    base = models.get(BASE)
    if not isinstance(base, type):
        return
    for name, model in sorted(models.items()):
        if (
            not name.isidentifier()
            or not isinstance(model, type)
            or model is base
            or not issubclass(model, base)
            or getattr(model._meta, "abstract", False)
        ):
            continue
        fields = model._meta.fields
        for field in CITING:
            definition = fields.get(field) if fields is not None else None
            why = (
                "is missing" if definition is None else _why_not(definition)
            )  # fmt: skip
            if why is None:
                continue
            raise PanglossModelError(
                f"{name}: an EventJudgement cites the two statements it judges, and its field {field!r} {why}. "
                f"Declare both on {name}, with your class of statements: "
                "`statement: Cites[Statement]` and `other: Cites[Statement]` (the prescription first, where one of "
                "the two is)"
            )


def _registered_once(hooks: list, check: Any) -> None:
    # (once, though the tests run this module again for a fresh registry)
    hooks[:] = [
        hook
        for hook in hooks
        if getattr(hook, "__qualname__", None) != check.__qualname__
        or getattr(hook, "__module__", None) != __name__
    ] + [check]


_registered_once(ModelRegistry.after_finalise, check_judgement_classes)
