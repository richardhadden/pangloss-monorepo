"""Learning from judgements: every judgement read, made examples of, fitted, compared and written as a fit, used only
past a check (implementation_docs/spaces-and-comparison-plan.md, step 6.6; implementation_docs/compare.md, "Learning
from judgements"). What the examples are is `learning.py`'s, the maths `pangloss_learn`'s; this reads and writes. The
same design as `pangloss_reconcile.fits`.

    (:PGCompareModel {id, at, signature, judgements, latest, left_out, one_event, answers, one_event_examples,
                      answers_examples, one_event_why, answers_why, compared, one_event_used, answers_used, in_use})

one for each fit written, **none ever deleted**: what makes fits comparable (`signature`, `learning.signature`), how
many judgements were read and when the newest one taken was made (`latest`), those left out by why (`left_out`,
JSON), each of the two models (`one_event`: one event or two; `answers`: does this answer that) as
`pangloss_learn.Model.to_json()` or null, how many judgements it is of, and why it was not fitted or, fitted, not
compared (`*_why`), what each comparison found (`compared`, JSON: `{"one_event": {decisions, model, baseline} | null,
"answers": ...}`), whether each model may be used (`one_event_used`, `answers_used`: it passed the check), and
`in_use`: **at most one fit is in use**, set and unset in one write transaction. A fit is in use when one of its
models or both passed; the route uses those of its models that did, and the hand-set weights for the other.

The check, of each model by itself: it is of `COMPARE_LEARN_FROM` judgements or more, it was fitted and compared,
and on the judgements held out it called the judgement rightly as often as the hand-set score or more. A fit none of
whose models passes is still written, not in use, and the fit in use before stays in use. `use` puts an earlier fit in
use through the same check (its stored counts and comparisons, today's `COMPARE_LEARN_FROM`, and its signature
today's), or none.

`learn` is what `pangloss compare learn` and the admin job `compare_learn` run; `Learnt.lines()` is what both print.
`in_use_in` is what the route reads (`compare.compare`), and `for_route` what it makes of it."""

import dataclasses
import datetime
import json
import uuid
from collections.abc import Mapping
from typing import Any

from pangloss_learn import Compared, Model

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
    "one_event",
    "answers",
    "one_event_examples",
    "answers_examples",
    "one_event_why",
    "answers_why",
    "compared",
    "one_event_used",
    "answers_used",
    "in_use",
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


def why_not(examples: int, model: bool, why: str | None, compared: Compared | None) -> str | None:  # fmt: skip
    """Why one model may not be used (the check), or None: each condition that failed. `why`: why it was not fitted,
    or, fitted, not compared"""
    reasons = []
    least = settings.learn_from()
    if examples < least:
        reasons.append(
            f"it is of {_many(examples, 'judgement')}, fewer than COMPARE_LEARN_FROM ({least:,})"
        )
    if not model:
        reasons.append(f"it could not be fitted ({why})")
    elif compared is None:
        reasons.append(f"it could not be compared ({why})")
    elif not compared.no_worse:
        reasons.append(
            f"it called {compared.model:,} of {compared.decisions:,} judgements held out rightly, fewer than the "
            f"hand-set score ({compared.baseline:,})"
        )
    return "; ".join(reasons) or None


def _why_of(fitted: Fitted) -> str | None:
    return fitted.why if fitted.model is None else fitted.compared_why


@dataclasses.dataclass
class Learnt:
    """What `learn` did, or would do (`dry_run`): how many judgements were read, those left out by why, how many
    were examples of each model; then either nothing was fitted (no judgement is an example of either model), or both
    models were (`fits`), each used or not and why not (`why_not`, by `maths.ONE_EVENT` and `maths.ANSWERS_IT`), the
    fit written (`id`; in a dry run, none), whether it is in use, and the fit that stays in use when it is not"""

    dry_run: bool
    judgements: int = 0
    left_out: dict[str, int] = dataclasses.field(default_factory=dict)
    examples: dict[str, int] = dataclasses.field(default_factory=dict)
    fits: learning.Fits | None = None
    why_not: dict[str, str | None] = dataclasses.field(default_factory=dict)
    id: str | None = None
    in_use: bool = False
    kept_in_use: str | None = None

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
        if self.fits is None:
            lines.append(
                "Nothing fitted and nothing written: no judgement is an example of either model"
            )
            return lines
        for model in learning.MODELS:
            lines.append(_said(model, self.fits.of(model), self.why_not.get(model)))
        used = [TITLES[m].lower() for m in learning.MODELS if self.used(m)]
        if self.dry_run:
            lines.append(
                "Nothing written (a dry run): the fit would be "
                + (
                    f"put in use, for {' and '.join(used)}"
                    if used
                    else "written, not in use"
                )
            )
            return lines
        if self.in_use:
            lines.append(f"Written: the fit {self.id}, in use for {' and '.join(used)}")
        else:
            lines.append(f"Written: the fit {self.id}, not in use")
            lines.append(
                f"The fit in use stays in use: {self.kept_in_use}"
                if self.kept_in_use
                else NO_FIT
            )
        return lines


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
            f"rightly in {found.model:,} by the fit, {found.baseline:,} by the hand-set score"
        )
    return f"{said}; {'used' if why is None else f'not used: {why}'}"


def _compared_json(found: Compared | None) -> dict[str, int] | None:
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
    fit: Mapping[str, Any] | None, signature: str
) -> tuple[dict[str, dict[str, float]] | None, dict[str, Any] | None]:
    """What the route makes of the fit in use: the models `maths.verdict(fitted=...)` takes (those that passed the
    check), and what the answer says of it (`model`). Both None where no fit is in use, or the one in use is of
    another signature than `signature` (its numbers would not mean what they meant)"""
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
    return fitted, {
        "id": fit["id"],
        "at": None if at is None else at.isoformat(),
        # (of the models in use: not those of one that is fitted and not used)
        "judgements": sum(
            int(fit.get(f"{NAMES[model]}_examples") or 0) for model in fitted
        ),
        "oneEvent": maths.ONE_EVENT in fitted,
        "answers": maths.ANSWERS_IT in fitted,
    }


async def learn(*, dry_run: bool = False) -> Learnt:
    """Read every judgement (as an admin), make the examples of both models (`learning.examples`), and unless no
    judgement is an example of either, fit and compare both (`learning.fit_both`), write the fit (not in a dry run)
    and put it in use if one of its models passes the check (`why_not`)"""
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
    now = _now()
    learnt.fits = learning.fit_both(found, fitted_at=now.isoformat())
    for model in learning.MODELS:
        fitted = learnt.fits.of(model)
        learnt.why_not[model] = why_not(
            fitted.examples, fitted.model is not None, _why_of(fitted), fitted.compared
        )
    learnt.in_use = any(learnt.used(model) for model in learning.MODELS)
    if dry_run:
        learnt.in_use = False
        return learnt

    signature = learning.signature(known)
    learnt.id = str(uuid.uuid4())
    properties: dict[str, Any] = {
        "id": learnt.id,
        "at": now,
        "signature": signature,
        "judgements": found.judgements,
        "latest": found.latest,
        "left_out": json.dumps(found.left_out, sort_keys=True),
        "compared": json.dumps(
            {
                NAMES[m]: _compared_json(learnt.fits.of(m).compared)
                for m in learning.MODELS
            },
            sort_keys=True,
        ),
        "in_use": learnt.in_use,
    }
    for model in learning.MODELS:
        fitted, name = learnt.fits.of(model), NAMES[model]
        properties[name] = fitted.model.to_json() if fitted.model else None
        properties[f"{name}_examples"] = fitted.examples
        properties[f"{name}_why"] = _why_of(fitted)
        properties[f"{name}_used"] = learnt.used(model)

    written = await fits()

    @database.write_transaction
    async def write(tx: Any) -> None:
        if properties["in_use"]:
            await (await tx.run(UNUSE_QUERY)).consume()
        await (await tx.run(WRITE_QUERY, **properties)).consume()

    await write()
    if not learnt.in_use:
        # (a fit marked in use that is of another signature is used by nothing: not said to stay in use)
        current = next(
            (f for f in written if f["in_use"] and f["signature"] == signature), None
        )
        learnt.kept_in_use = current["id"] if current else None
    return learnt


def _checked(found: Mapping[str, Any]) -> dict[str, str | None]:
    """Why each model of a stored fit may not be used, by today's `COMPARE_LEARN_FROM` (None: it may)"""
    compared = json.loads(found.get("compared") or "{}")
    checked = {}
    for model in learning.MODELS:
        name = NAMES[model]
        of = compared.get(name)
        checked[model] = why_not(
            int(found.get(f"{name}_examples") or 0),
            found.get(name) is not None,
            found.get(f"{name}_why"),
            None if not of else Compared(**of),
        )
    return checked


async def use(id: str | None) -> dict[str, Any] | None:
    """Put the fit `id` in use, and no other, through the check (`why_not`, of what it stored, by today's
    `COMPARE_LEARN_FROM`; which of its models may be used is written again) and only if its signature is today's;
    `Refused` otherwise, and nothing changes. None: no fit in use. Gives the fit put in use"""
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
    return {**found, **used, "in_use": True}


async def status() -> dict[str, Any]:
    """The fit in use (or None), whether it is of today's signature, and how many judgements there are (as an
    admin sees them), with `COMPARE_LEARN_FROM`. One read transaction, two statements"""
    from pangloss_core import backend
    from pangloss_models import ModelRegistry

    database = _database()

    @database.read_transaction
    async def read(tx: Any) -> tuple[dict[str, Any] | None, int]:
        fit = await in_use_in(tx)
        if BASE not in ModelRegistry._model_dict:
            return fit, 0
        record = await (
            await tx.run(count_query(backend.current().fragments), see_unpublished=True)
        ).single()
        return fit, int(record["n"]) if record else 0

    fit, count = await read()
    return {
        "fit": fit,
        "of_today": fit is not None and fit["signature"] == today(),
        "judgements": count,
        "learn_from": settings.learn_from(),
    }


def status_lines(found: Mapping[str, Any]) -> list[str]:
    """What `pangloss compare status` prints"""
    count, least = found["judgements"], found["learn_from"]
    lines = [
        f"judgements: {count:,}",
        f"COMPARE_LEARN_FROM: {least:,} (judgements of one kind of pair, for a fitted model to be used)"
        + (f": at least {least - count:,} more needed" if count < least else ""),
    ]
    fit = found["fit"]
    if fit is None:
        lines.append(NO_FIT)
        return lines
    used = [TITLES[m].lower() for m in learning.MODELS if fit.get(f"{NAMES[m]}_used")]
    lines.append(
        f"in use: the fit {fit['id']} of {_said_when(fit['at'])}, for {' and '.join(used) or 'nothing'}"
    )
    if not found["of_today"]:
        lines.append(
            "it is of other features, hand-set weights or rules than today's: nothing uses it"
        )
    return lines
