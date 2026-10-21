# Getting started

This tutorial makes a small project from nothing. You will:

- make a **project** and an **app** for your models;
- declare **models**: people, places, and letters between them;
- make the database know about them, with a **migration**;
- **write and read data** from Python;
- use the same data through the **REST API**;
- **change a model** after there is data, and see the data follow.

It assumes you can read Python and have used a terminal. You do not need to know graph databases: Pangloss keeps your data in one (Memgraph), but you work with Python classes.

## The idea in one paragraph

You describe your data as Python classes (`Person`, `Letter`). From each class Pangloss generates the models for **creating**, **updating** and **reading** it, checks the data with them (they are [Pydantic](https://docs.pydantic.dev/) models), and stores it in a graph: each object is a node, and a field that refers to another object is an edge. Your classes are also the source of the REST API, so there is nothing to write for it.

## Parts

| | |
|---|---|
| [1. Setting up](01-setting-up.md) | What you need; making the project and an app |
| [2. Your first models](02-models.md) | `Entity` and `Document`; relations between them |
| [3. The database](03-database.md) | The first migration; a user |
| [4. Writing and reading data](04-data.md) | `Create(...).save()`, `get`, `list`, and the reverse relation |
| [5. The REST API](05-api.md) | Running the server; logging in; reading and writing over HTTP |
| [6. Changing a model](06-changing-a-model.md) | A new required field, and a second migration |

Each part builds on the one before. The code in this tutorial was run, in this order, on an empty database; the output shown is what it printed (shortened where it was long).

Reference documentation for everything used here is in [`docs/`](../../docs/README.md), starting with [Defining models](../../docs/models.md) and [Command line](../../docs/cli.md).
