Modelling issues
================

## Problems:

### How to distinguish (if this categorisation works at all) and model it:

1. Specific individual roles ("Prime Minister of the UK")

(Person)-[has_role]->(SpecificRole)-[has_type]->(RoleType)

2. 'Multi-tenant' roles — poeta laureata, Maximilian's secretary

(Person)-[has_role]->(SpecificRole)-[has_type]->(RoleType) 
  # Same as 1

(Person)-[has_role]->(OneOfSpecificRole)-[is_one_of]->(SpecificRole)-[has_type]->(RoleType) 
  - how do you bloody know it's not 1.?
  - Can't transform-on-duplication, as it could be contradiction not multi-tenancy
  - So just use 1? (Maaybe people know? And can add a 'multi-tenancy' flag to a role when creating?)

3. Generic roles ("prime minister")

Using TypedSingleton[T[Role], T[Typology]]

(Person)-[has_role]->(RoleTypedSingleton)-[has_type]->(RoleType)
  - RoleTypedSingleton is not strictly necessary, but it makes the path isomorphic to 1 and 2.

4. Person role-ing

Can't do anything with this: it's socially determined whether it's a role (position) or doing-thing
  - should have allowed more AusübungEinerTätigkeit-ing, and by sheer weight of it (past some threshold) declare that it's a role (of type 2?)
