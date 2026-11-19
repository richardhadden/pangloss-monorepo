"""`_criteria_meta`: whether an entity of a class may be described and not named.

    class Person(Entity):
        _criteria_meta = CriteriaMeta(allowed=True)

Every relation that takes the entity class then also takes a `MatchesCriteria` of it (`pangloss_criteria.models`),
as if the annotation said `Person | MatchesCriteria[Person]`: a relation to `Agent` (a `Person` or a `Group`, both
allowed) takes a `MatchesCriteria[Group | Person]`. A subclass has its parent's setting unless it sets its own: one
that says `allowed=False` is not described where a relation takes it alone, but a description of its parent class
still finds it (a search for a person finds a saint). One field refuses it with a marker:
`Annotated[Person, NoCriteria()]`.

A field whose annotation writes the description out (`Person | MatchesCriteria[Person]`) takes it whatever the
class says.

(implementation_docs/matches-criteria.md, "Stand-ins that are generic")
"""

import dataclasses

from pangloss_models import (
    Entity,
    ModelRegistry,
    PanglossModelError,
    hooks,
    register_meta_slot,
)
from pangloss_models.markers import FieldMarker

SLOT = "_criteria_meta"

# (the name of the class: `pangloss_criteria.models`, which a client of the API may not have imported yet)
MATCHES_CRITERIA = "MatchesCriteria"


@dataclasses.dataclass(frozen=True)
class CriteriaMeta:
    allowed: bool = False
    """Whether a relation that takes an entity of the class also takes a description of one"""


register_meta_slot(SLOT, CriteriaMeta)


class NoCriteria(FieldMarker):
    """On a relation: it does not take a `MatchesCriteria` in place of an entity, whatever the entity's class allows
    (`Annotated[Person, NoCriteria()]`)"""


def allows_criteria(model: type) -> bool:
    """Whether a relation that takes the entity class also takes a description in its place"""
    meta = getattr(model, SLOT, None)
    return isinstance(meta, CriteriaMeta) and meta.allowed and issubclass(model, Entity)


def check_matches_criteria_is_declared() -> None:
    """(before the models are initialised) A class that allows descriptions needs the `MatchesCriteria` model. On a
    server it is declared by `pangloss_criteria` being an installed app (which also gives its migration, its worker
    and its commands), and it is an error if it is not. A client of the API (the SDK) has only the models, and the
    project's say `CriteriaMeta` without importing `pangloss_criteria.models`: there it is imported here"""
    models = ModelRegistry._model_dict
    if MATCHES_CRITERIA in models:
        return
    allowing = sorted(name for name, model in models.items() if allows_criteria(model))
    if not allowing:
        return
    from pangloss_core import settings

    # (a server's settings are `BaseSettings`; a client's only `ClientSettings`)
    if isinstance(getattr(settings, "SETTINGS", None), settings.BaseSettings):
        raise PanglossModelError(
            f"{', '.join(allowing)}: CriteriaMeta(allowed=True) needs the MatchesCriteria model of "
            "pangloss_criteria: add 'pangloss_criteria' to INSTALLED_APPS (or import pangloss_criteria.models)"
        )
    import pangloss_criteria.models  # noqa: F401


# (a generic stand-in: the option is `MatchesCriteria[...]` of the relation's entity classes that allow it. What is
# given for it is checked by the class's own validator, which knows what its parameter stands for)
STAND_IN = hooks.StandIn(
    document=MATCHES_CRITERIA,
    stands_for=allows_criteria,
    refused_by=NoCriteria,
)


def install() -> None:
    if STAND_IN not in hooks.stand_ins:
        hooks.stand_ins.append(STAND_IN)
    if check_matches_criteria_is_declared not in ModelRegistry.before_finalise:
        ModelRegistry.before_finalise.append(check_matches_criteria_is_declared)


# (done as soon as a model can say it, whether or not the app is installed)
install()
