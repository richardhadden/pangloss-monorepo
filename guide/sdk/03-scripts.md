# 3. In your scripts

`sdk-demo/sdk_demo.py` is a complete script, written as `# %%` cells so that an editor or Jupytext opens it as a notebook.
The pieces of it follow.

## Connecting

```python
import asyncio
import pangloss_demo_sdk as sdk

sdk.connect("https://pangloss.example.org")         # not awaited: it initialises the models

from demo_app.models import Person, Factoid         # import the models AFTER connect()
```

`connect` imports your apps' models, runs `initialise()` with the model functions bound to requests, and tells the
server which SDK this is. **Import the project's modules after it.** The URL can be left out if `PANGLOSS_URL` is set.

### Async or blocking

The default is async, like the server's own code:

```python
async def main():
    page = await Person.list(page_size=5)
    await sdk.disconnect()

asyncio.run(main())
```

For a script with no event loop to spare, or a quick session at a prompt, connect with `sync=True` and the same calls
block:

```python
sdk.connect("https://pangloss.example.org", sync=True)
from demo_app.models import Person

page = Person.list(page_size=5)         # no await
sdk.disconnect_sync()
```

In the blocking flavour the helpers are `sdk.check_sync()`, `sdk.disconnect_sync()` and `pangloss_sdk.iterate_sync`.
The two flavours are chosen once, at `connect`. The type stubs that come with the package describe the async one; for a
type checker to agree with `sync=True`, run `pangloss-sdk sync-stubs` ([chapter 4](04-current.md#type-checking)).

## Logging in

Reading needs no login. The first request that does need one (a write, or `get_for_edit`) finds one, in this order:

1. A token already held: `token=` / `PANGLOSS_TOKEN` (a personal access token, used as it is), or one renewed with the
   refresh token.
2. `username=` and `password=` to `connect`, or `PANGLOSS_USERNAME` and `PANGLOSS_PASSWORD`.
3. A login [kept by `pangloss-sdk login`](#keeping-a-login).
4. **A prompt**, if there is a terminal or a Jupyter kernel: it names the server, asks for the username, and reads the
   password with `getpass`. Three tries.
5. Otherwise `PanglossAuthenticationRequired`. A script that runs unattended fails; it never waits at a prompt that
   nobody will answer.

The password is never stored. The access token (30 minutes) lives in memory and is renewed when it expires.

Settings can all be given to `connect(...)` (`username=`, `password=`, `token=`, `timeout=`, `verify_tls=`,
`max_connections=`, `read_retries=`, `use_stored_login=`) or in the environment with the prefix `PANGLOSS_` (a `.env`
in the working directory is read).

### For unattended jobs: a token

Make a personal access token on the server (`pangloss users tokens create ada --name nightly --scope write`), and give
it to the job:

```bash
PANGLOSS_URL=https://pangloss.example.org PANGLOSS_TOKEN=pgl_… python nightly.py
```

A token can be revoked without changing a password, can expire, and can be `read` only. A report that only reads should
use a read-only token.

### Keeping a login

For a laptop, where you do not want to type a password for every script:

```bash
pangloss-sdk login https://pangloss.example.org          # asks once
pangloss-sdk status                                      # which login is kept, and is it still good
pangloss-sdk logout                                      # revokes it on the server, and forgets it
```

(`status` and `logout` take the URL too, or read `PANGLOSS_URL`.)

What is kept is a **refresh token** (14 days), never the password: in the OS keyring if `keyring` is installed, else in
`~/.config/pangloss/credentials.json` with mode `600`. Only `login` writes it; a running script never does. Settings you
give explicitly win over a kept login. `pangloss-sdk login URL --token` keeps a personal access token instead.

## Reading

```python
person  = await Person.get(person_id)                  # a Person.HeadView, or None
person  = await Person.get("https://example.org/e/1")  # an entity may be found by one of its URLs
page    = await Person.list(search_terms="charl", page_size=20)
page    = await Person.list(search_terms="rome", deep_search=True)   # through the documents that mention it
for item in page.results:                              # reference views: id, type, label, meta
    ...
page.count, page.next_page, page.truncated
```

To go through everything, let `iterate` follow `next_page`:

```python
import pangloss_sdk

async for person in pangloss_sdk.iterate(Person.list, page_size=100):
    ...

for person in pangloss_sdk.iterate_sync(Person.list, page_size=100):   # sync=True
    ...
```

### Searching by structure

`Document.search` and `Entity.search` take a pattern, the same JSON as `POST /api/search`
([Searching](../search/README.md)):

```python
from pangloss_models.search import Match

found = await Factoid.search(
    Match(where={"statements": {"type": "Activity", "where": {"carried_out_by": {"is": str(charlemagne.id)}}}}),
    page_size=25,
)
```

`Entity.autocomplete("smi", types=[Person, Place])` finds entities by label as someone types.

## Writing

```python
charlemagne = await Person.Create(
    label="Charlemagne",
    known_as={"value": "Karolus Magnus", "certainty": 5},
    aliases=["Charles the Great"],
).save()
charlemagne.id
```

`save()` returns a reference view of what was made; `save(detail=True)` returns the full `HeadView`. A document that
refers to entities names them by id:

```python
factoid = await Factoid.Create(
    label="Charlemagne is in Rome",
    statements=[{
        "type": "Activity",
        "carried_out_by": {"type": "Person", "id": charlemagne.id},
        ...
    }],
).save(detail=True)
```

### Updating: against the version you read

An update replaces the whole document, so say which version you based it on. If someone else saved first, the update is
refused, not merged.

```python
from pangloss_models.exceptions import PanglossVersionConflictError

editing = await Person.get_for_edit(charlemagne.id)       # the EditView, with meta.version
based_on = editing.meta.version
try:
    await Person.Update(id=charlemagne.id, label="Charlemagne, emperor", ...).save(expected_version=based_on)
except PanglossVersionConflictError as error:
    print("changed meanwhile; now at", error.current_version)
```

### Deleting

```python
await Factoid.delete(factoid.id)          # documents first
await Person.delete(charlemagne.id)       # an entity that is still referred to raises PanglossEntityInUseError
await Person.undelete(charlemagne.id)
```

A delete only *marks* the node (it is hidden from every read), as on the server. If the server uses
[`pangloss-review`](../review/README.md), `save(published=True)` or `save(review_status="checked")` writes data you know
to be right as published.

### Bulk loads

Each `save()` is a request. For a few thousand records that is fine, and several `asyncio.gather`ed saves share the
connection pool (`max_connections`, default 10). For hundreds of thousands, the server-side loader is far faster:
`pangloss memgraph bulk-load` on an empty database ([Large data](../../docs/large-data.md)). A write is never retried
by the client (it might have happened); a read is, twice, after a network error.

## Errors

The errors the models already have are raised as they are on the server (`PanglossVersionConflictError`,
`PanglossNotFoundError`, `PanglossReferenceError`, `PanglossEntityInUseError`, `PanglossConflictError`, with the same
attributes). The client adds:

| | |
|---|---|
| `PanglossConnectionError` | The server could not be reached, or did not answer in time |
| `PanglossAuthenticationRequired` | A login is needed and no credentials can be had (unattended, nothing set) |
| `PanglossAuthenticationError` | The login or token was refused (401) |
| `PanglossPermissionError` | Logged in, not allowed (403): a read-only token trying to write, for example |
| `PanglossSdkOutOfDate` | The server refused a write because the models of this SDK are older than its own: [update](04-current.md) |
| `PanglossRequestError` | The server did not accept the request as made (400/422); usually the SDK is out of date |
| `PanglossServerError` | 5xx |
| `PanglossNotConnected` | A model function was used before `connect()` |

All of them derive from `pangloss_sdk.PanglossSdkError`. Using a model function before `connect()` is the most common
mistake: models imported before `connect` are not initialised.

## A template for a script

```python
"""Import the letters in letters.csv"""
import asyncio
import csv
import sys

import pangloss_demo_sdk as sdk
from pangloss_models.exceptions import PanglossWriteError

sdk.connect()       # PANGLOSS_URL, and PANGLOSS_TOKEN or a kept login, from the environment

from demo_app.models import Person        # noqa: E402  (after connect)


async def main(path: str) -> int:
    await sdk.check()                      # warns if this SDK is out of date
    failures = 0
    with open(path, newline="") as file:
        for row in csv.DictReader(file):
            try:
                await Person.Create(label=row["name"]).save()
            except PanglossWriteError as error:
                failures += 1
                print(f"{row['name']}: {error}", file=sys.stderr)
    await sdk.disconnect()
    return failures


raise SystemExit(asyncio.run(main(sys.argv[1])))
```

## In tests and notebooks

- **A notebook** needs the async flavour's `await` at top level (Jupyter allows it), or `connect(..., sync=True)`. The
  login prompt works in a Jupyter kernel.
- **Tests of your own code** that uses the SDK: `connect_offline()` imports and initialises the models with no server, to
  check that they import. The model classes are validated locally, so `Person.Create(...)` raising `ValidationError` needs no
  server. A test that saves needs a server; use a scratch project and database.
