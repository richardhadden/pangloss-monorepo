# pangloss-criteria

Matches criteria: someone (or something) a source describes and does not name. "N. N., Maximilian's secretary" is
stored as what the source gives, a description, written as a structured search, and is linked to every entity the
search finds, now and as data is added.

The design, and how far it is built, is in
[implementation_docs/matches-criteria.md](../../implementation_docs/matches-criteria.md).

Built so far:

- `SearchPattern`: a literal type that holds a pattern of structured search (the JSON of `POST /api/search`, or a
  `Model.Where`), stored as JSON text. `check_stored` checks one against the models and refuses what a stored
  pattern may not hold; `resolve_merged` gives it with the ids of merged entities replaced by their survivors.
- `MatchesCriteria[T]`, written in a field's annotation (`list[Person | MatchesCriteria[Person]]`): a `wording`, the
  `criteria`, and a computed `target`, the candidates.
- The worker (`pangloss_criteria.worker`), a background task of the server or `pangloss criteria worker`: it
  evaluates the descriptions of each saved document. `await settled(head_id)` waits for it; `await run_pending()`
  does the pending work now (tests, scripts).

```python
INSTALLED_APPS = [..., "pangloss_criteria"]
```

Settings: `CRITERIA_MAX_CANDIDATES` (50: how many candidates of a description are linked) and
`CRITERIA_WORKER_IN_SERVER` (true).
