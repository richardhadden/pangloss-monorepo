"""Going through every page of a list"""

from collections.abc import AsyncIterator, Iterator
from inspect import isawaitable
from typing import Any


async def iterate(list_function: Any, *args: Any, **kwargs: Any) -> AsyncIterator[Any]:
    """Every item of a list, page after page: `async for p in iterate(Person.list, ...)`.
    (`list_function` is `Person.list`, which is given the other arguments.)"""
    page = kwargs.pop("page_number", 1)
    while page is not None:
        result = list_function(*args, page_number=page, **kwargs)
        if isawaitable(result):
            result = await result
        for item in result.results:
            yield item
        page = result.next_page


def iterate_sync(list_function: Any, *args: Any, **kwargs: Any) -> Iterator[Any]:
    """The same, for the blocking database module"""
    page = kwargs.pop("page_number", 1)
    while page is not None:
        result = list_function(*args, page_number=page, **kwargs)
        yield from result.results
        page = result.next_page
