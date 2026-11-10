# Part 5: The REST API

Everything you have done from Python can be done over HTTP, by a script in any language, a front-end, or another
system. There is no code to write for it: the API is made from your models. In this part you read and write with `curl`.

## The endpoints

Start the server if it is not running (`pangloss dev`) and open <http://127.0.0.1:8000/docs>. Since part 1, an entry
has appeared for each of your models. For a factoid:

```
GET    /api/Factoid                  list (search and paging are query parameters)
POST   /api/Factoid                  create
GET    /api/Factoid/{id}             read one
GET    /api/Factoid/{id}/edit        read one for editing
PUT    /api/Factoid/{id}             update
DELETE /api/Factoid/{id}             delete
POST   /api/Factoid/{id}/undelete    undelete
```

and the same for `Person`, `Group`, `Place` and `Source`, and for `Meeting` and `Journey` too. `GET /api/Meeting` lists
every meeting, whatever factoid it is in (each says, in its `meta`, the factoid that holds it), which is the start of
asking questions across all your sources. You write statements as part of their factoid, as in part 4.

The documentation page is interactive: open an endpoint, press *Try it out*, and it sends the request for you. Here you
use `curl`, so that you can see exactly what is sent.

## Reading needs no login

```console
$ curl http://127.0.0.1:8000/api/Person
{"results":[{"id":"01a197d5-42b1-...","label":"Charlemagne","type":"Person"},{"id":"01a197d5-42bc-...","label":"Pope Leo III","type":"Person"}],"count":2,"page":1,"pageSize":50,"nextPage":null,"previousPage":null,"truncated":false}
```

`?q=leo` searches, as `Person.list("leo")` did; `?page=2` and `?page_size=10` page through.

Read one of the factoids from part 4 (use an id from `GET /api/Factoid`):

```console
$ curl http://127.0.0.1:8000/api/Factoid/01a197d7-ea3b-...
{
  "id": "01a197d7-ea3b-...",
  "meta": {"createdBy": "alice", "createdWhen": "2026-11-01T16:01:12.253679Z", ..., "version": 1, ...},
  "type": "Factoid",
  "label": "Leo is received at Paderborn",
  "page": "s.a. 799",
  "text": "The king received the pope at Paderborn with great honour.",
  "source": {"id": "01a197d5-429a-...", "label": "Royal Frankish Annals", "type": "Source"},
  "mentions": [...],
  "statements": [
    {"id": "...", "type": "Meeting", "label": "Charles receives Leo", "when": {...}, "at": [...], "participants": [...]},
    {"id": "...", "type": "Journey", "label": "Leo travels to Paderborn", ...}
  ]
}
```

(laid out here for reading; `curl` prints it on one line, and `| python -m json.tool` lays it out.) It is the
`HeadView` you read from Python, as JSON. One difference: **the JSON uses camelCase** (`createdBy`, `pageSize`) where
Python uses snake_case (`created_by`). Pangloss converts at the edge, so each side gets what is usual for it.

## Writing needs a login

```console
$ curl -X POST http://127.0.0.1:8000/api/Place -H 'content-type: application/json' -d '{"label": "Aachen"}'
{"detail":"Not logged in"}
```

Anyone may read; to write you must say who you are. Log in as alice to get a token:

```console
$ curl -X POST http://127.0.0.1:8000/api/users/token -d 'username=alice&password=alice-password'
{"access_token":"eyJhbGciOi...","refresh_token":"eyJhbGciOi...","token_type":"bearer","expires_in":1800}
```

and send the `access_token` with each request that writes:

```console
$ TOKEN=eyJhbGciOi...          # the access_token from above
$ curl -X POST http://127.0.0.1:8000/api/Place \
    -H "Authorization: Bearer $TOKEN" -H 'content-type: application/json' \
    -d '{"label": "Aachen"}'
{"id":"01a197d9-34d6-7040-8729-fe6fb01ebc35","label":"Aachen","type":"Place"}
```

The place is recorded as created by alice, as when you wrote from Python. The token lasts 30 minutes (`expires_in`, in
seconds); the `refresh_token` gets a new one. For a script that runs for longer, or unattended, give it a **personal
access token** instead: see [Users, logins and the API](../accounts/README.md).

## A factoid over HTTP

A factoid is written with the same shape as from Python, as JSON. Put this in a file `factoid.json`, with the ids of the
Annals, Charlemagne and Aachen from your own database:

```json
{
  "label": "Charles spends the winter at Aachen",
  "source": {"type": "Source", "id": "01a197d5-429a-..."},
  "page": "s.a. 799",
  "text": "The king wintered at Aachen.",
  "mentions": [{"type": "Person", "id": "01a197d5-42b1-..."}],
  "statements": [
    {
      "type": "Journey",
      "label": "Charles goes to Aachen",
      "when": {"type": "ExactDate", "year": 799},
      "traveller": {"type": "Person", "id": "01a197d5-42b1-..."},
      "destination": {"type": "Place", "id": "01a197d9-34d6-..."}
    }
  ]
}
```

and send it:

```console
$ curl -X POST http://127.0.0.1:8000/api/Factoid \
    -H "Authorization: Bearer $TOKEN" -H 'content-type: application/json' \
    -d @factoid.json
{"id":"01a197d9-352e-...","label":"Charles spends the winter at Aachen",...,"type":"Factoid"}
```

## When a request is wrong

Leave out the `page` and give a participant a role that does not exist:

```console
$ curl -X POST http://127.0.0.1:8000/api/Factoid \
    -H "Authorization: Bearer $TOKEN" -H 'content-type: application/json' \
    -d '{"label": "Bad", "source": {"type": "Source", "id": "01a197d5-429a-..."}, "text": "...", "mentions": [],
         "statements": [{"type": "Meeting", "label": "m", "when": {"type": "ExactDate", "year": 799}, "at": [],
                         "participants": [{"type": "InRole", "role": "bishop", "target": [{"type": "Person", "id": "01a197d5-42b1-..."}]}]}]}'
```

The answer is a `422` that lists every problem and where it is:

```json
{"detail": [
  {"type": "missing", "loc": ["body", "page"], "msg": "Field required", ...},
  {"type": "enum", "loc": ["body", "statements", 0, "MeetingCreate", "participants", 0, "role"],
   "msg": "Input should be 'host', 'guest', 'envoy' or 'witness'", ...}
]}
```

The same Pydantic models that checked your Python check the JSON, so the rules are the same whichever way data comes in,
and nothing is written unless all of it is right.

## Other ways in

- **From Python, on another machine**: the SDK gives a script the same classes you used in part 2, talking to the server
  over HTTP instead of to the database. See [the SDK guide](../sdk/README.md).
- **A lot of data at once**: `pangloss memgraph bulk-load` loads a file of records into an empty database, much faster
  than one request at a time. See [Large data](../../implementation_docs/large-data.md).
- **Searching by structure** ("every meeting at which Leo was a guest"): `POST /api/search`. See
  [the search guide](../search/README.md).

## What you have done

You have read and written your data over HTTP, logged in, and seen how a wrong request is explained. In
[part 6](06-packages.md) you add two more of Pangloss's optional packages.
