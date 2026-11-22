"""A search by a name (implementation_docs/similarity-build-plan.md, step 8.6): the name vector of a text, as a stored
item's would be, and the items nearest it through `pangloss_vectors.nearest(vector=...)`.

    found = await pangloss_names.search("Jon Smyth", types=["Person"])

**What a hit's score is.** The query has only the name part; the stored vectors of a profile have every part it
weighs. A profile's combined vector is each part's at length one times the square root of its weight, end to end
(`store.Layout.combine`), so the score of a hit (the cosine of the two combined vectors) is

    cos(names) × sqrt(w_name / Σ w of the parts the hit has a vector of)

With `{"name": 1, "graph": 0.25}`, 0.894 × the cosine of the names for a hit with a graph vector, and the cosine of
the names itself for one without. Among hits with the same parts the order is that of the names; a hit with fewer
parts is lifted against one with more. The score is not the cosine of the names, and not comparable between profiles.
"""

from collections.abc import Collection, Iterable
from typing import Any

from pangloss_vectors.search import Nearest
from pangloss_vectors.store import RebuildDue

from pangloss_names.part import NAME, PART

# (what a profile that weighs the name part looks like, for the message that none does)
EXAMPLE_PROFILE = '{"who": {"name": 1, "graph": 0.25}}'


class NotBuilt(RebuildDue):
    """The name part has never been built, so there is no table of rarity to weigh a name by"""


async def vector_of(text: str | Iterable[str]) -> list[float] | None:
    """The name vector of a text (or of several names of one item), as a stored item with those names would have it:
    by the table of rarity in use (the one kept with the generation of the last rebuild) and the table of variants;
    None if the text has no letter or digit. `NotBuilt` if the part has never been built; `store.RebuildDue` if it is
    built and its table of rarity is not there"""
    rarity = await PART.rarity()
    if rarity is None:
        raise NotBuilt(
            "The name part has never been built, so there is no table of rarity to weigh a name by: run "
            "`pangloss vectors rebuild`"
        )
    names = [text] if isinstance(text, str) else list(text)
    return PART.vector(names, rarity)


def profile_for(profile: str | None = None) -> str:
    """The profile a search by a name uses: the one named, which must weigh the name part, or else the first of the
    settings' profiles that does, in the order of their names. `ValueError`, saying what to set, if there is none"""
    from pangloss_vectors.parts import profiles

    known = profiles()
    if profile is not None:
        if profile not in known:
            raise ValueError(
                f"There is no profile named {profile!r}: the profiles are {', '.join(sorted(known))}"
            )
        if known[profile].get(NAME, 0) <= 0:
            raise ValueError(
                f"The profile {profile!r} does not weigh the name part, so a name cannot be searched by it: a "
                f"profile must weigh the name part (VECTORS_PROFILES = {EXAMPLE_PROFILE})"
            )
        return profile
    weighing = [name for name in sorted(known) if known[name].get(NAME, 0) > 0]
    if not weighing:
        raise ValueError(
            "No profile weighs the name part, so a name cannot be searched: a profile must weigh the name part "
            f"(VECTORS_PROFILES = {EXAMPLE_PROFILE})"
        )
    return weighing[0]


def classes_of(types: Collection[str]) -> list[str]:
    """The concrete classes the names stand for (each class and those below it, or a trait's), in order of name.
    `pangloss_vectors.fields.NotAClass` (a `ValueError`) for a name that is not one of documents or entities"""
    from pangloss_vectors.fields import classes_of as of_one

    return sorted({found for name in types for found in of_one(name)})


async def search(
    text: str | Iterable[str],
    *,
    types: Collection[str] | None = None,
    profile: str | None = None,
    k: int = 10,
    see_unpublished: bool = False,
) -> Nearest:
    """The `k` items nearest the name vector of `text` (`vector_of`), by a profile that weighs the name part
    (`profile_for`), narrowed to the classes `types` (and those below them), as `pangloss_vectors.nearest(vector=...)`
    gives them (a hit's score: see the module). Unpublished documents only with `see_unpublished`. `ValueError` if the
    text has no letter or digit, or no profile weighs the name part; `NotBuilt` if the part was never built"""
    from pangloss_vectors.search import nearest

    if isinstance(types, str):
        types = [types]
    chosen = profile_for(profile)
    narrowed = classes_of(types) if types else None
    vector = await vector_of(text)
    if vector is None:
        raise ValueError(
            f"{text!r} has no letter or digit: there is no name to search by"
        )
    asked: Any = list(types) if types else None
    return await nearest(
        vector={NAME: vector},
        profile=chosen,
        types=narrowed,
        k=k,
        see_unpublished=see_unpublished,
        asked=asked,
    )
