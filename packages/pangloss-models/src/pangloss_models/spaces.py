"""The walk: what a node's path says of it (implementation_docs/semantic-spaces.md, "The walk").

`signature(path)` reads a node's stored path (`pangloss_models.context`: the nodes it is nested in, outermost
first) and what each space class on it says of its contents (`SemanticSpace.Meta`), and gives a `Signature`:
whether the node is asserted, denied or neither; where neither, which way it leans and at what degree; whether it
is prescribed, and by which statement; and the modality it is under. It reads no database, and nothing it gives is
stored: a change of a space's meta changes what the walk gives and nothing else.

In two steps:

1. **Normalising** (`normalise`). Each run of spaces next to each other is rewritten so that a "not" stands as far in
   as it can go: two cancel; one passes a modality by turning it into its dual of the same flavour (not possible =
   necessarily not; not necessary = possibly not); a modality `of_not` is the modality of a "not". A "not" passes
   nothing else: no space that is not a modality, and no statement (`Not[Permission(content=Permitted[p])]` says
   that no permission was given, not that p was forbidden).

2. **Walking**, from the outside, with a sign that starts as asserted. A space that asserts its contents keeps it and
   a denial turns it. Once it is denied, anything further in (a space or a statement) leaves the node neither, leaning
   neither way: that there was no service says nothing of its parts. At the first space that neither asserts nor
   denies, the node is neither, and the walk goes on only for its lean: for, until a denial turns it against, and
   anything further in than that leaves it leaning neither way.

A space says something of its `contents` only. What it holds in a field of its own (who reported it, when) is held
as by any statement: `Reported(reported_at=d, contents=[p])` leaves p uncommitted and says nothing less of d.

The degree is no part of the sign. It is given beside it, for a node that leans for or against: the degree entered
on the innermost space that leaves its contents neither (in its entry of the path), else that class's default. A
judgement of the statement made elsewhere is the caller's to weigh.

The cases are data, `tests/space_cases.json`, which the interface's port of the walk passes too.
"""

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any, Literal, NotRequired, TypedDict

from pangloss_models.context import SPACE, PathEntry

FOR, AGAINST, NEITHER = "for", "against", "neither"
NECESSITY, POSSIBILITY = "necessity", "possibility"
PRESCRIBES = "prescribes"
# The field through which a space holds what it says something of
CONTENTS = "contents"


class SpaceFacts(TypedDict):
    """What a space class says of its contents, as the export gives it (`export.export_space`)"""

    veridical: int
    fit: str
    logical: dict[str, Any] | None
    """None, `{"not": True}`, or `{"force", "flavour", "ofNot"}`"""
    unary: NotRequired[bool]
    degree: str | None
    abstract: NotRequired[bool]


class UnknownSpaceError(LookupError):
    """A path names a space class that is not among the models"""


@dataclass(frozen=True)
class Signature:
    """What a node's path says of it"""

    veridical: Literal[1, 0, -1]
    """`1`: asserted; `-1`: denied; `0`: neither"""
    lean: str | None
    """Where `veridical` is `0`: `"for"`, `"against"` or `"neither"`. None where it is not"""
    degree: str | None
    """Where it leans for or against: how far, one of `DEGREE_STEPS` (entered on the space, else its class's
    default), or None where neither says"""
    fit: str
    """`"prescribes"` where a space of the path prescribes its contents, else `"describes"`"""
    prescribed_by: str | None
    """The id of the node that holds the innermost space that prescribes (the order, of what is ordered)"""
    force: str | None
    """Of the innermost modality of the normalised path: `"necessity"` or `"possibility"`"""
    flavour: str | None

    def as_json(self) -> dict[str, Any]:
        return {
            "veridical": self.veridical,
            "lean": self.lean,
            "degree": self.degree,
            "fit": self.fit,
            "prescribedBy": self.prescribed_by,
            "force": self.force,
            "flavour": self.flavour,
        }


# --- the steps of a normalised path ----------------------------------------------------------------------

NOT, MODAL, OTHER, STATEMENT = "not", "modal", "other", "statement"


@dataclass(frozen=True)
class Step:
    """One step of a normalised path, outermost first"""

    kind: str
    """`"not"`; `"modal"`; `"other"` (a space that is neither); `"statement"` (any node that is not a space)"""
    veridical: int = 1
    """What the step says of what is inside it. A "not" is `-1`; a statement asserts what it holds"""
    force: str | None = None
    flavour: str | None = None
    degree: str | None = None
    """Of a space that leaves its contents neither: the degree entered on it, else its class's default"""
    type: str | None = None
    """The class of the node, where the step is one of the path as written (a dual, and the "not" of an `of_not`,
    have none)"""


def registered_spaces() -> dict[str, SpaceFacts]:
    """What each space class among the models says of its contents. A caller that asks for many signatures makes it
    once and gives it to each"""
    from pangloss_models.export import export_space
    from pangloss_models.model_bases.semantic_space import SemanticSpaceMeta
    from pangloss_models.model_registry import ModelRegistry

    spaces: dict[str, SpaceFacts] = {}
    for name, model in ModelRegistry.all_models().items():
        meta = model._meta
        # (`Epistemic[T]`, made where a class is declared below `Epistemic`, is no class of the project's: it has
        # the logic of `Epistemic` and not its `abstract`, and would be counted as a necessity that commits to
        # nothing. The export leaves these out too, and the interface's port reads the export)
        if (getattr(model, "__pydantic_generic_metadata__", None) or {}).get("origin"):
            continue
        if isinstance(meta, SemanticSpaceMeta):
            said = export_space(meta)
            spaces[name] = SpaceFacts(
                veridical=said["veridical"],
                fit=said["fit"],
                logical=said["logical"],
                unary=said["unary"],
                degree=said["degree"],
                abstract=meta.abstract,
            )
    return spaces


def _facts(entry: PathEntry, spaces: Mapping[str, SpaceFacts]) -> SpaceFacts:
    try:
        return spaces[entry["type"]]
    except KeyError:
        raise UnknownSpaceError(
            f"The path names a semantic space {entry['type']!r} that is not among the models"
        ) from None


def _commits(force: str, flavour: str, spaces: Mapping[str, SpaceFacts]) -> bool:
    """Whether the project's modality of this force and flavour commits the source to what it holds, for a dual
    that no entry of the path wrote. A possibility never does. A necessity does where the project has declared
    one of that flavour and every one it has declared commits (`veridical=1`, or `-1` on one `of_not`): what is
    known not to be possible is denied only if what is known to be necessary is asserted."""
    if force == POSSIBILITY:
        return False
    found = [
        _modal_commits(facts)
        for facts in spaces.values()
        if not facts.get("abstract")
        and _is_modal(facts)
        and facts["logical"]["force"] == force  # ty: ignore[not-subscriptable]
        and facts["logical"]["flavour"] == flavour  # ty: ignore[not-subscriptable]
    ]
    return bool(found) and all(found)


def _is_modal(facts: SpaceFacts) -> bool:
    return bool(facts["logical"]) and "force" in facts["logical"]


def _modal_commits(facts: SpaceFacts) -> bool:
    of_not = facts["logical"]["ofNot"]  # ty: ignore[not-subscriptable]
    return facts["veridical"] == (-1 if of_not else 1)


def _dual(force: str) -> str:
    return POSSIBILITY if force == NECESSITY else NECESSITY


def holds_as_space(entry: PathEntry) -> bool:
    """Whether an entry of a path is a space holding its contents. What a space holds in a field of its own (who
    reported it, when) is not what it says anything of: there the space is a statement like any other node"""
    return entry["kind"] == SPACE and entry["field"] == CONTENTS


def normalise(
    path: Iterable[PathEntry], spaces: Mapping[str, SpaceFacts] | None = None
) -> list[Step]:
    """The steps of a path, outermost first, each run of spaces next to each other rewritten so that a "not" stands
    as far in as it can go (the module's docstring). Never what is stored: a reading of it."""
    if spaces is None:
        spaces = registered_spaces()
    steps: list[Step] = []
    # A "not" of the run in hand that has not been put down yet
    pending = False

    def put_down() -> None:
        nonlocal pending
        if pending:
            steps.append(Step(NOT, veridical=-1))
            pending = False

    for entry in path:
        if not holds_as_space(entry):
            put_down()
            steps.append(Step(STATEMENT, type=entry["type"]))
            continue
        facts = _facts(entry, spaces)
        logical = facts["logical"]
        degree = entry.get("degree") or facts["degree"]
        if logical and logical.get("not"):
            pending = not pending
        elif logical:
            force, flavour = logical["force"], logical["flavour"]
            if pending:
                # (not N = P not; not P = N not: within the one flavour, so the dual is the project's own of it)
                force = _dual(force)
                commits = _commits(force, flavour, spaces)
            else:
                commits = _modal_commits(facts)
            steps.append(
                Step(
                    MODAL,
                    veridical=1 if commits else 0,
                    force=force,
                    flavour=flavour,
                    degree=None if commits else degree,
                    type=None if pending else entry["type"],
                )
            )
            if logical["ofNot"]:
                pending = not pending
        else:
            put_down()
            veridical = facts["veridical"]
            steps.append(
                Step(
                    OTHER,
                    veridical=veridical,
                    degree=degree if veridical == 0 else None,
                    type=entry["type"],
                )
            )
    put_down()
    return steps


def signature(
    path: Iterable[PathEntry], spaces: Mapping[str, SpaceFacts] | None = None
) -> Signature:
    """What a node's path says of it. `path` is the node's stored path (`meta.path`); `spaces`, what each space
    class says of its contents, is read from the models where it is not given (`registered_spaces`)."""
    path = list(path)
    if spaces is None:
        spaces = registered_spaces()

    veridical, lean, degree = 1, None, None
    force = flavour = None
    for step in normalise(path, spaces):
        if step.kind == MODAL:
            force, flavour = step.force, step.flavour
        if veridical == -1 or lean == AGAINST:
            # (that something is not so says nothing of what it holds)
            veridical, lean = 0, NEITHER
        elif lean == NEITHER or step.kind == STATEMENT:
            pass
        elif step.veridical == -1:
            if lean == FOR:
                lean = AGAINST
            else:
                veridical = -1
        elif step.veridical == 0:
            veridical, lean, degree = 0, FOR, step.degree
    if lean not in (FOR, AGAINST):
        degree = None

    fit, prescribed_by = "describes", None
    holder = None
    for entry in path:
        if not holds_as_space(entry):
            holder = entry["id"]
        elif _facts(entry, spaces)["fit"] == PRESCRIBES:
            fit, prescribed_by = PRESCRIBES, holder

    return Signature(
        veridical=veridical,
        lean=lean,
        degree=degree,
        fit=fit,
        prescribed_by=prescribed_by,
        force=force,
        flavour=flavour,
    )
