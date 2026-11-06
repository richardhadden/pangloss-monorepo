# Interface module of `pangloss_review`

A Solid 2.0 library that the interface (`pangloss interface build`) includes when `pangloss_review` is in `INSTALLED_APPS`.
It adds a **review button** to the console of every item page and edit page of a reviewed document (a flag coloured by
the status, and the number of open comments), which opens a **panel** on the right: buttons to change the status, and
the comments as a conversation, kept up to date while the page is open. The plan is in
[docs/review-interface.md](../../../../../docs/review-interface.md).

- `src/index.ts`: the manifest; the button is a `consoleActions` entry (`ReviewAction`).
- `src/feed.ts`: `reviewFeed`, a `live()` server function. It runs on the interface's server, asks
  `GET /api/review/{id}` every `PANGLOSS_REVIEW_POLL_MS` (3000) milliseconds with the reader's cookies, and sends the
  browser a new snapshot when something changed.
- `src/state.ts`: the store over the feed, and the writes (status, comment, resolve), shown at once and confirmed by
  the feed.
- `src/api.ts`: the review API's types and calls.

Its tests run in a built project (`npx vitest run --root modules/pangloss_review` in `.pangloss/interface`); the e2e
suite does that.
