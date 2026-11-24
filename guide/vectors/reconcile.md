# Who an unidentified person may be

A source names "Jon Smyth" and you do not yet know which Jon Smyth. With `pangloss-review` that is an
`Unreconciled` in the person's place ([review](../review/README.md)). With `pangloss-reconcile`, Pangloss
suggests who it may be: the people whose **names** are near, ranked also by the **company they keep** (the
other people, places and groups the document names), and by how many of those other documents name **with
them**. A namesake who was at the same place with the same people comes before one who was not.

It suggests **candidates**. A person chooses; nothing is reconciled or merged by it. What it does keep is what it
suggested for a saved mention, and which of them the person then chose (below, "What it keeps"), so that it can
later learn from those decisions.

The reference is [reconciliation](../../implementation_docs/reconcile.md).

## 1. Install it

```python
INSTALLED_APPS = [
    "pangloss_memgraph",
    ...
    "pangloss_review",       # Unreconciled, and the dialog that reconciles
    "pangloss_vectors",
    "pangloss_fastrp",       # the graph part: the company
    "pangloss_names",        # the name part
    "pangloss_reconcile",
    "my_app",
    "pangloss_interface",
]

VECTORS_PROFILES = {"who": {"name": 1, "graph": 0.25}}
RECONCILE_PROFILE = "who"
```

`RECONCILE_PROFILE` names the profile the candidates are found and scored by. It should weigh the name and a
little of the graph. On a made-up prosopography where many people share a name, with 7,000 people the name
alone put the right person first 71 times in 100 and the name with the graph at 0.25, 78; with 38,000 people,
58 and 65. The right person was among the first five 97 to 99 times in 100 with the graph. Much more of the
graph is worse (at equal weights, 16 to 30 in 100): the company finds the right family, not the person. Counting
also the people, places and groups of the document that other documents name with a candidate (which is done
unless you turn it off, below) puts the right person first 86 or 87 times in 100 with 38,000 people, and among the
first five 99. It counts by how near the name is: it tells namesakes apart, and does not make someone of another
name a candidate because they keep the same company. Measured on that made-up world:

| | Right first | Among five | Of names several people have, first |
|---|---|---|---|
| name 1, graph 0.25 | 66.5% | 95.5% | 53.9% |
| + shared at 0.75 (the first form, n / (n + 2) for everyone alike) | 82.0% | 99.5% | 76.5% |
| + name's cosine × n/(n+2) at 1 | 85.5% | 99.5% | 79.1% |
| **the same at 1.5** (the default) | **86.5%** | 99.5% | 82.6% |
| at 2 / 3 / 4 | 86.5% / 86.0% / 85.0% | 99.5% | 82.6% / 81.7% / 80.9% |

If you leave the setting out and two profiles could serve, the server says so when it starts and asks you to name
one.

Then, as after any change of the profiles ([similar items](README.md)):

```sh
pangloss makemigrations && pangloss migrate
pangloss vectors rebuild
```

## 2. In the reconcile dialog

Open the reconcile dialog of a mention (its spanner, in the form of its document or on the page of
reconciliations). Above the box where you search for the entity there is now **Suggested**: up to five people,
best first, each with

- its chip (a link to its page),
- a bar and a figure: the score, from 0 to 1, made of three things: how near the name is, how near the company,
  and how many of this document's people, places and groups other documents name with the candidate, counted by
  how near the name is (hover the
  bar: *name*, *graph* and *named with*, each from 0 to 1),
- **Choose**, which makes it the one the mention is reconciled with, as if you had found it in the box,
- and, under it, *also named with*: the people, places and groups of this document that other documents name
  together with that candidate, which is why it is suggested. A number beside one says in how many documents.

Nothing is suggested when nobody scores 0.15 or more (`RECONCILE_LEAST_SCORE`), and the box works as before. The mention has to be
saved first (the dialog says so): the suggestions are of the document as it is stored.

The score is a help in ordering, not a likelihood: 0.9 does not mean nine in ten. And the right answer may be
"none of these": the person may not be in the database yet.

Once the package has learnt from enough of your decisions (section 6: `pangloss reconcile learn` has put a fit in
use), a quiet line under **Suggested** may say *Probably not in the database yet*: a model fitted on those decisions
says that the person meant is more likely than not (above `RECONCILE_NEW_ABOVE`, 0.5) **none of those suggested**:
someone new, or someone who is not among them. Hover it for the likelihood ("82% likely to be none of these"). It
hides nothing and changes no order: the suggestions are still there, best first by the score; look at them, and if
none is right, find the person in the box or make them with +. With no fit in use, or one made with other vectors or
weights than today's, there is no such line.

## 3. From a script or a toolchain

Two routes, both for a user who is logged in.

**Before you save a document**, send the payload you would create it with:

```sh
curl -X POST "$SERVER/api/reconcile/candidates?limit=5" -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" -d '{
    "type": "Activity", "label": "Lunch at the Drones",
    "carriedOutBy": {"type": "Unreconciled", "unreconciledType": "Person", "label": "Jon Smyth"},
    "at": {"type": "Place", "id": "…"}
  }'
```

It is checked as a create is, and refused as a create would be (a reference that does not exist, a field you
may not set), and **nothing is written**. The answer lists each unidentified person of the payload with its
candidates:

```json
{"status": "ok", "profile": "who", "unknowns": [
  {"id": "…", "type": "Person", "label": "Jon Smyth",
   "candidates": [
     {"id": "…", "type": "Person", "label": "John Smith",
      "score": 0.6, "scores": {"name": 1.0, "graph": 0.57, "shared": 0.33},
      "shared": [{"id": "…", "type": "Place", "label": "The Drones", "documents": 2}]}]}]}
```

**For a mention already saved**, by the id of the `Unreconciled`:

```sh
curl "$SERVER/api/reconcile/candidates/$MENTION_ID?limit=5" -H "Authorization: Bearer $TOKEN"
```

`status` is `"pending"` while the vectors have never been built (the lists are empty: run
`pangloss vectors rebuild`).

Things to know:

- A payload may hold at most 20 unidentified people (`RECONCILE_MOST_UNKNOWNS`); each costs a search.
- A request takes one to two seconds (measured: 1.3 s with 7,000 people, 2.2 s with 38,000, on Memgraph): it
  reads every person's vector, on purpose, so that namesakes are not missed.
- The same document asked before and after it is saved gives the same candidates in the same order, with scores
  that may differ in the second decimal place.
- A candidate is always of the class the mention says (`unreconciledType`) or one below it.

## 4. Settings

| Setting | Default | |
|---|---|---|
| `RECONCILE_PROFILE` | none | The profile to find and score by |
| `RECONCILE_WEIGHTS` | `{}` | Other weights for the score than the profile's, by part: `{"name": 1, "graph": 0.1}`; and of `shared`, the entities named with the candidate elsewhere (counted by how near the name is), 1.5 unless you say (`{"shared": 0}` leaves them out of the score) |
| `RECONCILE_FETCH` | 50 | How many candidates are gathered by the name, and by the company, before they are scored together |
| `RECONCILE_MOST_UNKNOWNS` | 20 | The most unidentified people in one payload |
| `RECONCILE_REASONS` | 5 | The most "also named with" a candidate; 0 hides them (they still count in the score) |
| `RECONCILE_LEAST_SCORE` | 0.15 | A candidate scoring less is not suggested, by the dialog or by either route |
| `RECONCILE_KEEP_DECISIONS` | True | Keep what was suggested for a saved mention, and what was chosen of it (below). `False` keeps nothing |
| `RECONCILE_SHOWN_FOR` | 30 | In minutes: a mention reconciled longer than this after its suggestions were shown is not kept as a decision |
| `RECONCILE_LEARN_FROM` | 100 | The fewest decisions a fit is made of before it is put in use (below) |
| `RECONCILE_LEARN_FROM_SUGGESTIONS` | True | Learn from the toolchain's suggestions that people confirmed, beside the dialog's decisions (section 5). `False` leaves them out (they are still counted) |
| `RECONCILE_NEW_ABOVE` | 0.5 | With a fit in use, the likelihood that the person meant is none of those suggested above which the dialog says *Probably not in the database yet*. From 0 to 1 |

Pangloss's own toolchain, which writes a suggestion in the place of a mention in the background, is being built
(not yet to be relied on: [reconciliation](../../implementation_docs/reconcile.md), "The worker that suggests"). Its
settings:

| Setting | Default | |
|---|---|---|
| `RECONCILE_SUGGEST_ON_SAVE` | False | Whether a save leaves a document with a mention in it for the toolchain when the save does not say (`?suggest=true` or `?suggest=false`, or `save(instructions={"suggest": True})`, says it either way) |
| `RECONCILE_SUGGEST_AS` | `IdentificationByToolchainFromText` | The kind of identification it writes |
| `RECONCILE_TOOLCHAIN` | `pangloss-reconcile` | The user it writes as: a toolchain, made when it is not there |
| `RECONCILE_WORKER_IN_SERVER` | True | Whether the server runs it; `False` to run it apart, `pangloss reconcile worker` |
| `RECONCILE_SUGGEST_WITH` | none | A function of yours that may replace what it suggests: `"myproject.judges:judge"` (below, "A judge of your own") |
| `RECONCILE_SUGGEST_TIMEOUT` | 60 | In seconds, how long your function is given for one mention |

### Turning it on

- **For every save**: `RECONCILE_SUGGEST_ON_SAVE = True`. Each save of a document that can hold a mention leaves it
  for the toolchain, unless the save says otherwise.
- **A pipeline that loads documents** and does not want suggestions made in them says so on each write:
  `POST /api/Factoid?suggest=false` (or `save(instructions={"suggest": False})`). `suggest=false` also takes off a
  document's place in the queue, if it had one. `?suggest=true` asks for it on that one save, the setting off.
- **What is already stored** (after a bulk load, which leaves nothing for it, or when the setting is first turned
  on): `pangloss reconcile suggest`, or the admin job *Suggest identifications in stored documents* on `/admin`, or
  `POST /api/reconcile/suggest` as an admin. It leaves for the toolchain every unpublished document that holds a
  mention and is not already waiting (`--class NAME`: only of a class and those below it). A mention the toolchain
  tried and could suggest nobody for is not asked about again until something that decides it changes; `--again`
  (`{"again": true}`, the job's option) asks again for those too.
- **How far it has got**: `pangloss reconcile status` (or `GET /api/reconcile/suggest`): the documents waiting, the
  mentions tried and left, the suggestions not yet confirmed.

### A judge of your own

If you would rather decide yourself who a mention is, for instance by looking more up about each candidate and
asking a language model, you can put that **inside** the toolchain: it finds the candidates and makes its own
decision, and then asks your function, which may keep that decision, replace it, or say to leave the mention. Name
it in the settings:

```python
RECONCILE_SUGGEST_WITH = "myproject.judges:judge"
RECONCILE_SUGGEST_TIMEOUT = 60      # seconds for one mention
```

It is checked when the server starts (the module has to import, and the name has to be a function). It is called once
for each mention the toolchain would write a suggestion for (not for one in a place where your models' checks refuse
any identification: that one goes on as with no judge), with one argument, an `Asked`: plain data, made for that
call. `asked.stand_in` (`label`, `stood_for`, the class it stands for, `uris`, `place`, the field names from the
document down to it, `held_by`); `asked.document`, the whole document as Python names its fields; `asked.candidates`,
those the reconcile dialog would show (`id`, `type`, `label`, `score`, `scores` by part, `shared`, the people and
places it is named with elsewhere); `asked.decision`, what the toolchain decided (`alternatives` with their
`percent`, and the `reason`); and `asked.takes`, the `shape` of the place (`"alternatives"`, or `"one"` person only)
and the `classes` it may name. It answers one of:

- `None` or `Unchanged()`: the toolchain's decision stands;
- `Leave()`: suggest nobody for this mention (it is not asked again until something changes, as when the toolchain
  finds nobody);
- `Suggest(alternatives=[({"type": "Person", "id": "…"}, weight), ...], fields={...})`: your own alternatives, with
  weights above 0, which **need not be among the candidates**; they are made percentages (where the place takes one
  person, the heaviest alone). `fields` fills further fields of the suggestion, if you name a class of your own with
  more fields in `RECONCILE_SUGGEST_AS` (a `note`, say). A `Suggest` of the same people at the same percentages as
  the toolchain decided, with no `fields`, is its decision, as `Unchanged()` is.

A worked judge, which reads each candidate through your models and asks a language model. `ask_model` is yours to
write: it sends a prompt to whichever model you use and gives back its text.

```python
# myproject/judges.py
import asyncio
import json
from uuid import UUID

from pangloss_reconcile import Asked, Leave, Suggest, Unchanged

from myproject.models import Person


def ask_model(prompt: str) -> str:
    """Your own call to a language model (its client, its key, its limits): the text it answers"""
    raise NotImplementedError


async def judge(asked: Asked):
    if not asked.candidates:
        return Unchanged()
    about = []
    for candidate in asked.candidates:
        person = await Person.get(UUID(candidate["id"]))
        about.append({
            "id": candidate["id"],
            "name": candidate["label"],
            "score": candidate["score"],
            "named with": [shared["label"] for shared in candidate["shared"]],
            "record": person.model_dump(mode="json") if person else None,
        })
    prompt = (
        f"A source names {asked.stand_in['label']!r} in this document:\n{json.dumps(asked.document)}\n"
        f"Who of these is it?\n{json.dumps(about)}\n"
        'Answer JSON: {"none": true} if none of them, or {"ids": {"<id>": <how likely, 0 to 1>, ...}}'
    )
    # (`ask_model` is not async: run in a thread, so the toolchain goes on while the model answers)
    answer = json.loads(await asyncio.to_thread(ask_model, prompt))
    if answer.get("none"):
        return Leave()
    chosen = [
        ({"type": "Person", "id": id}, weight)
        for id, weight in answer.get("ids", {}).items()
        if weight > 0
    ]
    return Suggest(chosen) if chosen else Unchanged()
```

Things to know:

- **Your function runs in the toolchain's process, as the toolchain's user**, who sees what is not yet published, and
  **not as an admin**. What it reads, and what it sends to a model's API (the document, the names, the records), is
  **your project's own decision and responsibility**: Pangloss sends nothing anywhere itself.
- What it is given is a copy: changing it changes nothing the toolchain checks your answer against.
- A function that is not `async` is run in one of the toolchain's own threads (four of them, not the server's); one
  that takes longer than `RECONCILE_SUGGEST_TIMEOUT` is given up on (a thread cannot be stopped: it runs on, what it
  answers is not used, and it keeps its thread until it returns; while all four are kept so, each mention fails at
  once).
- An `async` function must not **block**: a slow call inside `async def` that is not awaited (a sync client, a
  `time.sleep`) stops the timeout and the toolchain's hold on its work with it. Await it, or write the function as a
  plain `def`. An `async` function that catches its own cancellation cannot be stopped at the timeout.
- If it fails for a mention (it raises, takes too long, answers something that is not one of the four, or suggests
  what the save would refuse: someone who is not there, is deleted, was merged into someone else, or that the place
  cannot take, a field the class does not have, a value your models' checks refuse), **that mention is left as it
  is**, said in the server's log, and asked again at the next save or `pangloss reconcile suggest`; the toolchain's
  own decision is **not** written instead. The document's other mentions are written as usual. (Two answers each
  fine alone can together be refused by a check of the whole document: then the document is not written, as when the
  toolchain's own suggestions are refused.)
- Before your judge's own suggestion is written, it is tried as the save would try it, your models' checks too
  (validators and before-hooks, as the save runs them): they run once more than the save runs them, in a copy of
  the toolchain's context, so they should read and refuse, never write.
- The suggestion says it was made with your judge (`toolchain_version`: `profile who, judge myproject.judges:judge`).
- What your judge suggests is no more evidence than the toolchain's own until a person confirms it; and the
  toolchain learns only from people's confirmations, as ever, of what **it** offered (a person who confirms someone
  your judge added that the toolchain did not find teaches it that the right one was "none of those it offered").
  Those confirmations are counted apart by `pangloss reconcile learn` ("30 of them of confirmed suggestions (4 of a
  project's judge)").

## 5. What it keeps

Each time the suggestions of a saved mention are asked for (the dialog, or `GET /api/reconcile/candidates/{id}`),
the server keeps what it offered you: the ten best people it found, with the numbers each score was made of, and
which of them you were shown. Only ids and numbers: no name of anyone. When you then reconcile that mention yourself,
from its dialog, within half an hour (`RECONCILE_SHOWN_FOR`), that is kept as one **decision**: what was offered, and
which of them you chose, or that you chose someone else or made someone new. Who decided is not kept. A mention
reconciled along with it, by someone else, too late, or in an unsaved form makes no decision, and what was kept for
it goes.

When Pangloss's own toolchain (section 4) writes a suggestion, it keeps the same of it: the people it found and their
numbers, and which it suggested. **What it suggests is never a decision by itself.** When a person confirms one of its
suggestions as one person (as it is, "Confirm as this one", or by saving the document with someone else in its place),
that is kept as a decision: what the toolchain offered, and whom the person confirmed (or that it was someone it did
not offer). Only a person's confirmation counts: not one in the name of a toolchain, of a disabled user, of a user
who does not exist, or of the default user of scripts, and not a restore from history. A suggestion confirmed with
several people still open is no decision, nor is one edited away. An outside toolchain's suggestions make none
(nothing of what it saw is known).

These are what the package learns from (below). To keep nothing, set
`RECONCILE_KEEP_DECISIONS = False`. They are kept on nodes of the package's own, made by its migrations, so after
installing or updating the package run `pangloss migrate`. What was offered and never decided is removed by

```sh
pangloss reconcile sweep
```

which you can run now and then (it removes what is older than `RECONCILE_SHOWN_FOR`, what belonged to a mention
no longer in its document, and a decision that was undone: a mention back in its document, or a confirmed suggestion
restored to before it was confirmed).

## 6. Learning from the decisions

What it buys, measured on a made-up world of 32,000 people with 400 decisions learnt from: the line "Probably not
in the database yet" is right for about two mentions in three, where a guess is right for half. The order of the
suggestions does not change: a learnt order was no better than the one set by hand.

```sh
pangloss reconcile learn --dry-run     # what it would do, writing nothing
pangloss reconcile learn
```

(or the job "Learn from reconciliations" on `/admin`, with its report to download). It sweeps, reads the decisions
kept, and fits two models from them: one that ranks the people offered, and one that says how likely it is that the
person meant is **none of those offered** (someone new, or someone not suggested). Each is compared with what it
would replace, on decisions held back from it: the ranking with the score set by hand, "none of these" with always
giving the commoner answer. It then writes the fit, and says what it did, line by line (here of 120 made-up
decisions):

```
0 records of what was offered removed
120 examples read
120 decisions to learn from
8 decisions with no suggestion displayed: left out of the "none of these" model
The ranking model: fitted on 1,200 rows; the one taken was first in 64 of 89 by the model, 64 by the score set by hand (recorded: nothing uses the ranking model)
The "none of these" model: fitted on 112 decisions; called rightly in 112 of 112 by the model, 64 by always answering the commoner
Written: the fit 6f1c…, in use
```

A fit is **put in use** only when its "none of these" model is of `RECONCILE_LEARN_FROM` decisions or more (100;
decisions in which nothing was shown do not count) and no worse than always giving the commoner answer. How the
ranking model did is shown and kept, but nothing uses it, and it does not keep a fit out of use. Otherwise a fit is
written all the same, not in use, the fit in use before stays in use, and the last lines say why. Decisions kept with other vectors or weights than
today's (after a rebuild that changed a part, or a change to `RECONCILE_WEIGHTS` or `RECONCILE_LEAST_SCORE`) are left out and counted, and so are
those of a mention that had no vector of some part. Decisions that were confirmations of the toolchain's suggestions
are counted apart ("120 decisions to learn from, 30 of them of confirmed suggestions"), and left out, and counted,
with `RECONCILE_LEARN_FROM_SUGGESTIONS = False`. Run with nothing new since the last fit, it writes nothing and
says so (and, if that fit is not in use, how to put it in use). Fits are never deleted.

To go back:

```sh
pangloss reconcile learn --use 6f1c…   # an earlier fit in use again (through the same check, and only if its vectors and weights are today's)
pangloss reconcile learn --use none    # no fit in use
```

What a fit in use changes is the line *Probably not in the database yet* (section 2): over the API, the stored route's
answer (`GET /api/reconcile/candidates/{id}`) has `model` (the fit in use: its `id`, when it was fitted, how many
decisions, and `used`, false when it was made with other vectors or weights than today's), and each mention, when the
fit is used and there are suggestions, `new` (the likelihood, from 0 to 1, that the person meant is none of the
suggestions given, in the order and number given: ask for one and the figure is about that one) and `probablyNew`.
The payload route (`POST`) gives neither. The suggestions are still ranked by the score set by hand: a ranking fitted
on decisions was tried and was no better.

## What it does not do

- It does not say how likely it is that the person is **someone new** until a fit is in use (section 6), and then
  only for a saved mention, not for a payload.
- It does not suggest while you type a name into a form; only for a saved mention, and over the API.
- It does not act by itself unless turned on (section 4, "Turning it on"): only then is an identification written
  for a person to confirm.
- Dates are not used: a candidate who died a century earlier is not ranked lower for it.
