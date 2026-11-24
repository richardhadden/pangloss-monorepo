"""Retraining: the decisions kept (`decisions.py`) fitted, compared and written as a fit, put in use only past a check
(step 11.5 of implementation_docs/similarity-build-plan.md; implementation_docs/reconcile.md, "Learning from
decisions"). What the examples are is `learning.py`'s, the maths `pangloss_learn`'s; this reads and writes.

    (:PGReconcileModel {id, at, profile, signature, parts, weights, features, decisions, suggested, latest, ranking,
                        none, ranking_why, none_why, compared, in_use})

one for each fit written, **none ever deleted**: the signatures of the examples it was made of (`decisions.SIGNATURES`,
as an example holds them), how many decisions went into it, how many of those were made of confirmed suggestions
(`suggested`, step 10.5f; null in a fit written before it) and the newest one's `at` (`latest`), each of the two
models as `pangloss_learn.Model.to_json()` or null with why (the `Unfittable`'s message), what each comparison found
(`compared`, JSON: `{"ranking": {decisions, model, baseline} | null, "none": ... | null}`), and `in_use`: **at most one
fit is in use**, set and unset in one write transaction.

The check (call e): a fit is put in use only when it is of `RECONCILE_LEARN_FROM` decisions or more, and its "none of
these" model was fitted and `compare_calls` found it no worse than always answering the commoner. The ranking model's
comparison is recorded and used by nothing (the ranking stays hand-set: step 11.6). A fit that
fails the check is still written, not in use, and the fit in use before stays in use. `use` puts an earlier fit in use
through the same check (its stored decisions and comparison, and its signatures today's), or none.

`learn` is what `pangloss reconcile learn` and the admin job `reconcile_learn` run; `Learnt.lines()` is what both
print."""

import dataclasses
import datetime
import json
import uuid
from collections.abc import Mapping
from typing import Any

from pangloss_learn import Compared, Model, Unfittable, compare, compare_calls, fit

from pangloss_reconcile import decisions, learning, settings
from pangloss_reconcile import score as scoring

MODEL = "PGReconcileModel"

# (how the comparisons are made: the same each time, so that a fit says the same of the same decisions)
FOLDS = 5
SEED = 0
RIDGE = 1.0

PROPERTIES = (
    "id",
    "at",
    *decisions.SIGNATURES,
    "decisions",
    "suggested",
    "latest",
    "ranking",
    "none",
    "ranking_why",
    "none_why",
    "compared",
    "in_use",
)

# (those a fit written before step 10.5f lacks, and a caller of `write` may leave out)
OPTIONAL = ("suggested",)

FITS_QUERY = f"""
MATCH (m:{MODEL})
RETURN {", ".join(f"m.{name} AS {name}" for name in PROPERTIES)}
ORDER BY at DESC, id
"""

# (the newest of those marked: two runs at the same instant could each have marked one)
IN_USE_QUERY = f"""
MATCH (m:{MODEL})
WHERE m.in_use = true
RETURN {", ".join(f"m.{name} AS {name}" for name in PROPERTIES)}
ORDER BY at DESC, id
LIMIT 1
"""

FIT_QUERY = f"""
MATCH (m:{MODEL} {{id: $id}})
RETURN {", ".join(f"m.{name} AS {name}" for name in PROPERTIES)}
"""

UNUSE_QUERY = f"""
MATCH (m:{MODEL} {{in_use: true}})
SET m.in_use = false
"""

USE_QUERY = f"""
MATCH (m:{MODEL} {{id: $id}})
SET m.in_use = true
"""

WRITE_QUERY = f"""
CREATE (m:{MODEL} {{{", ".join(f"{name}: ${name}" for name in PROPERTIES)}}})
"""


NO_FIT = "No fit is in use"

# (the ranking model's comparison is kept and read by nothing: its line says so, so that a fit in use beside a ranking
# model that did worse is not misread)
RANKING_UNUSED = " (recorded: nothing uses the ranking model)"


class Refused(ValueError):
    """A fit that cannot be put in use (`use`): the message says why"""


@dataclasses.dataclass(frozen=True)
class Fitted:
    """One of the two models of a fit: the model, or why it could not be fitted; what its comparison found, or why
    it could not be made"""

    model: Model | None
    why: str | None = None
    compared: Compared | None = None
    compared_why: str | None = None


@dataclasses.dataclass
class Learnt:
    """What `learn` did, or would do (`dry_run`): how many shown records were swept (or would be), how many examples
    were read, left out as of other vectors or weights (`other`), left out as lacking a part (`lacking`), left out as
    made of confirmed suggestions while `RECONCILE_LEARN_FROM_SUGGESTIONS` is False (`suggestions_left_out`), the
    decisions learnt from, those of them made of confirmed suggestions (`suggested`), and those with no row displayed
    (`undisplayed`: left out of the "none of these" model). Then either nothing was fitted (no decision; or nothing new since the fit `unchanged`), or both models
    (`ranking`, `none`), the fit written (`id`; in a dry run, none), whether it is in use, and why not (`why_not`)"""

    dry_run: bool
    swept: int
    read: int = 0
    other: int = 0
    lacking: int = 0
    suggestions_left_out: int = 0
    decisions: int = 0
    suggested: int = 0
    undisplayed: int = 0
    unchanged: Mapping[str, Any] | None = None
    ranking: Fitted | None = None
    none: Fitted | None = None
    id: str | None = None
    in_use: bool = False
    why_not: str | None = None
    kept_in_use: str | None = None
    """(a fit not put in use) the id of the fit that stays in use, if one is"""

    def counts(self) -> dict[str, int]:
        """The counts, as the admin job gives them"""
        return {
            "swept": self.swept,
            "read": self.read,
            "other": self.other,
            "lacking": self.lacking,
            "suggestions_left_out": self.suggestions_left_out,
            "decisions": self.decisions,
            "suggested": self.suggested,
            "undisplayed": self.undisplayed,
        }

    def lines(self) -> list[str]:
        """What happened, in plain lines (what `pangloss reconcile learn` prints)"""
        lines = [
            (
                f"{_many(self.swept, 'record')} of what was offered "
                + ("would be removed (a dry run)" if self.dry_run else "removed")
            ),
            f"{_many(self.read, 'example')} read",
        ]
        if self.other:
            lines.append(
                f"{_many(self.other, 'example')} left out: of other vectors or weights"
            )
        if self.lacking:
            lines.append(
                f"{_many(self.lacking, 'example')} left out: a mention had no vector of a part the features need"
            )
        if self.suggestions_left_out:
            lines.append(
                f"{_many(self.suggestions_left_out, 'example')} left out: of confirmed suggestions "
                "(RECONCILE_LEARN_FROM_SUGGESTIONS is False)"
            )
        lines.append(
            f"{_many(self.decisions, 'decision')} to learn from"
            + (
                f", {self.suggested:,} of them of confirmed suggestions"
                if self.suggested
                else ""
            )
        )
        if not self.decisions:
            lines.append(
                "Nothing fitted and nothing written: there is no decision to learn from"
            )
            return lines
        if self.unchanged is not None:
            fitted = self.unchanged
            lines.append(
                f"Nothing new since the fit of {_when(fitted['at'])} ({fitted['id']}): nothing written"
                + (
                    ""
                    if fitted["in_use"]
                    else f"; it is not in use (`pangloss reconcile learn --use {fitted['id']}` puts it in use, "
                    "through the check)"
                )
            )
            return lines
        if self.undisplayed:
            lines.append(
                f"{_many(self.undisplayed, 'decision')} with no suggestion displayed: left out of the "
                '"none of these" model'
            )
        assert self.ranking is not None and self.none is not None
        lines.append(
            _said("The ranking model", self.ranking, ranking=True) + RANKING_UNUSED
        )
        lines.append(_said('The "none of these" model', self.none, ranking=False))
        if self.dry_run:
            lines.append(
                "Nothing written (a dry run): the fit would be "
                + (
                    "put in use"
                    if self.why_not is None
                    else f"written, not in use: {self.why_not}"
                )
            )
            return lines
        if self.in_use:
            lines.append(f"Written: the fit {self.id}, in use")
        else:
            lines.append(f"Written: the fit {self.id}, not in use: {self.why_not}")
            lines.append(
                f"The fit in use stays in use: {self.kept_in_use}"
                if self.kept_in_use
                else NO_FIT
            )
        return lines


def _many(n: int, what: str) -> str:
    return f"{n:,} {what}{'' if n == 1 else 's'}"


def _when(value: Any) -> str:
    found = decisions._utc(decisions._native(value))
    if isinstance(found, datetime.datetime):
        return found.astimezone(datetime.UTC).strftime("%Y-%m-%d %H:%M:%S UTC")
    return str(found)


def _said(name: str, fitted: Fitted, *, ranking: bool) -> str:
    if fitted.model is None:
        return f"{name}: not fitted ({fitted.why})"
    of = (
        _many(fitted.model.examples, "row")
        if ranking
        else _many(fitted.model.examples, "decision")
    )
    if fitted.compared is None:
        return f"{name}: fitted on {of}; not compared ({fitted.compared_why})"
    found = fitted.compared
    if ranking:
        return (
            f"{name}: fitted on {of}; the one taken was first in {found.model:,} of {found.decisions:,} by the "
            f"model, {found.baseline:,} by the score set by hand"
        )
    return (
        f"{name}: fitted on {of}; called rightly in {found.model:,} of {found.decisions:,} by the model, "
        f"{found.baseline:,} by always answering the commoner"
    )


def _fitted(examples: list[Any], features: list[str], compared: Any) -> Fitted:
    """A model of the examples, and its comparison (`compared()`), each or why not"""
    try:
        model = fit(examples, features, ridge=RIDGE, fitted_at=_now().isoformat())
    except Unfittable as error:
        return Fitted(None, str(error))
    try:
        return Fitted(model, None, compared())
    except Unfittable as error:
        return Fitted(model, None, None, str(error))


def _now() -> datetime.datetime:
    return datetime.datetime.now(datetime.UTC)


def why_not(
    none_decisions: int,
    none_fitted: bool,
    none_why: str | None,
    none_compared: Compared | None,
) -> str | None:
    """Why a fit may not be put in use (the check, call e), or None: each condition that failed. `none_decisions` is
    how many decisions the "none of these" model was fitted on (those with a row displayed): the model the check
    guards, so the count `RECONCILE_LEARN_FROM` is held against; `none_why` why it was not fitted, or not compared"""
    reasons = []
    least = settings.learn_from()
    if none_decisions < least:
        reasons.append(
            f'its "none of these" model is of {_many(none_decisions, "decision")}, fewer than RECONCILE_LEARN_FROM '
            f"({least:,})"
        )
    if not none_fitted:
        reasons.append(f'its "none of these" model could not be fitted ({none_why})')
    elif none_compared is None:
        reasons.append(f'its "none of these" model could not be compared ({none_why})')
    elif not none_compared.no_worse:
        reasons.append(
            f'its "none of these" model called {none_compared.model:,} of {none_compared.decisions:,} rightly, '
            f"fewer than always answering the commoner ({none_compared.baseline:,})"
        )
    return "; ".join(reasons) or None


def _compared_json(found: Compared | None) -> dict[str, int] | None:
    return None if found is None else dataclasses.asdict(found)


def _compared_of(data: Any) -> Compared | None:
    return None if not data else Compared(**data)


def _database() -> Any:
    return decisions._database()


async def fits() -> list[dict[str, Any]]:
    """Every fit written, newest first"""
    database = _database()

    @database.read_transaction
    async def read(tx: Any) -> list[dict[str, Any]]:
        return [record.data() async for record in await tx.run(FITS_QUERY)]

    return await read()


async def in_use() -> dict[str, Any] | None:
    """The fit in use (the newest of those marked), or None: one read of one node, which the stored route makes on
    every request (step 11.6)"""
    database = _database()

    @database.read_transaction
    async def read(tx: Any) -> dict[str, Any] | None:
        record = await (await tx.run(IN_USE_QUERY)).single()
        return record.data() if record else None

    return await read()


def usable(fit: Mapping[str, Any] | None, now: Mapping[str, Any]) -> bool:
    """Whether a fit (as `in_use` gives it) can say "none of these" today: it is of today (`decisions.of_today`: the
    profile, its signature and its parts', the weights, `FEATURES`, the least score, those `now` holds) and it has a
    "none of these" model. `in_use` on the node alone does not mean that"""
    return (
        fit is not None and fit.get("none") is not None and decisions.of_today(fit, now)
    )


async def write(properties: Mapping[str, Any]) -> None:
    """Write a fit (`PROPERTIES`, each given but those of `OPTIONAL`, null when not), in one write transaction: when it
    is `in_use`, the fit in use before is no longer. What `learn` writes with"""
    database = _database()
    given = {
        name: properties.get(name) if name in OPTIONAL else properties[name]
        for name in PROPERTIES
    }

    @database.write_transaction
    async def written(tx: Any) -> None:
        if given["in_use"]:
            await (await tx.run(UNUSE_QUERY)).consume()
        await (await tx.run(WRITE_QUERY, **given)).consume()

    await written()


async def learn(*, dry_run: bool = False) -> Learnt:
    """Sweep (`decisions.sweep`; in a dry run, only counted), read the examples of today (`decisions.of_today`; the
    others left out, counted), leave out, counted, those in which a row lacks a feature, and those made of confirmed
    suggestions when `RECONCILE_LEARN_FROM_SUGGESTIONS` is False (counted apart either way), and unless there is no
    decision or nothing new since the newest fit of today, fit and compare both models, write the fit (not in a dry
    run) and put it in use if it passes the check (`why_not`)"""
    from pangloss_vectors import store

    swept = await decisions.sweepable() if dry_run else await decisions.sweep()
    now = decisions.today(await store.states())
    kept = await decisions.examples()
    todays = [example for example in kept if decisions.of_today(example, now)]
    weights = json.loads(now["weights"])
    ranking_features = learning.ranking_features(weights)
    none_features = learning.none_features(ranking_features)
    complete = [e for e in todays if not learning.lacking(e["rows"], ranking_features)]
    # (those made of confirmed suggestions are left out when the setting says so: counted apart either way)
    of_suggestions = settings.learn_from_suggestions()
    every = [(e, learning.decision_of(e)) for e in complete]
    taken = [
        (e, d) for e, d in every if of_suggestions or not learning.from_suggestion(d)
    ]
    usable = [e for e, _ in taken]
    chosen = [d for _, d in taken]
    none_examples = learning.none_examples(chosen, none_features)
    learnt = Learnt(
        dry_run=dry_run,
        swept=swept,
        read=len(kept),
        other=len(kept) - len(todays),
        lacking=len(todays) - len(complete),
        suggestions_left_out=len(every) - len(taken),
        decisions=len(chosen),
        suggested=sum(1 for d in chosen if learning.from_suggestion(d)),
        undisplayed=len(chosen) - len(none_examples),
    )
    if not chosen:
        return learnt
    latest = max(e["at"] for e in usable)
    written = await fits()
    newest = next((f for f in written if decisions.of_today(f, now)), None)
    if (
        newest is not None
        and newest["decisions"] == len(chosen)
        and decisions._utc(decisions._native(newest["latest"])) == latest
    ):
        learnt.unchanged = newest
        return learnt

    ranking_examples = learning.ranking_examples(chosen, ranking_features)
    learnt.ranking = _fitted(
        ranking_examples,
        ranking_features,
        lambda: compare(
            ranking_examples,
            ranking_features,
            lambda features: scoring.score(features, weights),
            folds=FOLDS,
            seed=SEED,
            ridge=RIDGE,
        ),
    )
    learnt.none = _fitted(
        none_examples,
        none_features,
        lambda: compare_calls(
            none_examples, none_features, folds=FOLDS, seed=SEED, ridge=RIDGE
        ),
    )
    none = learnt.none
    learnt.why_not = why_not(
        len(none_examples),
        none.model is not None,
        none.why if none.model is None else none.compared_why,
        none.compared,
    )
    learnt.in_use = learnt.why_not is None
    if dry_run:
        learnt.in_use = False
        return learnt

    learnt.id = str(uuid.uuid4())
    ranking = learnt.ranking
    properties = {
        "id": learnt.id,
        "at": _now(),
        **{name: now[name] for name in decisions.SIGNATURES},
        "decisions": len(chosen),
        "suggested": learnt.suggested,
        "latest": latest,
        "ranking": ranking.model.to_json() if ranking.model else None,
        "none": none.model.to_json() if none.model else None,
        # (why it was not fitted, or, fitted, why it could not be compared)
        "ranking_why": ranking.why if ranking.model is None else ranking.compared_why,
        "none_why": none.why if none.model is None else none.compared_why,
        "compared": json.dumps(
            {
                "ranking": _compared_json(ranking.compared),
                "none": _compared_json(none.compared),
            },
            sort_keys=True,
        ),
        "in_use": learnt.in_use,
    }
    await write(properties)
    if not learnt.in_use:
        # (a fit marked in use that is not of today is used by nothing: not said to stay in use)
        current = next(
            (
                f
                for f in written
                if f["in_use"]
                and f.get("none") is not None
                and decisions.of_today(f, now)
            ),
            None,
        )
        learnt.kept_in_use = current["id"] if current else None
    return learnt


async def use(id: str | None) -> dict[str, Any] | None:
    """Put the fit `id` in use, and no other, through the check (`why_not`, of what it stored) and only if its
    signatures are today's; `Refused` otherwise, and nothing changes. None: no fit in use. Gives the fit put in
    use"""
    from pangloss_vectors import store

    database = _database()
    if id is None:

        @database.write_transaction
        async def unuse(tx: Any) -> None:
            await (await tx.run(UNUSE_QUERY)).consume()

        await unuse()
        return None

    @database.read_transaction
    async def read(tx: Any) -> dict[str, Any] | None:
        record = await (await tx.run(FIT_QUERY, id=id)).single()
        return record.data() if record else None

    found = await read()
    if found is None:
        raise Refused(f"There is no fit {id}")
    if not decisions.of_today(found, decisions.today(await store.states())):
        raise Refused(
            f"The fit {id} is of other vectors or weights than today's (the profile, its parts, their signatures, "
            "RECONCILE_WEIGHTS, RECONCILE_LEAST_SCORE or the features have changed since): its numbers would not "
            "mean what they meant"
        )
    compared = json.loads(found["compared"] or "{}")
    why = why_not(
        Model.from_json(found["none"]).examples if found["none"] else 0,
        found["none"] is not None,
        found["none_why"],
        _compared_of(compared.get("none")),
    )
    if why is not None:
        raise Refused(f"The fit {id} cannot be put in use: {why}")

    @database.write_transaction
    async def put(tx: Any) -> None:
        await (await tx.run(UNUSE_QUERY)).consume()
        await (await tx.run(USE_QUERY, id=id)).consume()

    await put()
    return {**found, "in_use": True}
