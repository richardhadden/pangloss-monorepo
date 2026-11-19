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
