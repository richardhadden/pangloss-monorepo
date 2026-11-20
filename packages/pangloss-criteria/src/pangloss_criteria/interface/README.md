# Interface module of `pangloss_criteria`

A Solid 2.0 library that the interface (`pangloss interface build`) includes when `pangloss_criteria` is in
`INSTALLED_APPS`. `MatchesCriteria` names its two cards for itself (`InterfaceMeta(view_card=..., edit_card=...)` in
`pangloss_criteria/models.py`). The plan is [implementation_docs/matches-criteria.md](../../../../../implementation_docs/matches-criteria.md),
"The interface".

- `src/index.ts`: the manifest (the two cards, the page `/criteria/broken`, and a part of `/admin`).
- `src/describe.ts`: `describeCriteria`, the one summary of criteria (a list of parts: text, a type, an entity, brackets),
  `describeText` and `cutParts`; `components/CriteriaSummary.tsx` draws it with each entity a `ReferenceChip`.
- `components/CriteriaCard.tsx`: the card on a document's page; it follows `candidatesFeed` (`src/feed.ts`, a `live()`
  server function that asks `GET /api/criteria/{id}/candidates` every `PANGLOSS_CRITERIA_POLL_MS` (2000) ms and ends
  when the description is evaluated) until the worker has found the candidates. Someone logged in has "This is…" in
  its bar, which opens `components/ResolveDialog.tsx` (loaded when first opened): the candidates (`CandidatePages`,
  the paged list "and N more" opens too), one chosen and confirmed is put in its place (`POST /api/criteria/{id}/resolve`),
  and the page is read again. In a list of what refers to a candidate (`ViewCardProps.incoming`) the card is only
  "identified as candidate" and the summary.
- `components/CriteriaEditor.tsx` and `CriteriaDialog.tsx`: the card in a form, and the dialog its pencil opens: the
  class described, the wording, the search form of the class (`SearchFields`), and what the criteria find
  (`POST /api/criteria/preview`).
- A description out of date (its computed `broken`, the reason, and `brokenSince`, the migration; after a migration
  took away what its criteria name): the card says so (`BrokenNotice` in `components/parts.tsx`) and keeps its last
  candidates, faded; its dialog has a red notice at the top, the row of the field the reason names red
  (`SearchFields`' `invalid`), and, where the form can no longer show the criteria, their JSON and "Start afresh".
  `components/BrokenPage.tsx` is `/criteria/broken` (someone logged in: `GET /api/criteria/broken`, a page of 25),
  linked from `/admin` by `components/BrokenAdminSection.tsx` (`slots.admin`), with how many there are.
- `src/value.ts`: a description as the form holds it (and `brokenOf`, `brokenField`); `src/labels.ts`: the labels of
  the entities criteria name.

Its tests run in a built project (`npx vitest run --root modules/pangloss_criteria` in `.pangloss/interface`); the e2e
suite does that (`e2e/test_module_unit_tests.py`).
