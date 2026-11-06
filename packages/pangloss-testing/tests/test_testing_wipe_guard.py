"""The tests empty the database they are pointed at: not one that looks like somebody's data
(`pangloss_testing.live.refuse_to_empty_real_data`)"""

import pytest
from pangloss_testing.live import REAL_DATA_NODES, refuse_to_empty_real_data


class Counted:
    """(a driver that only counts: there are `nodes` in its database)"""

    def __init__(self, nodes: int):
        self.nodes = nodes
        self.asked: list[str] = []

    def execute_query(self, query: str, **kwargs):
        self.asked.append(query)
        return [{"nodes": self.nodes}], None, None


def test_a_database_with_a_great_deal_in_it_is_not_emptied(monkeypatch):
    monkeypatch.delenv("PANGLOSS_TEST_WIPE", raising=False)
    # (what a test run leaves behind, and an empty database: go ahead)
    for nodes in (0, 2_500, REAL_DATA_NODES):
        refuse_to_empty_real_data(Counted(nodes), "bolt://localhost:7687", "memgraph")
    # a project's data: the run stops, and says why and what to do
    with pytest.raises(pytest.exit.Exception) as stopped:
        refuse_to_empty_real_data(Counted(337_423), "bolt://localhost:7687", "memgraph")
    said = str(stopped.value)
    assert "337,423 nodes" in said and "bolt://localhost:7687" in said
    assert "PANGLOSS_TEST_WIPE=1" in said and "another port" in said
    assert stopped.value.returncode == 3


def test_it_is_emptied_when_told_to(monkeypatch):
    monkeypatch.setenv("PANGLOSS_TEST_WIPE", "1")
    driver = Counted(337_423)
    refuse_to_empty_real_data(driver, "bolt://localhost:7687", "memgraph")
    # (not even counted)
    assert driver.asked == []
