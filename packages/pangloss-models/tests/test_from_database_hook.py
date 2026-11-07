"""The models do not know the database's types: its module registers a converter"""

import datetime

from pangloss_models import hooks


class Native:
    def to_native(self):
        return datetime.datetime(2026, 1, 1)


def convert(data):
    if isinstance(data, dict):
        return {k: convert(v) for k, v in data.items()}
    return data.to_native() if isinstance(data, Native) else data


def test_without_a_converter_data_is_as_it_is(monkeypatch):
    # (a database module imported in the same run may have added its own)
    monkeypatch.setattr(hooks, "from_database", [])
    data = {"a": Native()}
    assert hooks.convert_from_database(data) is data


def test_a_registered_converter_is_applied(monkeypatch):
    monkeypatch.setattr(hooks, "from_database", [convert])
    assert hooks.convert_from_database({"a": Native()}) == {
        "a": datetime.datetime(2026, 1, 1)
    }


class Counting:
    """A model's validator, standing in: counts how often each value is given to the converter"""

    def __init__(self):
        self.seen = 0

    def __call__(self, data):
        self.seen += 1
        return data.to_native() if isinstance(data, Native) else data


def test_a_converter_is_given_each_value_once_however_deep_the_data(monkeypatch):
    # (every nested model converts what it is made from: without the mark, each level walked its whole
    # subtree again, and a document 60 deep took a second to read)
    counting = Counting()
    monkeypatch.setattr(hooks, "from_database", [counting])
    inner: dict = {"when": Native(), "label": "innermost"}
    for n in range(20):
        inner = {"when": Native(), "label": str(n), "contents": [inner]}
    converted = hooks.convert_from_database(inner)
    leaves = counting.seen
    assert leaves == 21 * 2
    assert converted["contents"][0]["when"] == datetime.datetime(2026, 1, 1)
    # what a nested model is given has been through already: nothing is walked again
    level = converted
    for _ in range(21):
        assert hooks.convert_from_database(level) is level
        level = level["contents"][0] if "contents" in level else level
    assert counting.seen == leaves
