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
little of the graph: the part `graph`, not `actual` (being named together in a denial is evidence of who someone is,
and the actual network leaves denials out; a profile that weighs `actual` and not `graph` is warned of when the
project starts). On a made-up prosopography where many people share a name, with 7,000 people the name
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

Two routes, both for a user who is logged in. (A worked script that uses them to write suggestions for review is in
section 4, "A toolchain of your own, outside Pangloss".)

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

## 4. Settings, and Pangloss's own toolchain

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

### Pangloss's own toolchain

Pangloss can also act on its own: a document saved with a mention in it is left for a **worker in the background**,
which asks the candidates of each mention as the dialog would, decides, and writes, in the mention's place, a
**suggestion** of who it is (an `IdentificationByToolchainFromText` of the library, which keeps the name the source
wrote) for a person to confirm in review. It is built and tested on both backends; how fast it goes at size is still
being measured ([reconciliation](../../implementation_docs/reconcile.md), "The worker that suggests"). It is off
until you turn it on.

It needs `pangloss_library` and `pangloss_review` beside `pangloss_reconcile`, and a field that takes the suggestion
where the mention is: one that takes `Identification[WeightedAlternative[Person]]` (or `Identification[Person]`,
where only one person can be suggested) takes it, as it takes every class below `Identification`
([review](../review/README.md), "Keeping what the source wrote"). A mention in a field that takes no identification is
left as it is.

| Setting | Default | |
|---|---|---|
| `RECONCILE_SUGGEST_ON_SAVE` | False | Whether a save leaves a document with a mention in it for the toolchain when the save does not say (`?suggest=true` or `?suggest=false`, or `save(instructions={"suggest": True})`, says it either way) |
| `RECONCILE_SUGGEST_ABOVE` | 0.6 | The least score of the best candidate for anything to be suggested. From 0 to 1; 0.5 or 0.4 shows reviewers more, and more that is wrong |
| `RECONCILE_SUGGEST_MOST` | 3 | The most people one suggestion offers (1 to 10, and never more than the five the dialog shows) |
| `RECONCILE_SUGGEST_WITHIN` | 0.7 | A second or third person is offered only if they score at least this share of the best one's score |
| `RECONCILE_SUGGEST_AS` | `IdentificationByToolchainFromText` | The kind of identification it writes: the library's, or a subclass of your own with more fields |
| `RECONCILE_TOOLCHAIN` | `pangloss-reconcile` | The user it writes as: a toolchain, made when it is not there |
| `RECONCILE_WORKER_IN_SERVER` | True | Whether the server runs it; `False` to run it apart, `pangloss reconcile worker` |
| `RECONCILE_SUGGEST_WITH` | none | A function of yours that may replace what it suggests: `"myproject.judges:judge"` (below, "A judge of your own") |
| `RECONCILE_SUGGEST_TIMEOUT` | 60 | In seconds, how long your function is given for one mention |

Nothing is suggested for a mention whose best candidate scores under `RECONCILE_SUGGEST_ABOVE`, that has no
candidate, or that a fit in use says is probably someone new (section 6). Otherwise the best (up to
`RECONCILE_SUGGEST_MOST`) are offered with whole percentages that add up to 100, in proportion to their scores; where
the field takes one person only, the best alone. Measured on a made-up world of 32,000 people, at 0.6 about a third of
the mentions of people who are in the database got a suggestion, and it held the right person 98 times in 100; about
one mention in six of someone who is not in the database got one too (one in eight with a fit in use). No threshold
tells someone new from someone known: it is a choice of how much a reviewer is shown.

### Before you turn it on: migrations and a rebuild

```sh
pangloss makemigrations     # your own: an AlterRelationTarget for each field that takes an identification
pangloss migrate            # pangloss_library 0005 (the two classes that keep the text), pangloss_reconcile 0003 (what the worker keeps)
pangloss vectors rebuild    # once: the graph part's signature changed (below)
```

The API does not start until the migrations are applied. **The rebuild is due in every project with similarity's graph
part** (`pangloss-vectors` with `pangloss-fastrp`), whether you turn the toolchain on or not: since this version a
suggestion that nobody has confirmed (anyone's `IdentificationByToolchain`, an outside toolchain's too) is **no
evidence**: what is below one is not walked by the graph part and does not count in "also named with". That changed
the graph part's signature, so `pangloss vectors status` says a rebuild is due, and the stored candidates route
answers `rebuild_due`. Once a person confirms a suggestion it counts like any identification.

**The worker waits for this rebuild.** While the profile is not built, its vectors are of another dimension than
its parts make today, or a part's signature changed (as with this version), it claims nothing:
`pangloss reconcile status` says "waiting for the vectors: the profile is rebuild_due", and the documents marked
meanwhile are suggested once the rebuild is done. It suggests nothing the reconcile dialog would not offer.

### Turning it on

- **For every save**: `RECONCILE_SUGGEST_ON_SAVE = True`. Each save of a document that can hold a mention (a create
  or an update, in the interface, over the API or from Python) leaves it for the toolchain, unless the save says
  otherwise.
- **For one save**: `?suggest=true` on the create or update route (`POST /api/Factoid?suggest=true`,
  `PUT /api/Factoid/{id}?suggest=true`), or `save(instructions={"suggest": True})`, with the setting off.
- **A pipeline that loads documents** and does not want suggestions made in them says so on each write:
  `?suggest=false` (or `save(instructions={"suggest": False})`). `suggest=false` also takes off a document's place in
  the queue, if it had one. Any other value is refused (422).
- **What is already stored** (after a bulk load, which leaves nothing for it, or when the setting is first turned
  on):

  ```sh
  pangloss reconcile suggest                   # every class that can hold a mention
  pangloss reconcile suggest --class Factoid   # only of this class and those below it (more than once: of any)
  pangloss reconcile suggest --again           # and ask again for mentions tried before
  ```

  or the admin job *Suggest identifications in stored documents* on `/admin` (every class; its one option, *Ask
  again for mentions tried before*), or as an admin `POST /api/reconcile/suggest` with
  `{"classes": ["Factoid"], "again": false}` (both optional; it answers `{marked, already, standIns, forgotten}`). It
  leaves for the toolchain every document that holds a mention, is not deleted, is **unpublished**, and is not
  already waiting, and says how many ("120 documents left for the worker; 3 were already waiting (310 mentions in
  them)"). A class that can hold no mention is refused, with those that can. A mention the toolchain tried and
  could suggest nobody for is not asked about again until something that decides it changes (its label, its URIs,
  where it sits, the settings above, the vectors, a fit put in use, your judge). `--again` (`"again": true`) first
  forgets what was tried of the mentions of those documents, so they are asked about again, and marks again a
  document that was already waiting too: it is put back in the queue afresh, and a worker that holds it at that
  moment writes nothing of it, and it is done again.

**Who it writes as.** The worker writes each document as the user `RECONCILE_TOOLCHAIN` (`pangloss-reconcile`), a
user of kind `toolchain`: it cannot log in, and the history of the document shows the new version as its. It is made
("Pangloss's reconciliation") when the worker first claims a document to work on, before it asks any candidates,
so even a document it then suggests nobody for makes it; a project in which nothing is ever left for the worker gets
no such user. You can make it yourself first with `pangloss users create-toolchain pangloss-reconcile` (or **New
toolchain** on the admin page). If the name is that of a person, or of a disabled toolchain, the worker refuses to
write as it and **stops**, saying why in the log ("Reconcile: the worker stops: …", at error); `pangloss reconcile
worker` then ends without printing anything, and only with `--once` does it print "Refused: …" (and exit 1). Name
another and restart.

**Running it apart.** By default every server with the app runs the worker as a background task (one works at a time,
whichever holds its lease; with nothing waiting it still makes two small writes every ten seconds or so, renewing its
lease and trying to claim). To run it in a process of its own, set
`RECONCILE_WORKER_IN_SERVER = False` in the servers and run

```sh
pangloss reconcile worker              # until stopped (Ctrl-C)
pangloss reconcile worker --once       # what can be done now, then stop ("4 documents done")
pangloss reconcile worker --batch 10   # documents claimed at once (5)
```

A worker in the server is woken by the saves that leave it work; one apart looks every ten seconds.

**What it touches, and what it leaves.** Only **unpublished** documents, and only those that people write (not a
derived document, never an entity). It leaves a whole document alone when a part it would change is cited by another
document, and a document published between its read and its write. It makes **one update** of a document, based on
the version it read: a person who saved meanwhile wins, and it tries again later; a person who has the document open
in a form while it writes is told on saving that the document has changed, as with any other writer. Mentions it
decides nothing for stay as they are, with their ids. It does not change any entity.

It waits while the vectors are being rebuilt (a rebuild holds its lease), while the profile the candidates are found by
is not built or its stored vectors are of another dimension than its parts make today, and until the vectors of the
save that left it the work are made (the candidates are found by them). It does **not** wait for a rebuild that is due
only because a part's signature changed ("Before you turn it on", above).

**How far it has got**: `pangloss reconcile status` (or, as an admin, `GET /api/reconcile/suggest`):

```
waiting: 12 documents (5 claimed)
oldest: 2026-11-24T10:02:11+00:00
waiting for the vectors: 0
worker: 9b1f…, its lease until 2026-11-24T10:05:41+00:00
mentions tried and left: 340
suggestions not yet confirmed: 118
```

"waiting for the vectors: the profile is rebuild_due: nothing is claimed until it is built" (or `pending`) means run
`pangloss vectors rebuild`; it is shown when the profile is not built, its dimension changed, or a part's
signature changed (as `pangloss vectors status` reports). "worker: none running" with documents waiting means no server runs it and no `pangloss reconcile worker` is
running. What it did, and why it left a document, is in the server's log (`pangloss.reconcile.worker`).

### What a reviewer then sees

Each suggestion is a task of review, on the tab of identifications to confirm (`/review/identifications`), as any
toolchain's: it shows the name as the source wrote it, quoted ("Jon Smyth"), the people suggested, each with how
likely, and who suggested it (`pangloss-reconcile profile who`, and `, fit …` when a fit was used, `, judge …` with a
judge). The suggestion reads as the name the source wrote (`{text}`) in the label of what holds it, so a document
whose label template names that field keeps that name until the suggestion is confirmed (a label that does not come
from the field shows nothing of it either way). A row opens the form of
its document at the suggestion; **Confirm** confirms it as it is, and, where it offers several people, the dialog has
**Confirm as this one** on each (the others are taken out). A person may also correct it in the form like any part, or
reject it: restore the version before it from the document's history, and the mention is back and is not suggested
for again (unless `--again`); edit it back into a new mention by hand and it is asked about again.

What is learnt from it (section 5): **only a person's confirmation as one person**, by "Confirm as this one", by
Confirm of a suggestion of one person, or by correcting it in the form to one person and then pressing "Confirm
identification" and saving, is kept as a decision. A suggestion whose people are changed in the form but which is
not confirmed is still a suggestion and teaches nothing; nor does one replaced outright (by a person chosen in its
place, or a mention), the suggestion alone, one confirmed with several people still open, a restore from history, or
anything done by a toolchain, a disabled user or the default user of scripts.

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
for each mention the toolchain asks about (one not already tried, in a place that takes a suggestion), after the
toolchain has decided, **whether or not** it decided to suggest anyone (then `asked.decision` has no alternatives, and
its `reason` says why: `none`, no candidate; `low`, the best under `RECONCILE_SUGGEST_ABOVE`; `new`, probably someone
new); not for one in a place where your models' checks refuse any identification, which goes on as with no judge. It
is given one argument, an `Asked`: plain data, made for that call. `asked.stand_in` (`id`, `label`, `stood_for`, the
class it stands for, `uris`, `place`, the field names from the document down to it, `held_by`); `asked.document`, the whole document as Python names its fields; `asked.candidates`,
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
write: it sends a prompt to whichever model you use, with an async client and a timeout of its own, and gives back its
text.

```python
# myproject/judges.py
import json
from uuid import UUID

from pangloss_reconcile import Asked, Leave, Suggest, Unchanged

from myproject.models import Person


async def ask_model(prompt: str) -> str:
    """Your own call to a language model (its async client, its key, its limits): the text it answers"""
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
    answer = json.loads(await ask_model(prompt))
    if answer.get("none"):
        return Leave()
    # (each by the class the candidate is of; an id that is no candidate's is not taken from the model's answer)
    types = {candidate["id"]: candidate["type"] for candidate in asked.candidates}
    chosen = [
        ({"type": types[id], "id": id}, weight)
        for id, weight in answer.get("ids", {}).items()
        if id in types and isinstance(weight, (int, float)) and weight > 0
    ]
    return Suggest(chosen) if chosen else Unchanged()
```

(Write `ask_model` with an async client rather than run a sync one with `asyncio.to_thread`: that thread is the
server's own, shared with everything else, and one that hangs past the timeout keeps it. A judge that is all sync is
better a plain `def`, which the toolchain runs in threads of its own, below.)

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

### A toolchain of your own, outside Pangloss

A pipeline of your own can do what the toolchain does from outside, with the routes of section 3, and write its
suggestions for review in the same way. A worked example in plain HTTP (Python with `httpx`; any language that speaks
HTTP does the same): it reads one document, finds its `Unreconciled` mentions, asks the candidates of each, decides as
the toolchain does with its default settings (below, "What it decides"), and writes an `IdentificationByToolchainFromText` with weighted alternatives in the
place of each mention it decided for, all in **one update** based on the version it read (`If-Match`).

```python
# identify.py: python identify.py Factoid 01a197d9-352e-...
import os
import sys

import httpx

SERVER = os.environ["PANGLOSS_URL"]      # https://pangloss.example.org
TOKEN = os.environ["PANGLOSS_TOKEN"]     # a personal access token (pgl_…) of whoever runs it
TOOLCHAIN = "my-identifier"              # made once: pangloss users create-toolchain my-identifier
VERSION = "0.3"
ABOVE, MOST, WITHIN = 0.6, 3, 0.7        # as RECONCILE_SUGGEST_ABOVE, _MOST, _WITHIN


def mentions(value, found):
    """Every Unreconciled in the document as read, at any depth"""
    if isinstance(value, dict):
        if value.get("type") == "Unreconciled":
            found.append(value)
        else:
            for inner in value.values():
                mentions(inner, found)
    elif isinstance(value, list):
        for inner in value:
            mentions(inner, found)
    return found


def replaced(value, by_id):
    """The document with each mention decided for replaced by its suggestion"""
    if isinstance(value, dict):
        if value.get("type") == "Unreconciled" and value.get("id") in by_id:
            return by_id[value["id"]]
        return {key: replaced(inner, by_id) for key, inner in value.items()}
    if isinstance(value, list):
        return [replaced(inner, by_id) for inner in value]
    return value


def decide(unknown):
    """As the toolchain decides: nobody if there is no candidate, if the best scores under ABOVE, or if a fit in use
    says the one meant is probably someone new (`probablyNew`, given only when a fit is in use); else the best MOST
    that score at least WITHIN of the best's (best first, as given)"""
    candidates = unknown["candidates"]
    if not candidates or candidates[0]["score"] < ABOVE or unknown.get("probablyNew"):
        return []
    best = candidates[0]["score"]
    return [c for c in candidates[:MOST] if c["score"] >= WITHIN * best]


def percentages(scores):
    """Whole per cent that add up to 100, as the toolchain makes them: each has 1 first, the other 100 - n are
    shared in proportion to the scores, and what rounding down leaves goes to the largest remainders (the earlier
    of equal ones first)"""
    held = [max(score, 0.0) for score in scores]
    if sum(held) <= 0:
        held = [1.0] * len(held)
    spare = 100 - len(held)
    exact = [spare * score / sum(held) for score in held]
    shares = [int(share) for share in exact]
    by_remainder = sorted(range(len(exact)), key=lambda i: (-(exact[i] - shares[i]), i))
    for i in by_remainder[: spare - sum(shares)]:
        shares[i] += 1
    return [1 + share for share in shares]


def suggestion(mention, chosen):
    made = {
        "type": "IdentificationByToolchainFromText",
        "text": mention["label"],                     # what the source wrote
        "uris": mention.get("uris") or [],
        "identifiedBy": TOOLCHAIN,
        "toolchainVersion": VERSION,
        "target": [{
            "type": "WeightedAlternative",
            "alternatives": [
                {"type": c["type"], "id": c["id"], "edgeProperties": {"percent": percent}}
                for c, percent in zip(chosen, percentages([c["score"] for c in chosen]))
            ],
        }],
    }
    if mention.get("edgeProperties") is not None:     # the relation's own properties, kept
        made["edgeProperties"] = mention["edgeProperties"]
    return made


def identify(client, type_name, id):
    # (a class with subclasses answers 308 to the document's own class: the client follows it, below)
    read = client.get(f"/api/{type_name}/{id}/edit")
    read.raise_for_status()
    document, version = read.json(), read.headers["ETag"]
    type_name = document["type"]                      # its own class: the update goes there (409 otherwise)
    if document["meta"].get("published"):
        return 0                                      # as the toolchain: only unpublished documents
    by_id = {}
    for mention in mentions(document, []):
        asked = client.get(f"/api/reconcile/candidates/{mention['id']}", params={"limit": 5})
        asked.raise_for_status()
        answer = asked.json()
        if answer["status"] != "ok":
            sys.exit(f"The vectors are {answer['status']}: run pangloss vectors rebuild first")
        (unknown,) = answer["unknowns"]
        chosen = decide(unknown)
        if chosen:
            by_id[mention["id"]] = suggestion(mention, chosen)
    if not by_id:
        return 0
    written = client.put(
        f"/api/{type_name}/{id}",
        params={"suggest": "false"},                  # not left for Pangloss's own toolchain as well
        headers={"If-Match": version},
        json=replaced(document, by_id),               # what was read, sent back with the mentions replaced
    )
    if written.status_code == 412:
        return None                                   # someone saved it meanwhile: nothing written
    written.raise_for_status()
    return len(by_id)


if __name__ == "__main__":
    type_name, id = sys.argv[1:3]
    with httpx.Client(
        base_url=SERVER,
        headers={"Authorization": f"Bearer {TOKEN}"},
        timeout=60,
        follow_redirects=True,                        # the edit view of a parent class redirects (308)
    ) as client:
        done = identify(client, type_name, id)
    print("Changed meanwhile: run it again" if done is None else f"{done} suggestions written")
```

Things to know:

- **Who writes it.** A toolchain cannot log in, and the update route takes no `?toolchain=` (that is a create's, for
  an admin: [review](../review/README.md), "Uploading for others, and with a toolchain"). So the update is written by whoever the
  token belongs to (the document's history says so), and the suggestion says which toolchain made it in
  `identifiedBy` and `toolchainVersion`, which is what review lists and what makes it a toolchain's suggestion for a
  person to confirm. A new document can carry its suggestions from the start: an admin's
  `POST /api/Factoid?toolchain=my-identifier&toolchain_version=0.3` fills both in each suggestion that does not give
  them.
- **The one update.** The edit view (`GET /api/NAME/{id}/edit`) can be sent back as it was read: what only the
  server sets (`meta` and the like) is left out by the server. Its `ETag` is the version, sent back as `If-Match`; a
  `412` means someone saved meanwhile and nothing was written. A `422` means the whole update was refused and nothing
  was written, for instance a mention in a field that takes no `Identification[WeightedAlternative[...]]`: where a
  field takes `Identification[Person]` (one person), give the target as the person alone,
  `"target": [{"type": "Person", "id": "…"}]`. A mention left out stays as it was, with its id.
- **`?suggest=false`** keeps Pangloss's own toolchain off the document (with `RECONCILE_SUGGEST_ON_SAVE` on, the
  save would otherwise leave the mentions your script left for it), and takes the document out of its queue if it was
  waiting. Leave it out if you want the toolchain to look at what your script left.
- **What the toolchain checks and this does not**: that no part it changes is cited by another document (here the
  update is refused with a `409`, `PanglossCitedError`, naming the citing documents: the toolchain leaves such a
  document alone, and so should a script, rather than acknowledge the citations for a guess), the shape each field
  takes, and what it tried before. Your script decides
  which documents to run on; `GET /api/review/unreconciled` (with `?type=Person`) lists the mentions, each with its
  `head`, the document to update.
- The candidates route keeps a record of what it offered the script's user, as for a person in the dialog. Your
  update is no reconciliation, so it makes no decision of it; `pangloss reconcile sweep` removes the records.
- An outside toolchain's suggestions are no more evidence than Pangloss's own until a person confirms them (section
  "Before you turn it on"), and a confirmation of one teaches nothing: nothing of what your script saw is known.
- **What it decides.** `decide` and `percentages` follow the toolchain's own rule with its default settings (and no
  judge): nobody under `ABOVE`, nobody when the route says `probablyNew` (it says so only when a fit is in use, of
  the five candidates it gives with `limit=5`, as the toolchain looks at five), each alternative 1 per cent first and
  the rest in proportion. Change `ABOVE`, `MOST` and `WITHIN` if your project's settings differ.
- **The document's own class.** Asked by a class that has subclasses, the edit view answers `308` to the document's
  own class's route (hence `follow_redirects=True`), and an update sent to the parent class is refused with a `409`:
  the script takes the class from the `type` of what it read.
- **Nothing checks `identifiedBy`.** The update keeps whatever `identifiedBy` you give: it is not checked to be the
  name of a toolchain user (make it one with `pangloss users create-toolchain`, so that review shows a toolchain).
  Whether the update route should take `?toolchain=` as a create does is not decided.
- The SDK can do the read and the one update (`get_for_edit`, then an `Update` of your models saved with `expected_version=`
  and `instructions={"suggest": False}`: [the SDK guide](../sdk/README.md)), but it has no call for the candidates:
  ask `GET /api/reconcile/candidates/{id}` over HTTP as above.

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
suggestions as one person (Confirm as it is, "Confirm as this one", or Confirm in the form after putting someone else
in it, saved),
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
