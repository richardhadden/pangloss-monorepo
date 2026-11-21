"""Phase 4's first trial (step 4.1), by hand on the scratch Memgraph (`:7702`): what is left of a working query
module when it is updated with text that does not load; and what a module can read of a node and an edge.

    uv run python notes/similarity-evaluation/module_trial.py
"""

import neo4j

d = neo4j.GraphDatabase.driver("bolt://localhost:7702", auth=("test", "test"))


def run(q, **p):
    with d.session() as s:
        return [r.data() for r in s.run(q, **p)]


def attempt(said, q, **p):
    try:
        print(said, "->", str(run(q, **p))[:300])
    except Exception as error:  # noqa: BLE001
        print(said, "-> REFUSED:", str(error)[:200])


GOOD = '''
import mgp

@mgp.read_proc
def hello(ctx: mgp.ProcCtx) -> mgp.Record(said=str):
    return mgp.Record(said="one")
'''
BROKEN = GOOD.replace('"one"', '"two"') + "\nimport a_module_that_is_not_there\n"
READS = '''
import mgp

@mgp.read_proc
def shape(ctx: mgp.ProcCtx, ids: mgp.List[str]) -> mgp.Record(id=str, type=mgp.Nullable[str], labels=mgp.List[str], out=mgp.List[mgp.Any]):
    wanted = set(ids)
    found = []
    for vertex in ctx.graph.vertices:
        i = vertex.properties.get("id")
        if i in wanted:
            edges = [[e.type.name, e.to_vertex.properties.get("id"), dict(e.properties.items())] for e in vertex.out_edges]
            found.append(mgp.Record(id=i, type=vertex.properties.get("type"), labels=[l.name for l in vertex.labels], out=edges))
    return found
'''


def names(module):
    return sorted(r["name"] for r in run("CALL mg.procedures() YIELD name RETURN name") if r["name"].startswith(module + "."))


attempt("delete", "CALL mg.delete_module_file('/var/lib/memgraph/internal_modules/pg_trial.py')")
attempt("delete", "CALL mg.delete_module_file('/var/lib/memgraph/internal_modules/pg_reads.py')")
print("== 1. a working module, then text that does not load")
attempt("create", "CALL mg.create_module_file('pg_trial.py', $text) YIELD path RETURN path", text=GOOD)
print("procedures:", names("pg_trial"))
attempt("call", "CALL pg_trial.hello() YIELD said RETURN said")
attempt("update with broken text", "CALL mg.update_module_file('/var/lib/memgraph/internal_modules/pg_trial.py', $text)", text=BROKEN)
print("procedures after:", names("pg_trial"))
attempt("call after", "CALL pg_trial.hello() YIELD said RETURN said")
attempt("the file now", "CALL mg.get_module_file('/var/lib/memgraph/internal_modules/pg_trial.py') YIELD content RETURN content CONTAINS 'not_there' AS broken")
attempt("update with the good text again", "CALL mg.update_module_file('/var/lib/memgraph/internal_modules/pg_trial.py', $text)", text=GOOD)
print("procedures restored:", names("pg_trial"))
attempt("call restored", "CALL pg_trial.hello() YIELD said RETURN said")

print("== 2. what a module reads")
attempt("create", "CALL mg.create_module_file('pg_reads.py', $text) YIELD path RETURN path", text=READS)
ids = [r["id"] for r in run("MATCH (n:PGIndexableNode)-[e]->() WHERE e.computed OR e.percent IS NOT NULL RETURN DISTINCT n.id AS id LIMIT 2")]
attempt("shape", "CALL pg_reads.shape($ids) YIELD id, type, labels, out RETURN type, labels, out", ids=ids)
attempt("delete", "CALL mg.delete_module_file('/var/lib/memgraph/internal_modules/pg_trial.py')")
attempt("delete", "CALL mg.delete_module_file('/var/lib/memgraph/internal_modules/pg_reads.py')")
