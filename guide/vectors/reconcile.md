# Who an unidentified person may be

A source names "Jon Smyth" and you do not yet know which Jon Smyth. With `pangloss-review` that is an
`Unreconciled` in the person's place ([review](../review/README.md)). With `pangloss-reconcile`, Pangloss
suggests who it may be: the people whose **names** are near, ranked also by the **company they keep** (the
other people, places and groups the document names). A namesake who was at the same place with the same people
comes before one who was not.

It suggests **candidates**. A person chooses; nothing is reconciled, merged or written by it.

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
graph is worse (at equal weights, 16 to 30 in 100): the company finds the right family, not the person. If you leave the setting out and two profiles could serve, the server
says so when it starts and asks you to name one.

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
- a bar and a figure: the score, from 0 to 1 (hover the bar for the name's and the company's share of it),
- **Choose**, which makes it the one the mention is reconciled with, as if you had found it in the box,
- and, under it, *also named with*: the people, places and groups of this document that other documents name
  together with that candidate, which is why it is suggested. A number beside one says in how many documents.

Nothing is suggested when nobody's name is near enough, and the box works as before. The mention has to be
saved first (the dialog says so): the suggestions are of the document as it is stored.

The score is a help in ordering, not a likelihood: 0.9 does not mean nine in ten. And the right answer may be
"none of these": the person may not be in the database yet.

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
      "score": 0.91, "scores": {"name": 1.0, "graph": 0.57},
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
| `RECONCILE_WEIGHTS` | `{}` | Other weights for the score than the profile's, by part: `{"name": 1, "graph": 0.1}` |
| `RECONCILE_FETCH` | 50 | How many candidates are gathered by the name, and by the company, before they are scored together |
| `RECONCILE_MOST_UNKNOWNS` | 20 | The most unidentified people in one payload |
| `RECONCILE_REASONS` | 5 | The most "also named with" a candidate; 0 turns them off |

## What it does not do

- It does not say how likely it is that the person is **someone new**.
- It does not suggest while you type a name into a form; only for a saved mention, and over the API.
- It does not act by itself: no identification is written for a person to confirm. (Planned.)
- Dates are not used: a candidate who died a century earlier is not ranked lower for it.
