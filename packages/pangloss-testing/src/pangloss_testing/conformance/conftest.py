"""The fixtures of the conformance tests: those of a live test (`pangloss_testing.live`), on the backend under test"""

import pytest
from pangloss_core.storage import load

from pangloss_testing.backends import under_test
from pangloss_testing.live import *  # noqa: F403
from pangloss_testing.live import mark_database_tests


def pytest_itemcollected(item):
    mark_database_tests(item)


def pytest_collection_modifyitems(items):
    """A test that looks underneath with the driver (Cypher) needs a backend that has Cypher"""
    for item in items:
        if "db_driver" in getattr(item, "fixturenames", ()):
            item.add_marker(pytest.mark.requires("cypher"))


def pytest_configure(config):
    config.addinivalue_line(
        "markers", "requires(capability): the backend must have the capability"
    )
    config.addinivalue_line(
        "markers",
        "stored_by_hand: the test writes nodes in a shape the models do not (their paths are not checked)",
    )


@pytest.fixture(autouse=True)
def required_capabilities(request):
    for mark in request.node.iter_markers("requires"):
        capability = mark.args[0]
        if not getattr(load(under_test().storage).capabilities, capability):
            pytest.skip(f"{under_test().name} has no {capability}")


@pytest.fixture(autouse=True)
def paths_are_true(request):
    """After every test that looks underneath: what the test left in the database has true paths
    (`helpers.assert_paths_true`), whatever wrote it (the models, an update, a migration). A test that writes nodes
    by hand, in a shape the models do not write, is marked `stored_by_hand`"""
    if "db_driver" not in request.fixturenames or request.node.get_closest_marker(
        "stored_by_hand"
    ):
        yield
        return
    driver = request.getfixturevalue("db_driver")
    if "clear_database" in request.fixturenames:
        # (asked for first, so that it is cleared after this has looked)
        request.getfixturevalue("clear_database")
    yield
    from pangloss_testing.conformance.helpers import assert_paths_true

    assert_paths_true(driver)
