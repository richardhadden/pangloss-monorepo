# Security review, 2026-11-07

A read-through of the code on branch `security-check` (from `dev` at e2e1a54) for security problems, plus
`pip-audit` of the locked Python dependencies and `npm audit` of the interface workspace. Nothing was
changed. Severity is a judgment: none of these is an open hole in a default deployment.

## What holds up

- Every Cypher query takes values as parameters. Names that go into query text (class labels, field edges)
  are checked against `^[A-Za-z_][A-Za-z0-9_]*$` (`pangloss_cypher.fragments._checked`) or come from the
  registry after `check_where` has matched them to a model's fields. Text-search terms are cut to `\w+`
  before they become regexes (`pangloss_models.autocomplete.search_words`), so no regex or Lucene syntax
  reaches the index.
- Passwords: Argon2id, a dummy hash so an unknown username takes as long as a wrong password, rehash on
  parameter change, 8-character minimum, per-username throttle (429 with `Retry-After`).
- Tokens: HS256 pinned, `sub`/`exp`/`type` required, access and refresh tokens cannot be swapped, `jti`
  revocation and a per-user `token_generation` so a password change ends every session. Personal access
  tokens are random (32 bytes), stored as a SHA-256 hash, scoped, and `read` scope is refused for unsafe
  methods. Users are looked up on every request, so a disabled user is cut off at once.
- Cookies are `HttpOnly`; `Secure` is forced when `SameSite=None`. CORS refuses credentials with `*`.
- Unhandled errors answer a generic 500. Logs redact anything that looks like a secret; usernames are
  logged with `%r`. Validation errors echo input only when it is short.
- Visibility (deleted, unpublished) is applied in reads, incoming relations, lists, search and the
  calendar through the one `fragments.visible` helper.
- SDK server: git over HTTP is upload-pack only; wheel and sdist are built in memory from the package
  files only; downloads need admin by default. SDK client keeps a refresh token (never the password) in
  the keyring or a 0600 file, and refuses a file others can read.
- `npm audit` of the interface workspace: 0 vulnerabilities.

## Findings

### Medium

1. **Cookie sessions have no CSRF defence but `SameSite`** (`pangloss_api/dependencies.py`
   `get_access_token`; documented in `implementation_docs/api.md:49` and `:201`). `lax` (the default) stops cross-site
   `POST`s, but `AUTH_COOKIE_SAMESITE="none"` is an allowed setting and then any site can make a
   logged-in browser create, update or delete documents. There is also no login-CSRF protection
   (`POST /api/users/session` from a third-party form logs the victim into the attacker's account).
   Suggested: when the token comes from the cookie (not the `Authorization` header) and the method is
   unsafe, require `Sec-Fetch-Site` to be `same-origin`/`same-site`/`none` or `Origin` to be in
   `BACKEND_CORS_ORIGINS`; or refuse to start with `SameSite=None` and cookie login together.

2. **`/docs` loads RapiDoc from unpkg with no Subresource Integrity, and `persist-auth="true"`**
   (`pangloss_api/openapi.py:52-63`). A compromise of the CDN or of that package version runs script on
   the API's origin, where RapiDoc has persisted the user's bearer token in `localStorage`. Suggested:
   serve the file from the package (or pin `integrity=`), and drop `persist-auth`.

3. **Known vulnerabilities in locked Python dependencies** (`pip-audit` on `uv export`):

   | Package | Locked | Fix | Reaches Pangloss? |
   |---|---|---|---|
   | certifi | 2026.5.20 | 2026.10.19 | **Yes**: httpx (Zotero client, SDK) trusts its bundle; a compromised eMudhra root is in it |
   | urllib3 | 2.7.0 | 2.8.0 | Indirect: dulwich, requests, docker (dev/test); streaming-client bugs, low here |
   | pydantic-settings | 2.14.1 | 2.14.2 | No: `secrets_dir` is not used; upgrade anyway |
   | ujson | 5.12.1 | 5.13.0 | No: only python-lsp-server (dev) |
   | black | 26.5.1 | 26.10.1 | No: the GitHub Action only |

   `uv lock --upgrade-package certifi --upgrade-package urllib3 --upgrade-package pydantic-settings` and
   rebuild any image that vendors certifi.

### Low

4. **`.env` is not in `.gitignore`**, and `pangloss-demo/.env` and `pangloss-smoketest/.env` hold a real
   `ZOTERO_API_KEY` and `AUTHJWT_SECRET_KEY`. They are untracked today; one `git add -A` publishes them.
   Add `.env` and `.env.*` to `.gitignore`.

5. **A short `AUTHJWT_SECRET_KEY` only warns** (`pangloss_api/app.py` `MIN_SECRET_LENGTH`). The project
   principle is fail early: refuse to start under 32 characters (the scaffold makes 64).

6. **The refresh cookie has no `Path`** (`pangloss_api/routes/users.py` `set_cookie`), so the long-lived
   refresh token travels on every request, including through the interface's Node server, which copies the
   browser's `cookie` header to the API (`interface-app/src/api.ts`). Set `path="/api/users/session"` on
   `pangloss_refresh`; only `/session/refresh` and `DELETE /session` read it.

7. **Client addresses behind a proxy**: login logs use `request.client.host`, and uvicorn is started
   without `proxy_headers`/`forwarded_allow_ips` (`pangloss_cli/server.py`), so behind `serve.mjs` or any
   reverse proxy every login is logged from the proxy's address. The throttle is per username only; there
   is no per-address limit (documented as a brake, not a rate limit).

8. **`GET /api/zotero/status` is public** (`pangloss_zotero/api.py:21`): library ids, sync versions, the
   watcher's state and `last_error` text (which can carry Zotero's error messages). The other Zotero
   routes need a login; this one should too.

9. **Two raw identifier interpolations in the search compiler** (`pangloss_cypher/search_query.py:116`
   and `:147`) put `label` and `c.field` in backticks directly instead of through `fragments.label` /
   `fragments.field_edge`. Both values come from the registry and from `check_where`, so they are safe
   today; routing them through the checked helpers removes the dependence on that.

### Known and documented, not re-raised

- No roles beyond admin: any logged-in user can create, update, delete, restore history, publish via
  review status, and link Zotero items (`implementation_docs/api.md` lists permissions as not built).
- Throttle state is per process and lost on restart.
- `AUTH_COOKIE_SECURE` defaults to `False` (dev); the guide says to set it over HTTPS.
- No request-size limit in the app; left to the proxy.
- `GET /api/sdk/version` and `/openapi.json` are public by design.

## Applied (same day, on this branch)

- CSRF: `pangloss_api.dependencies.require_same_site`. A write logged in by the cookie (not `Authorization`), and
  `POST /session`, `POST /session/refresh`, `DELETE /session`, are refused (403) when `Sec-Fetch-Site` is `cross-site`,
  or there is no `Sec-Fetch-Site` and `Origin` is neither the request's `Host` nor in `BACKEND_CORS_ORIGINS`. Requests
  with neither header (scripts, the SDK, the interface's server render) pass. Tests: `test_same_site.py`.
- RapiDoc 12.0.0 vendored at `pangloss_api/static/rapidoc/` (MIT, LICENSE beside it), served at
  `/docs/rapidoc-min.js?v=12.0.0`; `persist-auth` dropped.
- `.env`, `.env.*` ignored (`.env.example` kept).
- A secret under 32 characters is a `RuntimeError` at `create_app()`, no longer a warning.
- The refresh cookie has `Path=/api/users/session` (`REFRESH_COOKIE_PATH`), set and cleared alike.
- `GET /api/zotero/status` needs a login.
- Every label, edge type and property name in `search_query.py` goes through `fragments.label`,
  `fragments.field_edge` or the new `fragments.property_name`.
- certifi 2026.10.23, urllib3 2.8.0, pydantic-settings 2.16.2 (`uv lock --upgrade-package`).
- Not done: proxy-aware client addresses (`uvicorn --proxy-headers`), a per-address login limit.
