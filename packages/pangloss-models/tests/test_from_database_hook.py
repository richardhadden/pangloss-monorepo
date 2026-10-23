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


def test_without_a_converter_data_is_as_it_is():
    data = {"a": Native()}
    assert hooks.convert_from_database(data) is data


def test_a_registered_converter_is_applied():
    hooks.from_database.append(convert)
    try:
        assert hooks.convert_from_database({"a": Native()}) == {
            "a": datetime.datetime(2026, 1, 1)
        }
    finally:
        hooks.from_database.remove(convert)
