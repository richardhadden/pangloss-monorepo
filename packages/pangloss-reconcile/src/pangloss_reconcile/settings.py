"""The settings of `pangloss-reconcile`, read from the project's settings object with their defaults, and checked at
`initialise()` when the app is installed (implementation_docs/reconcile.md):

- `RECONCILE_PROFILE` (None): the profile of `pangloss-vectors` candidates are found and scored by. None: the
  profile that weighs the most parts that can say what an unknown would be (`Part.unknown`). Refused if it names
  no profile, or one that weighs no such part, or if none does, or if without it several weigh as many (with the
  graph part installed `default`, of the class and the graph, ties with a profile of the name and the graph).
- `RECONCILE_FETCH` (50): how many candidates each part is asked for (`nearest(k=...)`). A whole number from 1 to
  1,000.
- `RECONCILE_MOST_UNKNOWNS` (20): the most unknowns a plan may have: one with more is refused before any part is
  asked (`TooManyUnknowns`, a 422 over the API). A whole number of 1 or more.
- `RECONCILE_REASONS` (5): the most entities a candidate is said to share with the payload (`shared`, `reasons.py`);
  0 asks nothing. A whole number of 0 or more.
- `RECONCILE_WEIGHTS` (`{}`): the weight of each part in a candidate's score, by part; a part not named has the
  weight the profile gives it. `shared` may be named beside the parts (the entities of the document a candidate is
  named with elsewhere, `score.py`): 1.5 unless given, 0 for phase 10's score. Refused: a name that is no part and
  not `shared`, a weight that is not a number of 0 or more, and weights that leave no part the profile weighs above 0
  (nothing would be found: `shared` alone is not enough).
- `RECONCILE_LEAST_SCORE` (0.15): the least score of a candidate given by either route; those under it are left out
  (after ranking, before the cut to `limit`). A number from 0 to 1.
- `RECONCILE_KEEP_DECISIONS` (True): whether the stored route keeps what it offered, and a reconciliation made of it
  is kept as an example (`decisions.py`). False: nothing is written, as before step 11.4. True or False.
- `RECONCILE_SHOWN_FOR` (30): in minutes, how long what was offered is an example of a decision made of it: a
  reconciliation later than that makes none, and the sweep removes what is older. A number above 0.
- `RECONCILE_LEARN_FROM` (100): the fewest decisions a fit (`pangloss reconcile learn`, `fits.py`) is made of for it
  to be put in use. A whole number of 1 or more.
- `RECONCILE_LEARN_FROM_SUGGESTIONS` (True): whether `learn` learns from the examples a person's confirmation of one
  of the worker's suggestions made (`via: "suggestion"`, step 10.5f), beside those of the dialog; they count towards
  `RECONCILE_LEARN_FROM` when they are in, and are counted apart either way. True or False.
- `RECONCILE_NEW_ABOVE` (0.5): the stored route says an unknown is probably none of those offered (`probablyNew`)
  when the fit in use gives a likelihood of that above it (`new`, step 11.6). A number from 0 to 1.

What to suggest for an unknown (`suggest.decide_for`, step 10.5c; the worker that writes it is to come, 10.5d), from
its candidates as the dialog is answered (the first `candidates.DISPLAYED`):

- `RECONCILE_SUGGEST_ABOVE` (0.6): the least score of the best candidate for a suggestion to be made. A number from
  0 to 1.
- `RECONCILE_SUGGEST_MOST` (3): the most alternatives a suggestion has. A whole number from 1 to 10 (no more than
  `DISPLAYED` are ever offered).
- `RECONCILE_SUGGEST_WITHIN` (0.7): an alternative scores at least this share of the best one's score (0 keeps
  every one up to the most, 1 only those that score as the best does). A number from 0 to 1.

The worker that writes suggestions (`suggesting.py`, step 10.5d):

- `RECONCILE_SUGGEST_ON_SAVE` (False): whether a save of a document that may hold a stand-in leaves it for the worker
  when the write does not say (`suggest=true|false`, an instruction of the write, says it either way). True or False.
- `RECONCILE_SUGGEST_AS` (`"IdentificationByToolchainFromText"`): the name of the class the worker writes in a
  stand-in's place: a model with the fields it fills (`text`, `uris`, `identified_by`, `toolchain_version`,
  `target`). Text, always; that it is such a model is checked only when `RECONCILE_SUGGEST_ON_SAVE` is True, or when
  the worker runs (a project without `pangloss-library`, and the setting off, is not refused).
- `RECONCILE_TOOLCHAIN` (`"pangloss-reconcile"`): the username the worker writes as, a user of kind `toolchain`
  (made when it is not there). A username.
- `RECONCILE_WORKER_IN_SERVER` (True): whether the server runs the worker as a background task; False to run it in a
  process of its own (`pangloss reconcile worker`). True or False.

A project's judge in the worker (`judging.py`, step 10.5c'):

- `RECONCILE_SUGGEST_WITH` (None): `"package.module:function"`, a function of the project's that the worker asks of
  each stand-in after it has decided and before it writes, and whose answer may replace the decision. Checked at
  `initialise()` when set: the form, that the module imports (its own error said), that the name is there and can be
  called. None: no judge, and nothing of one is made or imported.
- `RECONCILE_SUGGEST_TIMEOUT` (60): in seconds, how long the judge is given for one stand-in; past it the mention is
  left as it is. A number above 0.
"""

import importlib
import math
import re
from collections.abc import Mapping
from typing import Any

from pangloss_models import ModelRegistry
from pangloss_models.exceptions import PanglossInitialisationError

from pangloss_reconcile.score import SHARED

APP = "pangloss_reconcile"

DEFAULT_FETCH = 50
MOST_FETCH = 1000
DEFAULT_MOST_UNKNOWNS = 20
DEFAULT_REASONS = 5
DEFAULT_SHARED = 1.5
DEFAULT_LEAST_SCORE = 0.15
DEFAULT_KEEP_DECISIONS = True
DEFAULT_SHOWN_FOR = 30
DEFAULT_LEARN_FROM = 100
DEFAULT_LEARN_FROM_SUGGESTIONS = True
DEFAULT_NEW_ABOVE = 0.5
DEFAULT_SUGGEST_ABOVE = 0.6
DEFAULT_SUGGEST_MOST = 3
MOST_SUGGEST_MOST = 10
DEFAULT_SUGGEST_WITHIN = 0.7
DEFAULT_SUGGEST_ON_SAVE = False
DEFAULT_SUGGEST_AS = "IdentificationByToolchainFromText"
DEFAULT_TOOLCHAIN = "pangloss-reconcile"
DEFAULT_WORKER_IN_SERVER = True
DEFAULT_SUGGEST_TIMEOUT = 60

# What `RECONCILE_SUGGEST_WITH` looks like: a module's dotted name, a colon, a function's name
JUDGE_FORM = re.compile(
    r"^[A-Za-z_][A-Za-z0-9_]*(\.[A-Za-z_][A-Za-z0-9_]*)*:[A-Za-z_][A-Za-z0-9_]*$"
)

# The fields of `RECONCILE_SUGGEST_AS` the worker fills
SUGGESTION_FIELDS = ("text", "uris", "identified_by", "toolchain_version", "target")

__all__ = [
    "check",
    "check_suggest_as",
    "fetch",
    "keep_decisions",
    "learn_from",
    "learn_from_suggestions",
    "least_score",
    "most_unknowns",
    "new_above",
    "profile",
    "reasons",
    "shown_for",
    "suggest_above",
    "suggest_as",
    "suggest_most",
    "suggest_on_save",
    "suggest_timeout",
    "suggest_with",
    "suggest_within",
    "judge",
    "toolchain",
    "weights",
    "worker_in_server",
]


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


def _whole(name: str, value: Any, low: int, high: int | None, what: str) -> int:
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or value < low
        or (high is not None and value > high)
    ):
        bounds = f"from {low} to {high:,}" if high is not None else f"of {low} or more"
        raise PanglossInitialisationError(
            f"{name} is a whole number {bounds} ({what}), not {value!r}"
        )
    return value


def fetch(settings: Any = None) -> int:
    """`RECONCILE_FETCH`: how many candidates each part is asked for (50, at most 1,000)"""
    value = getattr(_settings(settings), "RECONCILE_FETCH", DEFAULT_FETCH)
    return _whole(
        "RECONCILE_FETCH",
        value,
        1,
        MOST_FETCH,
        "how many candidates each part is asked for",
    )


def most_unknowns(settings: Any = None) -> int:
    """`RECONCILE_MOST_UNKNOWNS`: the most unknowns a plan may have (20)"""
    value = getattr(
        _settings(settings), "RECONCILE_MOST_UNKNOWNS", DEFAULT_MOST_UNKNOWNS
    )
    return _whole(
        "RECONCILE_MOST_UNKNOWNS",
        value,
        1,
        None,
        "the most unknowns a document asked about may have",
    )


def reasons(settings: Any = None) -> int:
    """`RECONCILE_REASONS`: the most entities a candidate is said to share with the payload (5; 0: none asked)"""
    value = getattr(_settings(settings), "RECONCILE_REASONS", DEFAULT_REASONS)
    return _whole(
        "RECONCILE_REASONS",
        value,
        0,
        None,
        "the most entities a candidate is said to share with what is asked about",
    )


def least_score(settings: Any = None) -> float:
    """`RECONCILE_LEAST_SCORE`: the least score of a candidate the routes give (0.15)"""
    value = getattr(_settings(settings), "RECONCILE_LEAST_SCORE", DEFAULT_LEAST_SCORE)
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not 0 <= value <= 1
    ):
        raise PanglossInitialisationError(
            "RECONCILE_LEAST_SCORE is a number from 0 to 1 (the least score of a candidate given), "
            f"not {value!r}"
        )
    return float(value)


def keep_decisions(settings: Any = None) -> bool:
    """`RECONCILE_KEEP_DECISIONS`: whether what the stored route offers, and what is chosen of it, is kept (True)"""
    value = getattr(
        _settings(settings), "RECONCILE_KEEP_DECISIONS", DEFAULT_KEEP_DECISIONS
    )
    if not isinstance(value, bool):
        raise PanglossInitialisationError(
            "RECONCILE_KEEP_DECISIONS is True or False (whether what the stored route offers, and what is chosen "
            f"of it, is kept), not {value!r}"
        )
    return value


def shown_for(settings: Any = None) -> float:
    """`RECONCILE_SHOWN_FOR`: in minutes, how long what was offered is an example of a decision made of it (30)"""
    value = getattr(_settings(settings), "RECONCILE_SHOWN_FOR", DEFAULT_SHOWN_FOR)
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not 0 < value < math.inf
    ):
        raise PanglossInitialisationError(
            "RECONCILE_SHOWN_FOR is a finite number of minutes above 0 (how long what was offered is an example of a "
            f"decision made of it), not {value!r}"
        )
    return float(value)


def learn_from(settings: Any = None) -> int:
    """`RECONCILE_LEARN_FROM`: the fewest decisions a fit is made of for it to be put in use (100)"""
    value = getattr(_settings(settings), "RECONCILE_LEARN_FROM", DEFAULT_LEARN_FROM)
    return _whole(
        "RECONCILE_LEARN_FROM",
        value,
        1,
        None,
        "the fewest decisions a fit is made of for it to be put in use",
    )


def new_above(settings: Any = None) -> float:
    """`RECONCILE_NEW_ABOVE`: the likelihood that the one meant is none of those offered above which the stored route
    says so (`probablyNew`; 0.5)"""
    value = getattr(_settings(settings), "RECONCILE_NEW_ABOVE", DEFAULT_NEW_ABOVE)
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not 0 <= value <= 1
    ):
        raise PanglossInitialisationError(
            "RECONCILE_NEW_ABOVE is a number from 0 to 1 (the likelihood that the one meant is none of those "
            f"offered, above which the answer says it is probably someone new), not {value!r}"
        )
    return float(value)


def _share(name: str, value: Any, what: str) -> float:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not 0 <= value <= 1
    ):
        raise PanglossInitialisationError(
            f"{name} is a number from 0 to 1 ({what}), not {value!r}"
        )
    return float(value)


def suggest_above(settings: Any = None) -> float:
    """`RECONCILE_SUGGEST_ABOVE`: the least score of the best candidate for a suggestion to be made (0.6)"""
    value = getattr(
        _settings(settings), "RECONCILE_SUGGEST_ABOVE", DEFAULT_SUGGEST_ABOVE
    )
    return _share(
        "RECONCILE_SUGGEST_ABOVE",
        value,
        "the least score of the best candidate for a suggestion to be made",
    )


def suggest_most(settings: Any = None) -> int:
    """`RECONCILE_SUGGEST_MOST`: the most alternatives a suggestion has (3, at most 10)"""
    value = getattr(_settings(settings), "RECONCILE_SUGGEST_MOST", DEFAULT_SUGGEST_MOST)
    return _whole(
        "RECONCILE_SUGGEST_MOST",
        value,
        1,
        MOST_SUGGEST_MOST,
        "the most alternatives a suggestion has",
    )


def suggest_within(settings: Any = None) -> float:
    """`RECONCILE_SUGGEST_WITHIN`: the least share of the best one's score an alternative scores (0.7)"""
    value = getattr(
        _settings(settings), "RECONCILE_SUGGEST_WITHIN", DEFAULT_SUGGEST_WITHIN
    )
    return _share(
        "RECONCILE_SUGGEST_WITHIN",
        value,
        "the least share of the best candidate's score that another suggested with it scores",
    )


def _true_or_false(name: str, value: Any, what: str) -> bool:
    if not isinstance(value, bool):
        raise PanglossInitialisationError(
            f"{name} is True or False ({what}), not {value!r}"
        )
    return value


def learn_from_suggestions(settings: Any = None) -> bool:
    """`RECONCILE_LEARN_FROM_SUGGESTIONS`: whether `learn` learns from the examples made of confirmed suggestions
    (True)"""
    value = getattr(
        _settings(settings),
        "RECONCILE_LEARN_FROM_SUGGESTIONS",
        DEFAULT_LEARN_FROM_SUGGESTIONS,
    )
    return _true_or_false(
        "RECONCILE_LEARN_FROM_SUGGESTIONS",
        value,
        "whether a fit learns from the examples a person's confirmation of a suggestion of the worker made",
    )


def suggest_on_save(settings: Any = None) -> bool:
    """`RECONCILE_SUGGEST_ON_SAVE`: whether a save that says nothing leaves its document for the worker (False)"""
    value = getattr(
        _settings(settings), "RECONCILE_SUGGEST_ON_SAVE", DEFAULT_SUGGEST_ON_SAVE
    )
    return _true_or_false(
        "RECONCILE_SUGGEST_ON_SAVE",
        value,
        "whether a save that says nothing of it leaves its document for the worker that suggests",
    )


def worker_in_server(settings: Any = None) -> bool:
    """`RECONCILE_WORKER_IN_SERVER`: whether the server runs the worker that suggests (True)"""
    value = getattr(
        _settings(settings), "RECONCILE_WORKER_IN_SERVER", DEFAULT_WORKER_IN_SERVER
    )
    return _true_or_false(
        "RECONCILE_WORKER_IN_SERVER",
        value,
        "whether the server runs the worker that suggests, or it runs apart: `pangloss reconcile worker`",
    )


def toolchain(settings: Any = None) -> str:
    """`RECONCILE_TOOLCHAIN`: the username the worker writes as ("pangloss-reconcile")"""
    from pangloss_users.models import USERNAME_PATTERN

    value = getattr(_settings(settings), "RECONCILE_TOOLCHAIN", DEFAULT_TOOLCHAIN)
    if not isinstance(value, str) or not USERNAME_PATTERN.match(value):
        raise PanglossInitialisationError(
            "RECONCILE_TOOLCHAIN is the username the worker writes as (letters, numbers, '_', '.' and '-', at most "
            f"64), not {value!r}"
        )
    return value


def suggest_as(settings: Any = None) -> str:
    """`RECONCILE_SUGGEST_AS`: the name of the class the worker writes ("IdentificationByToolchainFromText"). Only that
    it is a name: `check_suggest_as` checks the model"""
    value = getattr(_settings(settings), "RECONCILE_SUGGEST_AS", DEFAULT_SUGGEST_AS)
    if not isinstance(value, str) or not value.isidentifier():
        raise PanglossInitialisationError(
            "RECONCILE_SUGGEST_AS is the name of the class the worker writes in a stand-in's place "
            f"({DEFAULT_SUGGEST_AS!r}), not {value!r}"
        )
    return value


def check_suggest_as(settings: Any = None) -> Any:
    """The model `RECONCILE_SUGGEST_AS` names, refused (`PanglossInitialisationError`) if there is none or it lacks
    a field the worker fills (`SUGGESTION_FIELDS`). Asked at `initialise()` when `RECONCILE_SUGGEST_ON_SAVE` is True,
    and by the worker before it works"""
    name = suggest_as(settings)
    model = ModelRegistry._model_dict.get(name)
    fields = getattr(getattr(model, "_meta", None), "fields", None)
    if model is None or fields is None:
        raise PanglossInitialisationError(
            f"RECONCILE_SUGGEST_AS names {name!r}, which is not a model: name a class of suggestion with the fields "
            f"{', '.join(SUGGESTION_FIELDS)} (pangloss_library's {DEFAULT_SUGGEST_AS}, with pangloss_library "
            "installed)"
        )
    lacking = [field for field in SUGGESTION_FIELDS if field not in fields]
    if lacking:
        raise PanglossInitialisationError(
            f"RECONCILE_SUGGEST_AS names {name!r}, which has no {', '.join(lacking)}: the worker fills "
            f"{', '.join(SUGGESTION_FIELDS)} (pangloss_library's {DEFAULT_SUGGEST_AS} has them)"
        )
    return model


def suggest_with(settings: Any = None) -> str | None:
    """`RECONCILE_SUGGEST_WITH`: the name of a project's judge, `"package.module:function"` (None). Only its form:
    `judge` imports it"""
    value = getattr(_settings(settings), "RECONCILE_SUGGEST_WITH", None)
    if value is None:
        return None
    if not isinstance(value, str) or not JUDGE_FORM.match(value):
        raise PanglossInitialisationError(
            "RECONCILE_SUGGEST_WITH names a project's judge as 'package.module:function' (the module's dotted name, "
            f"a colon, the function's name), not {value!r}"
        )
    return value


def judge(settings: Any = None) -> tuple[str, Any] | None:
    """The judge `RECONCILE_SUGGEST_WITH` names, imported: its name and the function, or None when it is not set.
    Refused (`PanglossInitialisationError`) if its module cannot be imported (with the import's own error), has no
    such name, or what it names cannot be called"""
    name = suggest_with(settings)
    if name is None:
        return None
    module_name, function_name = name.split(":")
    try:
        module = importlib.import_module(module_name)
    except Exception as error:
        raise PanglossInitialisationError(
            f"RECONCILE_SUGGEST_WITH names {name!r}, whose module {module_name!r} cannot be imported: "
            f"{type(error).__name__}: {error}"
        ) from error
    function = getattr(module, function_name, None)
    if function is None:
        raise PanglossInitialisationError(
            f"RECONCILE_SUGGEST_WITH names {name!r}, but {module_name!r} has no {function_name!r}"
        )
    if not callable(function):
        raise PanglossInitialisationError(
            f"RECONCILE_SUGGEST_WITH names {name!r}, which is not a function that can be called (it is a "
            f"{type(function).__name__})"
        )
    return name, function


def suggest_timeout(settings: Any = None) -> float:
    """`RECONCILE_SUGGEST_TIMEOUT`: in seconds, how long a project's judge is given for one stand-in (60)"""
    value = getattr(
        _settings(settings), "RECONCILE_SUGGEST_TIMEOUT", DEFAULT_SUGGEST_TIMEOUT
    )
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not 0 < value < math.inf
    ):
        raise PanglossInitialisationError(
            "RECONCILE_SUGGEST_TIMEOUT is a number of seconds above 0 (how long a project's judge is given for one "
            f"stand-in), not {value!r}"
        )
    return float(value)


def weights(settings: Any = None) -> dict[str, float]:
    """The weight of each part in a candidate's score: the profile's (`profile()`), with `RECONCILE_WEIGHTS` over
    them, and of `shared` (1.5 unless given); those above 0, by name"""
    from pangloss_vectors.parts import parts, profiles

    settings = _settings(settings)
    given = getattr(settings, "RECONCILE_WEIGHTS", None) or {}
    if not isinstance(given, Mapping):
        raise PanglossInitialisationError(
            f"RECONCILE_WEIGHTS is a weight for each part ({{'name': 1, 'graph': 0.5}}), not {given!r}"
        )
    known = parts()
    unknown = sorted(
        str(name) for name in given if name not in known and name != SHARED
    )
    if unknown:
        raise PanglossInitialisationError(
            f"RECONCILE_WEIGHTS names {', '.join(repr(u) for u in unknown)}, which is not a part: what may be named "
            f"is the parts ({', '.join(known) or 'none'}) and {SHARED} (the entities a candidate is named with)"
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
    name = profile(settings)
    searched = profiles(settings)[name]
    found = {**searched, SHARED: DEFAULT_SHARED, **given}
    if not any(
        found.get(part, 0) > 0 for part, weight in searched.items() if weight > 0
    ):
        raise PanglossInitialisationError(
            f"RECONCILE_WEIGHTS gives each part the profile {name!r} weighs ({', '.join(sorted(searched))}) a "
            f"weight of 0: what is found by them could not be scored ({SHARED} alone is not enough). Give one of "
            "them a weight above 0"
        )
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
    most_unknowns(settings)
    reasons(settings)
    least_score(settings)
    keep_decisions(settings)
    shown_for(settings)
    learn_from(settings)
    learn_from_suggestions(settings)
    new_above(settings)
    suggest_above(settings)
    suggest_most(settings)
    suggest_within(settings)
    weights(settings)
    worker_in_server(settings)
    toolchain(settings)
    suggest_as(settings)
    if suggest_on_save(settings):
        check_suggest_as(settings)
    suggest_timeout(settings)
    judge(settings)


def install() -> None:
    """(`pangloss_reconcile._install`)"""
    if check not in ModelRegistry.after_finalise:
        ModelRegistry.after_finalise.append(check)
