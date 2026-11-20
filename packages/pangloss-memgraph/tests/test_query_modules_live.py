"""Query modules put into Memgraph by `backend.install_query_module` (Memgraph only: `Capabilities.query_modules`)"""

import pytest
from pangloss_core.storage import PanglossStorageError
from pangloss_memgraph.databases.memgraph import backend

pytestmark = pytest.mark.asyncio(loop_scope="session")

GREETING = """import mgp


@mgp.read_proc
def greet(ctx: mgp.ProcCtx, name: str) -> mgp.Record(text=str):
    return mgp.Record(text="{word} " + name)
"""

MATHS = "def double(x):\n    return 2 * x\n"

USES_MATHS = """import mgp
import pg_test_maths


@mgp.function
def twice(x: int) -> int:
    return pg_test_maths.double(x)
"""


def greeting(word: str) -> str:
    return GREETING.replace("{word}", word)


def module_files(db_driver) -> dict[str, str]:
    """The files of the tests' modules (`pg_test_...`): name -> path"""
    with db_driver.session() as session:  # (not in a transaction)
        rows = session.run("CALL mg.get_module_files() YIELD path RETURN path").data()
    return {
        path.rsplit("/", 1)[-1].removesuffix(".py"): path
        for path in (row["path"] for row in rows)
        if path.rsplit("/", 1)[-1].startswith("pg_test_")
    }


@pytest.fixture
def no_test_modules(db_driver):
    """None of the tests' modules before the test, nor after it, however it ends"""

    def delete() -> None:
        with db_driver.session() as session:
            for path in module_files(db_driver).values():
                session.run("CALL mg.delete_module_file($path)", path=path).consume()

    delete()
    yield
    delete()


def call(db_driver, cypher: str, **parameters) -> list[dict]:
    with db_driver.session() as session:
        return session.run(cypher, parameters).data()


def modified(db_driver, name: str) -> str:
    """The text of the module as the database has it"""
    rows = call(
        db_driver,
        "CALL mg.get_module_file($path) YIELD content RETURN content",
        path=module_files(db_driver)[name],
    )
    return rows[0]["content"]


async def test_a_module_is_installed_and_callable_at_once(db_driver, no_test_modules):
    assert await backend.install_query_module("pg_test_greeting", greeting("Hello"))
    rows = call(db_driver, "CALL pg_test_greeting.greet('Ann') YIELD text RETURN text")
    assert rows == [{"text": "Hello Ann"}]


async def test_the_same_text_again_writes_nothing(db_driver, no_test_modules):
    assert await backend.install_query_module("pg_test_greeting", greeting("Hello"))
    path = module_files(db_driver)["pg_test_greeting"]
    assert not await backend.install_query_module(
        "pg_test_greeting", greeting("Hello"), expects=["greet"]
    )
    assert module_files(db_driver) == {"pg_test_greeting": path}
    assert modified(db_driver, "pg_test_greeting") == greeting("Hello")


async def test_changed_text_replaces_the_module(db_driver, no_test_modules):
    await backend.install_query_module("pg_test_greeting", greeting("Hello"))
    assert await backend.install_query_module("pg_test_greeting", greeting("Goodbye"))
    rows = call(db_driver, "CALL pg_test_greeting.greet('Ann') YIELD text RETURN text")
    assert rows == [{"text": "Goodbye Ann"}]
    assert modified(db_driver, "pg_test_greeting") == greeting("Goodbye")


async def test_a_module_may_import_another_installed_beside_it(
    db_driver, no_test_modules
):
    # (a module of helpers alone has no procedure: it is a library)
    assert await backend.install_query_module("pg_test_maths", MATHS, library=True)
    assert await backend.install_query_module(
        "pg_test_uses_maths", USES_MATHS, expects=["twice"]
    )
    assert call(db_driver, "RETURN pg_test_uses_maths.twice(21) AS n") == [{"n": 42}]
    # (the helpers changed: seen by the module that imports them)
    await backend.install_query_module(
        "pg_test_maths", MATHS.replace("2 *", "3 *"), library=True
    )
    assert call(db_driver, "RETURN pg_test_uses_maths.twice(21) AS n") == [{"n": 63}]


async def test_a_module_whose_import_fails_is_refused_by_name(
    db_driver, no_test_modules
):
    broken = "import mgp\nimport pg_test_no_such_module_anywhere\n\n" + greeting(
        "Hello"
    ).removeprefix("import mgp\n")
    with pytest.raises(PanglossStorageError) as raised:
        await backend.install_query_module("pg_test_broken", broken)
    message = str(raised.value)
    assert "pg_test_broken" in message
    assert "did not load" in message and "log" in message


async def test_a_name_that_is_expected_and_missing_is_named(db_driver, no_test_modules):
    with pytest.raises(PanglossStorageError) as raised:
        await backend.install_query_module(
            "pg_test_greeting", greeting("Hello"), expects=["greet", "wave", "bow"]
        )
    message = str(raised.value)
    assert "pg_test_greeting" in message
    assert "has no wave, bow" in message and "(it has greet)" in message


async def test_a_module_name_must_be_a_name():
    for name in ("pg_test_x.py", "pg-test", "", "a/b"):
        with pytest.raises(ValueError, match="cannot be the name of a query module"):
            await backend.install_query_module(name, MATHS, library=True)
