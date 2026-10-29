# End-to-end tests

A real project (the API, the test Memgraph, the built interface) driven in a browser by [Playwright](https://playwright.dev/python/).
They are not in `packages/`, so `./run_tests.sh` does not run them.

```sh
uv sync --all-packages --all-groups --all-extras   # the `e2e` group has pytest-playwright
uv run playwright install chromium                 # once (about 100 MB)
uv run pytest e2e                                  # headless
uv run pytest e2e --headed --slowmo 300            # to watch
uv run pytest e2e --tracing retain-on-failure      # then: uv run playwright show-trace test-results/…/trace.zip
```

Needs the test Memgraph on :7687 (**wiped**, as the other tests do) and Node. The session fixture (`conftest.py`) makes a
new project in a temporary directory with the commands a user runs (`new-project`, `makemigrations`, `migrate`,
`interface build`, …), starts `pangloss run` and `pangloss interface serve`, and puts a small proxy in front so that `/api` is
beside the interface, as it is when deployed.

Keep these few: what only a browser shows (drag and drop, the built chunks, hydration). Logic belongs in the Vitest tests
of the interface and the API tests.

Notes for writing them:
- The page is server-rendered and then hydrated: wait for `window._$HY.done` before something needs a handler (a drag).
- Drag with `page.mouse` in steps; `drag_to` moves in one step, which the browser does not take for a drag.
- Log in with `POST /api/users/session` (the `logged_in` fixture); the nav's login button is only there when it is expanded.
