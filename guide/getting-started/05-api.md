# 5. The REST API

The models you wrote are also a web API. There is no code to add.

## Run the server

```console
$ pangloss run
INFO:     Uvicorn running on http://127.0.0.1:8000 (Press CTRL+C to quit)
```

(`pangloss dev` is the same, but restarts when a file changes, which is what you want while working.) Leave it running and use another terminal. Open <http://127.0.0.1:8000/docs> in a browser: it is the interactive documentation of every endpoint, made from your models.

For each model there are endpoints under `/api`:

```
GET    /api/Letter              list (search and paging are query parameters)
POST   /api/Letter              create
GET    /api/Letter/{id}         read one
GET    /api/Letter/{id}/edit    the form of the letter for editing it
PUT    /api/Letter/{id}         replace
DELETE /api/Letter/{id}         delete
POST   /api/Letter/{id}/undelete
```

and the same for `Person` and `Place` (for entities the `{id}` can also be a URL).

## Reading needs no login; writing does

```console
$ curl http://127.0.0.1:8000/api/Letter
{"results":[{"id":"01a15eec-5000-...","label":"Ada to Babbage, 1843", ...,"type":"Letter"}],"count":1,"page":1,"pageSize":50, ...}

$ curl -X POST http://127.0.0.1:8000/api/Person \
    -H 'content-type: application/json' -d '{"label": "Mary Somerville", "name": "Mary Somerville"}'
{"detail":"Not logged in"}
```

Log in as the user you made in part 3, to get a token:

```console
$ curl -X POST http://127.0.0.1:8000/api/users/token -d 'username=alice&password=alice-password'
{"access_token":"eyJhbGciOi...","refresh_token":"eyJhbGciOi...","token_type":"bearer","expires_in":1800}
```

and send it with the request:

```console
$ TOKEN=eyJhbGciOi...        # the access_token from above
$ curl -X POST http://127.0.0.1:8000/api/Person \
    -H "Authorization: Bearer $TOKEN" -H 'content-type: application/json' \
    -d '{"label": "Mary Somerville", "name": "Mary Somerville"}'
{"id":"01a15eec-8130-...","label":"Mary Somerville","type":"Person"}
```

The person is written as `alice`, as in part 4. Read one letter back, with its relations:

```console
$ curl http://127.0.0.1:8000/api/Letter/01a15eec-5000-7407-90c6-6201e6d166d6
{"id":"01a15eec-5000-...","meta":{"createdBy":"alice", ..., "version":1},"type":"Letter",
 "label":"Ada to Babbage, 1843","text":"My dear Babbage ...",
 "sentBy":{"id":"01a15eec-4fb3-...","label":"Ada Lovelace","type":"Person"},
 "sentTo":{"id":"...","label":"Charles Babbage","type":"Person"},
 "sentFrom":[{"id":"...","label":"London","type":"Place"}]}
```

Two things to notice:

- **The JSON uses camelCase** (`sentBy`, `createdBy`) while the Python uses snake_case (`sent_by`). Pangloss converts at the edge.
- **A wrong request is explained.** Leave out `name` and you get a `422` that says which field is missing and where, because the same Pydantic model that checked your Python call checks the JSON.

## Where the rest is

Tokens, cookie sessions, CORS for a browser front-end, and the user endpoints are in [REST API](../../docs/api.md). Stop the server with Ctrl-C before the next part (or leave it: `pangloss dev` will restart by itself).

Next: [changing a model](06-changing-a-model.md), now that there is data.
