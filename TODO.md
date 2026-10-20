Partial (started but incomplete)

Semantic spaces through UpdateDB: works and is tested, but the todo.md item is still unticked. This may only need ticking.
Head node type and id through CreateDB / UpdateDB: open in todo.md.
ReifiedRelationDocument has no label, but its ReferenceView still requires one.
Concurrent updates: last write wins, with no version check.
save() with return type "Detail": named in the registry wrapper but not handled by the Memgraph backend.
pangloss-sdk is stubs only, and pangloss-users only has the current_request_username context variable.
Not implemented
REST API / web layer, and authentication, users and permissions.
Permanently removing deleted nodes. Also, an entity marked for deletion isn’t deleted automatically when its last reference goes.
A command-line interface for initialise_database.
Model-layer gaps: optional relations, optional embedded objects, lists of embedded objects or annotated values, and plain dict fields.
The "subtract" type wrapper, Relation[Subject, Object], installed apps / plugin discovery and interface languages.
Other database backends.
Removing debug output (print calls, query dumps to disk) from the Memgraph backend.
Open design questions are in notes/modelling.md: how to model specific, multi-tenant and generic roles, and when an activity becomes a role.
I’d do these next, in this order:
Remove the debug output, since it’s small and affects every write.
Deal with the marked-for-deletion follow-up, which sits right next to the delete and undelete work.
Add the CLI for initialise_database.
Build the REST layer, which is the largest item and the one other pieces depend on.
Which of these do you want to take on?
