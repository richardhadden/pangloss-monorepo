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

Where one document describes the same one in several places ("N. N. carried the letter, and N. N. was paid for it"),
the places share a mark, `same_one` (any UUID the client makes: it means something only within the document). One of
them holds the criteria (or several, the same criteria); the others have none, and take the candidates of the one
that does. Resolving one resolves them all. Two descriptions with equal criteria and no shared mark are two.

Criteria used in many documents are a **shared description**, `Description`: a head document of its own, with a
label ("Maximilian's secretary") and the criteria. A mention cites it (`description`), and may add conditions of its
own (`criteria`): it is evaluated by both (`pangloss_criteria.effective`). Editing the shared description is a change
to what is cited (`acknowledge_citations`), and changes the candidates of every mention that cites it.

(An installed app's `models` module is imported as the server and the commands start.)
"""

import datetime
import hashlib
from typing import Annotated, Any
from uuid import UUID

from pangloss_models import (
    Cites,
    Computed,
    DBField,
    Document,
    Entity,
    PanglossSearchError,
    PanglossWriteRefused,
    ReifiedRelation,
    before_create,
    before_update,
    classes_stood_for,
    create_validator,
    nodes_of,
    read_validator,
    update_validator,
    whole_write,
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

# The name of the class of a shared description
DESCRIPTION = "Description"

# The wrappers the criteria are evaluated without (rule 1 of "What is searched": a path of the search never passes
# through a description. If it could, one description's result would depend on another's candidates)
EXCLUDED = (NAME,)


def classes_touched(root: type, checked: Any) -> list[str]:
    """The names of the classes a checked pattern touches: the class it is of, those of the patterns of its
    relations and of what refers to it, and the wrappers it asks to pass through (by `through`, or as an item of
    `via`: an edge model is no node, and is not one of them)"""
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
        for item in condition.via:
            if item.kind == "wrapper":
                names.setdefault(item.model.__name__, None)
    return list(names)


# What is worked out from the criteria when a description is saved, for the worker (`worked_out`)
WORKED_OUT = ("criteria_hash", "depends_on", "names", "anchors", "reach", "shape")


def worked_out(criteria: SearchPattern | None, allowed: Any = None) -> dict[str, Any]:
    """What the worker needs to know of criteria, as a description stores it (`WORKED_OUT`): worked out on save
    (`check_the_criteria`), and again after a migration that changes the models they are read by
    (`pangloss_criteria.migrating`). Checked first, as a stored pattern is (`allowed`: the classes they may be of);
    raises `PanglossSearchError`. Of no criteria (a place of a mark that another place holds them for), nothing"""
    if criteria is None:
        return {
            "criteria_hash": None,
            "depends_on": [],
            "names": [],
            "anchors": [],
            "reach": None,
            "shape": None,
        }
    checked = check_stored(criteria, allowed, EXCLUDED)
    from pangloss_models.search import resolve_search_type

    root = resolve_search_type(criteria.type)
    analysis = analyse(root, checked)
    return {
        "criteria_hash": hashlib.sha1(criteria.text().encode()).hexdigest(),
        "depends_on": classes_touched(root, checked),
        "names": ids_named(criteria),
        "anchors": analysis.stored_anchors,
        "reach": analysis.reach,
        "shape": shape_of(criteria),
    }


def holds(place: Any) -> bool:
    """Whether a place of a mark (`same_one`) holds criteria: its own, or a shared description it cites"""
    return place.criteria is not None or place.description is not None


def what_is_held(place: Any) -> tuple[str | None, str | None]:
    """What a place holds, to compare with the other places of its mark: the shared description it cites, and its
    own criteria as they are stored"""
    cited = getattr(place.description, "target_id", None)
    return (
        None if cited is None else str(cited),
        None if place.criteria is None else place.criteria.text(),
    )


def interface_meta(**options: Any) -> dict:
    """How the interface shows one, if it is installed (a client of the API, with the SDK, does not have it): by
    default (a description) a card with the summary of the criteria and the candidates, and in a form a card whose
    pencil opens the criteria in a dialog (the criteria interface module); `options`, the `InterfaceMeta` of another
    class of the module (a shared description's page)"""
    try:
        from pangloss_interface import InterfaceMeta
    except ImportError:
        return {}
    return {
        "_interface_meta": InterfaceMeta(
            **(
                options
                or {
                    "view_card": "pangloss_criteria:CriteriaCard",
                    "edit_card": "pangloss_criteria:CriteriaEditor",
                }
            )
        )
    }


class Description(Document):
    """Criteria shared by mentions in many documents ("Maximilian's secretary"). It does not say that they are one:
    each mention that cites it has the candidates its criteria find"""

    # (always published: not reviewed, or a published mention could cite what a reader may not see. Not in "search
    # everything": it is a description of someone, not something a source says)
    _meta = Document.Meta(global_search=False)
    # (its page, with its mentions and the criteria shown as the summary; in its form the criteria are edited there)
    locals().update(
        interface_meta(
            item_page="pangloss_criteria:DescriptionPage", hide_on_forms=("criteria",)
        )
    )

    criteria: SearchPattern
    """A pattern of structured search whose root is a class of entity"""

    @create_validator
    @update_validator
    def check_the_shared_criteria(self: Any):
        """The criteria are checked against the models as a search would be, and against what a stored pattern may
        hold; their type is a class of entity. (Whether the place of each mention that cites it takes that class is
        checked when the mention is saved, and when this is: `pangloss_criteria.effective`)"""
        try:
            check_stored(self.criteria, (Entity,), EXCLUDED)
        except PanglossSearchError as error:
            raise ValueError(f"criteria: {error}") from None


class CitesShared[Target](Cites[Target]):
    """A citation of a shared description: of the description itself, never of something chosen that stands for one
    (no cited basis, `Cites.bases`). So the field, and the migration that made it, are the same in a project that has
    derived documents and in one that has none"""

    bases = False


class MatchesCriteria[T](ReifiedRelation[T]):
    """Someone or something the source describes but does not name: whoever fits the criteria"""

    # (`label_index`: the worker reads them by label. `label_template`: in the label of a document that holds one, it
    # is named by what the source says, "Meeting by N. N., Maximilian's secretary"; a wrapper with no template is
    # named by what it holds, and a description holds its candidates)
    _meta = ReifiedRelation.Meta(label_index=True, label_template="{wording}")
    locals().update(interface_meta())
    if DerivedMeta is not None:
        # A rule reads through a description, and says so: the fact is not plain (`qualify`: "MatchesCriteria" is in
        # the context of its justification, and a rule that derives a document reads through it only if it allows
        # it). The candidates are alternatives: one justification takes at most one of them (`exclusive`), or a
        # rule over two participants of an activity would relate every two candidates of its one "N. N."
        # The places of one description (`same_one`) are one alternative together: or one justification could
        # take Waldauf where N. N. carried the letter and Serntein where he was paid, and relate the two
        _derived_meta = DerivedMeta(derivation="qualify", exclusive="same_one")

    # --- what the user writes ---
    wording: str | None = None
    """What the source says ("N. N., Maximilian's secretary")"""
    description: CitesShared[Description] | None = None
    """A shared description it cites: its criteria are those, and its own (`criteria`) as well"""
    criteria: SearchPattern | None = None
    """A pattern of structured search whose root is one of the classes T allows. With a shared description, the
    conditions it adds to that one's (of its class, or a class below it)"""
    same_one: UUID | None = None
    """A mark shared by the places of this document that describe the same one. One of them holds the criteria"""

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
    broken_since: Annotated[str | None, Computed()] = None
    """`app.name` of the migration that made the criteria wrong; None if the worker found it"""

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
    stands_for: Annotated[list[str], DBField] = []
    """The names of the classes its place takes (what T stands for): what its criteria may be of, kept so that a
    change of the shared description it cites can be checked against them"""

    @create_validator
    @update_validator
    def check_the_criteria(self: Any):
        """The criteria are checked against the models as a search would be, and against what a stored pattern may
        hold; their type is one of the classes this description stands among. What the worker needs to know of
        them is worked out here: of a mention that cites a shared description, before the save, by what that one is
        now (`with_the_shared_criteria`)"""
        allowed = classes_stood_for(self, "T")
        self.stands_for = sorted(
            cls.__name__ for cls in allowed or () if isinstance(cls, type)
        )
        if self.criteria is None and self.description is None:
            if self.same_one is None:
                raise ValueError(
                    "criteria: a description needs the criteria it is of, or a shared description it cites"
                    " (`description`), or `same_one`, the mark of another place of this document that holds them"
                )
            # (another place holds the criteria: nothing of them here. Whether one does: `check_the_places`)
            found = worked_out(None)
        elif self.criteria is None:
            # (of the shared description alone: worked out before the save)
            found = worked_out(None)
        else:
            try:
                # (with a shared description: its own conditions alone, of their own class; with the shared ones,
                # before the save)
                found = worked_out(self.criteria, allowed)
            except PanglossSearchError as error:
                raise ValueError(f"criteria: {error}") from None
            if self.description is not None:
                found = worked_out(None)
        for name, value in found.items():
            setattr(self, name, value)

    @before_create
    @before_update
    async def with_the_shared_criteria(self: Any, previous: Any = None):
        """Of a mention that cites a shared description: the shared criteria and its own together checked, against
        what its place takes too, and what the worker needs to know of them worked out (`effective.fill`), to be
        written with it"""
        if self.description is None:
            return
        # (only the server saves: a client of the API has no database to read the description from)
        from pangloss_criteria import effective

        head = whole_write()
        await effective.fill(
            self, classes_stood_for(self, "T"), getattr(head, "id", None)
        )

    @before_create
    @before_update
    async def check_the_places(self: Any, previous: Any = None):
        """Of the places of this document with one mark (`same_one`), at least one holds the criteria (its own, or a
        shared description it cites); those that do hold the same (the same description cited, and the same criteria
        of their own: a place may repeat them, as a copy of a statement in its own document is still of the same
        one); and what they find is something every place takes. Checked of the whole document as it will be
        (`whole_write`), at each place: the refusal names the place that is wrong"""
        if self.same_one is None:
            return
        places = [
            node
            for _, node in nodes_of(whole_write())
            if getattr(node, "same_one", None) == self.same_one
            and issubclass(getattr(type(node), "_owner", object), MatchesCriteria)
        ]
        holding = [place for place in places if holds(place)]
        if not holding:
            raise PanglossWriteRefused(
                f"No place of this document with the mark {self.same_one} holds criteria: this one says it is the"
                " same one as another, and none says who",
                field="same_one",
            )
        if holds(self):
            if any(what_is_held(place) != what_is_held(self) for place in holding):
                raise PanglossWriteRefused(
                    f"The places with the mark {self.same_one} hold different criteria: they are the same one, so"
                    " one of them holds the criteria (or all the same), and the others none",
                    field="criteria" if self.criteria is not None else "description",
                )
            return
        allowed = classes_stood_for(self, "T")
        holder = holding[0]
        if allowed is not None:
            # (the class of what the holder's criteria find: of its own, worked out by now for one that cites)
            from pangloss_models.search import resolve_search_type

            if holder.criteria is not None:
                type_name = holder.criteria.type
            else:
                from pangloss_criteria import effective

                cited = str(holder.description.target_id)
                found = (await effective.read_shared([cited])).get(cited)
                if found is None or found.criteria is None:
                    # (the citation is checked when it is written: the write refuses it)
                    return
                type_name = SearchPattern(found.criteria).type
            root = resolve_search_type(type_name)
            if not any(issubclass(root, cls) for cls in allowed):
                raise PanglossWriteRefused(
                    f"The criteria of the mark {self.same_one} are of {root.__name__}, which is not taken here"
                    f" ({', '.join(sorted(cls.__name__ for cls in allowed))})",
                    field="same_one",
                )

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
