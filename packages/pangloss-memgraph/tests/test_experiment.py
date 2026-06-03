def test_database_writing_for_sanity(db_driver):

    db_driver.execute_query("CREATE (node:Node {name: 'Tony'})", database="memgraph")

    records, summary, keys = db_driver.execute_query("MATCH (node:Node) RETURN node")

    assert records[0].data() == {"node": {"name": "Tony"}}
