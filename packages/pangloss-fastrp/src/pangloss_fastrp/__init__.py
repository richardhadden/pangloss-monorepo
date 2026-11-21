"""The graph part of similarity for Pangloss (an app: `INSTALLED_APPS += ["pangloss_fastrp"]`, with
`pangloss_vectors`): FastRP over the joined graph of documents and entities. `maths.py` is the whole of the
computing, with no database in it. implementation_docs/similarity-build-plan.md, phase 3"""

# (its reader runs Cypher of its own, and its vectors are searched through the backend's vector index)
requires = {"cypher", "vector_index"}
