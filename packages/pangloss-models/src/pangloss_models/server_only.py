"""`@server_only`: a function of a model that only the server can run.

    class Person(Entity):
        @server_only
        async def recompute_ranking(self):
            from my_project.graph import expensive_query   # (the server has this)
            ...

On the server it is the function. In the SDK that the server hands out, **the body is taken out**
(and the imports inside it are not followed, so they need not be available to a client): the
function is there, with its signature, and calling it raises `PanglossServerOnly`. Use it for
what cannot be moved out of the module of the models, such as a method that reads the database.
"""

import typing

F = typing.TypeVar("F", bound=typing.Callable[..., typing.Any])

MARKER = "__pangloss_server_only__"


def server_only(function: F) -> F:
    """Mark a function as one the SDK leaves the body out of. (Put it under `@classmethod` or
    `@staticmethod`, as the nearest decorator to the function.)"""
    setattr(function, MARKER, True)
    return function
