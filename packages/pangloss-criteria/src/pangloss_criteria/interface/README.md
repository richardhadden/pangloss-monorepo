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
- `components/CriteriaForm.tsx`: what the dialog and the form of a shared description both edit criteria with
  (`createCriteriaEditing`, `CriteriaFields`, `CriteriaResult`: the search form of the class, what it cannot show,
  and the preview).
- Shared descriptions (`Description`, cited by a mention's `description`; its `criteria` are then the mention's own
  extra conditions): `components/Shared.tsx` has the summary of a mention that cites one (the chip, "+", its own
  conditions), its marks ("changed since cited", with "Seen" in a form: the core's `CitationMarks`), "Start from" in the
  dialog (`GET /api/criteria/shared`, Use and Copy), the head of the dialog of a mention that cites one, and the offer
  to make identical criteria one (`POST /api/criteria/similar`, then `/share`). `components/DescriptionPage.tsx` is
  its page (`item_page`: how many mentions use it, its criteria, what they find, its mentions from
  `GET /api/criteria/shared/{id}/mentions`); `components/DescriptionCriteria.tsx` its criteria in its form
  (`newItemFields`, `editItemFields`, for that class only; the class's `hide_on_forms` leaves the plain field off).
- `src/value.ts`: a description as the form holds it (and `brokenOf`, `brokenField`); `src/labels.ts`: the labels of
  the entities criteria name.

Its tests run in a built project (`npx vitest run --root modules/pangloss_criteria` in `.pangloss/interface`); the e2e
suite does that (`e2e/test_module_unit_tests.py`).
