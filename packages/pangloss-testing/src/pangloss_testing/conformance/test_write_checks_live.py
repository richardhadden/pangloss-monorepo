"""What a declared class does when it is written, on either backend: `@before_create` and `@before_update` read the
database and refuse a write (nothing is written; a 422 over the API, at the field it names); a `@create_validator` or
`@update_validator` fills in what only the database has; pydantic's validators run once a save."""

from typing import Annotated, no_type_check

import httpx2 as httpx
import pytest
from pangloss_api import create_app
from pangloss_models import (
    DBField,
    Document,
    Entity,
    Match,
    PanglossWriteRefused,
    before_create,
    before_update,
    create_validator,
    initialise,
    update_validator,
)
from pangloss_users import service
from pydantic import model_validator

from .helpers import run

pytestmark = pytest.mark.asyncio(loop_scope="session")


@no_type_check
def declare():
    class Person(Entity):
        @before_create
        async def label_is_new(self):
            # (the database, read by the models)
            found = await Person.search(Match(where={"label": {"eq": self.label}}))
            if found.results:
                raise PanglossWriteRefused(
                    f"There is already a person called {self.label}", field="label"
                )

    class Letter(Document):
        text: str
        sent: bool = False
        words: Annotated[int | None, DBField] = None
        edits: Annotated[int | None, DBField] = None

        @before_update
        async def not_after_it_was_sent(self, previous):
            if previous.sent and self.text != previous.text:
                raise PanglossWriteRefused(
                    "A letter that was sent cannot be changed", field="text"
                )

        @create_validator
        def count(self):
            self.words, self.edits = len(self.text.split()), 0

        @update_validator
        def recount(self):
            self.words, self.edits = len(self.text.split()), 1

    initialise()
    return Person, Letter


@no_type_check
async def test_before_create_reads_the_database_and_refuses(db_driver, clear_database):
    Person, _ = declare()

    await Person.Create(label="Jane").save()
    with pytest.raises(
        PanglossWriteRefused, match="already a person called Jane"
    ) as refused:
        await Person.Create(label="Jane").save()
    assert refused.value.field == "label"
    assert len(run(db_driver, "MATCH (n:Person) RETURN n")) == 1


@no_type_check
async def test_before_update_is_given_the_head_as_it_is_now(db_driver, clear_database):
    _, Letter = declare()

    letter = await Letter.Create(label="L", text="Dear sir").save()
    await Letter.Update(id=letter.id, label="L", text="Dear madam", sent=True).save()
    with pytest.raises(PanglossWriteRefused, match="was sent cannot be changed"):
        await Letter.Update(id=letter.id, label="L", text="Hello", sent=True).save()
    assert (await Letter.get(letter.id)).text == "Dear madam"
    # (what it does not refuse is written)
    await Letter.Update(
        id=letter.id, label="Renamed", text="Dear madam", sent=True
    ).save()
    assert (await Letter.get(letter.id)).label == "Renamed"


@no_type_check
async def test_create_and_update_validators_fill_in_what_is_stored(
    db_driver, clear_database
):
    _, Letter = declare()

    letter = await Letter.Create(label="L", text="one two three").save()
    node = run(db_driver, "MATCH (n:Letter) RETURN n")[0]["n"]
    assert (node["words"], node["edits"]) == (3, 0)

    await Letter.Update(id=letter.id, label="L", text="one two").save()
    node = run(db_driver, "MATCH (n:Letter) RETURN n")[0]["n"]
    assert (node["words"], node["edits"]) == (2, 1)


@no_type_check
async def test_a_model_validator_runs_once_a_save(clear_database):
    calls = []

    class Note(Document):
        tags: list[str] = []

        @model_validator(mode="after")
        def mark(self):
            calls.append(type(self).__name__)
            self.tags.append("checked")
            return self

    initialise()

    saved = await Note.Create(label="n").save()
    assert calls == ["NoteCreate"]
    assert (await Note.get(saved.id)).tags == ["checked"]


@no_type_check
async def test_a_refusal_over_the_api_is_a_422_at_its_field(clear_database):
    declare()

    app = create_app()
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        await service.create_user("john", "john@example.com", "correct horse")
        token = (
            await client.post(
                "/api/users/token",
                data={"username": "john", "password": "correct horse"},
            )
        ).json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        assert (
            await client.post(
                "/api/Person", json={"type": "Person", "label": "Jane"}, headers=headers
            )
        ).status_code == 201
        response = await client.post(
            "/api/Person", json={"type": "Person", "label": "Jane"}, headers=headers
        )
        assert response.status_code == 422
        assert response.json()["error"] == "PanglossWriteRefused"
        assert response.json()["detail"] == [
            {
                "loc": ["body", "label"],
                "msg": "There is already a person called Jane",
                "type": "refused",
            }
        ]


@no_type_check
def declare_nested():
    seen = []

    class Clause(Document):
        text: str
        signed: bool = False

        @before_create
        async def no_blank(self):
            seen.append(("create", self.text))
            if not self.text.strip():
                raise PanglossWriteRefused("A clause needs a text", field="text")

        @before_update
        async def not_once_signed(self, previous):
            seen.append(("update", self.text, previous.text))
            if previous.signed and self.text != previous.text:
                raise PanglossWriteRefused(
                    "A signed clause cannot be changed", field="text"
                )

    class Contract(Document):
        clauses: list[Clause]

    initialise()
    return Contract, Clause, seen


@no_type_check
async def test_a_nested_document_is_checked_when_its_head_is_made(
    db_driver, clear_database
):
    Contract, _, seen = declare_nested()

    with pytest.raises(PanglossWriteRefused, match="needs a text"):
        await Contract.Create(
            label="C",
            clauses=[
                {"type": "Clause", "label": "1", "text": "Pay"},
                {"type": "Clause", "label": "2", "text": " "},
            ],
        ).save()
    assert run(db_driver, "MATCH (n:Contract) RETURN n") == []
    assert seen == [("create", "Pay"), ("create", " ")]


@no_type_check
async def test_a_nested_document_is_checked_against_itself_as_it_is_when_its_head_is_updated(
    clear_database,
):
    Contract, _, seen = declare_nested()

    contract = await Contract.Create(
        label="C",
        clauses=[{"type": "Clause", "label": "1", "text": "Pay", "signed": True}],
    ).save()
    edit = (await Contract.get(contract.id)).model_dump()
    clause = edit["clauses"][0]
    seen.clear()

    with pytest.raises(PanglossWriteRefused, match="signed clause cannot be changed"):
        await Contract.Update(
            id=contract.id, label="C", clauses=[{**clause, "text": "Pay later"}]
        ).save()
    assert seen == [("update", "Pay later", "Pay")]
    assert (await Contract.get(contract.id)).clauses[0].text == "Pay"

    # (one added in an update is new: its before_create is what runs)
    seen.clear()
    await Contract.Update(
        id=contract.id,
        label="C",
        clauses=[clause, {"type": "Clause", "label": "2", "text": "Deliver"}],
    ).save()
    assert seen == [("update", "Pay", "Pay"), ("create", "Deliver")]
    assert [c.text for c in (await Contract.get(contract.id)).clauses] == [
        "Pay",
        "Deliver",
    ]


@no_type_check
async def test_an_entity_made_in_a_document_is_checked_as_a_new_one(
    db_driver, clear_database
):
    from uuid import uuid7

    class Person(Entity):
        _meta = Entity.Meta(create_inline=True, create_with_id=True)

        @before_create
        async def not_anonymous(self):
            if self.label == "Anonymous":
                raise PanglossWriteRefused("Name the person", field="label")

    class Statement(Document):
        about: Person

    initialise()

    with pytest.raises(PanglossWriteRefused, match="Name the person"):
        await Statement.Create(
            label="S",
            about={
                "type": "Person",
                "id": uuid7(),
                "label": "Anonymous",
                "create_new": True,
            },
        ).save()
    assert run(db_driver, "MATCH (n:Person) RETURN n") == []


@no_type_check
async def test_a_bulk_load_runs_the_checks_and_stops_at_the_record_refused(
    db_driver, clear_database
):
    from pangloss_models.bulk_upload import upload
    from pangloss_models.exceptions import PanglossBulkRecordError

    class Letter(Document):
        text: str

        @before_create
        async def no_blank(self):
            if not self.text:
                raise PanglossWriteRefused("A letter needs a text", field="text")

    initialise()

    records = [
        (1, {"type": "Letter", "label": "A", "text": "one"}),
        (2, {"type": "Letter", "label": "B", "text": ""}),
        (3, {"type": "Letter", "label": "C", "text": "three"}),
    ]
    with pytest.raises(
        PanglossBulkRecordError, match="A letter needs a text"
    ) as failed:
        await upload(records, concurrency=1)
    assert failed.value.line == 2
    # (what came before it stays written; it and what comes after are not)
    assert [n["n"]["label"] for n in run(db_driver, "MATCH (n:Letter) RETURN n")] == [
        "A"
    ]


@no_type_check
async def test_a_nested_refusal_says_where_it_is(clear_database):
    Contract, _, _ = declare_nested()

    with pytest.raises(PanglossWriteRefused) as refused:
        await Contract.Create(
            label="C",
            clauses=[
                {"type": "Clause", "label": "1", "text": "Pay"},
                {"type": "Clause", "label": "2", "text": ""},
            ],
        ).save()
    assert refused.value.path == ("clauses", 1, "text")

    app = create_app()
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        await service.create_user("john", "john@example.com", "correct horse")
        token = (
            await client.post(
                "/api/users/token",
                data={"username": "john", "password": "correct horse"},
            )
        ).json()["access_token"]
        response = await client.post(
            "/api/Contract",
            json={
                "type": "Contract",
                "label": "C",
                "clauses": [{"type": "Clause", "label": "1", "text": ""}],
            },
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 422
        assert response.json()["detail"][0]["loc"] == ["body", "clauses", 0, "text"]
