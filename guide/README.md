# Pangloss guides

Tutorials and how-tos. The reference, with the design of each part and what is built, is in [`docs/`](../docs/README.md).

**New here?** Start with *Getting started*, then read the guide for the part you need. To see which package does what:
[the packages, and where each is explained](packages.md).

| Guide | |
|-------|--|
| [Getting started](getting-started/README.md) | Make a project, declare some models, store data, and use it from Python and over HTTP (about 30 minutes) |
| [Migrations](migrations/README.md) | Changing your models after there is data in the database |
| [The SDK](sdk/README.md) | **Your models in your own scripts**: build the SDK on the server, install it, connect, read and write, stay current |
| [Searching](search/README.md) | Lists, autocomplete, and structured search by a JSON pattern |
| [Users, logins and the API](accounts/README.md) | Users, tokens (including personal access tokens for scripts), running the REST API |
| [Choosing and running a database](backends/README.md) | Memgraph or Neo4j; settings, differences, tests of add-ons |
| [Review](review/README.md) | Checking documents before they are published, with comments (`pangloss-review`) |
| [History](history/README.md) | Every version of every document, diffs and restore (`pangloss-history`) |
| [Dates](dates/README.md) | Uncertain dates, ranges, periods and repeated events in the Julian or Gregorian calendar (`pangloss-dates`) |
| [Calendar](calendar/README.md) | What is dated on a day, in a month, in a year; feasts and Easter (`pangloss-calendar`) |
| [Typology](typology/README.md) | Vocabularies of types in a hierarchy (`pangloss-typology`) |
| [Zotero](zotero/README.md) | A Zotero library kept in the database as sources and subjects (`pangloss-zotero`) |
| [The interface](interface/README.md) | The web interface: running it, colours, navigation, your own components, languages |

## Which guide for which job

| I want to… | Read |
|---|---|
| Run a script or notebook against a project's data | [The SDK](sdk/README.md), chapters 2 and 3 |
| Let colleagues' scripts in, safely | [The SDK](sdk/01-server.md#who-may-download-it) and [personal access tokens](accounts/README.md#personal-access-tokens-for-scripts) |
| Change a model that already has data | [Migrations](migrations/README.md) |
| Find "all letters from Smith before 1600" | [Searching](search/README.md) |
| Load hundreds of thousands of records | [Large data](../docs/large-data.md) |
| Undo a bad edit | [History](history/README.md) |
