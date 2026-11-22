"""The suite every part of similarity passes (implementation_docs/vectors.md, "The suite of a part"): `PartSuite`,
which a part's test module subclasses. The claims, on `pangloss_testing.similar_models` and the backend under test,
for each part it names, against the part's *slow way* (the vectors a whole rebuild would give now, by item id):

- after each kind of write (`writes.WRITES`), the other workers (criteria, derived) and **one turn** of the vectors'
  worker, the part's stored vectors in use are the slow way's, to `tolerance`, of exactly the same ids; and nothing a
  write took away (`writes.GONE`) keeps a vector of any part;
- the same after a delete and its undelete, a merge and its undo, a publish and an unpublish under both values of
  `VECTORS_GRAPH_SEES`;
- **an overlay equals the same payload written**: `part.overlay(plan)` of a `Create` writes nothing, and gives, for
  the ids it answers for, the vectors stored once that payload is written and the worker has turned; it answers for
  the head when the head then has a vector;
- **a rebuild under writes loses none**: what is written while a (slowed) rebuild runs is all reflected after it and
  one turn.
"""

import asyncio
from collections.abc import Awaitable, Callable, Mapping, Sequence
from typing import Any, ClassVar, no_type_check

import pytest

from pangloss_testing.live import run
from pangloss_testing.parts import writes
from pangloss_testing.parts.writes import WRITES

# The vectors a whole rebuild of a part would give now, by item id (lists of floats or numpy arrays)
type Slow = Callable[[Any], Awaitable[Mapping[str, Any]]]

# The workers other than the vectors', whose work a write may leave
OTHER_KINDS = ("criteria", "derive")

# The apps `pangloss_testing.similar_models` is declared with, and similarity's own
APPS = [
    "pangloss_derived",
    "pangloss_library",
    "pangloss_criteria",
    "pangloss_vectors",
]


def installed_apps(*more: str) -> list[str]:
    """`INSTALLED_APPS` for the suite, with the part's own package (`installed_apps("pangloss_fastrp")`): for the
    `installed_apps` fixture of the conftest of the tests that call it"""
    return APPS + [app for app in more if app not in APPS]


def settings_extras(**more: tuple[Any, Any]) -> dict[str, tuple[Any, Any]]:
    """The settings the suite changes, and more of the part's own (`FASTRP_REFRESH_CAP=(int, 50_000)`): for the
    `settings_extras` fixture of the conftest"""
    return {
        "VECTORS_PROFILES": (dict | None, None),
        "VECTORS_GRAPH_SEES": (str, "everyone"),
        "VECTORS_REBUILD_AFTER": (int | None, None),
        **more,
    }


# ---------------------------------------------------------------------------
# What the claims are made of
# ---------------------------------------------------------------------------


def differences(
    have: Mapping[str, Any], want: Mapping[str, Any], tolerance: float = 1e-5
) -> list[str]:
    """What differs between stored vectors and those wanted, in words (empty if nothing)"""
    import numpy as np

    found = []
    for of in sorted(set(have) - set(want)):
        found.append(f"{of}: stored, and the slow way has none")
    for of in sorted(set(want) - set(have)):
        found.append(f"{of}: the slow way has one, and none is stored")
    for of in sorted(set(have) & set(want)):
        gap = float(
            np.max(np.abs(np.asarray(have[of], dtype=float) - np.asarray(want[of])))
        )
        if gap > tolerance:
            found.append(f"{of}: differs by {gap:.2e}")
    return found


def drop_vector_indexes(db_driver) -> None:
    """The tests' own vector indexes dropped (the database is emptied between tests, its indexes are not), and on
    Memgraph the deleted nodes collected (it keeps them in a vector index)"""
    from pangloss_testing.backends import under_test

    backend = under_test()
    with db_driver.session(database=backend.database) as session:
        # (not in a transaction: Memgraph refuses its list in one)
        if backend.name == "neo4j":
            names = [
                r["name"]
                for r in session.run(
                    "SHOW INDEXES YIELD name, type WHERE type = 'VECTOR' RETURN name"
                ).data()
            ]
        else:
            names = [
                r["index_name"] for r in session.run("SHOW VECTOR INDEX INFO").data()
            ]
        for name in names:
            if name.startswith("pgv_"):
                drop = (
                    f"DROP INDEX {name} IF EXISTS"
                    if backend.name == "neo4j"
                    else f"DROP VECTOR INDEX {name}"
                )
                session.run(drop).consume()
        if backend.name == "memgraph":
            session.run("FREE MEMORY").consume()


async def stored(db_driver, part_name: str) -> dict[str, list[float]]:
    """The part's vectors in use, by item (none if it was never built)"""
    from pangloss_vectors import store

    state = (await store.states()).parts.get(part_name)
    if state is None:
        return {}
    return {
        row["of"]: row["vector"]
        for row in run(
            db_driver,
            "MATCH (v:PGVector {part: $part, generation: $generation}) RETURN v.of AS of, v.vector AS vector",
            part=part_name,
            generation=state.generation,
        )
    }


def vectors_left(db_driver, ids: Sequence[str]) -> list[str]:
    """Which of these ids have a vector of any part or profile"""
    return sorted(
        row["of"]
        for row in run(
            db_driver,
            "MATCH (v) WHERE (v:PGVector OR v:PGProfileVector) AND v.of IN $ids RETURN DISTINCT v.of AS of",
            ids=list(ids),
        )
    )


def others_pending(db_driver) -> int:
    return run(
        db_driver,
        "MATCH (p:PGPending) WHERE p.kind IN $kinds RETURN count(p) AS n",
        kinds=list(OTHER_KINDS),
    )[0]["n"]


async def the_others_done(db_driver) -> None:
    """The criteria and derived workers run until neither has work (each may leave work for the other)"""
    from pangloss_criteria import run_pending as criteria_pending
    from pangloss_derived.worker import run_pending_derivations

    for _ in range(6):
        await criteria_pending()
        await run_pending_derivations()
        if not others_pending(db_driver):
            return
    raise AssertionError("the criteria and derived workers did not settle")


async def one_turn(db_driver) -> int:
    """The other workers, then one turn of the vectors' worker; nothing of the kind left. Gives the heads done"""
    from pangloss_vectors.worker import run_pending

    await the_others_done(db_driver)
    done = await run_pending()
    left = run(db_driver, "MATCH (p:PGPending {kind: 'vectors'}) RETURN count(p) AS n")
    assert left[0]["n"] == 0, "heads still pending for the vectors after one turn"
    return done


def node_count(db_driver) -> int:
    return run(db_driver, "MATCH (n) RETURN count(n) AS n")[0]["n"]


# The payloads of the claim of an overlay, by name: a document (with a nested reified relation, a wrapper with a
# relation of its own, a class below a wrapper, and a citation) and an entity
@no_type_check
def overlay_payload(m, ids: dict[str, str], name: str) -> Any:
    ref = writes.ref_to
    if name == "a person":
        return m.Person.Create(label="Hal")
    return m.Factoid.Create(
        label="a meeting overlaid",
        statements=[
            {
                "type": "Activity",
                "label": "Gus met Ada and Fay",
                "carried_out_by": ref(ids["Gus"]),
                "participants": [
                    {
                        "type": "InRole",
                        "role": "guest",
                        "at": ref(ids["place"], "Place"),
                        "target": [ref(ids["Ada"])],
                    },
                    {"type": "Sworn", "role": "witness", "target": [ref(ids["Fay"])]},
                ],
            },
            {
                "type": "Inference",
                "label": "So Gus knew Ben",
                "evidence": [{"type": "Transfer", "id": ids["transfer"]}],
            },
        ],
    )


OVERLAID = ("a factoid", "a person")


# ---------------------------------------------------------------------------
# The suite
# ---------------------------------------------------------------------------


class PartSuite:
    """The claims every part passes, as tests of a subclass in a part's test module:

        from pangloss_testing.parts import PartSuite

        class TestTheNamePart(PartSuite):
            parts = {"name": names_rebuilt}       # each part checked, with its slow way

    `parts`: the parts checked after every step, by name, each with its slow way, `async def slow(db_driver)`: the
    vectors a whole rebuild would give now, by id. Every registered part is rebuilt; those named are checked.
    `tolerance`: how far a stored number may be from the slow way's (`tolerances`: of a part, by its name). `also`: more claims of the subclass's own after
    each step. The conftest gives the apps and settings (`installed_apps`, `settings_extras` of this module)."""

    pytestmark: ClassVar = [pytest.mark.asyncio(loop_scope="session")]

    parts: ClassVar[Mapping[str, Slow]] = {}
    tolerance: ClassVar[float] = 1e-5
    tolerances: ClassVar[Mapping[str, float]] = {}

    def tolerance_of(self, name: str) -> float:
        return self.tolerances.get(name, self.tolerance)

    async def also(self, step: str, m: Any, ids: dict[str, str], database: Any) -> None:
        """More claims after a step, by its name (`"after a create"`, ..., `"deleted"`, `"undeleted"`, `"merged"`,
        `"unmerged"`, `"saved unpublished"`, `"published"`, `"unpublished"`, `"overlaid a factoid"`,
        `"rebuilt under writes"`): nothing here. `ids` are `write_shapes`'s, with `"secret"` (the factoid saved
        unpublished), `"overlaid"` (the head of an overlay's payload)"""

    @pytest.fixture
    def database(self, db_driver, clear_database):
        """(the database emptied, and the vector indexes the tests made dropped, before and after)"""
        drop_vector_indexes(db_driver)
        yield db_driver
        drop_vector_indexes(db_driver)

    async def as_the_slow_way(self, database) -> None:
        """Every part named has stored the slow way's vectors, of exactly its ids"""
        assert self.parts, "the suite names no part (`parts = {name: slow}`)"
        for name, slow in self.parts.items():
            found = differences(
                await stored(database, name),
                await slow(database),
                self.tolerance_of(name),
            )
            assert found == [], f"the {name} part: {found}"

    async def checked(self, step: str, m: Any, ids: dict[str, str], database) -> None:
        await self.as_the_slow_way(database)
        await self.also(step, m, ids, database)

    @no_type_check
    async def built(self, m, database, **saved) -> dict[str, str]:
        """The shapes written, every part rebuilt, and the marks of the writes worked off (so a test starts equal)"""
        from pangloss_vectors.rebuild import rebuild

        ids = await writes.write_shapes(m, database, **saved)
        await rebuild()
        await one_turn(database)
        await self.checked("built", m, ids, database)
        return ids

    # -- after each kind of write --

    @pytest.mark.parametrize("write", list(WRITES))
    @no_type_check
    async def test_after_a_write_and_one_turn_the_stored_vectors_are_the_slow_way_s(
        self, database, write
    ):
        from pangloss_testing.similar_models import declare

        m = declare()
        ids = await self.built(m, database)
        await WRITES[write](m, ids)
        assert await one_turn(database) > 0
        await self.checked(f"after {write}", m, ids, database)
        gone = [ids[name] for name in writes.GONE.get(write, ())]
        assert vectors_left(database, gone) == [], "what the write took away"

    @no_type_check
    async def test_after_a_delete_nothing_of_it_keeps_a_vector_and_after_its_undelete_the_vectors_are_the_slow_way_s(
        self, database
    ):
        from pangloss_testing.similar_models import declare

        m = declare()
        ids = await self.built(m, database)
        await m.Factoid.delete(ids["meeting"])
        await one_turn(database)
        await self.checked("deleted", m, ids, database)
        assert vectors_left(database, [ids["meeting"], ids["activity"]]) == []
        await m.Factoid.undelete(ids["meeting"])
        await one_turn(database)
        await self.checked("undeleted", m, ids, database)

    @no_type_check
    async def test_after_a_merge_the_absorbed_keeps_no_vector_and_after_its_undo_the_vectors_are_the_slow_way_s(
        self, database
    ):
        from pangloss_testing.similar_models import declare

        m = declare()
        ids = await self.built(m, database)
        merged = await m.Person.merge(absorb=ids["Eve"], into=ids["Dee"])
        await one_turn(database)
        await self.checked("merged", m, ids, database)
        assert vectors_left(database, [ids["Eve"]]) == []
        await m.Person.unmerge(merged.merge.id)
        await one_turn(database)
        await self.checked("unmerged", m, ids, database)

    @pytest.mark.parametrize("sees", ["everyone", "logged_in"])
    @no_type_check
    async def test_after_a_publish_and_an_unpublish_the_vectors_are_the_slow_way_s(
        self, database, monkeypatch, sees
    ):
        """(under each value of `VECTORS_GRAPH_SEES`)"""
        pytest.importorskip("pangloss_review")
        import pangloss_core.settings as core_settings
        from pangloss_review.service import set_status
        from pangloss_review.status import ReviewStatus
        from pangloss_users import current_request_username

        from pangloss_testing.similar_models import declare

        monkeypatch.setattr(core_settings.SETTINGS, "VECTORS_GRAPH_SEES", sees)
        m = declare(reviewed=True)
        ids = await self.built(m, database, published=True)
        secret = await m.Factoid.Create(
            label="secret",
            statements=[writes.transfer(writes.people(ids, "Ada", "Ben", "Cy"))],
        ).save()
        ids["secret"] = str(secret.id)
        await one_turn(database)
        await self.checked("saved unpublished", m, ids, database)
        user = current_request_username.get()
        await set_status(secret.id, ReviewStatus.PUBLISHED, user)
        assert await one_turn(database) > 0
        await self.checked("published", m, ids, database)
        await set_status(secret.id, ReviewStatus.UNCHECKED, user)
        assert await one_turn(database) > 0
        await self.checked("unpublished", m, ids, database)

    # -- an overlay --

    @pytest.mark.parametrize("payload", OVERLAID)
    @no_type_check
    async def test_an_overlay_writes_nothing_and_equals_the_same_payload_written(
        self, database, payload
    ):
        """The plan of a `CreateDB`, overlaid by each part, then that same instance written (so its nested ids are the
        plan's) and the worker turned: what each part's overlay gives is what it then stores, and it answers for the
        head if the head then has a vector"""
        from pangloss_cypher.write_functions import to_db_model, write_head_node
        from pangloss_cypher.write_plan import plan_create
        from pangloss_vectors.parts import part

        from pangloss_testing.similar_models import declare

        m = declare()
        ids = await self.built(m, database)
        instance = to_db_model(overlay_payload(m, ids, payload))
        head = str(instance.id)
        ids["overlaid"] = head
        plan = plan_create(instance)
        nodes = node_count(database)
        overlaid = {name: await part(name).overlay(plan) for name in self.parts}
        assert node_count(database) == nodes, "an overlay wrote"
        await write_head_node(instance)
        assert await one_turn(database) > 0
        await self.checked(f"overlaid {payload}", m, ids, database)
        for name, given in overlaid.items():
            have = await stored(database, name)
            assert set(given) <= set(have), (
                f"the {name} part's overlay gives vectors of what has none written: "
                f"{sorted(set(given) - set(have))}"
            )
            found = differences(
                given, {of: have[of] for of in given}, self.tolerance_of(name)
            )
            assert found == [], f"the {name} part's overlay: {found}"
            assert (head in given) == (head in have), (
                f"the {name} part's overlay {'gives' if head in given else 'lacks'} the head's vector, and the "
                f"payload written {'has' if head in have else 'has none'}"
            )

    # -- a rebuild under writes --

    @no_type_check
    async def test_writes_made_during_a_slowed_rebuild_are_all_reflected_after_it_and_one_turn(
        self, database, monkeypatch
    ):
        """The last part a rebuild builds (every part before it has read and written) is held once it has read and
        computed, before it writes; meanwhile writes of every kind, which the worker leaves while the rebuild runs;
        after it and one turn, the vectors are the slow way's"""
        from pangloss_vectors.parts import parts
        from pangloss_vectors.rebuild import rebuild
        from pangloss_vectors.worker import run_pending

        from pangloss_testing.similar_models import declare

        m = declare()
        ids = await self.built(m, database)
        computed, go = asyncio.Event(), asyncio.Event()
        last = list(parts().values())[-1]
        rebuild_last = type(last).rebuild

        async def slowed(self, write) -> int:
            rows: list = []

            async def keep(page) -> None:
                rows.extend(page)

            count = await rebuild_last(self, keep)
            computed.set()
            await go.wait()
            await write(rows)
            return count

        monkeypatch.setattr(type(last), "rebuild", slowed)
        rebuilding = asyncio.create_task(rebuild())
        await asyncio.wait_for(computed.wait(), 30)
        for write in (
            writes.create,
            writes.new_citation,
            writes.update_that_replaces_its_statements,
            writes.update_that_renames_a_person,
        ):
            await write(m, ids)
        await m.Person.merge(absorb=ids["Eve"], into=ids["Dee"])
        await m.Factoid.delete(ids["no gift"])
        # (the worker does nothing while the rebuild runs)
        await the_others_done(database)
        assert await run_pending() == 0
        go.set()
        await asyncio.wait_for(rebuilding, 60)
        monkeypatch.setattr(type(last), "rebuild", rebuild_last)
        assert await one_turn(database) > 0
        await self.checked("rebuilt under writes", m, ids, database)
