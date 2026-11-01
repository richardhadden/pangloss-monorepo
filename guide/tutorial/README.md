# Writing your first Pangloss application

This tutorial builds one application from an empty directory to something you could start putting real research into.
Along the way it explains not just *what* to type but *why* Pangloss is shaped the way it is, so that when you come to
model your own material you know which choice to make.

## What you will build

A database of **what chronicles say about people**. You will record:

- **sources**: the Royal Frankish Annals, Einhard's *Life of Charlemagne*;
- the **people**, **groups** and **places** they mention: Charlemagne, Pope Leo III, Paderborn;
- **factoids**: what one source says at one place in it ("s.a. 799"), made of **statements**: a *meeting* between
  Charles and Leo, in which Charles was the host and Leo the guest; a *journey* Leo made to Paderborn; and things a source
  says did **not** happen.

You will see that data three ways: from Python, in the web interface, and over the REST API. Then you will add three of
the optional packages (historical dates, a vocabulary of occupations, review before publishing) and write tests for your
models.

If you work with sources, this shape will be familiar: it is a small version of a *factoid* prosopography. If you do not,
it does not matter; the same ideas carry over to letters, charters, court cases or anything else where documents make
claims about things.

## Before you start

You should be comfortable reading Python and using a terminal. You do **not** need to know anything about graph databases:
Pangloss keeps your data in one, but you work with Python classes. If you have used Django, much will feel familiar
(projects, apps, models, migrations); where Pangloss differs, the tutorial says so.

The whole tutorial takes a few hours. Each part ends at a point where everything works, so you can stop between them.

## The parts

| | |
|---|---|
| [1. A project](01-project.md) | Installing; the database; making a project and an app; what each file is for; the first migration; starting the server |
| [2. Models](02-models.md) | Entities and documents; fields and relations; migrations; a user; exploring your data from Python |
| [3. The web interface](03-interface.md) | Seeing your data in a browser; colours, navigation, and naming the reverse of a relation |
| [4. Statements](04-statements.md) | Documents inside documents; an abstract model; roles; traits; saying that something did *not* happen; dates |
| [5. The REST API](05-api.md) | Reading and writing over HTTP; logging in; what an error tells you |
| [6. More packages](06-packages.md) | A vocabulary of occupations in a hierarchy; checking factoids before they are published |
| [7. Testing](07-testing.md) | Tests for the rules of your models; where to go next |

## How to read it

- Commands start with `$` and are run in the directory of your project (made in part 1) unless the text says otherwise.
  Lines that follow without a `$` are what the command printed.
- Python that starts with `>>>` is typed into an interactive Python session (part 2 sets one up). Lines without `>>>`
  are what it printed back.
- What is printed has been shortened where it was long; ids (`01a197d5-...`) will be different for you.

Every command and every piece of code in this tutorial was run, in order, on an empty database, and the output shown is
what it printed.

## If you get stuck

- [`docs/`](../../docs/README.md) is the reference: [Defining models](../../docs/models.md),
  [Relations and fields](../../docs/relations.md), [Command line](../../docs/cli.md), [REST API](../../docs/api.md).
- The other [guides](../README.md) go deeper into each part: migrations, searching, the SDK, each optional package.
- The demo project (`pangloss-demo/`) is a larger version of what you will build, using most of what Pangloss has.

Ready? Start with [part 1](01-project.md).
