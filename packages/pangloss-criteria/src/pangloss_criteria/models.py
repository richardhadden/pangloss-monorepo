"""`MatchesCriteria[T]`: someone or something a source describes and does not name
(implementation_docs/matches-criteria.md, "The model").

    class Activity(Document):
        carried_out_by: list[Person | MatchesCriteria[Person]]

    Activity(label="A letter carried to Innsbruck", carried_out_by=[
        MatchesCriteria[Person](
            wording="N. N., secretarius Maximiliani",
            criteria=Person.Where(incoming_=[IncomingFrom(
                where=HoldsOffice.Where(office=secretary, employer=maximilian), field="holder")]),
        )])

It is a reified relation, part of the document that mentions it. What the user writes is the `criteria` (a pattern
of structured search) and the `wording`. Its `target`, the **candidates**, is computed: the worker
(`pangloss_criteria.worker`) links it to every entity the criteria find, and does so again whenever a write could
change the result. A save only marks the document as pending.

(An installed app's `models` module is imported as the server and the commands start.)
"""

import datetime
import hashlib
from typing import Annotated, Any

from pangloss_models import (
    Computed,
    DBField,
    PanglossSearchError,
    ReifiedRelation,
    classes_stood_for,
    create_validator,
    read_validator,
    update_validator,
)

# (a class that says `CriteriaMeta(allowed=True)` is offered this one: the hook is in place wherever it is declared)
from pangloss_criteria import meta as _meta  # noqa: E402, F401
from pangloss_models.search import CheckedCondition, CheckedPattern, conditions_of

from pangloss_criteria.analysis import analyse, shape_of
from pangloss_criteria.pattern import SearchPattern, check_stored, ids_named

try:
    # (what a rule of `pangloss-derived` does with a description, if that package is there: below)
    from pangloss_derived import DerivedMeta
except ImportError:  # pragma: no cover
    DerivedMeta = None

# The name of the class, as a label of its nodes and as the wrapper no criteria pass through
NAME = "MatchesCriteria"

# The wrappers the criteria are evaluated without (rule 1 of "What is searched": a path of the search never passes
# through a description. If it could, one description's result would depend on another's candidates)
EXCLUDED = (NAME,)


def classes_touched(root: type, checked: Any) -> list[str]:
    """The names of the classes a checked pattern touches: the class it is of, those of the patterns of its
    relations and of what refers to it, and the wrappers it asks to pass through"""
    names: dict[str, None] = {root.__name__: None}
    for condition in conditions_of(checked):
        if not isinstance(condition, CheckedCondition):
            continue
        value = condition.value
        if isinstance(value, CheckedPattern):
            names.setdefault(value.model.__name__, None)
        elif hasattr(value, "pattern") and isinstance(value.pattern, CheckedPattern):
            names.setdefault(value.pattern.model.__name__, None)
        for name in condition.through:
            names.setdefault(name, None)
    return list(names)


def interface_meta() -> dict:
    """How the interface shows one, if it is installed (a client of the API, with the SDK, does not have it): a card
    with the summary of the criteria and the candidates, and in a form a card whose pencil opens the criteria in a
    dialog (the criteria interface module)"""
    try:
        from pangloss_interface import InterfaceMeta
    except ImportError:
        return {}
    return {
        "_interface_meta": InterfaceMeta(
            view_card="pangloss_criteria:CriteriaCard",
            edit_card="pangloss_criteria:CriteriaEditor",
        )
    }


class MatchesCriteria[T](ReifiedRelation[T]):
    """Someone or something the source describes but does not name: whoever fits the criteria"""

    _meta = ReifiedRelation.Meta(label_index=True)  # the worker reads them by label
    locals().update(interface_meta())
    if DerivedMeta is not None:
        # A rule reads through a description, and says so: the fact is not plain (`qualify`: "MatchesCriteria" is in
        # the context of its justification, and a rule that derives a document reads through it only if it allows
        # it). The candidates are alternatives: one justification takes at most one of them (`exclusive`), or a
        # rule over two participants of an activity would relate every two candidates of its one "N. N."
        _derived_meta = DerivedMeta(derivation="qualify", exclusive=True)

    # --- what the user writes ---
    wording: str | None = None
    """What the source says ("N. N., Maximilian's secretary")"""
    criteria: SearchPattern | None = None
    """A pattern of structured search whose root is one of the classes T allows"""

    # --- what the worker writes ---
    target: Annotated[list[T], Computed()] = []
    """The candidates: the entities the criteria find (at most `CRITERIA_MAX_CANDIDATES`, the first by label)"""
    candidate_count: Annotated[int, Computed()] = 0
    """How many the criteria find, though at most so many are linked. As read: the reader's own count"""
    candidate_count_everyone: Annotated[int, Computed(), DBField] = 0
    """Of what a reader who is not logged in sees (kept beside the other; a read gives one, `candidate_count`)"""
    evaluated_when: Annotated[datetime.datetime | None, Computed()] = None
    broken: Annotated[str | None, Computed()] = None
    """Why it is no longer evaluated (its criteria no longer fit the models)"""

    # --- what the server works out from the pattern when it is saved, for the worker ---
    criteria_hash: Annotated[str | None, DBField] = None
    """The pattern as it is stored, hashed: the same for the same criteria"""
    depends_on: Annotated[list[str], DBField] = []
    """The class labels the pattern touches"""
    names: Annotated[list[str], DBField] = []
    """The ids of every entity the pattern names"""
    anchors: Annotated[list[str], DBField] = []
    """The ids of which a write must name one to bear on the result; none, if any write may (`analysis`)"""
    reach: Annotated[str | None, DBField] = None
    """`local` or `far`: whether a write can change a match only of an entity it names"""
    shape: Annotated[str | None, DBField] = None
    """The pattern with its ids and values taken out, hashed"""

    @create_validator
    @update_validator
    def check_the_criteria(self: Any):
        """The criteria are checked against the models as a search would be, and against what a stored pattern may
        hold; their type is one of the classes this description stands among. What the worker needs to know of
        them is worked out here"""
        if self.criteria is None:
            raise ValueError("criteria: a description needs the criteria it is of")
        try:
            checked = check_stored(
                self.criteria, classes_stood_for(self, "T"), EXCLUDED
            )
        except PanglossSearchError as error:
            raise ValueError(f"criteria: {error}") from None
        from pangloss_models.search import resolve_search_type

        self.criteria_hash = hashlib.sha1(self.criteria.text().encode()).hexdigest()
        self.names = ids_named(self.criteria)
        root = resolve_search_type(self.criteria.type)
        self.depends_on = classes_touched(root, checked)
        analysis = analyse(root, checked)
        self.reach = analysis.reach
        self.anchors = analysis.stored_anchors
        self.shape = shape_of(self.criteria)

    @read_validator
    def the_readers_own_count(cls, data: dict[str, Any]) -> dict[str, Any]:
        """A view gives one count: of what its reader sees"""
        if "candidate_count_everyone" not in data:
            return data
        # (imported here: a client of the API has the models, and so this module, and not `pangloss_users`)
        from pangloss_users import see_unpublished

        if not see_unpublished.get():
            return {**data, "candidate_count": data["candidate_count_everyone"]}
        return data
