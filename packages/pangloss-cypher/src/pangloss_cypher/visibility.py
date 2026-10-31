"""Who may see what has not been published"""

from pangloss_users import see_unpublished


def unpublished_visible() -> bool:
    """Whether the request in progress may see documents that are not published: a node with no `published`
    property is published, and a request that is not logged in does not see the others"""
    return see_unpublished.get()
