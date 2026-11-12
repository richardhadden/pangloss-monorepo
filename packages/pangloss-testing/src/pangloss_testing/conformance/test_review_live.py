"""Review (`pangloss-review`) with the data in the database"""

from types import SimpleNamespace
from typing import no_type_check
from uuid import uuid4

import pytest
from pangloss_models import Document, initialise
from pangloss_review import (
    PanglossCommentTargetError,
    PanglossNoSuchCommentError,
    PanglossNotReviewableError,
    PanglossSelfReviewError,
    ReviewMeta,
    ReviewStatus,
    service,
)
from pangloss_users import current_request_username, see_unpublished

from .helpers import DATABASE_NAME

pytestmark = pytest.mark.asyncio(loop_scope="session")


def models():
    class Note(Document):
        text: str

    class Letter(Document):
        _review_meta = ReviewMeta(reviewable=True)
        title: str
        notes: list[Note]

    class Memo(Document):
        title: str

    class Postcard(Letter):  # (inherits that it is reviewed)
        pass

    initialise()
    return Note, Letter, Memo, Postcard


def make_user(db_driver, username):
    db_driver.execute_query(
        "MERGE (:PGUser {username: $username})",
        parameters_={"username": username},
        database=DATABASE_NAME,
    )


@no_type_check
async def test_a_reviewed_document_starts_unpublished_and_is_published_by_checking(
    clear_database, db_driver
):
    Note, Letter, Memo, Postcard = models()
    make_user(db_driver, "reviewer")
    letter = await Letter.Create(
        label="L", title="t", notes=[Note.Create(label="n", text="a")]
    ).save()
    memo = await Memo.Create(label="M", title="t").save()
    postcard = await Postcard.Create(label="P", title="t", notes=[]).save()

    state = await service.get_state(letter.id)
    assert (state.status, state.published) == (ReviewStatus.UNCHECKED, False)
    assert [c.username for c in state.created_by] == ["pangloss_default_user"]
    meta = (await Letter.get(id=letter.id)).meta
    assert (meta.published, meta.review_status) == (False, "unchecked")

    # (only logged-in users see it; a class that is not reviewed is published at once)
    token = see_unpublished.set(False)
    try:
        assert (await Letter.list()).results == []
        assert [m.label for m in (await Memo.list()).results] == ["M"]
    finally:
        see_unpublished.reset(token)
    with pytest.raises(PanglossNotReviewableError):
        await service.get_state(memo.id)
    assert (await service.get_state(postcard.id)).published is False

    queue = await service.queue()
    assert sorted(i.label for i in queue.results) == ["L", "P"]
    assert queue.count == 2

    errors = await service.set_status(
        letter.id, ReviewStatus.ERRORS_FOUND, "reviewer", comment="Wrong date"
    )
    assert (errors.status, errors.published, errors.reviewed_by) == (
        ReviewStatus.ERRORS_FOUND,
        False,
        "reviewer",
    )
    assert errors.open_comments == 1
    assert [i.label for i in (await service.queue()).results] == ["P"]
    found = await service.queue([ReviewStatus.ERRORS_FOUND])
    assert [i.label for i in found.results] == ["L"]

    done = await service.set_status(letter.id, ReviewStatus.PUBLISHED, "reviewer")
    assert done.published is True
    token = see_unpublished.set(False)
    try:
        assert [i.label for i in (await Letter.list()).results] == ["L"]
    finally:
        see_unpublished.reset(token)

    # an edit leaves it published and checked
    await Letter.Update(id=letter.id, label="L", title="changed", notes=[]).save()
    after = await service.get_state(letter.id)
    assert (after.status, after.published) == (ReviewStatus.PUBLISHED, True)
    assert after.last_edited_by == "pangloss_default_user"

    # whoever edits can send it back for checking, which unpublishes it
    sent_back = await service.set_status(letter.id, ReviewStatus.UNCHECKED, "john")
    assert sent_back.published is False


@no_type_check
async def test_comments_on_a_document_and_on_a_part(clear_database, db_driver):
    Note, Letter, *_ = models()
    letter = await Letter.Create(
        label="L", title="t", notes=[Note.Create(label="the note", text="a")]
    ).save()
    note_id = (await Letter.get(id=letter.id)).notes[0].id

    whole = await service.add_comment(letter.id, "ann", "  Needs a source  ")
    part = await service.add_comment(letter.id, "bob", "Check this", target_id=note_id)
    assert whole.text == "Needs a source" and whole.target_id is None
    assert (part.target_id, part.target_label) == (note_id, "the note")

    assert [c.text for c in await service.list_comments(letter.id)] == [
        "Needs a source",
        "Check this",
    ]
    with pytest.raises(PanglossCommentTargetError):
        await service.add_comment(letter.id, "ann", "x", target_id=uuid4())
    with pytest.raises(PanglossNotReviewableError):
        await service.add_comment(uuid4(), "ann", "x")

    # the part is renamed, then gone: the comment still says what it was about
    await Letter.Update(
        id=letter.id,
        label="L",
        title="t",
        notes=[Note.Update(id=note_id, label="renamed", text="a")],
    ).save()
    assert (await service.list_comments(letter.id))[1].target_label == "the note"

    resolved = await service.resolve_comment(letter.id, whole.id, "bob")
    assert resolved.resolved and resolved.resolved_by == "bob"
    assert [c.text for c in await service.list_comments(letter.id)] == ["Check this"]
    assert len(await service.list_comments(letter.id, include_resolved=True)) == 2
    assert (await service.get_state(letter.id)).open_comments == 1
    with pytest.raises(PanglossNoSuchCommentError):
        await service.resolve_comment(letter.id, uuid4(), "bob")


@no_type_check
async def test_a_user_can_be_stopped_from_checking_their_own_work(
    clear_database, db_driver, monkeypatch
):
    from pangloss_core import settings as core_settings

    _, Letter, *_ = models()
    make_user(db_driver, "ann")
    make_user(db_driver, "bob")
    token = current_request_username.set("ann")
    try:
        letter = await Letter.Create(label="L", title="t", notes=[]).save()
    finally:
        current_request_username.reset(token)

    # (allowed unless the setting says no)
    await service.set_status(letter.id, ReviewStatus.UNCHECKED, "ann")

    monkeypatch.setattr(
        core_settings,
        "SETTINGS",
        SimpleNamespace(
            STORAGE=core_settings.SETTINGS.STORAGE,
            REVIEW_ALLOW_SELF_REVIEW=False,
        ),
    )
    with pytest.raises(PanglossSelfReviewError):
        await service.set_status(letter.id, ReviewStatus.PUBLISHED, "ann")
    assert (
        await service.set_status(letter.id, ReviewStatus.PUBLISHED, "bob")
    ).published is True

    # the last editor counts as well
    token = current_request_username.set("bob")
    try:
        await Letter.Update(id=letter.id, label="L", title="u", notes=[]).save()
    finally:
        current_request_username.reset(token)
    with pytest.raises(PanglossSelfReviewError):
        await service.set_status(letter.id, ReviewStatus.PUBLISHED, "bob")
    # (the creator still counts, though somebody else edited it since)
    with pytest.raises(PanglossSelfReviewError):
        await service.set_status(letter.id, ReviewStatus.PUBLISHED, "ann")
    await service.set_status(letter.id, ReviewStatus.PUBLISHED, "cat")


@no_type_check
async def test_the_api(clear_database, db_driver):
    from pangloss_api import create_app
    from pangloss_review import api

    from .test_api_models import client_for, logged_in

    models()
    app = create_app()
    app.include_router(api.router)
    api.configure_app(app, None)

    async with client_for(app) as client:
        ann = await logged_in(client, "ann")
        bob = await logged_in(client, "bob")

        # nothing about review is sent with a create
        made = await client.post(
            "/api/Letter",
            headers=ann,
            json={
                "type": "Letter",
                "label": "L",
                "title": "t",
                "notes": [{"type": "Note", "label": "n", "text": "a"}],
            },
        )
        assert made.status_code == 201, made.text
        id = made.json()["id"]
        memo = await client.post(
            "/api/Memo", headers=ann, json={"type": "Memo", "label": "M", "title": "t"}
        )
        assert memo.status_code == 201

        # it is in the meta of the read, and not for anyone who is not logged in
        meta = (await client.get(f"/api/Letter/{id}", headers=bob)).json()["meta"]
        assert (meta["published"], meta["reviewStatus"]) == (False, "unchecked")
        assert (await client.get(f"/api/Letter/{id}")).status_code == 404
        meta = (await client.get(f"/api/Memo/{memo.json()['id']}")).json()["meta"]
        assert (meta["published"], meta["reviewStatus"]) == (True, None)

        # review needs a login
        assert (await client.get("/api/review/queue")).status_code == 401
        queue = (await client.get("/api/review/queue", headers=bob)).json()
        assert [i["label"] for i in queue["results"]] == ["L"]
        assert [c["username"] for c in queue["results"][0]["createdBy"]] == ["ann"]

        detail = (await client.get(f"/api/review/{id}", headers=bob)).json()
        assert detail["status"] == "unchecked" and detail["comments"] == []
        assert (
            await client.get(f"/api/review/{memo.json()['id']}", headers=bob)
        ).status_code == 404

        part = (await client.get(f"/api/Letter/{id}", headers=bob)).json()["notes"][0][
            "id"
        ]
        comment = await client.post(
            f"/api/review/{id}/comments",
            headers=bob,
            json={"text": "Check this", "targetId": part},
        )
        assert comment.status_code == 201
        assert comment.json()["targetLabel"] == "n"
        bad = await client.post(
            f"/api/review/{id}/comments",
            headers=bob,
            json={"text": "x", "targetId": str(uuid4())},
        )
        assert bad.status_code == 422

        errors = await client.post(
            f"/api/review/{id}/status",
            headers=bob,
            json={"status": "errors_found", "comment": "Wrong"},
        )
        assert errors.status_code == 200
        assert errors.json()["status"] == "errors_found"
        assert len(errors.json()["comments"]) == 2

        resolved = await client.post(
            f"/api/review/{id}/comments/{comment.json()['id']}/resolve", headers=bob
        )
        assert resolved.json()["resolved"] is True
        shown = (await client.get(f"/api/review/{id}", headers=bob)).json()
        assert len(shown["comments"]) == 1
        everything = (
            await client.get(f"/api/review/{id}?resolved=true", headers=bob)
        ).json()
        assert len(everything["comments"]) == 2

        done = await client.post(
            f"/api/review/{id}/status", headers=bob, json={"status": "published"}
        )
        assert done.json()["published"] is True
        # (published: anyone can read it, with its state in the meta)
        read = (await client.get(f"/api/Letter/{id}")).json()
        assert read["meta"]["reviewStatus"] == "published"
        assert (await client.get("/api/review/queue", headers=bob)).json()["count"] == 0


@no_type_check
async def test_lists_and_searches_carry_the_state_and_can_be_filtered(
    clear_database, db_driver
):
    from pangloss_api import create_app
    from pangloss_models import Match
    from pangloss_review import api

    from .test_api_models import client_for, logged_in

    _, Letter, *_ = models()
    await Letter.Create(label="Waiting", title="t", notes=[]).save()
    wrong = await Letter.Create(label="Wrong", title="t", notes=[]).save()
    right = await Letter.Create(label="Right", title="t", notes=[]).save()
    await service.set_status(wrong.id, ReviewStatus.ERRORS_FOUND, "bob")
    await service.set_status(right.id, ReviewStatus.PUBLISHED, "bob")

    def states(found):
        return {
            i.label: (i.meta.published, i.meta.review_status) for i in found.results
        }

    everything = await Letter.list()
    assert states(everything) == {
        "Waiting": (False, "unchecked"),
        "Wrong": (False, "errors_found"),
        "Right": (True, "published"),
    }
    assert states(await Letter.search(Match(where={})))["Right"] == (True, "published")

    def labels(found):
        return sorted(i.label for i in found.results)

    assert labels(await Letter.list(published=True)) == ["Right"]
    assert labels(await Letter.list(published=False)) == ["Waiting", "Wrong"]
    assert labels(await Letter.list(review_status="errors_found")) == ["Wrong"]
    assert labels(await Letter.list(published=False, review_status="unchecked")) == [
        "Waiting"
    ]
    # (and in the other kinds of list, which count and page the same way)
    assert labels(await Letter.list(search_terms="Wr", published=False)) == ["Wrong"]
    assert (
        labels(
            await Letter.list(
                search_terms="Wr", deep_search=True, review_status="published"
            )
        )
        == []
    )

    app = create_app()
    app.include_router(api.router)
    async with client_for(app) as client:
        bob = await logged_in(client, "bob")
        found = await client.get(
            "/api/Letter?published=false&review_status=unchecked", headers=bob
        )
        assert [r["label"] for r in found.json()["results"]] == ["Waiting"]
        assert found.json()["results"][0]["meta"]["reviewStatus"] == "unchecked"
        assert found.json()["count"] == 1
        # not logged in: what is not published is not there, whatever is asked
        assert (await client.get("/api/Letter?published=false")).json()["count"] == 0
        anyone = (await client.get("/api/Letter")).json()
        assert [r["label"] for r in anyone["results"]] == ["Right"]


@no_type_check
async def test_structured_search_by_published_and_review_status(
    clear_database, db_driver
):
    from pangloss_models import Match

    _, Letter, Memo, _ = models()
    await Letter.Create(label="Waiting", title="t", notes=[]).save()
    wrong = await Letter.Create(label="Wrong", title="t", notes=[]).save()
    right = await Letter.Create(label="Right", title="t", notes=[]).save()
    await Memo.Create(label="Memo", title="t").save()
    await service.set_status(wrong.id, ReviewStatus.ERRORS_FOUND, "bob")
    await service.set_status(right.id, ReviewStatus.PUBLISHED, "bob")

    async def find(model, **where):
        found = await model.search(Match(where=where))
        return sorted(i.label for i in found.results)

    assert await find(Letter, published={"eq": False}) == ["Waiting", "Wrong"]
    assert await find(Letter, published={"eq": True}) == ["Right"]
    assert await find(Letter, published={"ne": True}) == ["Waiting", "Wrong"]
    assert await find(Letter, review_status={"eq": "errors_found"}) == ["Wrong"]
    assert await find(Letter, review_status={"in": ["unchecked", "published"]}) == [
        "Right",
        "Waiting",
    ]
    assert await find(Letter, review_status={"exists": True}) == [
        "Right",
        "Waiting",
        "Wrong",
    ]
    # (a document of a class that is not reviewed is published, and has no status)
    assert await find(Memo, published={"eq": True}) == ["Memo"]
    assert await find(Memo, review_status={"exists": True}) == []
    assert await find(
        Letter,
        **{
            "$any_of": [
                {"review_status": {"eq": "published"}},
                {"label": {"eq": "Wrong"}},
            ]
        },
    ) == ["Right", "Wrong"]
    assert await find(Letter, **{"$not": {"published": {"eq": True}}}) == [
        "Waiting",
        "Wrong",
    ]

    # (not logged in: what is not published is not there, whatever is asked)
    token = see_unpublished.set(False)
    try:
        assert await find(Letter, published={"eq": False}) == []
        assert await find(Letter) == ["Right"]
    finally:
        see_unpublished.reset(token)


@no_type_check
async def test_data_that_is_known_to_be_right_can_be_saved_as_published(
    clear_database, db_driver
):
    _, Letter, Memo, _ = models()

    # (create: the default is unchecked; published=True is checked, written with the document)
    plain = await Letter.Create(label="A", title="t", notes=[]).save()
    right = await Letter.Create(label="B", title="t", notes=[]).save(published=True)
    errors = await Letter.Create(label="C", title="t", notes=[]).save(
        review_status="errors_found"
    )
    memo = await Memo.Create(label="M", title="t").save(published=True)  # (ignored)
    assert (await service.get_state(plain.id)).published is False
    state = await service.get_state(right.id)
    assert (state.status, state.published) == (ReviewStatus.PUBLISHED, True)
    assert state.reviewed_by == "pangloss_default_user" and state.reviewed_at
    assert (await service.get_state(errors.id)).status == ReviewStatus.ERRORS_FOUND
    assert (await Memo.get(id=memo.id)).meta.review_status is None
    with pytest.raises(ValueError):
        await Letter.Create(label="D", title="t", notes=[]).save(
            published=True, review_status="published"
        )

    # (published without a login can be read at once)
    token = see_unpublished.set(False)
    try:
        assert [m.label for m in (await Letter.list()).results] == ["B"]
    finally:
        see_unpublished.reset(token)

    # update: leaves the state alone, unless asked
    await Letter.Update(id=right.id, label="B2", title="u", notes=[]).save()
    assert (await service.get_state(right.id)).published is True
    await Letter.Update(id=right.id, label="B3", title="u", notes=[]).save(
        review_status="unchecked"
    )
    state = await service.get_state(right.id)
    assert (state.status, state.published) == (ReviewStatus.UNCHECKED, False)
    await Letter.Update(id=plain.id, label="A2", title="u", notes=[]).save(
        published=True
    )
    assert (await service.get_state(plain.id)).published is True
    assert (await Letter.get(id=plain.id)).title == "u"

    # a block can ask as well (for what is not saved with `save(...)`)
    from pangloss_review.meta import with_status

    with with_status("published"):
        inside = await Letter.Create(label="E", title="t", notes=[]).save()
    assert (await service.get_state(inside.id)).published is True


@no_type_check
async def test_asking_for_a_status_is_refused_when_self_review_is_not_allowed(
    clear_database, db_driver, monkeypatch
):
    from pangloss_core import settings as core_settings
    from pangloss_review import PanglossSelfReviewError

    _, Letter, *_ = models()
    monkeypatch.setattr(
        core_settings,
        "SETTINGS",
        SimpleNamespace(
            STORAGE=core_settings.SETTINGS.STORAGE,
            REVIEW_ALLOW_SELF_REVIEW=False,
        ),
    )
    with pytest.raises(PanglossSelfReviewError):
        await Letter.Create(label="A", title="t", notes=[]).save(published=True)
    assert (await Letter.list()).results == []
    # (without asking, it is as ever)
    assert (
        await service.get_state(
            (await Letter.Create(label="B", title="t", notes=[]).save()).id
        )
    ).published is False


@no_type_check
async def test_the_api_takes_the_status_to_write_as_a_query(clear_database, db_driver):
    from pangloss_api import create_app
    from pangloss_review import api

    from .test_api_models import client_for, logged_in

    models()
    app = create_app()
    app.include_router(api.router)
    api.configure_app(app, None)

    letter = {"type": "Letter", "label": "L", "title": "t", "notes": []}
    async with client_for(app) as client:
        ann = await logged_in(client, "ann")

        made = await client.post(
            "/api/Letter",
            headers=ann,
            params={"review_status": "published"},
            json=letter,
        )
        assert made.status_code == 201, made.text
        id = made.json()["id"]
        # (anyone can read it)
        meta = (await client.get(f"/api/Letter/{id}")).json()["meta"]
        assert (meta["published"], meta["reviewStatus"]) == (True, "published")

        bad = await client.post(
            "/api/Letter", headers=ann, params={"review_status": "great"}, json=letter
        )
        assert bad.status_code == 422

        # (the name in camelCase is the same parameter, and another is refused: the route has none of its own)
        camel = await client.post(
            "/api/Letter",
            headers=ann,
            params={"reviewStatus": "published"},
            json=letter,
        )
        assert camel.status_code == 201, camel.text
        meta = (await client.get(f"/api/Letter/{camel.json()['id']}")).json()["meta"]
        assert (meta["published"], meta["reviewStatus"]) == (True, "published")
        unknown = await client.post(
            "/api/Letter",
            headers=ann,
            params={"review_status": "published", "reviewed": "yes"},
            json=letter,
        )
        assert unknown.status_code == 422
        assert "Unknown query parameter 'reviewed'" in unknown.text

        # (an update with no status keeps it; with one, changes it)
        update = {**letter, "id": id, "title": "u"}
        assert (
            await client.put(
                f"/api/Letter/{id}", headers={**ann, "If-Match": "*"}, json=update
            )
        ).status_code == 200
        assert (await client.get(f"/api/Letter/{id}")).status_code == 200
        assert (
            await client.put(
                f"/api/Letter/{id}",
                headers={**ann, "If-Match": "*"},
                params={"review_status": "errors_found"},
                json=update,
            )
        ).status_code == 200
        assert (await client.get(f"/api/Letter/{id}")).status_code == 404
        meta = (await client.get(f"/api/Letter/{id}", headers=ann)).json()["meta"]
        assert (meta["published"], meta["reviewStatus"]) == (False, "errors_found")

        # (not for anyone who is not logged in)
        assert (
            await client.post(
                "/api/Letter", params={"review_status": "published"}, json=letter
            )
        ).status_code == 401


@no_type_check
async def test_a_document_can_carry_its_own_review_status(clear_database, db_driver):
    _, Letter, Memo, _ = models()

    # (a load in which some items are checked and some are not)
    saved = [
        await Letter.Create(
            label=f"L{n}", title="t", notes=[], review_status=status
        ).save()
        for n, status in enumerate(["published", None, "errors_found", "published"])
    ]
    states = [await service.get_state(letter.id) for letter in saved]
    assert [s.status for s in states] == [
        ReviewStatus.PUBLISHED,
        ReviewStatus.UNCHECKED,
        ReviewStatus.ERRORS_FOUND,
        ReviewStatus.PUBLISHED,
    ]
    assert [s.published for s in states] == [True, False, False, True]
    assert states[0].reviewed_by == "pangloss_default_user"

    token = see_unpublished.set(False)
    try:
        assert sorted(m.label for m in (await Letter.list()).results) == ["L0", "L3"]
    finally:
        see_unpublished.reset(token)

    # (what the document says wins over what the call says; the field is not a field of the document)
    both = await Letter.Create(
        label="B", title="t", notes=[], review_status="published"
    ).save(review_status="unchecked")
    assert (await service.get_state(both.id)).published is True
    assert "review_status" not in (await Letter.get(id=both.id)).model_dump(
        exclude={"meta"}
    )

    # (an update: with the field it changes the state, without it leaves it)
    first = saved[0]
    await Letter.Update(id=first.id, label="L0b", title="u", notes=[]).save()
    assert (await service.get_state(first.id)).published is True
    await Letter.Update(
        id=first.id, label="L0c", title="u", notes=[], review_status="unchecked"
    ).save()
    assert (await service.get_state(first.id)).published is False

    # (a class that is not reviewed ignores it)
    memo = await Memo.Create(label="M", title="t", review_status="published").save()
    assert (await Memo.get(id=memo.id)).meta.review_status is None

    with pytest.raises(ValueError):
        Letter.Create(label="X", title="t", notes=[], review_status="great")


@no_type_check
async def test_the_api_takes_the_review_status_in_the_body(clear_database, db_driver):
    from pangloss_api import create_app
    from pangloss_review import api

    from .test_api_models import client_for, logged_in

    models()
    app = create_app()
    app.include_router(api.router)
    api.configure_app(app, None)

    async with client_for(app) as client:
        ann = await logged_in(client, "ann")
        body = {"type": "Letter", "label": "L", "title": "t", "notes": []}
        checked = await client.post(
            "/api/Letter", headers=ann, json={**body, "reviewStatus": "published"}
        )
        assert checked.status_code == 201, checked.text
        plain = await client.post("/api/Letter", headers=ann, json=body)
        bad = await client.post(
            "/api/Letter", headers=ann, json={**body, "reviewStatus": "great"}
        )
        assert bad.status_code == 422

        assert (
            await client.get(f"/api/Letter/{checked.json()['id']}")
        ).status_code == 200
        assert (
            await client.get(f"/api/Letter/{plain.json()['id']}")
        ).status_code == 404


@no_type_check
async def test_a_bulk_load_record_can_carry_its_review_status(
    clear_database, db_driver
):
    from pangloss_models.bulk_upload import upload, validate

    _, Letter, *_ = models()
    records = [
        (
            1,
            {
                "type": "Letter",
                "label": "A",
                "title": "t",
                "notes": [],
                "review_status": "published",
            },
        ),
        (2, {"type": "Letter", "label": "B", "title": "t", "notes": []}),
        (
            3,
            {
                "type": "Letter",
                "label": "C",
                "title": "t",
                "notes": [],
                "reviewStatus": "errors_found",
            },
        ),
    ]
    assert validate(records) == {"Letter": 3}
    assert await upload(records, concurrency=1) == {"Letter": 3}

    token = see_unpublished.set(False)
    try:
        assert [m.label for m in (await Letter.list()).results] == ["A"]
    finally:
        see_unpublished.reset(token)
    queue = await service.queue(
        [ReviewStatus.UNCHECKED, ReviewStatus.ERRORS_FOUND], None, 1
    )
    assert sorted((i.label, i.status) for i in queue.results) == [
        ("B", ReviewStatus.UNCHECKED),
        ("C", ReviewStatus.ERRORS_FOUND),
    ]


@no_type_check
async def test_a_document_is_given_to_someone_to_review_and_anyone_may_take_it_over(
    clear_database, db_driver
):
    from pangloss_review import PanglossAssignmentError
    from pangloss_review.meta import assigned_to

    Note, Letter, Memo, Postcard = models()
    for name in ("ann", "bob"):
        make_user(db_driver, name)

    # (with the create: `save(review_assigned_to=...)`, or around it)
    given = await Letter.Create(label="Given", title="t", notes=[]).save(
        review_assigned_to="ann"
    )
    with assigned_to("bob"):
        around = await Letter.Create(label="Around", title="t", notes=[]).save()
    free = await Letter.Create(label="Free", title="t", notes=[]).save()
    # (a class that is not reviewed is given to no one)
    await Memo.Create(label="M", title="t").save(review_assigned_to="ann")
    state = await service.get_state(given.id)
    assert (state.assigned_to, state.assigned_by) == ("ann", "pangloss_default_user")
    assert state.assigned_at is not None
    assert (await service.get_state(around.id)).assigned_to == "bob"
    assert (await service.get_state(free.id)).assigned_to is None

    # the queue, of everyone, of one person, of no one
    def labels(queue):
        return sorted(item.label for item in queue.results)

    assert labels(await service.queue()) == ["Around", "Free", "Given"]
    mine = await service.queue(assigned_to="ann")
    assert labels(mine) == ["Given"] and mine.results[0].assigned_to == "ann"
    assert labels(await service.queue(assigned_to="")) == ["Free"]

    # an update keeps it
    await Letter.Update(id=given.id, label="Given", title="changed", notes=[]).save()
    assert (await service.get_state(given.id)).assigned_to == "ann"

    # anyone takes it for themselves, whoever has it; only an admin gives it to another
    taken = await service.assign(given.id, "bob", "bob", admin=False)
    assert (taken.assigned_to, taken.assigned_by) == ("bob", "bob")
    with pytest.raises(PanglossAssignmentError, match="Only an admin"):
        await service.assign(given.id, "ann", "bob", admin=False)
    with pytest.raises(PanglossAssignmentError, match="Only an admin"):
        await service.assign(given.id, None, "ann", admin=False)
    assert (
        await service.assign(given.id, "ann", "root", admin=True)
    ).assigned_to == "ann"
    with pytest.raises(PanglossAssignmentError, match="no user 'nobody'"):
        await service.assign(given.id, "nobody", "root", admin=True)
    # giving it up
    dropped = await service.assign(given.id, None, "ann", admin=False)
    assert (dropped.assigned_to, dropped.assigned_by, dropped.assigned_at) == (
        None,
        None,
        None,
    )


@no_type_check
async def test_the_queue_is_searched_by_the_words_of_the_labels(
    clear_database, db_driver
):
    Note, Letter, Memo, Postcard = models()
    for label in ("Letter to Ghent", "A letter from Bruges", "Report on Ghent"):
        await Letter.Create(label=label, title="t", notes=[]).save()

    def labels(queue):
        return sorted(item.label for item in queue.results)

    # (every word, anywhere in the label, whatever the case)
    assert labels(await service.queue(q="ghent")) == [
        "Letter to Ghent",
        "Report on Ghent",
    ]
    assert labels(await service.queue(q="LETTER ghent")) == ["Letter to Ghent"]
    assert labels(await service.queue(q="ett")) == [
        "A letter from Bruges",
        "Letter to Ghent",
    ]
    found = await service.queue(q="antwerp")
    assert (found.results, found.count) == ([], 0)
    # (nothing asked for: all of them)
    assert (await service.queue(q="  ")).count == 3


async def test_assigning_over_the_api(clear_database, db_driver):
    from pangloss_api import create_app
    from pangloss_review import api
    from pangloss_users import service as users

    from .test_api_models import PASSWORD, client_for, logged_in

    models()
    app = create_app()
    app.include_router(api.router)
    api.configure_app(app, None)
    await users.create_user("root", "root@example.com", PASSWORD, admin=True)

    async with client_for(app) as client:
        ann = await logged_in(client, "ann")
        bob = await logged_in(client, "bob")
        root = await logged_in(client, "root")
        body = {"type": "Letter", "label": "L", "title": "t", "notes": []}

        # with the create: an admin gives it to anyone; others only to themselves; the user must exist
        refused = await client.post(
            "/api/Letter", params={"review_assigned_to": "bob"}, headers=ann, json=body
        )
        assert refused.status_code == 403, refused.text
        unknown = await client.post(
            "/api/Letter",
            params={"reviewAssignedTo": "nobody"},
            headers=root,
            json=body,
        )
        assert unknown.status_code == 422, unknown.text
        made = await client.post(
            "/api/Letter",
            params={"review_assigned_to": "bob", "review_status": "checked"},
            headers=root,
            json=body,
        )
        assert made.status_code == 201, made.text
        id = made.json()["id"]
        own = await client.post(
            "/api/Letter",
            params={"review_assigned_to": "ann"},
            headers=ann,
            json={**body, "label": "Own"},
        )
        assert own.status_code == 201, own.text
        # (`checked`, the earlier name of the status, is still taken)
        detail = (await client.get(f"/api/review/{id}", headers=ann)).json()
        assert (detail["assignedTo"], detail["assignedBy"]) == ("bob", "root")
        assert (detail["status"], detail["published"]) == ("published", True)

        # the queue of one's own, of another (an admin's to ask), of no one
        def queue(headers, **params):
            return client.get(
                "/api/review/queue",
                headers=headers,
                params={"status": ["unchecked", "published"], **params},
            )

        mine = (await queue(bob, assigned_to="me")).json()
        assert [(i["label"], i["assignedTo"]) for i in mine["results"]] == [
            ("L", "bob")
        ]
        assert (await queue(ann, assignedTo="bob")).status_code == 403
        assert [
            i["label"] for i in (await queue(root, assigned_to="ann")).json()["results"]
        ] == ["Own"]
        assert (await queue(ann, assigned_to="none")).json()["results"] == []

        # taking it over, and giving it to another
        taken = await client.post(
            f"/api/review/{id}/assign", headers=ann, json={"username": "ann"}
        )
        assert taken.status_code == 200, taken.text
        assert taken.json()["assignedTo"] == "ann"
        assert (
            await client.post(
                f"/api/review/{id}/assign", headers=ann, json={"username": "bob"}
            )
        ).status_code == 403
        given = await client.post(
            f"/api/review/{id}/assign", headers=root, json={"username": None}
        )
        assert given.json()["assignedTo"] is None


@no_type_check
async def test_heads_made_together_are_reviewed_as_each_would_be_alone(
    clear_database, db_driver
):
    from pangloss_models import create_heads

    Note, Letter, Memo, _ = models()
    letter, memo = await create_heads(
        Letter.Create(label="L", title="t", notes=[]), Memo.Create(label="M", title="t")
    )

    assert (await service.get_state(letter.id)).status == ReviewStatus.UNCHECKED
    assert (await Memo.get(id=memo.id)).meta.published is True
