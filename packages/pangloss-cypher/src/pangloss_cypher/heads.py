"""Of head nodes (a document or an entity), as they are stored"""

# The version of a head node: 1, and 1 more for each update of it
VERSION_OF_HEAD = "size([(head)<-[:is_update_of]-(update:PGUpdate) | update]) + 1"
