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


@pytest.fixture(autouse=True)
def required_capabilities(request):
    for mark in request.node.iter_markers("requires"):
        capability = mark.args[0]
        if not getattr(load(under_test().storage).capabilities, capability):
            pytest.skip(f"{under_test().name} has no {capability}")
