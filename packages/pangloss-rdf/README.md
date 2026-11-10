# pangloss-rdf

🚧 Optional: every document and entity as RDF, and an ontology made from the models. See [implementation_docs/rdf.md](../../implementation_docs/rdf.md) and
the [guide](../../guide/rdf/README.md); the design is in [implementation_docs/rdf-export-plan.md](../../implementation_docs/rdf-export-plan.md).

```python
from pangloss_rdf import RDFMeta


class Person(Entity):
    _rdf_meta = RDFMeta(class_name="HistoricalPerson")
```

Item URIs start with the `ENTITY_BASE_URL` setting: `{ENTITY_BASE_URL}/Person/{uuid}`. Classes and properties are under
`RDF_ONTOLOGY_URL` (optional; by default `{ENTITY_BASE_URL}/ontology/`): `.../ontology/Person`,
`.../ontology/Activity.carriedOutBy`, named after the class that first declares the field.
