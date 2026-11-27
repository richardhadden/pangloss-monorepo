"""Learning from judgements: every judgement read, made examples of, fitted, compared and written as a fit, used only
past a check (implementation_docs/spaces-and-comparison-plan.md, step 6.6; implementation_docs/compare.md, "Learning
from judgements"). What the examples are is `learning.py`'s, the maths `pangloss_learn`'s; this reads and writes. The
same design as `pangloss_reconcile.fits`.

    (:PGCompareModel {id, at, signature, judgements, latest, left_out, examples_digest, one_event, answers,
                      one_event_examples,
                      answers_examples, one_event_why, answers_why, compared, margin, one_event_used, answers_used,
                      in_use, not_in_use})

one for each fit written, **none ever deleted**: what makes fits comparable (`signature`, `learning.signature`), how
many judgements were read and when the newest of them was made (`latest`), those left out by why (`left_out`,
JSON), each of the two models (`one_event`: one event or two; `answers`: does this answer that) as
`pangloss_learn.Model.to_json()` or null, how many judgements it is of, and why it was not fitted or, fitted, not
compared (`*_why`), what each comparison found (`compared`, JSON: `{"one_event": {decisions, model, baseline, differ}
| null, "answers": ...}`), the `COMPARE_LEARN_MARGIN` it was checked by (`margin`), whether each model may be used
(`one_event_used`, `answers_used`: it passed the check), `in_use`, and why a fit whose models passed was not put in
use (`not_in_use`, or null). **At most one fit is in use**: set and unset in one write transaction, then, in another, all but the newest of those marked unmarked (`SETTLE_QUERY`: two runs at once may each mark their own without seeing the other's; the later settling sees both). A fit is in use
when one of its models or both passed, unless the fit in use has a model it lacks (below); the route uses those of
its models that passed, and the hand-set weights for the other.

The check, of each model by itself: it is of `COMPARE_LEARN_FROM` judgements or more, it was fitted and compared,
and on the judgements held out the hand-set score was not right more often than it by more than
`COMPARE_LEARN_MARGIN` times the square root of the number the two call differently (`learning.Fitted.passes`). A fit
none of whose models passes is still written, not in use, and the fit in use before stays in use. **A fit that would
lose a model** (the fit in use, of today's signature, has a model in use that the new fit's did not pass) is written
and not put in use, and says why (`not_in_use`); `use` can still put it in use. `use` puts an earlier fit in use
through the same check (its stored counts and comparisons, today's `COMPARE_LEARN_FROM` and `COMPARE_LEARN_MARGIN`, and
its signature today's), or none.

**Nothing new, nothing written** (as reconciliation's `learn`): where the newest fit written (in use or not) is of
today's signature, of as many judgements read, its `latest` the newest creation of those read now, of as many
examples of each model and left out for each reason, and of the same examples (`examples_digest`, `learning.digest`:
an edit of a cited statement or a merge of entities that changes an example is something new), `learn` writes
nothing and says so (`Learnt.unchanged`). A dry run still fits and compares, and says that nothing would be written.

`learn` is what `pangloss compare learn` and the admin job `compare_learn` run; `Learnt.lines()` is what both print.
`in_use_in` is what the route reads (`compare.compare`), and `for_route` what it makes of it."""

import dataclasses
import datetime
import json
import math
import uuid
from collections.abc import Mapping
from typing import Any

from pangloss_learn import CallsCompared, Model

from pangloss_compare import learning, maths, settings
from pangloss_compare.learning import Fitted
from pangloss_compare.models import BASE

MODEL = "PGCompareModel"

# (each model's name as the stored properties have it: `one_event`, `answers`)
NAMES = {maths.ONE_EVENT: "one_event", maths.ANSWERS_IT: "answers"}
MODELS = learning.MODELS
TITLES = {maths.ONE_EVENT: '"One event or two"', maths.ANSWERS_IT: '"Does this answer that"'}  # fmt: skip

PROPERTIES = (
    "id",
    "at",
    "signature",
    "judgements",
    "latest",
    "left_out",
    "examples_digest",
    "one_event",
    "answers",
    "one_event_examples",
    "answers_examples",
    "one_event_why",
    "answers_why",
    "compared",
    "margin",
    "one_event_used",
    "answers_used",
    "in_use",
    "not_in_use",
)

RETURNED = ", ".join(f"m.{name} AS {name}" for name in PROPERTIES)

FITS_QUERY = f"""
MATCH (m:{MODEL})
RETURN {RETURNED}
ORDER BY at DESC, id
"""

# (the newest of those marked: two runs at the same instant could each have marked one)
IN_USE_QUERY = f"""
MATCH (m:{MODEL})
WHERE m.in_use = true
RETURN {RETURNED}
ORDER BY at DESC, id
LIMIT 1
"""

FIT_QUERY = f"""
MATCH (m:{MODEL} {{id: $id}})
RETURN {RETURNED}
"""

UNUSE_QUERY = f"""
MATCH (m:{MODEL} {{in_use: true}})
SET m.in_use = false
"""

# (after a fit is put in use, in a transaction of its own: of those marked, all but the newest unmarked, as
# `IN_USE_QUERY` reads them. Two writes at once can each unmark what was marked before and mark their own, neither
# seeing the other's; the later of the two settlings, begun after both were written, sees both)
SETTLE_QUERY = f"""
MATCH (m:{MODEL})
WHERE m.in_use = true
WITH m ORDER BY m.at DESC, m.id
WITH collect(m) AS marked
UNWIND marked[1..] AS older
SET older.in_use = false
"""

USE_QUERY = f"""
MATCH (m:{MODEL} {{id: $id}})
SET m.in_use = true, m.one_event_used = $one_event_used, m.answers_used = $answers_used
"""

WRITE_QUERY = f"""
CREATE (m:{MODEL} {{{", ".join(f"{name}: ${name}" for name in PROPERTIES)}}})
"""


def judgements_query(fragments: Any) -> str:
    """Every judgement the reader sees (`$see_unpublished`), with the ids it cites, its verdict, whether either
    citation is marked changed, and when its head was made"""
    head = fragments.head_of("j", "j_head")
    return f"""
        MATCH (j:{BASE})
        {head.match}
        WITH j, j_head
        WHERE (j.head_node_id IS NULL OR j_head IS NOT NULL) AND {fragments.visible("j", head)}
        MATCH (j)-[e1:statement]->(c1:PGCitation)
        WHERE {fragments.forward("e1")}
        MATCH (j)-[e2:other]->(c2:PGCitation)
        WHERE {fragments.forward("e2")}
        WITH j, c1, c2, {head} AS made
        OPTIONAL MATCH (made)<-[:is_creation_of]-(creation:PGCreation)
        RETURN j.id AS id, j.verdict AS verdict, c1.target_id AS statement, c2.target_id AS other,
            coalesce(c1.changed_since_cited, false) OR coalesce(c2.changed_since_cited, false) AS changed,
            creation.created_when AS created_when
    """


def count_query(fragments: Any) -> str:
    head = fragments.head_of("j", "j_head")
    return f"""
        MATCH (j:{BASE})
        {head.match}
        WITH j, j_head
        WHERE (j.head_node_id IS NULL OR j_head IS NOT NULL) AND {fragments.visible("j", head)}
        RETURN count(j) AS n
    """


NO_FIT = "No fit is in use"

# How each reason a judgement is left out reads (`learning.LEFT_OUT`)
WHY = {
    learning.OLDER: "a newer judgement of the same pair counts",
    learning.CHANGED: "a statement it cites has changed since it was cited",
    learning.UNREAD: "a statement it cites is not there to be compared",
    learning.ITSELF: "it cites one statement twice",
    learning.NOT_COMPARED: "the two have no compared class in common",
    learning.SAYS_NOTHING: "one of the two says nothing of its contents",
    learning.TWO_PRESCRIPTIONS: "both prescribe",
    learning.BY_RULE: "the rules settle one event or two with no weighing",
    learning.NOT_THE_THING: "what may answer the prescription is not of the thing prescribed",
    learning.OTHER_VERDICT: "its verdict is of the other kind of pair",
}


class Refused(ValueError):
    """A fit that cannot be put in use (`use`): the message says why"""


def _many(n: int, what: str) -> str:
    return f"{n:,} {what}{'' if n == 1 else 's'}"


def _when(value: Any) -> datetime.datetime | None:
    from pangloss_compare.judgements import _when as when

    return when(value)


def _said_when(value: Any) -> str:
    found = _when(value)
    if found is None:
        return str(value)
    return found.astimezone(datetime.UTC).strftime("%Y-%m-%d %H:%M:%S UTC")


def _now() -> datetime.datetime:
    return datetime.datetime.now(datetime.UTC)


def why_not(
    examples: int,
    model: bool,
    why: str | None,
    compared: CallsCompared | None,
    margin: float | None = None,
) -> str | None:
    """Why one model may not be used (the check), or None: each condition that failed. `why`: why it was not fitted,
    or, fitted, not compared. `margin`: `COMPARE_LEARN_MARGIN` unless given"""
    reasons = []
    least = settings.learn_from()
    margin = settings.learn_margin() if margin is None else margin
    if examples < least:
        reasons.append(
            f"it is of {_many(examples, 'judgement')}, fewer than COMPARE_LEARN_FROM ({least:,})"
        )
    if not model:
        reasons.append(f"it could not be fitted ({why})")
    elif compared is None:
        reasons.append(f"it could not be compared ({why})")
    elif not compared.within(margin):
        reasons.append(
            f"it called {compared.model:,} of {compared.decisions:,} judgements held out rightly, the hand-set score "
            f"{compared.baseline:,}: worse by {compared.baseline - compared.model:,}, more than chance allows "
            f"(COMPARE_LEARN_MARGIN {margin:g} × √{compared.differ:,} called differently = "
            f"{margin * math.sqrt(compared.differ):.1f})"
        )
    return "; ".join(reasons) or None


def _why_of(fitted: Fitted) -> str | None:
    return fitted.why if fitted.model is None else fitted.compared_why


@dataclasses.dataclass
class Learnt:
    """What `learn` did, or would do (`dry_run`): how many judgements were read, those left out by why, how many
    were examples of each model; then either nothing was fitted (no judgement is an example of either model), or both
    models were (`fits`), each used or not and why not (`why_not`, by `maths.ONE_EVENT` and `maths.ANSWERS_IT`), the
    fit written (`id`; in a dry run, none), whether it is in use, why not where its models passed (`not_in_use`: it
    would lose a model the fit in use has, `lost`), and the fit that stays in use when it is not. `unchanged`: the
    newest fit written, where nothing is new since it (nothing written)"""

    dry_run: bool
    judgements: int = 0
    left_out: dict[str, int] = dataclasses.field(default_factory=dict)
    examples: dict[str, int] = dataclasses.field(default_factory=dict)
    fits: learning.Fits | None = None
    why_not: dict[str, str | None] = dataclasses.field(default_factory=dict)
    id: str | None = None
    in_use: bool = False
    kept_in_use: str | None = None
    not_in_use: str | None = None
    lost: tuple[str, ...] = ()
    unchanged: Mapping[str, Any] | None = None

    def used(self, model: str) -> bool:
        return self.fits is not None and self.why_not.get(model, "") is None

    def counts(self) -> dict[str, int]:
        """The counts, as the admin job gives them"""
        return {
            "judgements": self.judgements,
            **{f"left_out_{why}": n for why, n in self.left_out.items()},
            **{NAMES[model]: n for model, n in self.examples.items()},
        }

    def lines(self) -> list[str]:
        """What happened, in plain lines (what `pangloss compare learn` prints)"""
        lines = [f"{_many(self.judgements, 'judgement')} read"]
        if not self.judgements:
            lines.append(
                "Nothing fitted and nothing written: there is no judgement to learn from"
            )
            return lines
        for why in learning.LEFT_OUT:
            if self.left_out.get(why):
                lines.append(f"{_many(self.left_out[why], 'judgement')} left out: {WHY[why]}")  # fmt: skip
        for model in learning.MODELS:
            lines.append(
                f"{_many(self.examples.get(model, 0), 'judgement')} of {TITLES[model].lower()}"
            )
        if self.unchanged is not None and not self.dry_run:
            lines.append(_nothing_new(self.unchanged))
            return lines
        if self.fits is None:
            lines.append(
                "Nothing fitted and nothing written: no judgement is an example of either model"
            )
            return lines
        for model in learning.MODELS:
            lines.append(_said(model, self.fits.of(model), self.why_not.get(model)))
        used = [TITLES[m].lower() for m in learning.MODELS if self.used(m)]
        if self.dry_run:
            if self.unchanged is not None:
                would = "nothing, as a run would not write it: " + _nothing_new(self.unchanged, dry_run=True)  # fmt: skip
            elif used and self.not_in_use is None:
                would = f"put in use, for {' and '.join(used)}"
            else:
                would = "written, not in use" + (
                    f": {self.not_in_use}" if self.not_in_use else ""
                )
            lines.append(f"Nothing written (a dry run): the fit would be {would}")
            return lines
        if self.in_use:
            lines.append(f"Written: the fit {self.id}, in use for {' and '.join(used)}")
        else:
            lines.append(
                f"Written: the fit {self.id}, not in use"
                + (
                    f": {self.not_in_use} (`pangloss compare learn --use {self.id}` puts it in use)"
                    if self.not_in_use
                    else ""
                )
            )
            lines.append(
                f"The fit in use stays in use: {self.kept_in_use}"
                if self.kept_in_use
                else NO_FIT
            )
        return lines


def _nothing_new(fit: Mapping[str, Any], dry_run: bool = False) -> str:
    """(`learn` with nothing new since the newest fit written)"""
    said = (
        f"nothing new since the fit {fit['id']} of {_said_when(fit['at'])} (as many judgements, the newest made "
        "at the same time, and the same features, hand-set weights and rules)"
    )
    if dry_run:
        return said
    return f"{said[0].upper()}{said[1:]}: nothing written" + (
        ""
        if fit.get("in_use")
        else f"; it is not in use (`pangloss compare learn --use {fit['id']}` puts it in use, through the check)"
    )


def _said(model: str, fitted: Fitted, why: str | None) -> str:
    name = TITLES[model]
    if fitted.model is None:
        said = f"{name}: not fitted ({fitted.why})"
    elif fitted.compared is None:
        said = f"{name}: fitted on {_many(fitted.examples, 'judgement')}; not compared ({fitted.compared_why})"  # fmt: skip
    else:
        found = fitted.compared
        said = (
            f"{name}: fitted on {_many(fitted.examples, 'judgement')}; of {found.decisions:,} held out, called "
            f"rightly in {found.model:,} by the fit, {found.baseline:,} by the hand-set score, "
            f"{found.differ:,} called differently"
        )
    return f"{said}; {'used' if why is None else f'not used: {why}'}"


def _compared_json(found: CallsCompared | None) -> dict[str, int] | None:
    return None if found is None else dataclasses.asdict(found)


def _database() -> Any:
    from pangloss_core import backend

    return backend.current().database()


async def judged_in(tx: Any) -> list[learning.Judged]:
    """In an open read transaction: every judgement, as an admin sees them (deleted ones left out), with the two
    statements it cites as they are read now (`reading.read`: None where one is not there to be compared)"""
    from pangloss_core import backend
    from pangloss_models import ModelRegistry

    from pangloss_compare import reading

    if BASE not in ModelRegistry._model_dict:
        return []
    result = await tx.run(
        judgements_query(backend.current().fragments), see_unpublished=True
    )
    rows = [record.data() async for record in result]
    ids = {str(r[name]) for r in rows for name in ("statement", "other")}
    told = await reading.read(tx, sorted(ids), see_unpublished=True) if ids else {}
    return [
        learning.Judged(
            id=str(r["id"]),
            verdict=str(r["verdict"]),
            cited=(str(r["statement"]), str(r["other"])),
            a=told.get(str(r["statement"])),
            b=told.get(str(r["other"])),
            at=_when(r["created_when"]),
            changed=bool(r["changed"]),
        )
        for r in rows
    ]


async def fits() -> list[dict[str, Any]]:
    """Every fit written, newest first"""
    database = _database()

    @database.read_transaction
    async def read(tx: Any) -> list[dict[str, Any]]:
        return [record.data() async for record in await tx.run(FITS_QUERY)]

    return await read()


async def in_use_in(tx: Any) -> dict[str, Any] | None:
    """In an open transaction, one statement: the fit in use (the newest of those marked), or None"""
    record = await (await tx.run(IN_USE_QUERY)).single()
    return record.data() if record else None


async def in_use() -> dict[str, Any] | None:
    """The fit in use, in a read transaction of its own"""
    database = _database()

    @database.read_transaction
    async def read(tx: Any) -> dict[str, Any] | None:
        return await in_use_in(tx)

    return await read()


def today() -> str:
    """What makes fits comparable, today (`learning.signature` of the compared classes' rules)"""
    from pangloss_compare.rules import rules

    return learning.signature(rules())


def for_route(
    fit: Mapping[str, Any] | None, signature: str, *, logged_in: bool = True
) -> tuple[dict[str, dict[str, float]] | None, dict[str, Any] | None]:
    """What the route makes of the fit in use: the models `maths.verdict(fitted=...)` takes (those that passed the
    check), and what the answer says of it (`model`). Both None where no fit is in use, or the one in use is of
    another signature than `signature` (its numbers would not mean what they meant). `logged_in`: whether the reader
    is; to one who is not, `model` gives the fit's id and when it was made, and its counts as null (a fit is of every
    judgement, those the reader may not see too)"""
    if fit is None or fit.get("signature") != signature:
        return None, None
    fitted = {
        model: learning.as_fitted(Model.from_json(fit[NAMES[model]]))
        for model in learning.MODELS
        if fit.get(f"{NAMES[model]}_used") and fit.get(NAMES[model])
    }
    if not fitted:
        return None, None
    at = _when(fit["at"])
    said: dict[str, Any] = {
        "id": fit["id"],
        "at": None if at is None else at.isoformat(),
        # (of the models in use: not those of one that is fitted and not used)
        "judgements": sum(
            int(fit.get(f"{NAMES[model]}_examples") or 0) for model in fitted
        ),
        "oneEvent": maths.ONE_EVENT in fitted,
        "answers": maths.ANSWERS_IT in fitted,
    }
    if not logged_in:
        said.update(dict.fromkeys(COUNTED))
    return fitted, said


# (what the route's `model` says of the judgements a fit is of: only to a reader who is logged in)
COUNTED = ("judgements", "oneEvent", "answers")


def _unchanged(
    newest: Mapping[str, Any] | None, signature: str, found: learning.Examples
) -> bool:
    """Whether nothing is new since the newest fit written: of today's signature; of as many judgements read, the
    newest of them made at the same time (a judgement is never edited, `models.py`: one added or deleted changes
    the count or the newest); as many examples of each model and left out for each reason; and the examples
    themselves the same (`learning.digest`: what each is worked out of is the statements as they are now, so an
    edit of a cited statement, or a merge of two entities, that changes an example's features or whether it is
    one, is something new though no judgement is)"""
    return (
        newest is not None
        and newest.get("signature") == signature
        and int(newest.get("judgements") or 0) == found.judgements
        and _when(newest.get("latest")) == found.latest
        and all(
            int(newest.get(f"{NAMES[model]}_examples") or 0)
            == len(found.by_model[model])
            for model in learning.MODELS
        )
        and json.loads(newest.get("left_out") or "{}") == dict(found.left_out)
        and newest.get("examples_digest") == learning.digest(found)
    )


def _would_lose(
    current: Mapping[str, Any] | None, signature: str, learnt: Learnt
) -> tuple[str, ...]:
    """The models the fit in use (of today's signature: another is used by nothing) has in use, and the new fit did
    not pass"""
    if current is None or current.get("signature") != signature:
        return ()
    return tuple(
        model
        for model in learning.MODELS
        if current.get(f"{NAMES[model]}_used") and not learnt.used(model)
    )


async def learn(*, dry_run: bool = False) -> Learnt:
    """Read every judgement (as an admin), make the examples of both models (`learning.examples`), and unless no
    judgement is an example of either, or nothing is new since the newest fit written (`_unchanged`; a dry run goes
    on, and says so), fit and compare both (`learning.fit_both`), write the fit (not in a dry run) and put it in use
    if one of its models passes the check (`why_not`) and it loses no model the fit in use has (`_would_lose`)"""
    from pangloss_compare.rules import rules

    database = _database()

    @database.read_transaction
    async def read(tx: Any) -> list[learning.Judged]:
        return await judged_in(tx)

    judged = await read()
    known = rules()
    found = learning.examples(judged, known)
    learnt = Learnt(
        dry_run=dry_run,
        judgements=found.judgements,
        left_out=dict(found.left_out),
        examples={model: len(found.by_model[model]) for model in learning.MODELS},
    )
    if not found.taken:
        return learnt
    signature = learning.signature(known)
    written = await fits()
    if _unchanged(written[0] if written else None, signature, found):
        learnt.unchanged = written[0]
        if not dry_run:
            return learnt
    now = _now()
    margin = settings.learn_margin()
    learnt.fits = learning.fit_both(found, fitted_at=now.isoformat())
    for model in learning.MODELS:
        fitted = learnt.fits.of(model)
        learnt.why_not[model] = why_not(
            fitted.examples,
            fitted.model is not None,
            _why_of(fitted),
            fitted.compared,
            margin,
        )
    passed = any(learnt.used(model) for model in learning.MODELS)
    current = next((f for f in written if f["in_use"]), None)
    if passed and (lost := _would_lose(current, signature, learnt)):
        assert current is not None
        learnt.lost = lost
        learnt.not_in_use = (
            f"the fit in use, {current['id']}, has {' and '.join(TITLES[m] for m in lost)} in use, which this one "
            "has not (put in use, it would leave the verdicts of that kind to the hand-set score)"
        )
    learnt.in_use = passed and learnt.not_in_use is None
    if dry_run:
        learnt.in_use = False
        return learnt

    learnt.id = str(uuid.uuid4())
    properties: dict[str, Any] = {
        "id": learnt.id,
        "at": now,
        "signature": signature,
        "judgements": found.judgements,
        "latest": found.latest,
        "left_out": json.dumps(found.left_out, sort_keys=True),
        "examples_digest": learning.digest(found),
        "compared": json.dumps(
            {
                NAMES[m]: _compared_json(learnt.fits.of(m).compared)
                for m in learning.MODELS
            },
            sort_keys=True,
        ),
        "margin": margin,
        "in_use": learnt.in_use,
        "not_in_use": learnt.not_in_use,
    }
    for model in learning.MODELS:
        fitted, name = learnt.fits.of(model), NAMES[model]
        properties[name] = fitted.model.to_json() if fitted.model else None
        properties[f"{name}_examples"] = fitted.examples
        properties[f"{name}_why"] = _why_of(fitted)
        properties[f"{name}_used"] = learnt.used(model)

    @database.write_transaction
    async def write(tx: Any) -> None:
        if properties["in_use"]:
            await (await tx.run(UNUSE_QUERY)).consume()
        await (await tx.run(WRITE_QUERY, **properties)).consume()

    await write()
    if learnt.in_use:
        await _settle()
    if not learnt.in_use:
        # (a fit marked in use that is of another signature is used by nothing: not said to stay in use)
        kept = current if current is not None and current["signature"] == signature else None  # fmt: skip
        learnt.kept_in_use = kept["id"] if kept else None
    return learnt


def _checked(found: Mapping[str, Any]) -> dict[str, str | None]:
    """Why each model of a stored fit may not be used, by today's `COMPARE_LEARN_FROM` and `COMPARE_LEARN_MARGIN`
    (None: it may)"""
    compared = json.loads(found.get("compared") or "{}")
    checked = {}
    for model in learning.MODELS:
        name = NAMES[model]
        of = compared.get(name)
        checked[model] = why_not(
            int(found.get(f"{name}_examples") or 0),
            found.get(name) is not None,
            found.get(f"{name}_why"),
            None if not of else CallsCompared(**of),
        )
    return checked


async def use(id: str | None) -> dict[str, Any] | None:
    """Put the fit `id` in use, and no other, through the check (`why_not`, of what it stored, by today's
    `COMPARE_LEARN_FROM` and `COMPARE_LEARN_MARGIN`; which of its models may be used is written again) and only if its
    signature is today's; `Refused` otherwise, and nothing changes. A fit that was not put in use because it lacked a
    model of the one in use then (`not_in_use`) may be. None: no fit in use. Gives the fit put in use"""
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
    if found["signature"] != today():
        raise Refused(
            f"The fit {id} is of other features, hand-set weights or rules than today's: its numbers would not mean "
            "what they meant"
        )
    checked = _checked(found)
    if all(why is not None for why in checked.values()):
        raise Refused(
            f"The fit {id} cannot be put in use: "
            + "; ".join(f"{TITLES[m]}: {checked[m]}" for m in learning.MODELS)
        )
    used = {f"{NAMES[m]}_used": checked[m] is None for m in learning.MODELS}

    @database.write_transaction
    async def put(tx: Any) -> None:
        await (await tx.run(UNUSE_QUERY)).consume()
        await (await tx.run(USE_QUERY, id=id, **used)).consume()

    await put()
    await _settle()
    return {**found, **used, "in_use": True}


async def _settle() -> None:
    """At most one fit marked in use, the newest of those marked (`SETTLE_QUERY`)"""
    database = _database()

    @database.write_transaction
    async def settle(tx: Any) -> None:
        await (await tx.run(SETTLE_QUERY)).consume()

    await settle()


NEWEST_QUERY = f"""
MATCH (m:{MODEL})
RETURN {RETURNED}
ORDER BY at DESC, id
LIMIT 1
"""


async def status() -> dict[str, Any]:
    """The fit in use (or None), whether it is of today's signature, why each of its models is or is not used by
    today's check (`checked`); the newest fit written where it is not the one in use (`newest`); and how many
    judgements there are (as an admin sees them), with `COMPARE_LEARN_FROM` and `COMPARE_LEARN_MARGIN`. One read
    transaction, three statements"""
    from pangloss_core import backend
    from pangloss_models import ModelRegistry

    database = _database()

    @database.read_transaction
    async def read(tx: Any) -> tuple[dict[str, Any] | None, dict[str, Any] | None, int]:  # fmt: skip
        fit = await in_use_in(tx)
        record = await (await tx.run(NEWEST_QUERY)).single()
        newest = record.data() if record else None
        if BASE not in ModelRegistry._model_dict:
            return fit, newest, 0
        record = await (
            await tx.run(count_query(backend.current().fragments), see_unpublished=True)
        ).single()
        return fit, newest, int(record["n"]) if record else 0

    fit, newest, count = await read()
    return {
        "fit": fit,
        "of_today": fit is not None and fit["signature"] == today(),
        "checked": _checked(fit) if fit is not None else {},
        "newest": newest
        if newest is not None and (fit is None or newest["id"] != fit["id"])
        else None,
        "judgements": count,
        "learn_from": settings.learn_from(),
        "margin": settings.learn_margin(),
    }


def _compared_said(fit: Mapping[str, Any], model: str) -> str:
    """What a stored fit's comparison of one model found, or why there is none"""
    name = NAMES[model]
    of = json.loads(fit.get("compared") or "{}").get(name)
    if fit.get(name) is None:
        return f"not fitted ({fit.get(f'{name}_why')})"
    if not of:
        return f"not compared ({fit.get(f'{name}_why')})"
    found = CallsCompared(**of)
    return (
        f"of {_many(int(fit.get(f'{name}_examples') or 0), 'judgement')}; of {found.decisions:,} held out, called "
        f"rightly in {found.model:,} by the fit, {found.baseline:,} by the hand-set score, {found.differ:,} called "
        "differently"
    )


def status_lines(found: Mapping[str, Any]) -> list[str]:
    """What `pangloss compare status` prints"""
    count, least = found["judgements"], found["learn_from"]
    lines = [
        f"judgements: {count:,}",
        f"COMPARE_LEARN_FROM: {least:,} (judgements of one kind of pair, for a fitted model to be used)"
        + (f": at least {least - count:,} more needed" if count < least else ""),
        f"COMPARE_LEARN_MARGIN: {found['margin']:g} (how much worse than the hand-set score a fit may be, for chance, "
        "times the square root of the judgements held out the two call differently)",
    ]
    fit = found["fit"]
    if fit is None:
        lines.append(NO_FIT)
    else:
        used = [TITLES[m].lower() for m in learning.MODELS if fit.get(f"{NAMES[m]}_used")]  # fmt: skip
        lines.append(
            f"in use: the fit {fit['id']} of {_said_when(fit['at'])}, for {' and '.join(used) or 'nothing'}"
        )
        if not found["of_today"]:
            lines.append(
                "it is of other features, hand-set weights or rules than today's: nothing uses it"
            )
        for model in learning.MODELS:
            name = NAMES[model]
            why = found["checked"].get(model)
            state = "used" if fit.get(f"{name}_used") else "not used"
            today_said = (
                "it passes today's check"
                if why is None
                else f"by today's check it would not be used: {why}"
            )
            lines.append(f"  {TITLES[model]}: {state}; {_compared_said(fit, model)}; {today_said}")  # fmt: skip
    newest = found.get("newest")
    if newest is not None:
        why = newest.get("not_in_use") or (
            "none of its models passed the check"
            if not any(newest.get(f"{NAMES[m]}_used") for m in learning.MODELS)
            else "it was put out of use since (`pangloss compare learn --use`)"
        )
        lines.append(
            f"the newest fit, {newest['id']} of {_said_when(newest['at'])}, is not in use: {why}"
        )
    return lines
