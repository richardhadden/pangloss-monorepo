# Autocomplete: finding existing entities ✅

One endpoint in `pangloss-api` that finds existing entities by what the user has typed so far, over any set of entity types. The interface will use it for relation fields ("pick the Person"); anything else can use it too, for example the autocomplete of the Oxygen author editor. Built and tested (unit tests, Memgraph, HTTP). No page of the interface uses it yet.

## What it searches

Every entity has a `label` (a required `str`), and it is in the `label_text` text index (all `PGIndexableNode`s are). The label is the only thing searched. Only **entities** are found: a document cannot refer to a document that is not contained in its own head document, so nothing needs to look one up.

## The endpoint

```
GET /api/autocomplete?q=smi&type=Person&type=Organisation&page=1&page_size=10
```

| Parameter | Meaning |
|-----------|---------|
| `q` | What was typed. Required, at least one character. Every word of it has to occur in the label (as in `list`), as the start or the middle of a word, in any case |
| `type` | An entity class, or a trait that only entities have, or `Entity` (any entity). Repeat it for several. At least one is required |
| `page` | The page, from 1 (default 1) |
| `page_size` | Items on a page: 10 by default, at most 50 |

It answers one page, best match first:

```json
{
  "results": [
    {"id": "0194…", "type": "Person", "label": "Smith, John"},
    {"id": "0194…", "type": "Organisation", "label": "Smith & Sons"}
  ],
  "count": 2, "page": 1, "pageSize": 10, "nextPage": null, "previousPage": null
}
```

`type` of an item is the class the entity was created as (its subclass, if it is one), so the interface can show it and open the right route. The `id` is the entity's id; an entity's URLs are not part of the answer.

- The order is: labels that **begin with** what was typed first, then by the text index's score, then alphabetically.
- An entity that has been deleted is not found.
- A `type` that is not an entity type (a document, an embedded model, a name that does not exist) is a 422 that names it. It is never ignored.
- Text with no letters or digits (`(`, `.*`) finds nothing; it is not an error.
- Reading is open to everyone, like the lists.
- A model cannot be called `autocomplete`: the path is taken (like `users`).

## Making the query small

A node has the name of each of its parents and traits as a label, so the types asked for are reduced before the query is made (`pangloss_models.autocomplete.smallest_types`): a class that is a subclass of another one asked for (or has the trait asked for) is dropped, as it finds nothing more. `[Poet, Person, Place]` is matched as `n:Person OR n:Place`.

## Calling it from Python

`Entity.autocomplete(search_terms, types=None, page_number=None, page_size=None)` is bound to the entities like `list` is. `types` default to the class it is called on:

```python
await Person.autocomplete("smi")                          # only Persons (and subclasses)
await Entity.autocomplete("smi", types=[Agent, Place])    # either
```

Over the SDK it is one request to the endpoint. The answer is an `AutocompleteResults` (`results`, `count`, `page`, `page_size`, `next_page`, `previous_page`), whose items are `AutocompleteItem`s (`id`, `type`, `label`).

## How it is done

One text search per word of `q` (lower case, cut at anything that is not a letter or digit, the way the index cuts a label, so no punctuation or regular-expression character reaches the index), `.*word.*` for each. A node is kept if it matched **every** word, is an entity with one of the labels, and is not deleted. The query is `pangloss_memgraph/.../build_autocomplete_query.py`.

Two things found while building it:

- The nodes the index finds, collected after the ordering, came back as the *same node* several times. The query collects a map of `id`, `type` and `label` instead of the nodes.
- `list` makes its patterns from the typed text as it is (`.*word.*`) and so does not escape it. I have not found it to break, and I have not tested what the index does with a `(`; it is not part of this change.

## To do later

- **Speed on a big database.** `.*word.*` cannot use the start of a word, so it looks at every term of the index. This is fine for thousands of entities. With the 600,000 nodes of [large data](large-data.md) it has to be measured before it is relied on while the user types. If it is too slow, a prefix pattern (`word.*`) is the fallback, and the interface debounces its requests in any case. A one-letter `q` finds a great deal; the interface may want to wait for two letters.
- **More than the label.** A text index over all the text fields, so that an entity can be found by something other than its label (a name in another field). Not designed. (Note that [every text index costs a commit](large-data.md), and that the existing index is only on `label`.)
- **The XML answer for Oxygen.** Oxygen's author-mode autocomplete expects its own XML format. Probably a `format` parameter or another route over the same function. To be done when the format is known.
- **The per-field route** `GET /api/{Model}/{field}/autocomplete?q=`, which finds the allowed types of a field and calls the same function. The interface already has the types from `export_models()`, so it is not needed yet.
- **The interface.** A relation field that uses it (debounced, with the type shown beside the label). Nothing is added to the interface pages yet.
- **Allowed types for a field.** Nothing checks that the types sent are those of a field; it is a read, so there is nothing to protect, but a client can search types the field would not accept.
- **Searching documents** (to open one, not to refer to it): not wanted for now; `list` with `q` does it per class.
