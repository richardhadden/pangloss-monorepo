"""The settings of `pangloss-reconcile`, read from the project's settings object with their defaults, and checked at
`initialise()` when the app is installed (implementation_docs/reconcile.md):

- `RECONCILE_PROFILE` (None): the profile of `pangloss-vectors` candidates are found and scored by. None: the
  profile that weighs the most parts that can say what an unknown would be (`Part.unknown`). Refused if it names
  no profile, or one that weighs no such part, or if none does, or if without it several weigh as many (with the
  graph part installed `default`, of the class and the graph, ties with a profile of the name and the graph).
- `RECONCILE_FETCH` (50): how many candidates each part is asked for (`nearest(k=...)`). A whole number of 1 or
  more.
- `RECONCILE_WEIGHTS` (`{}`): the weight of each part in a candidate's score, by part; a part not named has the
  weight the profile gives it. Refused: a name that is no part, a weight that is not a number of 0 or more.
"""

from collections.abc import Mapping
from typing import Any

from pangloss_models import ModelRegistry
from pangloss_models.exceptions import PanglossInitialisationError

APP = "pangloss_reconcile"

DEFAULT_FETCH = 50

__all__ = ["check", "fetch", "profile", "weights"]


def _settings(settings: Any) -> Any:
    if settings is not None:
        return settings
    from pangloss_core import settings as core_settings

    return core_settings.__dict__.get("SETTINGS")


def _unknowing() -> list[str]:
    """The names of the registered parts that can say what an unknown would be"""
    from pangloss_vectors.parts import parts

    return [
        name
        for name, made in parts().items()
        if callable(getattr(made, "unknown", None))
    ]


def profile(settings: Any = None) -> str:
    """`RECONCILE_PROFILE`, or the profile chosen without it: the name of a profile that weighs a part that can say
    what an unknown would be. Refused (`PanglossInitialisationError`) with what to set otherwise"""
    from pangloss_vectors.parts import profiles

    settings = _settings(settings)
    known = profiles(settings)
    able = _unknowing()
    named = getattr(settings, "RECONCILE_PROFILE", None)
    if named is not None:
        if not isinstance(named, str) or named not in known:
            raise PanglossInitialisationError(
                f"RECONCILE_PROFILE names {named!r}, which is not a profile: the profiles are "
                f"{', '.join(sorted(known))} (VECTORS_PROFILES)"
            )
        if not any(known[named].get(name, 0) > 0 for name in able):
            raise PanglossInitialisationError(
                f"RECONCILE_PROFILE names {named!r}, which weighs no part that can say what an unknown would be "
                f"({', '.join(able) or 'none is registered'}): name a profile that weighs one of them, or give "
                f"{named!r} a weight for one in VECTORS_PROFILES"
            )
        return named
    weighing = {
        name: sum(1 for part in able if weights.get(part, 0) > 0)
        for name, weights in known.items()
    }
    best = max(weighing.values(), default=0)
    if best == 0:
        raise PanglossInitialisationError(
            "No profile weighs a part that can say what an unknown would be "
            f"({', '.join(able) or 'none is registered: install pangloss_fastrp or pangloss_names'}): add one to "
            'VECTORS_PROFILES ({"who": {"name": 1, "graph": 0.25}}) and set RECONCILE_PROFILE to its name'
        )
    tied = sorted(name for name, count in weighing.items() if count == best)
    if len(tied) > 1:
        # (which of them is for reconciling is the project's to say: `default`, of the class and the graph, weighs
        # as many such parts as one of the name and the graph, and finds nobody by a name)
        raise PanglossInitialisationError(
            f"The profiles {', '.join(tied)} each weigh {best} of the parts that can say what an unknown would be "
            f"({', '.join(able)}), so which one candidates are found by has to be said: set RECONCILE_PROFILE to "
            "the name of one (one that weighs the name and the graph, for people)"
        )
    return tied[0]


def fetch(settings: Any = None) -> int:
    """`RECONCILE_FETCH`: how many candidates each part is asked for (50)"""
    value = getattr(_settings(settings), "RECONCILE_FETCH", DEFAULT_FETCH)
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise PanglossInitialisationError(
            f"RECONCILE_FETCH is a whole number of 1 or more (how many candidates each part is asked for), not "
            f"{value!r}"
        )
    return value


def weights(settings: Any = None) -> dict[str, float]:
    """The weight of each part in a candidate's score: the profile's (`profile()`), with `RECONCILE_WEIGHTS` over
    them; those above 0, by part"""
    from pangloss_vectors.parts import parts, profiles

    settings = _settings(settings)
    given = getattr(settings, "RECONCILE_WEIGHTS", None) or {}
    if not isinstance(given, Mapping):
        raise PanglossInitialisationError(
            f"RECONCILE_WEIGHTS is a weight for each part ({{'name': 1, 'graph': 0.5}}), not {given!r}"
        )
    known = parts()
    unknown = sorted(str(name) for name in given if name not in known)
    if unknown:
        raise PanglossInitialisationError(
            f"RECONCILE_WEIGHTS names {', '.join(repr(u) for u in unknown)}, which is not a part: the parts are "
            f"{', '.join(known) or 'none'}"
        )
    for name, weight in given.items():
        if (
            isinstance(weight, bool)
            or not isinstance(weight, (int, float))
            or weight < 0
        ):
            raise PanglossInitialisationError(
                f"RECONCILE_WEIGHTS[{name!r}] is a weight of 0 or more, not {weight!r}"
            )
    found = {**profiles(settings)[profile(settings)], **given}
    return {name: float(weight) for name, weight in sorted(found.items()) if weight > 0}


def check() -> None:
    """(`ModelRegistry.after_finalise`) a project with this app installed has its settings checked at `initialise()`,
    each installed app imported first so that every part is registered"""
    settings = _settings(None)
    if APP not in list(getattr(settings, "INSTALLED_APPS", None) or []):
        return
    from pangloss_vectors import import_installed_apps

    import_installed_apps(settings)
    fetch(settings)
    weights(settings)


def install() -> None:
    """(`pangloss_reconcile._install`)"""
    if check not in ModelRegistry.after_finalise:
        ModelRegistry.after_finalise.append(check)
