"""Values as the driver gives them"""

import typing


def native_datetime(value: typing.Any) -> typing.Any:
    """Convert a neo4j DateTime to a Python datetime"""
    return value.to_native() if hasattr(value, "to_native") else value
