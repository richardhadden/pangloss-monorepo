"""Neo4j's own text for parts of the kit's queries (`Dialect.query`), where the kit's is slow on Neo4j"""

from pangloss_models import Document, Entity

from pangloss_cypher import fragments
from pangloss_cypher.list_query import LISTED_HEAD


def plain_page(object_class: type[Document | Entity]) -> str:
    """`list.plain.page`: the nodes of the page of a plain list, ordered by id, as `n`, with the number of them all
    (`total`).

    An entity has no head node: its tests are of itself, and the lookup of a head node that is never there is left out. The
    class is scanned once, for the ids and their number; the ids of the page are found among them, and only those nodes are
    read. (The ids are sorted whole and sliced: with `SKIP`/`LIMIT` after the `ORDER BY` Neo4j plans a `Top` of the skip and
    the limit together, which ran out of memory for a skip of about 2,500 ids)"""
    head: str | fragments.HeadOf
    if object_class.__metatype__ == "Entity":
        looking, head = "", "n"
    else:
        head = LISTED_HEAD
        looking = head.match
    visible = f"WHERE {fragments.visible('n', head, filters=True)}"
    return f"""
            MATCH (n:$($node_type))
            // (what has been deleted is not listed: a deleted entity, or a node of a deleted document)
            {looking}
            WITH n{"" if not looking else ", listed_head"}
            {visible}
            WITH count(n) AS total, collect(n.id) AS ids
            CALL (ids) {{
              UNWIND ids AS listed_id
              WITH listed_id
              ORDER BY listed_id
              WITH collect(listed_id) AS sorted_ids
              RETURN sorted_ids[($page_number - 1) * $page_size .. $page_number * $page_size] AS page_ids
            }}
            UNWIND page_ids AS page_id
            MATCH (n:PGIndexableNode {{id: page_id}})
            WITH n, total
            ORDER BY n.id
            """


QUERIES = {"list.plain.page": plain_page}
