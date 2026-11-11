# Labels worked out from what an item holds

Every document and entity has a label: the line that names it in lists, in chips, in search results. Typing one for
each nested document is tedious when it only repeats what the document says. A **label template** says how to build
the label from the fields, so that nobody has to type it:

```python
class Bequest(Document):
    item: str
    recipient: Person

    _meta = Document.Meta(label_template="{item} to {recipient}")
```

A bequest of "a silver cup" to Judith Quiney is labelled *a silver cup to Judith Quiney*. The form fills the label in
as you type, and the server works it out again when the item is saved. A user who wants a different label can still
write one.

🚧 Label templates are new (2026-11-11) and may change. The design, and what is not built yet, are in
[the reference](../../implementation_docs/label-templates.md).

## Contents

- [A first template](#a-first-template)
- [Where a template goes](#where-a-template-goes)
- [Placeholders and paths](#placeholders-and-paths)
- [Optional parts](#optional-parts)
- [Alternatives](#alternatives)
- [Filters](#filters)
- [What a value reads as](#what-a-value-reads-as)
- [Nested documents](#nested-documents)
- [Reified relations, conjunctions and semantic spaces](#reified-relations-conjunctions-and-semantic-spaces)
- [Dates, and formatters of your own](#dates-and-formatters-of-your-own)
- [Special characters](#special-characters)
- [In the form, and when it is saved](#in-the-form-and-when-it-is-saved)
- [Mistakes it catches](#mistakes-it-catches)
- [Writing labels that read well](#writing-labels-that-read-well)
- [Quick reference](#quick-reference)

The examples use these models:

```python
from pangloss_dates import Date
from pangloss_models import Conjunction, Document, Entity, LabelTemplate, ReifiedRelation


class Person(Entity):
    forename: str | None = None
    surname: str | None = None


class Place(Entity):
    pass


class Identification[T](ReifiedRelation[T]):
    certainty: int | None = None


class Witnesses[T](Conjunction):
    witness: list[T]


class Bequest(Document):
    item: str
    recipient: Person


class Will(Document):
    testator: Person
    made_at: Place | None
    date: Date | None
    bequests: list[Bequest]
    witnesses: Witnesses[Person] | None = None
```

## A first template

Text, with field names in braces:

```python
class Will(Document):
    ...
    _meta = Document.Meta(label_template="Will of {testator}")
```

`{testator}` is the field; a person reads as their label, so the will of Anne Hathaway is *Will of Anne Hathaway*.
Spaces in a label are tidied: runs of them become one, and those at the ends go.

## Where a template goes

`label_template` is an option of `Meta`, on any kind of model, and a subclass has its parent's unless it gives its own.
What the template is for depends on the kind:

| Kind | The template |
|---|---|
| `Document`, `Entity`, `ReifiedRelationDocument` | **is the label**: kept as the item's label, unless someone writes their own |
| `ReifiedRelation`, `Conjunction`, `SemanticSpace`, `Embedded` | has no label of its own to fill: it says **how it reads inside the label of what holds it** |

So an entity can build its own label from its fields:

```python
class Person(Entity):
    forename: str | None = None
    surname: str | None = None

    _meta = Entity.Meta(label_template=LabelTemplate("{forename} {surname}", "{surname}"))
```

A string is one template; `LabelTemplate(...)` takes several (see [Alternatives](#alternatives)).

A template is not data: adding one, or changing it, needs no migration. Items already in the database keep their
labels until they are next saved.

## Placeholders and paths

A placeholder is a field name in braces: `{item}`. The names are the Python ones (`made_at`, not `madeAt`).

A **path** goes on into what a field holds, with dots: `{bequests.recipient}` is the recipient of each bequest. Through
a list a path takes every item, so for a will of two bequests `{bequests.recipient}` gives two people, joined with
`", "` unless a [filter](#filters) says otherwise.

A path can go into a nested document, an embedded object, a reified relation or a conjunction, but **not into an
entity or a document that is only referred to**: what a form or a save has of those is their label, and nothing else.
`{testator}` is fine; `{testator.surname}` is refused when the models are initialised.

A path that names a field a [wrapper](#reified-relations-conjunctions-and-semantic-spaces) does not have goes through it
to what it holds: if `bequests` were `list[Identification[Bequest]]`, `{bequests.item}` would still reach the item of
each bequest, while `{bequests.certainty}` is the identification's own field.

## Optional parts

Square brackets mark a **group**: it is left out if any placeholder in it is empty.

```python
"Will of {testator}[ at {made_at}][, {date}]"
```

| Filled in | Label |
|---|---|
| testator, place and date | *Will of Anne Hathaway at Stratford, 4 March 1601* |
| testator and date | *Will of Anne Hathaway, 4 March 1601* |
| testator only | *Will of Anne Hathaway* |

Put the words that belong to an optional field (" at", ", ") inside its group, so they go with it. Groups can be nested.

A placeholder that is empty **outside** any group makes the whole template give nothing (see the next section).

## Alternatives

`LabelTemplate(a, b, ...)` tries each template in turn, and takes the first that gives a label, that is the first
with no empty placeholder outside a group:

```python
_meta = Entity.Meta(label_template=LabelTemplate("{forename} {surname}", "{surname}", "{forename}"))
```

| Filled in | Label |
|---|---|
| Anne, Hathaway | *Anne Hathaway* |
| Hathaway | *Hathaway* |
| Anne | *Anne* |

Use groups for what is optional, and alternatives for wording that changes with what is there.

If none gives a label, the label is empty, and an item that must have a label is refused when it is saved (the form
shows the label in red first). Write one by hand, or fill in what the template names.

## Filters

A placeholder can pass its values through filters, each after a `|`, in order:

```python
"{bequests|join("; ")}"
"{bequests|each("{item} to {recipient}")|join("; ", " and ")}"
```

The text a filter takes is in double quotes.

| Filter | Does | Example, for a will with bequests of a cup and a bed |
|---|---|---|
| `join("sep")` | Joins the values with `sep` (`", "` if not given) | `{bequests\|join("; ")}`: *a cup to Judith; a bed to Anne* |
| `join("sep", "last")` | The same, with `last` before the last value | `{bequests\|join(", ", " and ")}`: *a cup to Judith and a bed to Anne* |
| `each("template")` | Writes each value with a template of its own, whose paths start at that value | `{bequests\|each("{item}")}`: *a cup, a bed* |
| `first`, `last` | Keeps the first, or the last, value | `{bequests\|first}`: *a cup to Judith* |
| `count` | How many values there are; **empty if there are none** | `{bequests\|count}`: *2* |
| `default("text")` | `text` if there is nothing | `{made_at\|default("an unknown place")}` |
| `lower` | In lower case | `{item\|lower}` |
| `capitalise` | With a capital first letter | `{item\|capitalise}`: *A cup* |

Because `count` of nothing is empty, a group with a count drops out when there is nothing to count:
`[: {bequests|count} bequests]`.

`join` with no filter before it is what a placeholder does anyway, so `{bequests}` and `{bequests|join}` are the same.

## What a value reads as

| The value is | It reads as |
|---|---|
| Text | itself; empty text is empty |
| A number | as written: *2*, *1.5* |
| A choice (an enum) | its stored value: *witness* (not the translated name) |
| A date (`datetime.date`) | as stored: *1601-03-04*. A date of `pangloss-dates` reads better: see [Dates](#dates-and-formatters-of-your-own) |
| A reference to an entity or a document | its label |
| A nested document, or an entity made with the document | its label: worked out first by its own template if it has one, or as written |
| A reified relation, conjunction or semantic space | its own template if it has one; if not, what it holds (see [below](#reified-relations-conjunctions-and-semantic-spaces)) |
| An embedded object | its template, or its formatter. One with neither cannot be written: name one of its fields instead |
| A list | its items, each as above, joined with `", "` |
| A yes-or-no field | refused: a label would say *true* or *false* |

## Nested documents

A nested document's own label is worked out **before** the label of what holds it, so an outer template can use the
inner labels. There are three ways to bring what a nested document holds into the outer label, from the simplest:

```python
class Bequest(Document):
    item: str
    recipient: Person
    _meta = Document.Meta(label_template="{item} to {recipient}")


class Will(Document):
    ...
    # 1. by its label
    _meta = Document.Meta(label_template='Will of {testator}[: {bequests|join("; ")}]')
```

*Will of Anne Hathaway: a silver cup to Judith Quiney; the second-best bed to Anne Hathaway*

```python
    # 2. a field of each, by a path
    _meta = Document.Meta(label_template='Will of {testator}[, to {bequests.recipient|join(", ", " and ")}]')
```

*Will of Anne Hathaway, to Judith Quiney and Anne Hathaway*

```python
    # 3. each in words of the will's own
    _meta = Document.Meta(label_template='Will of {testator}[: {bequests|each("{item} (to {recipient})")|join("; ")}]')
```

*Will of Anne Hathaway: a silver cup (to Judith Quiney); the second-best bed (to Anne Hathaway)*

If someone wrote a bequest's label by hand, the first way uses what they wrote; the other two use its fields whatever
its label says.

What sets the nested parts apart is your own punctuation: brackets, semicolons, a dash. There is no quoting of its
own. Nested labels with commas in them, inside a list joined with commas, are hard to read: join with `"; "`, or put
brackets round them.

## Reified relations, conjunctions and semantic spaces

These **wrappers** have no label of their own. Unless one has a template, it reads as **what it holds**: a reified
relation as its `target`, a conjunction or a semantic space as everything in its relations. So with
`recipient: Identification[Person]`, `{recipient}` is the person.

At the end of a path, a wrapper without a template is opened: `join`, `count` and the placeholder's text take what is
in it. With `witnesses: Witnesses[Person]`:

```python
"Will of {testator}[, witnessed by {witnesses|join(", ", " and ")}]"
```

*Will of Anne Hathaway, witnessed by Francis Collins, Julyne Shaw and Hamnet Sadler*

`each`, `first` and `last` take the wrappers themselves, so that `each` can name their own fields. With
`witnesses: list[Identification[Person]]`:

```python
'{witnesses|each("{target}[ (certainty {certainty})]")|join("; ")}'
```

*Francis Collins (certainty 2); Julyne Shaw*

A wrapper with a template of its own reads by that template, wherever it is. A template on a semantic space says what
the space means:

```python
class Negative[T](SemanticSpace[T]):
    _meta = SemanticSpace.Meta(label_template="not: {contents}")
```

## Dates, and formatters of your own

A date of `pangloss-dates` reads as a person would say it, with no template of yours: `{date}` gives *4 March 1601*,
*1500 to 1502 (julian)*, *every year on Easter + 49 days, 1450 – 1530*. That is a **formatter**: a function, kept in
Python and in the interface's module under one name, that `Date` names in its `Meta`.

An embedded model of your own can have a template (`label_template="{number} {unit}"`), or, when that is not enough, a
formatter. A formatter is given the object as the interface holds it (camelCase JSON) and gives its text, or `None`:

```python
from pangloss_models import Embedded, Formatter, register_label_formatter


def say_measure(value):
    return f"{value['number']} {value['unit']}" if value.get("number") is not None else None


register_label_formatter("my_app:measure", say_measure)


class Measure(Embedded):
    number: int
    unit: str

    _meta = Embedded.Meta(label_template=Formatter("my_app:measure"))
```

And the same function in your app's [interface module](../interface/README.md), under the name after the colon:

```ts
export default defineModule({
  name: "my_app",
  components: {},
  labelFormatters: {
    measure: (value) => (value.number != null ? `${value.number} ${value.unit}` : undefined),
  },
});
```

The two must give the same text: the form shows what the TypeScript gives, the server keeps what the Python gives.
Formatters are in English for now.

## Special characters

`{`, `}`, `[`, `]` and `\` have meanings. To write one as itself, put a `\` before it: `\[?\]` gives *[?]*. In a Python
string that is `"\\[?\\]"`, or a raw string, `r"\[?\]"`.

Inside the quotes of a filter, `\"` is a quote and `\\` a backslash. The template of `each` is itself a template, so
`each("\\[{item}\\]")` gives *[a cup]*.

Watch for brackets meant as text: `"Ordered: [{thing}]"` makes a group, not brackets round the thing. Use round
brackets, or `\[`.

## In the form, and when it is saved

**In the form**, a label that its template works out is greyed out and cannot be typed in. It fills itself in as the
fields are, nested documents first. Beside it:

- the **pencil** (*Write the label by hand*) unlocks it, keeping its text so you can change it;
- **↺** (*Work the label out from what is filled in*) on a label written by hand locks it again and works it out.

Opening an item does not work its labels out again: they are as they were saved until something is changed.

**When it is saved**, the server works out every automatic label again, from what the item holds and the labels the
database has for what it refers to. It keeps its own result, so the form, a script and a bulk load all give the same
label. Each such item records whether its label is worked out: `label_auto` (`labelAuto` in JSON).

| Sent | Kept |
|---|---|
| No label | worked out; `label_auto` true |
| `label_auto: true` (whatever the label) | worked out; `label_auto` true |
| A label, and no `label_auto` | the label as sent; `label_auto` false |
| A label, and `label_auto: false` | the label as sent |

So in a script, leave the label out to have it worked out:

```python
await Will.Create(testator={"type": "Person", "id": anne.id}, made_at=None, bequests=[]).save()
```

and give one to keep it. A label is kept as it was made: if Anne Hathaway is later renamed, the will's label keeps the
old name until the will is next saved.

## Mistakes it catches

A template is read when it is declared, and checked against the models when they are initialised, so a mistake stops
the server, and `pangloss check` and the language server show it at its line:

| Mistake | What it says |
|---|---|
| A brace or a bracket left open, an unknown filter | `label_template 'Will of {testator': a } expected (at 17)`; `there is no filter 'jion'. Did you mean 'join'?` |
| A field that is not there | `Will has no field 'testatr'. Did you mean 'testator'?` |
| A path into an entity | `'testator' is a reference to Person, of which a label can only use the label, not 'surname'` |
| A yes-or-no field | `'sent' is a yes-or-no field, ...` |
| An embedded object with no template or formatter | `'size' is an embedded Measure, which has no label_template of its own (nor a Formatter)` |
| A formatter no app has registered | `no formatter of that name is registered` |

## Writing labels that read well

- **Say what matters first.** Lists cut long labels short; put the words that tell items apart at the start.
- **Keep them short.** `{statements|first}` with a count is easier to read than every statement joined.
- **Put optional words inside their group**: `[ at {place}]`, not ` at [{place}]`.
- **Join lists with "and" or "or"** where a person would: `join(", ", " and ")`.
- **Mind numbers**: there is no plural yet, so `{bequests|count} bequests` says *1 bequests*. Write `bequests:
  {bequests|count}`, or leave the count out.
- **Mind other languages.** A template is in one language. A sentence that puts a nested label inside another (*that
  …*, *because …*) works in English, but in German the verb moves to the end after *dass* or *weil*, and a label with
  an article cannot change its case. A **list style** works in any language: `"Übergabe: {quantity} × {item}; von
  {given_by}; an {given_to}"`. See [the trial](../../implementation_docs/label-templates.md#the-trial-readable-english-and-german-2026-11-11).

## Quick reference

```
template     text, {placeholders} and [groups]
{field}      a field;  {a.b}  a path into what a field holds (not into an entity)
[ ... ]      left out if a placeholder in it is empty
LabelTemplate("a", "b")   the first that has no empty placeholder outside a group

|join("sep")  |join("sep", "last")  |each("template")  |first  |last
|count  |default("text")  |lower  |capitalise

\{ \} \[ \] \\      the characters themselves;  \" inside a filter's text
```
