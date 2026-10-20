"""(what the server asks of a database about migrations)"""

APPLIED: dict = {}


async def applied():
    return dict(APPLIED)
