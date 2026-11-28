# pangloss-compare

Comparison of statements for Pangloss: which statements tell of one event, and how they stand to each other (agree,
disagree, an order carried out or not). Being built: what a class says of its comparison (`CompareMeta`) and its checks,
the verdict, the pairs by rule and through near entities (`?near=true`), a person's judgement (`EventJudgement`, which the project's class cites the two
statements from; never edited once made: a new one decides), the route `GET /api/compare/{type}/{ref}` and learning
from the judgements (`pangloss compare learn`, `status`) and an interface module (the section "Compared" on a statement's page, and the page of two statements side by side,
`/compare/:type/:a/:b`, where a judgement is recorded) are there; the rest is in phase 6 of
`implementation_docs/spaces-and-comparison-plan.md`.

See `implementation_docs/compare.md`.
