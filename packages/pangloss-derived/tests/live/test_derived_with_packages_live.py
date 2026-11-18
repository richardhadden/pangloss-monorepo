"""Derived edges with the other packages: the wrappers of `pangloss-library` (an identification a person made is read
through; a weighted alternative and a toolchain's suggestion qualify), suggestions confirmed and documents checked
with `pangloss-review`, and a version restored with `pangloss-history`"""

import importlib
from types import SimpleNamespace
from typing import Annotated, no_type_check

import pangloss_core.settings as core_settings
import pytest
from pangloss_models import (
    Document,
    Entity,
    Match,
    Rel,
    Through,
    ToolchainRun,
    hooks,
    initialise,
)
from pangloss_testing.live import run

from pangloss_derived import (
    DerivedEdge,
    Object,
    PerJustification,
    RuleType,
    Subject,
    SymmetricLabel,
    Var,
    read,
    rule,
)
from pangloss_derived.worker import run_pending_derivations

pytestmark = pytest.mark.asyncio(loop_scope="session")

RUN = ToolchainRun("extractor", version="1.2")


@no_type_check
def models(reviewable: bool = False, likely: bool = False):
    # (the registry was reset, and a module is only run once: the packages' models are declared again)
    import pangloss_library.models
    import pangloss_review.models
    from pangloss_review import ReviewMeta

    importlib.reload(pangloss_review.models)
    importlib.reload(pangloss_library.models)
    library = pangloss_library.models
    Alternatives = library.WeightedAlternative
    Identification = library.Identification
    Suggested = library.IdentificationByToolchain

    class Person(Entity):
        pass

    class Group(Entity):
        pass

    class MemberOf(Document):
        _meta = Document.Meta(create_directly=False)
        member: (
            Person
            | Identification[Alternatives[Person]]
            | Suggested[Alternatives[Person]]
        )
        group: Group

    class Joined(Document):
        _meta = Document.Meta(create_directly=False)
        member: Person | Identification[Person]
        group: Group

    class Factoid(Document):
        _review_meta = ReviewMeta(reviewable=reviewable)
        statements: list[MemberOf | Joined]

    family = RuleType("family", "Ties of family")

    class SameGroup(DerivedEdge):
        _meta = DerivedEdge.Meta(symmetric=True)
        first: Annotated[Person, SymmetricLabel("member")]
        second: Annotated[Person, SymmetricLabel("member")]
        group: Group

    @rule(types=[family])
    def same_group(a: Var[Person], b: Var[Person], g: Var[Group]):
        return SameGroup.Derive(first=a, second=b, group=g).when(
            MemberOf.Where(member=a, group=g),
            MemberOf.Where(member=b, group=g),
        )

    @rule(types=[family])
    def joined_same_group(a: Var[Person], b: Var[Person], g: Var[Group]):
        return SameGroup.Derive(first=a, second=b, group=g).when(
            MemberOf.Where(member=a, group=g),
            Joined.Where(member=b, group=g),
        )

    LikelyMember = None
    if likely:
        # (the library's shares, as a rule reads them: only an alternative of 60 per cent or more, and the share kept
        # on each justification)
        class LikelyMember(DerivedEdge):
            """Is likely a member of"""

            person: Annotated[Person, Subject()]
            group: Annotated[Group, Object(reverse_name="likely_members")]
            likelihood: Annotated[int, PerJustification()]

        @rule(types=[family])
        def likely_member(a: Var[Person], g: Var[Group], p: Var[int]):
            return LikelyMember.Derive(person=a, group=g, likelihood=p).when(
                MemberOf.Where(
                    member=Rel(
                        is_=a,
                        through=[
                            Through(
                                Alternatives, edge=library.Likelihood.Where(percent=p)
                            )
                        ],
                    ),
                    group=g,
                ),
                p >= 60,
                allow=[Alternatives],
            )

    initialise()
    return SimpleNamespace(
        Person=Person,
        Group=Group,
        Factoid=Factoid,
        SameGroup=SameGroup,
        LikelyMember=LikelyMember,
    )


async def entities(m):
    n = {}
    for name in "ABCDE":
        n[name] = await m.Person.Create(label=name).save()
    n["G"] = await m.Group.Create(label="G").save()
    return n


def weighted(*shares):
    return [
        {
            "type": "WeightedAlternative",
            "alternatives": [
                {
                    "type": "Person",
                    "id": who.id,
                    "edge_properties": {"percent": percent},
                }
                for who, percent in shares
            ],
        }
    ]


def member(group, who, kind="MemberOf"):
    return {
        "type": kind,
        "label": "m",
        "member": who,
        "group": {"type": "Group", "id": group.id},
    }


def plainly(who):
    return {"type": "Person", "id": who.id}


async def ties(m):
    page = await read.list_facts(m.SameGroup, page_size=100)
    return sorted(
        (*sorted([v.first.label, v.second.label]), tuple(v.context_labels), v.plain)
        for v in page["results"]
    )


async def toolchain(db_driver) -> None:
    from pangloss_users import service

    run(db_driver, "MERGE (:PGUser {username: 'ann'})")
    await service.create_toolchain("extractor")


@no_type_check
async def test_the_wrappers_of_the_library_through_which_an_edge_is_or_is_not_plain(
    clear_database, db_driver
):
    from pangloss_review import identify

    m = models()
    n = await entities(m)
    await toolchain(db_driver)
    g = n["G"]
    await m.Factoid.Create(label="F1", statements=[member(g, plainly(n["A"]))]).save()
    # (a person's identification of one of two, each with its share)
    await m.Factoid.Create(
        label="F2",
        statements=[
            member(
                g,
                {
                    "type": "Identification",
                    "target": weighted((n["B"], 60), (n["C"], 40)),
                },
            )
        ],
    ).save()
    # (a person's identification of one person: nothing in the way)
    await m.Factoid.Create(
        label="F3",
        statements=[
            member(
                g,
                {"type": "Identification", "target": [plainly(n["D"])]},
                kind="Joined",
            )
        ],
    ).save()
    # (a toolchain's suggestion)
    await m.Factoid.Create(
        label="F4",
        statements=[
            member(
                g,
                {
                    "type": "IdentificationByToolchain",
                    "target": weighted((n["E"], 100)),
                },
            )
        ],
    ).save(created_by=["ann"], toolchain=RUN)
    await run_pending_derivations()
    doubted = ("WeightedAlternative",)
    guessed = ("IdentificationByToolchain", "WeightedAlternative")
    assert await ties(m) == [
        # (not B with C: one alternative at a time. Nor B or C with E: each is doubted, and so is their tie)
        ("A", "B", doubted, False),
        ("A", "C", doubted, False),
        ("A", "D", (), True),
        ("A", "E", guessed, False),
        ("B", "D", doubted, False),
        ("B", "E", guessed, False),
        ("C", "D", doubted, False),
        ("C", "E", guessed, False),
        ("D", "E", guessed, False),
    ]
    # (the share is kept with the justification)
    page = await read.list_facts(
        m.SameGroup, m.SameGroup.Where(first=n["A"], second=n["B"])
    )
    detail = await read.get_fact(m.SameGroup, page["results"][0].id)
    (why,) = detail.justifications
    assert {"percent": 60} in [r["properties"] for r in why.context.relations]
    assert (await read.list_facts(m.SameGroup, m.SameGroup.Where(plain=True)))[
        "count"
    ] == 1

    # (a person confirms the suggestion: it is an identification of theirs, and no longer a machine's guess)
    (suggestion,) = (await identify.list_suggestions()).results
    await identify.confirm(suggestion.id, "ann")
    await run_pending_derivations()
    labels = {(a, b): context for a, b, context, _ in await ties(m) if "E" in (a, b)}
    assert set(labels) == {("A", "E"), ("B", "E"), ("C", "E"), ("D", "E")}
    assert all(
        "IdentificationByToolchain" not in context for context in labels.values()
    )


@no_type_check
async def test_an_edge_is_seen_when_a_justification_rests_on_published_documents(
    clear_database, db_driver
):
    from pangloss_review import ReviewStatus, service
    from pangloss_users import see_unpublished

    m = models(reviewable=True)
    n = await entities(m)
    run(db_driver, "MERGE (:PGUser {username: 'reviewer'})")
    g = n["G"]
    f1 = await m.Factoid.Create(
        label="F1", statements=[member(g, plainly(n["A"]))]
    ).save()
    f2 = await m.Factoid.Create(
        label="F2", statements=[member(g, plainly(n["B"]))]
    ).save()
    await run_pending_derivations()

    async def seen_by_a_reader():
        token = see_unpublished.set(False)
        try:
            section = await read.derived_of_entity(m.Person, n["A"].id)
            found = await m.Person.search(m.Person.Where(derived_=m.SameGroup.Where()))
            return (
                len(await ties(m)),
                sorted(section),
                sorted(p.label for p in found.results),
            )
        finally:
            see_unpublished.reset(token)

    # (derived from documents not yet checked: there for who is logged in, not for a reader)
    assert len(await ties(m)) == 1
    assert await seen_by_a_reader() == (0, [], [])
    await service.set_status(f1.id, ReviewStatus.PUBLISHED, "reviewer")
    assert await seen_by_a_reader() == (0, [], [])
    # (both checked: seen at once, with nothing for the worker to do)
    await service.set_status(f2.id, ReviewStatus.PUBLISHED, "reviewer")
    assert await seen_by_a_reader() == (1, ["SameGroup"], ["A", "B"])
    # (errors found in one: hidden at once)
    await service.set_status(f2.id, ReviewStatus.ERRORS_FOUND, "reviewer")
    assert await seen_by_a_reader() == (0, [], [])
    assert len(await ties(m)) == 1
    # (said again by a checked document: seen through that justification, though the other is hidden)
    f3 = await m.Factoid.Create(
        label="F3", statements=[member(g, plainly(n["B"]))]
    ).save()
    await service.set_status(f3.id, ReviewStatus.PUBLISHED, "reviewer")
    await run_pending_derivations()
    assert await seen_by_a_reader() == (1, ["SameGroup"], ["A", "B"])
    token = see_unpublished.set(False)
    try:
        (tie,) = (await read.list_facts(m.SameGroup))["results"]
        detail = await read.get_fact(m.SameGroup, tie.id)
        # (a reader is shown only the justification they may see)
        assert [sorted(e.label for e in j.evidence) for j in detail.justifications] == [
            ["F1", "F3"]
        ]
    finally:
        see_unpublished.reset(token)
    assert len((await read.get_fact(m.SameGroup, tie.id)).justifications) == 2


@pytest.fixture
def history(tmp_path, monkeypatch):
    from pangloss_history import listener
    from pangloss_history.store import SqliteStore

    path = tmp_path / "h.sqlite3"

    def start():
        settings = core_settings.SETTINGS

        class WithHistory:
            """The settings of the test, and those of history"""

            HISTORY_DB_PATH = str(path)
            HISTORY_BATCH_MS = 1

            def __getattr__(self, name):
                return getattr(settings, name)

        monkeypatch.setattr(core_settings, "SETTINGS", WithHistory(), raising=False)
        listener.reset_recorder()
        listener.install()
        return SqliteStore(path)

    yield start
    listener.reset_recorder()
    hooks.after_write[:] = [h for h in hooks.after_write if h is not listener.on_write]


@no_type_check
async def test_a_restored_version_brings_its_edges_back(clear_database, history):
    from pangloss_history.restore import restore

    m = models()
    store = history()
    n = await entities(m)
    g = n["G"]
    factoid = await m.Factoid.Create(
        label="F",
        statements=[member(g, plainly(n["A"])), member(g, plainly(n["B"]))],
    ).save()
    await run_pending_derivations()
    assert [t[:2] for t in await ties(m)] == [("A", "B")]
    await m.Factoid.Update(
        id=factoid.id, label="F", statements=[member(g, plainly(n["A"]))]
    ).save()
    await run_pending_derivations()
    assert await ties(m) == []
    # (the first version again: a write as any other, so the worker derives from it)
    await restore(store, m.Factoid, factoid.id, 1)
    await run_pending_derivations()
    assert [t[:2] for t in await ties(m)] == [("A", "B")]


# ---------------------------------------------------------------------------
# The library's shares, read by a rule
# ---------------------------------------------------------------------------


@no_type_check
async def test_a_rule_reads_the_share_of_a_weighted_alternative(clear_database):
    """The plan's example: through an alternative only when it is likely enough, the share kept on the justification;
    and a share moved by an update (the others give way, as the library has it) moves what is derived"""
    m = models(likely=True)
    n = await entities(m)
    A, B, C, G = n["A"], n["B"], n["C"], n["G"]

    def identified(*shares):
        return {
            "type": "Identification",
            "identified_by": "Smith",
            "target": weighted(*shares),
        }

    first = await m.Factoid.Create(
        label="F1", statements=[member(G, identified((A, 70), (B, 30)))]
    ).save()
    await m.Factoid.Create(
        label="F2", statements=[member(G, identified((A, 60), (B, 25), (C, 15)))]
    ).save()
    await m.Factoid.Create(label="F3", statements=[member(G, plainly(C))]).save()
    await run_pending_derivations()

    async def likely():
        found = {}
        for view in (await read.list_facts(m.LikelyMember, page_size=100))["results"]:
            detail = await read.get_fact(m.LikelyMember, view.id)
            found[view.person.label] = (
                sorted(
                    (j.values["likelihood"], j.evidence[0].label)
                    for j in detail.justifications
                ),
                view.plain,
            )
        return found

    # (C, said plainly, passes through no alternative; the edge is through a wrapper that qualifies: not plain)
    assert await likely() == {"A": ([(60, "F2"), (70, "F1")], False)}
    # (read from the group, by the reverse name)
    section = await read.derived_of_entity(m.Group, G.id)
    assert section["likely_members"]["count"] == 1
    assert [row["other"]["label"] for row in section["likely_members"]["items"]] == [
        "A"
    ]
    # (the shares of the first change places)
    await m.Factoid.Update(
        id=first.id, label="F1", statements=[member(G, identified((A, 20), (B, 80)))]
    ).save()
    await run_pending_derivations()
    assert await likely() == {
        "A": ([(60, "F2")], False),
        "B": ([(80, "F1")], False),
    }
    # (and a search by the share, of the documents themselves: the same edge model, as `edge=`)
    found = await m.Factoid.search(
        Match(
            where={
                "$mentions": {
                    "is": str(B.id),
                    "through": [
                        {
                            "type": "WeightedAlternative",
                            "edge": {
                                "type": "Likelihood",
                                "where": {"percent": {"gte": 60}},
                            },
                        }
                    ],
                }
            }
        )
    )
    assert [item.label for item in found.results] == ["F1"]


# ---------------------------------------------------------------------------
# Derived documents, with review and with history
# ---------------------------------------------------------------------------


@no_type_check
def factoids(own_review: bool = False):
    """Factoids that are reviewed, and derived ones, which share their parent (and so its `ReviewMeta`)"""
    import pangloss_review.models
    from pangloss_review import ReviewMeta

    from pangloss_derived import DerivedDocument, DerivedFrom

    importlib.reload(pangloss_review.models)

    class Person(Entity):
        pass

    class AbstractFactoid(Document):
        _meta = Document.Meta(abstract=True)
        _review_meta = ReviewMeta(reviewable=True)
        about: list[Person]

    class Factoid(AbstractFactoid):
        pass

    if own_review:

        class DerivedFactoid(AbstractFactoid, DerivedDocument):
            _review_meta = ReviewMeta(reviewable=True)
            sources: list[DerivedFrom[Factoid]]

    else:

        class DerivedFactoid(AbstractFactoid, DerivedDocument):
            sources: list[DerivedFrom[Factoid]]

    initialise()
    return SimpleNamespace(**locals())


@no_type_check
async def test_a_derived_document_is_never_reviewed_whatever_its_parent_says(
    clear_database, db_driver
):
    from pangloss_review import is_reviewable, service
    from pangloss_users import see_unpublished

    from pangloss_derived import writing_derived

    m = factoids()
    assert is_reviewable(m.Factoid) and is_reviewable(m.AbstractFactoid)
    assert not is_reviewable(m.DerivedFactoid)
    assert "Factoid" in service.reviewable_types()
    assert "DerivedFactoid" not in service.reviewable_types()
    a = await m.Person.Create(label="A").save()
    written = await m.Factoid.Create(label="Written", about=[]).save()
    with writing_derived("some_rule"):
        derived = await m.DerivedFactoid.Create(
            label="Derived",
            about=[{"type": "Person", "id": a.id}],
            sources=[{"type": "Factoid", "id": written.id}],
        ).save()
    # (a reader who is not logged in does not see what waits to be reviewed; a derived document does not wait)
    token = see_unpublished.set(False)
    try:
        assert await m.Factoid.get(written.id) is None
        assert (await m.DerivedFactoid.get(derived.id)).label == "Derived"
    finally:
        see_unpublished.reset(token)


@no_type_check
async def test_a_derived_class_that_says_it_is_reviewable_is_refused(clear_database):
    from pangloss_derived import PanglossDerivedError

    with pytest.raises(PanglossDerivedError) as refused:
        factoids(own_review=True)
    assert "DerivedFactoid: a derived document class is not reviewable" in str(
        refused.value
    )


@no_type_check
async def test_a_version_of_a_derived_document_is_restored_only_by_the_worker(
    clear_database, history
):
    import asyncio

    from pangloss_history.restore import restore

    from pangloss_derived import PanglossDerivedDocumentError, writing_derived

    m = factoids()
    store = history()
    with writing_derived("some_rule"):
        derived = await m.DerivedFactoid.Create(
            label="First", about=[], sources=[]
        ).save()
        await m.DerivedFactoid.Update(
            id=derived.id, label="Second", about=[], sources=[]
        ).save()
    await asyncio.sleep(0.1)
    # (a restore is an update: by a person it is refused, as any other write of one)
    with pytest.raises(PanglossDerivedDocumentError, match="not changed by hand"):
        await restore(store, m.DerivedFactoid, derived.id, 1)
    assert (await m.DerivedFactoid.get(derived.id)).label == "Second"
    with writing_derived("some_rule"):
        await restore(store, m.DerivedFactoid, derived.id, 1)
    assert (await m.DerivedFactoid.get(derived.id)).label == "First"


@no_type_check
def reviewed_family(citing: bool = False):
    """Factoids that are reviewed, of statements; and a rule that derives a factoid from two of them. `citing`: a
    factoid can cite others as its evidence, and there are notes, reviewed too, that cite what they read"""
    import pangloss_review.models
    from pangloss_review import ReviewMeta

    from pangloss_derived import DerivedDocument, DerivedFrom, unordered

    importlib.reload(pangloss_review.models)

    class Person(Entity):
        pass

    class Statement(Document):
        _meta = Document.Meta(abstract=True, create_directly=False)

    class ChildOf(Statement):
        child: Person
        parent: Person

    class Sibling(Statement):
        people: list[Person]

    class AbstractFactoid(Document):
        _meta = Document.Meta(abstract=True)
        _review_meta = ReviewMeta(reviewable=True)
        statements: list[Statement]

    if citing:
        from pangloss_models import Cites

        class Factoid(AbstractFactoid):
            evidence: list[Cites[AbstractFactoid]] = []
            first_source: Cites[AbstractFactoid] | None = None

    else:

        class Factoid(AbstractFactoid):
            pass

    class DerivedFactoid(AbstractFactoid, DerivedDocument):
        sources: list[DerivedFrom[Factoid]]

    if citing:

        class Note(Document):
            _review_meta = ReviewMeta(reviewable=True)
            evidence: list[Cites[AbstractFactoid]] = []

        class Jotting(Document):
            """Cites as a note does, and is not reviewed"""

            evidence: list[Cites[AbstractFactoid]] = []

    @rule
    def siblings(a: Var[Person], b: Var[Person], p: Var[Person]):
        return DerivedFactoid.Derive(
            label="Siblings",
            statements=[Sibling.Template(label="Siblings", people=[a, b])],
        ).when(
            ChildOf.Where(child=a, parent=p),
            ChildOf.Where(child=b, parent=p),
            unordered(a, b),
            block=[DerivedFactoid],
        )

    initialise()
    return SimpleNamespace(**locals())


async def a_family(m):
    people = {
        name: await m.Person.Create(label=name).save() for name in ("A", "B", "P")
    }
    factoids = {}
    # (a factoid that can cite cites nothing)
    extra = {"evidence": []} if "evidence" in m.Factoid.Create.model_fields else {}
    for child in "AB":
        factoids[child] = await m.Factoid.Create(
            **extra,
            label=f"{child} of P",
            statements=[
                {
                    "type": "ChildOf",
                    "label": "c",
                    "child": {"type": "Person", "id": people[child].id},
                    "parent": {"type": "Person", "id": people["P"].id},
                }
            ],
        ).save()
    return people, factoids


@no_type_check
async def test_a_derived_document_is_published_when_its_sources_have_been_checked(
    clear_database, db_driver
):
    from pangloss_review import ReviewStatus, service
    from pangloss_users import see_unpublished

    m = reviewed_family()
    run(db_driver, "MERGE (:PGUser {username: 'reviewer'})")
    people, factoids = await a_family(m)
    await run_pending_derivations()
    (derived,) = (await m.DerivedFactoid.list()).results

    async def a_reader_sees():
        token = see_unpublished.set(False)
        try:
            return await m.DerivedFactoid.get(derived.id) is not None
        finally:
            see_unpublished.reset(token)

    # (neither factoid has been checked: what follows from them is not shown either)
    assert not await a_reader_sees()
    await service.set_status(factoids["A"].id, ReviewStatus.PUBLISHED, "reviewer")
    await run_pending_derivations()
    assert not await a_reader_sees()
    # (the second is checked: the change of status is what tells the worker)
    await service.set_status(factoids["B"].id, ReviewStatus.PUBLISHED, "reviewer")
    await run_pending_derivations()
    assert await a_reader_sees()
    # (it was never among what is to be reviewed, and review does not take it)
    for status in ReviewStatus:
        queued = await service.queue(statuses=[status])
        assert derived.id not in [item.id for item in queued.results]
    from pangloss_review import PanglossNotReviewableError

    with pytest.raises(PanglossNotReviewableError):
        await service.set_status(derived.id, ReviewStatus.UNCHECKED, "reviewer")
    # (errors found in a source: unpublished again, and what rests on it with it)
    await service.set_status(factoids["A"].id, ReviewStatus.ERRORS_FOUND, "reviewer")
    await run_pending_derivations()
    assert not await a_reader_sees()
    rows = run(
        db_driver,
        "MATCH (h:HeadNode {id: $id}) OPTIONAL MATCH (h)<-[:is_update_of]-(u) "
        "RETURN h.review_status AS status, h.published AS published, count(u) AS updates",
        id=str(derived.id),
    )
    # (its status is the worker's: no review status, and no version made by being published and unpublished)
    assert rows == [{"status": None, "published": False, "updates": 0}]


@no_type_check
async def test_the_versions_of_a_derived_document_are_the_worker_s(
    clear_database, history
):
    import asyncio

    m = reviewed_family()
    store = history()
    people, factoids = await a_family(m)
    await run_pending_derivations()
    (derived,) = (await m.DerivedFactoid.list()).results
    # (looked at again, with nothing changed: no version)
    await m.Factoid.Update(
        id=factoids["A"].id,
        label="A of P, checked",
        statements=[
            s.model_dump(mode="json")
            for s in (await m.Factoid.get(factoids["A"].id)).statements
        ],
    ).save()
    await run_pending_derivations()
    await asyncio.sleep(0.1)
    (first,) = store.versions(derived.id)
    assert (first.op, first.version, first.who) == ("create", 1, "derived")

    # (a source deleted, and back: deleted and undeleted by the worker, its content never written again)
    await m.Factoid.delete(factoids["B"].id)
    await run_pending_derivations()
    await m.Factoid.undelete(factoids["B"].id)
    await run_pending_derivations()
    await asyncio.sleep(0.1)
    records = store.versions(derived.id)
    assert [(r.op, r.who) for r in records] == [
        ("create", "derived"),
        ("delete", "derived"),
        ("undelete", "derived"),
    ]
    assert (await m.DerivedFactoid.get(derived.id)).label == "Siblings"


# ---------------------------------------------------------------------------
# Notices: what review is told of a document (converted; a derivation it cites lost)
# ---------------------------------------------------------------------------


async def open_comments(id, resolved=False):
    from pangloss_review import service

    return await service.list_comments(id, include_resolved=resolved)


@no_type_check
async def test_a_converted_document_keeps_its_status_and_has_a_notice(
    clear_database, db_driver
):
    from pangloss_review import ReviewStatus, service
    from pangloss_users import current_request_username

    from pangloss_derived import convert

    m = reviewed_family(citing=True)
    run(db_driver, "MERGE (:PGUser {username: 'reviewer'})")
    people, factoids = await a_family(m)
    for factoid in factoids.values():
        await service.set_status(factoid.id, ReviewStatus.PUBLISHED, "reviewer")
    await run_pending_derivations()
    (derived,) = (await m.DerivedFactoid.list()).results

    form = await convert.prefill("DerivedFactoid", derived.id, "Factoid")
    # (its sources are citations of the form: in the first field that takes them, a field of one taking one)
    initial = form["initial"]
    assert sorted(c["targetId"] for c in initial["evidence"]) == sorted(
        str(f.id) for f in factoids.values()
    )
    assert {c["type"] for c in initial["evidence"]} == {"PGCitation"}
    assert "firstSource" not in initial
    token = current_request_username.set("reviewer")
    try:
        await convert.convert(
            "DerivedFactoid", derived.id, "Factoid", initial, form["version"]
        )
    finally:
        current_request_username.reset(token)

    own = await m.Factoid.get(derived.id)
    assert sorted(c.target_id for c in own.evidence) == sorted(
        f.id for f in factoids.values()
    )
    assert {c.type for c in own.evidence} == {"PGCitation"}
    # (and they are protected now, as anything cited is)
    from pangloss_models.exceptions import PanglossCitedError

    with pytest.raises(PanglossCitedError):
        await m.Factoid.delete(factoids["A"].id)

    # it was published (its sources were), and stays so; whoever reviews it is told what it was
    state = await service.get_state(derived.id)
    assert state.published and state.status == ReviewStatus.PUBLISHED
    (comment,) = await open_comments(derived.id)
    assert comment.kind == "converted" and comment.username == "reviewer"
    assert "DerivedFactoid" in comment.text and "siblings" in comment.text
    assert comment.target_id is None
    # (the queue of what is published has it, and alone among those with something open)
    published = await service.queue(statuses=[ReviewStatus.PUBLISHED])
    assert len(published.results) == 3
    noticed = await service.queue(statuses=[ReviewStatus.PUBLISHED], commented=True)
    assert [(item.id, item.open_comments) for item in noticed.results] == [
        (derived.id, 1)
    ]
    assert noticed.count == 1
    assert (await service.queue(commented=True)).results == []
    # resolved as any comment is
    await service.resolve_comment(derived.id, comment.id, "reviewer")
    assert await open_comments(derived.id) == []
    noticed = await service.queue(statuses=[ReviewStatus.PUBLISHED], commented=True)
    assert noticed.results == []


@no_type_check
async def test_a_source_goes_into_a_field_that_takes_one(clear_database, db_driver):
    """With no list that takes them, the first source is the one a field of one is given"""
    from pangloss_derived import convert

    m = reviewed_family(citing=True)
    people, factoids = await a_family(m)
    sources = [
        {"target_id": str(f.id), "target_type": "Factoid", "target_state": "there"}
        for f in factoids.values()
    ]

    class OnlyOne:
        _meta = SimpleNamespace(
            fields={"first_source": m.Factoid._meta.fields["first_source"]}
        )

    given = convert.cited_sources(OnlyOne, sources)
    assert given["first_source"]["target_id"] == sources[0]["target_id"]
    # (one that is gone, or of a class no field takes, is left to the person)
    gone = [{**sources[0], "target_state": "removed"}]
    assert convert.cited_sources(m.Factoid, gone) == {}
    other = [{**sources[0], "target_type": "Person"}]
    assert convert.cited_sources(m.Factoid, other) == {}
    assert convert.cited_sources(m.Note, sources)["evidence"][1]["type"] == "PGCitation"
    assert [name for name, _, _ in convert.citing_fields(m.Factoid)] == [
        "evidence",
        "first_source",
    ]
    assert convert.citing_fields(m.DerivedFactoid) == []


@no_type_check
async def test_a_document_that_cites_a_lost_derivation_has_a_notice(
    clear_database, db_driver
):
    from pangloss_models.citations import acknowledging
    from pangloss_review import ReviewStatus, service

    m = reviewed_family(citing=True)
    run(db_driver, "MERGE (:PGUser {username: 'reviewer'})")
    people, factoids = await a_family(m)
    await run_pending_derivations()
    (derived,) = (await m.DerivedFactoid.list()).results
    cite = [{"type": "DerivedFactoid", "id": derived.id}]
    note = await m.Note.Create(label="Note", evidence=cite).save()
    jotting = await m.Jotting.Create(label="Jotting", evidence=cite).save()
    await service.set_status(note.id, ReviewStatus.PUBLISHED, "reviewer")
    assert await open_comments(note.id) == []

    with acknowledging("removals"):
        await m.Factoid.delete(factoids["B"].id)
    await run_pending_derivations()
    (basis,) = (await m.Note.get(note.id)).evidence
    assert basis.derivation_state == "lost"
    (comment,) = await open_comments(note.id)
    assert comment.kind == "derivation_lost" and comment.username == "pangloss"
    assert comment.target_id == basis.id and comment.target_label == "Siblings"
    assert comment.text == "A derivation this document cites no longer holds: Siblings"
    # (D15: it stays published; and one of a class that is not reviewed has no comments to have one among)
    state = await service.get_state(note.id)
    assert state.published and state.status == ReviewStatus.PUBLISHED
    rows = run(
        db_driver,
        "MATCH (c:PGReviewComment)-[:comment_on]->(h {id: $id}) RETURN c.id AS id",
        id=str(jotting.id),
    )
    assert rows == []
    assert (await m.Jotting.get(jotting.id)).evidence[0].derivation_state == "lost"

    # the derivation is back: nothing to look at any more
    await m.Factoid.undelete(factoids["B"].id)
    await run_pending_derivations()
    assert (await m.Note.get(note.id)).evidence[0].derivation_state == ""
    assert await open_comments(note.id) == []
    (resolved,) = await open_comments(note.id, resolved=True)
    assert resolved.resolved and resolved.resolved_by == "pangloss"

    # lost again: the same comment, open again (one notice of a kind about a part)
    with acknowledging("removals"):
        await m.Factoid.delete(factoids["B"].id)
    await run_pending_derivations()
    (again,) = await open_comments(note.id)
    assert again.id == comment.id and not again.resolved and again.resolved_by is None
    assert len(await open_comments(note.id, resolved=True)) == 1

    # its author has seen it, and saves the note with the mark off: the notice goes with it
    read = (await m.Note.get(note.id)).model_dump(mode="json")
    evidence = read["evidence"]
    evidence[0]["derivation_state"] = ""
    await m.Note.Update(id=note.id, label="Note", evidence=evidence).save()
    assert (await m.Note.get(note.id)).evidence[0].derivation_state == ""
    assert await open_comments(note.id) == []


@no_type_check
async def test_a_notice_goes_when_the_citation_is_removed_and_a_change_has_its_own(
    clear_database, db_driver
):
    from pangloss_models.citations import acknowledging

    m = reviewed_family(citing=True)
    people, factoids = await a_family(m)
    extra = await m.Person.Create(label="Z").save()
    await run_pending_derivations()
    (derived,) = (await m.DerivedFactoid.list()).results
    note = await m.Note.Create(
        label="Note", evidence=[{"type": "DerivedFactoid", "id": derived.id}]
    ).save()

    # (the derivation changes, and stays: said as that. The statement is the node it was, saying something else)
    statement = (await m.Factoid.get(factoids["B"].id)).statements[0].id
    with acknowledging(True):
        await m.Factoid.Update(
            id=factoids["B"].id,
            label="Z of P",
            evidence=[],
            statements=[
                {
                    "type": "ChildOf",
                    "id": statement,
                    "label": "c",
                    "child": {"type": "Person", "id": extra.id},
                    "parent": {"type": "Person", "id": people["P"].id},
                }
            ],
        ).save()
    await run_pending_derivations()
    (comment,) = await open_comments(note.id)
    assert comment.kind == "derivation_changed"
    assert comment.text.startswith("A derivation this document cites has changed")
    # (then it is lost: the one notice about it says what it is now)
    with acknowledging("removals"):
        await m.Factoid.delete(factoids["A"].id)
    await run_pending_derivations()
    (comment,) = await open_comments(note.id)
    assert comment.kind == "derivation_lost"
    kinds = sorted(c.kind for c in await open_comments(note.id, resolved=True))
    assert kinds == ["derivation_changed", "derivation_lost"]
    # the citation is taken out of the note
    await m.Note.Update(id=note.id, label="Note", evidence=[]).save()
    assert await open_comments(note.id) == []


@no_type_check
async def test_the_filter_is_offered_where_some_documents_are_derived(clear_database):
    from pangloss_models import ModelRegistry
    from pangloss_models.search_where import export_search_patterns

    m = reviewed_family()
    people, factoids = await a_family(m)
    await run_pending_derivations()
    (derived,) = (await m.DerivedFactoid.list()).results
    patterns = export_search_patterns(ModelRegistry._models)
    assert patterns["AbstractFactoid"]["flags"] == ["$derived_document"]
    assert "flags" not in patterns["Factoid"]
    assert "flags" not in patterns["DerivedFactoid"]

    async def found(where):
        results = (await m.AbstractFactoid.search(Match(where=where))).results
        return sorted(str(r.id) for r in results)

    assert await found({"$derived_document": True}) == [str(derived.id)]
    assert await found({"$derived_document": False}) == sorted(
        str(f.id) for f in factoids.values()
    )
    assert len(await found({})) == 3


@no_type_check
async def test_the_routes_of_conversion(clear_database, db_driver):
    import httpx2 as httpx
    from pangloss_api import create_app
    from pangloss_api.dependencies import get_current_user
    from pangloss_users import current_request_username

    from pangloss_review import ReviewStatus, service

    m = reviewed_family(citing=True)
    run(db_driver, "MERGE (:PGUser {username: 'reviewer'})")
    run(db_driver, "MERGE (:PGUser {username: 'someone'})")
    people, factoids = await a_family(m)
    # (checked, so that what is derived from them is published: a request here is seen as anyone's)
    for factoid in factoids.values():
        await service.set_status(factoid.id, ReviewStatus.PUBLISHED, "reviewer")
    await run_pending_derivations()
    (derived,) = (await m.DerivedFactoid.list()).results
    app = create_app()
    at = f"/api/derived/convert/DerivedFactoid/{derived.id}/Factoid"

    async def someone():
        current_request_username.set("someone")
        return SimpleNamespace(username="someone", admin=False, disabled=False)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        # (not for someone who is not logged in)
        assert (await client.get(at)).status_code == 401
        refused = await client.post(
            "/api/derived/convert",
            json={
                "model": "DerivedFactoid",
                "id": str(derived.id),
                "to": "Factoid",
                "version": 1,
                "data": {},
            },
        )
        assert refused.status_code == 401
        cleared = f"/api/derived/document/Factoid/{derived.id}/clear-context"
        assert (await client.post(cleared)).status_code == 401

        app.dependency_overrides[get_current_user] = someone
        # "derived from this", of a source
        rows = (
            await client.get(
                f"/api/Factoid/{factoids['A'].id}/cited", params={"unprotected": "true"}
            )
        ).json()
        assert [(r["id"], r["type"]) for r in rows] == [
            (str(derived.id), "DerivedFactoid")
        ]
        why_it_is = (
            await client.get(f"/api/derived/document/DerivedFactoid/{derived.id}")
        ).json()
        assert why_it_is["convertsTo"] == ["Factoid"] and not why_it_is["converted"]

        form = await client.get(at)
        assert form.status_code == 200
        form = form.json()
        assert form["type"] == "Factoid" and form["derivedBy"] == "siblings"
        assert len(form["sources"]) == 2 and len(form["initial"]["evidence"]) == 2
        missing = await client.get(
            f"/api/derived/convert/DerivedFactoid/{derived.id}/Person"
        )
        assert missing.status_code == 400
        assert (await client.post(cleared)).status_code == 404

        # what the form gives is checked as any save is: said at its fields
        bad = await client.post(
            "/api/derived/convert",
            json={
                "model": "DerivedFactoid",
                "id": str(derived.id),
                "to": "Factoid",
                "version": form["version"],
                "data": {**form["initial"], "statements": "none"},
            },
        )
        assert bad.status_code == 422
        assert bad.json()["detail"][0]["loc"][:3] == ["body", "data", "statements"]
        assert await m.DerivedFactoid.get(derived.id) is not None

        # (someone else wrote it since the form was read)
        stale = await client.post(
            "/api/derived/convert",
            json={
                "model": "DerivedFactoid",
                "id": str(derived.id),
                "to": "Factoid",
                "version": form["version"] + 5,
                "data": form["initial"],
            },
        )
        assert stale.status_code in (409, 412), stale.text

        made = await client.post(
            "/api/derived/convert",
            json={
                "model": "DerivedFactoid",
                "id": str(derived.id),
                "to": "Factoid",
                "version": form["version"],
                "data": form["initial"],
            },
        )
        assert made.status_code == 200, made.text
        assert made.json() == {
            "id": str(derived.id),
            "type": "Factoid",
            "label": "Siblings",
        }
        item = (await client.get(f"/api/Factoid/{derived.id}")).json()
        assert [c["type"] for c in item["evidence"]] == ["PGCitation"] * 2
        assert (
            await client.get(f"/api/DerivedFactoid/{derived.id}")
        ).status_code == 404
        why_it_is = (
            await client.get(f"/api/derived/document/Factoid/{derived.id}")
        ).json()
        assert why_it_is["converted"] and why_it_is["convertedBy"] == "someone"
        assert why_it_is["holds"] and why_it_is["convertsTo"] == []
        # (twice: it is not a derived document any more)
        again = await client.get(at)
        assert again.status_code == 400
        # its context is cleared (it had none: still what it is), and only of one made from a derivation
        answer = await client.post(cleared)
        assert answer.status_code == 200 and answer.json()["context"] == []
        other = f"/api/derived/document/Factoid/{factoids['A'].id}/clear-context"
        assert (await client.post(other)).status_code == 404
        derived_class = (
            f"/api/derived/document/DerivedFactoid/{derived.id}/clear-context"
        )
        assert (await client.post(derived_class)).status_code == 400
        # (the sources are cited now: no longer "derived from this")
        rows = (
            await client.get(
                f"/api/Factoid/{factoids['A'].id}/cited", params={"unprotected": "true"}
            )
        ).json()
        assert rows == []
        cited = (await client.get(f"/api/Factoid/{factoids['A'].id}/cited")).json()
        assert [r["id"] for r in cited] == [str(derived.id)]
