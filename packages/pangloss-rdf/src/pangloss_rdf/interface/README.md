# Interface module of `pangloss_rdf`

A **View as RDF** button in the console of every item page, next to View as JSON. It opens a small menu of the formats, each
`GET /api/rdf/{type}/{id}?format=...` in a new tab, as plain text so that the browser shows it, and the API's own JSON, which replaces
the console's View as JSON button (`jsonLinkIn` in the manifest).
