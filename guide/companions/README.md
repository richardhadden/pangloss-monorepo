# Documents made with a new entity (companions)

When someone writing a factoid makes a new person, it is the moment to ask what the source calls them, and their gender.
These are not fields of the person: they are claims of a source, so they are statements, in a factoid of their own. A
**companion** is such a document, offered under the form of a new entity and written with it if anything in it is filled
in. The full description, and what is built, is in [companion documents](../../implementation_docs/companion-documents.md).

## Declaring one

On the entity, in its `Meta`. The names are strings, because the entity is usually declared before the documents that
refer to it; `initialise()` (and the language server) check them.

```python
from pangloss_models import Companion, CompanionPart, CopyFromOuter, Document, Entity, Standalone, Within


class Person(Entity):
    _meta = Entity.Meta(
        companions=[
            Companion(
                name="naming_and_gender",
                document="Factoid",                     # what is made with the person
                field="statements",                     # its list of parts
                parts=[
                    CompanionPart(type="Naming", entity_field="named"),       # the person goes in `named`
                    CompanionPart(type="Gendering", entity_field="gendered"),
                ],
                copies=[CopyFromOuter(field="source")],  # the source of the factoid the person is made from
                offered=[Within(heads=["Factoid"]), Standalone()],
            )
        ]
    )


class Naming(Statement):  # (a statement of the project, held by a Factoid)
    named: Person
    first_name: str | None = None
    family_name: str | None = None
    title: str | None = None
```

- `offered` says where it is offered: `Within(heads=[...])` in the form of a document of those types (and the types
  below them), narrowed if you like by `fields=["Statement.involves"]` (the relation the person is made from, with the
  fields that stand for it) and `holders=[...]` (the type of the document that has the relation); `Standalone()` where
  the person is made on its own (its own new page). With nothing, everywhere.
- Without `field`, the companion is itself the one part: `Companion(name="note", document="Note", entity_field="about")`.
- A subclass of the entity has its companions too; `companions=[]` on it has none.
- Changing a companion is not a migration: it is not data.

## In the interface

The dialog that makes a person from a factoid's form shows, under the person's fields, a factoid with a naming and a
gendering, its source filled in from the factoid behind (it can be changed), and the person in each part, named as the
person's label is typed. Fill in anything of a part and Save makes the person and the factoid, with only the parts that
were filled in; fill in nothing and only the person is made. On the page of a new person the same factoid is offered,
with the source to be given.

Parts cannot be added or removed in the companion. A part that is filled in is checked like any document: a required
field left empty is red, and nothing is saved.

## From Python and over the API

```python
person, [factoid] = await Person.Create(label="John of Gaunt").save_with_companions(
    {
        "naming_and_gender": {
            "source": {"type": "AtPage", "page": "12", "target": [{"type": "Source", "id": source_id}]},
            "statements": [{"type": "Naming", "first_name": "John"}],
        }
    }
)
```

Over HTTP it is `POST /api/Person/with-companions` with `{"item": {...}, "companions": [{"name": ..., "document":
{...}}]}`. The entity is put in its places by the server: leave it out. All of it is written in one transaction, or none
of it; `from pangloss_models import create_heads` does the same for any documents and entities you give it.
